#!/usr/bin/env python3
"""攻击场景端到端可追踪性校验。

依据 docs/10「每个关键场景都能从原始日志追踪到异常事件和页面结果」与 docs/09 的
attack_chain_id 贯穿约定，按场景统计每条攻击链是否能逐段追踪:

    manifest(injected_label) -> security_logs -> anomaly_events -> AI 研判 / 页面

判定口径:
  - in_security_logs : attack_chain_id 在 security_logs 可查（event_id 贯穿成功）。
  - has_anomaly      : 该链产出了 anomaly_events。
  - high_or_critical : 该链产出了 high/critical 异常（AI 研判候选）。
  - has_ai           : 该链的某条异常已有 ai_judgements 记录。
  - 注：AI 仅研判 high/critical（docs/07），medium 止步于异常事件属预期，不计为缺口。

在能访问 ClickHouse 的环境运行（推荐后端容器内）:
    docker exec log-ai-backend python -m scripts.verify_traceability --max-chains 80
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.storage import ClickHouseStorage


def _load_label_chains(manifest_path: Path) -> dict[str, list[str]]:
    label_chains: dict[str, set[str]] = defaultdict(set)
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            label = str(row.get("injected_label") or "")
            chain = str(row.get("attack_chain_id") or "")
            if label.startswith("attack_") and chain:
                label_chains[label].add(chain)
    return {label: sorted(chains) for label, chains in sorted(label_chains.items())}


def _chains_present(storage: ClickHouseStorage, table: str, chains: list[str], where: str = "") -> set[str]:
    if not chains:
        return set()
    sql = f"SELECT DISTINCT attack_chain_id FROM {table} WHERE attack_chain_id IN {{chains:Array(String)}}"
    if where:
        sql += f" AND {where}"
    rows = storage.query(sql, {"chains": chains})
    return {str(r[0]) for r in rows if r and r[0]}


def _chains_with_ai(storage: ClickHouseStorage, chains: list[str]) -> set[str]:
    if not chains:
        return set()
    sql = (
        "SELECT DISTINCT a.attack_chain_id "
        "FROM anomaly_events a "
        "INNER JOIN ai_judgements j ON j.event_id = a.event_id "
        "WHERE a.attack_chain_id IN {chains:Array(String)}"
    )
    rows = storage.query(sql, {"chains": chains})
    return {str(r[0]) for r in rows if r and r[0]}


def verify(manifest_path: Path, max_chains: int) -> dict[str, Any]:
    label_chains = _load_label_chains(manifest_path)
    storage = ClickHouseStorage()
    report: list[dict[str, Any]] = []

    for label, all_chains in label_chains.items():
        chains = all_chains[-max_chains:] if max_chains > 0 else all_chains
        in_sl = _chains_present(storage, "security_logs", chains)
        in_anom = _chains_present(storage, "anomaly_events", chains)
        in_hc = _chains_present(
            storage, "anomaly_events", chains, where="risk_level IN ('high','critical')"
        )
        in_ai = _chains_with_ai(storage, chains)
        report.append(
            {
                "scenario": label.replace("attack_", ""),
                "chains_sampled": len(chains),
                "in_security_logs": len(in_sl),
                "has_anomaly": len(in_anom),
                "high_or_critical": len(in_hc),
                "has_ai": len(in_ai),
                "traceable_to_anomaly": bool(in_anom),
                "traceable_to_ai": bool(in_ai),
            }
        )

    return {"manifest": str(manifest_path), "scenarios": report}


def _print_table(report: dict[str, Any]) -> None:
    header = f"{'scenario':<24}{'sampled':>8}{'in_sec':>8}{'anomaly':>8}{'high/crit':>10}{'ai':>5}"
    print(header)
    print("-" * len(header))
    for s in report["scenarios"]:
        print(
            f"{s['scenario']:<24}{s['chains_sampled']:>8}{s['in_security_logs']:>8}"
            f"{s['has_anomaly']:>8}{s['high_or_critical']:>10}{s['has_ai']:>5}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="攻击场景端到端可追踪性校验")
    parser.add_argument("--manifest", default="/var/log/app/manifest.jsonl")
    parser.add_argument("--max-chains", type=int, default=80, help="每个场景最多抽样多少条链")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args()

    report = verify(Path(args.manifest), args.max_chains)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
