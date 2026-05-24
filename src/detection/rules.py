from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque

from src.config import settings
from src.schemas import AnomalyEvent, NormalizedLog

SENSITIVE_KEYWORDS = ("export", "download", "admin", "/admin", "sensitive", "config", "backup")
WINDOW_1M = timedelta(minutes=1)
WINDOW_5M = timedelta(minutes=5)
WINDOW_10M = timedelta(minutes=10)


def _risk_score(level: str) -> int:
    return {"low": 30, "medium": 60, "high": 90, "critical": 100}.get(level, 30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_sensitive(resource: str | None) -> bool:
    if not resource:
        return False
    lowered = resource.lower()
    return any(k in lowered for k in SENSITIVE_KEYWORDS)


class RuleEngine:
    def __init__(self):
        self.ip_failed_logins: dict[str, Deque[datetime]] = defaultdict(deque)
        self.user_failed_logins: dict[str, Deque[datetime]] = defaultdict(deque)
        self.ip_failed_users: dict[str, Deque[tuple[datetime, str]]] = defaultdict(deque)
        self.user_api_calls: dict[str, Deque[datetime]] = defaultdict(deque)
        self.user_sensitive_access: dict[str, Deque[datetime]] = defaultdict(deque)
        self.known_login_ips: dict[str, set[str]] = defaultdict(set)
        self.new_ip_login_events: dict[str, Deque[tuple[datetime, str, str]]] = defaultdict(deque)

    def evaluate_log(self, log: NormalizedLog) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []
        ts = log.event_time

        if log.action == "login" and log.result == "fail":
            anomalies.extend(self._handle_login_failed(log, ts))

        if log.action == "login" and log.result == "success":
            anomalies.extend(self._handle_login_success(log, ts))

        if log.action == "api_call":
            anomalies.extend(self._handle_api_call(log, ts))

        if _is_sensitive(log.resource):
            anomalies.extend(self._handle_sensitive_access(log, ts))

        if log.user_id and log.user_id != "admin" and log.resource and "admin" in log.resource.lower():
            anomalies.append(
                self._build_anomaly(
                    log,
                    risk_level="high",
                    rule="普通用户访问admin接口",
                    reason_codes=["admin_resource_access"],
                    evidence={"resource": log.resource, "user_id": log.user_id},
                )
            )

        if log.source_type == "system":
            msg = (log.message or "").lower()
            if log.result == "error" or "error" in msg or "critical" in msg:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="medium",
                        rule="系统日志出现error或critical",
                        reason_codes=["system_error_pattern"],
                        evidence={"message": log.message, "result": log.result},
                    )
                )

        return anomalies

    def _handle_login_failed(self, log: NormalizedLog, ts: datetime) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []

        if log.src_ip:
            q = self.ip_failed_logins[log.src_ip]
            q.append(ts)
            self._trim_times(q, ts - WINDOW_5M)
            if len(q) >= settings.threshold_ip_fail_5m:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="high",
                        rule="同一src_ip在5分钟内登录失败超阈值",
                        reason_codes=["failed_login_spike"],
                        evidence={"src_ip": log.src_ip, "failed_count_5m": len(q)},
                    )
                )

        if log.user_id:
            uq = self.user_failed_logins[log.user_id]
            uq.append(ts)
            self._trim_times(uq, ts - WINDOW_5M)
            if len(uq) >= settings.threshold_user_fail_5m:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="medium",
                        rule="同一user_id在5分钟内登录失败超阈值",
                        reason_codes=["failed_login_spike"],
                        evidence={"user_id": log.user_id, "failed_count_5m": len(uq)},
                    )
                )

        if log.src_ip and log.user_id:
            fq = self.ip_failed_users[log.src_ip]
            fq.append((ts, log.user_id))
            self._trim_pairs(fq, ts - WINDOW_5M)
            unique_users = {user for _, user in fq}
            if len(unique_users) >= settings.threshold_multi_user_fail_ip_5m:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="high",
                        rule="同一IP多用户登录失败",
                        reason_codes=["credential_stuffing_pattern"],
                        evidence={
                            "src_ip": log.src_ip,
                            "distinct_users_5m": sorted(unique_users),
                            "count": len(unique_users),
                        },
                    )
                )

        return anomalies

    def _handle_login_success(self, log: NormalizedLog, ts: datetime) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []
        if log.user_id and log.src_ip:
            known = self.known_login_ips[log.user_id]
            if log.src_ip not in known:
                known.add(log.src_ip)
                self.new_ip_login_events[log.user_id].append((ts, log.src_ip, log.event_id))
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="medium",
                        rule="新IP登录",
                        reason_codes=["new_source_ip"],
                        evidence={"user_id": log.user_id, "new_ip": log.src_ip},
                    )
                )

        if ts.hour < settings.work_hour_start or ts.hour >= settings.work_hour_end:
            anomalies.append(
                self._build_anomaly(
                    log,
                    risk_level="low",
                    rule="非工作时间登录",
                    reason_codes=["rare_login_hour"],
                    evidence={"event_hour": ts.hour, "work_hours": f"{settings.work_hour_start}:00-{settings.work_hour_end}:00"},
                )
            )
        return anomalies

    def _handle_api_call(self, log: NormalizedLog, ts: datetime) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []
        if not log.user_id:
            return anomalies

        q = self.user_api_calls[log.user_id]
        q.append(ts)
        self._trim_times(q, ts - WINDOW_1M)
        if len(q) >= settings.threshold_api_call_1m:
            anomalies.append(
                self._build_anomaly(
                    log,
                    risk_level="medium",
                    rule="同一user_id在1分钟内API调用超阈值",
                    reason_codes=["high_api_rate"],
                    evidence={"user_id": log.user_id, "api_calls_1m": len(q)},
                )
            )
        return anomalies

    def _handle_sensitive_access(self, log: NormalizedLog, ts: datetime) -> list[AnomalyEvent]:
        anomalies: list[AnomalyEvent] = []
        if not log.user_id:
            return anomalies

        q = self.user_sensitive_access[log.user_id]
        q.append(ts)
        self._trim_times(q, ts - WINDOW_5M)
        if len(q) >= settings.threshold_sensitive_5m:
            anomalies.append(
                self._build_anomaly(
                    log,
                    risk_level="medium",
                    rule="同一user_id在5分钟内敏感资源访问超阈值",
                    reason_codes=["sensitive_resource_access"],
                    evidence={"user_id": log.user_id, "sensitive_count_5m": len(q), "resource": log.resource},
                )
            )

        new_ip_events = self.new_ip_login_events.get(log.user_id, deque())
        self._trim_new_ip_events(new_ip_events, ts - WINDOW_10M)
        if new_ip_events:
            recent = [e for e in new_ip_events if e[1] == log.src_ip or log.src_ip is None]
            if recent:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        risk_level="high",
                        rule="新IP登录后短时间访问敏感资源",
                        reason_codes=["new_source_then_sensitive_access", "sensitive_resource_access"],
                        evidence={"user_id": log.user_id, "src_ip": log.src_ip, "resource": log.resource},
                        related_event_ids=[item[2] for item in recent],
                    )
                )
                if log.resource and any(k in log.resource.lower() for k in ("export", "download")):
                    anomalies.append(
                        self._build_anomaly(
                            log,
                            risk_level="high",
                            rule="新IP登录后短时间大量调用导出接口",
                            reason_codes=["new_source_then_sensitive_access", "download_volume_spike"],
                            evidence={"user_id": log.user_id, "resource": log.resource, "src_ip": log.src_ip},
                            related_event_ids=[item[2] for item in recent],
                        )
                    )

        return anomalies

    @staticmethod
    def _trim_times(items: Deque[datetime], min_time: datetime) -> None:
        while items and items[0] < min_time:
            items.popleft()

    @staticmethod
    def _trim_pairs(items: Deque[tuple[datetime, str]], min_time: datetime) -> None:
        while items and items[0][0] < min_time:
            items.popleft()

    @staticmethod
    def _trim_new_ip_events(items: Deque[tuple[datetime, str, str]], min_time: datetime) -> None:
        while items and items[0][0] < min_time:
            items.popleft()

    def _build_anomaly(
        self,
        log: NormalizedLog,
        risk_level: str,
        rule: str,
        reason_codes: list[str],
        evidence: dict,
        related_event_ids: list[str] | None = None,
    ) -> AnomalyEvent:
        related_ids = related_event_ids or []
        summary = (
            f"user={log.user_id or 'unknown'} src_ip={log.src_ip or 'unknown'} "
            f"action={log.action} result={log.result} resource={log.resource or '-'}"
        )
        risk_score = _risk_score(risk_level)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_time": log.event_time,
            "detect_time": _now(),
            "tenant_id": log.tenant_id,
            "user_id": log.user_id,
            "src_ip": log.src_ip,
            "host": log.host,
            "source_type": log.source_type,
            "action": log.action,
            "object_type": log.object_type,
            "object_id": log.object_id,
            "attack_type": None,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_components": {"rule_score": risk_score},
            "rule_hits": [rule],
            "baseline_deviations": [],
            "reason_codes": reason_codes,
            "evidence": evidence,
            "related_event_ids": [log.event_id] + related_ids,
            "related_logs_summary": summary,
            "scenario_id": log.scenario_id,
            "scenario_type": log.scenario_type,
            "attack_chain_id": log.attack_chain_id,
            "ai_status": "pending" if risk_level in {"high", "critical"} else "not_required",
            "status": "new",
            "created_at": _now(),
        }
        return AnomalyEvent.model_validate(payload)


def detect_batch(logs: list[NormalizedLog], engine: RuleEngine | None = None) -> list[AnomalyEvent]:
    engine = engine or RuleEngine()
    anomalies: list[AnomalyEvent] = []
    for log in sorted(logs, key=lambda x: x.event_time):
        anomalies.extend(engine.evaluate_log(log))
    return anomalies
