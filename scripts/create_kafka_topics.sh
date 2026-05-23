#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
PARTITIONS="${KAFKA_TOPIC_PARTITIONS:-3}"
REPLICATION_FACTOR="${KAFKA_TOPIC_REPLICATION_FACTOR:-1}"

TOPICS=(
  "${KAFKA_RAW_TOPIC:-raw_logs}"
  "${KAFKA_PARSED_TOPIC:-parsed_logs}"
  "${KAFKA_ALERT_TOPIC:-alert_events}"
  "${KAFKA_AI_TOPIC:-ai_reports}"
  "${KAFKA_METRICS_TOPIC:-system_metrics}"
)

for topic in "${TOPICS[@]}"; do
  /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$PARTITIONS" \
    --replication-factor "$REPLICATION_FACTOR"
done

echo "Kafka topics are ready: ${TOPICS[*]}"
