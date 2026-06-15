"""AI 提示词构造测试。"""

from datetime import date, datetime

from src.ai_engine.prompts import build_anomaly_judgement_prompt


def test_prompt_serializes_date_in_baseline_without_error() -> None:
    """真实研判路径会把 baseline(含 baseline_date 等 date/datetime) json.dumps 进提示词。

    回归：date/datetime 不可被默认 json 序列化，必须用 default=str 兜底，否则真实
    DashScope 研判会在构造提示词时抛 TypeError（mock 模式不构造提示词，掩盖了该缺陷）。
    """
    baseline = {
        "user_id": "li.fang",
        "baseline_date": date(2026, 6, 2),
        "updated_at": datetime(2026, 6, 2, 3, 4, 5),
        "sample_days": 30,
    }
    prompt = build_anomaly_judgement_prompt(
        anomaly={"event_id": "anom-1", "risk_level": "critical"},
        baseline=baseline,
        related_logs=[],
        window_stats={"failed_login_count_5m": 3},
    )
    assert "2026-06-02" in prompt
    assert "li.fang" in prompt
