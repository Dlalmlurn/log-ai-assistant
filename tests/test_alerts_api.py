from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.app import app, list_alerts


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
    "ai_status": "not_required",
    "status": "new",
    "created_at": "2026-05-13T10:00:10Z",
}


class FakeAlertStorage:
    def __init__(self, items: list[dict[str, object]] | None = None, total: int | None = None) -> None:
        self.items = items if items is not None else [ALERT_DOC]
        self.total = len(self.items) if total is None else total
        self.calls: list[dict[str, object]] = []

    def list_anomalies(self, **kwargs):
        self.calls.append(kwargs)
        return self.items, self.total


class FailingAlertStorage:
    def list_anomalies(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")


def test_list_alerts_queries_clickhouse_anomalies_with_pagination_and_filters() -> None:
    storage = FakeAlertStorage(total=7)
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    response = list_alerts(
        tenant_id="default",
        risk_level="high",
        user_id="alice",
        src_ip="203.0.113.9",
        reason_code="new_source_then_sensitive_access",
        ai_status="pending",
        status="new",
        start_time=start,
        end_time=end,
        limit=25,
        offset=50,
        storage=storage,
    )
    payload = response.model_dump(mode="json")

    assert payload["items"][0]["event_id"] == "anom-1"
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50
    assert storage.calls == [
        {
            "tenant_id": "default",
            "risk_level": "high",
            "user_id": "alice",
            "src_ip": "203.0.113.9",
            "reason_code": "new_source_then_sensitive_access",
            "ai_status": "pending",
            "status": "new",
            "start_time": start,
            "end_time": end,
            "limit": 25,
            "offset": 50,
        }
    ]


def test_list_alerts_allows_critical_risk_level() -> None:
    storage = FakeAlertStorage(items=[ALERT_DOC | {"risk_level": "critical", "risk_score": 100}])

    response = list_alerts(
        tenant_id=None,
        risk_level="critical",
        user_id=None,
        src_ip=None,
        reason_code=None,
        ai_status=None,
        status=None,
        start_time=None,
        end_time=None,
        limit=50,
        offset=0,
        storage=storage,
    )

    assert response.items[0].risk_level == "critical"
    assert storage.calls[0]["risk_level"] == "critical"


def test_list_alerts_returns_standard_error_shape_when_query_fails() -> None:
    with pytest.raises(HTTPException) as exc_info:
        list_alerts(
            tenant_id=None,
            risk_level=None,
            user_id=None,
            src_ip=None,
            reason_code=None,
            ai_status=None,
            status=None,
            start_time=None,
            end_time=None,
            limit=50,
            offset=0,
            storage=FailingAlertStorage(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "clickhouse_query_failed",
        "message": "Failed to query anomaly events from ClickHouse",
        "details": {"table": "anomaly_events"},
    }


def test_alerts_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/anomalies"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnomalyEventListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
