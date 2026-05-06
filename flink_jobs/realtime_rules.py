from __future__ import annotations

import json
from kafka import KafkaConsumer, KafkaProducer

from src.config import settings
from src.detection.rules import RuleEngine
from src.schemas import NormalizedLog


def run_rules_consumer() -> None:
    consumer = KafkaConsumer(
        settings.kafka_parsed_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="python-realtime-rules",
        auto_offset_reset="latest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )
    engine = RuleEngine()

    for msg in consumer:
        try:
            log = NormalizedLog.model_validate(msg.value)
            alerts = engine.evaluate_log(log)
            for alert in alerts:
                producer.send(settings.kafka_alert_topic, alert.model_dump(mode="json"))
        except Exception:
            continue


if __name__ == "__main__":
    run_rules_consumer()
