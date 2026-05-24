from datetime import datetime

from src.ueba.baseline import build_baselines_from_logs


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
