from __future__ import annotations

"""规则检测引擎。

这个文件负责“发现异常行为”，例如暴力破解、新 IP 登录、敏感资源访问等。
发现异常后，它会把事件生成工作交给 AnomalyEventBuilder。
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from typing import Deque

from src.config import settings
from src.detection.anomaly_builder import AnomalyEventBuilder
from src.schemas import AnomalyEvent, NormalizedLog

# 判断敏感资源时用的关键词。只要 resource 里包含这些词，就会进入敏感访问规则。
SENSITIVE_KEYWORDS = ("export", "download", "admin", "/admin", "sensitive", "config", "backup")

# 滑动窗口长度：规则会统计最近 1/5/10 分钟内发生了多少次相关行为。
WINDOW_1M = timedelta(minutes=1)
WINDOW_5M = timedelta(minutes=5)
WINDOW_10M = timedelta(minutes=10)


@dataclass
class DetectionContext:
    """单条日志检测时的外部上下文，由 worker 从 ClickHouse/baseline 查好后传入。"""

    seen_source: bool | None = None
    baseline_deviations: list[dict[str, Any]] = field(default_factory=list)


def _is_sensitive(resource: str | None) -> bool:
    """判断当前访问的资源是否属于敏感资源。"""

    if not resource:
        return False
    lowered = resource.lower()
    return any(k in lowered for k in SENSITIVE_KEYWORDS)


class RuleEngine:
    """基于内存滑动窗口的规则引擎。"""

    def __init__(self, builder: AnomalyEventBuilder | None = None):
        # builder 专门负责把规则命中结果组装成 AnomalyEvent。
        self.builder = builder or AnomalyEventBuilder()

        # 下面这些 dict/deque 是规则引擎的短期记忆，用来统计一段时间内的行为次数。
        self.ip_failed_logins: dict[str, Deque[datetime]] = defaultdict(deque)
        self.user_failed_logins: dict[str, Deque[datetime]] = defaultdict(deque)
        self.ip_failed_users: dict[str, Deque[tuple[datetime, str]]] = defaultdict(deque)
        self.user_api_calls: dict[str, Deque[datetime]] = defaultdict(deque)
        self.user_sensitive_access: dict[str, Deque[datetime]] = defaultdict(deque)
        self.known_login_ips: dict[str, set[str]] = defaultdict(set)
        self.new_ip_login_events: dict[str, Deque[tuple[datetime, str, str]]] = defaultdict(deque)

    def evaluate_log(self, log: NormalizedLog, context: DetectionContext | None = None) -> list[AnomalyEvent]:
        """评估单条日志，返回这条日志触发的所有异常事件。"""

        context = context or DetectionContext()
        anomalies: list[AnomalyEvent] = []
        ts = log.event_time

        # 登录失败、登录成功、API 调用、敏感访问分别走不同规则。
        if log.action == "login" and log.result == "fail":
            anomalies.extend(self._handle_login_failed(log, ts, context))

        if log.action == "login" and log.result == "success":
            anomalies.extend(self._handle_login_success(log, ts, context))

        if log.action == "api_call":
            anomalies.extend(self._handle_api_call(log, ts, context))

        if _is_sensitive(log.resource):
            anomalies.extend(self._handle_sensitive_access(log, ts, context))

        # 普通用户访问 admin 资源，通常代表越权或敏感操作风险。
        if log.user_id and log.user_id != "admin" and log.resource and "admin" in log.resource.lower():
            anomalies.append(
                self._build_anomaly(
                    log,
                    rule="普通用户访问admin接口",
                    reason_codes=["admin_resource_access"],
                    evidence={"resource": log.resource, "user_id": log.user_id},
                    baseline_deviations=context.baseline_deviations,
                )
            )

        # 系统日志里的 error/critical 用于捕获系统异常类事件。
        if log.source_type == "system":
            msg = (log.message or "").lower()
            if log.result == "error" or "error" in msg or "critical" in msg:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        rule="系统日志出现error或critical",
                        reason_codes=["system_error_pattern"],
                        evidence={"message": log.message, "result": log.result},
                        baseline_deviations=context.baseline_deviations,
                    )
                )

        return anomalies

    def _handle_login_failed(
        self,
        log: NormalizedLog,
        ts: datetime,
        context: DetectionContext,
    ) -> list[AnomalyEvent]:
        """处理登录失败相关规则：同 IP 多次失败、同用户多次失败、同 IP 攻击多个用户。"""

        anomalies: list[AnomalyEvent] = []

        if log.src_ip:
            q = self.ip_failed_logins[log.src_ip]
            q.append(ts)
            self._trim_times(q, ts - WINDOW_5M)
            if len(q) >= settings.threshold_ip_fail_5m:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        rule="同一src_ip在5分钟内登录失败超阈值",
                        reason_codes=["failed_login_spike"],
                        evidence={"src_ip": log.src_ip, "failed_count_5m": len(q)},
                        risk_component_overrides={"rule_strength": 70},
                        baseline_deviations=context.baseline_deviations,
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
                        rule="同一user_id在5分钟内登录失败超阈值",
                        reason_codes=["failed_login_spike"],
                        evidence={"user_id": log.user_id, "failed_count_5m": len(uq)},
                        baseline_deviations=context.baseline_deviations,
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
                        rule="同一IP多用户登录失败",
                        reason_codes=["credential_stuffing_pattern"],
                        evidence={
                            "src_ip": log.src_ip,
                            "distinct_users_5m": sorted(unique_users),
                            "count": len(unique_users),
                        },
                        baseline_deviations=context.baseline_deviations,
                    )
                )

        return anomalies

    def _handle_login_success(
        self,
        log: NormalizedLog,
        ts: datetime,
        context: DetectionContext | None = None,
    ) -> list[AnomalyEvent]:
        """处理登录成功相关规则：新 IP 登录、非工作时间登录。"""

        anomalies: list[AnomalyEvent] = []
        if log.user_id and log.src_ip:
            known = self.known_login_ips[log.user_id]
            is_new_source = context.seen_source is False if context and context.seen_source is not None else log.src_ip not in known
            if is_new_source:
                # 第一次见到这个用户从该 IP 登录，记录下来供后续敏感访问关联。
                known.add(log.src_ip)
                self.new_ip_login_events[log.user_id].append((ts, log.src_ip, log.event_id))
                anomalies.append(
                    self._build_anomaly(
                        log,
                        rule="新IP登录",
                        reason_codes=["new_source_ip"],
                        evidence={"user_id": log.user_id, "new_ip": log.src_ip},
                        baseline_deviations=context.baseline_deviations if context else None,
                    )
                )
            else:
                known.add(log.src_ip)

        if ts.hour < settings.work_hour_start or ts.hour >= settings.work_hour_end:
            anomalies.append(
                self._build_anomaly(
                    log,
                    rule="非工作时间登录",
                    reason_codes=["rare_login_hour"],
                    evidence={"event_hour": ts.hour, "work_hours": f"{settings.work_hour_start}:00-{settings.work_hour_end}:00"},
                    baseline_deviations=context.baseline_deviations if context else None,
                )
            )
        return anomalies

    def _handle_api_call(
        self,
        log: NormalizedLog,
        ts: datetime,
        context: DetectionContext,
    ) -> list[AnomalyEvent]:
        """处理 API 调用频率异常。"""

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
                    rule="同一user_id在1分钟内API调用超阈值",
                    reason_codes=["high_api_rate"],
                    evidence={"user_id": log.user_id, "api_calls_1m": len(q)},
                    baseline_deviations=context.baseline_deviations,
                )
            )
        return anomalies

    def _handle_sensitive_access(
        self,
        log: NormalizedLog,
        ts: datetime,
        context: DetectionContext,
    ) -> list[AnomalyEvent]:
        """处理敏感资源访问，并尝试关联“新 IP 登录后访问敏感资源”的攻击链。"""

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
                    rule="同一user_id在5分钟内敏感资源访问超阈值",
                    reason_codes=["sensitive_resource_access"],
                    evidence={"user_id": log.user_id, "sensitive_count_5m": len(q), "resource": log.resource},
                    baseline_deviations=context.baseline_deviations,
                )
            )

        new_ip_events = self.new_ip_login_events.get(log.user_id, deque())
        self._trim_new_ip_events(new_ip_events, ts - WINDOW_10M)
        if new_ip_events:
            # 如果 10 分钟内同一用户发生过新 IP 登录，再访问敏感资源，就认为两件事有关联。
            recent = [e for e in new_ip_events if e[1] == log.src_ip or log.src_ip is None]
            if recent:
                anomalies.append(
                    self._build_anomaly(
                        log,
                        rule="新IP登录后短时间访问敏感资源",
                        reason_codes=["new_source_then_sensitive_access", "sensitive_resource_access"],
                        evidence={"user_id": log.user_id, "src_ip": log.src_ip, "resource": log.resource},
                        related_event_ids=[item[2] for item in recent],
                        baseline_deviations=context.baseline_deviations,
                    )
                )
                # 如果敏感资源还是导出/下载接口，风险更像数据外泄。
                if log.resource and any(k in log.resource.lower() for k in ("export", "download")):
                    anomalies.append(
                        self._build_anomaly(
                            log,
                            rule="新IP登录后短时间大量调用导出接口",
                            reason_codes=["new_source_then_sensitive_access", "download_volume_spike"],
                            evidence={"user_id": log.user_id, "resource": log.resource, "src_ip": log.src_ip},
                            related_event_ids=[item[2] for item in recent],
                            baseline_deviations=context.baseline_deviations,
                        )
                    )

        return anomalies

    @staticmethod
    def _trim_times(items: Deque[datetime], min_time: datetime) -> None:
        """删除滑动窗口外的旧时间点。"""

        while items and items[0] < min_time:
            items.popleft()

    @staticmethod
    def _trim_pairs(items: Deque[tuple[datetime, str]], min_time: datetime) -> None:
        """删除滑动窗口外的旧二元组记录。"""

        while items and items[0][0] < min_time:
            items.popleft()

    @staticmethod
    def _trim_new_ip_events(items: Deque[tuple[datetime, str, str]], min_time: datetime) -> None:
        """删除滑动窗口外的新 IP 登录记录。"""

        while items and items[0][0] < min_time:
            items.popleft()

    def _build_anomaly(
        self,
        log: NormalizedLog,
        rule: str,
        reason_codes: list[str],
        evidence: dict,
        related_event_ids: list[str] | None = None,
        risk_component_overrides: dict[str, int] | None = None,
        baseline_deviations: list[dict[str, Any]] | None = None,
    ) -> AnomalyEvent:
        """把规则命中信息交给 builder，生成标准异常事件。"""

        seed = _event_id_seed(log, rule, reason_codes)
        return self.builder.build(
            log=log,
            rule_hits=[rule],
            reason_codes=reason_codes,
            evidence=evidence,
            related_event_ids=related_event_ids,
            risk_component_overrides=risk_component_overrides,
            baseline_deviations=baseline_deviations,
            event_id_seed=seed,
        )


def detect_batch(logs: list[NormalizedLog], engine: RuleEngine | None = None) -> list[AnomalyEvent]:
    """按事件时间顺序批量检测日志。"""

    engine = engine or RuleEngine()
    anomalies: list[AnomalyEvent] = []
    for log in sorted(logs, key=lambda x: x.event_time):
        anomalies.extend(engine.evaluate_log(log))
    return anomalies


def _event_id_seed(log: NormalizedLog, rule: str, reason_codes: list[str]) -> str:
    """根据源日志和规则生成稳定 seed，支持 worker 重扫时得到同一个异常 ID。"""

    return "|".join(
        [
            log.tenant_id,
            log.event_id,
            ",".join(reason_codes),
            rule,
        ]
    )
