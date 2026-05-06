from src.storage.elastic_client import ElasticStorage

if __name__ == "__main__":
    es = ElasticStorage()
    es.ensure_indices()
    print("Elasticsearch indices initialized")
