from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from kafka import KafkaConsumer, KafkaProducer

from src.config import settings
from src.parser.log_parser import normalize_raw_record
from src.schemas import ParseFailure
from src.storage import ClickHouseStorage


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
    storage = ClickHouseStorage()

    count = 0
    for msg in consumer:
        try:
            normalized = normalize_raw_record(msg.value, source_type_hint="vpn")
            producer.send(settings.kafka_parsed_topic, normalized.model_dump(mode="json"))
            count += 1
            if max_messages is not None and count >= max_messages:
                break
        except Exception as exc:
            raw_payload = json.dumps(msg.value, ensure_ascii=False) if not isinstance(msg.value, str) else msg.value
            failure = ParseFailure(
                failure_id=f"parse-{uuid.uuid4()}",
                occurred_at=datetime.now(timezone.utc),
                source_topic=settings.kafka_raw_topic,
                partition=int(msg.partition),
                offset=int(msg.offset),
                raw_payload=raw_payload,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            storage.insert_parse_failure(failure)
            parse_error = normalize_raw_record(
                {
                    "event_id": failure.failure_id,
                    "event_time": failure.occurred_at.isoformat(),
                    "source_type": "system",
                    "log_type": "parse_error",
                    "action": "parse",
                    "result": "error",
                    "message": f"parse_error: {exc}",
                    "raw_log": raw_payload,
                    "risk_tags": ["parse_error"],
                    "attrs": {"failure_id": failure.failure_id, "error": str(exc)},
                },
                source_type_hint="system",
            )
            producer.send(settings.kafka_parsed_topic, parse_error.model_dump(mode="json"))
            count += 1

    producer.flush()
    producer.close()
    consumer.close()
    return count
