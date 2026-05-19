import pytest
from fastapi import HTTPException

from src.api.app import app, get_baseline_detail, list_baselines
from src.config import settings


BASELINE_DOC = {
    "_id": "baseline-doc-1",
    "username": "alice",
    "active_hours": ["09:00-18:00"],
    "common_ips": ["10.0.0.7"],
    "common_user_agents": ["Chrome"],
    "avg_api_calls_per_minute": 2.4,
    "common_resources": ["/home", "/api/profile"],
    "failed_login_count_7d": 1,
    "sensitive_access_rate": 0.02,
    "updated_at": "2026-05-13T10:00:00Z",
}


class FakeBaselineStorage:
    def __init__(self, items: list[dict[str, object]] | None = None, total: int | None = None) -> None:
        self.items = items if items is not None else [BASELINE_DOC]
        self.total = len(self.items) if total is None else total
        self.calls: list[dict[str, object]] = []

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        return self.items, self.total


class FailingBaselineStorage:
    def search_page(self, **_kwargs):
        raise RuntimeError("es unavailable")


def test_list_baselines_queries_user_baselines_with_pagination() -> None:
    storage = FakeBaselineStorage(total=7)

    response = list_baselines(limit=25, offset=50, storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["username"] == "alice"
    assert "_id" not in payload["items"][0]
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50
    assert storage.calls == [
        {
            "index": settings.elasticsearch_baseline_index,
            "query": {"match_all": {}},
            "limit": 25,
            "offset": 50,
            "sort": [{"updated_at": "desc"}],
        }
    ]


def test_get_baseline_detail_queries_user_baselines_by_username() -> None:
    storage = FakeBaselineStorage()

    response = get_baseline_detail(username="alice", storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["username"] == "alice"
    assert payload["common_ips"] == ["10.0.0.7"]
    assert "_id" not in payload
    assert storage.calls == [
        {
            "index": settings.elasticsearch_baseline_index,
            "query": {"term": {"username": "alice"}},
            "limit": 1,
            "offset": 0,
        }
    ]


def test_get_baseline_detail_returns_clear_404_error_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_baseline_detail(username="missing-user", storage=FakeBaselineStorage(items=[]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "baseline_not_found",
        "message": "User baseline not found",
        "details": {
            "index": settings.elasticsearch_baseline_index,
            "username": "missing-user",
        },
    }


def test_baseline_query_failures_return_standard_error_shape() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_baselines(storage=FailingBaselineStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "elasticsearch_query_failed",
        "message": "Failed to query user baselines from Elasticsearch",
        "details": {"index": settings.elasticsearch_baseline_index},
    }


def test_baselines_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserBaselineListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_baseline_detail_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines/{username}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserBaseline"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
