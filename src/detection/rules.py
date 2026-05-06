from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque

from src.config import settings
from src.schemas import AlertEvent, NormalizedLog

SENSITIVE_KEYWORDS = ("export", "download", "admin", "/admin", "sensitive", "config", "backup")
WINDOW_1M = timedelta(minutes=1)
WINDOW_5M = timedelta(minutes=5)
WINDOW_10M = timedelta(minutes=10)


def _risk_score(level: str) -> int:
    return {"低": 30, "中": 60, "高": 90}.get(level, 30)


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

    def evaluate_log(self, log: NormalizedLog) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        ts = log.event_time

        if log.action == "login" and log.status == "failed":
            alerts.extend(self._handle_login_failed(log, ts))

        if log.action == "login" and log.status == "success":
            alerts.extend(self._handle_login_success(log, ts))

        if log.action == "api_call":
            alerts.extend(self._handle_api_call(log, ts))

        if _is_sensitive(log.resource):
            alerts.extend(self._handle_sensitive_access(log, ts))

        if log.username and log.username != "admin" and log.resource and "admin" in log.resource.lower():
            alerts.append(
                self._build_alert(
                    log,
                    risk_level="高",
                    rule="普通用户访问admin接口",
                    evidence={"resource": log.resource, "username": log.username},
                )
            )

        if log.source_type == "system":
            msg = (log.message or "").lower()
            if log.status == "error" or "error" in msg or "critical" in msg:
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="中",
                        rule="系统日志出现error或critical",
                        evidence={"message": log.message, "status": log.status},
                    )
                )

        return alerts

    def _handle_login_failed(self, log: NormalizedLog, ts: datetime) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []

        if log.src_ip:
            q = self.ip_failed_logins[log.src_ip]
            q.append(ts)
            self._trim_times(q, ts - WINDOW_5M)
            if len(q) >= settings.threshold_ip_fail_5m:
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="高",
                        rule="同一src_ip在5分钟内登录失败超阈值",
                        evidence={"src_ip": log.src_ip, "failed_count_5m": len(q)},
                    )
                )

        if log.username:
            uq = self.user_failed_logins[log.username]
            uq.append(ts)
            self._trim_times(uq, ts - WINDOW_5M)
            if len(uq) >= settings.threshold_user_fail_5m:
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="中",
                        rule="同一username在5分钟内登录失败超阈值",
                        evidence={"username": log.username, "failed_count_5m": len(uq)},
                    )
                )

        if log.src_ip and log.username:
            fq = self.ip_failed_users[log.src_ip]
            fq.append((ts, log.username))
            self._trim_pairs(fq, ts - WINDOW_5M)
            unique_users = {user for _, user in fq}
            if len(unique_users) >= settings.threshold_multi_user_fail_ip_5m:
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="高",
                        rule="同一IP多用户登录失败",
                        evidence={
                            "src_ip": log.src_ip,
                            "distinct_users_5m": sorted(unique_users),
                            "count": len(unique_users),
                        },
                    )
                )

        return alerts

    def _handle_login_success(self, log: NormalizedLog, ts: datetime) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        if log.username and log.src_ip:
            known = self.known_login_ips[log.username]
            if log.src_ip not in known:
                known.add(log.src_ip)
                self.new_ip_login_events[log.username].append((ts, log.src_ip, log.event_id))
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="中",
                        rule="新IP登录",
                        evidence={"username": log.username, "new_ip": log.src_ip},
                    )
                )

        if ts.hour < settings.work_hour_start or ts.hour >= settings.work_hour_end:
            alerts.append(
                self._build_alert(
                    log,
                    risk_level="低",
                    rule="非工作时间登录",
                    evidence={"event_hour": ts.hour, "work_hours": f"{settings.work_hour_start}:00-{settings.work_hour_end}:00"},
                )
            )
        return alerts

    def _handle_api_call(self, log: NormalizedLog, ts: datetime) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        if not log.username:
            return alerts

        q = self.user_api_calls[log.username]
        q.append(ts)
        self._trim_times(q, ts - WINDOW_1M)
        if len(q) >= settings.threshold_api_call_1m:
            alerts.append(
                self._build_alert(
                    log,
                    risk_level="中",
                    rule="同一username在1分钟内API调用超阈值",
                    evidence={"username": log.username, "api_calls_1m": len(q)},
                )
            )
        return alerts

    def _handle_sensitive_access(self, log: NormalizedLog, ts: datetime) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        if not log.username:
            return alerts

        q = self.user_sensitive_access[log.username]
        q.append(ts)
        self._trim_times(q, ts - WINDOW_5M)
        if len(q) >= settings.threshold_sensitive_5m:
            alerts.append(
                self._build_alert(
                    log,
                    risk_level="中",
                    rule="同一username在5分钟内敏感资源访问超阈值",
                    evidence={"username": log.username, "sensitive_count_5m": len(q), "resource": log.resource},
                )
            )

        new_ip_events = self.new_ip_login_events.get(log.username, deque())
        self._trim_new_ip_events(new_ip_events, ts - WINDOW_10M)
        if new_ip_events:
            recent = [e for e in new_ip_events if e[1] == log.src_ip or log.src_ip is None]
            if recent:
                alerts.append(
                    self._build_alert(
                        log,
                        risk_level="高",
                        rule="新IP登录后短时间访问敏感资源",
                        evidence={"username": log.username, "src_ip": log.src_ip, "resource": log.resource},
                        related_event_ids=[item[2] for item in recent],
                    )
                )
                if log.resource and any(k in log.resource.lower() for k in ("export", "download")):
                    alerts.append(
                        self._build_alert(
                            log,
                            risk_level="高",
                            rule="新IP登录后短时间大量调用导出接口",
                            evidence={"username": log.username, "resource": log.resource, "src_ip": log.src_ip},
                            related_event_ids=[item[2] for item in recent],
                        )
                    )

        return alerts

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

    def _build_alert(
        self,
        log: NormalizedLog,
        risk_level: str,
        rule: str,
        evidence: dict,
        related_event_ids: list[str] | None = None,
    ) -> AlertEvent:
        related_ids = related_event_ids or []
        summary = (
            f"user={log.username or 'unknown'} src_ip={log.src_ip or 'unknown'} "
            f"action={log.action} status={log.status} resource={log.resource or '-'}"
        )
        payload = {
            "alert_id": str(uuid.uuid4()),
            "event_time": log.event_time,
            "detect_time": _now(),
            "username": log.username,
            "src_ip": log.src_ip,
            "source_type": log.source_type,
            "risk_level": risk_level,
            "risk_score": _risk_score(risk_level),
            "rule_hits": [rule],
            "evidence": evidence,
            "related_event_ids": [log.event_id] + related_ids,
            "related_logs_summary": summary,
            "status": "new",
            "llm_analysis_id": None,
        }
        return AlertEvent.model_validate(payload)


def detect_batch(logs: list[NormalizedLog], engine: RuleEngine | None = None) -> list[AlertEvent]:
    engine = engine or RuleEngine()
    alerts: list[AlertEvent] = []
    for log in sorted(logs, key=lambda x: x.event_time):
        alerts.extend(engine.evaluate_log(log))
    return alerts
