from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kafka import KafkaProducer

from src.config import settings


class RawKafkaProducer:
    def __init__(self, bootstrap_servers: list[str] | None = None, topic: str | None = None):
        self.topic = topic or settings.kafka_raw_topic
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers or settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            linger_ms=10,
            retries=3,
        )

    def send_raw_line(
        self,
        raw_line: str,
        source_type: str = "vpn",
        extra: dict[str, Any] | None = None,
    ) -> None:
        envelope = {
            "raw_message": raw_line,
            "source_type": source_type,
            "ingest_time": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            envelope.update(extra)
        self.producer.send(self.topic, envelope)

    def flush(self) -> None:
        self.producer.flush()

    def close(self) -> None:
        self.flush()
        self.producer.close()


def run_generator_once(
    outdir: Path,
    fmt: str = "jsonl",
    days: int = 1,
    count: int = 80,
    start: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(settings.generator_script),
        "--outdir",
        str(outdir),
        "--format",
        fmt,
        "--days",
        str(days),
        "--count",
        str(count),
    ]
    if start:
        cmd.extend(["--start", start])
    return subprocess.run(cmd, check=False, capture_output=True, text=True)
