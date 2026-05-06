from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.ai_engine.prompts import build_alert_analysis_prompt
from src.config import settings
from src.schemas import AIReport, AlertEvent


class AIAnalyzer:
    def __init__(self):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_model

    @property
    def mock_mode(self) -> bool:
        return not bool(self.api_key)

    def analyze(
        self,
        alert: AlertEvent,
        baseline: dict[str, Any] | None,
        related_logs: list[dict[str, Any]] | None = None,
        window_stats: dict[str, Any] | None = None,
    ) -> AIReport:
        related_logs = related_logs or []
        window_stats = window_stats or {}

        if self.mock_mode:
            result = self._mock_result(alert)
        else:
            prompt = build_alert_analysis_prompt(
                alert=alert.model_dump(mode="json"),
                baseline=baseline,
                related_logs=related_logs,
                window_stats=window_stats,
            )
            result = self._call_dashscope(prompt)

        report = {
            "ai_report_id": str(uuid.uuid4()),
            "alert_id": alert.alert_id,
            "created_at": datetime.now(timezone.utc),
            "attack_type": result.get("attack_type", "可疑账号行为"),
            "risk_level": result.get("risk_level", alert.risk_level),
            "reason": result.get("reason", "检测到异常行为组合，需要进一步核查。"),
            "suggestion": result.get("suggestion", "请核查账号和来源IP，并审计相关资源访问。"),
            "confidence": float(result.get("confidence", 0.75)),
            "next_steps": result.get("next_steps", ["核查来源IP", "审计相关日志"]),
            "raw_response": result,
        }
        return AIReport.model_validate(report)

    def _mock_result(self, alert: AlertEvent) -> dict[str, Any]:
        reason = (
            f"事件命中规则: {', '.join(alert.rule_hits)}；"
            f"用户={alert.username or 'unknown'}，IP={alert.src_ip or 'unknown'}，风险等级={alert.risk_level}。"
        )
        return {
            "attack_type": "账号接管或疑似数据窃取",
            "risk_level": alert.risk_level,
            "reason": reason,
            "suggestion": "建议临时限制账号高危操作，核查登录来源并回溯相关访问行为。",
            "confidence": 0.82,
            "next_steps": ["核查IP归属", "检查账号凭证泄露风险", "审计导出接口访问记录"],
            "mode": "mock",
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
                "risk_level": "中",
                "reason": f"DashScope 调用失败: {exc}",
                "suggestion": "请检查 DASHSCOPE_API_KEY 与网络连通性。",
                "confidence": 0.3,
                "next_steps": ["检查 API Key", "重试调用"],
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
