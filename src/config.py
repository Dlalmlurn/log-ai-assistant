from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    kafka_bootstrap_servers: list[str]
    kafka_raw_topic: str
    kafka_parsed_topic: str
    kafka_alert_topic: str
    kafka_ai_topic: str
    kafka_metrics_topic: str

    elasticsearch_url: str
    elasticsearch_log_index: str
    elasticsearch_alert_index: str
    elasticsearch_ai_index: str
    elasticsearch_daily_index: str
    elasticsearch_baseline_index: str

    flink_dashboard_url: str

    dashscope_api_key: str
    dashscope_model: str

    generator_script: Path
    generator_jsonl: Path
    generator_syslog: Path

    threshold_ip_fail_5m: int
    threshold_user_fail_5m: int
    threshold_api_call_1m: int
    threshold_sensitive_5m: int
    threshold_multi_user_fail_ip_5m: int

    work_hour_start: int
    work_hour_end: int


settings = Settings(
    kafka_bootstrap_servers=_get_csv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
    kafka_raw_topic=os.getenv("KAFKA_RAW_TOPIC", "raw_logs"),
    kafka_parsed_topic=os.getenv("KAFKA_PARSED_TOPIC", "parsed_logs"),
    kafka_alert_topic=os.getenv("KAFKA_ALERT_TOPIC", "alert_events"),
    kafka_ai_topic=os.getenv("KAFKA_AI_TOPIC", "ai_reports"),
    kafka_metrics_topic=os.getenv("KAFKA_METRICS_TOPIC", "system_metrics"),
    elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
    elasticsearch_log_index=os.getenv("ELASTICSEARCH_LOG_INDEX", "security-logs"),
    elasticsearch_alert_index=os.getenv("ELASTICSEARCH_ALERT_INDEX", "security-alerts"),
    elasticsearch_ai_index=os.getenv("ELASTICSEARCH_AI_INDEX", "ai-reports"),
    elasticsearch_daily_index=os.getenv("ELASTICSEARCH_DAILY_INDEX", "daily-reports"),
    elasticsearch_baseline_index=os.getenv("ELASTICSEARCH_BASELINE_INDEX", "user-baselines"),
    flink_dashboard_url=os.getenv("FLINK_DASHBOARD_URL", "http://localhost:8081"),
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
    dashscope_model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
    generator_script=(PROJECT_ROOT / os.getenv("GENERATOR_SCRIPT", "log-generator/gen_vpn_logs.py")).resolve(),
    generator_jsonl=(PROJECT_ROOT / os.getenv("GENERATOR_JSONL", "log-generator/vpn_output/vpn_logs.jsonl")).resolve(),
    generator_syslog=(PROJECT_ROOT / os.getenv("GENERATOR_SYSLOG", "log-generator/vpn_output/vpn_logs.log")).resolve(),
    threshold_ip_fail_5m=_get_int("THRESHOLD_IP_FAIL_5M", 8),
    threshold_user_fail_5m=_get_int("THRESHOLD_USER_FAIL_5M", 5),
    threshold_api_call_1m=_get_int("THRESHOLD_API_CALL_1M", 80),
    threshold_sensitive_5m=_get_int("THRESHOLD_SENSITIVE_5M", 5),
    threshold_multi_user_fail_ip_5m=_get_int("THRESHOLD_MULTI_USER_FAIL_IP_5M", 4),
    work_hour_start=_get_int("WORK_HOUR_START", 9),
    work_hour_end=_get_int("WORK_HOUR_END", 18),
)
