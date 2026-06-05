from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.quality.data_quality import build_data_quality_metrics


class FakeStorage:
    def security_logs_table_size_bytes(self) -> int:
        return 500

    def security_log_quality_stats(self, event_ids):
        return {
            "security_logs_count": len(event_ids) - 1,
            "missing_event_time_count": 0,
            "missing_user_id_count": 1,
            "missing_src_ip_count": 0,
            "missing_action_count": 0,
            "missing_result_count": 0,
            "parse_error_count": 1,
        }


def test_build_data_quality_metrics_groups_manifest_by_source(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {
            "event_id": "evt-1",
            "timestamp": "2026-05-31 10:00:00",
            "tenant_id": "default",
            "source_type": "api",
            "raw_file": "logs/api.log",
            "raw_size_bytes": 300,
            "injected_label": "normal",
        },
        {
            "event_id": "evt-2",
            "timestamp": "2026-05-31 10:00:01",
            "tenant_id": "default",
            "source_type": "api",
            "raw_file": "logs/api.log",
            "raw_size_bytes": 200,
            "injected_label": "attack_account_takeover",
        },
    ]
    manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    metrics = build_data_quality_metrics(
        storage=FakeStorage(),
        manifest_path=manifest,
        metric_date=date(2026, 5, 31),
    )

    assert len(metrics) == 1
    metric = metrics[0]
    assert metric.source_type == "api"
    assert metric.generated_count == 2
    assert metric.raw_logs_count == 2
    assert metric.security_logs_count == 1
    assert metric.injected_anomaly_count == 1
    assert metric.injected_high_risk_count == 1
    assert metric.raw_size_bytes == 500
    assert metric.compression_ratio == 1.0
    assert metric.missing_user_id_rate == 1.0
    assert metric.parse_error_rate == 0.5


class RealCountStorage:
    """Storage that exposes real per-(date, source) ClickHouse counts."""

    def security_logs_table_size_bytes(self) -> int:
        return 250

    def security_logs_daily_counts(self, *, metric_date, tenant_id, source_type):
        return {
            "clickhouse_insert_count": 5,
            "parsed_logs_count": 4,
            "parse_error_count": 1,
            "missing_event_time_count": 0,
            "missing_user_id_count": 2,
            "missing_src_ip_count": 1,
            "missing_action_count": 0,
            "missing_result_count": 0,
        }


def test_build_data_quality_metrics_prefers_real_clickhouse_counts(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {
            "event_id": "evt-1",
            "timestamp": "2026-05-31 10:00:00",
            "tenant_id": "default",
            "source_type": "api",
            "raw_file": "logs/api.log",
            "raw_size_bytes": 500,
            "injected_label": "normal",
        },
        {
            "event_id": "evt-2",
            "timestamp": "2026-05-31 10:00:01",
            "tenant_id": "default",
            "source_type": "api",
            "raw_file": "logs/api.log",
            "raw_size_bytes": 500,
            "injected_label": "normal",
        },
    ]
    manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    metrics = build_data_quality_metrics(
        storage=RealCountStorage(),
        manifest_path=manifest,
        metric_date=date(2026, 5, 31),
    )

    assert len(metrics) == 1
    metric = metrics[0]
    # raw count stays manifest-derived; parsed/insert come from ClickHouse and diverge.
    assert metric.raw_logs_count == 2
    assert metric.clickhouse_insert_count == 5
    assert metric.parsed_logs_count == 4
    assert metric.security_logs_count == 4
    # missing rates use the real row count (5) as denominator, not generated_count.
    assert metric.missing_user_id_rate == round(2 / 5, 6)
    assert metric.missing_src_ip_rate == round(1 / 5, 6)
    assert metric.parse_error_rate == round(1 / 5, 6)
