from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import settings
from src.schemas import DailyReport
from src.storage.elastic_client import ElasticStorage


class DailyReportBuilder:
    def __init__(self, storage: ElasticStorage):
        self.storage = storage

    def build(self, date_str: str | None = None) -> DailyReport:
        day = datetime.now(timezone.utc).date() if date_str is None else datetime.strptime(date_str, "%Y-%m-%d").date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        log_count = self.storage.count(
            settings.elasticsearch_log_index,
            query={"range": {"event_time": {"gte": start.isoformat(), "lt": end.isoformat()}}},
        )
        alert_count = self.storage.count(
            settings.elasticsearch_alert_index,
            query={"range": {"detect_time": {"gte": start.isoformat(), "lt": end.isoformat()}}},
        )
        high_risk_count = self.storage.count(
            settings.elasticsearch_alert_index,
            query={
                "bool": {
                    "must": [
                        {"range": {"detect_time": {"gte": start.isoformat(), "lt": end.isoformat()}}},
                        {"term": {"risk_level": "高"}},
                    ]
                }
            },
        )

        major_risks, high_users, typical_alerts = self._aggregate_alert_details(start, end)
        overall_score = self._score(log_count, alert_count, high_risk_count)
        ai_summary = self._summary_text(log_count, alert_count, high_risk_count, major_risks)
        recommendation = self._recommendation(high_risk_count, major_risks)
        markdown = self._markdown(
            day.isoformat(),
            overall_score,
            log_count,
            alert_count,
            high_risk_count,
            major_risks,
            high_users,
            typical_alerts,
            ai_summary,
            recommendation,
        )

        report = DailyReport(
            report_id=str(uuid.uuid4()),
            date=day.isoformat(),
            created_at=datetime.now(timezone.utc),
            overall_score=overall_score,
            log_count=log_count,
            alert_count=alert_count,
            high_risk_count=high_risk_count,
            major_risks=major_risks,
            high_risk_users=high_users,
            typical_alerts=typical_alerts,
            ai_summary=ai_summary,
            recommendation=recommendation,
            markdown=markdown,
        )
        return report

    def _aggregate_alert_details(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        agg_body = {
            "size": 0,
            "query": {"range": {"detect_time": {"gte": start.isoformat(), "lt": end.isoformat()}}},
            "aggs": {
                "rule_hits": {"terms": {"field": "rule_hits", "size": 5}},
                "users": {"terms": {"field": "username", "size": 5}},
            },
        }
        agg_resp = self.storage.aggregate(settings.elasticsearch_alert_index, agg_body)

        risk_buckets = agg_resp.get("aggregations", {}).get("rule_hits", {}).get("buckets", [])
        user_buckets = agg_resp.get("aggregations", {}).get("users", {}).get("buckets", [])

        major_risks = [b.get("key", "unknown") for b in risk_buckets]
        high_users = [b.get("key", "unknown") for b in user_buckets]

        typical_alerts = self.storage.search(
            settings.elasticsearch_alert_index,
            query={"range": {"detect_time": {"gte": start.isoformat(), "lt": end.isoformat()}}},
            size=5,
            sort=[{"risk_score": "desc"}, {"detect_time": "desc"}],
        )
        for item in typical_alerts:
            item.pop("_id", None)
        return major_risks, high_users, typical_alerts

    @staticmethod
    def _score(log_count: int, alert_count: int, high_risk_count: int) -> float:
        if log_count == 0:
            return 100.0
        alert_ratio = alert_count / max(log_count, 1)
        high_ratio = high_risk_count / max(alert_count, 1)
        score = 100 - alert_ratio * 60 - high_ratio * 30
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _summary_text(log_count: int, alert_count: int, high_risk_count: int, major_risks: list[str]) -> str:
        risk_text = "、".join(major_risks[:3]) if major_risks else "暂无明显主风险"
        return (
            f"今日共处理日志 {log_count} 条，识别异常 {alert_count} 条，其中高危 {high_risk_count} 条。"
            f"主要风险类型为：{risk_text}。"
        )

    @staticmethod
    def _recommendation(high_risk_count: int, major_risks: list[str]) -> str:
        if high_risk_count == 0:
            return "持续监控并按日复核异常规则命中情况。"
        top = major_risks[0] if major_risks else "高危异常行为"
        return f"优先处置 {top} 相关事件，建议核查账号、IP 与敏感资源访问链路。"

    @staticmethod
    def _markdown(
        date: str,
        overall_score: float,
        log_count: int,
        alert_count: int,
        high_risk_count: int,
        major_risks: list[str],
        high_users: list[str],
        typical_alerts: list[dict[str, Any]],
        ai_summary: str,
        recommendation: str,
    ) -> str:
        lines = [
            "# 每日安全态势简报",
            f"- 日期: {date}",
            f"- 总体安全评分: {overall_score}",
            f"- 日志总量: {log_count}",
            f"- 异常事件数量: {alert_count}",
            f"- 高危事件数量: {high_risk_count}",
            f"- 主要风险类型: {', '.join(major_risks) if major_risks else '无'}",
            f"- 高危用户列表: {', '.join(high_users) if high_users else '无'}",
            "",
            "## 典型异常事件",
        ]
        if typical_alerts:
            for item in typical_alerts[:5]:
                lines.append(
                    f"- [{item.get('risk_level')}] {item.get('username')} {item.get('rule_hits')} @ {item.get('detect_time')}"
                )
        else:
            lines.append("- 无")

        lines.extend(["", "## AI 总结", ai_summary, "", "## 处置建议", recommendation])
        return "\n".join(lines)


def generate_daily_report(storage: ElasticStorage, date_str: str | None = None) -> DailyReport:
    builder = DailyReportBuilder(storage)
    return builder.build(date_str=date_str)
