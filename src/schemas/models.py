from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["低", "中", "高"]
SourceType = Literal["vpn", "oa", "api", "system", "security_device"]
ResponseItemT = TypeVar("ResponseItemT")


class ListResponse(BaseModel, Generic[ResponseItemT]):
    """REQ-003/REQ-004/REQ-005/REQ-006/REQ-008: standard paginated API list shape."""

    items: list[ResponseItemT] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    offset: int = Field(default=0, ge=0)


class ErrorResponse(BaseModel):
    """Standard API error response documented in docs/05_api_contract.md."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class NormalizedLog(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    event_time: datetime
    ingest_time: datetime
    source_type: SourceType = "vpn"
    username: str | None = None
    src_ip: str | None = None
    src_port: int | None = None
    dst_ip: str | None = None
    dst_port: int | None = None
    action: str
    resource: str | None = None
    status: str
    http_method: str | None = None
    user_agent: str | None = None
    message: str
    raw_message: str
    risk_tags: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    original_fields: dict[str, Any] = Field(default_factory=dict)


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    alert_id: str
    event_time: datetime
    detect_time: datetime
    username: str | None = None
    src_ip: str | None = None
    source_type: SourceType = "vpn"
    risk_level: RiskLevel
    risk_score: int
    rule_hits: list[str]
    evidence: dict[str, Any]
    related_event_ids: list[str] = Field(default_factory=list)
    related_logs_summary: str = ""
    status: str = "new"
    llm_analysis_id: str | None = None


class UserBaseline(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: str
    active_hours: list[str] = Field(default_factory=list)
    common_ips: list[str] = Field(default_factory=list)
    common_user_agents: list[str] = Field(default_factory=list)
    avg_api_calls_per_minute: float = 0.0
    common_resources: list[str] = Field(default_factory=list)
    failed_login_count_7d: int = 0
    sensitive_access_rate: float = 0.0
    updated_at: datetime


class BaselineRebuildResponse(BaseModel):
    """REQ-003: response for rebuilding user behavior baselines."""

    rebuilt_count: int = Field(ge=0)


class AIReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    ai_report_id: str
    alert_id: str
    created_at: datetime
    attack_type: str
    risk_level: RiskLevel
    reason: str
    suggestion: str
    confidence: float
    next_steps: list[str] = Field(default_factory=list)
    raw_response: dict[str, Any] = Field(default_factory=dict)


class EvidenceChain(BaseModel):
    """REQ-004/REQ-006: evidence summary for alert detail views and AI context."""

    rule_hits: list[str] = Field(default_factory=list)
    baseline_deviations: list[str] = Field(default_factory=list)
    risk_reason: str = ""


class AlertDetailResponse(BaseModel):
    """REQ-004/REQ-006: composed alert detail contract from docs/05_api_contract.md."""

    alert: AlertEvent
    baseline: dict[str, Any] = Field(default_factory=dict)
    related_logs: list[NormalizedLog] = Field(default_factory=list)
    ai_report: dict[str, Any] = Field(default_factory=dict)
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
    """REQ-002/REQ-006: reusable list response for structured logs."""


class AlertEventListResponse(ListResponse[AlertEvent]):
    """REQ-004/REQ-006/REQ-008: reusable list response for alert events."""


class UserBaselineListResponse(ListResponse[UserBaseline]):
    """REQ-003/REQ-006: reusable list response for user baselines."""


class AIReportListResponse(ListResponse[AIReport]):
    """REQ-004/REQ-006: reusable list response for AI reports."""


class DailyReportListResponse(ListResponse[DailyReport]):
    """REQ-005/REQ-006: reusable list response for daily reports."""
