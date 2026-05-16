import json

from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.app import app, http_exception_handler
from src.schemas import (
    AIReportListResponse,
    AlertEventListResponse,
    DailyReportListResponse,
    ErrorResponse,
    ListResponse,
    NormalizedLogListResponse,
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
        AlertEventListResponse,
        UserBaselineListResponse,
        AIReportListResponse,
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
