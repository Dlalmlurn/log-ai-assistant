from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.schemas import UserBaseline
from src.storage import ClickHouseStorage
from src.storage.clickhouse_client import DAILY_FEATURES_COLUMNS

# Used by build_baselines_from_logs (the raw-log fallback path). The daily
# feature aggregation now computes night/sensitive/download/permission counts
# inside ClickHouse (see ClickHouseStorage.aggregate_daily_features_sql).
SENSITIVE_HINTS = ("download", "export", "admin", "sensitive")


def _ip_prefix(ip: str | None) -> str:
    if not ip:
        return ""
    parts = str(ip).split(".")
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return str(ip)


def _top_n_items(counter: Counter[str], n: int) -> list[str]:
    return [item for item, _ in counter.most_common(n)]


def aggregate_daily_features(
    storage: ClickHouseStorage,
    target_date: datetime | None = None,
) -> int:
    """Aggregate one day of ``security_logs`` into per-user daily features.

    The heavy per-log grouping is pushed into ClickHouse via
    :meth:`ClickHouseStorage.aggregate_daily_features_sql`; this function only
    shapes the small per-user aggregate rows into feature records. This avoids
    pulling up to 100k raw logs into Python and scales to 1GB/day.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc) - timedelta(days=1)

    if isinstance(target_date, datetime):
        date_val = target_date.date()
        day_start = datetime.combine(date_val, datetime.min.time(), tzinfo=timezone.utc)
    else:
        date_val = target_date.date() if hasattr(target_date, "date") else target_date
        day_start = datetime.combine(date_val, datetime.min.time(), tzinfo=timezone.utc)

    aggregates = storage.aggregate_daily_features_sql(metric_date=date_val)
    if not aggregates:
        return 0

    now_dt = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for agg in aggregates:
        event_count = int(agg.get("event_count") or 0)
        common_src_ips = _non_empty_top(agg.get("common_src_ips_raw"), 5)
        common_hosts = _non_empty_top(agg.get("common_hosts_raw"), 5)
        common_actions = _non_empty_top(agg.get("common_actions_raw"), 5)
        account_type_top = _non_empty_top(agg.get("account_type_top"), 1)
        night_count = int(agg.get("night_event_count") or 0)
        sensitive_count = int(agg.get("sensitive_action_count") or 0)

        rows.append({
            "feature_date": date_val,
            "tenant_id": str(agg.get("tenant_id") or "default"),
            "user_id": str(agg.get("user_id")),
            "account_type": account_type_top[0] if account_type_top else "unknown",
            "login_count": int(agg.get("login_count") or 0),
            "failed_login_count": int(agg.get("failed_login_count") or 0),
            "success_login_count": int(agg.get("success_login_count") or 0),
            "distinct_src_ip_count": int(agg.get("distinct_src_ip_count") or 0),
            "distinct_host_count": int(agg.get("distinct_host_count") or 0),
            "distinct_action_count": int(agg.get("distinct_action_count") or 0),
            "first_seen_time": agg.get("first_seen_time") or day_start,
            "last_seen_time": agg.get("last_seen_time") or day_start,
            "night_event_count": night_count,
            "sensitive_action_count": sensitive_count,
            "download_count": int(agg.get("download_count") or 0),
            "permission_change_count": int(agg.get("permission_change_count") or 0),
            "new_source_count": 0,
            "maintenance_window_hit_count": 0,
            "common_src_ips": common_src_ips,
            # Prefixes are derived from the top source IPs; cheap and good enough
            # for baseline location profiling without a second aggregation pass.
            "common_ip_prefixes": _top_n_items(
                Counter({p: 1 for p in {_ip_prefix(ip) for ip in common_src_ips}}), 5
            ),
            "common_hosts": common_hosts,
            "common_actions": common_actions,
            "profile_metrics": json.dumps({
                "unique_src_ips": int(agg.get("distinct_src_ip_count") or 0),
                "unique_hosts": int(agg.get("distinct_host_count") or 0),
                "unique_actions": int(agg.get("distinct_action_count") or 0),
                "night_ratio": round(night_count / event_count, 4) if event_count else 0,
                "sensitive_ratio": round(sensitive_count / event_count, 4) if event_count else 0,
            }),
            "created_at": now_dt,
        })

    storage.insert_user_daily_features(rows)
    return len(rows)


def _non_empty_top(values: Any, n: int) -> list[str]:
    """Filter empty strings out of a ClickHouse topK array and cap to ``n``."""
    if not isinstance(values, (list, tuple)):
        return []
    result = [str(item) for item in values if item is not None and str(item) != ""]
    return result[:n]


def aggregate_daily_features_batch(
    storage: ClickHouseStorage,
    start_date: datetime,
    end_date: datetime,
) -> int:
    total = 0
    current = start_date
    while current <= end_date:
        total += aggregate_daily_features(storage, current)
        current += timedelta(days=1)
    return total


def update_seen_sources(
    storage: ClickHouseStorage,
    target_date: datetime | None = None,
) -> int:
    if target_date is None:
        target_date = datetime.now(timezone.utc) - timedelta(days=1)

    if isinstance(target_date, datetime):
        date_val = target_date.date()
        start_dt = datetime.combine(date_val, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(date_val, datetime.max.time(), tzinfo=timezone.utc)
    else:
        start_dt = target_date
        end_dt = target_date + timedelta(days=1)

    logs, _total = storage.list_logs(
        start_time=start_dt,
        end_time=end_dt,
        limit=100000,
        offset=0,
    )
    if not logs:
        return 0

    new_sources: dict[tuple[str, str, str, str], datetime] = {}
    for log in logs:
        uid = str(log.get("user_id") or "")
        stype = str(log.get("source_type") or "")
        src_ip = str(log.get("src_ip") or "")
        dst_ip = str(log.get("dst_ip") or "")
        if not uid:
            continue

        keys: list[tuple[str, str, str, str] | None] = [
            ("default", uid, "ip", src_ip) if src_ip else None,
            ("default", uid, "host", dst_ip) if dst_ip else None,
        ]

        for key in filter(None, keys):
            tenant, user, source_type, source_key = key
            if not source_key:
                continue
            composite = (tenant, user, source_type, source_key)
            et = log.get("event_time")
            dt = _to_dt(et) if isinstance(et, str) else et
            if isinstance(dt, datetime):
                if composite not in new_sources or new_sources[composite] > dt:
                    new_sources[composite] = dt

    upserted = 0
    now_utc = datetime.now(timezone.utc)
    for (tenant, user, source_type, source_key), first_seen in new_sources.items():
        existing = storage.query_user_seen_sources(
            tenant_id=tenant,
            user_id=user,
            source_type=source_type,
            source_key=source_key,
            limit=1,
        )
        if existing:
            storage.upsert_user_seen_sources([{
                "tenant_id": tenant,
                "user_id": user,
                "source_type": source_type,
                "source_key": source_key,
                "first_seen_time": existing[0]["first_seen_time"],
                "last_seen_time": first_seen,
                "seen_count": int(existing[0].get("seen_count", 0)) + 1,
            }])
        else:
            storage.upsert_user_seen_sources([{
                "tenant_id": tenant,
                "user_id": user,
                "source_type": source_type,
                "source_key": source_key,
                "first_seen_time": first_seen,
                "last_seen_time": first_seen,
                "seen_count": 1,
            }])
        upserted += 1

    return upserted


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


def build_baselines_from_daily_features(
    storage: ClickHouseStorage,
    *,
    lookback_days: int = 90,
    tenant_id: str = "default",
) -> list[UserBaseline]:
    """Build per-user baselines from all available daily feature data.

    Uses up to ``lookback_days`` of history (default 90).  All dates with
    daily features are included so baselines reflect the full behaviour history.
    """
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=lookback_days)

    rows = storage.query(
        """SELECT * FROM ueba_user_daily_features
           WHERE feature_date BETWEEN {start:Date} AND {end:Date}
             AND tenant_id = {tenant:String}
           ORDER BY user_id, feature_date""",
        {"start": start_date, "end": end_date, "tenant": tenant_id},
    )

    if not rows:
        return []

    cols = list(DAILY_FEATURES_COLUMNS)
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        record = dict(zip(cols, row))
        by_user[str(record["user_id"])].append(record)

    DAILY_NUMERIC = (
        "login_count", "failed_login_count", "success_login_count",
        "distinct_src_ip_count", "distinct_host_count", "distinct_action_count",
        "night_event_count", "sensitive_action_count", "download_count",
        "permission_change_count", "new_source_count",
    )
    DAILY_STRING = ("account_type", "common_src_ips", "common_ip_prefixes", "common_hosts", "common_actions")

    import statistics
    from collections import Counter as _Counter

    def _p50(vals: list[float]) -> float:
        return float(statistics.median(vals)) if vals else 0

    def _p95(vals: list[float]) -> float:
        if not vals:
            return 0
        svals = sorted(vals)
        idx = int(len(svals) * 0.95)
        return float(svals[min(idx, len(svals) - 1)])

    def _p99(vals: list[float]) -> float:
        if not vals:
            return 0
        svals = sorted(vals)
        idx = int(len(svals) * 0.99)
        return float(svals[min(idx, len(svals) - 1)])

    results: list[UserBaseline] = []
    for user_id, daily_records in by_user.items():
        feature_dates = sorted({r["feature_date"] for r in daily_records if r.get("feature_date")})
        trained_from = min(feature_dates) if feature_dates else start_date
        trained_to = max(feature_dates) if feature_dates else end_date
        sample_days = len(feature_dates)
        sample_count = sum(int(r.get("login_count", 0) or 0) for r in daily_records)

        account_type = "unknown"
        who: dict[str, Any] = {"user_id": user_id, "account_type": "unknown"}
        time: dict[str, Any] = {}
        location: dict[str, Any] = {}
        access: dict[str, Any] = {}
        volume: dict[str, Any] = {}
        result: dict[str, Any] = {}
        why: dict[str, Any] = {}

        for field in DAILY_NUMERIC:
            vals = [float(r.get(field, 0) or 0) for r in daily_records]
            if not vals:
                continue
            mu = sum(vals) / len(vals)
            if len(vals) > 1:
                sigma = (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
            else:
                sigma = 0.0
            feature_stats = {"mean": round(mu, 4), "std": round(sigma, 4), "p50": round(_p50(vals), 4),
                             "p95": round(_p95(vals), 4), "p99": round(_p99(vals), 4)}

            if field in ("login_count", "success_login_count", "failed_login_count", "night_event_count"):
                result[field] = feature_stats
            elif field in ("distinct_src_ip_count", "distinct_host_count"):
                location[field] = feature_stats
            elif field in ("distinct_action_count", "sensitive_action_count", "download_count", "permission_change_count"):
                access[field] = feature_stats
            else:
                volume[field] = feature_stats

        if daily_records:
            ac = daily_records[0].get("account_type") or "unknown"
            account_type = str(ac)
            who["account_type"] = account_type

        if feature_dates:
            time["active_dates"] = [d.isoformat() for d in feature_dates]
            time["sample_days"] = sample_days

        # --- multi-factor confidence -------------------------------------------
        # factor 1: days coverage (40%)
        days_ratio = sample_days / max(lookback_days, sample_days) if lookback_days > 0 else 0
        days_score = min(1.0, sample_days / 3)  # 3 days = full score

        # factor 2: sample volume, log-scale (30%)
        volume_target = 50
        log_sample = __import__("math").log10(max(sample_count, 1))
        log_target = __import__("math").log10(volume_target)
        volume_score = min(1.0, log_sample / log_target) if log_target > 0 else 0

        # factor 3: feature coverage (30%)
        all_features: dict[str, Any] = {}
        for p in (who, time, location, access, volume, result):
            all_features.update(p)
        filled = sum(1 for v in all_features.values() if v is not None and v not in ("", [], {}))
        total_feats = max(len(all_features), 1)
        feature_score = filled / total_feats

        confidence = round(0.40 * days_score + 0.30 * volume_score + 0.30 * feature_score, 2)
        confidence = max(0.05, min(0.95, confidence))
        fallback = "peer_group" if confidence < 0.3 else "none"

        baseline = UserBaseline(
            baseline_date=datetime.now(timezone.utc).date(),
            tenant_id=tenant_id,
            user_id=user_id,
            model_version="baseline-v1",
            trained_from=trained_from,
            trained_to=trained_to,
            sample_days=sample_days,
            sample_count=sample_count,
            baseline_confidence=confidence,
            who_profile=who,
            time_profile=time,
            location_profile=location,
            access_profile=access,
            volume_profile=volume,
            result_profile=result,
            why_profile=why,
            fallback_level=fallback,
            created_at=datetime.now(timezone.utc),
        )
        results.append(baseline)

    return results


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

        fallback_days = len(set(event_dates))
        fallback_count = len(user_logs)
        import math as _math
        fallback_days_score = min(1.0, fallback_days / 3)
        fallback_vol_score = min(1.0, _math.log10(max(fallback_count, 1)) / _math.log10(50))
        fallback_conf = round(0.40 * fallback_days_score + 0.30 * fallback_vol_score + 0.30 * 1.0, 2)
        fallback_conf = max(0.05, min(0.95, fallback_conf))

        baseline = UserBaseline(
            baseline_date=datetime.now(timezone.utc).date(),
            tenant_id=tenant_id,
            user_id=user_id,
            model_version="baseline-v1",
            trained_from=trained_from,
            trained_to=trained_to,
            sample_days=fallback_days,
            sample_count=fallback_count,
            baseline_confidence=fallback_conf,
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
    # Primary path: build from daily features (T+1 from aggregated stats)
    baselines = build_baselines_from_daily_features(storage)

    # Fallback: if no daily features exist, build directly from raw security_logs
    if not baselines:
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
        if logs:
            baselines = build_baselines_from_logs(logs)

    if baselines:
        docs = [item.model_dump(mode="json") for item in baselines]
        storage.insert_user_baselines(baselines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)

    return baselines
