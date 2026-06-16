"""AnomalyEventBuilder 的单元测试。

这些测试主要保证：reason_codes 能稳定转换成风险分数、风险等级和攻击类型。
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.detection.anomaly_builder import AnomalyEventBuilder, RISK_COMPONENT_KEYS
from src.schemas import NormalizedLog


NOW = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)


def build_log(**kwargs) -> NormalizedLog:
    """构造一条默认日志，测试里只覆盖关心的字段。"""

    base = {
        "event_id": "evt-1",
        "event_time": NOW - timedelta(minutes=1),
        "ingest_time": NOW,
        "tenant_id": "default",
        "source_type": "vpn",
        "log_type": "login",
        "user_id": "alice",
        "src_ip": "10.0.0.7",
        "action": "login",
        "resource": "vpn-gw-bj01",
        "result": "success",
        "message": "VPN login success",
        "raw_log": "raw vpn line",
    }
    base.update(kwargs)
    return NormalizedLog.model_validate(base)


def test_new_source_ip_builds_medium_account_takeover_event() -> None:
    """新 IP 登录应被识别为账号接管风险，且风险等级为 medium。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)

    event = builder.build(
        log=build_log(),
        rule_hits=["New source IP login"],
        reason_codes=["new_source_ip"],
        evidence={"user_id": "alice", "new_ip": "10.0.0.7"},
    )

    assert event.attack_type == "account_takeover"
    assert event.risk_level == "medium"
    assert event.risk_score == 35
    assert event.scoring_version == "risk-scoring-v1"
    assert set(event.risk_components) == set(RISK_COMPONENT_KEYS)
    assert event.risk_components["rule_strength"] == 20
    assert event.risk_components["baseline_deviation"] == 15
    assert event.ai_status == "not_required"


def test_rare_login_hour_stays_low_when_it_is_the_only_signal() -> None:
    """单独的非工作时间登录风险较低，不应该直接进入 high/critical。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)

    event = builder.build(
        log=build_log(event_time=datetime(2026, 5, 13, 2, 0, tzinfo=timezone.utc)),
        rule_hits=["Rare login hour"],
        reason_codes=["rare_login_hour"],
        evidence={"event_hour": 2},
    )

    assert event.attack_type == "suspicious_login"
    assert event.risk_level == "low"
    assert event.risk_score < 40


def test_correlated_sensitive_access_is_critical_and_keeps_related_ids() -> None:
    """新 IP 登录后访问敏感资源属于关联事件，应该保留关联日志 id。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)
    log = build_log(event_id="evt-sensitive", action="access", resource="/api/admin/export")

    event = builder.build(
        log=log,
        rule_hits=["New source followed by sensitive access"],
        reason_codes=["new_source_then_sensitive_access", "sensitive_resource_access"],
        evidence={"user_id": "alice", "src_ip": "10.0.0.7", "resource": "/api/admin/export"},
        related_event_ids=["evt-login"],
    )

    assert event.attack_type == "account_takeover"
    assert event.risk_level == "critical"
    assert event.risk_score == 80
    assert event.related_event_ids == ["evt-sensitive", "evt-login"]
    assert event.ai_status == "pending"


def test_baseline_deviations_are_preserved_and_increase_baseline_component() -> None:
    """baseline 偏离会保存在事件里，并提高 baseline_deviation 分数。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)
    deviations = [
        {
            "feature": "src_ip",
            "expected": ["10.0.0.0/24"],
            "actual": "203.0.113.9",
            "severity": "high",
        }
    ]

    event = builder.build(
        log=build_log(src_ip="203.0.113.9"),
        rule_hits=["New source IP login"],
        reason_codes=["new_source_ip"],
        evidence={"user_id": "alice", "new_ip": "203.0.113.9"},
        baseline_deviations=deviations,
    )

    assert event.baseline_deviations == deviations
    assert event.risk_components["baseline_deviation"] == 25
    assert event.risk_score == 45


def test_event_id_seed_generates_stable_event_id() -> None:
    """同一个 seed 应生成同一个异常 event_id，方便自动检测 worker 做幂等。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)
    first = builder.build(
        log=build_log(),
        rule_hits=["New source IP login"],
        reason_codes=["new_source_ip"],
        evidence={"user_id": "alice", "new_ip": "10.0.0.7"},
        event_id_seed="default:evt-1:new_source_ip",
    )
    second = builder.build(
        log=build_log(),
        rule_hits=["New source IP login"],
        reason_codes=["new_source_ip"],
        evidence={"user_id": "alice", "new_ip": "10.0.0.7"},
        event_id_seed="default:evt-1:new_source_ip",
    )

    assert first.event_id == second.event_id
    assert first.event_id.startswith("anom-")


def test_builder_requires_rule_hits_and_reason_codes() -> None:
    """异常事件必须同时有 rule_hits 和 reason_codes，缺少任意一个都报错。"""

    builder = AnomalyEventBuilder(clock=lambda: NOW)

    with pytest.raises(ValueError, match="rule_hits"):
        builder.build(log=build_log(), rule_hits=[], reason_codes=["new_source_ip"])

    with pytest.raises(ValueError, match="reason_codes"):
        builder.build(log=build_log(), rule_hits=["New source IP login"], reason_codes=[])
