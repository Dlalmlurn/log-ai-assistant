from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.schemas import UserBaseline
from src.storage import ClickHouseStorage

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
    by_user: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for log in logs:
        user_id = log.get("user_id")
        if user_id:
            by_user[(str(log.get("tenant_id") or "default"), str(user_id))].append(log)

    results: list[UserBaseline] = []
    for (tenant_id, user_id), user_logs in by_user.items():
        ip_counter: Counter[str] = Counter()
        ua_counter: Counter[str] = Counter()
        res_counter: Counter[str] = Counter()
        action_counter: Counter[str] = Counter()
        hours: list[int] = []
        api_calls_per_minute: Counter[str] = Counter()
        failed_login = 0
        success_login = 0
        sensitive_count = 0
        event_times: list[datetime] = []
        account_types: Counter[str] = Counter()
        roles: Counter[str] = Counter()
        departments: Counter[str] = Counter()

        for log in user_logs:
            dt = _to_dt(log.get("event_time"))
            event_times.append(dt)
            hours.append(dt.hour)

            if log.get("account_type"):
                account_types[str(log["account_type"])] += 1
            if log.get("user_role"):
                roles[str(log["user_role"])] += 1
            if log.get("department"):
                departments[str(log["department"])] += 1
            if log.get("src_ip"):
                ip_counter[str(log["src_ip"])] += 1

            if log.get("user_agent"):
                ua_counter[str(log["user_agent"])] += 1

            if log.get("resource"):
                res = str(log["resource"])
                res_counter[res] += 1
                if any(k in res.lower() for k in SENSITIVE_HINTS):
                    sensitive_count += 1

            if log.get("action"):
                action_counter[str(log["action"])] += 1

            if log.get("action") == "api_call":
                minute_key = dt.strftime("%Y-%m-%dT%H:%M")
                api_calls_per_minute[minute_key] += 1

            if log.get("action") == "login" and log.get("result") == "fail":
                failed_login += 1
            if log.get("action") == "login" and log.get("result") == "success":
                success_login += 1

        avg_api = 0.0
        if api_calls_per_minute:
            avg_api = round(sum(api_calls_per_minute.values()) / len(api_calls_per_minute), 2)

        sensitive_rate = 0.0
        if user_logs:
            sensitive_rate = round(sensitive_count / len(user_logs), 4)

        event_dates = [item.date() for item in event_times]
        trained_from = min(event_dates) if event_dates else datetime.now(timezone.utc).date()
        trained_to = max(event_dates) if event_dates else trained_from
        login_total = failed_login + success_login
        success_rate = round(success_login / login_total, 4) if login_total else 0.0
        failed_rate = round(failed_login / login_total, 4) if login_total else 0.0

        baseline = UserBaseline(
            baseline_date=datetime.now(timezone.utc).date(),
            tenant_id=tenant_id,
            user_id=user_id,
            model_version="baseline-v1",
            trained_from=trained_from,
            trained_to=trained_to,
            sample_days=len(set(event_dates)),
            sample_count=len(user_logs),
            baseline_confidence=min(1.0, round(len(set(event_dates)) / 7, 2)),
            who_profile={
                "user_id": user_id,
                "account_type": _top_n(account_types, 1)[0] if account_types else "unknown",
                "user_role": _top_n(roles, 1)[0] if roles else "",
                "department": _top_n(departments, 1)[0] if departments else "",
            },
            time_profile={
                "active_hours": _active_hour_ranges(hours),
                "hour_histogram": {str(hour): count for hour, count in Counter(hours).items()},
            },
            location_profile={
                "common_ips": _top_n(ip_counter, 5),
            },
            access_profile={
                "common_user_agents": _top_n(ua_counter, 3),
                "common_resources": _top_n(res_counter, 5),
                "common_actions": _top_n(action_counter, 5),
                "avg_api_calls_per_minute": avg_api,
                "sensitive_access_rate": sensitive_rate,
            },
            volume_profile={
                "event_count": len(user_logs),
            },
            result_profile={
                "failed_login_count_7d": failed_login,
                "success_login_count_7d": success_login,
                "login_success_rate": success_rate,
                "login_failed_rate": failed_rate,
            },
            why_profile={},
            fallback_level="none",
            created_at=datetime.now(timezone.utc),
        )
        results.append(baseline)

    return results


def build_and_store_baselines(storage: ClickHouseStorage, output_path: Path | None = None) -> list[UserBaseline]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)
    logs, _total = storage.list_logs(
        start_time=start_time,
        end_time=end_time,
        limit=10000,
        offset=0,
    )
    if not logs:
        logs, _total = storage.list_logs(limit=10000, offset=0)
    baselines = build_baselines_from_logs(logs)

    docs = [item.model_dump(mode="json") for item in baselines]
    storage.insert_user_baselines(baselines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)

    return baselines
