#!/usr/bin/env python3
"""UEBA accuracy test runner.

Generates deterministic logs, runs the anomaly scorer/rule-engine directly
(no Kafka), and evaluates detection accuracy against embedded ground-truth labels.

Can be called from CLI or imported as ``run_accuracy_test()`` for API use.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Dimension mapping: generator risk_tag → UEBA dimension
TAG_DIMENSION_MAP = {
    "非工作时间登录": "time",
    "异常IP地址": "ip",
    "境外登录": "geo",
    "大量数据下载": "volume",
    "登录失败": "result",
    "会话时长异常短": "access",
}


def run_accuracy_test(
    *,
    seed: int = 42,
    days: int = 3,
    count: int = 100,
    start_date: str | None = None,
    **_: Any,  # accept deprecated kwargs silently
) -> dict[str, Any]:
    """Run accuracy test directly against the UEBA scorer and return a JSON result."""

    if start_date is None:
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # 1. Generate deterministic logs
    normalised_logs = _generate_and_parse(seed=seed, days=days, count=count, start=start_date)

    # 2. Run RuleEngine + UebaScorer directly on each log
    from src.detection.rules import RuleEngine
    from src.storage import ClickHouseStorage
    from src.ueba.scorer import UebaScorer

    storage = ClickHouseStorage()
    rule_engine = RuleEngine()
    scorer = UebaScorer(storage)

    # Per-dimension tracking
    dim_tp: dict[str, int] = defaultdict(int)
    dim_fp: dict[str, int] = defaultdict(int)
    dim_fn: dict[str, int] = defaultdict(int)
    tp = fp = fn = tn = 0
    total_gt_pos = 0
    total_gt_neg = 0

    for log, gt_risk_score, gt_risk_tags in normalised_logs:
        is_gt_positive = gt_risk_score > 0
        if is_gt_positive:
            total_gt_pos += 1
        else:
            total_gt_neg += 1

        # Run detection
        try:
            rule_alerts = rule_engine.evaluate_log(log)
            ueba_alerts = scorer.evaluate_log(log)
        except Exception:
            rule_alerts = []
            ueba_alerts = []

        all_alerts = list(rule_alerts) + list(ueba_alerts)
        is_pred_positive = len(all_alerts) > 0

        # Collect detected dimensions
        detected_dims: set[str] = set()
        for alert in all_alerts:
            for dev in alert.baseline_deviations:
                d = dev.get("dimension", "") if isinstance(dev, dict) else getattr(dev, "dimension", "")
                if d:
                    detected_dims.add(d)

        expected_dims = _expected_dimensions(gt_risk_tags)

        if is_gt_positive and is_pred_positive:
            tp += 1
            for dim in expected_dims:
                if dim in detected_dims:
                    dim_tp[dim] += 1
                else:
                    dim_fn[dim] += 1
        elif is_gt_positive and not is_pred_positive:
            fn += 1
            for dim in expected_dims:
                dim_fn[dim] += 1
        elif not is_gt_positive and is_pred_positive:
            fp += 1
            for dim in detected_dims:
                dim_fp[dim] += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    by_dim: dict[str, Any] = {}
    all_dims = set(dim_tp) | set(dim_fp) | set(dim_fn)
    for dim in sorted(all_dims):
        d_tp = dim_tp.get(dim, 0)
        d_fp = dim_fp.get(dim, 0)
        d_fn = dim_fn.get(dim, 0)
        p = d_tp / (d_tp + d_fp) if (d_tp + d_fp) > 0 else 0.0
        r = d_tp / (d_tp + d_fn) if (d_tp + d_fn) > 0 else 0.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        by_dim[dim] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
                       "tp": d_tp, "fp": d_fp, "fn": d_fn}

    warnings: list[str] = []
    if total_gt_pos == 0:
        warnings.append("无正样本 (所有日志 risk_score=0)，无法评估召回率")
    if total_gt_neg == 0:
        warnings.append("无负样本，无法评估精确率")

    return {
        "seed": seed,
        "days": days,
        "count_per_day": count,
        "logs_generated": len(normalised_logs),
        "logs_sent": len(normalised_logs),
        "anomalies_found": 0,  # no longer from ClickHouse; kept for API compat
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "by_dimension": by_dim,
        "warnings": warnings,
    }


def _expected_dimensions(risk_tags: list[str]) -> set[str]:
    dims: set[str] = set()
    for tag in risk_tags:
        for prefix, dim in TAG_DIMENSION_MAP.items():
            if tag.startswith(prefix):
                dims.add(dim)
    return dims


# -- internal helpers -----------------------------------------------------------


def _generate_and_parse(
    seed: int, days: int, count: int, start: str
) -> list[tuple[Any, int, list[str]]]:
    """Generate deterministic logs and parse them to NormalizedLog objects.

    Returns list of (NormalizedLog, risk_score, risk_tags).
    """
    import random as _random_mod

    log_gen_dir = str(PROJECT_ROOT / "log-generator")
    if log_gen_dir not in sys.path:
        sys.path.insert(0, log_gen_dir)

    from gen_vpn_logs import generate_logs, to_syslog, VPNLogEntry  # type: ignore[import-untyped]
    from src.parser.log_parser import normalize_raw_record

    _random_mod.seed(seed)

    start_dt = datetime.strptime(start, "%Y-%m-%d")
    logs: list[VPNLogEntry] = generate_logs(start_dt, days=days, normal_per_day=count)

    import tempfile
    fd, path = tempfile.mkstemp(suffix=".log", prefix="ueba_test_")
    os.close(fd)
    to_syslog(logs, path)

    results: list[tuple[Any, int, list[str]]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = normalize_raw_record(line, source_type_hint="vpn")
                # Extract ground truth from the log entry
                gt_score = 0
                gt_tags: list[str] = []
                for entry in logs:
                    if entry.username == parsed.user_id and str(entry.timestamp) in line:
                        gt_score = entry.risk_score
                        gt_tags = [t.strip() for t in entry.risk_tags.split(",") if t.strip() and t.strip() != "正常"]
                        break
                results.append((parsed, gt_score, gt_tags))
            except Exception:
                continue

    try:
        os.unlink(path)
    except OSError:
        pass

    return results


# -- CLI ------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()
    result = run_accuracy_test(
        seed=args.seed,
        days=args.days,
        count=args.count,
        start_date=args.start,
    )

    print("=" * 56)
    print("  UEBA 准确度测试报告 (直接评估模式)")
    print(f"  种子={result['seed']}  天数={result['days']}  每日日志={result['count_per_day']}")
    print("=" * 56)
    print(f"  评估日志   : {result['logs_generated']} 条")
    print(f"  Precision  : {result['precision']:.2%}")
    print(f"  Recall     : {result['recall']:.2%}")
    print(f"  F1         : {result['f1']:.2%}")
    print(f"  TP={result['tp']}  FP={result['fp']}  FN={result['fn']}  TN={result['tn']}")
    print()

    if result["by_dimension"]:
        print("  各维度:")
        for dim, m in sorted(result["by_dimension"].items()):
            p = m.get("precision", 0)
            r = m.get("recall", 0)
            f = m.get("f1", 0)
            print(f"    {dim:<10} P={p:.1%}  R={r:.1%}  F1={f:.1%}")

    for w in result["warnings"]:
        print(f"  ⚠  {w}")

    if result["f1"] < args.min_f1:
        print(f"\n  F1={result['f1']:.2%} < {args.min_f1:.0%}，未通过。")
        sys.exit(1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UEBA accuracy test runner")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--start", default=None)
    p.add_argument("--min-f1", type=float, default=0.0)
    return p.parse_args()


if __name__ == "__main__":
    main()
