from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT


@dataclass(frozen=True)
class OperationsConfig:
    timezone_name: str
    lock_dir: Path
    manifest_path: Path
    threshold_path: Path
    scheduler_interval_seconds: int
    max_attempts: int
    retry_base_seconds: int
    watermark_grace_minutes: int
    notification_webhook_url: str
    notification_max_attempts: int
    frontend_base_url: str


def load_operations_config() -> OperationsConfig:
    return OperationsConfig(
        timezone_name=os.getenv("OPERATIONS_TIMEZONE", "UTC"),
        lock_dir=Path(os.getenv("OPERATIONS_LOCK_DIR", "/var/lock/log-ai-operations")),
        manifest_path=Path(os.getenv("LOG_GENERATOR_MANIFEST", "/var/log/app/manifest.jsonl")),
        threshold_path=Path(
            os.getenv(
                "ACCEPTANCE_THRESHOLDS_PATH",
                str(PROJECT_ROOT / "config" / "acceptance-thresholds-v1.json"),
            )
        ),
        scheduler_interval_seconds=_int_env("OPERATIONS_SCHEDULER_INTERVAL_SECONDS", 60),
        max_attempts=_int_env("OPERATIONS_MAX_ATTEMPTS", 3),
        retry_base_seconds=_int_env("OPERATIONS_RETRY_BASE_SECONDS", 2),
        watermark_grace_minutes=_int_env("OPERATIONS_WATERMARK_GRACE_MINUTES", 30),
        notification_webhook_url=os.getenv("NOTIFICATION_WEBHOOK_URL", "").strip(),
        notification_max_attempts=_int_env("NOTIFICATION_MAX_ATTEMPTS", 5),
        frontend_base_url=os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/"),
    )


def load_thresholds(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not payload.get("version"):
        raise ValueError(f"invalid acceptance threshold configuration: {path}")
    return payload


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
