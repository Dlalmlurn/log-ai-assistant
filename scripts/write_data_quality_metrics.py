from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.quality.data_quality import (
    build_reconciliation_report,
    verify_manifest_event_ids,
    write_data_quality_metrics,
)
from src.storage import ClickHouseStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Write data_quality_metrics from generator manifest and ClickHouse.")
    parser.add_argument("--manifest", default="logs/manifest.jsonl")
    parser.add_argument("--date", default=None, help="Metric date in YYYY-MM-DD. Defaults to manifest timestamps.")
    parser.add_argument(
        "--verify-event-ids",
        action="store_true",
        help="Sample manifest event_id values and verify they are present in security_logs.",
    )
    parser.add_argument("--sample-size", type=int, default=20)
    args = parser.parse_args()

    metric_date = date.fromisoformat(args.date) if args.date else None
    storage = ClickHouseStorage()
    metrics = write_data_quality_metrics(
        storage=storage,
        manifest_path=Path(args.manifest),
        metric_date=metric_date,
    )
    event_id_check = (
        verify_manifest_event_ids(
            storage=storage,
            manifest_path=Path(args.manifest),
            sample_size=args.sample_size,
        )
        if args.verify_event_ids
        else None
    )
    print(
        json.dumps(
            {
                "written": len(metrics),
                "items": [item.model_dump(mode="json") for item in metrics],
                "reconciliation": build_reconciliation_report(metrics),
                "event_id_check": event_id_check,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
