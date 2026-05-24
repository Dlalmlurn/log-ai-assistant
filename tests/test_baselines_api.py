import importlib

import pytest
from fastapi import HTTPException

from src.api.app import app, get_baseline_detail, list_baselines, rebuild_baselines
from src.config import settings


api_app_module = importlib.import_module("src.api.app")


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
        "common_resources": ["/home", "/api/profile"],
        "avg_api_calls_per_minute": 2.4,
        "sensitive_access_rate": 0.02,
    },
    "volume_profile": {},
    "result_profile": {"failed_login_count_7d": 1},
    "why_profile": {},
    "fallback_level": "none",
    "created_at": "2026-05-13T10:00:00Z",
}


class FakeBaselineStorage:
    def __init__(self, items: list[dict[str, object]] | None = None, total: int | None = None) -> None:
        self.items = items if items is not None else [BASELINE_DOC]
        self.total = len(self.items) if total is None else total
        self.calls: list[dict[str, object]] = []

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        return self.items, self.total


class FakeRebuildStorage:
    def __init__(self) -> None:
        self.ensure_indices_called = False

    def ensure_indices(self) -> None:
        self.ensure_indices_called = True


class FailingBaselineStorage:
    def search_page(self, **_kwargs):
        raise RuntimeError("es unavailable")


class FailingRebuildStorage:
    def ensure_indices(self) -> None:
        raise RuntimeError("es unavailable")


def test_list_baselines_queries_user_baselines_with_pagination() -> None:
    storage = FakeBaselineStorage(total=7)

    response = list_baselines(limit=25, offset=50, storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["user_id"] == "alice"
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
            "sort": [{"created_at": "desc"}],
        }
    ]


def test_get_baseline_detail_queries_user_baselines_by_user_id() -> None:
    storage = FakeBaselineStorage()

    response = get_baseline_detail(user_id="alice", storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["user_id"] == "alice"
    assert payload["location_profile"]["common_ips"] == ["10.0.0.7"]
    assert "_id" not in payload
    assert storage.calls == [
        {
            "index": settings.elasticsearch_baseline_index,
            "query": {"term": {"user_id": "alice"}},
            "limit": 1,
            "offset": 0,
        }
    ]


def test_get_baseline_detail_returns_clear_404_error_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_baseline_detail(user_id="missing-user", storage=FakeBaselineStorage(items=[]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "baseline_not_found",
        "message": "User baseline not found",
        "details": {
            "index": settings.elasticsearch_baseline_index,
            "user_id": "missing-user",
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


def test_rebuild_baselines_uses_existing_builder_and_returns_count(monkeypatch) -> None:
    storage = FakeRebuildStorage()
    calls: list[object] = []

    def fake_build_and_store_baselines(passed_storage):
        calls.append(passed_storage)
        return [object(), object(), object()]

    monkeypatch.setattr(api_app_module, "build_and_store_baselines", fake_build_and_store_baselines)

    response = rebuild_baselines(storage=storage)

    assert response.model_dump() == {"rebuilt_count": 3}
    assert storage.ensure_indices_called is True
    assert calls == [storage]


def test_rebuild_baselines_returns_standard_error_shape_when_builder_fails(monkeypatch) -> None:
    def fake_build_and_store_baselines(_storage):
        raise RuntimeError("rebuild failed")

    monkeypatch.setattr(api_app_module, "build_and_store_baselines", fake_build_and_store_baselines)

    with pytest.raises(HTTPException) as exc_info:
        rebuild_baselines(storage=FakeRebuildStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "baseline_rebuild_failed",
        "message": "Failed to rebuild user baselines",
        "details": {
            "source_index": settings.elasticsearch_log_index,
            "target_index": settings.elasticsearch_baseline_index,
        },
    }


def test_rebuild_baselines_returns_standard_error_shape_when_index_setup_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        rebuild_baselines(storage=FailingRebuildStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "baseline_rebuild_failed",
        "message": "Failed to rebuild user baselines",
        "details": {
            "source_index": settings.elasticsearch_log_index,
            "target_index": settings.elasticsearch_baseline_index,
        },
    }


def test_baselines_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserBaselineListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_baseline_rebuild_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines/rebuild"]["post"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/BaselineRebuildResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_baseline_detail_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines/{user_id}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserBaseline"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
