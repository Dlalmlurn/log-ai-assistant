from __future__ import annotations

from typing import Any

import requests
from pydantic import BaseModel, Field

from src.config import settings


CONSUMER_GROUP_TOPICS: dict[str, list[str]] = {
    "flink-raw-to-parsed": [settings.kafka_raw_topic],
    "log-ai-consume-to-es": [settings.kafka_parsed_topic, settings.kafka_alert_topic],
}


class HealthResponse(BaseModel):
    kafka: bool
    flink: bool
    elasticsearch: bool
    dashscope_configured: bool
    latest_log_ingest_time: str | None = None
    consumer_lag: dict[str, int] = Field(default_factory=dict)


def get_health_status() -> HealthResponse:
    """REQ-001/REQ-002/REQ-007: expose formal pipeline health to the API layer."""
    kafka_ok = _check_kafka()
    elasticsearch_ok, latest_log_ingest_time = _check_elasticsearch()

    return HealthResponse(
        kafka=kafka_ok,
        flink=_check_flink(),
        elasticsearch=elasticsearch_ok,
        dashscope_configured=bool(settings.dashscope_api_key),
        latest_log_ingest_time=latest_log_ingest_time,
        consumer_lag=_get_consumer_lag() if kafka_ok else _empty_consumer_lag(),
    )


def get_cli_health_payload() -> dict[str, object]:
    """Return the legacy CLI health JSON shape while reusing shared checks."""
    status = get_health_status()
    return {
        "kafka": status.kafka,
        "elasticsearch": status.elasticsearch,
        "flink": status.flink,
        "dashscope_configured": status.dashscope_configured,
        "last_data_update": status.latest_log_ingest_time or "N/A",
    }


def _empty_consumer_lag() -> dict[str, int]:
    return {group_id: 0 for group_id in CONSUMER_GROUP_TOPICS}


def _check_kafka() -> bool:
    try:
        from kafka import KafkaAdminClient

        admin = KafkaAdminClient(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            request_timeout_ms=3000,
            api_version_auto_timeout_ms=3000,
        )
        try:
            admin.list_topics()
            return True
        finally:
            admin.close()
    except Exception:
        return False


def _check_elasticsearch() -> tuple[bool, str | None]:
    try:
        from src.storage import ElasticStorage

        storage = ElasticStorage()
        elasticsearch_ok = storage.health()
        latest_log_ingest_time = _fetch_latest_log_ingest_time(storage) if elasticsearch_ok else None
        return elasticsearch_ok, latest_log_ingest_time
    except Exception:
        return False, None


def _fetch_latest_log_ingest_time(storage: Any) -> str | None:
    try:
        latest = storage.search(
            settings.elasticsearch_log_index,
            query={"match_all": {}},
            size=1,
            sort=[{"ingest_time": "desc"}],
        )
    except Exception:
        return None

    if not latest:
        return None
    value = latest[0].get("ingest_time")
    return str(value) if value else None


def _check_flink() -> bool:
    try:
        resp = requests.get(f"{settings.flink_dashboard_url}/overview", timeout=3)
        return resp.ok
    except Exception:
        return False


def _get_consumer_lag() -> dict[str, int]:
    lags: dict[str, int] = {}
    for group_id, topics in CONSUMER_GROUP_TOPICS.items():
        try:
            lags[group_id] = _get_group_lag(group_id, topics)
        except Exception:
            lags[group_id] = 0
    return lags


def _get_group_lag(group_id: str, topics: list[str]) -> int:
    from kafka import KafkaConsumer, TopicPartition

    consumer = KafkaConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        request_timeout_ms=3000,
        api_version_auto_timeout_ms=3000,
        consumer_timeout_ms=1000,
    )
    try:
        total_lag = 0
        for topic in topics:
            partitions = consumer.partitions_for_topic(topic) or set()
            topic_partitions = [TopicPartition(topic, partition) for partition in partitions]
            if not topic_partitions:
                continue

            end_offsets = consumer.end_offsets(topic_partitions)
            for topic_partition in topic_partitions:
                committed_offset = consumer.committed(topic_partition)
                end_offset = end_offsets.get(topic_partition, 0)
                total_lag += max(0, end_offset - (committed_offset or 0))
        return total_lag
    finally:
        consumer.close()
