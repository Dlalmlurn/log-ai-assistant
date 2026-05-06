from datetime import datetime

from src.ueba.baseline import build_baselines_from_logs


def test_build_baseline_stats() -> None:
    logs = [
        {
            "username": "admin",
            "event_time": datetime(2026, 4, 1, 9, 10, 0).isoformat(),
            "src_ip": "10.0.0.1",
            "user_agent": "ua1",
            "action": "api_call",
            "resource": "/api/info",
            "status": "success",
        },
        {
            "username": "admin",
            "event_time": datetime(2026, 4, 1, 9, 10, 30).isoformat(),
            "src_ip": "10.0.0.1",
            "user_agent": "ua1",
            "action": "api_call",
            "resource": "/api/export",
            "status": "success",
        },
        {
            "username": "admin",
            "event_time": datetime(2026, 4, 1, 10, 0, 0).isoformat(),
            "src_ip": "10.0.0.2",
            "user_agent": "ua2",
            "action": "login",
            "resource": "vpn",
            "status": "failed",
        },
    ]

    baselines = build_baselines_from_logs(logs)
    assert len(baselines) == 1
    baseline = baselines[0]
    assert baseline.username == "admin"
    assert "10.0.0.1" in baseline.common_ips
    assert baseline.failed_login_count_7d == 1
    assert baseline.avg_api_calls_per_minute > 0
