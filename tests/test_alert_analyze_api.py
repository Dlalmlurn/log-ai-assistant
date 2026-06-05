from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from src.api.app import analyze_alert, app
from src.schemas import AIJudgement, AnomalyEvent


ALERT_DOC = {
    "event_id": "anom-1",
    "event_time": "2026-05-13T10:00:00Z",
    "detect_time": "2026-05-13T10:00:10Z",
    "tenant_id": "default",
    "user_id": "alice",
    "src_ip": "203.0.113.9",
    "source_type": "vpn",
    "risk_level": "high",
    "risk_score": 90,
    "risk_components": {"rule_score": 90},
    "rule_hits": ["新IP登录后短时间访问敏感资源"],
    "baseline_deviations": [],
    "reason_codes": ["new_source_then_sensitive_access"],
    "evidence": {"user_id": "alice", "src_ip": "203.0.113.9", "resource": "/api/export"},
    "related_event_ids": ["evt-login", "evt-export"],
    "ai_status": "pending",
    "status": "new",
    "created_at": "2026-05-13T10:00:10Z",
}

BASELINE_DOC = {
    "baseline_date": "2026-05-13",
    "tenant_id": "default",
    "user_id": "alice",
    "model_version": "baseline-v1",
    "trained_from": "2026-05-06",
    "trained_to": "2026-05-12",
    "sample_days": 7,
    "sample_count": 100,
    "baseline_confidence": 1.0,
    "who_profile": {"user_id": "alice"},
    "time_profile": {"active_hours": ["09:00-18:00"]},
    "location_profile": {"common_ips": ["10.0.0.7"]},
    "access_profile": {"common_resources": ["/home"]},
    "volume_profile": {},
    "result_profile": {},
    "why_profile": {},
    "fallback_level": "none",
    "created_at": "2026-05-13T09:00:00Z",
}

RELATED_LOGS = [
    {
        "event_id": "evt-login",
        "event_time": "2026-05-13T10:00:00Z",
        "ingest_time": "2026-05-13T10:00:05Z",
        "tenant_id": "default",
        "source_type": "vpn",
        "log_type": "login",
        "user_id": "alice",
        "src_ip": "203.0.113.9",
        "action": "login",
        "resource": None,
        "result": "success",
        "message": "VPN login success",
        "raw_log": "raw login line",
        "risk_tags": [],
        "attrs": {},
    },
    {
        "event_id": "evt-export",
        "event_time": "2026-05-13T10:02:00Z",
        "ingest_time": "2026-05-13T10:02:05Z",
        "tenant_id": "default",
        "source_type": "vpn",
        "log_type": "api_call",
        "user_id": "alice",
        "src_ip": "203.0.113.9",
        "action": "api_call",
        "resource": "/api/export",
        "result": "success",
        "message": "Export API called",
        "raw_log": "raw export line",
        "risk_tags": ["sensitive_resource"],
        "attrs": {},
    },
]


class FakeAnalyzeStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.inserted: list[AIJudgement] = []
        self.updated: list[dict[str, object]] = []
        self.anomaly: dict[str, object] | None = dict(ALERT_DOC)

    def get_anomaly(self, event_id: str):
        self.calls.append({"method": "get_anomaly", "event_id": event_id})
        return self.anomaly

    def get_user_baseline(self, user_id: str, *, tenant_id: str | None = None, baseline_date=None):
        self.calls.append({"method": "get_user_baseline", "user_id": user_id, "tenant_id": tenant_id})
        return dict(BASELINE_DOC)

    def list_logs_by_event_ids(self, event_ids):
        self.calls.append({"method": "list_logs_by_event_ids", "event_ids": list(event_ids)})
        return RELATED_LOGS

    def insert_ai_judgement(self, report: AIJudgement) -> None:
        self.inserted.append(report)

    def update_anomaly_ai_status(self, event_id: str, ai_status: str) -> None:
        self.updated.append({"event_id": event_id, "ai_status": ai_status})


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def analyze(
        self,
        *,
        event: AnomalyEvent,
        baseline: dict[str, Any] | None,
        related_logs: list[dict[str, Any]] | None = None,
        window_stats: dict[str, Any] | None = None,
    ) -> AIJudgement:
        self.calls.append(
            {
                "event": event,
                "baseline": baseline,
                "related_logs": related_logs,
                "window_stats": window_stats,
            }
        )
        return AIJudgement(
            judgement_id="ai-1",
            event_id=event.event_id,
            created_at=datetime(2026, 5, 13, 10, 3, tzinfo=timezone.utc),
            model_name="mock-security-analyst",
            attack_type="账号接管",
            risk_level=event.risk_level,
            judgement="New IP followed by export.",
            key_reasons=["new_source_then_sensitive_access"],
            recommended_actions=["Review account activity."],
            confidence=0.9,
            feedback_suggestions={},
            raw_response={"mode": "test"},
            is_mock=True,
        )


class FailingAnalyzer(FakeAnalyzer):
    def analyze(self, **_kwargs) -> AIJudgement:
        raise RuntimeError("model unavailable")


def test_analyze_alert_requires_context_stores_report_and_updates_alert() -> None:
    storage = FakeAnalyzeStorage()
    analyzer = FakeAnalyzer()

    response = analyze_alert(event_id="anom-1", storage=storage, analyzer=analyzer)
    payload = response.model_dump(mode="json")

    assert payload["judgement_id"] == "ai-1"
    assert payload["event_id"] == "anom-1"
    assert payload["attack_type"] == "账号接管"

    analyzer_call = analyzer.calls[0]
    assert analyzer_call["event"].event_id == "anom-1"
    assert analyzer_call["baseline"]["user_id"] == "alice"
    assert [item["event_id"] for item in analyzer_call["related_logs"]] == ["evt-login", "evt-export"]
    assert analyzer_call["window_stats"] == {}

    assert storage.inserted[0].judgement_id == "ai-1"
    assert storage.updated == [{"event_id": "anom-1", "ai_status": "analyzed"}]
    assert storage.calls == [
        {"method": "get_anomaly", "event_id": "anom-1"},
        {"method": "get_user_baseline", "user_id": "alice", "tenant_id": "default"},
        {"method": "list_logs_by_event_ids", "event_ids": ["evt-login", "evt-export"]},
    ]


def test_analyze_alert_returns_clear_404_when_alert_is_missing() -> None:
    storage = FakeAnalyzeStorage()
    storage.anomaly = None

    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="missing-alert", storage=storage, analyzer=FakeAnalyzer())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "anomaly_not_found",
        "message": "Anomaly event not found",
        "details": {"table": "anomaly_events", "event_id": "missing-alert"},
    }


def test_analyze_alert_returns_standard_error_when_alert_query_fails() -> None:
    class FailingQueryStorage(FakeAnalyzeStorage):
        def get_anomaly(self, _event_id: str):
            raise RuntimeError("clickhouse unavailable")

    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="anom-1", storage=FailingQueryStorage(), analyzer=FakeAnalyzer())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "clickhouse_query_failed",
        "message": "Failed to query anomaly for AI judgement",
        "details": {"table": "anomaly_events", "event_id": "anom-1"},
    }


def test_analyze_alert_returns_standard_error_when_analysis_or_store_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="anom-1", storage=FakeAnalyzeStorage(), analyzer=FailingAnalyzer())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "ai_judgement_failed",
        "message": "Failed to judge anomaly and store AI judgement",
        "details": {"event_id": "anom-1"},
    }


class FeedbackTrackingStorage(FakeAnalyzeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.feedback: list[Any] = []

    def insert_feedback(self, feedback) -> None:
        self.feedback.append(feedback)


class SuggestingAnalyzer(FakeAnalyzer):
    def analyze(self, **kwargs) -> AIJudgement:
        report = super().analyze(**kwargs)
        return report.model_copy(
            update={
                "feedback_suggestions": {
                    "rule_weight": "Raise weight for new-source-then-sensitive rule.",
                    "false_positive": {
                        "suggestion": "Looks legitimate for a service account.",
                        "confidence": 0.4,
                    },
                }
            }
        )


def test_analyze_alert_splits_feedback_suggestions_into_ai_feedback() -> None:
    storage = FeedbackTrackingStorage()

    analyze_alert(event_id="anom-1", storage=storage, analyzer=SuggestingAnalyzer())

    assert len(storage.feedback) == 2
    by_type = {fb.feedback_type: fb for fb in storage.feedback}
    assert set(by_type) == {"rule_weight", "false_positive"}
    rule_fb = by_type["rule_weight"]
    assert rule_fb.target_component == "rule"
    assert rule_fb.review_status == "pending"
    assert rule_fb.event_id == "anom-1"
    assert rule_fb.judgement_id == "ai-1"
    fp_fb = by_type["false_positive"]
    assert fp_fb.target_component == "scoring"
    assert fp_fb.confidence == 0.4
    assert fp_fb.suggestion == "Looks legitimate for a service account."


def test_analyze_alert_rejects_non_candidate_anomaly() -> None:
    storage = FakeAnalyzeStorage()
    storage.anomaly = {**ALERT_DOC, "risk_level": "low", "ai_status": "not_required"}

    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="anom-1", storage=storage, analyzer=FakeAnalyzer())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "ai_judgement_not_candidate"
    assert exc_info.value.detail["details"]["risk_level"] == "low"


def test_analyze_alert_force_overrides_candidate_gate() -> None:
    storage = FakeAnalyzeStorage()
    storage.anomaly = {**ALERT_DOC, "risk_level": "low", "ai_status": "not_required"}

    response = analyze_alert(event_id="anom-1", force=True, storage=storage, analyzer=FakeAnalyzer())

    assert response.judgement_id == "ai-1"
    assert storage.updated == [{"event_id": "anom-1", "ai_status": "analyzed"}]


def test_analyze_alert_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/ai/judge/{event_id}"]["post"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AIJudgement"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
