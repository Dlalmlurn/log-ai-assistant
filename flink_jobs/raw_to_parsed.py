from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pyflink.common import Types
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)

try:
    # Available on pyflink 1.18; lets committed_offsets() fall back to earliest
    # when the consumer group has no committed position yet.
    from pyflink.datastream.connectors.kafka import KafkaOffsetResetStrategy
except ImportError:  # pragma: no cover - depends on pyflink build
    KafkaOffsetResetStrategy = None

# Make src importable when running with `flink run -py`
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.log_parser import normalize_raw_record  # noqa: E402


def to_parsed_json(raw: str) -> str:
    try:
        # The Filebeat envelope carries source_type for all 7 log families; the
        # hint is only used when the envelope omits it. Default to "system" so a
        # missing source_type never silently mislabels a record as VPN.
        normalized = normalize_raw_record(raw, source_type_hint="system")
        return json.dumps(normalized.model_dump(mode="json"), ensure_ascii=False)
    except Exception as exc:
        err = {
            "event_id": "parse-error",
            "event_time": "1970-01-01T00:00:00Z",
            "ingest_time": "1970-01-01T00:00:00Z",
            "tenant_id": "default",
            "source_type": "system",
            "log_type": "parse_error",
            "action": "access",
            "result": "error",
            "message": f"parse_error: {exc}",
            "raw_log": raw,
            "risk_tags": ["parse_error"],
            "attrs": {"error": str(exc)},
        }
        return json.dumps(err, ensure_ascii=False)


def run_job(bootstrap_servers: str, raw_topic: str, parsed_topic: str, group_id: str) -> None:
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.enable_checkpointing(10000)

    # Resume from the consumer group's committed offsets so a restart does not
    # re-process the whole topic. When the group has no committed offset yet
    # (first submit, or Filebeat wrote before Flink was submitted), fall back to
    # EARLIEST instead of LATEST so already-buffered raw_logs are not skipped.
    if KafkaOffsetResetStrategy is not None:
        starting_offsets = KafkaOffsetsInitializer.committed_offsets(
            KafkaOffsetResetStrategy.EARLIEST
        )
    else:  # pragma: no cover - depends on pyflink build
        starting_offsets = KafkaOffsetsInitializer.earliest()

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_topics(raw_topic)
        .set_group_id(group_id)
        .set_starting_offsets(starting_offsets)
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(parsed_topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    ds = env.from_source(source, WatermarkStrategy.no_watermarks(), "raw-logs-source")
    parsed = ds.map(to_parsed_json, output_type=Types.STRING())
    parsed.sink_to(sink)

    env.execute("raw_logs_to_parsed_logs")


def main() -> None:
    parser = argparse.ArgumentParser(description="PyFlink job: raw_logs -> parsed_logs")
    parser.add_argument("--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"))
    parser.add_argument("--raw-topic", default=os.getenv("KAFKA_RAW_TOPIC", "raw_logs"))
    parser.add_argument("--parsed-topic", default=os.getenv("KAFKA_PARSED_TOPIC", "parsed_logs"))
    parser.add_argument("--group-id", default="flink-raw-to-parsed")
    args = parser.parse_args()
    run_job(args.bootstrap_servers, args.raw_topic, args.parsed_topic, args.group_id)


if __name__ == "__main__":
    main()
