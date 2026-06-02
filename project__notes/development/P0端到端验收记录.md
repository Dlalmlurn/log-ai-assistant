# P0 End-to-End Acceptance

This note records the P0 gate owned by member C.

## Scope

The gate checks that the formal path is still usable:

```text
Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React
```

It also checks that generated logs carry a stable `event_id` from the raw file to `security_logs`, so manifest rows can be reconciled with ClickHouse rows.

## Command

```bash
scripts/p0_e2e_check.sh
```

If the stack is already running:

```bash
SKIP_COMPOSE_UP=1 scripts/p0_e2e_check.sh
```

## Expected Evidence

- `docker compose ps` shows Kafka, Flink, ClickHouse, backend, frontend, Filebeat and log-generator running or healthy.
- At least one generated source file exists under `logs/`, such as `vpn.log`, `api.log` or `oa.log`.
- `log_ai.security_logs` count is greater than 0.
- `security_logs` contains multiple `source_type` values after the generator has run for a short period.
- `GET /api/v1/logs?limit=1` returns a paginated JSON response.
- `GET /api/v1/anomalies?limit=1` returns a paginated JSON response, even if `items` is empty.
- `data_quality_metrics` can be written from `logs/manifest.jsonl` after ClickHouse rows appear.

## Useful Manual Queries

```bash
docker compose exec -T clickhouse clickhouse-client --query \
  "SELECT source_type, count() FROM log_ai.security_logs GROUP BY source_type ORDER BY source_type"
```

```bash
docker compose exec -T clickhouse clickhouse-client --query \
  "SELECT event_id, source_type, scenario_type, attack_chain_id, step_index FROM log_ai.security_logs WHERE attack_chain_id != '' ORDER BY attack_chain_id, step_index LIMIT 20"
```

```bash
curl -fsS "http://localhost:8000/api/v1/logs?limit=5"
```

## Failure Notes

- If raw files grow but `security_logs` does not, check Filebeat output and the Flink submit job.
- If ClickHouse rows exist but API calls fail, check backend health and ClickHouse connection settings.
- If manifest counts exceed ClickHouse counts, inspect parse errors and Kafka/Flink lag before treating it as data loss.
- If duplicate raw delivery is suspected, verify whether repeated rows share the same `event_id`; `security_logs` uses `ReplacingMergeTree(ingest_time)` with `event_id` in the sorting key.
