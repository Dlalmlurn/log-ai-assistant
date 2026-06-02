from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from src.config import settings
from src.schemas import AIFeedback, AIJudgement, AnomalyEvent, DailyReport, DataQualityMetric, UserBaseline


LOG_COLUMNS: tuple[str, ...] = (
    "event_id",
    "event_time",
    "ingest_time",
    "tenant_id",
    "source_type",
    "log_type",
    "user_id",
    "account_type",
    "user_role",
    "department",
    "host",
    "src_ip",
    "src_port",
    "dst_ip",
    "dst_port",
    "geo",
    "action",
    "object_type",
    "object_id",
    "resource",
    "result",
    "severity",
    "user_agent",
    "protocol",
    "auth_method",
    "session_id",
    "trace_id",
    "scenario_id",
    "scenario_type",
    "attack_chain_id",
    "step_index",
    "injected_label",
    "message",
    "raw_log",
    "risk_tags",
    "attrs",
)
LOG_JSON_FIELDS = {"geo", "attrs"}
LOG_FILTERS = {
    "tenant_id",
    "source_type",
    "log_type",
    "user_id",
    "src_ip",
    "action",
    "result",
}

ANOMALY_COLUMNS: tuple[str, ...] = (
    "event_id",
    "event_time",
    "detect_time",
    "tenant_id",
    "user_id",
    "src_ip",
    "host",
    "source_type",
    "action",
    "object_type",
    "object_id",
    "attack_type",
    "risk_score",
    "risk_level",
    "risk_components",
    "rule_hits",
    "baseline_deviations",
    "reason_codes",
    "evidence",
    "related_event_ids",
    "scenario_id",
    "scenario_type",
    "attack_chain_id",
    "ai_status",
    "status",
    "model_version",
    "created_at",
)
ANOMALY_JSON_FIELDS = {"risk_components", "baseline_deviations", "evidence"}

BASELINE_COLUMNS: tuple[str, ...] = (
    "baseline_date",
    "tenant_id",
    "user_id",
    "profile_group",
    "feature_name",
    "mean_value",
    "std_value",
    "p50_value",
    "p95_value",
    "p99_value",
    "common_values",
    "value_histogram",
    "sample_days",
    "sample_count",
    "baseline_confidence",
    "trained_from",
    "trained_to",
    "fallback_level",
    "model_version",
    "created_at",
)

DAILY_REPORT_COLUMNS: tuple[str, ...] = (
    "report_date",
    "tenant_id",
    "total_logs",
    "anomaly_count",
    "high_count",
    "critical_count",
    "overall_score",
    "top_risk_users",
    "top_attack_types",
    "key_events",
    "ai_summary",
    "recommended_actions",
    "markdown_body",
    "created_at",
)

AI_JUDGEMENT_COLUMNS: tuple[str, ...] = (
    "judgement_id",
    "event_id",
    "created_at",
    "model_name",
    "model_version",
    "risk_level",
    "attack_type",
    "judgement",
    "key_reasons",
    "recommended_actions",
    "confidence",
    "feedback_suggestions",
    "raw_response",
    "is_mock",
)

AI_FEEDBACK_COLUMNS: tuple[str, ...] = (
    "feedback_id",
    "event_id",
    "judgement_id",
    "tenant_id",
    "user_id",
    "feedback_type",
    "suggestion",
    "target_component",
    "confidence",
    "review_status",
    "created_at",
)

DATA_QUALITY_COLUMNS: tuple[str, ...] = (
    "metric_date",
    "tenant_id",
    "source_type",
    "generated_count",
    "injected_anomaly_count",
    "injected_high_risk_count",
    "raw_logs_count",
    "parsed_logs_count",
    "clickhouse_insert_count",
    "security_logs_count",
    "raw_size_bytes",
    "table_size_bytes",
    "compression_ratio",
    "missing_event_time_rate",
    "missing_user_id_rate",
    "missing_src_ip_rate",
    "missing_action_rate",
    "missing_result_rate",
    "parse_error_rate",
    "created_at",
)

AI_JUDGEMENT_JSON_FIELDS = {"feedback_suggestions", "raw_response"}
DAILY_REPORT_JSON_FIELDS = set()

ALLOWED_AGGREGATE_GROUPS = {
    "tenant_id",
    "source_type",
    "log_type",
    "user_id",
    "src_ip",
    "action",
    "result",
    "event_date",
}
ALLOWED_AGGREGATE_METRICS = {
    "count": "count() AS count",
    "unique_users": "uniqExact(user_id) AS unique_users",
    "unique_src_ips": "uniqExact(src_ip) AS unique_src_ips",
    "avg_severity": "avg(severity) AS avg_severity",
    "max_severity": "max(severity) AS max_severity",
}


class ClickHouseStorage:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
        client: Any | None = None,
    ):
        if client is not None:
            self.client = client
            return

        import clickhouse_connect

        self.client = clickhouse_connect.get_client(
            host=host or settings.clickhouse_host,
            port=port or settings.clickhouse_http_port,
            database=database or settings.clickhouse_database,
            username=username or settings.clickhouse_user,
            password=settings.clickhouse_password if password is None else password,
        )

    def health(self) -> bool:
        try:
            result = self.client.query("SELECT 1").result_rows
            return bool(result and result[0][0] == 1)
        except Exception:
            return False

    def latest_security_log_ingest_time(self) -> str | None:
        try:
            result = self.client.query("SELECT count(), max(ingest_time) FROM security_logs").result_rows
        except Exception:
            return None
        if not result or not result[0][0] or result[0][1] is None:
            return None
        return str(result[0][1])

    def query(self, sql: str, parameters: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        return list(self.client.query(sql, parameters=parameters or {}).result_rows)

    def list_logs(
        self,
        *,
        tenant_id: str | None = None,
        source_type: str | None = None,
        log_type: str | None = None,
        user_id: str | None = None,
        src_ip: str | None = None,
        action: str | None = None,
        result: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_log_filters(
            tenant_id=tenant_id,
            source_type=source_type,
            log_type=log_type,
            user_id=user_id,
            src_ip=src_ip,
            action=action,
            result=result,
            start_time=start_time,
            end_time=end_time,
        )
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)

        items = self._select_dicts(
            f"""
            SELECT {_columns_sql(LOG_COLUMNS)}
            FROM security_logs
            {where_sql}
            ORDER BY event_time DESC
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            """,
            parameters,
        )
        total = self._select_scalar(
            f"SELECT count() FROM security_logs {where_sql}",
            parameters,
            default=0,
        )
        return [_normalize_log_row(item) for item in items], int(total or 0)

    def get_log(self, event_id: str) -> dict[str, Any] | None:
        items = self._select_dicts(
            f"""
            SELECT {_columns_sql(LOG_COLUMNS)}
            FROM security_logs
            WHERE event_id = {{event_id:String}}
            ORDER BY event_time DESC
            LIMIT 1
            """,
            {"event_id": event_id},
        )
        return _normalize_log_row(items[0]) if items else None

    def list_logs_by_event_ids(self, event_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        items = self._select_dicts(
            f"""
            SELECT {_columns_sql(LOG_COLUMNS)}
            FROM security_logs
            WHERE event_id IN {{event_ids:Array(String)}}
            ORDER BY event_time ASC
            LIMIT {{limit:UInt64}}
            """,
            {"event_ids": list(event_ids), "limit": max(1, len(event_ids))},
        )
        order = {event_id: index for index, event_id in enumerate(event_ids)}
        logs = [_normalize_log_row(item) for item in items]
        return sorted(logs, key=lambda item: order.get(str(item.get("event_id")), len(order)))

    def aggregate_logs(
        self,
        *,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        filters: dict[str, Any] | None = None,
        group_by: Sequence[str] | None = None,
        metrics: Sequence[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        resolved_group_by = list(group_by or ["event_date"])
        resolved_metrics = list(metrics or ["count"])
        _assert_allowed_values(resolved_group_by, ALLOWED_AGGREGATE_GROUPS, "group_by")
        _assert_allowed_values(resolved_metrics, ALLOWED_AGGREGATE_METRICS.keys(), "metrics")

        field_filters, parameters = _build_log_filters(
            start_time=time_from,
            end_time=time_to,
            **{key: value for key, value in (filters or {}).items() if key in LOG_FILTERS},
        )
        ignored_filters = sorted(set(filters or {}) - LOG_FILTERS)
        if ignored_filters:
            raise ValueError(f"Unsupported log filters: {', '.join(ignored_filters)}")

        select_parts = [*resolved_group_by, *(ALLOWED_AGGREGATE_METRICS[item] for item in resolved_metrics)]
        parameters["limit"] = _normalize_limit(limit)
        group_sql = ", ".join(resolved_group_by)
        order_metric = resolved_metrics[0]
        return self._select_dicts(
            f"""
            SELECT {", ".join(select_parts)}
            FROM security_logs
            {_where(field_filters)}
            GROUP BY {group_sql}
            ORDER BY {order_metric} DESC
            LIMIT {{limit:UInt64}}
            """,
            parameters,
        )

    def list_anomalies(
        self,
        *,
        tenant_id: str | None = None,
        risk_level: str | None = None,
        user_id: str | None = None,
        src_ip: str | None = None,
        reason_code: str | None = None,
        ai_status: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_anomaly_filters(
            tenant_id=tenant_id,
            risk_level=risk_level,
            user_id=user_id,
            src_ip=src_ip,
            reason_code=reason_code,
            ai_status=ai_status,
            status=status,
            start_time=start_time,
            end_time=end_time,
        )
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)
        items = self._select_dicts(
            f"""
            SELECT {_columns_sql(ANOMALY_COLUMNS)}
            FROM anomaly_events
            {where_sql}
            ORDER BY event_time DESC, risk_score DESC
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            """,
            parameters,
        )
        total = self._select_scalar(
            f"SELECT count() FROM anomaly_events {where_sql}",
            parameters,
            default=0,
        )
        return [_normalize_anomaly_row(item) for item in items], int(total or 0)

    def get_anomaly(self, event_id: str) -> dict[str, Any] | None:
        items = self._select_dicts(
            f"""
            SELECT {_columns_sql(ANOMALY_COLUMNS)}
            FROM anomaly_events
            WHERE event_id = {{event_id:String}}
            ORDER BY detect_time DESC
            LIMIT 1
            """,
            {"event_id": event_id},
        )
        return _normalize_anomaly_row(items[0]) if items else None

    def insert_anomalies(self, anomalies: Sequence[AnomalyEvent | dict[str, Any]]) -> None:
        rows = [
            _row_from_payload(
                _model_payload(item),
                ANOMALY_COLUMNS,
                json_fields=ANOMALY_JSON_FIELDS,
                defaults={"model_version": "", "ai_status": "not_required", "status": "new"},
            )
            for item in anomalies
        ]
        if rows:
            self.client.insert("anomaly_events", rows, column_names=list(ANOMALY_COLUMNS))

    def update_anomaly_ai_status(self, event_id: str, ai_status: str) -> None:
        self.client.command(
            """
            ALTER TABLE anomaly_events
            UPDATE ai_status = {ai_status:String}
            WHERE event_id = {event_id:String}
            """,
            parameters={"event_id": event_id, "ai_status": ai_status},
        )

    def aggregate_anomalies(
        self,
        *,
        field: str,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        _assert_allowed_values([field], {"attack_type", "user_id", "risk_level", "status"}, "anomaly aggregate field")
        filters, parameters = _build_anomaly_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
        )
        parameters["limit"] = _normalize_limit(limit)
        return self._select_dicts(
            f"""
            SELECT {field} AS key, count() AS count
            FROM anomaly_events
            {_where(filters)}
            GROUP BY {field}
            ORDER BY count DESC
            LIMIT {{limit:UInt64}}
            """,
            parameters,
        )

    def list_user_risk_stats(
        self,
        *,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_anomaly_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
        )
        filters.append("user_id != ''")
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)
        rows = self._select_dicts(
            f"""
            SELECT
                user_id,
                count() AS anomaly_count,
                countIf(risk_level IN ('high', 'critical')) AS high_risk_count,
                countIf(risk_level = 'critical') AS critical_count,
                max(risk_score) AS max_risk_score,
                max(event_time) AS latest_event_time
            FROM anomaly_events
            {where_sql}
            GROUP BY user_id
            ORDER BY high_risk_count DESC, max_risk_score DESC, anomaly_count DESC, latest_event_time DESC
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            """,
            parameters,
        )
        total = self._select_scalar(
            f"""
            SELECT count()
            FROM (
                SELECT user_id
                FROM anomaly_events
                {where_sql}
                GROUP BY user_id
            )
            """,
            parameters,
            default=0,
        )
        return rows, int(total or 0)

    def list_user_baselines(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        baseline_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_baseline_filters(
            tenant_id=tenant_id,
            user_id=user_id,
            baseline_date=baseline_date,
        )
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)
        rows = self._select_dicts(
            f"""
            WITH baseline_keys AS (
                SELECT tenant_id, user_id, baseline_date, model_version, trained_from, trained_to
                FROM ueba_user_baseline
                {where_sql}
                GROUP BY tenant_id, user_id, baseline_date, model_version, trained_from, trained_to
                ORDER BY baseline_date DESC, user_id ASC
                LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            )
            SELECT {_columns_sql(BASELINE_COLUMNS, "b")}
            FROM ueba_user_baseline AS b
            INNER JOIN baseline_keys AS k
                USING (tenant_id, user_id, baseline_date, model_version, trained_from, trained_to)
            ORDER BY b.baseline_date DESC, b.user_id ASC, b.profile_group ASC, b.feature_name ASC
            """,
            parameters,
        )
        total = self._select_scalar(
            f"""
            SELECT count()
            FROM (
                SELECT tenant_id, user_id, baseline_date, model_version, trained_from, trained_to
                FROM ueba_user_baseline
                {where_sql}
                GROUP BY tenant_id, user_id, baseline_date, model_version, trained_from, trained_to
            )
            """,
            parameters,
            default=0,
        )
        return _baseline_rows_to_profiles(rows), int(total or 0)

    def get_user_baseline(
        self,
        user_id: str,
        *,
        tenant_id: str | None = None,
        baseline_date: date | None = None,
    ) -> dict[str, Any] | None:
        items, _total = self.list_user_baselines(
            tenant_id=tenant_id,
            user_id=user_id,
            baseline_date=baseline_date,
            limit=1,
            offset=0,
        )
        return items[0] if items else None

    def insert_ai_judgement(self, judgement: AIJudgement | dict[str, Any]) -> None:
        payload = _model_payload(judgement)
        row = _row_from_payload(
            payload,
            AI_JUDGEMENT_COLUMNS,
            json_fields=AI_JUDGEMENT_JSON_FIELDS,
            defaults={"model_version": "", "is_mock": False},
        )
        self.client.insert("ai_judgements", [row], column_names=list(AI_JUDGEMENT_COLUMNS))

    def list_ai_judgements(
        self,
        *,
        event_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_filters(equals={"event_id": event_id})
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)
        rows = self._select_dicts(
            f"""
            SELECT {_columns_sql(AI_JUDGEMENT_COLUMNS)}
            FROM ai_judgements
            {where_sql}
            ORDER BY created_at DESC
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            """,
            parameters,
        )
        total = self._select_scalar(
            f"SELECT count() FROM ai_judgements {where_sql}",
            parameters,
            default=0,
        )
        return [_normalize_ai_judgement_row(row) for row in rows], int(total or 0)

    def get_latest_ai_judgement(self, event_id: str) -> dict[str, Any] | None:
        items, _total = self.list_ai_judgements(event_id=event_id, limit=1, offset=0)
        return items[0] if items else None

    def insert_feedback(self, feedback: AIFeedback | dict[str, Any]) -> None:
        payload = _model_payload(feedback)
        row = _row_from_payload(
            payload,
            AI_FEEDBACK_COLUMNS,
            defaults={"judgement_id": "", "user_id": "", "review_status": "pending"},
        )
        self.client.insert("ai_feedback", [row], column_names=list(AI_FEEDBACK_COLUMNS))

    def insert_daily_report(self, report: DailyReport | dict[str, Any], *, tenant_id: str = "default") -> None:
        payload = _daily_report_payload(_model_payload(report), tenant_id=tenant_id)
        row = _row_from_payload(payload, DAILY_REPORT_COLUMNS)
        self.client.insert("daily_security_reports", [row], column_names=list(DAILY_REPORT_COLUMNS))

    def insert_data_quality_metrics(self, metrics: Sequence[DataQualityMetric | dict[str, Any]]) -> None:
        rows = [
            _row_from_payload(_model_payload(metric), DATA_QUALITY_COLUMNS)
            for metric in metrics
        ]
        if rows:
            self.client.insert("data_quality_metrics", rows, column_names=list(DATA_QUALITY_COLUMNS))

    def security_log_quality_stats(self, event_ids: Sequence[str]) -> dict[str, Any]:
        if not event_ids:
            return {
                "security_logs_count": 0,
                "missing_event_time_count": 0,
                "missing_user_id_count": 0,
                "missing_src_ip_count": 0,
                "missing_action_count": 0,
                "missing_result_count": 0,
                "parse_error_count": 0,
            }
        sql = """
            SELECT
                count() AS security_logs_count,
                countIf(event_time IS NULL) AS missing_event_time_count,
                countIf(user_id = '') AS missing_user_id_count,
                countIf(src_ip = '') AS missing_src_ip_count,
                countIf(action = '') AS missing_action_count,
                countIf(result = '') AS missing_result_count,
                countIf(log_type = 'parse_error' OR has(risk_tags, 'parse_error')) AS parse_error_count
            FROM security_logs {final_clause}
            WHERE event_id IN {{event_ids:Array(String)}}
            """
        try:
            rows = self._select_dicts(
                sql.format(final_clause="FINAL"),
                {"event_ids": list(event_ids)},
            )
        except Exception:
            rows = self._select_dicts(
                sql.format(final_clause=""),
                {"event_ids": list(event_ids)},
            )
        return rows[0] if rows else {
            "security_logs_count": 0,
            "missing_event_time_count": 0,
            "missing_user_id_count": 0,
            "missing_src_ip_count": 0,
            "missing_action_count": 0,
            "missing_result_count": 0,
            "parse_error_count": 0,
        }

    def security_logs_table_size_bytes(self) -> int:
        value = self._select_scalar(
            """
            SELECT sum(bytes_on_disk)
            FROM system.parts
            WHERE database = {database:String}
              AND table = 'security_logs'
              AND active
            """,
            {"database": settings.clickhouse_database},
            default=0,
        )
        return int(value or 0)

    def insert_user_baselines(self, baselines: Sequence[UserBaseline | dict[str, Any]]) -> None:
        rows: list[list[Any]] = []
        for baseline in baselines:
            rows.extend(_baseline_rows_from_payload(_model_payload(baseline)))
        if rows:
            self.client.insert("ueba_user_baseline", rows, column_names=list(BASELINE_COLUMNS))

    def list_daily_reports(
        self,
        *,
        tenant_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filters, parameters = _build_daily_report_filters(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )
        where_sql = _where(filters)
        parameters |= _pagination_parameters(limit=limit, offset=offset)
        rows = self._select_dicts(
            f"""
            SELECT {_columns_sql(DAILY_REPORT_COLUMNS)}
            FROM daily_security_reports
            {where_sql}
            ORDER BY report_date DESC, tenant_id ASC
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
            """,
            parameters,
        )
        total = self._select_scalar(
            f"SELECT count() FROM daily_security_reports {where_sql}",
            parameters,
            default=0,
        )
        return [_normalize_daily_report_row(row) for row in rows], int(total or 0)

    def get_stats_overview(
        self,
        *,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        log_filters, parameters = _build_log_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
        )
        anomaly_filters, anomaly_parameters = _build_anomaly_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
        )
        parameters |= {f"anom_{key}": value for key, value in anomaly_parameters.items()}
        anomaly_where = _where(
            [clause.replace("{", "{anom_") for clause in anomaly_filters]
        )
        row = self._select_dicts(
            f"""
            SELECT
                (SELECT count() FROM security_logs {_where(log_filters)}) AS log_count,
                (SELECT max(ingest_time) FROM security_logs {_where(log_filters)}) AS latest_log_ingest_time,
                (SELECT count() FROM anomaly_events {anomaly_where}) AS anomaly_count,
                (
                    SELECT count()
                    FROM anomaly_events
                    {_where([*anomaly_filters, "risk_level IN ('high', 'critical')"]).replace("{", "{anom_")}
                ) AS high_risk_count,
                (
                    SELECT count()
                    FROM anomaly_events
                    {_where([*anomaly_filters, "risk_level = 'critical'"]).replace("{", "{anom_")}
                ) AS critical_count
            """,
            parameters,
        )
        return row[0] if row else {
            "log_count": 0,
            "latest_log_ingest_time": None,
            "anomaly_count": 0,
            "high_risk_count": 0,
            "critical_count": 0,
        }

    def _select_scalar(
        self,
        sql: str,
        parameters: dict[str, Any] | None = None,
        *,
        default: Any = None,
    ) -> Any:
        rows = self.query(sql, parameters)
        if not rows:
            return default
        return rows[0][0] if rows[0] else default

    def _select_dicts(
        self,
        sql: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.query(sql, parameters=parameters or {})
        rows = list(getattr(result, "result_rows", []))
        column_names = list(getattr(result, "column_names", []))
        if not column_names:
            column_names = _parse_select_aliases(sql)
        return [dict(zip(column_names, row)) for row in rows]


def _build_log_filters(
    *,
    tenant_id: str | None = None,
    source_type: str | None = None,
    log_type: str | None = None,
    user_id: str | None = None,
    src_ip: str | None = None,
    action: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[str], dict[str, Any]]:
    return _build_filters(
        equals={
            "tenant_id": tenant_id,
            "source_type": source_type,
            "log_type": log_type,
            "user_id": user_id,
            "src_ip": src_ip,
            "action": action,
            "result": result,
        },
        time_field="event_time",
        start_time=start_time,
        end_time=end_time,
    )


def _build_anomaly_filters(
    *,
    tenant_id: str | None = None,
    risk_level: str | None = None,
    user_id: str | None = None,
    src_ip: str | None = None,
    reason_code: str | None = None,
    ai_status: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[str], dict[str, Any]]:
    filters, parameters = _build_filters(
        equals={
            "tenant_id": tenant_id,
            "risk_level": risk_level,
            "user_id": user_id,
            "src_ip": src_ip,
            "ai_status": ai_status,
            "status": status,
        },
        time_field="event_time",
        start_time=start_time,
        end_time=end_time,
    )
    if reason_code:
        filters.append("has(reason_codes, {reason_code:String})")
        parameters["reason_code"] = reason_code
    return filters, parameters


def _build_baseline_filters(
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    baseline_date: date | None = None,
) -> tuple[list[str], dict[str, Any]]:
    filters, parameters = _build_filters(
        equals={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "baseline_date": baseline_date,
        }
    )
    return filters, parameters


def _build_daily_report_filters(
    *,
    tenant_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[list[str], dict[str, Any]]:
    filters, parameters = _build_filters(equals={"tenant_id": tenant_id})
    if start_date:
        filters.append("report_date >= {start_date:Date}")
        parameters["start_date"] = start_date
    if end_date:
        filters.append("report_date <= {end_date:Date}")
        parameters["end_date"] = end_date
    return filters, parameters


def _build_filters(
    *,
    equals: dict[str, Any],
    time_field: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[str], dict[str, Any]]:
    filters: list[str] = []
    parameters: dict[str, Any] = {}
    for field, value in equals.items():
        if value is None:
            continue
        filters.append(f"{field} = {{{field}:{_clickhouse_type(value)}}}")
        parameters[field] = value
    if time_field and (start_time or end_time):
        if start_time:
            filters.append(f"{time_field} >= {{start_time:DateTime64(3)}}")
            parameters["start_time"] = start_time
        if end_time:
            filters.append(f"{time_field} <= {{end_time:DateTime64(3)}}")
            parameters["end_time"] = end_time
    return filters, parameters


def _where(filters: Sequence[str]) -> str:
    return f"WHERE {' AND '.join(filters)}" if filters else ""


def _columns_sql(columns: Sequence[str], table_alias: str | None = None) -> str:
    if not table_alias:
        return ", ".join(columns)
    return ", ".join(f"{table_alias}.{column} AS {column}" for column in columns)


def _pagination_parameters(*, limit: int, offset: int) -> dict[str, int]:
    return {
        "limit": _normalize_limit(limit),
        "offset": max(0, int(offset)),
    }


def _normalize_limit(limit: int) -> int:
    return max(1, int(limit))


def _clickhouse_type(value: Any) -> str:
    # 一处细节：datetime 需要写在 date 的前面，因为 datetime 是 date 的子类
    if isinstance(value, datetime):
        return "DateTime64(3)"
    if isinstance(value, date):
        return "Date"
    if isinstance(value, int):
        return "Int64"
    if isinstance(value, float):
        return "Float64"
    return "String"

# 调用 json_loads 把日志的 json 字段转化为 Python 对象
def _normalize_log_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for field in LOG_JSON_FIELDS:
        normalized[field] = _json_loads(normalized.get(field), default={})
    return normalized


# 把表示基线偏离的 json 字段转化为列表，其他的转化为其他 Python 对象
def _normalize_anomaly_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for field in ANOMALY_JSON_FIELDS:
        default = [] if field == "baseline_deviations" else {}
        normalized[field] = _json_loads(normalized.get(field), default=default)
    return normalized


def _normalize_ai_judgement_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for field in AI_JUDGEMENT_JSON_FIELDS:
        normalized[field] = _json_loads(normalized.get(field), default={})
    normalized["is_mock"] = bool(normalized.get("is_mock"))
    return normalized


# 把日报组织成适合接口返回的对象
def _normalize_daily_report_row(row: dict[str, Any]) -> dict[str, Any]:
    report_date = row.get("report_date")
    recommended_actions = _string_list(row.get("recommended_actions"))
    return {
        "report_id": f"{row.get('tenant_id', 'default')}:{report_date}",
        "date": str(report_date),
        "created_at": row.get("created_at"),
        "overall_score": row.get("overall_score", 0),
        "log_count": row.get("total_logs", 0),
        "alert_count": row.get("anomaly_count", 0),
        "high_risk_count": int(row.get("high_count") or 0) + int(row.get("critical_count") or 0),
        "major_risks": _string_list(row.get("top_attack_types")),
        "high_risk_users": _string_list(row.get("top_risk_users")),
        "typical_alerts": [{"event_id": event_id} for event_id in _string_list(row.get("key_events"))],
        "ai_summary": row.get("ai_summary", ""),
        "recommendation": "\n".join(recommended_actions),
        "markdown": row.get("markdown_body", ""),
    }


# 把多行 baseline feature 合并成一个用户基线 profile
def _baseline_rows_to_profiles(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        # 构造：用户基线的唯一标识，即 key
        key = (
            row.get("baseline_date"),
            row.get("tenant_id"),
            row.get("user_id"),
            row.get("model_version"),
            row.get("trained_from"),
            row.get("trained_to"),
        )
        # 如果字段已经有，key 设为字典中的字段，否则取默认值
        item = grouped.setdefault(
            key,
            {
                "baseline_date": row.get("baseline_date"),
                "tenant_id": row.get("tenant_id"),
                "user_id": row.get("user_id"),
                "model_version": row.get("model_version"),
                "trained_from": row.get("trained_from"),
                "trained_to": row.get("trained_to"),
                "sample_days": row.get("sample_days", 0),
                "sample_count": row.get("sample_count", 0),
                "baseline_confidence": row.get("baseline_confidence", 0),
                "who_profile": {},
                "time_profile": {},
                "location_profile": {},
                "access_profile": {},
                "volume_profile": {},
                "result_profile": {},
                "why_profile": {},
                "fallback_level": row.get("fallback_level", "none"),
                "created_at": row.get("created_at"),
            },
        )
        # 取 max 值保险，一般没问题
        item["sample_days"] = max(int(item.get("sample_days") or 0), int(row.get("sample_days") or 0))
        item["sample_count"] = max(int(item.get("sample_count") or 0), int(row.get("sample_count") or 0))
        item["baseline_confidence"] = max(
            float(item.get("baseline_confidence") or 0),
            float(row.get("baseline_confidence") or 0),
        )

        profile_name = f"{row.get('profile_group')}_profile"
        if profile_name not in item:
            continue
        item[profile_name][str(row.get("feature_name"))] = {
            "mean_value": row.get("mean_value"),
            "std_value": row.get("std_value"),
            "p50_value": row.get("p50_value"),
            "p95_value": row.get("p95_value"),
            "p99_value": row.get("p99_value"),
            "common_values": _string_list(row.get("common_values")),
            "value_histogram": _json_loads(row.get("value_histogram"), default={}),
        }
    return list(grouped.values())


def _daily_report_payload(payload: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    report_date = _coerce_date(payload.get("date") or payload.get("report_date"))
    high_risk_count = int(payload.get("high_risk_count") or 0)
    typical_alerts = payload.get("typical_alerts") if isinstance(payload.get("typical_alerts"), list) else []
    key_events = [
        str(item.get("event_id"))
        for item in typical_alerts
        if isinstance(item, dict) and item.get("event_id")
    ]
    recommendation = payload.get("recommendation", "")
    recommended_actions = recommendation if isinstance(recommendation, list) else _split_non_empty_lines(str(recommendation))
    return {
        "report_date": report_date,
        "tenant_id": tenant_id,
        "total_logs": int(payload.get("log_count") or payload.get("total_logs") or 0),
        "anomaly_count": int(payload.get("alert_count") or payload.get("anomaly_count") or 0),
        "high_count": high_risk_count,
        "critical_count": int(payload.get("critical_count") or 0),
        "overall_score": float(payload.get("overall_score") or 0),
        "top_risk_users": _string_list(payload.get("high_risk_users") or payload.get("top_risk_users")),
        "top_attack_types": _string_list(payload.get("major_risks") or payload.get("top_attack_types")),
        "key_events": key_events or _string_list(payload.get("key_events")),
        "ai_summary": str(payload.get("ai_summary") or ""),
        "recommended_actions": recommended_actions,
        "markdown_body": str(payload.get("markdown") or payload.get("markdown_body") or ""),
        "created_at": payload.get("created_at"),
    }


def _baseline_rows_from_payload(payload: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    profile_names = {
        "who_profile": "who",
        "time_profile": "time",
        "location_profile": "location",
        "access_profile": "access",
        "volume_profile": "volume",
        "result_profile": "result",
        "why_profile": "why",
    }
    base = {
        "baseline_date": payload.get("baseline_date"),
        "tenant_id": payload.get("tenant_id") or "default",
        "user_id": payload.get("user_id") or "",
        "sample_days": payload.get("sample_days") or 0,
        "sample_count": payload.get("sample_count") or 0,
        "baseline_confidence": payload.get("baseline_confidence") or 0,
        "trained_from": payload.get("trained_from"),
        "trained_to": payload.get("trained_to"),
        "fallback_level": payload.get("fallback_level") or "none",
        "model_version": payload.get("model_version") or "",
        "created_at": payload.get("created_at"),
    }
    for profile_name, profile_group in profile_names.items():
        profile = payload.get(profile_name)
        if not isinstance(profile, dict):
            continue
        for feature_name, value in profile.items():
            feature_payload = {
                **base,
                "profile_group": profile_group,
                "feature_name": str(feature_name),
                **_baseline_feature_value(value),
            }
            rows.append(
                _row_from_payload(
                    feature_payload,
                    BASELINE_COLUMNS,
                    json_fields={"value_histogram"},
                    defaults={
                        "mean_value": None,
                        "std_value": None,
                        "p50_value": None,
                        "p95_value": None,
                        "p99_value": None,
                        "common_values": [],
                        "value_histogram": {},
                    },
                )
            )
    return rows


def _baseline_feature_value(value: Any) -> dict[str, Any]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"mean_value": float(value), "common_values": [], "value_histogram": {}}
    if isinstance(value, list):
        return {"common_values": _string_list(value), "value_histogram": {}}
    if isinstance(value, dict):
        numeric_fields = {
            field: value.get(field)
            for field in ("mean_value", "std_value", "p50_value", "p95_value", "p99_value")
            if isinstance(value.get(field), (int, float))
        }
        common_values = value.get("common_values")
        histogram = value.get("value_histogram")
        if numeric_fields or common_values is not None or histogram is not None:
            return {
                **numeric_fields,
                "common_values": _string_list(common_values),
                "value_histogram": histogram if isinstance(histogram, dict) else {},
            }
        return {"common_values": [], "value_histogram": value}
    return {"common_values": [str(value)] if value not in (None, "") else [], "value_histogram": {}}


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _split_non_empty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


# 把 json 字符串转化成字典或者列表
def _json_loads(value: Any, *, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


# 和 loads 相反，python 对象转化为 json 字符串
def _json_dumps(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


# 把 string 和 Iterable 转化为列表
def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Iterable):
        return [str(item) for item in value if item is not None]
    return []


# 把 Pydantic 对象转化为字典
def _model_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return dict(value)


# 把字典转化为可以放进数据库对应列的数据结构
def _row_from_payload(
    payload: dict[str, Any],
    columns: Sequence[str],
    *,
    json_fields: set[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> list[Any]:
    resolved_defaults = defaults or {}
    resolved_json_fields = json_fields or set()
    row: list[Any] = []
    for column in columns:
        value = payload.get(column, resolved_defaults.get(column))
        if value is None and column in resolved_defaults:
            value = resolved_defaults[column]
        if column in resolved_json_fields:
            value = _json_dumps(value)
        if isinstance(value, bool):
            value = int(value)
        row.append(value)
    return row


# 检查传入的内容是否在允许范围内（用 set 的差实现）
def _assert_allowed_values(values: Sequence[str], allowed: Iterable[str], label: str) -> None:
    allowed_set = set(allowed)
    invalid = sorted(set(values) - allowed_set)
    if invalid:
        raise ValueError(f"Unsupported {label}: {', '.join(invalid)}")


# 从 SELECT 中得到列名字段
def _parse_select_aliases(sql: str) -> list[str]:
    upper_sql = sql.upper()
    if "SELECT" not in upper_sql or "FROM" not in upper_sql:
        return []
    # 字符串切片，取 SELECT 和 FROM 之间的字段（本质[:]语法）
    select_sql = sql[upper_sql.index("SELECT") + len("SELECT"):upper_sql.index("FROM")]
    aliases: list[str] = []
    for raw_part in select_sql.split(","):
        part = raw_part.strip()
        if " AS " in part.upper():
            # 从右边第一个空格切，取右数第一个字段（即 AS 右边的字段，别名）
            aliases.append(part.rsplit(" ", 1)[-1])
        # 排除诸如 max(count) 这类字段
        elif part and "(" not in part:
            # 比如 b.tenant_id 执行后得到 tenant_id
            aliases.append(part.split(".")[-1])
    return aliases
