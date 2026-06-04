"""Anomaly detector worker 的单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.detection.worker import AnomalyDetectorWorker
from src.schemas import AnomalyEvent, NormalizedLog


BASE_TIME = datetime(2026, 6, 4, 10, 0, 0)


def build_log(idx: int, **kwargs: Any) -> dict[str, Any]:
    base = {
        "event_id": f"evt-{idx}",
        "event_time": BASE_TIME + timedelta(seconds=idx),
        "ingest_time": BASE_TIME + timedelta(seconds=idx),
        "tenant_id": "default",
        "source_type": "vpn",
        "log_type": "login",
        "user_id": "alice",
        "src_ip": "8.8.8.8",
        "action": "login",
        "resource": "/login",
        "result": "fail",
        "message": "failed login",
        "raw_log": "raw",
        "risk_tags": [],
        "attrs": {},
    }
    base.update(kwargs)
    return NormalizedLog.model_validate(base).model_dump(mode="json")


class FakeStorage:
    def __init__(
        self,
        logs: list[dict[str, Any]],
        seen_sources: set[tuple[str, str, str, str]] | None = None,
    ) -> None:
        self.logs = logs
        self.seen_sources = seen_sources or set()
        self.list_calls: list[dict[str, Any]] = []
        self.inserted_batches: list[list[AnomalyEvent]] = []
        self.upserted_sources: list[dict[str, Any]] = []

    def list_logs(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        self.list_calls.append(kwargs)
        start_time = kwargs.get("start_time")
        limit = kwargs.get("limit") or len(self.logs)
        offset = kwargs.get("offset") or 0
        items = [
            item
            for item in self.logs
            if start_time is None or NormalizedLog.model_validate(item).event_time > start_time
        ]
        items.sort(key=lambda item: NormalizedLog.model_validate(item).event_time, reverse=True)
        return items[offset:offset + limit], len(items)

    def insert_anomalies(self, anomalies: list[AnomalyEvent]) -> None:
        self.inserted_batches.append(list(anomalies))

    def query_user_seen_sources(
        self,
        tenant_id: str = "default",
        user_id: str | None = None,
        source_type: str | None = None,
        source_key: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        key = (tenant_id, user_id or "", source_type or "", source_key or "")
        if key not in self.seen_sources:
            return []
        return [
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "source_type": source_type,
                "source_key": source_key,
                "first_seen_time": BASE_TIME - timedelta(days=1),
                "last_seen_time": BASE_TIME - timedelta(days=1),
                "seen_count": 3,
            }
        ][:limit]

    def upsert_user_seen_sources(self, sources: list[dict[str, Any]]) -> None:
        self.upserted_sources.extend(sources)
        for item in sources:
            self.seen_sources.add(
                (
                    str(item.get("tenant_id") or "default"),
                    str(item.get("user_id") or ""),
                    str(item.get("source_type") or ""),
                    str(item.get("source_key") or ""),
                )
            )


def test_worker_run_once_inserts_detected_anomalies_and_advances_checkpoint() -> None:
    logs = [build_log(i) for i in range(10)]
    storage = FakeStorage(logs)
    worker = AnomalyDetectorWorker(
        storage=storage,
        lookback_minutes=5,
        batch_size=100,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )

    first = worker.run_once()
    second = worker.run_once()

    assert first.logs_read == 10
    assert first.anomalies_detected > 0
    assert first.anomalies_inserted == first.anomalies_detected
    assert len(storage.inserted_batches) == 1
    assert second.logs_read == 0
    assert second.anomalies_inserted == 0


def test_worker_uses_stable_event_ids_for_detected_anomalies() -> None:
    logs = [build_log(i) for i in range(10)]
    first_storage = FakeStorage(logs)
    second_storage = FakeStorage(logs)

    first_worker = AnomalyDetectorWorker(
        storage=first_storage,
        lookback_minutes=5,
        batch_size=100,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )
    second_worker = AnomalyDetectorWorker(
        storage=second_storage,
        lookback_minutes=5,
        batch_size=100,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )

    first_worker.run_once()
    second_worker.run_once()

    first_ids = [item.event_id for item in first_storage.inserted_batches[0]]
    second_ids = [item.event_id for item in second_storage.inserted_batches[0]]
    assert first_ids == second_ids


def test_worker_processes_oldest_page_first_when_backlog_exceeds_batch_size() -> None:
    logs = [build_log(i) for i in range(12)]
    storage = FakeStorage(logs)
    worker = AnomalyDetectorWorker(
        storage=storage,
        lookback_minutes=5,
        batch_size=5,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )

    worker.run_once()
    worker.run_once()

    assert len(storage.inserted_batches) == 2
    assert storage.list_calls[1]["offset"] == 7
    assert storage.list_calls[3]["offset"] == 2
    assert storage.inserted_batches[0][0].related_event_ids[0] == "evt-4"


def test_worker_uses_seen_sources_to_suppress_known_source_login() -> None:
    logs = [
        build_log(
            1,
            action="login",
            result="success",
            src_ip="10.0.0.7",
            resource="/home",
            message="login success",
        )
    ]
    storage = FakeStorage(
        logs,
        seen_sources={("default", "alice", "ip", "10.0.0.7")},
    )
    worker = AnomalyDetectorWorker(
        storage=storage,
        lookback_minutes=5,
        batch_size=100,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )

    summary = worker.run_once()

    assert summary.anomalies_detected == 0
    assert storage.inserted_batches == []
    assert storage.upserted_sources == [
        {
            "tenant_id": "default",
            "user_id": "alice",
            "source_type": "ip",
            "source_key": "10.0.0.7",
            "first_seen_time": BASE_TIME - timedelta(days=1),
            "last_seen_time": BASE_TIME + timedelta(seconds=1),
            "seen_count": 4,
        }
    ]


def test_worker_records_new_seen_source_after_new_source_login_anomaly() -> None:
    logs = [
        build_log(
            1,
            action="login",
            result="success",
            src_ip="203.0.113.9",
            resource="/home",
            message="login success",
        )
    ]
    storage = FakeStorage(logs)
    worker = AnomalyDetectorWorker(
        storage=storage,
        lookback_minutes=5,
        batch_size=100,
        clock=lambda: BASE_TIME + timedelta(minutes=1),
    )

    summary = worker.run_once()

    assert summary.anomalies_detected == 1
    assert storage.inserted_batches[0][0].reason_codes == ["new_source_ip"]
    assert storage.upserted_sources == [
        {
            "tenant_id": "default",
            "user_id": "alice",
            "source_type": "ip",
            "source_key": "203.0.113.9",
            "first_seen_time": BASE_TIME + timedelta(seconds=1),
            "last_seen_time": BASE_TIME + timedelta(seconds=1),
            "seen_count": 1,
        }
    ]
