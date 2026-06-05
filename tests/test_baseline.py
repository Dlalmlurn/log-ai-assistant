import json
from datetime import date, datetime, timezone

from src.ueba.baseline import aggregate_daily_features, build_baselines_from_logs


def test_build_baseline_stats() -> None:
    logs = [
        {
            "tenant_id": "default",
            "user_id": "admin",
            "event_time": datetime(2026, 4, 1, 9, 10, 0).isoformat(),
            "src_ip": "10.0.0.1",
            "user_agent": "ua1",
            "action": "api_call",
            "resource": "/api/info",
            "result": "success",
        },
        {
            "tenant_id": "default",
            "user_id": "admin",
            "event_time": datetime(2026, 4, 1, 9, 10, 30).isoformat(),
            "src_ip": "10.0.0.1",
            "user_agent": "ua1",
            "action": "api_call",
            "resource": "/api/export",
            "result": "success",
        },
        {
            "tenant_id": "default",
            "user_id": "admin",
            "event_time": datetime(2026, 4, 1, 10, 0, 0).isoformat(),
            "src_ip": "10.0.0.2",
            "user_agent": "ua2",
            "action": "login",
            "resource": "vpn",
            "result": "fail",
        },
    ]

    baselines = build_baselines_from_logs(logs)
    assert len(baselines) == 1
    baseline = baselines[0]
    assert baseline.user_id == "admin"
    assert "10.0.0.1" in baseline.location_profile["common_ips"]
    assert baseline.result_profile["failed_login_count_7d"] == 1
    assert baseline.access_profile["avg_api_calls_per_minute"] > 0


class FakeAggStorage:
    """Storage that returns ClickHouse-side daily aggregates for one user."""

    def __init__(self, aggregates):
        self._aggregates = aggregates
        self.captured_date = None
        self.inserted = None

    def aggregate_daily_features_sql(self, *, metric_date, tenant_id=None):
        self.captured_date = metric_date
        return self._aggregates

    def insert_user_daily_features(self, rows):
        self.inserted = rows


def test_aggregate_daily_features_uses_clickhouse_pushdown() -> None:
    aggregates = [
        {
            "tenant_id": "default",
            "user_id": "alice",
            "account_type_top": ["service"],
            "event_count": 10,
            "login_count": 4,
            "failed_login_count": 1,
            "success_login_count": 3,
            "distinct_src_ip_count": 2,
            "distinct_host_count": 1,
            "distinct_action_count": 3,
            "first_seen_time": datetime(2026, 5, 31, 1, 0, tzinfo=timezone.utc),
            "last_seen_time": datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc),
            "night_event_count": 5,
            "sensitive_action_count": 2,
            "download_count": 1,
            "permission_change_count": 0,
            "common_src_ips_raw": ["10.0.0.1", "10.0.0.2", ""],
            "common_hosts_raw": ["host-a", ""],
            "common_actions_raw": ["login", "download", ""],
        }
    ]
    storage = FakeAggStorage(aggregates)

    count = aggregate_daily_features(
        storage, target_date=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    )

    assert count == 1
    assert storage.captured_date == date(2026, 5, 31)
    row = storage.inserted[0]
    assert row["user_id"] == "alice"
    assert row["account_type"] == "service"
    # Empty topK entries are filtered out.
    assert row["common_src_ips"] == ["10.0.0.1", "10.0.0.2"]
    assert row["common_hosts"] == ["host-a"]
    assert row["distinct_src_ip_count"] == 2
    metrics = json.loads(row["profile_metrics"])
    assert metrics["night_ratio"] == 0.5
    assert metrics["sensitive_ratio"] == 0.2
