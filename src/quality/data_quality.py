from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.schemas import DataQualityMetric
from src.storage import ClickHouseStorage


HIGH_RISK_LABEL_HINTS = (
    "account_takeover",
    "data_exfiltration",
    "credential_stuffing",
    "privilege_abuse",
    "lateral_movement",
)


def load_manifest_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def build_data_quality_metrics(
    *,
    storage: ClickHouseStorage,
    manifest_path: Path,
    metric_date: date | None = None,
) -> list[DataQualityMetric]:
    rows = load_manifest_rows(manifest_path)
    if not rows:
        return []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "default")
        source_type = str(row.get("source_type") or "unknown")
        grouped[(tenant_id, source_type)].append(row)

    table_size = storage.security_logs_table_size_bytes()
    created_at = datetime.now(timezone.utc)
    metrics: list[DataQualityMetric] = []

    for (tenant_id, source_type), items in grouped.items():
        event_ids = [str(item["event_id"]) for item in items if item.get("event_id")]
        stats = storage.security_log_quality_stats(event_ids)
        generated_count = len(items)
        security_logs_count = int(stats.get("security_logs_count") or 0)
        raw_size_bytes = sum(int(item.get("raw_size_bytes") or 0) for item in items)
        parse_error_count = int(stats.get("parse_error_count") or 0)
        injected_labels = [
            str(item.get("injected_label") or "")
            for item in items
            if str(item.get("injected_label") or "") not in {"", "normal"}
        ]
        metric = DataQualityMetric(
            metric_date=metric_date or _manifest_metric_date(items),
            tenant_id=tenant_id,
            source_type=source_type,
            generated_count=generated_count,
            injected_anomaly_count=len(injected_labels),
            injected_high_risk_count=sum(_is_high_risk_label(label) for label in injected_labels),
            raw_logs_count=_raw_line_count(items),
            parsed_logs_count=security_logs_count,
            clickhouse_insert_count=security_logs_count,
            security_logs_count=security_logs_count,
            raw_size_bytes=raw_size_bytes,
            table_size_bytes=table_size,
            compression_ratio=round(raw_size_bytes / table_size, 4) if table_size else 0,
            missing_event_time_rate=_rate(stats.get("missing_event_time_count"), security_logs_count),
            missing_user_id_rate=_rate(stats.get("missing_user_id_count"), security_logs_count),
            missing_src_ip_rate=_rate(stats.get("missing_src_ip_count"), security_logs_count),
            missing_action_rate=_rate(stats.get("missing_action_count"), security_logs_count),
            missing_result_rate=_rate(stats.get("missing_result_count"), security_logs_count),
            parse_error_rate=_rate(parse_error_count, generated_count),
            created_at=created_at,
        )
        metrics.append(metric)

    return sorted(metrics, key=lambda item: (item.tenant_id, str(item.source_type)))


def write_data_quality_metrics(
    *,
    storage: ClickHouseStorage,
    manifest_path: Path,
    metric_date: date | None = None,
) -> list[DataQualityMetric]:
    metrics = build_data_quality_metrics(
        storage=storage,
        manifest_path=manifest_path,
        metric_date=metric_date,
    )
    storage.insert_data_quality_metrics(metrics)
    return metrics


def _manifest_metric_date(items: list[dict[str, Any]]) -> date:
    for item in items:
        raw = item.get("timestamp")
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return datetime.now(timezone.utc).date()


def _raw_line_count(items: list[dict[str, Any]]) -> int:
    by_file: dict[str, int] = defaultdict(int)
    for item in items:
        raw_file = str(item.get("raw_file") or "")
        if raw_file:
            by_file[raw_file] += 1
    return sum(by_file.values()) or len(items)


def _is_high_risk_label(label: str) -> bool:
    lowered = label.lower()
    return any(hint in lowered for hint in HIGH_RISK_LABEL_HINTS)


def _rate(value: Any, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(value or 0) / denominator, 6)
