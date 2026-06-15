from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_YML = PROJECT_ROOT / "docker-compose.yml"


def test_anomaly_detector_service_runs_on_default_compose_path() -> None:
    config = COMPOSE_YML.read_text(encoding="utf-8")

    assert "anomaly-detector:" in config
    detector_section = config.split("  anomaly-detector:", 1)[1].split("\n  raw-to-parsed:", 1)[0]
    assert "profiles:" not in detector_section
    assert "detect-worker" in config
    assert "--interval-seconds" in config
    assert "${ANOMALY_DETECTOR_INTERVAL_SECONDS:-1}" in detector_section
    assert "${ANOMALY_DETECTOR_BATCH_SIZE:-2000}" in detector_section


def test_flink_runtime_is_part_of_default_compose_path() -> None:
    config = COMPOSE_YML.read_text(encoding="utf-8")

    flink_jobmanager_section = config.split("  flink-jobmanager:", 1)[1].split("\n  flink-taskmanager:", 1)[0]
    flink_taskmanager_section = config.split("  flink-taskmanager:", 1)[1].split("\n  filebeat:", 1)[0]
    flink_submit_section = config.split("  flink-submit:", 1)[1].split("\n  tester:", 1)[0]

    assert "profiles:" not in flink_jobmanager_section
    assert "profiles:" not in flink_taskmanager_section
    assert "profiles:" not in flink_submit_section

    backend_section = config.split("  backend:", 1)[1].split("\n  anomaly-detector:", 1)[0]
    assert "flink-jobmanager:\n        condition: service_healthy" in backend_section


def test_raw_to_parsed_is_fallback_only() -> None:
    config = COMPOSE_YML.read_text(encoding="utf-8")

    raw_to_parsed_section = config.split("  raw-to-parsed:", 1)[1].split("\n  frontend:", 1)[0]
    assert 'profiles: ["fallback"]' in raw_to_parsed_section


def test_scale_generator_defaults_to_1500_rows_per_minute() -> None:
    config = COMPOSE_YML.read_text(encoding="utf-8")

    default_generator_section = config.split("  log-generator:", 1)[1].split("\n  log-generator-scale:", 1)[0]
    scale_generator_section = config.split("  log-generator-scale:", 1)[1].split("\n  flink-submit:", 1)[0]

    assert "LOG_GENERATOR_INTERVAL_SECONDS: ${LOG_GENERATOR_INTERVAL_SECONDS:-5}" in default_generator_section
    assert "LOG_GENERATOR_BATCH_SIZE: ${LOG_GENERATOR_BATCH_SIZE:-3}" in default_generator_section
    assert "LOG_GENERATOR_INTERVAL_SECONDS: ${LOG_GENERATOR_SCALE_INTERVAL_SECONDS:-1}" in scale_generator_section
    assert "LOG_GENERATOR_BATCH_SIZE: ${LOG_GENERATOR_SCALE_BATCH_SIZE:-25}" in scale_generator_section
