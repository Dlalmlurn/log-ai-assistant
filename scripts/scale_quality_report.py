#!/usr/bin/env python3
"""scale 数据正式质量报告。

汇总 docs/10_final_quality_criteria.md「数据规模标准」要求的指标，并补充查询耗时维度，
形成一份可对账的正式报告，覆盖：

  1. 数量      —— 各阶段计数(generated/raw/parsed/clickhouse_insert/security_logs)与原始/表大小。
  2. 缺失率    —— event_time/user_id/src_ip/action/result 缺失率与 parse_error_rate。
  3. 对账      —— 各阶段差异(deltas)与可解释说明(explanations)，event_id 抽样贯穿校验。
  4. 压缩率    —— raw_size_bytes / table_size_bytes。
  5. 查询耗时  —— 对 security_logs / anomaly_events 的代表性查询与聚合做基准计时。

前四项复用 src/quality/data_quality.py 的已验证实现并写入 data_quality_metrics；
查询耗时为报告期实测，不进入按日指标表，单列在报告 query_latency 段。

在能访问 ClickHouse 的环境运行（推荐后端容器内）:
    docker exec log-ai-backend python -m scripts.scale_quality_report \
        --manifest /var/log/app/manifest.jsonl --verify-event-ids
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.quality.data_quality import (
    build_data_quality_metrics,
    build_reconciliation_report,
    load_manifest_rows,
    verify_manifest_event_ids,
)
from src.storage import ClickHouseStorage


# 代表性查询：覆盖 docs/10「支持按时间、用户、IP、行为、日志类型查询；按用户、行为、
# 结果、风险等级聚合」。占位符在运行时用真实样本(最近的 user/ip)填充。
_QUERY_SPECS: list[tuple[str, str]] = [
    ("recent_by_time", "SELECT count() FROM security_logs WHERE event_time >= now() - INTERVAL 1 DAY"),
    ("filter_by_user", "SELECT count() FROM security_logs WHERE user_id = {user:String}"),
    ("filter_by_src_ip", "SELECT count() FROM security_logs WHERE src_ip = {ip:String}"),
    ("filter_by_action", "SELECT count() FROM security_logs WHERE action = {action:String}"),
    ("filter_by_source_type", "SELECT count() FROM security_logs WHERE source_type = {source_type:String}"),
    ("agg_by_user", "SELECT user_id, count() c FROM security_logs GROUP BY user_id ORDER BY c DESC LIMIT 20"),
    ("agg_by_action_result", "SELECT action, result, count() FROM security_logs GROUP BY action, result"),
    ("agg_by_risk_level", "SELECT risk_level, count() FROM anomaly_events GROUP BY risk_level"),
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def _sample_filters(storage: ClickHouseStorage) -> dict[str, str]:
    """取真实样本值填充参数化查询，保证基准查询命中实际数据。"""

    def _first(sql: str, default: str) -> str:
        try:
            rows = storage.query(sql)
        except Exception:
            return default
        if rows and rows[0] and rows[0][0] is not None:
            return str(rows[0][0])
        return default

    return {
        "user": _first(
            "SELECT user_id FROM security_logs WHERE user_id != '' GROUP BY user_id ORDER BY count() DESC LIMIT 1",
            "unknown",
        ),
        "ip": _first(
            "SELECT src_ip FROM security_logs WHERE src_ip != '' GROUP BY src_ip ORDER BY count() DESC LIMIT 1",
            "0.0.0.0",
        ),
        "action": _first(
            "SELECT action FROM security_logs WHERE action != '' GROUP BY action ORDER BY count() DESC LIMIT 1",
            "login",
        ),
        "source_type": _first(
            "SELECT source_type FROM security_logs GROUP BY source_type ORDER BY count() DESC LIMIT 1",
            "vpn",
        ),
    }


def benchmark_queries(storage: ClickHouseStorage, runs: int) -> list[dict[str, Any]]:
    filters = _sample_filters(storage)
    params = {
        "user": filters["user"],
        "ip": filters["ip"],
        "action": filters["action"],
        "source_type": filters["source_type"],
    }
    results: list[dict[str, Any]] = []
    for name, sql in _QUERY_SPECS:
        timings: list[float] = []
        rows_returned = 0
        error: str | None = None
        for _ in range(max(1, runs)):
            start = time.perf_counter()
            try:
                rows = storage.query(sql, params)
            except Exception as exc:  # noqa: BLE001 - 基准记录错误后继续
                error = str(exc)
                break
            timings.append((time.perf_counter() - start) * 1000.0)
            rows_returned = len(rows)
        entry = {
            "name": name,
            "runs": len(timings),
            "avg_ms": round(sum(timings) / len(timings), 2) if timings else None,
            "p95_ms": round(_percentile(timings, 95), 2) if timings else None,
            "max_ms": round(max(timings), 2) if timings else None,
            "rows_returned": rows_returned,
        }
        if error:
            entry["error"] = error
        results.append(entry)
    return {"filters": filters, "queries": results}


def _row_date(row: dict[str, Any]) -> date | None:
    raw = row.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def collect_metrics(
    storage: ClickHouseStorage,
    manifest_path: Path,
    forced_date: date | None,
) -> list:
    """按日期对账：每个 (date, source) 的 generated 与各阶段计数同日对齐。

    manifest 为多日累积，security_logs 又带 TTL，若把全量 generated 与单日入库直接相减
    会产生虚假缺口。这里逐日切片 manifest，复用已验证的 build_data_quality_metrics，
    保证 raw→parsed→security 的差异是同日可解释的。
    """

    rows = load_manifest_rows(manifest_path)
    if not rows:
        return []

    if forced_date is not None:
        date_buckets: dict[date, list[dict[str, Any]]] = {
            forced_date: [r for r in rows if _row_date(r) in (forced_date, None)]
        }
    else:
        date_buckets = {}
        fallback = datetime.now(timezone.utc).date()
        for row in rows:
            bucket = _row_date(row) or fallback
            date_buckets.setdefault(bucket, []).append(row)

    metrics: list = []
    for bucket_date, bucket_rows in sorted(date_buckets.items()):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=True, encoding="utf-8") as tmp:
            for row in bucket_rows:
                tmp.write(json.dumps(row, ensure_ascii=False) + "\n")
            tmp.flush()
            metrics.extend(
                build_data_quality_metrics(
                    storage=storage,
                    manifest_path=Path(tmp.name),
                    metric_date=bucket_date,
                )
            )
    return metrics


def _totals(metric_items: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "generated_count",
        "raw_logs_count",
        "parsed_logs_count",
        "clickhouse_insert_count",
        "security_logs_count",
        "injected_anomaly_count",
        "injected_high_risk_count",
        "raw_size_bytes",
    )
    totals = {k: int(sum(int(item.get(k) or 0) for item in metric_items)) for k in keys}
    # 压缩率应以整表口径计算：单条按日记录的 compression_ratio 用的是全表大小做分母，
    # 仅整表 raw_total/table_size 才是真实压缩比。
    table_size = int(metric_items[0].get("table_size_bytes") or 0) if metric_items else 0
    totals["table_size_bytes"] = table_size
    totals["compression_ratio_overall"] = (
        round(totals["raw_size_bytes"] / table_size, 4) if table_size else 0.0
    )
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description="scale 数据正式质量报告（含查询耗时）")
    parser.add_argument("--manifest", default="/var/log/app/manifest.jsonl")
    parser.add_argument("--date", default=None, help="指标日期 YYYY-MM-DD，默认取 manifest 时间戳")
    parser.add_argument("--runs", type=int, default=5, help="每条基准查询重复次数")
    parser.add_argument("--sample-size", type=int, default=50, help="event_id 贯穿抽样数量")
    parser.add_argument("--no-write", action="store_true", help="只计算不写入 data_quality_metrics")
    parser.add_argument("--out", default=None, help="把完整报告 JSON 写入该路径")
    args = parser.parse_args()

    metric_date = date.fromisoformat(args.date) if args.date else None
    storage = ClickHouseStorage()

    metrics = collect_metrics(storage, Path(args.manifest), metric_date)
    if not args.no_write:
        storage.insert_data_quality_metrics(metrics)

    metric_items = [m.model_dump(mode="json") for m in metrics]
    report = {
        "manifest": args.manifest,
        "written_to_table": (not args.no_write),
        "scale_metrics": metric_items,
        "totals": _totals(metric_items),
        "reconciliation": build_reconciliation_report(metrics),
        "event_id_check": verify_manifest_event_ids(
            storage=storage,
            manifest_path=Path(args.manifest),
            sample_size=args.sample_size,
        ),
        "query_latency": benchmark_queries(storage, args.runs),
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
