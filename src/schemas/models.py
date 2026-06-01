from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["low", "medium", "high"]
SourceType = Literal["vpn", "oa", "api", "system", "file", "database", "security_device"]
LogResult = Literal["success", "fail", "denied", "error"]
AIStatus = Literal["not_required", "pending", "analyzed", "failed"]
AnomalyStatus = Literal["new", "investigating", "closed", "false_positive"]
FallbackLevel = Literal["none", "peer_group", "department", "global"]
FeedbackType = Literal[
    "rule_weight",
    "baseline_threshold",
    "false_positive",
    "new_pattern",
    "data_contract",
]
FeedbackTargetComponent = Literal["rule", "baseline", "scoring", "data_contract"]
ReviewStatus = Literal["pending", "accepted", "rejected"]
ResponseItemT = TypeVar("ResponseItemT")


class ListResponse(BaseModel, Generic[ResponseItemT]):
    """Standard paginated API list shape."""

    items: list[ResponseItemT] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    offset: int = Field(default=0, ge=0)


class ErrorResponse(BaseModel):
    """Standard API error response."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class NormalizedLog(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    event_time: datetime
    ingest_time: datetime
    tenant_id: str
    source_type: SourceType
    log_type: str

    user_id: str | None = None
    account_type: str | None = "unknown"
    user_role: str | None = None
    department: str | None = None
    host: str | None = None

    src_ip: str | None = None
    src_port: int | None = None
    dst_ip: str | None = None
    dst_port: int | None = None
    geo: dict[str, Any] = Field(default_factory=dict)

    action: str
    object_type: str | None = None
    object_id: str | None = None
    resource: str | None = None
    result: LogResult

    severity: int = Field(default=0, ge=0, le=10)
    user_agent: str | None = None
    protocol: str | None = None
    auth_method: str | None = None
    session_id: str | None = None
    trace_id: str | None = None

    scenario_id: str | None = None
    scenario_type: str | None = None
    attack_chain_id: str | None = None
    step_index: int | None = None
    injected_label: str | None = None

    message: str
    raw_log: str
    risk_tags: list[str] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)


class AnomalyEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    event_time: datetime
    detect_time: datetime
    tenant_id: str

    user_id: str | None = None
    src_ip: str | None = None
    host: str | None = None
    source_type: SourceType | None = None
    action: str | None = None
    object_type: str | None = None
    object_id: str | None = None
    attack_type: str | None = None

    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    risk_components: dict[str, Any] = Field(default_factory=dict)
    rule_hits: list[str] = Field(default_factory=list)
    baseline_deviations: list[dict[str, Any]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    related_event_ids: list[str] = Field(default_factory=list)

    scenario_id: str | None = None
    scenario_type: str | None = None
    attack_chain_id: str | None = None

    ai_status: AIStatus = "not_required"
    status: AnomalyStatus = "new"
    created_at: datetime


class AIJudgement(BaseModel):
    model_config = ConfigDict(extra="allow")

    judgement_id: str
    event_id: str
    created_at: datetime
    model_name: str
    model_version: str | None = None
    risk_level: RiskLevel
    attack_type: str
    judgement: str
    key_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    feedback_suggestions: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] = Field(default_factory=dict)
    is_mock: bool


class AIFeedback(BaseModel):
    model_config = ConfigDict(extra="allow")

    feedback_id: str
    event_id: str
    judgement_id: str | None = None
    tenant_id: str
    user_id: str | None = None
    feedback_type: FeedbackType
    suggestion: str
    target_component: FeedbackTargetComponent
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = "pending"
    created_at: datetime


class UserDailyFeature(BaseModel):
    model_config = ConfigDict(extra="allow")

    feature_date: date
    tenant_id: str
    user_id: str
    account_type: str | None = "unknown"

    login_count: int = Field(ge=0)
    failed_login_count: int = Field(ge=0)
    success_login_count: int = Field(ge=0)
    distinct_src_ip_count: int = Field(ge=0)
    distinct_host_count: int = Field(ge=0)
    distinct_action_count: int = Field(ge=0)

    first_seen_time: datetime
    last_seen_time: datetime

    night_event_count: int = Field(ge=0)
    sensitive_action_count: int = Field(ge=0)
    download_count: int = Field(ge=0)
    permission_change_count: int = Field(ge=0)
    new_source_count: int = Field(ge=0)
    maintenance_window_hit_count: int = Field(default=0, ge=0)

    profile_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class UserBaseline(BaseModel):
    model_config = ConfigDict(extra="allow")

    baseline_date: date
    tenant_id: str
    user_id: str
    model_version: str
    trained_from: date
    trained_to: date
    sample_days: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    baseline_confidence: float = Field(ge=0, le=1)

    who_profile: dict[str, Any] = Field(default_factory=dict)
    time_profile: dict[str, Any] = Field(default_factory=dict)
    location_profile: dict[str, Any] = Field(default_factory=dict)
    access_profile: dict[str, Any] = Field(default_factory=dict)
    volume_profile: dict[str, Any] = Field(default_factory=dict)
    result_profile: dict[str, Any] = Field(default_factory=dict)
    why_profile: dict[str, Any] = Field(default_factory=dict)

    fallback_level: FallbackLevel = "none"
    created_at: datetime


class DataQualityMetric(BaseModel):
    model_config = ConfigDict(extra="allow")

    metric_date: date
    tenant_id: str
    source_type: SourceType | str

    generated_count: int = Field(ge=0)
    injected_anomaly_count: int = Field(default=0, ge=0)
    injected_high_risk_count: int = Field(default=0, ge=0)
    raw_logs_count: int = Field(ge=0)
    parsed_logs_count: int = Field(ge=0)
    clickhouse_insert_count: int = Field(ge=0)
    security_logs_count: int = Field(ge=0)

    raw_size_bytes: int = Field(ge=0)
    table_size_bytes: int = Field(ge=0)
    compression_ratio: float = Field(ge=0)

    missing_event_time_rate: float = Field(ge=0, le=1)
    missing_user_id_rate: float = Field(ge=0, le=1)
    missing_src_ip_rate: float = Field(ge=0, le=1)
    missing_action_rate: float = Field(ge=0, le=1)
    missing_result_rate: float = Field(ge=0, le=1)
    parse_error_rate: float = Field(ge=0, le=1)
    created_at: datetime


class BaselineRebuildResponse(BaseModel):
    """Response for rebuilding user behavior baselines."""

    rebuilt_count: int = Field(ge=0)


class LogAggregateTimeRange(BaseModel):
    """Time window for ClickHouse-backed log aggregation."""

    model_config = ConfigDict(populate_by_name=True)

    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class LogAggregateRequest(BaseModel):
    """Request body for aggregating normalized logs."""

    time_range: LogAggregateTimeRange | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=lambda: ["event_date"])
    metrics: list[str] = Field(default_factory=lambda: ["count"])
    limit: int = Field(default=500, ge=1)


class LogAggregateResponse(BaseModel):
    """Generic row response for log aggregation results."""

    items: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceChain(BaseModel):
    """Evidence summary for anomaly detail views and AI context."""

    rule_hits: list[str] = Field(default_factory=list)
    baseline_deviations: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    risk_components: dict[str, Any] = Field(default_factory=dict)
    ai_status: AIStatus = "not_required"
    risk_reason: str = ""


class AnomalyDetailResponse(BaseModel):
    """Composed anomaly detail contract."""

    anomaly: AnomalyEvent
    baseline: dict[str, Any] = Field(default_factory=dict)
    related_logs: list[NormalizedLog] = Field(default_factory=list)
    ai_judgement: dict[str, Any] = Field(default_factory=dict)
    evidence_chain: EvidenceChain = Field(default_factory=EvidenceChain)


class DailyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    date: str
    created_at: datetime
    overall_score: float
    log_count: int
    alert_count: int
    high_risk_count: int
    major_risks: list[str]
    high_risk_users: list[str]
    typical_alerts: list[dict[str, Any]]
    ai_summary: str
    recommendation: str
    markdown: str


class NormalizedLogListResponse(ListResponse[NormalizedLog]):
    """Reusable list response for structured logs."""


class AnomalyEventListResponse(ListResponse[AnomalyEvent]):
    """Reusable list response for anomaly events."""


class UserBaselineListResponse(ListResponse[UserBaseline]):
    """Reusable list response for user baselines."""


class AIJudgementListResponse(ListResponse[AIJudgement]):
    """Reusable list response for AI judgements."""


class DailyReportListResponse(ListResponse[DailyReport]):
    """Reusable list response for daily reports."""
