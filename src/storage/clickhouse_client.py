from __future__ import annotations

from typing import Any

from src.config import settings


class ClickHouseStorage:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
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
