from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

from kafka import KafkaConsumer

from src.ai_engine import AIAnalyzer
from src.config import settings
from src.detection.rules import RuleEngine
from src.schemas import AnomalyEvent, NormalizedLog
from src.storage import ClickHouseStorage
from src.ueba.scorer import UebaScorer

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_detector() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    storage = ClickHouseStorage()
    rule_engine = RuleEngine()
    ueba_scorer = UebaScorer(storage)
    ai_analyzer = AIAnalyzer()

    consumer = KafkaConsumer(
        settings.kafka_parsed_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="anomaly-detector",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    logger.info(
        "anomaly-detector started: topic=%s, bootstrap=%s",
        settings.kafka_parsed_topic,
        settings.kafka_bootstrap_servers,
    )

    # Retry stranded pending anomalies in background (don't block consumer startup)
    threading.Thread(
        target=_retry_pending_analyses,
        args=(storage, ai_analyzer),
        daemon=True,
        name="retry-pending-ai",
    ).start()

    batch: list[AnomalyEvent] = []
    last_flush = time.monotonic()
    batch_max_size = 100
    batch_max_seconds = 10
    cache_refresh_interval = 300  # 5 min
    last_cache_refresh = time.monotonic()

    for msg in consumer:
        try:
            log = NormalizedLog.model_validate(msg.value)
        except Exception:
            continue

        try:
            rule_alerts = rule_engine.evaluate_log(log)
            ueba_alerts = ueba_scorer.evaluate_log(log)

            if rule_alerts and ueba_alerts:
                # Rule hit = high risk. Merge UEBA deviations as supporting evidence.
                for rule_alert in rule_alerts:
                    for ueba_alert in ueba_alerts:
                        for dev in ueba_alert.baseline_deviations:
                            if dev not in rule_alert.baseline_deviations:
                                rule_alert.baseline_deviations.append(dev)
                        for rc in ueba_alert.reason_codes:
                            if rc not in rule_alert.reason_codes:
                                rule_alert.reason_codes.append(rc)
                batch.extend(rule_alerts)
            else:
                for alert in rule_alerts:
                    batch.append(alert)
                for alert in ueba_alerts:
                    batch.append(alert)
        except Exception:
            logger.exception("Error evaluating log %s", log.event_id)
            continue

        now_mono = time.monotonic()
        if len(batch) >= batch_max_size or (batch and now_mono - last_flush >= batch_max_seconds):
            _flush_batch(storage, batch)
            _auto_analyze_high_risk(storage, ai_analyzer, batch)
            batch.clear()
            last_flush = now_mono

        if now_mono - last_cache_refresh >= cache_refresh_interval:
            ueba_scorer.refresh_cache()
            last_cache_refresh = now_mono

    if batch:
        _flush_batch(storage, batch)
        _auto_analyze_high_risk(storage, ai_analyzer, batch)


def _flush_batch(storage: ClickHouseStorage, batch: list[AnomalyEvent]) -> None:
    try:
        storage.insert_anomalies(batch)
        logger.info("Flushed %d anomalies to ClickHouse", len(batch))
    except Exception:
        logger.exception("Failed to flush %d anomalies", len(batch))


def _auto_analyze_high_risk(
    storage: ClickHouseStorage,
    analyzer: AIAnalyzer,
    batch: list[AnomalyEvent],
) -> None:
    high_risk = [a for a in batch if a.risk_level == "high" and a.ai_status == "pending"]
    if not high_risk:
        return

    logger.info("Auto-analyzing %d high-risk anomalies with AI", len(high_risk))
    for alert in high_risk:
        try:
            baseline = storage.get_user_baseline(alert.user_id or "", tenant_id=alert.tenant_id)
            report = analyzer.analyze(event=alert, baseline=baseline)
            storage.insert_ai_judgement(report)
            storage.update_anomaly_ai_status(alert.event_id, "analyzed")
            logger.info(
                "AI analysed %s: model=%s risk=%s attack=%s mock=%s",
                alert.event_id,
                report.model_name,
                report.risk_level,
                report.attack_type,
                report.is_mock,
            )
        except Exception:
            logger.exception("AI analysis failed for %s — keeping pending for retry", alert.event_id)


def _retry_pending_analyses(storage: ClickHouseStorage, analyzer: AIAnalyzer) -> None:
    """Retry stranded high-risk pending anomalies left from a previous restart."""
    pending, total = storage.list_anomalies(
        risk_level="high", ai_status="pending", limit=100,
    )
    if not pending:
        return

    logger.info("Found %d stranded pending high-risk anomalies to re-analyze", len(pending))
    for item in pending:
        try:
            event = AnomalyEvent.model_validate(item)
        except Exception:
            logger.exception("Failed to reconstruct anomaly %s", item.get("event_id"))
            continue

        try:
            baseline = storage.get_user_baseline(event.user_id or "", tenant_id=event.tenant_id)
            report = analyzer.analyze(event=event, baseline=baseline)
            storage.insert_ai_judgement(report)
            storage.update_anomaly_ai_status(event.event_id, "analyzed")
            logger.info(
                "Retry AI analysed %s: model=%s risk=%s attack=%s mock=%s",
                event.event_id,
                report.model_name,
                report.risk_level,
                report.attack_type,
                report.is_mock,
            )
        except Exception:
            logger.exception("Retry AI analysis failed for %s — keeping pending", event.event_id)


if __name__ == "__main__":
    run_detector()
