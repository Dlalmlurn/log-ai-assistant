from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

# Ensure project root is importable when launched via `streamlit run src/dashboard/app.py`
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_engine import AIAnalyzer
from src.config import settings
from src.report.daily_report import generate_daily_report
from src.schemas import AlertEvent
from src.storage import ElasticStorage

st.set_page_config(page_title="日志分析 AI 助手", layout="wide")


@st.cache_resource
def get_storage() -> ElasticStorage:
    return ElasticStorage()


@st.cache_resource
def get_analyzer() -> AIAnalyzer:
    return AIAnalyzer()


def page_overview(storage: ElasticStorage) -> None:
    st.title("系统概览")
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)

    today_query = {"range": {"ingest_time": {"gte": start.isoformat(), "lte": now.isoformat()}}}
    alert_query = {"range": {"detect_time": {"gte": start.isoformat(), "lte": now.isoformat()}}}

    log_count = storage.count(settings.elasticsearch_log_index, today_query)
    alert_count = storage.count(settings.elasticsearch_alert_index, alert_query)
    high_alert_count = storage.count(
        settings.elasticsearch_alert_index,
        {"bool": {"must": [alert_query, {"term": {"risk_level": "高"}}]}},
    )
    user_agg = storage.aggregate(
        settings.elasticsearch_log_index,
        {
            "size": 0,
            "query": today_query,
            "aggs": {
                "users": {"cardinality": {"field": "username"}},
                "ips": {"cardinality": {"field": "src_ip"}},
            },
        },
    )
    ai_count = storage.count(settings.elasticsearch_ai_index)

    users = user_agg.get("aggregations", {}).get("users", {}).get("value", 0)

    ips = user_agg.get("aggregations", {}).get("ips", {}).get("value", 0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("今日日志总量", log_count)
    c2.metric("今日异常数量", alert_count)
    c3.metric("高危异常数量", high_alert_count)
    c4.metric("涉及用户数量", users)
    c5.metric("涉及来源IP数量", ips)
    c6.metric("AI已研判数量", ai_count)


def page_recent_logs(storage: ElasticStorage) -> None:
    st.title("最近日志")
    col1, col2, col3, col4 = st.columns(4)
    source_type = col1.selectbox("source_type", ["全部", "vpn", "oa", "api", "system", "security_device"])
    username = col2.text_input("username")
    src_ip = col3.text_input("src_ip")
    status = col4.selectbox("status", ["全部", "success", "failed", "denied", "error"])
    now_utc = datetime.now(timezone.utc)
    t1, t2, t3, t4 = st.columns(4)
    start_date = t1.date_input("开始日期", value=(now_utc - timedelta(days=1)).date())
    start_clock = t2.time_input("开始时刻", value=(now_utc - timedelta(days=1)).time().replace(microsecond=0))
    end_date = t3.date_input("结束日期", value=now_utc.date())
    end_clock = t4.time_input("结束时刻", value=now_utc.time().replace(microsecond=0))
    start_time = datetime.combine(start_date, start_clock).replace(tzinfo=timezone.utc)
    end_time = datetime.combine(end_date, end_clock).replace(tzinfo=timezone.utc)
    if end_time < start_time:
        st.warning("结束时间早于开始时间，已自动交换。")
        start_time, end_time = end_time, start_time

    must = []
    must.append({"range": {"ingest_time": {"gte": start_time.isoformat(), "lte": end_time.isoformat()}}})
    if source_type != "全部":
        must.append({"term": {"source_type": source_type}})
    if username:
        must.append({"term": {"username": username}})
    if src_ip:
        must.append({"term": {"src_ip": src_ip}})
    if status != "全部":
        must.append({"term": {"status": status}})

    logs = storage.search(
        settings.elasticsearch_log_index,
        query={"bool": {"must": must}},
        size=300,
        sort=[{"ingest_time": "desc"}],
    )
    df = pd.DataFrame(logs)
    st.dataframe(df, use_container_width=True)


def _load_alerts(storage: ElasticStorage, risk: str, username: str, rule: str) -> list[dict]:
    must = []
    must.append({"range": {"detect_time": {"gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}}})
    if risk != "全部":
        must.append({"term": {"risk_level": risk}})
    if username:
        must.append({"term": {"username": username}})
    if rule:
        must.append({"match_phrase": {"rule_hits": rule}})

    return storage.search(
        settings.elasticsearch_alert_index,
        query={"bool": {"must": must}},
        size=500,
        sort=[{"detect_time": "desc"}],
    )


def page_alerts(storage: ElasticStorage, analyzer: AIAnalyzer) -> None:
    st.title("异常事件")
    c1, c2, c3 = st.columns(3)
    risk = c1.selectbox("风险等级", ["全部", "低", "中", "高"])
    username = c2.text_input("用户")
    rule = c3.text_input("规则关键词")

    alerts = _load_alerts(storage, risk, username, rule)
    if not alerts:
        st.info("暂无异常事件")
        return

    df = pd.DataFrame(alerts)
    st.dataframe(df[["alert_id", "detect_time", "username", "src_ip", "risk_level", "rule_hits", "status"]], use_container_width=True)

    selected_id = st.selectbox("选择异常事件", options=df["alert_id"].tolist())
    selected = next(item for item in alerts if item.get("alert_id") == selected_id)

    st.subheader("异常详情")
    st.json(selected)

    related_logs = storage.search(
        settings.elasticsearch_log_index,
        query={"terms": {"event_id": selected.get("related_event_ids", [])}},
        size=50,
    )
    st.subheader("相关日志摘要")
    st.dataframe(pd.DataFrame(related_logs), use_container_width=True)

    baseline = storage.search(
        settings.elasticsearch_baseline_index,
        query={"term": {"username": selected.get("username")}},
        size=1,
    )
    st.subheader("用户行为基线")
    st.json(baseline[0] if baseline else {})

    ai_report = storage.search(
        settings.elasticsearch_ai_index,
        query={"term": {"alert_id": selected_id}},
        size=1,
        sort=[{"created_at": "desc"}],
    )
    st.subheader("AI 研判结果")
    st.json(ai_report[0] if ai_report else {})

    if st.button("重新 AI 研判", key=f"reanalyze-{selected_id}"):
        alert = AlertEvent.model_validate(selected)
        baseline_doc = baseline[0] if baseline else {}
        report = analyzer.analyze(alert, baseline=baseline_doc, related_logs=related_logs)
        report_doc = report.model_dump(mode="json")
        storage.index_document(settings.elasticsearch_ai_index, report_doc, doc_id=report.ai_report_id)
        storage.update_document(
            settings.elasticsearch_alert_index,
            selected_id,
            {"llm_analysis_id": report.ai_report_id, "status": "analyzed"},
        )
        st.success("已重新生成 AI 研判")


def page_ai_reports(storage: ElasticStorage) -> None:
    st.title("AI 研判")
    reports = storage.search(
        settings.elasticsearch_ai_index,
        query={"match_all": {}},
        size=200,
        sort=[{"created_at": "desc"}],
    )
    st.dataframe(pd.DataFrame(reports), use_container_width=True)


def page_user_risk(storage: ElasticStorage) -> None:
    st.title("用户风险排行")
    body = {
        "size": 0,
        "aggs": {
            "users": {
                "terms": {"field": "username", "size": 20},
                "aggs": {
                    "alert_count": {"value_count": {"field": "alert_id"}},
                    "high_count": {"filter": {"term": {"risk_level": "高"}}},
                    "risk_score": {"sum": {"field": "risk_score"}},
                    "last_time": {"max": {"field": "detect_time"}},
                    "top_rule": {"terms": {"field": "rule_hits", "size": 1}},
                },
            }
        },
    }
    resp = storage.aggregate(settings.elasticsearch_alert_index, body)
    rows = []
    for bucket in resp.get("aggregations", {}).get("users", {}).get("buckets", []):
        top_rule_buckets = bucket.get("top_rule", {}).get("buckets", [])
        rows.append(
            {
                "username": bucket.get("key"),
                "异常数量": bucket.get("alert_count", {}).get("value", 0),
                "高危数量": bucket.get("high_count", {}).get("doc_count", 0),
                "风险分": bucket.get("risk_score", {}).get("value", 0),
                "主要规则": top_rule_buckets[0].get("key") if top_rule_buckets else "",
                "最近异常时间": bucket.get("last_time", {}).get("value_as_string", ""),
            }
        )
    df = pd.DataFrame(rows).sort_values(by="风险分", ascending=False) if rows else pd.DataFrame()
    st.dataframe(df, use_container_width=True)


def page_rule_stats(storage: ElasticStorage) -> None:
    st.title("规则命中统计")
    body = {"size": 0, "aggs": {"rules": {"terms": {"field": "rule_hits", "size": 20}}}}
    resp = storage.aggregate(settings.elasticsearch_alert_index, body)
    rows = [
        {"rule": b.get("key"), "count": b.get("doc_count")}
        for b in resp.get("aggregations", {}).get("rules", {}).get("buckets", [])
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def page_daily_report(storage: ElasticStorage) -> None:
    st.title("每日安全态势简报")
    if st.button("生成今日简报"):
        report = generate_daily_report(storage)
        doc = report.model_dump(mode="json")
        storage.index_document(settings.elasticsearch_daily_index, doc, doc_id=report.report_id)
        st.success("简报已生成")
        st.markdown(report.markdown)

    reports = storage.search(
        settings.elasticsearch_daily_index,
        query={"match_all": {}},
        size=20,
        sort=[{"created_at": "desc"}],
    )
    if reports:
        selected = st.selectbox("历史简报", options=[r["report_id"] for r in reports])
        report = next(r for r in reports if r["report_id"] == selected)
        st.markdown(report.get("markdown", ""))


def page_system_health(storage: ElasticStorage, analyzer: AIAnalyzer) -> None:
    st.title("系统运行状态")

    kafka_ok = True
    try:
        from kafka import KafkaAdminClient

        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
        admin.list_topics()
        admin.close()
    except Exception:
        kafka_ok = False

    es_ok = storage.health()

    flink_ok = False
    try:
        import requests

        resp = requests.get(f"{settings.flink_dashboard_url}/overview", timeout=3)
        flink_ok = resp.ok
    except Exception:
        flink_ok = False

    st.write(f"Kafka 连接: {'正常' if kafka_ok else '异常'}")
    st.write(f"Elasticsearch 连接: {'正常' if es_ok else '异常'}")
    st.write(f"Flink Dashboard: {settings.flink_dashboard_url} ({'正常' if flink_ok else '异常'})")
    st.write(f"DashScope API: {'已配置' if not analyzer.mock_mode else '未配置，当前为mock模式'}")

    latest = storage.search(
        settings.elasticsearch_log_index,
        query={"match_all": {}},
        size=1,
        sort=[{"ingest_time": "desc"}],
    )
    latest_time = latest[0].get("ingest_time") if latest else "N/A"
    st.write(f"最近一次数据更新时间: {latest_time}")


def main() -> None:
    storage = get_storage()
    analyzer = get_analyzer()

    page = st.sidebar.radio(
        "页面",
        [
            "系统概览",
            "最近日志",
            "异常事件",
            "AI 研判",
            "用户风险排行",
            "规则命中统计",
            "每日安全态势简报",
            "系统运行状态",
        ],
    )

    if page == "系统概览":
        page_overview(storage)
    elif page == "最近日志":
        page_recent_logs(storage)
    elif page == "异常事件":
        page_alerts(storage, analyzer)
    elif page == "AI 研判":
        page_ai_reports(storage)
    elif page == "用户风险排行":
        page_user_risk(storage)
    elif page == "规则命中统计":
        page_rule_stats(storage)
    elif page == "每日安全态势简报":
        page_daily_report(storage)
    elif page == "系统运行状态":
        page_system_health(storage, analyzer)


if __name__ == "__main__":
    main()
