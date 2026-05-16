from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.health import HealthResponse, get_health_status
from src.schemas import ErrorResponse


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
