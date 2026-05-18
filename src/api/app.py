from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import settings
from src.health import HealthResponse, get_health_status
from src.schemas import ErrorResponse, NormalizedLogListResponse, SourceType
from src.storage import ElasticStorage


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


def _strip_elasticsearch_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "_id"} for item in items]
