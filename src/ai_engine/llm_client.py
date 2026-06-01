from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.ai_engine.prompts import build_anomaly_judgement_prompt
from src.config import settings
from src.schemas import AIJudgement, AnomalyEvent

logger = logging.getLogger(__name__)


class AIAnalyzer:
    def __init__(self):
        self.deepseek_key = settings.deepseek_api_key
        self.deepseek_model = settings.deepseek_model
        self.deepseek_base = settings.deepseek_base_url
        self.dashscope_key = settings.dashscope_api_key
        self.dashscope_model = settings.dashscope_model

    @property
    def mock_mode(self) -> bool:
        return not (bool(self.deepseek_key) or bool(self.dashscope_key))

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
            result = self._call_llm(prompt)

        report = {
            "judgement_id": str(uuid.uuid4()),
            "event_id": event.event_id,
            "created_at": datetime.now(timezone.utc),
            "model_name": self._active_model(),
            "model_version": result.get("model_version"),
            "attack_type": result.get("attack_type", "可疑行为"),
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

    def _active_model(self) -> str:
        if self.deepseek_key:
            return self.deepseek_model
        if self.dashscope_key:
            return self.dashscope_model
        return "mock-security-analyst"

    # -- LLM dispatch ---------------------------------------------------------

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        if self.deepseek_key:
            return self._call_deepseek(prompt)
        if self.dashscope_key:
            return self._call_dashscope(prompt)
        return {"mode": "fallback", "is_mock": True}

    # -- DeepSeek (OpenAI-compatible API) ------------------------------------

    def _call_deepseek(self, prompt: str) -> dict[str, Any]:
        from openai import OpenAI

        last_error: str | None = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                client = OpenAI(
                    api_key=self.deepseek_key,
                    base_url=self.deepseek_base,
                )
                resp = client.chat.completions.create(
                    model=self.deepseek_model,
                    messages=[
                        {"role": "system", "content": "你是企业安全分析助手。必须输出严格 JSON，不能输出额外文本。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                )
                content = resp.choices[0].message.content or ""
                return self._extract_json(content)
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 1.5  # 1.5, 3, 6, 12 s
                    logger.warning(
                        "DeepSeek attempt %d/%d failed: %s — retry in %.1fs",
                        attempt + 1, max_retries, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("DeepSeek exhausted %d retries: %s", max_retries, exc)

        # Fallback to DashScope if available
        if self.dashscope_key:
            return self._call_dashscope(prompt)
        # Raise to let caller decide (keep pending for later retry)
        raise RuntimeError(f"DeepSeek API unreachable after {max_retries} retries: {last_error}")

    # -- DashScope (fallback) ------------------------------------------------

    def _call_dashscope(self, prompt: str) -> dict[str, Any]:
        last_error: str | None = None
        max_retries = 5
        for attempt in range(max_retries):
            try:
                from dashscope import Generation

                resp = Generation.call(
                    api_key=self.dashscope_key,
                    model=self.dashscope_model,
                    prompt=prompt,
                    result_format="message",
                )
                content = self._extract_content(resp)
                return self._extract_json(content)
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 1.5
                    logger.warning(
                        "DashScope attempt %d/%d failed: %s — retry in %.1fs",
                        attempt + 1, max_retries, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("DashScope exhausted %d retries: %s", max_retries, exc)

        raise RuntimeError(f"All AI APIs unreachable after {max_retries} retries: {last_error}")

    # -- mock -----------------------------------------------------------------

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
            "is_mock": True,
        }

    # -- helpers -------------------------------------------------------------

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
