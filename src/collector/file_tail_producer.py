from __future__ import annotations

import time
from pathlib import Path

from src.collector.kafka_producer import RawKafkaProducer


def stream_file_to_kafka(
    file_path: Path,
    source_type: str = "vpn",
    from_beginning: bool = True,
    follow: bool = False,
    poll_interval: float = 0.5,
    stop_after_eof: bool = True,
) -> int:
    sent = 0
    producer = RawKafkaProducer()
    with file_path.open("r", encoding="utf-8") as f:
        if not from_beginning:
            f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if not line:
                    continue
                producer.send_raw_line(line, source_type=source_type, extra={"log_path": str(file_path)})
                sent += 1
                continue
            if follow:
                time.sleep(poll_interval)
                continue
            if stop_after_eof:
                break
            time.sleep(poll_interval)
    producer.flush()
    producer.close()
    return sent
