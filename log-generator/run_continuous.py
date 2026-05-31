from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from scenario_generator import ScenarioGenerator, load_config, write_records


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default))


def main() -> None:
    output_dir = _get_path("LOG_GENERATOR_OUTPUT_DIR", "/var/log/app")
    manifest_path = _get_path("LOG_GENERATOR_MANIFEST", "/var/log/app/manifest.jsonl")
    config_path = _get_path(
        "LOG_GENERATOR_CONFIG",
        str(Path(__file__).resolve().parent / "scenarios" / "default.json"),
    )
    interval_seconds = max(1, _get_int("LOG_GENERATOR_INTERVAL_SECONDS", 5))
    batch_size = max(1, _get_int("LOG_GENERATOR_BATCH_SIZE", 3))
    seed = _get_int("LOG_GENERATOR_SEED", 42)

    config = load_config(config_path)
    generator = ScenarioGenerator(config, seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        "continuous scenario log-generator started: "
        f"output_dir={output_dir} manifest={manifest_path} "
        f"config={config_path} interval={interval_seconds}s batch_size={batch_size}"
    )

    while True:
        records = generator.generate_batch(now=datetime.now(), batch_size=batch_size)
        counts = write_records(records, output_dir, manifest_path)
        print(f"appended {sum(counts.values())} log lines by source: {counts}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
