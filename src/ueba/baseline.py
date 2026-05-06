from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import settings
from src.schemas import UserBaseline
from src.storage.elastic_client import ElasticStorage

SENSITIVE_HINTS = ("download", "export", "admin", "sensitive")


def _to_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _top_n(counter: Counter[str], n: int) -> list[str]:
    return [item for item, _ in counter.most_common(n)]


def _active_hour_ranges(hours: list[int]) -> list[str]:
    if not hours:
        return []
    counter = Counter(hours)
    top_hours = sorted([hour for hour, _ in counter.most_common(4)])
    if not top_hours:
        return []
    return [f"{top_hours[0]:02d}:00-{(top_hours[-1] + 1) % 24:02d}:00"]


def build_baselines_from_logs(logs: list[dict[str, Any]]) -> list[UserBaseline]:
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in logs:
        username = log.get("username")
        if username:
            by_user[username].append(log)

    results: list[UserBaseline] = []
    for username, user_logs in by_user.items():
        ip_counter: Counter[str] = Counter()
        ua_counter: Counter[str] = Counter()
        res_counter: Counter[str] = Counter()
        hours: list[int] = []
        api_calls_per_minute: Counter[str] = Counter()
        failed_login = 0
        sensitive_count = 0

        for log in user_logs:
            dt = _to_dt(log.get("event_time"))
            hours.append(dt.hour)

            if log.get("src_ip"):
                ip_counter[str(log["src_ip"])] += 1

            if log.get("user_agent"):
                ua_counter[str(log["user_agent"])] += 1

            if log.get("resource"):
                res = str(log["resource"])
                res_counter[res] += 1
                if any(k in res.lower() for k in SENSITIVE_HINTS):
                    sensitive_count += 1

            if log.get("action") == "api_call":
                minute_key = dt.strftime("%Y-%m-%dT%H:%M")
                api_calls_per_minute[minute_key] += 1

            if log.get("action") == "login" and log.get("status") == "failed":
                failed_login += 1

        avg_api = 0.0
        if api_calls_per_minute:
            avg_api = round(sum(api_calls_per_minute.values()) / len(api_calls_per_minute), 2)

        sensitive_rate = 0.0
        if user_logs:
            sensitive_rate = round(sensitive_count / len(user_logs), 4)

        baseline = UserBaseline(
            username=username,
            active_hours=_active_hour_ranges(hours),
            common_ips=_top_n(ip_counter, 5),
            common_user_agents=_top_n(ua_counter, 3),
            avg_api_calls_per_minute=avg_api,
            common_resources=_top_n(res_counter, 5),
            failed_login_count_7d=failed_login,
            sensitive_access_rate=sensitive_rate,
            updated_at=datetime.now(timezone.utc),
        )
        results.append(baseline)

    return results


def build_and_store_baselines(storage: ElasticStorage, output_path: Path | None = None) -> list[UserBaseline]:
    # For generated/historical event_time data, ingest_time is a more stable baseline window.
    logs = storage.fetch_recent_logs_by_field(hours=24 * 7, size=10000, time_field="ingest_time")
    if not logs:
        logs = storage.search(
            index=settings.elasticsearch_log_index,
            query={"match_all": {}},
            size=10000,
            sort=[{"ingest_time": "desc"}],
        )
    baselines = build_baselines_from_logs(logs)

    docs = [item.model_dump(mode="json") for item in baselines]
    storage.bulk_index(index=settings.elasticsearch_baseline_index, documents=docs, id_field="username")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)

    return baselines
