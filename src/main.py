from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests
from kafka import KafkaAdminClient, KafkaProducer
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

from src.ai_engine import AIAnalyzer
from src.collector import run_generator_once, stream_file_to_kafka
from src.config import PROJECT_ROOT, settings
from src.detection import detect_batch
from src.parser import normalize_raw_record, run_raw_to_parsed_worker
from src.report import generate_daily_report
from src.schemas import AlertEvent, NormalizedLog
from src.storage import ElasticStorage, KafkaToElasticConsumer
from src.ueba import build_and_store_baselines


def ensure_topics() -> None:
    admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
    topics = [
        settings.kafka_raw_topic,
        settings.kafka_parsed_topic,
        settings.kafka_alert_topic,
        settings.kafka_ai_topic,
        settings.kafka_metrics_topic,
    ]
    new_topics = [NewTopic(name=t, num_partitions=3, replication_factor=1) for t in topics]
    try:
        admin.create_topics(new_topics=new_topics, validate_only=False)
    except TopicAlreadyExistsError:
        pass
    except Exception:
        existing = set(admin.list_topics())
        missing = [t for t in topics if t not in existing]
        if missing:
            admin.create_topics(
                new_topics=[NewTopic(name=t, num_partitions=3, replication_factor=1) for t in missing],
                validate_only=False,
            )
    finally:
        admin.close()


def cmd_init(_: argparse.Namespace) -> None:
    ensure_topics()
    es = ElasticStorage()
    es.ensure_indices()
    print("Init completed: Kafka topics + Elasticsearch indices are ready.")


def cmd_inspect_generator(args: argparse.Namespace) -> None:
    outdir = PROJECT_ROOT / "log-generator" / "vpn_output"
    outdir.mkdir(parents=True, exist_ok=True)
    result = run_generator_once(outdir=outdir, fmt="all", days=1, count=args.count)

    print("=== log-generator inspect ===")
    print(f"script: {settings.generator_script}")
    print(f"return_code: {result.returncode}")
    if result.stdout:
        print("stdout:")
        print(result.stdout[:600])
    if result.stderr:
        print("stderr:")
        print(result.stderr[:600])

    jsonl = outdir / "vpn_logs.jsonl"
    syslog = outdir / "vpn_logs.log"
    csv_path = outdir / "vpn_logs.csv"

    print(f"output_jsonl: {jsonl} exists={jsonl.exists()}")
    print(f"output_syslog: {syslog} exists={syslog.exists()}")
    print(f"output_csv: {csv_path} exists={csv_path.exists()}")

    if jsonl.exists():
        with jsonl.open("r", encoding="utf-8") as f:
            sample = f.readline().strip()
            print("sample_jsonl_line:")
            print(sample[:1000])
            parsed = normalize_raw_record(sample)
            print("mapped_normalized_fields:")
            print(json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False, indent=2)[:1500])


def _produce_from_path(path: Path, source_type: str, follow: bool) -> int:
    sent = stream_file_to_kafka(
        file_path=path,
        source_type=source_type,
        from_beginning=True,
        follow=follow,
        stop_after_eof=not follow,
    )
    return sent


def cmd_produce(args: argparse.Namespace) -> None:
    if args.run_generator:
        outdir = PROJECT_ROOT / "log-generator" / "vpn_output"
        result = run_generator_once(outdir=outdir, fmt=args.format, days=args.days, count=args.count, start=args.start)
        if result.returncode != 0:
            print(result.stderr)
            raise SystemExit("log-generator run failed")

    if args.path:
        source_path = Path(args.path).resolve()
    else:
        source_path = settings.generator_jsonl if args.format in {"jsonl", "all"} else settings.generator_syslog

    if not source_path.exists():
        raise SystemExit(f"source log file not found: {source_path}")

    sent = _produce_from_path(source_path, source_type=args.source_type, follow=args.follow)
    print(f"Produced {sent} lines to Kafka topic: {settings.kafka_raw_topic}")


def cmd_consume_to_es(args: argparse.Namespace) -> None:
    runner = KafkaToElasticConsumer(
        consumer_timeout_ms=args.idle_timeout_ms,
        group_id=args.group_id,
    )
    consumed = runner.run(max_messages=args.max_messages)
    print(f"consume-to-es finished, processed records={consumed}")


def cmd_process_raw(args: argparse.Namespace) -> None:
    processed = run_raw_to_parsed_worker(
        max_messages=args.max_messages,
        from_beginning=not args.from_latest,
        idle_timeout_ms=args.idle_timeout_ms,
        group_id=args.group_id,
    )
    print(f"python raw->parsed finished, processed={processed}")


def cmd_build_baseline(_: argparse.Namespace) -> None:
    storage = ElasticStorage()
    storage.ensure_indices()
    output = PROJECT_ROOT / "data" / "user_baselines.json"
    baselines = build_and_store_baselines(storage, output_path=output)
    print(f"built baselines={len(baselines)}, output={output}")


def cmd_detect(args: argparse.Namespace) -> None:
    storage = ElasticStorage()
    logs = storage.fetch_recent_logs(hours=args.hours, size=args.size)
    normalized = [NormalizedLog.model_validate(item) for item in logs]
    alerts = detect_batch(normalized)
    alert_docs = [a.model_dump(mode="json") for a in alerts]
    storage.bulk_index(settings.elasticsearch_alert_index, alert_docs, id_field="alert_id")

    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )
    for item in alert_docs:
        producer.send(settings.kafka_alert_topic, item)
    producer.flush()
    producer.close()

    print(f"offline detect finished, alerts={len(alerts)}")


def cmd_analyze_alerts(args: argparse.Namespace) -> None:
    storage = ElasticStorage()
    analyzer = AIAnalyzer()

    query = {
        "bool": {
            "must_not": [{"exists": {"field": "llm_analysis_id"}}],
        }
    }
    pending = storage.search(
        settings.elasticsearch_alert_index,
        query=query,
        size=args.limit,
        sort=[{"detect_time": "desc"}],
    )

    if not pending:
        print("no pending alerts to analyze")
        return

    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )

    analyzed = 0
    for item in pending:
        alert = AlertEvent.model_validate(item)
        baseline = {}
        if alert.username:
            rows = storage.search(
                settings.elasticsearch_baseline_index,
                query={"term": {"username": alert.username}},
                size=1,
            )
            baseline = rows[0] if rows else {}

        related_logs = storage.search(
            settings.elasticsearch_log_index,
            query={"terms": {"event_id": alert.related_event_ids}},
            size=100,
        )

        report = analyzer.analyze(alert=alert, baseline=baseline, related_logs=related_logs)
        report_doc = report.model_dump(mode="json")
        storage.index_document(settings.elasticsearch_ai_index, report_doc, doc_id=report.ai_report_id)
        storage.update_document(
            settings.elasticsearch_alert_index,
            alert.alert_id,
            {"llm_analysis_id": report.ai_report_id, "status": "analyzed"},
        )
        producer.send(settings.kafka_ai_topic, report_doc)
        analyzed += 1

    producer.flush()
    producer.close()
    print(f"analyzed alerts={analyzed}, mode={'mock' if analyzer.mock_mode else 'dashscope'}")


def cmd_report(args: argparse.Namespace) -> None:
    storage = ElasticStorage()
    report = generate_daily_report(storage, date_str=args.date)
    doc = report.model_dump(mode="json")
    storage.index_document(settings.elasticsearch_daily_index, doc, doc_id=report.report_id)

    out_path = PROJECT_ROOT / "data" / f"daily_report_{report.date}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.markdown, encoding="utf-8")
    print(f"daily report generated: {out_path}")
    print(report.markdown)


def cmd_health(_: argparse.Namespace) -> None:
    status = {
        "kafka": False,
        "elasticsearch": False,
        "flink": False,
        "dashscope_configured": bool(settings.dashscope_api_key),
        "last_data_update": "N/A",
    }

    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
        admin.list_topics()
        admin.close()
        status["kafka"] = True
    except Exception:
        status["kafka"] = False

    es = ElasticStorage()
    status["elasticsearch"] = es.health()

    try:
        resp = requests.get(f"{settings.flink_dashboard_url}/overview", timeout=3)
        status["flink"] = resp.ok
    except Exception:
        status["flink"] = False

    try:
        latest = es.search(
            settings.elasticsearch_log_index,
            query={"match_all": {}},
            size=1,
            sort=[{"ingest_time": "desc"}],
        )
        if latest:
            status["last_data_update"] = latest[0].get("ingest_time", "N/A")
    except Exception:
        pass

    print(json.dumps(status, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Log Analysis AI Assistant CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化 Elasticsearch 索引和 Kafka topics")
    p_init.set_defaults(func=cmd_init)

    p_inspect = sub.add_parser("inspect-generator", help="检查导师 log-generator 输出格式")
    p_inspect.add_argument("--count", type=int, default=20)
    p_inspect.set_defaults(func=cmd_inspect_generator)

    p_produce = sub.add_parser("produce", help="读取 log-generator 输出并写入 Kafka raw_logs")
    p_produce.add_argument("--run-generator", action="store_true", help="先执行一次 log-generator")
    p_produce.add_argument("--format", choices=["jsonl", "syslog", "all"], default="jsonl")
    p_produce.add_argument("--days", type=int, default=1)
    p_produce.add_argument("--count", type=int, default=120)
    p_produce.add_argument("--start", default=None)
    p_produce.add_argument("--path", default=None, help="直接指定输入文件")
    p_produce.add_argument("--source-type", default="vpn")
    p_produce.add_argument("--follow", action="store_true", help="持续监听文件新增内容")
    p_produce.set_defaults(func=cmd_produce)

    p_consume = sub.add_parser("consume-to-es", help="消费 parsed_logs/alert_events 写入 Elasticsearch")
    p_consume.add_argument("--max-messages", type=int, default=None)
    p_consume.add_argument("--idle-timeout-ms", type=int, default=5000, help="空闲超时后退出，-1 表示持续运行")
    p_consume.add_argument("--group-id", default="log-ai-consume-to-es")
    p_consume.set_defaults(func=cmd_consume_to_es)

    p_process = sub.add_parser("process-raw", help="Python fallback: 消费 raw_logs 转换并写入 parsed_logs")
    p_process.add_argument("--max-messages", type=int, default=None)
    p_process.add_argument("--from-latest", action="store_true", help="从最新offset开始消费（默认从最早）")
    p_process.add_argument("--idle-timeout-ms", type=int, default=5000, help="空闲超时后退出，-1 表示持续运行")
    p_process.add_argument("--group-id", default="python-raw-to-parsed")
    p_process.set_defaults(func=cmd_process_raw)

    p_baseline = sub.add_parser("build-baseline", help="从 Elasticsearch 生成用户行为基线")
    p_baseline.set_defaults(func=cmd_build_baseline)

    p_detect = sub.add_parser("detect", help="执行离线/准实时异常检测")
    p_detect.add_argument("--hours", type=int, default=24)
    p_detect.add_argument("--size", type=int, default=5000)
    p_detect.set_defaults(func=cmd_detect)

    p_analyze = sub.add_parser("analyze-alerts", help="对未研判异常事件调用大模型")
    p_analyze.add_argument("--limit", type=int, default=100)
    p_analyze.set_defaults(func=cmd_analyze_alerts)

    p_report = sub.add_parser("report", help="生成每日安全态势简报")
    p_report.add_argument("--date", default=None, help="YYYY-MM-DD")
    p_report.set_defaults(func=cmd_report)

    p_health = sub.add_parser("health", help="检查 Kafka/ES/Flink/DashScope 状态")
    p_health.set_defaults(func=cmd_health)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
