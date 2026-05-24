from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from elasticsearch import Elasticsearch, helpers

from src.config import settings


class ElasticStorage:
    def __init__(self, url: str | None = None):
        self.client = Elasticsearch(url or settings.elasticsearch_url, request_timeout=30)

    def health(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False
# 确保索引存在
    def ensure_indices(self) -> None:
        for name, body in index_templates().items():
            if not self.client.indices.exists(index=name):
                self.client.indices.create(index=name, body=body)

    def index_document(self, index: str, document: dict[str, Any], doc_id: str | None = None) -> None:
        self.client.index(index=index, id=doc_id, document=document, refresh=False)

    def bulk_index(self, index: str, documents: list[dict[str, Any]], id_field: str | None = None) -> None:
        if not documents:
            return
        actions = []
        for doc in documents:
            action = {"_op_type": "index", "_index": index, "_source": doc}
            if id_field and doc.get(id_field):
                action["_id"] = doc[id_field]
            actions.append(action)
        helpers.bulk(self.client, actions, refresh=False)

    def update_document(self, index: str, doc_id: str, partial: dict[str, Any]) -> None:
        self.client.update(index=index, id=doc_id, doc=partial, refresh=False)

    def count(self, index: str, query: dict[str, Any] | None = None) -> int:
        payload = {"query": query or {"match_all": {}}}
        return int(self.client.count(index=index, body=payload)["count"])
# 从es查询数据
    def search(
        self,
        index: str,
        query: dict[str, Any] | None = None,
        size: int = 100,
        sort: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        body = {"query": query or {"match_all": {}}, "size": size}
        if sort:
            body["sort"] = sort
        resp = self.client.search(index=index, body=body)
        return [hit["_source"] | {"_id": hit["_id"]} for hit in resp["hits"]["hits"]]

# 带分页能力的 search
    def search_page(
        self,
        index: str,
        query: dict[str, Any] | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        body: dict[str, Any] = {
            "query": query or {"match_all": {}},
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }
        if sort:
            body["sort"] = sort
        resp = self.client.search(index=index, body=body)
        hits = resp["hits"]["hits"]
        return [hit["_source"] | {"_id": hit["_id"]} for hit in hits], _extract_total_hits(resp)

    def aggregate(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.client.search(index=index, body=body)

    def fetch_recent_logs(self, hours: int = 24, size: int = 5000) -> list[dict[str, Any]]:
        return self.fetch_recent_logs_by_field(hours=hours, size=size, time_field="event_time")

    def fetch_recent_logs_by_field(
        self,
        hours: int = 24,
        size: int = 5000,
        time_field: str = "event_time",
    ) -> list[dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        query = {
            "range": {
                time_field: {
                    "gte": start.isoformat(),
                    "lte": end.isoformat(),
                }
            }
        }
        return self.search(
            index=settings.elasticsearch_log_index,
            query=query,
            size=size,
            sort=[{time_field: "desc"}],
        )


def _extract_total_hits(resp: dict[str, Any]) -> int:
    total = resp.get("hits", {}).get("total", 0)
    if isinstance(total, dict):
        return int(total.get("value", 0))
    return int(total or 0)


def index_templates() -> dict[str, dict[str, Any]]:
    return {
        settings.elasticsearch_log_index: {
            "mappings": {
                "properties": {
                    "event_id": {"type": "keyword"},
                    "event_time": {"type": "date"},
                    "ingest_time": {"type": "date"},
                    "tenant_id": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "log_type": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "account_type": {"type": "keyword"},
                    "user_role": {"type": "keyword"},
                    "department": {"type": "keyword"},
                    "host": {"type": "keyword"},
                    "src_ip": {"type": "ip", "ignore_malformed": True},
                    "src_port": {"type": "integer"},
                    "dst_ip": {"type": "ip", "ignore_malformed": True},
                    "dst_port": {"type": "integer"},
                    "geo": {"type": "object", "enabled": True},
                    "action": {"type": "keyword"},
                    "object_type": {"type": "keyword"},
                    "object_id": {"type": "keyword"},
                    "resource": {"type": "keyword"},
                    "result": {"type": "keyword"},
                    "severity": {"type": "integer"},
                    "user_agent": {"type": "keyword"},
                    "protocol": {"type": "keyword"},
                    "auth_method": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "message": {"type": "text"},
                    "raw_log": {"type": "text"},
                    "risk_tags": {"type": "keyword"},
                    "trace_id": {"type": "keyword"},
                    "scenario_id": {"type": "keyword"},
                    "scenario_type": {"type": "keyword"},
                    "attack_chain_id": {"type": "keyword"},
                    "step_index": {"type": "integer"},
                    "injected_label": {"type": "keyword"},
                    "attrs": {"type": "object", "enabled": True},
                }
            }
        },
        settings.elasticsearch_alert_index: {
            "mappings": {
                "properties": {
                    "event_id": {"type": "keyword"},
                    "event_time": {"type": "date"},
                    "detect_time": {"type": "date"},
                    "tenant_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "src_ip": {"type": "ip", "ignore_malformed": True},
                    "host": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "action": {"type": "keyword"},
                    "object_type": {"type": "keyword"},
                    "object_id": {"type": "keyword"},
                    "attack_type": {"type": "keyword"},
                    "risk_level": {"type": "keyword"},
                    "risk_score": {"type": "float"},
                    "risk_components": {"type": "object", "enabled": True},
                    "rule_hits": {"type": "keyword"},
                    "baseline_deviations": {"type": "object", "enabled": True},
                    "reason_codes": {"type": "keyword"},
                    "evidence": {"type": "object", "enabled": True},
                    "related_event_ids": {"type": "keyword"},
                    "scenario_id": {"type": "keyword"},
                    "scenario_type": {"type": "keyword"},
                    "attack_chain_id": {"type": "keyword"},
                    "ai_status": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "created_at": {"type": "date"},
                }
            }
        },
        settings.elasticsearch_ai_index: {
            "mappings": {
                "properties": {
                    "judgement_id": {"type": "keyword"},
                    "event_id": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "model_name": {"type": "keyword"},
                    "model_version": {"type": "keyword"},
                    "attack_type": {"type": "keyword"},
                    "risk_level": {"type": "keyword"},
                    "judgement": {"type": "text"},
                    "key_reasons": {"type": "keyword"},
                    "recommended_actions": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "feedback_suggestions": {"type": "object", "enabled": True},
                    "raw_response": {"type": "object", "enabled": True},
                    "is_mock": {"type": "boolean"},
                }
            }
        },
        settings.elasticsearch_daily_index: {
            "mappings": {
                "properties": {
                    "report_id": {"type": "keyword"},
                    "date": {"type": "date", "format": "yyyy-MM-dd"},
                    "created_at": {"type": "date"},
                    "overall_score": {"type": "float"},
                    "log_count": {"type": "integer"},
                    "alert_count": {"type": "integer"},
                    "high_risk_count": {"type": "integer"},
                    "major_risks": {"type": "keyword"},
                    "high_risk_users": {"type": "keyword"},
                    "typical_alerts": {"type": "object", "enabled": True},
                    "ai_summary": {"type": "text"},
                    "recommendation": {"type": "text"},
                    "markdown": {"type": "text"},
                }
            }
        },
        settings.elasticsearch_baseline_index: {
            "mappings": {
                "properties": {
                    "baseline_date": {"type": "date", "format": "yyyy-MM-dd"},
                    "tenant_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "model_version": {"type": "keyword"},
                    "trained_from": {"type": "date", "format": "yyyy-MM-dd"},
                    "trained_to": {"type": "date", "format": "yyyy-MM-dd"},
                    "sample_days": {"type": "integer"},
                    "sample_count": {"type": "integer"},
                    "baseline_confidence": {"type": "float"},
                    "who_profile": {"type": "object", "enabled": True},
                    "time_profile": {"type": "object", "enabled": True},
                    "location_profile": {"type": "object", "enabled": True},
                    "access_profile": {"type": "object", "enabled": True},
                    "volume_profile": {"type": "object", "enabled": True},
                    "result_profile": {"type": "object", "enabled": True},
                    "why_profile": {"type": "object", "enabled": True},
                    "fallback_level": {"type": "keyword"},
                    "created_at": {"type": "date"},
                }
            }
        },
    }
