#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:${FASTAPI_HOST_PORT:-8000}}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:${FRONTEND_HOST_PORT:-5173}}"
CLICKHOUSE_DB="${CLICKHOUSE_DATABASE:-log_ai}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

log() {
  printf '[p0-e2e] %s\n' "$*"
}

wait_for() {
  local name="$1"
  local command="$2"
  local deadline=$((SECONDS + WAIT_SECONDS))
  until bash -lc "$command" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      log "timeout waiting for ${name}"
      return 1
    fi
    sleep 3
  done
  log "${name} ready"
}

if [[ "${SKIP_COMPOSE_UP:-0}" != "1" ]]; then
  log "starting default compose stack"
  docker compose up -d --build

  log "submitting Flink raw_logs -> parsed_logs job"
  docker compose --profile jobs up -d flink-submit
fi

log "checking service health"
docker compose ps

wait_for "backend health" "curl -fsS '${API_URL}/api/v1/health'"
wait_for "frontend" "curl -fsS '${FRONTEND_URL}'"

log "waiting for generated raw files"
wait_for "multi-source log files" "test -s logs/vpn.log -o -s logs/api.log -o -s logs/oa.log"

log "waiting for ClickHouse security_logs growth"
wait_for "security_logs rows" "test \"\$(docker compose exec -T clickhouse clickhouse-client --query 'SELECT count() FROM ${CLICKHOUSE_DB}.security_logs')\" -gt 0"
wait_for "multi-source security_logs rows" "test \"\$(docker compose exec -T clickhouse clickhouse-client --query 'SELECT uniqExact(source_type) FROM ${CLICKHOUSE_DB}.security_logs')\" -ge 3"

log "ClickHouse counts by source_type"
docker compose exec -T clickhouse clickhouse-client --query "
SELECT source_type, count()
FROM ${CLICKHOUSE_DB}.security_logs
GROUP BY source_type
ORDER BY source_type
FORMAT PrettyCompact
"

log "API /logs sample"
curl -fsS "${API_URL}/api/v1/logs?limit=1" | python3 -m json.tool

log "API /anomalies sample"
curl -fsS "${API_URL}/api/v1/anomalies?limit=1" | python3 -m json.tool

log "writing data_quality_metrics from manifest"
docker compose exec -T backend python scripts/write_data_quality_metrics.py --manifest /var/log/app/manifest.jsonl || \
  log "data quality write skipped; ensure scripts are available in the backend image or run from host with Python deps"

log "P0 e2e check completed"
