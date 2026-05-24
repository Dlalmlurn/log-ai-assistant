from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from src.api.app import analyze_alert, app
from src.config import settings
from src.schemas import AIJudgement, AnomalyEvent


ALERT_DOC = {
    "_id": "alert-doc-1",
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
    "evidence": {
        "user_id": "alice",
        "src_ip": "203.0.113.9",
        "resource": "/api/export",
    },
    "related_event_ids": ["evt-login", "evt-export"],
    "ai_status": "pending",
    "status": "new",
    "created_at": "2026-05-13T10:00:10Z",
}

BASELINE_DOC = {
    "_id": "baseline-doc-1",
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
    "access_profile": {
        "common_user_agents": ["Chrome"],
        "common_resources": ["/home"],
        "avg_api_calls_per_minute": 2.0,
        "sensitive_access_rate": 0.0,
    },
    "volume_profile": {},
    "result_profile": {"failed_login_count_7d": 0},
    "why_profile": {},
    "fallback_level": "none",
    "created_at": "2026-05-13T09:00:00Z",
}

RELATED_LOGS = [
    {
        "_id": "log-doc-2",
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
    {
        "_id": "log-doc-1",
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
]


class FakeAnalyzeStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.indexed: list[dict[str, object]] = []
        self.updated: list[dict[str, object]] = []
        self.responses: dict[str, list[dict[str, object]]] = {
            settings.elasticsearch_alert_index: [ALERT_DOC],
            settings.elasticsearch_baseline_index: [BASELINE_DOC],
            settings.elasticsearch_log_index: RELATED_LOGS,
        }

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        items = self.responses.get(str(kwargs["index"]), [])
        return items, len(items)

    def index_document(self, index: str, document: dict[str, Any], doc_id: str | None = None) -> None:
        self.indexed.append({"index": index, "document": document, "doc_id": doc_id})

    def update_document(self, index: str, doc_id: str, partial: dict[str, Any]) -> None:
        self.updated.append({"index": index, "doc_id": doc_id, "partial": partial})


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

    assert len(analyzer.calls) == 1
    analyzer_call = analyzer.calls[0]
    assert analyzer_call["event"].event_id == "anom-1"
    assert analyzer_call["baseline"]["user_id"] == "alice"
    assert "_id" not in analyzer_call["baseline"]
    assert [item["event_id"] for item in analyzer_call["related_logs"]] == ["evt-login", "evt-export"]
    assert all("_id" not in item for item in analyzer_call["related_logs"])
    assert analyzer_call["window_stats"] == {}

    assert storage.indexed == [
        {
            "index": settings.elasticsearch_ai_index,
            "document": payload,
            "doc_id": "ai-1",
        }
    ]
    assert storage.updated == [
        {
            "index": settings.elasticsearch_alert_index,
            "doc_id": "anom-1",
            "partial": {"ai_status": "analyzed"},
        }
    ]
    assert storage.calls == [
        {
            "index": settings.elasticsearch_alert_index,
            "query": {"term": {"event_id": "anom-1"}},
            "limit": 1,
            "offset": 0,
        },
        {
            "index": settings.elasticsearch_baseline_index,
            "query": {"term": {"user_id": "alice"}},
            "limit": 1,
            "offset": 0,
        },
        {
            "index": settings.elasticsearch_log_index,
            "query": {"terms": {"event_id": ["evt-login", "evt-export"]}},
            "limit": 2,
            "offset": 0,
            "sort": [{"event_time": "asc"}],
        },
    ]


def test_analyze_alert_returns_clear_404_when_alert_is_missing() -> None:
    storage = FakeAnalyzeStorage()
    storage.responses[settings.elasticsearch_alert_index] = []

    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="missing-alert", storage=storage, analyzer=FakeAnalyzer())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "alert_not_found",
        "message": "Alert not found",
        "details": {
            "index": settings.elasticsearch_alert_index,
            "event_id": "missing-alert",
        },
    }


def test_analyze_alert_returns_standard_error_when_alert_query_fails() -> None:
    class FailingQueryStorage(FakeAnalyzeStorage):
        def search_page(self, **_kwargs):
            raise RuntimeError("es unavailable")

    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="anom-1", storage=FailingQueryStorage(), analyzer=FakeAnalyzer())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "elasticsearch_query_failed",
        "message": "Failed to query alert for AI analysis",
        "details": {"index": settings.elasticsearch_alert_index, "event_id": "anom-1"},
    }


def test_analyze_alert_returns_standard_error_when_analysis_or_store_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        analyze_alert(event_id="anom-1", storage=FakeAnalyzeStorage(), analyzer=FailingAnalyzer())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "alert_analysis_failed",
        "message": "Failed to analyze alert and store AI report",
        "details": {
            "event_id": "anom-1",
            "ai_index": settings.elasticsearch_ai_index,
            "alert_index": settings.elasticsearch_alert_index,
        },
    }


def test_analyze_alert_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/alerts/{event_id}/analyze"]["post"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AIJudgement"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
