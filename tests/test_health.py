from types import SimpleNamespace

from src.api.app import app, health_check
from src.health import get_cli_health_payload, get_health_status


def test_health_response_contract(monkeypatch) -> None:
    monkeypatch.setattr("src.health.settings", SimpleNamespace(dashscope_api_key=""))
    monkeypatch.setattr("src.health._check_kafka", lambda: True)
    monkeypatch.setattr("src.health._check_flink", lambda: True)
    monkeypatch.setattr(
        "src.health._check_elasticsearch",
        lambda: (True, "2026-05-13T10:00:00Z"),
    )
    monkeypatch.setattr(
        "src.health._get_consumer_lag",
        lambda: {"flink-raw-to-parsed": 0, "log-ai-consume-to-es": 0},
    )

    status = get_health_status()

    assert status.model_dump(mode="json") == {
        "kafka": True,
        "flink": True,
        "elasticsearch": True,
        "dashscope_configured": False,
        "latest_log_ingest_time": "2026-05-13T10:00:00Z",
        "consumer_lag": {
            "flink-raw-to-parsed": 0,
            "log-ai-consume-to-es": 0,
        },
    }


def test_health_api_contract_binding(monkeypatch) -> None:
    monkeypatch.setattr("src.health.settings", SimpleNamespace(dashscope_api_key=""))
    monkeypatch.setattr("src.health._check_kafka", lambda: True)
    monkeypatch.setattr("src.health._check_flink", lambda: False)
    monkeypatch.setattr(
        "src.health._check_elasticsearch",
        lambda: (True, "2026-05-13T10:00:00Z"),
    )
    monkeypatch.setattr(
        "src.health._get_consumer_lag",
        lambda: {"flink-raw-to-parsed": 3, "log-ai-consume-to-es": 1},
    )

    paths = {route.path for route in app.routes}
    response = health_check()

    assert "/api/v1/health" in paths
    assert response.model_dump(mode="json") == {
        "kafka": True,
        "flink": False,
        "elasticsearch": True,
        "dashscope_configured": False,
        "latest_log_ingest_time": "2026-05-13T10:00:00Z",
        "consumer_lag": {
            "flink-raw-to-parsed": 3,
            "log-ai-consume-to-es": 1,
        },
    }


def test_cli_health_preserves_legacy_shape(monkeypatch) -> None:
    monkeypatch.setattr("src.health.settings", SimpleNamespace(dashscope_api_key="test-key"))
    monkeypatch.setattr("src.health._check_kafka", lambda: False)
    monkeypatch.setattr("src.health._check_flink", lambda: True)
    monkeypatch.setattr("src.health._check_elasticsearch", lambda: (False, None))

    assert get_cli_health_payload() == {
        "kafka": False,
        "elasticsearch": False,
        "flink": True,
        "dashscope_configured": True,
        "last_data_update": "N/A",
    }
