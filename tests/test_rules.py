from datetime import datetime, timedelta

from src.detection.rules import detect_batch
from src.schemas import NormalizedLog


def build_log(idx: int, **kwargs) -> NormalizedLog:
    base = {
        "event_id": f"evt-{idx}",
        "event_time": datetime(2026, 4, 1, 10, 0, 0) + timedelta(seconds=idx),
        "ingest_time": datetime(2026, 4, 1, 10, 0, 0) + timedelta(seconds=idx),
        "source_type": "vpn",
        "username": "test.user",
        "src_ip": "1.1.1.1",
        "action": "login",
        "resource": "/home",
        "status": "failed",
        "message": "failed login",
        "raw_message": "raw",
        "risk_tags": [],
    }
    base.update(kwargs)
    return NormalizedLog.model_validate(base)


def test_bruteforce_ip_rule_triggered() -> None:
    logs = [build_log(i, src_ip="8.8.8.8", username=f"u{i%2}") for i in range(10)]
    alerts = detect_batch(logs)
    rules = [rule for a in alerts for rule in a.rule_hits]
    assert "同一src_ip在5分钟内登录失败超阈值" in rules


def test_new_ip_then_sensitive_access() -> None:
    login = build_log(
        1,
        status="success",
        action="login",
        username="alice",
        src_ip="2.2.2.2",
        resource="vpn-gw-bj01",
    )
    sensitive = build_log(
        2,
        status="success",
        action="access",
        username="alice",
        src_ip="2.2.2.2",
        resource="/api/admin/export",
    )
    alerts = detect_batch([login, sensitive])
    rules = [rule for a in alerts for rule in a.rule_hits]
    assert "新IP登录后短时间访问敏感资源" in rules
