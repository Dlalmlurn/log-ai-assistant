from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.app import aggregate_logs, app, get_log_detail, list_logs
from src.schemas import LogAggregateRequest, LogAggregateTimeRange


LOG_DOC = {
    "event_id": "evt-1",
    "event_time": "2026-05-13T10:00:00Z",
    "ingest_time": "2026-05-13T10:00:05Z",
    "tenant_id": "default",
    "source_type": "vpn",
    "log_type": "login",
    "user_id": "alice",
    "src_ip": "10.0.0.7",
    "action": "login",
    "result": "fail",
    "message": "VPN login failed",
    "raw_log": "raw vpn line",
    "risk_tags": [],
    "attrs": {"vpn_result": "bad_password"},
}


class FakeLogStorage:
    def __init__(self, item: dict[str, object] | None = None) -> None:
        self.item = item
        self.calls: list[dict[str, object]] = []

    def list_logs(self, **kwargs):
        self.calls.append({"method": "list_logs", **kwargs})
        return ([LOG_DOC], 7)

    def get_log(self, event_id: str):
        self.calls.append({"method": "get_log", "event_id": event_id})
        return self.item

    def aggregate_logs(self, **kwargs):
        self.calls.append({"method": "aggregate_logs", **kwargs})
        return [{"user_id": "alice", "result": "fail", "count": 3}]


class FailingLogStorage(FakeLogStorage):
    def list_logs(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")

    def get_log(self, _event_id: str):
        raise RuntimeError("clickhouse unavailable")

    def aggregate_logs(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")


def test_logs_endpoint_queries_clickhouse_with_pagination_and_filters() -> None:
    storage = FakeLogStorage()
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    response = list_logs(
        tenant_id="default",
        source_type="vpn",
        log_type="login",
        user_id="alice",
        src_ip="10.0.0.7",
        action="login",
        result="fail",
        start_time=start,
        end_time=end,
        limit=25,
        offset=50,
        storage=storage,
    )

    item = response.model_dump(mode="json")["items"][0]

    assert item["event_id"] == "evt-1"
    assert item["attrs"] == {"vpn_result": "bad_password"}
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50
    assert storage.calls == [
        {
            "method": "list_logs",
            "tenant_id": "default",
            "source_type": "vpn",
            "log_type": "login",
            "user_id": "alice",
            "src_ip": "10.0.0.7",
            "action": "login",
            "result": "fail",
            "start_time": start,
            "end_time": end,
            "limit": 25,
            "offset": 50,
        }
    ]


def test_log_detail_queries_clickhouse_by_event_id() -> None:
    storage = FakeLogStorage(item=LOG_DOC | {"result": "success", "attrs": {"vpn_result": "ok"}})

    response = get_log_detail(event_id="evt-1", storage=storage)
    item = response.model_dump(mode="json")

    assert item["event_id"] == "evt-1"
    assert item["attrs"] == {"vpn_result": "ok"}
    assert storage.calls == [{"method": "get_log", "event_id": "evt-1"}]


def test_log_detail_returns_clear_404_error_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_log_detail(event_id="missing-event", storage=FakeLogStorage(item=None))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "log_not_found",
        "message": "Structured log not found",
        "details": {"table": "security_logs", "event_id": "missing-event"},
    }


def test_logs_endpoint_returns_standard_error_when_clickhouse_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_logs(
            tenant_id=None,
            source_type=None,
            log_type=None,
            user_id=None,
            src_ip=None,
            action=None,
            result=None,
            start_time=None,
            end_time=None,
            limit=50,
            offset=0,
            storage=FailingLogStorage(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "clickhouse_query_failed",
        "message": "Failed to query structured logs from ClickHouse",
        "details": {"table": "security_logs"},
    }


def test_logs_aggregate_calls_clickhouse_adapter() -> None:
    storage = FakeLogStorage()
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    response = aggregate_logs(
        request=LogAggregateRequest(
            time_range=LogAggregateTimeRange(from_=start, to=end),
            filters={"tenant_id": "default", "source_type": "vpn"},
            group_by=["user_id", "result"],
            metrics=["count"],
            limit=20,
        ),
        storage=storage,
    )

    assert response.model_dump(mode="json") == {"items": [{"user_id": "alice", "result": "fail", "count": 3}]}
    assert storage.calls == [
        {
            "method": "aggregate_logs",
            "time_from": start,
            "time_to": end,
            "filters": {"tenant_id": "default", "source_type": "vpn"},
            "group_by": ["user_id", "result"],
            "metrics": ["count"],
            "limit": 20,
        }
    ]


def test_logs_aggregate_rejects_invalid_fields() -> None:
    class InvalidAggregateStorage(FakeLogStorage):
        def aggregate_logs(self, **_kwargs):
            raise ValueError("Unsupported group_by: raw_log")

    with pytest.raises(HTTPException) as exc_info:
        aggregate_logs(
            request=LogAggregateRequest(group_by=["raw_log"]),
            storage=InvalidAggregateStorage(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "invalid_log_aggregate_request"


def test_logs_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/logs"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NormalizedLogListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_log_detail_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/logs/{event_id}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NormalizedLog"
    }
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_logs_aggregate_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/logs/aggregate"]["post"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LogAggregateResponse"
    }
    assert operation["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
