from __future__ import annotations

import json
from typing import Any


def build_alert_analysis_prompt(
    alert: dict[str, Any],
    baseline: dict[str, Any] | None,
    related_logs: list[dict[str, Any]],
    window_stats: dict[str, Any],
) -> str:
    payload = {
        "alert_event": alert,
        "baseline": baseline or {},
        "related_logs_summary": related_logs[:20],
        "window_stats": window_stats,
    }
    return (
        "你是企业安全分析助手。你必须基于输入的结构化上下文输出严格 JSON，不能输出额外文本。\n"
        "输出字段必须包含: attack_type, risk_level, reason, suggestion, confidence, next_steps。\n"
        "risk_level 只能是: 低, 中, 高。confidence 是 0-1 浮点数。\n"
        "输入上下文如下:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
