from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.quality.data_quality import write_data_quality_metrics
from src.storage import ClickHouseStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Write data_quality_metrics from generator manifest and ClickHouse.")
    parser.add_argument("--manifest", default="logs/manifest.jsonl")
    parser.add_argument("--date", default=None, help="Metric date in YYYY-MM-DD. Defaults to manifest timestamps.")
    args = parser.parse_args()

    metric_date = date.fromisoformat(args.date) if args.date else None
    metrics = write_data_quality_metrics(
        storage=ClickHouseStorage(),
        manifest_path=Path(args.manifest),
        metric_date=metric_date,
    )
    print(
        json.dumps(
            {
                "written": len(metrics),
                "items": [item.model_dump(mode="json") for item in metrics],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
