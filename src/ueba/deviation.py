from __future__ import annotations

"""用户行为偏离求值模块（持久化证据链）。

- UserContext / load_user_context：封装对 ClickHouse 基线与 seen_sources 的持久化查询。
- BaselineDeviation / evaluate_deviations：基于 UserContext 评估每条日志的 baseline 偏离，
  产出 9 字段契约证据数组；低置信度基线（confidence < 0.6）触发 severity 动态降级。

evaluate_deviations 为纯函数，无 baseline 时返回空列表，保证 RuleEngine 离线可测性。
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

DeviationType = Literal[
    "rare_login_hour",
    "new_source_ip",
    "new_geo_location",
    "failed_login_spike",
    "sensitive_resource_access",
    "outside_active_hours",
]
EvidenceSource = Literal["user_baseline", "seen_sources", "daily_feature"]
Severity = Literal["low", "medium", "high", "critical"]

_SEVERITY_DOWNGRADE: dict[str, str] = {
    "critical": "high",
    "high": "medium",
    "medium": "low",
    "low": "low",
}


class DeviationStorage(Protocol):
    """load_user_context 所需的最小存储契约。"""

    def get_user_baseline(
        self,
        user_id: str,
        *,
        tenant_id: str | None = None,
        baseline_date: Any = None,
    ) -> dict[str, Any] | None:
        ...

    def query_user_seen_sources(
        self,
        *,
        tenant_id: str = "default",
        user_id: str | None = None,
        source_type: str | None = None,
        source_key: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class BaselineDeviation:
    """P1 阶段 9 字段正式偏离证据契约。"""

    feature: str
    profile_group: str
    expected: Any
    actual: Any
    deviation_type: str
    severity: str
    confidence: float
    evidence_source: str
    sample_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "profile_group": self.profile_group,
            "expected": self.expected,
            "actual": self.actual,
            "deviation_type": self.deviation_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence_source": self.evidence_source,
            "sample_days": self.sample_days,
        }


@dataclass(frozen=True)
class UserContext:
    """单用户持久化上下文快照。"""

    tenant_id: str
    user_id: str | None
    baseline: dict[str, Any] | None = None
    seen_sources: set[str] = field(default_factory=set)

    @property
    def sample_days(self) -> int:
        if self.baseline is None:
            return 0
        return int(self.baseline.get("sample_days", 0))

    @property
    def confidence(self) -> float:
        if self.baseline is None:
            return 0.0
        return float(self.baseline.get("baseline_confidence", 0.0))


def load_user_context(
    storage: DeviationStorage,
    tenant_id: str,
    user_id: str | None,
) -> UserContext:
    """加载单用户持久化上下文（基线 + seen_sources）。"""
    if not user_id:
        return UserContext(tenant_id=tenant_id, user_id=None)

    baseline = storage.get_user_baseline(user_id, tenant_id=tenant_id)
    rows = storage.query_user_seen_sources(
        tenant_id=tenant_id,
        user_id=user_id,
        source_type="ip",
        limit=10000,
    )
    seen: set[str] = {str(r["source_key"]) for r in rows if r.get("source_key")}
    return UserContext(
        tenant_id=tenant_id,
        user_id=user_id,
        baseline=baseline,
        seen_sources=seen,
    )


def _safe_severity(severity: str, confidence: float) -> str:
    """confidence < 0.6 时动态降级一级，控制误报。"""
    if confidence >= 0.6:
        return severity
    return _SEVERITY_DOWNGRADE.get(severity, severity)


def evaluate_deviations(log: Any, context: UserContext) -> list[BaselineDeviation]:
    """评估单条日志的所有 baseline 偏离，输出 9 字段契约。"""
    if context.baseline is None:
        return []

    deviations: list[BaselineDeviation] = []
    conf = context.confidence
    days = context.sample_days

    location_profile = _dict_value(context.baseline.get("location_profile"))
    common_ips = _common_values(location_profile.get("common_ips"))
    src_ip = getattr(log, "src_ip", None)
    if src_ip and common_ips and src_ip not in common_ips:
        deviations.append(
            BaselineDeviation(
                feature="src_ip",
                profile_group="location",
                expected=common_ips,
                actual=src_ip,
                deviation_type="new_source_ip",
                severity=_safe_severity("high", conf),
                confidence=conf,
                evidence_source="user_baseline",
                sample_days=days,
            )
        )

    time_profile = _dict_value(context.baseline.get("time_profile"))
    active_hours = _common_values(time_profile.get("active_hours"))
    event_hour = getattr(log.event_time, "hour", 0) if hasattr(log, "event_time") else 0
    if active_hours and not _hour_in_ranges(event_hour, active_hours):
        deviations.append(
            BaselineDeviation(
                feature="event_hour",
                profile_group="time",
                expected=active_hours,
                actual=f"{event_hour:02d}:00",
                deviation_type="outside_active_hours",
                severity=_safe_severity("medium", conf),
                confidence=conf,
                evidence_source="user_baseline",
                sample_days=days,
            )
        )

    access_profile = _dict_value(context.baseline.get("access_profile"))
    common_resources = _common_values(access_profile.get("common_resources"))
    resource = getattr(log, "resource", None)
    if resource and common_resources and resource not in common_resources:
        deviations.append(
            BaselineDeviation(
                feature="resource",
                profile_group="access",
                expected=common_resources,
                actual=resource,
                deviation_type="sensitive_resource_access",
                severity=_safe_severity("high", conf),
                confidence=conf,
                evidence_source="user_baseline",
                sample_days=days,
            )
        )

    return deviations


def is_seen_source(context: UserContext, source_key: str) -> bool:
    """source_key 是否在用户持久化 seen_sources 中。"""
    return source_key in context.seen_sources


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