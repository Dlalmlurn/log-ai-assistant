import importlib

import pytest
from fastapi import HTTPException

from src.api.app import app, get_baseline_detail, list_baselines, rebuild_baselines


api_app_module = importlib.import_module("src.api.app")


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
    "access_profile": {"common_resources": ["/home", "/api/profile"]},
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

    def list_user_baselines(self, **kwargs):
        self.calls.append({"method": "list_user_baselines", **kwargs})
        return self.items, self.total

    def get_user_baseline(self, user_id: str, **kwargs):
        self.calls.append({"method": "get_user_baseline", "user_id": user_id, **kwargs})
        return self.items[0] if self.items else None


class FakeRebuildStorage:
    pass


class FailingBaselineStorage(FakeBaselineStorage):
    def list_user_baselines(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")

    def get_user_baseline(self, _user_id: str, **_kwargs):
        raise RuntimeError("clickhouse unavailable")


def test_list_baselines_queries_user_baselines_with_pagination() -> None:
    storage = FakeBaselineStorage(total=7)

    response = list_baselines(tenant_id="default", limit=25, offset=50, storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["user_id"] == "alice"
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50
    assert storage.calls == [
        {
            "method": "list_user_baselines",
            "tenant_id": "default",
            "limit": 25,
            "offset": 50,
        }
    ]


def test_get_baseline_detail_queries_user_baselines_by_user_id() -> None:
    storage = FakeBaselineStorage()

    response = get_baseline_detail(user_id="alice", tenant_id="default", storage=storage)
    payload = response.model_dump(mode="json")

    assert payload["user_id"] == "alice"
    assert payload["location_profile"]["common_ips"] == ["10.0.0.7"]
    assert storage.calls == [
        {
            "method": "get_user_baseline",
            "user_id": "alice",
            "tenant_id": "default",
        }
    ]


def test_get_baseline_detail_returns_clear_404_error_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_baseline_detail(user_id="missing-user", tenant_id=None, storage=FakeBaselineStorage(items=[]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "baseline_not_found",
        "message": "User baseline not found",
        "details": {"table": "ueba_user_baseline", "user_id": "missing-user"},
    }


def test_baseline_query_failures_return_standard_error_shape() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_baselines(tenant_id=None, limit=50, offset=0, storage=FailingBaselineStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "clickhouse_query_failed",
        "message": "Failed to query user baselines from ClickHouse",
        "details": {"table": "ueba_user_baseline"},
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
        "details": {"source_table": "security_logs", "target_table": "ueba_user_baseline"},
    }


def test_baselines_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/baselines/users"]["get"]

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
    operation = app.openapi()["paths"]["/api/v1/baselines/users/{user_id}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserBaseline"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
