from datetime import datetime, timezone

from src.api.app import _build_logs_query, app, list_logs
from src.config import settings
from src.storage.elastic_client import ElasticStorage


class FakeLogStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search_page(self, **kwargs):
        self.calls.append(kwargs)
        return (
            [
                {
                    "_id": "es-doc-1",
                    "event_id": "evt-1",
                    "event_time": "2026-05-13T10:00:00Z",
                    "ingest_time": "2026-05-13T10:00:05Z",
                    "source_type": "vpn",
                    "username": "alice",
                    "src_ip": "10.0.0.7",
                    "action": "login",
                    "status": "failed",
                    "message": "VPN login failed",
                    "raw_message": "raw vpn line",
                    "risk_tags": [],
                    "original_fields": {"vpn_result": "bad_password"},
                }
            ],
            7,
        )


def test_logs_query_applies_documented_filters() -> None:
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    response = list_logs(
        source_type="vpn",
        username="alice",
        src_ip="10.0.0.7",
        status="failed",
        start_time=start,
        end_time=end,
        limit=25,
        offset=50,
        storage=FakeLogStorage(),
    )

    item = response.model_dump(mode="json")["items"][0]

    assert item["event_id"] == "evt-1"
    assert item["original_fields"] == {"vpn_result": "bad_password"}
    assert "_id" not in item
    assert response.total == 7
    assert response.limit == 25
    assert response.offset == 50


def test_logs_endpoint_queries_security_logs_with_pagination_and_filters() -> None:
    storage = FakeLogStorage()
    start = datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    list_logs(
        source_type="vpn",
        username="alice",
        src_ip="10.0.0.7",
        status="failed",
        start_time=start,
        end_time=end,
        limit=25,
        offset=50,
        storage=storage,
    )

    assert storage.calls == [
        {
            "index": settings.elasticsearch_log_index,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "event_time": {
                                    "gte": "2026-05-13T09:00:00+00:00",
                                    "lte": "2026-05-13T10:00:00+00:00",
                                }
                            }
                        },
                        {"term": {"source_type": "vpn"}},
                        {"term": {"username": "alice"}},
                        {"term": {"src_ip": "10.0.0.7"}},
                        {"term": {"status": "failed"}},
                    ]
                }
            },
            "limit": 25,
            "offset": 50,
            "sort": [{"event_time": "desc"}],
        }
    ]


def test_logs_query_defaults_to_last_24_hours_when_start_time_omitted() -> None:
    end = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)

    query = _build_logs_query(end_time=end)

    assert query["bool"]["filter"] == [
        {
            "range": {
                "event_time": {
                    "gte": "2026-05-12T10:00:00+00:00",
                    "lte": "2026-05-13T10:00:00+00:00",
                }
            }
        }
    ]


def test_logs_openapi_binds_contract_and_error_shape() -> None:
    operation = app.openapi()["paths"]["/api/v1/logs"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NormalizedLogListResponse"
    }
    assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }


def test_elastic_search_page_uses_offset_limit_sort_and_total_hits() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.call: dict[str, object] | None = None

        def search(self, *, index: str, body: dict[str, object]):
            self.call = {"index": index, "body": body}
            return {
                "hits": {
                    "total": {"value": 12, "relation": "eq"},
                    "hits": [{"_id": "doc-1", "_source": {"event_id": "evt-1"}}],
                }
            }

    client = FakeClient()
    storage = ElasticStorage.__new__(ElasticStorage)
    storage.client = client

    items, total = storage.search_page(
        index="security-logs",
        query={"match_all": {}},
        limit=10,
        offset=20,
        sort=[{"event_time": "desc"}],
    )

    assert items == [{"event_id": "evt-1", "_id": "doc-1"}]
    assert total == 12
    assert client.call == {
        "index": "security-logs",
        "body": {
            "query": {"match_all": {}},
            "from": 20,
            "size": 10,
            "track_total_hits": True,
            "sort": [{"event_time": "desc"}],
        },
    }
