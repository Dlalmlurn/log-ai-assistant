"""UEBA accuracy evaluation engine.

Compares anomaly-detector output (from ClickHouse) against ground-truth labels
embedded in the generated log lines (``risk_score`` and ``risk_tags`` fields).

Usage (library)::

    from tests.accuracy.evaluator import evaluate

    report = evaluate(raw_log_path="tmp_output/vpn_logs.log",
                      anomaly_rows=clickhouse_anomalies)
    print(report.summary())
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Dimension mapping: generator risk_tag → UEBA dimension
TAG_DIMENSION_MAP = {
    "非工作时间登录": "time",
    "异常IP地址": "ip",
    "境外登录": "geo",
    "大量数据下载": "volume",
    "登录失败": "result",
    "会话时长异常短": "access",
}


@dataclass
class GroundTruth:
    """One labelled log entry extracted from the syslog file."""

    event_time: datetime
    user_id: str
    src_ip: str
    risk_score: int
    risk_tags: list[str]
    line: str = field(repr=False)


@dataclass
class EvalReport:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int
    by_dimension: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 56,
            "  UEBA 准确度评估报告",
            "=" * 56,
            f"  精确率 Precision : {self.precision:.2%}",
            f"  召回率 Recall    : {self.recall:.2%}",
            f"  F1 分数          : {self.f1:.2%}",
            f"  TP={self.tp}  FP={self.fp}  FN={self.fn}  TN={self.tn}",
            "",
        ]
        if self.by_dimension:
            lines.append("  各维度指标:")
            lines.append(f"  {'维度':<12} {'Precision':>8}  {'Recall':>8}  {'F1':>8}  {'TP':>5} {'FP':>5} {'FN':>5}")
            lines.append("  " + "-" * 54)
            for dim, m in sorted(self.by_dimension.items()):
                lines.append(
                    f"  {dim:<12} {m['precision']:>7.1%}  {m['recall']:>7.1%}  {m['f1']:>7.1%}  {m['tp']:>4.0f} {m['fp']:>4.0f} {m['fn']:>4.0f}"
                )
        if self.warnings:
            lines.append("\n  ⚠ 注意事项:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        lines.append("")
        return "\n".join(lines)


def evaluate(
    raw_log_path: str,
    anomaly_rows: list[dict],
    time_window_seconds: int = 120,
) -> EvalReport:
    """Run a full evaluation.

    Args:
        raw_log_path: Path to the syslog-format log file.
        anomaly_rows: List of anomaly dicts from ClickHouse (must include
                      ``user_id``, ``event_time``, ``baseline_deviations``).
        time_window_seconds: Max delta for matching a log to an anomaly
                             (default 120 s).
    """
    truths = _parse_ground_truths(raw_log_path)
    if not truths:
        return EvalReport(precision=0, recall=0, f1=0, tp=0, fp=0, fn=0, tn=0,
                          warnings=["No ground-truth entries parsed from log file"])

    # Partition ground truth
    pos_ids: set[int] = set()  # indices where risk_score > 0
    neg_ids: set[int] = set()  # indices where risk_score == 0
    for i, t in enumerate(truths):
        if t.risk_score > 0:
            pos_ids.add(i)
        else:
            neg_ids.add(i)

    # Build lookup: (user_id, minute_bucket) → set of anomaly rows
    anomaly_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in anomaly_rows:
        user = row.get("user_id", "")
        et = _parse_dt(row.get("event_time"))
        if not user or not et:
            continue
        bucket = et.strftime("%Y%m%d%H%M")
        anomaly_index[(user, bucket)].append(row)

    # Match: for each ground truth, check if anomaly exists within time window
    tp = fp = fn = tn = 0
    dim_tp: dict[str, int] = defaultdict(int)
    dim_fp: dict[str, int] = defaultdict(int)
    dim_fn: dict[str, int] = defaultdict(int)

    for i, t in enumerate(truths):
        is_positive = i in pos_ids
        matched = _find_matching_anomaly(t, anomaly_index, time_window_seconds)

        if is_positive and matched:
            tp += 1
            for dim in _expected_dimensions(t):
                if _has_dimension_deviation(matched, dim):
                    dim_tp[dim] += 1
                else:
                    dim_fn[dim] += 1
        elif is_positive and not matched:
            fn += 1
            for dim in _expected_dimensions(t):
                dim_fn[dim] += 1
        elif not is_positive and matched:
            fp += 1
            for dim in _detected_dimensions(matched):
                dim_fp[dim] += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Per-dimension metrics
    by_dim: dict[str, dict[str, float]] = {}
    all_dims = set(dim_tp) | set(dim_fp) | set(dim_fn)
    for dim in sorted(all_dims):
        d_tp = dim_tp.get(dim, 0)
        d_fp = dim_fp.get(dim, 0)
        d_fn = dim_fn.get(dim, 0)
        p = d_tp / (d_tp + d_fp) if (d_tp + d_fp) > 0 else 0.0
        r = d_tp / (d_tp + d_fn) if (d_tp + d_fn) > 0 else 0.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        by_dim[dim] = {"precision": p, "recall": r, "f1": f, "tp": d_tp, "fp": d_fp, "fn": d_fn}

    warnings: list[str] = []
    if len(pos_ids) == 0:
        warnings.append("无正样本 (所有日志 risk_score=0)，无法评估召回率")
    if len(neg_ids) == 0:
        warnings.append("无负样本，无法评估精确率")

    return EvalReport(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        by_dimension=by_dim,
        warnings=warnings,
    )


# -- internal helpers -----------------------------------------------------------


_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s"
    r".*user=(?P<user>[^\s]+)\s"
    r".*src_ip=(?P<src_ip>[^\s]+)\s"
    r".*risk_score=(?P<risk_score>\d+)"
    r"(?:\s+risk_tags=\"(?P<risk_tags>[^\"]*)\")?"
)


def _parse_ground_truths(path: str) -> list[GroundTruth]:
    truths: list[GroundTruth] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = _LOG_LINE_RE.search(line)
            if not m:
                continue
            try:
                et = datetime.strptime(m["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            risk_tags_str = m.group("risk_tags") or ""
            risk_tags = [t.strip() for t in risk_tags_str.split(",") if t.strip() and t.strip() != "正常"]
            truths.append(
                GroundTruth(
                    event_time=et,
                    user_id=m["user"],
                    src_ip=m["src_ip"],
                    risk_score=int(m["risk_score"]),
                    risk_tags=risk_tags,
                    line=line,
                )
            )
    return truths


def _find_matching_anomaly(
    truth: GroundTruth,
    index: dict[tuple[str, str], list[dict]],
    window_sec: int,
) -> dict | None:
    """Return the first anomaly that matches this ground truth within the time window."""
    from datetime import timedelta

    candidates: list[dict] = []
    half_buckets = int(window_sec / 60) + 1
    for offset_min in range(-half_buckets, half_buckets + 1):
        bucket_ts = truth.event_time + timedelta(minutes=offset_min)
        bucket = bucket_ts.strftime("%Y%m%d%H%M")
        candidates.extend(index.get((truth.user_id, bucket), []))

    # Deduplicate
    seen = set()
    unique: list[dict] = []
    for c in candidates:
        eid = c.get("event_id")
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(c)

    for anom in unique:
        anom_time = _parse_dt(anom.get("event_time"))
        if anom_time and abs((anom_time - truth.event_time).total_seconds()) <= window_sec:
            return anom
    return None


def _expected_dimensions(truth: GroundTruth) -> list[str]:
    """Which UEBA dimensions should fire based on the generator's risk_tags?"""
    dims: list[str] = []
    for tag in truth.risk_tags:
        for prefix, dim in TAG_DIMENSION_MAP.items():
            if tag.startswith(prefix) and dim not in dims:
                dims.append(dim)
    return dims


def _detected_dimensions(anomaly: dict) -> list[str]:
    """Which dimensions are present in an anomaly's baseline_deviations?"""
    devs = anomaly.get("baseline_deviations") or []
    if isinstance(devs, list):
        return list({d.get("dimension", "") for d in devs if isinstance(d, dict) and d.get("dimension")})
    return []


def _has_dimension_deviation(anomaly: dict, dim: str) -> bool:
    return dim in _detected_dimensions(anomaly)


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None
