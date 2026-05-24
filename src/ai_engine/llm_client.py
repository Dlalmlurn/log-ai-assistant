from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.ai_engine.prompts import build_anomaly_judgement_prompt
from src.config import settings
from src.schemas import AIJudgement, AnomalyEvent


class AIAnalyzer:
    def __init__(self):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_model

    @property
    def mock_mode(self) -> bool:
        return not bool(self.api_key)

    def analyze(
        self,
        event: AnomalyEvent,
        baseline: dict[str, Any] | None,
        related_logs: list[dict[str, Any]] | None = None,
        window_stats: dict[str, Any] | None = None,
    ) -> AIJudgement:
        related_logs = related_logs or []
        window_stats = window_stats or {}

        if self.mock_mode:
            result = self._mock_result(event)
        else:
            prompt = build_anomaly_judgement_prompt(
                anomaly=event.model_dump(mode="json"),
                baseline=baseline,
                related_logs=related_logs,
                window_stats=window_stats,
            )
            result = self._call_dashscope(prompt)

        report = {
            "judgement_id": str(uuid.uuid4()),
            "event_id": event.event_id,
            "created_at": datetime.now(timezone.utc),
            "model_name": self.model if not self.mock_mode else "mock-security-analyst",
            "model_version": result.get("model_version"),
            "attack_type": result.get("attack_type", "可疑账号行为"),
            "risk_level": result.get("risk_level", event.risk_level),
            "judgement": result.get("judgement") or result.get("reason", "检测到异常行为组合，需要进一步核查。"),
            "key_reasons": result.get("key_reasons", []),
            "recommended_actions": result.get(
                "recommended_actions",
                result.get("next_steps", ["核查来源IP", "审计相关日志"]),
            ),
            "confidence": float(result.get("confidence", 0.75)),
            "feedback_suggestions": result.get("feedback_suggestions", {}),
            "raw_response": result,
            "is_mock": bool(result.get("is_mock", self.mock_mode or result.get("mode") == "fallback")),
        }
        return AIJudgement.model_validate(report)

    def _mock_result(self, event: AnomalyEvent) -> dict[str, Any]:
        reason = (
            f"事件命中规则: {', '.join(event.rule_hits)}；"
            f"用户={event.user_id or 'unknown'}，IP={event.src_ip or 'unknown'}，风险等级={event.risk_level}。"
        )
        return {
            "attack_type": "账号接管或疑似数据窃取",
            "risk_level": event.risk_level,
            "judgement": reason,
            "key_reasons": event.reason_codes or event.rule_hits,
            "recommended_actions": ["核查IP归属", "检查账号凭证泄露风险", "审计导出接口访问记录"],
            "confidence": 0.82,
            "feedback_suggestions": {},
            "is_mock": True,
        }

    def _call_dashscope(self, prompt: str) -> dict[str, Any]:
        try:
            from dashscope import Generation

            resp = Generation.call(
                api_key=self.api_key,
                model=self.model,
                prompt=prompt,
                result_format="message",
            )
            content = self._extract_content(resp)
            return self._extract_json(content)
        except Exception as exc:
            return {
                "attack_type": "模型调用失败，回退mock",
                "risk_level": "medium",
                "judgement": f"DashScope 调用失败: {exc}",
                "key_reasons": ["model_call_failed"],
                "recommended_actions": ["检查 API Key", "重试调用"],
                "confidence": 0.3,
                "feedback_suggestions": {},
                "is_mock": True,
                "mode": "fallback",
            }

    @staticmethod
    def _extract_content(resp: Any) -> str:
        try:
            output = getattr(resp, "output", None) or resp.get("output", {})
            choices = output.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            text = output.get("text")
            if text:
                return text
        except Exception:
            pass
        return str(resp)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
