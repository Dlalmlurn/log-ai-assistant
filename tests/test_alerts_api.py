from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.app import _build_alerts_query, app, list_alerts
from src.config import settings
from src.storage.elastic_client import ElasticStorage


ALERT_DOC = {
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
    "evidence": {"username": "alice", "src_ip": "203.0.113.9", "resource": "/api/export"},
    "related_event_ids": ["evt-login", "evt-export"],
    "related_logs_summary": "user=alice src_ip=203.0.113.9 action=api_call",
    "status": "new",
    "llm_analysis_id": None,
}


class FakeAlertStorage:
    def __init__(self, items: list[dict[str, object]] | None = None, total: int | None = None) -> None:
        self.items = items if items is not None else [ALERT_DOC]
        self.total = len(self.items) if total is None else total
        self.calls: list[dict[str, object]] = []

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        return self.items, self.total


class FailingAlertStorage:
    def search_page(self, **_kwargs):
        raise RuntimeError("es unavailable")


def test_alerts_query_applies_documented_filters() -> None:
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    query = _build_alerts_query(
        risk_level="高",
        username="alice",
        rule="新IP登录",
        status="new",
        start_time=start,
        end_time=end,
    )

    assert query == {
        "bool": {
            "filter": [
                {
                    "range": {
                        "detect_time": {
                            "gte": "2026-05-13T09:00:00+00:00",
                            "lte": "2026-05-13T10:00:00+00:00",
                        }
                    }
                },
                {"term": {"risk_level": "高"}},
                {"term": {"username": "alice"}},
                {"term": {"status": "new"}},
                {"match_phrase": {"rule_hits": "新IP登录"}},
            ]
        }
    }


def test_alerts_query_uses_match_all_when_no_filters_are_provided() -> None:
    assert _build_alerts_query() == {"match_all": {}}


def test_list_alerts_queries_security_alerts_with_pagination_and_filters() -> None:
    storage = FakeAlertStorage(total=7)
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    response = list_alerts(
        risk_level="高",
        username="alice",
        rule="新IP登录",
        status="new",
        start_time=start,
        end_time=end,
        limit=25,
        offset=50,
        storage=storage,
    )
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["alert_id"] == "alert-1"
    assert "_id" not in payload["items"][0]
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50
    assert storage.calls == [
        {
            "index": settings.elasticsearch_alert_index,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "detect_time": {
                                    "gte": "2026-05-13T09:00:00+00:00",
                                    "lte": "2026-05-13T10:00:00+00:00",
                                }
                            }
                        },
                        {"term": {"risk_level": "高"}},
                        {"term": {"username": "alice"}},
                        {"term": {"status": "new"}},
                        {"match_phrase": {"rule_hits": "新IP登录"}},
                    ]
                }
            },
            "limit": 25,
            "offset": 50,
            "sort": [{"detect_time": "desc"}],
        }
    ]


def test_list_alerts_allows_emergency_risk_level() -> None:
    storage = FakeAlertStorage(items=[ALERT_DOC | {"risk_level": "紧急", "risk_score": 100}])

    response = list_alerts(
        risk_level="紧急",
        username=None,
        rule=None,
        status=None,
        start_time=None,
        end_time=None,
        limit=50,
        offset=0,
        storage=storage,
    )

    assert response.items[0].risk_level == "紧急"
    assert storage.calls[0]["query"] == {"bool": {"filter": [{"term": {"risk_level": "紧急"}}]}}


def test_list_alerts_returns_standard_error_shape_when_query_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_alerts(
            risk_level=None,
            username=None,
            rule=None,
            status=None,
            start_time=None,
            end_time=None,
            limit=50,
            offset=0,
            storage=FailingAlertStorage(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "elasticsearch_query_failed",
        "message": "Failed to query security alerts from Elasticsearch",
        "details": {"index": settings.elasticsearch_alert_index},
    }


def test_alerts_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/alerts"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AlertEventListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_elastic_search_page_supports_alert_sort_chain() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.call: dict[str, object] | None = None

        def search(self, *, index: str, body: dict[str, object]):
            self.call = {"index": index, "body": body}
            return {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [{"_id": "alert-doc-1", "_source": {"alert_id": "alert-1"}}],
                }
            }

    client = FakeClient()
    storage = ElasticStorage.__new__(ElasticStorage)
    storage.client = client

    items, total = storage.search_page(
        index="security-alerts",
        query={"match_all": {}},
        limit=10,
        offset=20,
        sort=[{"detect_time": "desc"}],
    )

    assert items == [{"alert_id": "alert-1", "_id": "alert-doc-1"}]
    assert total == 1
    assert client.call == {
        "index": "security-alerts",
        "body": {
            "query": {"match_all": {}},
            "from": 20,
            "size": 10,
            "track_total_hits": True,
            "sort": [{"detect_time": "desc"}],
        },
    }
