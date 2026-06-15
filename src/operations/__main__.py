from __future__ import annotations

import argparse
import json
from datetime import date

from src.operations.runner import OperationsRunner
from src.storage import ClickHouseStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="ADR-011 operations control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once = sub.add_parser("run-once", help="run one idempotent operations task")
    run_once.add_argument("--task", required=True)
    run_once.add_argument("--tenant-id", default="default")
    run_once.add_argument("--target-date", type=date.fromisoformat)
    run_once.add_argument("--force", action="store_true")

    sub.add_parser("scheduler", help="run the single-active scheduler loop")
    args = parser.parse_args()
    from src.health import get_consumer_lag

    runner = OperationsRunner(ClickHouseStorage(), lag_probe=get_consumer_lag)
    if args.command == "scheduler":
        runner.run_scheduler_forever()
        return

    result = runner.run_task(
        args.task,
        tenant_id=args.tenant_id,
        target_date=args.target_date,
        force=args.force,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if result.status not in {"succeeded", "needs_review"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
