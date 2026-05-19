from fastapi import HTTPException

from src.api.app import app, get_alert_detail
from src.config import settings


class FakeAlertDetailStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses: dict[str, list[dict[str, object]]] = {
            settings.elasticsearch_alert_index: [
                {
                    "_id": "alert-doc-1",
                    "alert_id": "alert-1",
                    "event_time": "2026-05-13T10:00:00Z",
                    "detect_time": "2026-05-13T10:00:10Z",
                    "username": "alice",
                    "src_ip": "203.0.113.9",
                    "source_type": "vpn",
                    "risk_level": "高",
                    "risk_score": 90,
                    "rule_hits": ["新IP登录后短时间访问敏感资源"],
                    "evidence": {
                        "username": "alice",
                        "src_ip": "203.0.113.9",
                        "resource": "/api/export",
                    },
                    "related_event_ids": ["evt-login", "evt-export"],
                    "related_logs_summary": "user=alice src_ip=203.0.113.9 action=api_call",
                    "status": "analyzed",
                    "llm_analysis_id": "ai-1",
                }
            ],
            settings.elasticsearch_baseline_index: [
                {
                    "_id": "baseline-doc-1",
                    "username": "alice",
                    "active_hours": ["09:00-18:00"],
                    "common_ips": ["10.0.0.7"],
                    "common_user_agents": ["Chrome"],
                    "avg_api_calls_per_minute": 2.0,
                    "common_resources": ["/home"],
                    "failed_login_count_7d": 0,
                    "sensitive_access_rate": 0.0,
                    "updated_at": "2026-05-13T09:00:00Z",
                }
            ],
            settings.elasticsearch_log_index: [
                {
                    "_id": "log-doc-2",
                    "event_id": "evt-export",
                    "event_time": "2026-05-13T10:02:00Z",
                    "ingest_time": "2026-05-13T10:02:05Z",
                    "source_type": "vpn",
                    "username": "alice",
                    "src_ip": "203.0.113.9",
                    "action": "api_call",
                    "resource": "/api/export",
                    "status": "success",
                    "message": "Export API called",
                    "raw_message": "raw export line",
                    "risk_tags": ["sensitive_resource"],
                    "original_fields": {},
                },
                {
                    "_id": "log-doc-1",
                    "event_id": "evt-login",
                    "event_time": "2026-05-13T10:00:00Z",
                    "ingest_time": "2026-05-13T10:00:05Z",
                    "source_type": "vpn",
                    "username": "alice",
                    "src_ip": "203.0.113.9",
                    "action": "login",
                    "resource": None,
                    "status": "success",
                    "message": "VPN login success",
                    "raw_message": "raw login line",
                    "risk_tags": [],
                    "original_fields": {},
                },
            ],
            settings.elasticsearch_ai_index: [
                {
                    "_id": "ai-doc-1",
                    "ai_report_id": "ai-1",
                    "alert_id": "alert-1",
                    "created_at": "2026-05-13T10:03:00Z",
                    "attack_type": "账号接管",
                    "risk_level": "高",
                    "reason": "New IP followed by export.",
                    "suggestion": "Review account activity.",
                    "confidence": 0.9,
                    "next_steps": ["disable session"],
                    "raw_response": {},
                }
            ],
        }

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        items = self.responses.get(str(kwargs["index"]), [])
        return items, len(items)


def test_alert_detail_composes_alert_baseline_related_logs_ai_report_and_evidence_chain() -> None:
    storage = FakeAlertDetailStorage()

    response = get_alert_detail(alert_id="alert-1", storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["alert"]["alert_id"] == "alert-1"
    assert payload["baseline"]["username"] == "alice"
    assert payload["ai_report"]["ai_report_id"] == "ai-1"
    assert [item["event_id"] for item in payload["related_logs"]] == ["evt-login", "evt-export"]
    assert "_id" not in payload["alert"]
    assert "_id" not in payload["baseline"]
    assert "_id" not in payload["ai_report"]
    assert all("_id" not in item for item in payload["related_logs"])
    assert payload["evidence_chain"]["rule_hits"] == ["新IP登录后短时间访问敏感资源"]
    assert "src_ip 203.0.113.9 is outside baseline common_ips" in payload["evidence_chain"]["baseline_deviations"]
    assert "resource /api/export is outside baseline common_resources" in payload["evidence_chain"]["baseline_deviations"]
    assert "related logs: 2" in payload["evidence_chain"]["risk_reason"]

    assert storage.calls == [
        {
            "index": settings.elasticsearch_alert_index,
            "query": {"term": {"alert_id": "alert-1"}},
            "limit": 1,
            "offset": 0,
        },
        {
            "index": settings.elasticsearch_baseline_index,
            "query": {"term": {"username": "alice"}},
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
        {
            "index": settings.elasticsearch_ai_index,
            "query": {"term": {"ai_report_id": "ai-1"}},
            "limit": 1,
            "offset": 0,
            "sort": [{"created_at": "desc"}],
        },
    ]


def test_alert_detail_returns_empty_related_context_when_optional_docs_are_missing() -> None:
    storage = FakeAlertDetailStorage()
    storage.responses[settings.elasticsearch_alert_index][0]["username"] = None
    storage.responses[settings.elasticsearch_alert_index][0]["related_event_ids"] = []
    storage.responses[settings.elasticsearch_alert_index][0]["llm_analysis_id"] = None
    storage.responses[settings.elasticsearch_ai_index] = []

    response = get_alert_detail(alert_id="alert-1", storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["baseline"] == {}
    assert payload["related_logs"] == []
    assert payload["ai_report"] == {}
    assert payload["evidence_chain"]["baseline_deviations"] == []
    assert "baseline is missing" in payload["evidence_chain"]["risk_reason"]


def test_alert_detail_returns_clear_404_error_when_missing() -> None:
    storage = FakeAlertDetailStorage()
    storage.responses[settings.elasticsearch_alert_index] = []

    try:
        get_alert_detail(alert_id="missing-alert", storage=storage)
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == {
            "code": "alert_not_found",
            "message": "Alert not found",
            "details": {
                "index": settings.elasticsearch_alert_index,
                "alert_id": "missing-alert",
            },
        }
    else:
        raise AssertionError("expected HTTPException")


def test_alert_detail_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/alerts/{alert_id}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AlertDetailResponse"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
