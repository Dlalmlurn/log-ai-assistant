from __future__ import annotations

"""异常检测自动入库 worker。

第一版 worker 从 ClickHouse security_logs 增量读取日志，复用 RuleEngine 生成
AnomalyEvent，并统一写入 anomaly_events。
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Any, Protocol

from src.detection.rules import DetectionContext, RuleEngine
from src.schemas import AnomalyEvent, NormalizedLog


class DetectionStorage(Protocol):
    def list_logs(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        ...

    def insert_anomalies(self, anomalies: list[AnomalyEvent]) -> None:
        ...

    def get_user_baseline(self, user_id: str, *, tenant_id: str | None = None, baseline_date=None) -> dict[str, Any] | None:
        ...

    def query_user_seen_sources(
        self,
        tenant_id: str = "default",
        user_id: str | None = None,
        source_type: str | None = None,
        source_key: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        ...

    def upsert_user_seen_sources(self, sources: list[dict[str, Any]]) -> None:
        ...


@dataclass(frozen=True)
class DetectionRunSummary:
    logs_read: int
    anomalies_detected: int
    anomalies_inserted: int
    last_event_time: datetime | None
    duration_ms: int


class AnomalyDetectorWorker:
    def __init__(
        self,
        *,
        storage: DetectionStorage,
        lookback_minutes: int = 10,
        batch_size: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage
        self.lookback_minutes = lookback_minutes
        self.batch_size = batch_size
        self._clock = clock or _now
        self._last_event_time: datetime | None = None
        self._seen_anomaly_ids: set[str] = set()
        self._engine = RuleEngine()
        self._batch_seen_sources: set[tuple[str, str, str, str]] = set()

    def run_once(self) -> DetectionRunSummary:
        started = time.perf_counter()
        end_time = self._clock()
        start_time = self._start_time(end_time)
        items, total = self.storage.list_logs(
            start_time=start_time,
            end_time=end_time,
            limit=self.batch_size,
            offset=0,
        )
        if total > self.batch_size:
            oldest_page_offset = max(total - self.batch_size, 0)
            items, _total = self.storage.list_logs(
                start_time=start_time,
                end_time=end_time,
                limit=self.batch_size,
                offset=oldest_page_offset,
            )
        logs = [NormalizedLog.model_validate(item) for item in items]
        logs.sort(key=lambda item: item.event_time)

        anomalies = _dedupe_anomalies(self._detect_logs(logs), self._seen_anomaly_ids)
        if anomalies:
            self.storage.insert_anomalies(anomalies)

        self._upsert_seen_sources(logs)

        if logs:
            self._last_event_time = max(item.event_time for item in logs)

        return DetectionRunSummary(
            logs_read=len(logs),
            anomalies_detected=len(anomalies),
            anomalies_inserted=len(anomalies),
            last_event_time=self._last_event_time,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def run_forever(self, *, interval_seconds: int = 30) -> None:
        while True:
            summary = self.run_once()
            print(_summary_line(summary), flush=True)
            time.sleep(interval_seconds)

    def _start_time(self, end_time: datetime) -> datetime:
        if self._last_event_time is not None:
            return self._last_event_time
        return end_time - timedelta(minutes=self.lookback_minutes)

    def _detect_logs(self, logs: list[NormalizedLog]) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []
        for log in logs:
            context = self._context_for_log(log)
            anomalies.extend(self._engine.evaluate_log(log, context))
            source = _source_identity(log)
            if source:
                self._batch_seen_sources.add(source)
        return anomalies

    def _context_for_log(self, log: NormalizedLog) -> DetectionContext:
        source = _source_identity(log)
        baseline = self._baseline_for_log(log)
        deviations = _baseline_deviations(log, baseline)
        if not source:
            return DetectionContext(baseline_deviations=deviations)

        tenant_id, user_id, source_type, source_key = source
        seen_in_batch = source in self._batch_seen_sources
        seen_in_store = bool(
            self.storage.query_user_seen_sources(
                tenant_id=tenant_id,
                user_id=user_id,
                source_type=source_type,
                source_key=source_key,
                limit=1,
            )
        )
        return DetectionContext(
            seen_source=seen_in_batch or seen_in_store,
            baseline_deviations=deviations,
        )

    def _baseline_for_log(self, log: NormalizedLog) -> dict[str, Any] | None:
        if not log.user_id:
            return None
        return self.storage.get_user_baseline(log.user_id, tenant_id=log.tenant_id)

    def _upsert_seen_sources(self, logs: list[NormalizedLog]) -> None:
        sources: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for log in logs:
            source = _source_identity(log)
            if not source:
                continue
            tenant_id, user_id, source_type, source_key = source
            current = sources.get(source)
            if current is None:
                sources[source] = {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_key": source_key,
                    "first_seen_time": log.event_time,
                    "last_seen_time": log.event_time,
                    "seen_count": 1,
                }
            else:
                current["first_seen_time"] = min(current["first_seen_time"], log.event_time)
                current["last_seen_time"] = max(current["last_seen_time"], log.event_time)
                current["seen_count"] = int(current.get("seen_count") or 0) + 1

        if sources:
            self.storage.upsert_user_seen_sources(
                [self._merge_existing_seen_source(source) for source in sources.values()]
            )

    def _merge_existing_seen_source(self, source: dict[str, Any]) -> dict[str, Any]:
        existing = self.storage.query_user_seen_sources(
            tenant_id=str(source["tenant_id"]),
            user_id=str(source["user_id"]),
            source_type=str(source["source_type"]),
            source_key=str(source["source_key"]),
            limit=1,
        )
        if not existing:
            return source

        row = existing[0]
        return {
            **source,
            "first_seen_time": row.get("first_seen_time") or source["first_seen_time"],
            "seen_count": int(row.get("seen_count") or 0) + int(source.get("seen_count") or 0),
        }


def _dedupe_anomalies(
    anomalies: list[AnomalyEvent],
    seen_ids: set[str],
) -> list[AnomalyEvent]:
    result: list[AnomalyEvent] = []
    for anomaly in anomalies:
        if anomaly.event_id in seen_ids:
            continue
        seen_ids.add(anomaly.event_id)
        result.append(anomaly)
    return result


def _source_identity(log: NormalizedLog) -> tuple[str, str, str, str] | None:
    if not log.user_id or not log.src_ip:
        return None
    return (log.tenant_id, log.user_id, "ip", log.src_ip)


def _baseline_deviations(
    log: NormalizedLog,
    baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not baseline:
        return []

    deviations: list[dict[str, Any]] = []
    location_profile = _dict_value(baseline.get("location_profile"))
    time_profile = _dict_value(baseline.get("time_profile"))
    access_profile = _dict_value(baseline.get("access_profile"))

    common_ips = _common_values(location_profile.get("common_ips"))
    if log.src_ip and common_ips and log.src_ip not in common_ips:
        deviations.append(
            {
                "feature": "src_ip",
                "expected": common_ips,
                "actual": log.src_ip,
                "severity": "high",
                "reason": "outside_baseline_common_ips",
            }
        )

    active_hours = _common_values(time_profile.get("active_hours"))
    if active_hours and not _hour_in_ranges(log.event_time.hour, active_hours):
        deviations.append(
            {
                "feature": "event_hour",
                "expected": active_hours,
                "actual": f"{log.event_time.hour:02d}:00",
                "severity": "medium",
                "reason": "outside_baseline_active_hours",
            }
        )

    common_resources = _common_values(access_profile.get("common_resources"))
    if log.resource and common_resources and log.resource not in common_resources:
        deviations.append(
            {
                "feature": "resource",
                "expected": common_resources,
                "actual": log.resource,
                "severity": "high",
                "reason": "outside_baseline_common_resources",
            }
        )

    return deviations


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _common_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("common_values"), list):
        return [str(item) for item in value["common_values"]]
    if isinstance(value.get("value_histogram"), dict):
        return [str(item) for item in value["value_histogram"].keys()]
    return []


def _hour_in_ranges(hour: int, ranges: list[str]) -> bool:
    for item in ranges:
        if _hour_in_range(hour, item):
            return True
    return False


def _hour_in_range(hour: int, value: str) -> bool:
    if "-" not in value:
        return value.startswith(f"{hour:02d}:") or value == str(hour)
    start_raw, end_raw = value.split("-", 1)
    start = _parse_hour(start_raw)
    end = _parse_hour(end_raw)
    if start is None or end is None:
        return False
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _parse_hour(value: str) -> int | None:
    raw = value.strip().split(":", 1)[0]
    if not raw.isdigit():
        return None
    hour = int(raw)
    return hour if 0 <= hour <= 23 else None


def _summary_line(summary: DetectionRunSummary) -> str:
    last = summary.last_event_time.isoformat() if summary.last_event_time else "-"
    return (
        "detector round finished: "
        f"logs_read={summary.logs_read} "
        f"anomalies_detected={summary.anomalies_detected} "
        f"anomalies_inserted={summary.anomalies_inserted} "
        f"last_event_time={last} "
        f"duration_ms={summary.duration_ms}"
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
