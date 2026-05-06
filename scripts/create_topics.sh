#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER=${1:-localhost:9092}
TOPICS=(raw_logs parsed_logs alert_events ai_reports system_metrics)

for topic in "${TOPICS[@]}"; do
  docker exec kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 1
done

echo "Created topics: ${TOPICS[*]}"
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP_SERVER" --list
