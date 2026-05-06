from __future__ import annotations

import json

from kafka import KafkaConsumer, KafkaProducer

from src.config import settings
from src.parser.log_parser import normalize_raw_record


def run_raw_to_parsed_worker(
    max_messages: int | None = None,
    from_beginning: bool = True,
    idle_timeout_ms: int = 5000,
    group_id: str = "python-raw-to-parsed",
) -> int:
    auto_offset_reset = "earliest" if from_beginning else "latest"
    consumer = KafkaConsumer(
        settings.kafka_raw_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=idle_timeout_ms,
    )
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )

    count = 0
    for msg in consumer:
        try:
            normalized = normalize_raw_record(msg.value, source_type_hint="vpn")
            producer.send(settings.kafka_parsed_topic, normalized.model_dump(mode="json"))
            count += 1
            if max_messages is not None and count >= max_messages:
                break
        except Exception:
            continue

    producer.flush()
    producer.close()
    consumer.close()
    return count
