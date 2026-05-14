from __future__ import annotations

from fastapi import FastAPI

from src.health import HealthResponse, get_health_status


app = FastAPI(
    title="Log AI Assistant API",
    version="0.1.0",
    description="FastAPI layer for the formal Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React path.",
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="System health status",
    description="REQ-001, REQ-002, REQ-007: report Kafka, Flink, Elasticsearch, DashScope config, latest log ingest time, and consumer lag.",
)
def health_check() -> HealthResponse:
    return get_health_status()
