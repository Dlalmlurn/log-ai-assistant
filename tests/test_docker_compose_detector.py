from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_YML = PROJECT_ROOT / "docker-compose.yml"


def test_anomaly_detector_service_is_profile_gated() -> None:
    config = COMPOSE_YML.read_text(encoding="utf-8")

    assert "anomaly-detector:" in config
    assert 'profiles: ["detector"]' in config
    assert "detect-worker" in config
    assert "--interval-seconds" in config
