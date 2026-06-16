from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from src.api.app import app, create_feedback, get_stats_overview, list_user_risk_stats
from src.schemas import FeedbackCreateRequest


class FakeWorkbenchStorage:
    def __init__(self) -> None:
        self.inserted_feedback = []
        self.calls: list[dict] = []

    def insert_feedback(self, feedback):
        self.inserted_feedback.append(feedback)

    def get_stats_overview(self, **kwargs):
        self.calls.append({"method": "get_stats_overview", **kwargs})
        return {
            "log_count": 100,
            "latest_log_ingest_time": datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
            "anomaly_count": 5,
            "high_risk_count": 2,
            "critical_count": 1,
        }

    def list_user_risk_stats(self, **kwargs):
        self.calls.append({"method": "list_user_risk_stats", **kwargs})
        return (
            [
                {
                    "user_id": "alice",
                    "window": "7d",
                    "anomaly_count": 4,
                    "high_risk_count": 2,
                    "critical_count": 1,
                    "max_risk_score": 96,
                    "active_risk_score": 180,
                    "decayed_risk_score": 126.5,
                    "false_positive_excluded_count": 1,
                    "latest_event_time": datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
                }
            ],
            1,
        )


class FailingWorkbenchStorage(FakeWorkbenchStorage):
    def insert_feedback(self, _feedback):
        raise RuntimeError("clickhouse unavailable")

    def get_stats_overview(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")

    def list_user_risk_stats(self, **_kwargs):
        raise RuntimeError("clickhouse unavailable")


def test_create_feedback_writes_pending_feedback() -> None:
    storage = FakeWorkbenchStorage()
    request = FeedbackCreateRequest(
        event_id="anom-1",
        judgement_id="ai-1",
        tenant_id="default",
        user_id="alice",
        feedback_type="false_positive",
        suggestion="Lower risk after analyst review.",
        target_component="scoring",
        confidence=0.8,
    )

    response = create_feedback(request=request, storage=storage)

    assert response.feedback_id.startswith("fb-")
    assert response.review_status == "pending"
    assert response.event_id == "anom-1"
    assert storage.inserted_feedback == [response]


def test_create_feedback_returns_standard_error_on_write_failure() -> None:
    request = FeedbackCreateRequest(
        event_id="anom-1",
        feedback_type="data_contract",
        suggestion="Missing source IP.",
        target_component="data_contract",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_feedback(request=request, storage=FailingWorkbenchStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "feedback_write_failed"
    assert exc_info.value.detail["details"]["table"] == "ai_feedback"


def test_get_stats_overview_queries_storage_with_filters() -> None:
    storage = FakeWorkbenchStorage()
    start = datetime(2026, 5, 13, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)

    response = get_stats_overview(tenant_id="default", start_time=start, end_time=end, storage=storage)

    assert response.log_count == 100
    assert response.critical_count == 1
    assert storage.calls == [
        {"method": "get_stats_overview", "tenant_id": "default", "start_time": start, "end_time": end}
    ]


def test_get_stats_overview_returns_standard_error_on_query_failure() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_stats_overview(tenant_id=None, start_time=None, end_time=None, storage=FailingWorkbenchStorage())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "clickhouse_query_failed"


def test_list_user_risk_stats_queries_storage_with_pagination() -> None:
    storage = FakeWorkbenchStorage()

    response = list_user_risk_stats(
        tenant_id="default",
        window="7d",
        start_time=None,
        end_time=None,
        limit=10,
        offset=20,
        storage=storage,
    )

    assert response.total == 1
    assert response.items[0].user_id == "alice"
    assert response.items[0].high_risk_count == 2
    assert response.items[0].window == "7d"
    assert response.items[0].false_positive_excluded_count == 1
    assert storage.calls == [
        {
            "method": "list_user_risk_stats",
            "tenant_id": "default",
            "window": "7d",
            "start_time": None,
            "end_time": None,
            "limit": 10,
            "offset": 20,
        }
    ]


def test_feedback_and_stats_openapi_bind_contracts() -> None:
    openapi = app.openapi()["paths"]

    assert openapi["/api/v1/feedback"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AIFeedback"
    }
    assert openapi["/api/v1/stats/overview"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/StatsOverviewResponse"
    }
    assert openapi["/api/v1/stats/users/risk"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UserRiskStatsListResponse"
    }
