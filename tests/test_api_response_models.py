import json
from datetime import date, datetime, timezone

from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.app import app, http_exception_handler
from src.schemas import (
    AIFeedback,
    AIJudgement,
    AIJudgementListResponse,
    AnomalyEvent,
    AnomalyEventListResponse,
    DataQualityMetric,
    DailyReportListResponse,
    ErrorResponse,
    ListResponse,
    NormalizedLog,
    NormalizedLogListResponse,
    UserDailyFeature,
    UserBaselineListResponse,
)


def test_list_response_contract_defaults() -> None:
    response = ListResponse[dict[str, str]]()

    assert response.model_dump(mode="json") == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_domain_list_responses_share_contract_shape() -> None:
    for response_model in (
        NormalizedLogListResponse,
        AnomalyEventListResponse,
        UserBaselineListResponse,
        AIJudgementListResponse,
        DailyReportListResponse,
    ):
        assert response_model().model_dump(mode="json") == {
            "items": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
        }


def test_error_response_contract_defaults() -> None:
    response = ErrorResponse(code="not_found", message="Missing")

    assert response.model_dump(mode="json") == {
        "code": "not_found",
        "message": "Missing",
        "details": {},
    }


def test_formal_p0_models_use_new_contract_fields() -> None:
    now = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    log = NormalizedLog(
        event_id="evt-1",
        event_time=now,
        ingest_time=now,
        tenant_id="default",
        source_type="vpn",
        log_type="login",
        user_id="alice",
        action="login",
        result="success",
        message="VPN login success",
        raw_log="raw line",
    )
    anomaly = AnomalyEvent(
        event_id="anom-1",
        event_time=now,
        detect_time=now,
        tenant_id="default",
        user_id="alice",
        risk_score=90,
        risk_level="high",
        rule_hits=["new ip"],
        reason_codes=["new_source_ip"],
        related_event_ids=[log.event_id],
        created_at=now,
    )
    judgement = AIJudgement(
        judgement_id="ai-1",
        event_id=anomaly.event_id,
        created_at=now,
        model_name="mock-security-analyst",
        risk_level="high",
        attack_type="account_takeover",
        judgement="Suspicious login.",
        confidence=0.8,
        is_mock=True,
    )
    feedback = AIFeedback(
        feedback_id="fb-1",
        event_id=anomaly.event_id,
        tenant_id="default",
        feedback_type="false_positive",
        suggestion="Lower score for this pattern.",
        target_component="scoring",
        confidence=0.7,
        created_at=now,
    )
    feature = UserDailyFeature(
        feature_date=date(2026, 5, 13),
        tenant_id="default",
        user_id="alice",
        login_count=3,
        failed_login_count=1,
        success_login_count=2,
        distinct_src_ip_count=1,
        distinct_host_count=1,
        distinct_action_count=2,
        first_seen_time=now,
        last_seen_time=now,
        night_event_count=0,
        sensitive_action_count=1,
        download_count=1,
        permission_change_count=0,
        new_source_count=1,
        created_at=now,
    )
    metric = DataQualityMetric(
        metric_date=date(2026, 5, 13),
        tenant_id="default",
        source_type="vpn",
        generated_count=10,
        raw_logs_count=10,
        parsed_logs_count=10,
        clickhouse_insert_count=10,
        security_logs_count=10,
        raw_size_bytes=1000,
        table_size_bytes=300,
        compression_ratio=3.33,
        missing_event_time_rate=0,
        missing_user_id_rate=0,
        missing_src_ip_rate=0,
        missing_action_rate=0,
        missing_result_rate=0,
        parse_error_rate=0,
        created_at=now,
    )

    assert log.model_dump()["user_id"] == "alice"
    assert log.model_dump()["result"] == "success"
    assert log.model_dump()["raw_log"] == "raw line"
    assert anomaly.reason_codes == ["new_source_ip"]
    assert judgement.is_mock is True
    assert feedback.review_status == "pending"
    assert feature.new_source_count == 1
    assert metric.security_logs_count == 10


async def _call_http_exception_handler() -> tuple[int, dict[str, object]]:
    response = await http_exception_handler(None, StarletteHTTPException(status_code=404))
    return response.status_code, json.loads(response.body)


def test_api_404_handler_uses_standard_error_response() -> None:
    import asyncio

    status_code, payload = asyncio.run(_call_http_exception_handler())

    assert status_code == 404
    assert payload == {
        "code": "not_found",
        "message": "Not Found",
        "details": {},
    }


def test_health_openapi_documents_standard_error_response() -> None:
    health_operation = app.openapi()["paths"]["/api/v1/health"]["get"]

    assert health_operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert health_operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
