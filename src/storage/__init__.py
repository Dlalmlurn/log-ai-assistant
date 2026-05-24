from .clickhouse_client import ClickHouseStorage

__all__ = ["ClickHouseStorage", "ElasticStorage", "KafkaToElasticConsumer"]


def __getattr__(name: str):
    if name == "ElasticStorage":
        from .elastic_client import ElasticStorage

        return ElasticStorage
    if name == "KafkaToElasticConsumer":
        from .kafka_es_consumer import KafkaToElasticConsumer

        return KafkaToElasticConsumer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
