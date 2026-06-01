from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.ai_engine import AIAnalyzer
from src.config import settings
from src.health import HealthResponse, get_health_status
from src.report.daily_report import generate_daily_report
from src.schemas import (
    AIJudgement,
    AIJudgementListResponse,
    AnomalyDetailResponse,
    AnomalyEvent,
    AnomalyEventListResponse,
    BaselineRebuildResponse,
    DailyReport,
    DailyReportListResponse,
    ErrorResponse,
    EvidenceChain,
    LogAggregateRequest,
    LogAggregateResponse,
    NormalizedLog,
    NormalizedLogListResponse,
    RiskLevel,
    SourceType,
    UserBaseline,
    UserBaselineListResponse,
)
from src.storage import ClickHouseStorage
from src.ueba import build_and_store_baselines
from src.ueba.baseline import aggregate_daily_features, update_seen_sources


ERROR_RESPONSE_SCHEMA = {
    "model": ErrorResponse,
    "description": "Standard error response with code, message, and details.",
}
STANDARD_ERROR_RESPONSES = {
    400: ERROR_RESPONSE_SCHEMA,
    404: ERROR_RESPONSE_SCHEMA,
    422: ERROR_RESPONSE_SCHEMA,
    500: ERROR_RESPONSE_SCHEMA,
}
HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
}


app = FastAPI(
    title="Log AI Assistant API",
    version="0.1.0",
    description="FastAPI layer for the formal Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React path.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["system"],
    summary="System health status",
    description="REQ-001, REQ-002, REQ-007: report Kafka, Flink, ClickHouse, DashScope config, latest log ingest time, and consumer lag.",
)
def health_check() -> HealthResponse:
    return get_health_status()

def get_storage() -> ClickHouseStorage:
    return ClickHouseStorage()


def get_analyzer() -> AIAnalyzer:
    return AIAnalyzer()


@app.get(
    "/api/v1/logs",
    response_model=NormalizedLogListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["logs"],
    summary="Query structured security logs",
    description="REQ-002, REQ-006: query normalized logs for the React realtime log view.",
)
def list_logs(
    tenant_id: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    log_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    src_ip: str | None = Query(default=None),
    action: str | None = Query(default=None),
    result: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ClickHouseStorage = Depends(get_storage),
) -> NormalizedLogListResponse:
    try:
        items, total = storage.list_logs(
            tenant_id=tenant_id,
            source_type=source_type,
            log_type=log_type,
            user_id=user_id,
            src_ip=src_ip,
            action=action,
            result=result,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query structured logs from ClickHouse",
                "details": {"table": "security_logs"},
            },
        ) from exc

    return NormalizedLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/logs/{event_id}",
    response_model=NormalizedLog,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["logs"],
    summary="Get structured security log detail",
    description="REQ-002, REQ-006: fetch one normalized log by event_id.",
)
def get_log_detail(
    event_id: str,
    storage: ClickHouseStorage = Depends(get_storage),
) -> NormalizedLog:
    try:
        item = storage.get_log(event_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query structured log detail from ClickHouse",
                "details": {"table": "security_logs", "event_id": event_id},
            },
        ) from exc

    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "log_not_found",
                "message": "Structured log not found",
                "details": {"table": "security_logs", "event_id": event_id},
            },
        )

    return NormalizedLog(**item)


@app.post(
    "/api/v1/logs/aggregate",
    response_model=LogAggregateResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["logs"],
    summary="Aggregate structured security logs",
    description="REQ-002, REQ-006: aggregate normalized logs for trend and distribution views.",
)
def aggregate_logs(
    request: LogAggregateRequest,
    storage: ClickHouseStorage = Depends(get_storage),
) -> LogAggregateResponse:
    try:
        rows = storage.aggregate_logs(
            time_from=request.time_range.from_ if request.time_range else None,
            time_to=request.time_range.to if request.time_range else None,
            filters=request.filters,
            group_by=request.group_by,
            metrics=request.metrics,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_log_aggregate_request",
                "message": str(exc),
                "details": {},
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to aggregate structured logs from ClickHouse",
                "details": {"table": "security_logs"},
            },
        ) from exc

    return LogAggregateResponse(items=rows)


@app.get(
    "/api/v1/anomalies",
    response_model=AnomalyEventListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["anomalies"],
    summary="Query anomaly events",
    description="REQ-004, REQ-006, REQ-008: query anomaly events for the React abnormal event view.",
)
def list_alerts(
    tenant_id: str | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    user_id: str | None = Query(default=None),
    src_ip: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    ai_status: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ClickHouseStorage = Depends(get_storage),
) -> AnomalyEventListResponse:
    try:
        items, total = storage.list_anomalies(
            tenant_id=tenant_id,
            risk_level=risk_level,
            user_id=user_id,
            src_ip=src_ip,
            reason_code=reason_code,
            ai_status=ai_status,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query anomaly events from ClickHouse",
                "details": {"table": "anomaly_events"},
            },
        ) from exc

    return AnomalyEventListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/anomalies/{event_id}",
    response_model=AnomalyDetailResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["anomalies"],
    summary="Get anomaly detail with evidence chain",
    description="REQ-004, REQ-006: fetch anomaly, user baseline, related logs, AI judgement, and evidence chain.",
)
def get_alert_detail(
    event_id: str,
    storage: ClickHouseStorage = Depends(get_storage),
) -> AnomalyDetailResponse:
    try:
        alert = storage.get_anomaly(event_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query anomaly detail from ClickHouse",
                "details": {"table": "anomaly_events", "event_id": event_id},
            },
        ) from exc

    if not alert:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "anomaly_not_found",
                "message": "Anomaly event not found",
                "details": {"table": "anomaly_events", "event_id": event_id},
            },
        )

    try:
        baseline = _fetch_alert_baseline(storage, alert)
        related_logs = _fetch_related_logs(storage, alert)
        ai_report = _fetch_ai_report(storage, alert)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to assemble anomaly evidence from ClickHouse",
                "details": {"event_id": event_id},
            },
        ) from exc

    return AnomalyDetailResponse(
        anomaly=alert,
        baseline=baseline,
        related_logs=related_logs,
        ai_judgement=ai_report,
        evidence_chain=_build_evidence_chain(alert, baseline, related_logs),
    )


@app.post(
    "/api/v1/ai/judge/{event_id}",
    response_model=AIJudgement,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["ai"],
    summary="Judge an anomaly with AI",
    description="REQ-004: analyze an existing anomaly with anomaly, baseline, related_logs, and window_stats context, then store the AI judgement.",
)
def analyze_alert(
    event_id: str,
    storage: ClickHouseStorage = Depends(get_storage),
    analyzer: AIAnalyzer = Depends(get_analyzer),
) -> AIJudgement:
    try:
        alert = storage.get_anomaly(event_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query anomaly for AI judgement",
                "details": {"table": "anomaly_events", "event_id": event_id},
            },
        ) from exc

    if not alert:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "anomaly_not_found",
                "message": "Anomaly event not found",
                "details": {"table": "anomaly_events", "event_id": event_id},
            },
        )

    try:
        baseline = _fetch_alert_baseline(storage, alert)
        related_logs = _fetch_related_logs(storage, alert)
        report = analyzer.analyze(
            event=AnomalyEvent.model_validate(alert),
            baseline=baseline,
            related_logs=related_logs,
            window_stats={},
        )
        storage.insert_ai_judgement(report)
        storage.update_anomaly_ai_status(event_id, "analyzed")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ai_judgement_failed",
                "message": "Failed to judge anomaly and store AI judgement",
                "details": {"event_id": event_id},
            },
        ) from exc

    return report


@app.get(
    "/api/v1/baselines/users",
    response_model=UserBaselineListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["baselines"],
    summary="Query user behavior baselines",
    description="REQ-003, REQ-006: query user behavior baselines for the React baseline view.",
)
def list_baselines(
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ClickHouseStorage = Depends(get_storage),
) -> UserBaselineListResponse:
    try:
        items, total = storage.list_user_baselines(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query user baselines from ClickHouse",
                "details": {"table": "ueba_user_baseline"},
            },
        ) from exc

    return UserBaselineListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/api/v1/baselines/rebuild",
    response_model=BaselineRebuildResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["baselines"],
    summary="Rebuild user behavior baselines",
    description="REQ-003: rebuild user behavior baselines from all stored security logs.",
)
def rebuild_baselines(
    storage: ClickHouseStorage = Depends(get_storage),
) -> BaselineRebuildResponse:
    """Backfill daily features for all dates with logs, then rebuild baselines from ALL data."""
    try:
        # 1. Find the date range that has logs but may not have features yet
        from datetime import date as _date
        today = _date.today()
        first_log = storage._select_scalar(
            "SELECT min(event_time::Date) FROM security_logs WHERE tenant_id = {t:String}",
            parameters={"t": "default"},
            default=today,
        )
        if first_log is None:
            first_log = today

        # 2. Aggregate daily features for every day that has logs (backfill)
        agg_dates = 0
        d = first_log if isinstance(first_log, _date) else first_log
        while d <= today:
            aggregate_daily_features(storage, target_date=datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc))
            agg_dates += 1
            d += timedelta(days=1)

        # 3. Update seen sources for the full range
        update_seen_sources(storage)

        # 4. Build baselines from ALL available daily features (90-day window)
        baselines = build_and_store_baselines(storage)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "baseline_rebuild_failed",
                "message": "Failed to rebuild user baselines",
                "details": {"source_table": "security_logs", "target_table": "ueba_user_baseline"},
            },
        ) from exc

    return BaselineRebuildResponse(rebuilt_count=len(baselines))


@app.get(
    "/api/v1/baselines/users/{user_id}",
    response_model=UserBaseline,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["baselines"],
    summary="Get user behavior baseline detail",
    description="REQ-003, REQ-006: fetch one user behavior baseline.",
)
def get_baseline_detail(
    user_id: str,
    tenant_id: str | None = Query(default=None),
    storage: ClickHouseStorage = Depends(get_storage),
) -> UserBaseline:
    try:
        item = storage.get_user_baseline(user_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query user baseline from ClickHouse",
                "details": {"table": "ueba_user_baseline", "user_id": user_id},
            },
        ) from exc

    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "baseline_not_found",
                "message": "User baseline not found",
                "details": {"table": "ueba_user_baseline", "user_id": user_id},
            },
        )

    return UserBaseline(**item)


@app.get(
    "/api/v1/ai/judgements",
    response_model=AIJudgementListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["ai"],
    summary="Query AI judgements",
    description="REQ-004, REQ-006: query AI judgements for the React AI analysis view.",
)
def list_ai_reports(
    event_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ClickHouseStorage = Depends(get_storage),
) -> AIJudgementListResponse:
    try:
        items, total = storage.list_ai_judgements(
            event_id=event_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query AI judgements from ClickHouse",
                "details": {"table": "ai_judgements"},
            },
        ) from exc

    return AIJudgementListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/reports/daily",
    response_model=DailyReportListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["daily-reports"],
    summary="Query daily security reports",
    description="REQ-005, REQ-006: query daily security posture reports.",
)
def list_daily_reports(
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ClickHouseStorage = Depends(get_storage),
) -> DailyReportListResponse:
    try:
        items, total = storage.list_daily_reports(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "clickhouse_query_failed",
                "message": "Failed to query daily reports from ClickHouse",
                "details": {"table": "daily_security_reports"},
            },
        ) from exc

    return DailyReportListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/api/v1/reports/daily",
    response_model=DailyReport,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["daily-reports"],
    summary="Generate a daily security report",
    description="REQ-005: generate a daily security posture report for the specified date.",
)
def create_daily_report(
    date: str | None = Query(default=None, description="Date in YYYY-MM-DD format. Defaults to today (UTC)."),
    tenant_id: str = Query(default="default"),
    storage: ClickHouseStorage = Depends(get_storage),
) -> DailyReport:
    try:
        report = generate_daily_report(storage, date_str=date)
        storage.insert_daily_report(report, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_date",
                "message": str(exc),
                "details": {"date": date},
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "daily_report_generation_failed",
                "message": "Failed to generate daily report",
                "details": {"date": date, "source_table": "security_logs", "target_table": "daily_security_reports"},
            },
        ) from exc

    return report


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "Request validation failed",
        code="validation_error",
        details={"errors": jsonable_encoder(exc.errors())},
    )


def _error_response(
    status_code: int,
    detail: Any,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = _build_error_response(status_code, detail, code=code, details=details)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _build_error_response(
    status_code: int,
    detail: Any,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    if isinstance(detail, dict):
        detail_code = detail.get("code")
        detail_message = detail.get("message")
        detail_details = detail.get("details")
        if isinstance(detail_code, str) and isinstance(detail_message, str):
            return ErrorResponse(
                code=code or detail_code,
                message=detail_message,
                details=detail_details if isinstance(detail_details, dict) else details or {},
            )

    message = detail if isinstance(detail, str) else "Request failed"
    return ErrorResponse(
        code=code or HTTP_ERROR_CODES.get(status_code, "http_error"),
        message=message,
        details=details or {},
    )


def _fetch_alert_baseline(storage: ClickHouseStorage, alert: dict[str, Any]) -> dict[str, Any]:
    user_id = alert.get("user_id")
    if not user_id:
        return {}

    item = storage.get_user_baseline(str(user_id), tenant_id=str(alert.get("tenant_id") or "default"))
    return item or {}


def _fetch_related_logs(storage: ClickHouseStorage, alert: dict[str, Any]) -> list[dict[str, Any]]:
    related_event_ids = _string_list(alert.get("related_event_ids"))
    if not related_event_ids:
        return []

    return storage.list_logs_by_event_ids(related_event_ids)


def _fetch_ai_report(storage: ClickHouseStorage, alert: dict[str, Any]) -> dict[str, Any]:
    event_id = alert.get("event_id")
    if not event_id:
        return {}

    return storage.get_latest_ai_judgement(str(event_id)) or {}


def _build_evidence_chain(alert: dict[str, Any], baseline: dict[str, Any], related_logs: list[dict[str, Any]]) -> EvidenceChain:
    rule_hits = _string_list(alert.get("rule_hits"))
    baseline_deviations = _extract_baseline_deviations(alert, baseline, related_logs)
    risk_reason = _build_risk_reason(alert, rule_hits, baseline_deviations, related_logs, has_baseline=bool(baseline))
    return EvidenceChain(
        rule_hits=rule_hits,
        baseline_deviations=baseline_deviations,
        reason_codes=_string_list(alert.get("reason_codes")),
        risk_components=alert.get("risk_components") if isinstance(alert.get("risk_components"), dict) else {},
        ai_status=str(alert.get("ai_status") or "not_required"),
        risk_reason=risk_reason,
    )


def _extract_baseline_deviations(
    alert: dict[str, Any],
    baseline: dict[str, Any],
    related_logs: list[dict[str, Any]],
) -> list[str]:
    evidence = alert.get("evidence") if isinstance(alert.get("evidence"), dict) else {}
    explicit = evidence.get("baseline_deviations")
    if isinstance(explicit, list):
        return [str(item) for item in explicit]

    if not baseline:
        return []

    deviations: list[str] = []
    src_ip = _first_string(evidence.get("src_ip"), evidence.get("new_ip"), alert.get("src_ip"))
    location_profile = baseline.get("location_profile") if isinstance(baseline.get("location_profile"), dict) else {}
    access_profile = baseline.get("access_profile") if isinstance(baseline.get("access_profile"), dict) else {}
    time_profile = baseline.get("time_profile") if isinstance(baseline.get("time_profile"), dict) else {}
    result_profile = baseline.get("result_profile") if isinstance(baseline.get("result_profile"), dict) else {}

    common_ips = _string_list(location_profile.get("common_ips"))
    if src_ip and common_ips and src_ip not in common_ips:
        deviations.append(f"src_ip {src_ip} is outside baseline location_profile.common_ips")

    event_hour = _event_hour(alert.get("event_time"))
    active_hours = _string_list(time_profile.get("active_hours"))
    if event_hour is not None and active_hours and not _hour_in_ranges(event_hour, active_hours):
        deviations.append(f"event hour {event_hour:02d}:00 is outside baseline time_profile.active_hours")

    resource = _first_string(evidence.get("resource"), _first_related_value(related_logs, "resource"))
    common_resources = _string_list(access_profile.get("common_resources"))
    if resource and common_resources and resource not in common_resources:
        deviations.append(f"resource {resource} is outside baseline access_profile.common_resources")

    user_agent = _first_related_value(related_logs, "user_agent")
    common_user_agents = _string_list(access_profile.get("common_user_agents"))
    if user_agent and common_user_agents and user_agent not in common_user_agents:
        deviations.append("user_agent is outside baseline access_profile.common_user_agents")

    api_calls = _numeric(evidence.get("api_calls_1m"))
    avg_api = _numeric(access_profile.get("avg_api_calls_per_minute"))
    if api_calls is not None and avg_api is not None and api_calls > max(avg_api * 2, avg_api + 5):
        deviations.append(f"api_calls_1m {api_calls:g} exceeds baseline access_profile.avg_api_calls_per_minute {avg_api:g}")

    failed_count = _numeric(evidence.get("failed_count_5m"))
    failed_baseline = _numeric(result_profile.get("failed_login_count_7d"))
    if failed_count is not None and failed_baseline is not None and failed_count > max(3, failed_baseline):
        deviations.append(f"failed_count_5m {failed_count:g} exceeds baseline result_profile.failed_login_count_7d {failed_baseline:g}")

    sensitive_count = _numeric(evidence.get("sensitive_count_5m"))
    sensitive_rate = _numeric(access_profile.get("sensitive_access_rate"))
    if sensitive_count is not None and sensitive_count > 0 and sensitive_rate is not None and sensitive_rate < 0.1:
        deviations.append(f"sensitive access count {sensitive_count:g} is unusual for baseline access_profile.sensitive_access_rate {sensitive_rate:g}")

    return deviations


def _build_risk_reason(
    alert: dict[str, Any],
    rule_hits: list[str],
    baseline_deviations: list[str],
    related_logs: list[dict[str, Any]],
    *,
    has_baseline: bool,
) -> str:
    risk_level = alert.get("risk_level") or "unknown"
    risk_score = alert.get("risk_score")
    rule_text = "、".join(rule_hits) if rule_hits else "no rule hits"
    pieces = [f"Risk level {risk_level}", f"score {risk_score}", f"rule evidence: {rule_text}"]
    if baseline_deviations:
        pieces.append(f"baseline deviations: {'; '.join(baseline_deviations)}")
    elif has_baseline:
        pieces.append("no baseline deviation was derived from the available evidence")
    else:
        pieces.append("baseline is missing, so the explanation relies on rule evidence only")
    pieces.append(f"related logs: {len(related_logs)}")
    return "; ".join(pieces)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item is not None]
    return []


def _first_string(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value):
            return str(value)
    return None


def _first_related_value(items: list[dict[str, Any]], field: str) -> str | None:
    for item in items:
        value = item.get(field)
        if value is not None and str(value):
            return str(value)
    return None


def _event_hour(value: Any) -> int | None:
    if isinstance(value, datetime):
        return value.hour
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).hour
        except ValueError:
            return None
    return None


def _hour_in_ranges(hour: int, ranges: list[str]) -> bool:
    parsed_ranges = [_parse_hour_range(value) for value in ranges]
    parsed_ranges = [value for value in parsed_ranges if value is not None]
    if not parsed_ranges:
        return True

    for start, end in parsed_ranges:
        if start <= end and start <= hour < end:
            return True
        if start > end and (hour >= start or hour < end):
            return True
    return False


def _parse_hour_range(value: str) -> tuple[int, int] | None:
    try:
        start, end = value.split("-", 1)
        return int(start.split(":", 1)[0]), int(end.split(":", 1)[0])
    except (ValueError, IndexError):
        return None


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


# -- accuracy test endpoint ----------------------------------------------------


@app.post(
    "/api/v1/test/accuracy",
    responses=STANDARD_ERROR_RESPONSES,
    tags=["test"],
    summary="Run UEBA accuracy test",
    description="Generate deterministic logs, run anomaly detection, and evaluate UEBA baseline scoring accuracy.",
)
def run_accuracy_test_endpoint(
    seed: int = Query(default=42, description="Random seed for reproducible generation"),
    days: int = Query(default=3, ge=1, le=10, description="Days of logs to generate"),
    count: int = Query(default=100, ge=50, le=500, description="Normal logins per day"),
) -> dict[str, Any]:
    try:
        from tests.accuracy.run_test import run_accuracy_test as _run_test

        return _run_test(
            seed=seed,
            days=days,
            count=count,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "accuracy_test_failed",
                "message": f"Accuracy test failed: {exc}",
                "details": {},
            },
        ) from exc
