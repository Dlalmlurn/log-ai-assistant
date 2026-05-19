import importlib

import pytest
from fastapi import HTTPException

from src.api.app import app, list_ai_reports, list_daily_reports, create_daily_report
from src.config import settings


api_app_module = importlib.import_module("src.api.app")


AI_REPORT_DOC = {
    "_id": "es-internal-id",
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

DAILY_REPORT_DOC = {
    "_id": "es-internal-id",
    "report_id": "daily-1",
    "date": "2026-05-13",
    "created_at": "2026-05-13T23:00:00Z",
    "overall_score": 85.0,
    "log_count": 1200,
    "alert_count": 15,
    "high_risk_count": 3,
    "major_risks": ["暴力破解", "账号接管"],
    "high_risk_users": ["alice", "bob"],
    "typical_alerts": [],
    "ai_summary": "今日共处理日志 1200 条。",
    "recommendation": "优先处置暴力破解相关事件。",
    "markdown": "# 每日安全态势简报",
}


class FakeStorage:
    def __init__(self, items=None, total=None):
        self.items = items if items is not None else []
        self.total = len(self.items) if total is None else total
        self.calls: list[dict] = []
        self.indexed: list[dict] = []
        self.ensure_indices_called = False

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        return self.items, self.total

    def ensure_indices(self):
        self.ensure_indices_called = True

    def index_document(self, index, document, doc_id=None):
        self.indexed.append({"index": index, "document": document, "doc_id": doc_id})


class FailingStorage:
    def search_page(self, **_kwargs):
        raise RuntimeError("es unavailable")

    def ensure_indices(self):
        raise RuntimeError("es unavailable")


# --- GET /api/v1/ai-reports ---


def test_list_ai_reports_queries_ai_index_with_pagination():
    storage = FakeStorage(items=[AI_REPORT_DOC], total=5)

    response = list_ai_reports(limit=20, offset=10, storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["ai_report_id"] == "ai-1"
    assert "_id" not in payload["items"][0]
    assert response.total == 5
    assert response.limit == 20
    assert response.offset == 10
    assert storage.calls == [
        {
            "index": settings.elasticsearch_ai_index,
            "query": {"match_all": {}},
            "limit": 20,
            "offset": 10,
            "sort": [{"created_at": "desc"}],
        }
    ]


def test_list_ai_reports_returns_standard_error_on_es_failure():
    with pytest.raises(HTTPException) as exc_info:
        list_ai_reports(storage=FailingStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "elasticsearch_query_failed"
    assert exc_info.value.detail["details"]["index"] == settings.elasticsearch_ai_index


# --- GET /api/v1/daily-reports ---


def test_list_daily_reports_queries_daily_index_with_pagination():
    storage = FakeStorage(items=[DAILY_REPORT_DOC], total=3)

    response = list_daily_reports(limit=10, offset=0, storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["report_id"] == "daily-1"
    assert "_id" not in payload["items"][0]
    assert response.total == 3
    assert response.limit == 10
    assert response.offset == 0
    assert storage.calls == [
        {
            "index": settings.elasticsearch_daily_index,
            "query": {"match_all": {}},
            "limit": 10,
            "offset": 0,
            "sort": [{"date": "desc"}],
        }
    ]


def test_list_daily_reports_returns_standard_error_on_es_failure():
    with pytest.raises(HTTPException) as exc_info:
        list_daily_reports(storage=FailingStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "elasticsearch_query_failed"
    assert exc_info.value.detail["details"]["index"] == settings.elasticsearch_daily_index


# --- POST /api/v1/daily-reports ---


def test_create_daily_report_generates_and_stores_report(monkeypatch):
    from src.schemas import DailyReport
    from datetime import datetime, timezone

    fake_report = DailyReport(
        report_id="daily-gen-1",
        date="2026-05-13",
        created_at=datetime(2026, 5, 13, 23, 0, 0, tzinfo=timezone.utc),
        overall_score=90.0,
        log_count=500,
        alert_count=5,
        high_risk_count=1,
        major_risks=["暴力破解"],
        high_risk_users=["alice"],
        typical_alerts=[],
        ai_summary="今日共处理日志 500 条。",
        recommendation="持续监控。",
        markdown="# 简报",
    )

    def fake_generate(storage, date_str=None):
        return fake_report

    monkeypatch.setattr(api_app_module, "generate_daily_report", fake_generate)
    storage = FakeStorage()

    response = create_daily_report(date="2026-05-13", storage=storage)

    assert response.report_id == "daily-gen-1"
    assert response.date == "2026-05-13"
    assert storage.ensure_indices_called is True
    assert len(storage.indexed) == 1
    assert storage.indexed[0]["index"] == settings.elasticsearch_daily_index
    assert storage.indexed[0]["doc_id"] == "daily-gen-1"


def test_create_daily_report_returns_error_on_invalid_date(monkeypatch):
    def fake_generate(storage, date_str=None):
        raise ValueError("time data 'bad-date' does not match format '%Y-%m-%d'")

    monkeypatch.setattr(api_app_module, "generate_daily_report", fake_generate)
    storage = FakeStorage()

    with pytest.raises(HTTPException) as exc_info:
        create_daily_report(date="bad-date", storage=storage)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "invalid_date"


def test_create_daily_report_returns_error_on_generation_failure(monkeypatch):
    def fake_generate(storage, date_str=None):
        raise RuntimeError("es unavailable")

    monkeypatch.setattr(api_app_module, "generate_daily_report", fake_generate)
    storage = FakeStorage()

    with pytest.raises(HTTPException) as exc_info:
        create_daily_report(date="2026-05-13", storage=storage)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "daily_report_generation_failed"


# --- OpenAPI contract checks ---


def test_ai_reports_openapi_binds_contract():
    operation = app.openapi()["paths"]["/api/v1/ai-reports"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AIReportListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_daily_reports_list_openapi_binds_contract():
    operation = app.openapi()["paths"]["/api/v1/daily-reports"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DailyReportListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_daily_reports_create_openapi_binds_contract():
    operation = app.openapi()["paths"]["/api/v1/daily-reports"]["post"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DailyReport"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
