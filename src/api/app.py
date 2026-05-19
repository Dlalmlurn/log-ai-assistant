from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.ai_engine import AIAnalyzer
from src.config import settings
from src.health import HealthResponse, get_health_status
from src.schemas import (
    AIReport,
    AlertDetailResponse,
    BaselineRebuildResponse,
    ErrorResponse,
    EvidenceChain,
    AlertEvent,
    AlertEventListResponse,
    NormalizedLog,
    NormalizedLogListResponse,
    RiskLevel,
    SourceType,
    UserBaseline,
    UserBaselineListResponse,
)
from src.storage import ElasticStorage
from src.ueba import build_and_store_baselines


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
    description="FastAPI layer for the formal Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React path.",
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["system"],
    summary="System health status",
    description="REQ-001, REQ-002, REQ-007: report Kafka, Flink, Elasticsearch, DashScope config, latest log ingest time, and consumer lag.",
)
def health_check() -> HealthResponse:
    return get_health_status()

# 给API接口创建并准备ElasticStorage访问对象的函数
def get_storage() -> ElasticStorage:
    return ElasticStorage()


def get_analyzer() -> AIAnalyzer:
    return AIAnalyzer()


@app.get(
    "/api/v1/logs",
    response_model=NormalizedLogListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["logs"],
    summary="Query structured security logs",
    description="REQ-002, REQ-006: query normalized logs from Elasticsearch security-logs for the React realtime log view.",
)
def list_logs(
    source_type: SourceType | None = Query(default=None),
    username: str | None = Query(default=None),
    src_ip: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ElasticStorage = Depends(get_storage),
) -> NormalizedLogListResponse:
# 构建 ES 查询
    query = _build_logs_query(
        source_type=source_type,
        username=username,
        src_ip=src_ip,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    try:
        items, total = storage.search_page(
            index=settings.elasticsearch_log_index,
            query=query,
            limit=limit,
            offset=offset,
            sort=[{"event_time": "desc"}],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query structured logs from Elasticsearch",
                "details": {"index": settings.elasticsearch_log_index},
            },
        ) from exc
# limit：返回日志上限。offset：从第n条日志开始查
    return NormalizedLogListResponse(
        items=_strip_elasticsearch_metadata(items),
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
    description="REQ-002, REQ-006: fetch one normalized log by event_id from Elasticsearch security-logs.",
)
def get_log_detail(
    event_id: str,
    storage: ElasticStorage = Depends(get_storage),
) -> NormalizedLog:
    try:
        items, _total = storage.search_page(
            index=settings.elasticsearch_log_index,
            query={"term": {"event_id": event_id}},
            limit=1,
            offset=0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query structured log detail from Elasticsearch",
                "details": {"index": settings.elasticsearch_log_index, "event_id": event_id},
            },
        ) from exc

    if not items:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "log_not_found",
                "message": "Structured log not found",
                "details": {"index": settings.elasticsearch_log_index, "event_id": event_id},
            },
        )

    return NormalizedLog(**_strip_elasticsearch_metadata(items)[0])


@app.get(
    "/api/v1/alerts",
    response_model=AlertEventListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["alerts"],
    summary="Query security alerts",
    description="REQ-004, REQ-006, REQ-008: query alert events from Elasticsearch security-alerts for the React abnormal event view.",
)
def list_alerts(
    risk_level: RiskLevel | None = Query(default=None),
    username: str | None = Query(default=None),
    rule: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ElasticStorage = Depends(get_storage),
) -> AlertEventListResponse:
    query = _build_alerts_query(
        risk_level=risk_level,
        username=username,
        rule=rule,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    try:
        items, total = storage.search_page(
            index=settings.elasticsearch_alert_index,
            query=query,
            limit=limit,
            offset=offset,
            sort=[{"detect_time": "desc"}],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query security alerts from Elasticsearch",
                "details": {"index": settings.elasticsearch_alert_index},
            },
        ) from exc

    return AlertEventListResponse(
        items=_strip_elasticsearch_metadata(items),
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get(
    "/api/v1/alerts/{alert_id}",
    response_model=AlertDetailResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["alerts"],
    summary="Get alert detail with evidence chain",
    description="REQ-004, REQ-006: fetch alert, user baseline, related logs, AI report, and evidence chain from Elasticsearch.",
)
def get_alert_detail(
    alert_id: str,
    storage: ElasticStorage = Depends(get_storage),
) -> AlertDetailResponse:
    try:
        alert_items, _total = storage.search_page(
            index=settings.elasticsearch_alert_index,
            query={"term": {"alert_id": alert_id}},
            limit=1,
            offset=0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query alert detail from Elasticsearch",
                "details": {"index": settings.elasticsearch_alert_index, "alert_id": alert_id},
            },
        ) from exc

    if not alert_items:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "alert_not_found",
                "message": "Alert not found",
                "details": {"index": settings.elasticsearch_alert_index, "alert_id": alert_id},
            },
        )

    alert = _strip_elasticsearch_metadata(alert_items)[0]
    try:
        baseline = _fetch_alert_baseline(storage, alert)
        related_logs = _fetch_related_logs(storage, alert)
        ai_report = _fetch_ai_report(storage, alert)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to assemble alert evidence from Elasticsearch",
                "details": {"alert_id": alert_id},
            },
        ) from exc

    return AlertDetailResponse(
        alert=alert,
        baseline=baseline,
        related_logs=related_logs,
        ai_report=ai_report,
        evidence_chain=_build_evidence_chain(alert, baseline, related_logs),
    )


@app.post(
    "/api/v1/alerts/{alerty_id}/analze",
    response_model=AIReport,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["alerts"],
    summary="Analyze an alert with AI",
    description="REQ-004: analyze an existing alert with alert, baseline, related_logs, and window_stats context, then store the AI report in Elasticsearch ai-reports.",
)
def analyze_alert(
    alert_id: str,
    storage: ElasticStorage = Depends(get_storage),
    analyzer: AIAnalyzer = Depends(get_analyzer),
) -> AIReport:
    try:
        alert_items, _total = storage.search_page(
            index=settings.elasticsearch_alert_index,
            query={"term": {"alert_id": alert_id}},
            limit=1,
            offset=0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query alert for AI analysis",
                "details": {"index": settings.elasticsearch_alert_index, "alert_id": alert_id},
            },
        ) from exc

    if not alert_items:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "alert_not_found",
                "message": "Alert not found",
                "details": {"index": settings.elasticsearch_alert_index, "alert_id": alert_id},
            },
        )

    alert = _strip_elasticsearch_metadata(alert_items)[0]
    try:
        baseline = _fetch_alert_baseline(storage, alert)
        related_logs = _fetch_related_logs(storage, alert)
        report = analyzer.analyze(
            alert=AlertEvent.model_validate(alert),
            baseline=baseline,
            related_logs=related_logs,
            window_stats={},
        )
        report_doc = report.model_dump(mode="json")
        storage.index_document(settings.elasticsearch_ai_index, report_doc, doc_id=report.ai_report_id)
        storage.update_document(
            settings.elasticsearch_alert_index,
            alert_id,
            {"llm_analysis_id": report.ai_report_id, "status": "analyzed"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "alert_analysis_failed",
                "message": "Failed to analyze alert and store AI report",
                "details": {
                    "alert_id": alert_id,
                    "ai_index": settings.elasticsearch_ai_index,
                    "alert_index": settings.elasticsearch_alert_index,
                },
            },
        ) from exc

    return report


@app.get(
    "/api/v1/baselines",
    response_model=UserBaselineListResponse,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["baselines"],
    summary="Query user behavior baselines",
    description="REQ-003, REQ-006: query user behavior baselines from Elasticsearch user-baselines for the React baseline view.",
)
def list_baselines(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    storage: ElasticStorage = Depends(get_storage),
) -> UserBaselineListResponse:
    try:
        items, total = storage.search_page(
            index=settings.elasticsearch_baseline_index,
            query={"match_all": {}},
            limit=limit,
            offset=offset,
            sort=[{"updated_at": "desc"}],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query user baselines from Elasticsearch",
                "details": {"index": settings.elasticsearch_baseline_index},
            },
        ) from exc

    return UserBaselineListResponse(
        items=_strip_elasticsearch_metadata(items),
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
    description="REQ-003: rebuild user behavior baselines from Elasticsearch security-logs and store them in user-baselines.",
)
def rebuild_baselines(
    storage: ElasticStorage = Depends(get_storage),
) -> BaselineRebuildResponse:
    try:
        storage.ensure_indices()
        baselines = build_and_store_baselines(storage)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "baseline_rebuild_failed",
                "message": "Failed to rebuild user baselines",
                "details": {
                    "source_index": settings.elasticsearch_log_index,
                    "target_index": settings.elasticsearch_baseline_index,
                },
            },
        ) from exc

    return BaselineRebuildResponse(rebuilt_count=len(baselines))


@app.get(
    "/api/v1/baselines/{username}",
    response_model=UserBaseline,
    responses=STANDARD_ERROR_RESPONSES,
    tags=["baselines"],
    summary="Get user behavior baseline detail",
    description="REQ-003, REQ-006: fetch one user behavior baseline from Elasticsearch user-baselines.",
)
def get_baseline_detail(
    username: str,
    storage: ElasticStorage = Depends(get_storage),
) -> UserBaseline:
    try:
        items, _total = storage.search_page(
            index=settings.elasticsearch_baseline_index,
            query={"term": {"username": username}},
            limit=1,
            offset=0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "elasticsearch_query_failed",
                "message": "Failed to query user baseline from Elasticsearch",
                "details": {"index": settings.elasticsearch_baseline_index, "username": username},
            },
        ) from exc

    if not items:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "baseline_not_found",
                "message": "User baseline not found",
                "details": {"index": settings.elasticsearch_baseline_index, "username": username},
            },
        )

    return UserBaseline(**_strip_elasticsearch_metadata(items)[0])


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


def _build_logs_query(
    *,
    source_type: SourceType | None = None,
    username: str | None = None,
    src_ip: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    # 默认查询最近 24 小时的内容而不是全量扫描
    resolved_end_time = end_time or datetime.now(timezone.utc)
    resolved_start_time = start_time or resolved_end_time - timedelta(hours=24)
    # ES 的 bool.filter，必须满足所有条件，单纯筛选而非进行相关度评分
    filters: list[dict[str, Any]] = [
        {
            "range": {
                "event_time": {
                    "gte": resolved_start_time.isoformat(),
                    "lte": resolved_end_time.isoformat(),
                }
            }
        }
    ]
    # 添加可选筛选条件，比如输入：username:"Alice"，会以es的json格式追加一个term条件：用户名为Alice（精确匹配的筛选条件）
    for field, value in (
        ("source_type", source_type),
        ("username", username),
        ("src_ip", src_ip),
        ("status", status),
    ):
        if value is not None:
            filters.append({"term": {field: value}})

    return {"bool": {"filter": filters}}


def _build_alerts_query(
    *,
    risk_level: RiskLevel | None = None,
    username: str | None = None,
    rule: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if start_time or end_time:
        range_filter: dict[str, str] = {}
        if start_time:
            range_filter["gte"] = start_time.isoformat()
        if end_time:
            range_filter["lte"] = end_time.isoformat()
        filters.append({"range": {"detect_time": range_filter}})

    for field, value in (
        ("risk_level", risk_level),
        ("username", username),
        ("status", status),
    ):
        if value is not None:
            filters.append({"term": {field: value}})

    if rule and rule.strip():
        escaped_rule = _escape_elasticsearch_wildcard_value(rule.strip())
        filters.append(
            {
                "wildcard": {
                    "rule_hits": {"value": f"*{escaped_rule}*"}
                }
            }
        )

    if not filters:
        return {"match_all": {}}
    return {"bool": {"filter": filters}}


def _escape_elasticsearch_wildcard_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _strip_elasticsearch_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "_id"} for item in items]


def _fetch_alert_baseline(storage: ElasticStorage, alert: dict[str, Any]) -> dict[str, Any]:
    username = alert.get("username")
    if not username:
        return {}

    items, _total = storage.search_page(
        index=settings.elasticsearch_baseline_index,
        query={"term": {"username": username}},
        limit=1,
        offset=0,
    )
    return _strip_elasticsearch_metadata(items)[0] if items else {}


def _fetch_related_logs(storage: ElasticStorage, alert: dict[str, Any]) -> list[dict[str, Any]]:
    related_event_ids = _string_list(alert.get("related_event_ids"))
    if not related_event_ids:
        return []

    items, _total = storage.search_page(
        index=settings.elasticsearch_log_index,
        query={"terms": {"event_id": related_event_ids}},
        limit=len(related_event_ids),
        offset=0,
        sort=[{"event_time": "asc"}],
    )
    logs = _strip_elasticsearch_metadata(items)
    order = {event_id: index for index, event_id in enumerate(related_event_ids)}
    return sorted(logs, key=lambda item: order.get(str(item.get("event_id")), len(order)))


def _fetch_ai_report(storage: ElasticStorage, alert: dict[str, Any]) -> dict[str, Any]:
    llm_analysis_id = alert.get("llm_analysis_id")
    if llm_analysis_id:
        items, _total = storage.search_page(
            index=settings.elasticsearch_ai_index,
            query={"term": {"ai_report_id": llm_analysis_id}},
            limit=1,
            offset=0,
            sort=[{"created_at": "desc"}],
        )
        if items:
            return _strip_elasticsearch_metadata(items)[0]

    alert_id = alert.get("alert_id")
    if not alert_id:
        return {}

    items, _total = storage.search_page(
        index=settings.elasticsearch_ai_index,
        query={"term": {"alert_id": alert_id}},
        limit=1,
        offset=0,
        sort=[{"created_at": "desc"}],
    )
    return _strip_elasticsearch_metadata(items)[0] if items else {}


def _build_evidence_chain(alert: dict[str, Any], baseline: dict[str, Any], related_logs: list[dict[str, Any]]) -> EvidenceChain:
    rule_hits = _string_list(alert.get("rule_hits"))
    baseline_deviations = _extract_baseline_deviations(alert, baseline, related_logs)
    risk_reason = _build_risk_reason(alert, rule_hits, baseline_deviations, related_logs, has_baseline=bool(baseline))
    return EvidenceChain(
        rule_hits=rule_hits,
        baseline_deviations=baseline_deviations,
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
    common_ips = _string_list(baseline.get("common_ips"))
    if src_ip and common_ips and src_ip not in common_ips:
        deviations.append(f"src_ip {src_ip} is outside baseline common_ips")

    event_hour = _event_hour(alert.get("event_time"))
    active_hours = _string_list(baseline.get("active_hours"))
    if event_hour is not None and active_hours and not _hour_in_ranges(event_hour, active_hours):
        deviations.append(f"event hour {event_hour:02d}:00 is outside baseline active_hours")

    resource = _first_string(evidence.get("resource"), _first_related_value(related_logs, "resource"))
    common_resources = _string_list(baseline.get("common_resources"))
    if resource and common_resources and resource not in common_resources:
        deviations.append(f"resource {resource} is outside baseline common_resources")

    user_agent = _first_related_value(related_logs, "user_agent")
    common_user_agents = _string_list(baseline.get("common_user_agents"))
    if user_agent and common_user_agents and user_agent not in common_user_agents:
        deviations.append("user_agent is outside baseline common_user_agents")

    api_calls = _numeric(evidence.get("api_calls_1m"))
    avg_api = _numeric(baseline.get("avg_api_calls_per_minute"))
    if api_calls is not None and avg_api is not None and api_calls > max(avg_api * 2, avg_api + 5):
        deviations.append(f"api_calls_1m {api_calls:g} exceeds baseline avg_api_calls_per_minute {avg_api:g}")

    failed_count = _numeric(evidence.get("failed_count_5m"))
    failed_baseline = _numeric(baseline.get("failed_login_count_7d"))
    if failed_count is not None and failed_baseline is not None and failed_count > max(3, failed_baseline):
        deviations.append(f"failed_count_5m {failed_count:g} exceeds baseline failed_login_count_7d {failed_baseline:g}")

    sensitive_count = _numeric(evidence.get("sensitive_count_5m"))
    sensitive_rate = _numeric(baseline.get("sensitive_access_rate"))
    if sensitive_count is not None and sensitive_count > 0 and sensitive_rate is not None and sensitive_rate < 0.1:
        deviations.append(f"sensitive access count {sensitive_count:g} is unusual for baseline sensitive_access_rate {sensitive_rate:g}")

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
