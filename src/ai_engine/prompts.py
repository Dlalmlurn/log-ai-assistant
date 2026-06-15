from __future__ import annotations

import json
from typing import Any


def build_anomaly_judgement_prompt(
    anomaly: dict[str, Any],
    baseline: dict[str, Any] | None,
    related_logs: list[dict[str, Any]],
    window_stats: dict[str, Any],
) -> str:
    payload = {
        "anomaly_event": anomaly,
        "baseline": baseline or {},
        "related_logs_summary": related_logs[:20],
        "window_stats": window_stats,
    }
    return (
        "你是企业安全分析助手。你必须基于输入的结构化上下文输出严格 JSON，不能输出额外文本。\n"
        "输出字段必须包含: attack_type, risk_level, judgement, key_reasons, recommended_actions, confidence。\n"
        "risk_level 只能是: low, medium, high, critical。confidence 是 0-1 浮点数。\n"
        "输入上下文如下:\n"
        # baseline/related_logs 可能包含 date、datetime 等非原生 JSON 类型（如 baseline_date），
        # 用 default=str 兜底序列化，避免真实研判时 json.dumps 抛 TypeError。
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
