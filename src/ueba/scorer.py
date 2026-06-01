from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from src.schemas import AnomalyEvent, NormalizedLog
from src.storage import ClickHouseStorage

# Default weights — will be overridden per-user by _adaptive_weights()
DEFAULT_WEIGHTS = {
    "time": 0.15,
    "ip": 0.25,
    "geo": 0.15,
    "access": 0.10,
    "volume": 0.20,
    "result": 0.15,
}

DEVIATION_THRESHOLD = 0.20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ip_prefix(ip: str) -> str:
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else ip


class UebaScorer:
    """6-dimension UEBA behavior deviation scorer with adaptive thresholds.

    Each dimension computes a *surprise score*: how unlikely is the observed
    behaviour given the user's historical baseline distribution?  Scores close
    to 1 mean "very surprising / anomalous"; scores near 0 mean "normal."

    Weights are *not* static — they adapt per user based on how stable each
    behavioural dimension is.  A user whose hours vary wildly gets a lower
    *time* weight; a user who logs in from only two IPs gets a higher *ip*
    weight, etc.
    """

    def __init__(self, storage: ClickHouseStorage):
        self._storage = storage
        self._cache: dict[str, dict[str, Any]] = {}

    # -- public API ----------------------------------------------------------

    def evaluate_log(self, log: NormalizedLog) -> list[AnomalyEvent]:
        if not log.user_id:
            return []

        baseline = self._get_baseline(log.user_id, log.tenant_id)
        if not baseline:
            return []

        weights = self._adaptive_weights(baseline)
        deviations = self._score_dimensions(log, baseline, weights)
        if not deviations:
            return []

        weighted_sum = sum(d["weight"] * d["score"] for d in deviations)
        max_score = max(d["score"] for d in deviations)
        combined = 0.5 * max_score + 0.5 * weighted_sum

        if combined < DEVIATION_THRESHOLD:
            return []

        if combined >= 0.75:
            risk_level = "high"
        elif combined >= 0.45:
            risk_level = "medium"
        else:
            risk_level = "low"

        risk_score = round(combined * 100)
        reason_codes = list({d["reason_code"] for d in deviations})
        baseline_deviations = [
            {"dimension": d["dimension"], "reason": d["reason"], "score": round(d["score"], 2)}
            for d in deviations
        ]

        return [
            AnomalyEvent(
                event_id=str(uuid.uuid4()),
                event_time=log.event_time,
                detect_time=_now(),
                tenant_id=log.tenant_id,
                user_id=log.user_id,
                src_ip=log.src_ip,
                host=log.host,
                source_type=log.source_type,
                action=log.action,
                object_type=log.object_type,
                object_id=log.object_id,
                attack_type=None,
                risk_score=float(risk_score),
                risk_level=risk_level,
                risk_components={"baseline_score": risk_score},
                rule_hits=[],
                baseline_deviations=baseline_deviations,
                reason_codes=reason_codes,
                evidence=self._build_evidence(log, deviations),
                related_event_ids=[log.event_id],
                scenario_id=log.scenario_id,
                scenario_type=log.scenario_type,
                attack_chain_id=log.attack_chain_id,
                ai_status="pending" if risk_level in ("high",) else "not_required",
                status="new",
                created_at=_now(),
            )
        ]

    # -- adaptive weights ----------------------------------------------------

    def _adaptive_weights(self, baseline: dict[str, Any]) -> dict[str, float]:
        """Compute per-dimension weights from baseline stability.

        Stable dimensions get higher weight (deviation is more meaningful).
        Volatile dimensions get lower weight (deviation is expected).
        """

        time_profile = baseline.get("time_profile") or {}
        loc_profile = baseline.get("location_profile") or {}
        access_profile = baseline.get("access_profile") or {}
        result_profile = baseline.get("result_profile") or {}

        # -- time stability: entropy of hour histogram --------------------
        hour_hist = self._feature_hist(time_profile.get("hour_histogram"))
        time_entropy = _normalized_entropy(hour_hist) if hour_hist else 0.5
        time_stability = 1.0 - time_entropy  # high entropy → low stability

        # -- IP stability: fewer distinct IPs → more stable ----------------
        distinct_ips = self._feature_val(loc_profile.get("distinct_src_ip_count"))
        ip_stability = _stability_from_count(distinct_ips, cap=100)

        # -- access stability: fewer unique actions/resources → more stable
        common_actions = self._feature_list(access_profile.get("common_actions"))
        common_resources = self._feature_list(access_profile.get("common_resources"))
        access_diversity = max(len(common_actions), len(common_resources), 1)
        access_stability = _stability_from_count(float(access_diversity), cap=20)

        # -- result stability: success rate near 0 or 1 → very stable -----
        success_rate = self._feature_val(result_profile.get("login_success_rate"))
        fail_rate = self._feature_val(result_profile.get("login_failed_rate"))
        result_rate = max(success_rate, fail_rate, 0.5)
        result_stability = abs(result_rate - 0.5) * 2  # 1.0 if 0/100%, 0 if 50%

        # -- volume stability: from event count (placeholder) --------------
        volume_profile = baseline.get("volume_profile") or {}
        event_count = self._feature_val(volume_profile.get("event_count")) or 1
        vol_stability = _stability_from_count(event_count, cap=1000)

        # Blend with defaults: weighted avg (70% adaptive, 30% default)
        defaults = DEFAULT_WEIGHTS
        stability = {
            "time": 0.7 * time_stability + 0.3,
            "ip": 0.7 * ip_stability + 0.3,
            "geo": 0.7 * ip_stability + 0.3,  # geo correlates with IP diversity
            "access": 0.7 * access_stability + 0.3,
            "volume": 0.7 * vol_stability + 0.3,
            "result": 0.7 * result_stability + 0.3,
        }

        # Normalise weights to sum to 1
        total = sum(stability[d] * defaults[d] for d in defaults)
        if total <= 0:
            return dict(defaults)

        return {d: stability[d] * defaults[d] / total for d in defaults}

    # -- per-dimension scoring ----------------------------------------------

    def _score_dimensions(
        self, log: NormalizedLog, baseline: dict[str, Any], weights: dict[str, float]
    ) -> list[dict[str, Any]]:
        deviations: list[dict[str, Any]] = []

        for scorer in [
            self._score_time,
            self._score_ip,
            self._score_geo,
            self._score_access,
            self._score_volume,
            self._score_result,
        ]:
            result = scorer(log, baseline)
            if result:
                result["weight"] = weights.get(result["dimension"], DEFAULT_WEIGHTS.get(result["dimension"], 0.1))
                deviations.append(result)

        return deviations

    # --- time ----------------------------------------------------------------

    def _score_time(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        """Score based on how unusual this hour is in the user's distribution."""
        time_profile = baseline.get("time_profile") or {}
        hour_hist = self._feature_hist(time_profile.get("hour_histogram"))

        if not hour_hist:
            # Fall back to active_hours range check
            active_hours = self._feature_list(time_profile.get("active_hours"))
            if not active_hours:
                return None
            event_hour = log.event_time.hour
            if self._hour_in_ranges(event_hour, active_hours):
                return None
            return {
                "dimension": "time",
                "score": 0.5,
                "reason_code": "rare_login_hour",
                "reason": f"event_hour={event_hour} outside active_hours={active_hours}",
            }

        total = sum(hour_hist.values())
        if total <= 0:
            return None

        event_hour_key = str(log.event_time.hour)
        event_count = hour_hist.get(event_hour_key, 0)

        # P(observing this hour or fewer events) — left-tail percentile
        count_lte = sum(v for k, v in hour_hist.items() if int(k) <= log.event_time.hour)
        percentile = count_lte / total

        # Surprise: 1 - probability mass at-or-below this hour
        # Uniform distribution → 24 bins → each ~4.2% → percentile range 0-1
        # Very low percentile → high score
        if percentile >= 0.05:  # not rare enough
            return None

        # Map percentile to score: 0% → 1.0, 5% → 0.4
        score = 1.0 - (percentile / 0.05) * 0.6
        score = max(0.25, min(1.0, score))

        return {
            "dimension": "time",
            "score": round(score, 2),
            "reason_code": "rare_login_hour",
            "reason": (
                f"event_hour={log.event_time.hour} at {percentile:.1%} percentile "
                f"(count={event_count}, total={total})"
            ),
        }

    # --- IP ------------------------------------------------------------------

    def _score_ip(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        if not log.src_ip:
            return None

        loc_profile = baseline.get("location_profile") or {}
        common_ips = self._feature_list(loc_profile.get("common_ips"))
        common_ip_prefixes = self._feature_list(loc_profile.get("common_ip_prefixes"))

        src_ip = str(log.src_ip)
        if src_ip in common_ips:
            return None

        # How diverse is this user's IP usage?
        distinct_ip_count = self._feature_val(loc_profile.get("distinct_src_ip_count"))
        known_count = max(len(common_ips), 1)

        prefix = _ip_prefix(src_ip)
        same_subnet = prefix in common_ip_prefixes if common_ip_prefixes else False

        # Base: how surprising is a *new* IP?
        # If user has N known IPs, P(new) ≈ 1/(N+1) for a stable user
        # For very diverse users (N large), a new IP is not surprising
        p_new = 1.0 / (known_count + 1)

        # Scale: high diversity → lower surprise
        diversity_factor = _stability_from_count(distinct_ip_count or known_count, cap=50)

        base_score = 1.0 - p_new  # ~0.5 for 1 known IP, ~0.09 for 10 known IPs
        if same_subnet:
            base_score *= 0.5

        score = base_score * diversity_factor + 0.1 * (1 - diversity_factor)
        score = max(0.15, min(1.0, score))

        return {
            "dimension": "ip",
            "score": round(score, 2),
            "reason_code": "new_source_ip",
            "reason": (
                f"src_ip={src_ip} not in {known_count} known IPs"
                + (f" (same /24, prefix={prefix})" if same_subnet else "")
            ),
        }

    # --- geo -----------------------------------------------------------------

    def _score_geo(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        geo = log.geo or {}
        if not geo:
            return None

        loc_profile = baseline.get("location_profile") or {}
        common_cities = self._feature_list(loc_profile.get("common_cities"))

        log_city = geo.get("city") or geo.get("region")
        if not log_city:
            return None

        if not common_cities:
            # No geo baseline → can't judge
            return None

        if log_city in common_cities:
            return None

        # Surprise: P(new city) ≈ 1/(N+1)
        known_count = len(common_cities)
        p_new = 1.0 / (known_count + 1)
        score = max(0.3, 1.0 - p_new)

        return {
            "dimension": "geo",
            "score": round(score, 2),
            "reason_code": "geo_deviation",
            "reason": f"geo={log_city} outside {known_count} known locations",
        }

    # --- access --------------------------------------------------------------

    def _score_access(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        access_profile = baseline.get("access_profile") or {}
        common_resources = self._feature_list(access_profile.get("common_resources"))
        common_actions = self._feature_list(access_profile.get("common_actions"))
        common_uas = self._feature_list(access_profile.get("common_user_agents"))

        deviations: list[tuple[str, float]] = []

        resource = log.resource
        if resource and common_resources and resource not in common_resources:
            is_sensitive = any(
                kw in resource.lower()
                for kw in ("export", "download", "admin", "sensitive", "config", "backup")
            )
            # P(new resource) ≈ 1/(N+1)
            p_new = 1.0 / (len(common_resources) + 1)
            base = 1.0 - p_new
            score = min(1.0, base * (1.5 if is_sensitive else 0.7))
            deviations.append((f"resource={resource}", score))

        action = log.action
        if action and common_actions and action not in common_actions:
            p_new = 1.0 / (len(common_actions) + 1)
            score = 1.0 - p_new
            deviations.append((f"action={action}", min(1.0, score * 0.8)))

        ua = log.user_agent
        if ua and common_uas and ua not in common_uas:
            p_new = 1.0 / (len(common_uas) + 1)
            score = 1.0 - p_new
            deviations.append(("user_agent", min(1.0, score * 0.6)))

        if not deviations:
            return None

        score = max(s for _, s in deviations)
        reasons = [r for r, _ in deviations]

        return {
            "dimension": "access",
            "score": round(score, 2),
            "reason_code": "unusual_access_pattern",
            "reason": "; ".join(reasons),
        }

    # --- volume --------------------------------------------------------------

    def _score_volume(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        """Score based on per-event volume signals.

        Full volume scoring needs an aggregation window; here we flag
        extreme per-event metrics (e.g. unusually large download).
        """
        # Per-event check: if the log has bytes_sent / bytes_recv we could check,
        # but NormalizedLog doesn't carry these.  Deferred to window aggregation.
        return None

    # --- result --------------------------------------------------------------

    def _score_result(self, log: NormalizedLog, baseline: dict[str, Any]) -> dict | None:
        result_profile = baseline.get("result_profile") or {}

        if log.action == "login" and log.result == "fail":
            failed_rate_field = result_profile.get("login_failed_rate")
            if failed_rate_field is None:
                return None

            failed_rate = self._feature_val(failed_rate_field)
            if failed_rate > 0.25:
                # Frequent failures → not anomalous
                return None

            # Surprise = how unlikely a failure is: 1 - P(failure)
            # Normalize to [0, 1]: very low failure rate → high surprise
            score = 1.0 - failed_rate * 2  # 0%→1.0, 25%→0.5
            score = max(0.3, min(1.0, score))

            return {
                "dimension": "result",
                "score": round(score, 2),
                "reason_code": "unusual_login_failure",
                "reason": f"login failed vs baseline failed_rate={failed_rate:.2%}",
            }

        if log.action == "login" and log.result == "success":
            success_rate_field = result_profile.get("login_success_rate")
            if success_rate_field is None:
                return None

            success_rate = self._feature_val(success_rate_field)
            if success_rate > 0.25:
                return None  # Success is normal

            # Low success rate → success is surprising
            score = 1.0 - success_rate * 2
            score = max(0.3, min(1.0, score))

            return {
                "dimension": "result",
                "score": round(score, 2),
                "reason_code": "unusual_login_success",
                "reason": f"login success vs baseline success_rate={success_rate:.2%}",
            }

        return None

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _feature_val(value: Any) -> float:
        """Extract a scalar from a baseline field (plain or stats-wrapped)."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, dict):
            mv = value.get("mean_value")
            if isinstance(mv, (int, float)) and mv is not None:
                return float(mv)
            # Fallback: value_histogram may contain {mean, std, p50, p95, p99}
            vh = value.get("value_histogram")
            if isinstance(vh, dict):
                m = vh.get("mean") or vh.get("mean_value")
                if isinstance(m, (int, float)) and m is not None:
                    return float(m)
        return 0.0

    @staticmethod
    def _feature_list(value: Any) -> list[str]:
        """Extract a list from a baseline field (plain or stats-wrapped)."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, dict):
            cv = value.get("common_values")
            if isinstance(cv, list):
                return [str(v) for v in cv]
        return []

    @staticmethod
    def _feature_hist(value: Any) -> dict[str, int] | None:
        """Extract a value histogram from a stats-wrapped baseline field."""
        if value is None:
            return None
        if isinstance(value, dict):
            vh = value.get("value_histogram")
            if isinstance(vh, dict) and vh:
                # Exclude stat-only histograms (mean/std/p50/p95/p99)
                stat_keys = {"mean", "std", "p50", "p95", "p99"}
                if all(k in stat_keys for k in vh):
                    return None
                return {str(k): int(v) for k, v in vh.items() if isinstance(v, (int, float))}
        return None

    def _get_baseline(self, user_id: str, tenant_id: str) -> dict[str, Any] | None:
        cache_key = f"{tenant_id}:{user_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        item = self._storage.get_user_baseline(user_id, tenant_id=tenant_id)
        if item:
            self._cache[cache_key] = item
        return item

    def refresh_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _hour_in_ranges(hour: int, ranges: list[str]) -> bool:
        for r in ranges:
            parsed = _parse_hour_range(r)
            if parsed is None:
                continue
            start, end = parsed
            if start <= end and start <= hour < end:
                return True
            if start > end and (hour >= start or hour < end):
                return True
        return False

    @staticmethod
    def _build_evidence(log: NormalizedLog, deviations: list[dict]) -> dict[str, Any]:
        return {
            "user_id": log.user_id,
            "src_ip": log.src_ip,
            "action": log.action,
            "resource": log.resource,
            "result": log.result,
            "event_hour": log.event_time.hour,
            "deviation_summary": [d["reason"] for d in deviations],
        }


# -- module-level helpers ----------------------------------------------------


def _parse_hour_range(value: str) -> tuple[int, int] | None:
    try:
        start, end = value.split("-", 1)
        return int(start.split(":", 1)[0]), int(end.split(":", 1)[0])
    except (ValueError, IndexError):
        return None


def _normalized_entropy(hist: dict[str, int]) -> float:
    """0..1 entropy of a count histogram (0 = single bin, 1 = uniform)."""
    total = sum(hist.values())
    if total <= 0:
        return 0.0
    n_bins = len(hist)
    if n_bins <= 1:
        return 0.0
    max_entropy = math.log(n_bins)
    if max_entropy <= 0:
        return 0.0
    entropy = 0.0
    for count in hist.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log(p)
    return entropy / max_entropy


def _stability_from_count(count: float, cap: float = 100) -> float:
    """Map a diversity count to a stability score [0, 1].

    Low count → high stability (e.g. 1 known IP → 1.0).
    High count → low stability (e.g. 100 known IPs → 0.0).
    """
    if count <= 0:
        return 0.5
    # Exponential decay: stability drops as count grows
    return max(0.05, math.exp(-count / (cap / 3)))
