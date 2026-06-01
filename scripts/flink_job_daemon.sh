#!/bin/bash
# Flink job daemon — waits for Flink, submits the raw→parsed job if missing,
# and monitors it, resubmitting after Flink restarts.
set -euo pipefail

FLINK_HOST="${FLINK_DASHBOARD_URL:-http://flink-jobmanager:8081}"
BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
RAW_TOPIC="${KAFKA_RAW_TOPIC:-raw_logs}"
PARSED_TOPIC="${KAFKA_PARSED_TOPIC:-parsed_logs}"
CHECK_INTERVAL="${FLINK_CHECK_INTERVAL:-30}"
JOB_NAME="raw_logs_to_parsed_logs"

echo "[flink-daemon] Starting, Flink at $FLINK_HOST"

wait_flink() {
    until curl -sf "${FLINK_HOST}/overview" > /dev/null 2>&1; do
        echo "[flink-daemon] Waiting for Flink at ${FLINK_HOST}..."
        sleep 5
    done
    echo "[flink-daemon] Flink is ready."
}

# Return 0 if a matching job exists (any non-terminal state)
job_present() {
    curl -sf "${FLINK_HOST}/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
try:
    jobs = json.load(sys.stdin).get('jobs', [])
    for j in jobs:
        if j.get('name', '') == '$JOB_NAME' and j.get('state') not in ('CANCELED','FAILED','FINISHED'):
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
"
}

submit_job() {
    echo "[flink-daemon] Submitting $JOB_NAME job..."
    timeout 30 flink run -d -m "${FLINK_HOST#http://}" -py /opt/app/flink_jobs/raw_to_parsed.py \
        --pyFiles /opt/app \
        --bootstrap-servers "$BOOTSTRAP_SERVERS" \
        --raw-topic "$RAW_TOPIC" \
        --parsed-topic "$PARSED_TOPIC" 2>&1 || true
    echo "[flink-daemon] Submission attempt complete."
}

# Main loop
wait_flink

while true; do
    if job_present; then
        echo "[flink-daemon] Job $JOB_NAME is present (RUNNING/RESTARTING/CREATED)."
    else
        echo "[flink-daemon] Job $JOB_NAME NOT present, submitting..."
        submit_job
    fi
    sleep "$CHECK_INTERVAL"
done
