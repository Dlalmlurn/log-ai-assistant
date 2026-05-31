from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SQL = PROJECT_ROOT / "sql" / "clickhouse" / "01_init.sql"


def test_clickhouse_init_sql_defines_remaining_p0_tables() -> None:
    sql = INIT_SQL.read_text(encoding="utf-8")

    for table_name in (
        "user_seen_sources",
        "daily_security_reports",
        "data_quality_metrics",
        "system_metrics",
    ):
        assert f"CREATE TABLE IF NOT EXISTS log_ai.{table_name}" in sql

    assert "ReplacingMergeTree(updated_at)" in sql
    assert "ReplacingMergeTree(created_at)" in sql
    assert "security_logs_count UInt64 DEFAULT 0" in sql
    assert "labels String DEFAULT '{}'" in sql


def test_clickhouse_init_sql_wires_parsed_logs_kafka_sink() -> None:
    sql = INIT_SQL.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS log_ai.parsed_logs_kafka_queue" in sql
    assert "ENGINE = Kafka" in sql
    assert "kafka_broker_list = 'kafka:9092'" in sql
    assert "kafka_topic_list = 'parsed_logs'" in sql
    assert "kafka_group_name = 'clickhouse-parsed-logs'" in sql
    assert "kafka_format = 'JSONAsString'" in sql
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS log_ai.parsed_logs_to_security_logs" in sql
    assert "TO log_ai.security_logs" in sql
    assert "FROM log_ai.parsed_logs_kafka_queue" in sql
    assert "JSONExtractString(raw, 'event_id')" in sql
    assert "JSONExtract(raw, 'risk_tags', 'Array(String)')" in sql
    assert "ENGINE = ReplacingMergeTree(ingest_time)" in sql
    assert "ORDER BY (tenant_id, event_id, event_date, user_id, src_ip, source_type, event_time)" in sql
