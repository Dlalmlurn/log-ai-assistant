"""RuleEngine 的规则触发测试。

这里不重复测试 builder 的所有细节，只确认规则引擎能正确触发规则并产出新结构。
"""

from datetime import datetime, timedelta

from src.detection.rules import detect_batch
from src.schemas import NormalizedLog


def build_log(idx: int, **kwargs) -> NormalizedLog:
    """构造一条默认登录失败日志，测试里通过 kwargs 改成不同场景。"""

    base = {
        "event_id": f"evt-{idx}",
        "event_time": datetime(2026, 4, 1, 10, 0, 0) + timedelta(seconds=idx),
        "ingest_time": datetime(2026, 4, 1, 10, 0, 0) + timedelta(seconds=idx),
        "tenant_id": "default",
        "source_type": "vpn",
        "log_type": "login",
        "user_id": "test.user",
        "src_ip": "1.1.1.1",
        "action": "login",
        "resource": "/home",
        "result": "fail",
        "message": "failed login",
        "raw_log": "raw",
        "risk_tags": [],
        "attrs": {},
    }
    base.update(kwargs)
    return NormalizedLog.model_validate(base)


def test_bruteforce_ip_rule_triggered() -> None:
    """同一个 IP 多次登录失败时，应触发暴力破解类规则。"""

    logs = [build_log(i, src_ip="8.8.8.8", user_id=f"u{i%2}") for i in range(10)]
    alerts = detect_batch(logs)
    rules = [rule for a in alerts for rule in a.rule_hits]
    assert "同一src_ip在5分钟内登录失败超阈值" in rules
    assert any("failed_login_spike" in alert.reason_codes for alert in alerts)
    assert all("rule_score" not in alert.risk_components for alert in alerts)
    assert all("rule_strength" in alert.risk_components for alert in alerts)
    ip_spike = next(
        alert
        for alert in alerts
        if "同一src_ip在5分钟内登录失败超阈值" in alert.rule_hits
    )
    assert ip_spike.attack_type == "brute_force"
    assert ip_spike.risk_level == "high"
    assert ip_spike.ai_status == "pending"


def test_new_ip_then_sensitive_access() -> None:
    """新 IP 登录后马上访问敏感资源，应触发关联异常。"""

    login = build_log(
        1,
        result="success",
        action="login",
        user_id="alice",
        src_ip="2.2.2.2",
        resource="vpn-gw-bj01",
    )
    sensitive = build_log(
        2,
        result="success",
        action="access",
        user_id="alice",
        src_ip="2.2.2.2",
        resource="/api/admin/export",
    )
    alerts = detect_batch([login, sensitive])
    rules = [rule for a in alerts for rule in a.rule_hits]
    assert "新IP登录后短时间访问敏感资源" in rules
    correlated = [
        alert
        for alert in alerts
        if "new_source_then_sensitive_access" in alert.reason_codes
    ]
    assert correlated
    assert correlated[0].attack_type == "account_takeover"
    assert correlated[0].risk_components["event_correlation"] > 0


def test_off_hours_login_only_never_reaches_critical() -> None:
    """【误报控制回归】非工作时间登录但无任何敏感行为时，风险分绝不突破 critical 区间。

    rare_login_hour 的风险组成为：rule_strength:20 + baseline_deviation:5 = 25（low 级别）。
    即便将来附加了 time baseline 偏离（medium severity → +15 baseline_deviation），
    总分上限也仅为 ~35，严禁进入 critical（≥ 90）甚至 high（≥ 70）区间。
    """
    # 选择工作时间之外的小时（凌晨 2 点，settings.work_hour_start 默认 9）
    off_hour_time = datetime(2026, 4, 1, 2, 0, 0)
    log = build_log(
        1,
        action="login",
        result="success",
        src_ip="1.1.1.1",
        resource="/home",
        user_id="ordinary.user",
        event_time=off_hour_time,
        ingest_time=off_hour_time,
    )
    alerts = detect_batch([log])

    # 应触发非工作时间登录规则
    off_hour_alerts = [a for a in alerts if "rare_login_hour" in a.reason_codes]
    assert off_hour_alerts, "应至少产出一条 rare_login_hour 异常事件"

    for alert in off_hour_alerts:
        # 仅有 rare_login_hour，不得混入敏感操作相关 reason_code
        assert "sensitive_resource_access" not in alert.reason_codes
        assert "new_source_then_sensitive_access" not in alert.reason_codes

        # 风险分严禁突破 critical（≥ 90）
        assert alert.risk_score < 90, (
            f"非工作时间单纯登录不应达到 critical，实际得分 {alert.risk_score}"
        )
        # 同时也不应达到 high（≥ 70）——单独 rare_login_hour 不足以触发高风险
        assert alert.risk_score < 70, (
            f"非工作时间单纯登录不应达到 high，实际得分 {alert.risk_score}"
        )
        assert alert.risk_level != "critical"
