CREATE DATABASE IF NOT EXISTS log_ai;

CREATE TABLE IF NOT EXISTS log_ai.security_logs
(
    event_id String,
    event_time DateTime64(3),
    event_date Date MATERIALIZED toDate(event_time),
    ingest_time DateTime64(3),
    tenant_id LowCardinality(String) DEFAULT 'default',
    source_type LowCardinality(String),
    log_type LowCardinality(String) DEFAULT '',
    user_id String DEFAULT '',
    account_type LowCardinality(String) DEFAULT 'unknown',
    user_role LowCardinality(String) DEFAULT '',
    department LowCardinality(String) DEFAULT '',
    host String DEFAULT '',
    src_ip String DEFAULT '',
    src_port Nullable(UInt16),
    dst_ip String DEFAULT '',
    dst_port Nullable(UInt16),
    geo String DEFAULT '{}',
    action LowCardinality(String),
    object_type LowCardinality(String) DEFAULT '',
    object_id String DEFAULT '',
    resource String DEFAULT '',
    result LowCardinality(String),
    severity UInt8 DEFAULT 0,
    user_agent String DEFAULT '',
    protocol LowCardinality(String) DEFAULT '',
    auth_method LowCardinality(String) DEFAULT '',
    session_id String DEFAULT '',
    trace_id String DEFAULT '',
    scenario_id String DEFAULT '',
    scenario_type LowCardinality(String) DEFAULT '',
    attack_chain_id String DEFAULT '',
    step_index Nullable(UInt16),
    injected_label LowCardinality(String) DEFAULT '',
    message String,
    raw_log String,
    risk_tags Array(String) DEFAULT [],
    attrs String DEFAULT '{}'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_id, event_date, user_id, src_ip, source_type, event_time)
TTL toDateTime(event_time) + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS log_ai.anomaly_events
(
    event_id String,
    event_time DateTime64(3),
    event_date Date MATERIALIZED toDate(event_time),
    detect_time DateTime64(3),
    tenant_id LowCardinality(String) DEFAULT 'default',
    user_id String DEFAULT '',
    src_ip String DEFAULT '',
    host String DEFAULT '',
    source_type LowCardinality(String) DEFAULT '',
    action LowCardinality(String) DEFAULT '',
    object_type LowCardinality(String) DEFAULT '',
    object_id String DEFAULT '',
    attack_type LowCardinality(String) DEFAULT 'unknown',
    risk_score Float32,
    risk_level LowCardinality(String),
    risk_components String DEFAULT '{}',
    rule_hits Array(String) DEFAULT [],
    baseline_deviations String DEFAULT '[]',
    reason_codes Array(String) DEFAULT [],
    evidence String DEFAULT '{}',
    related_event_ids Array(String) DEFAULT [],
    scenario_id String DEFAULT '',
    scenario_type LowCardinality(String) DEFAULT '',
    attack_chain_id String DEFAULT '',
    ai_status LowCardinality(String) DEFAULT 'not_required',
    status LowCardinality(String) DEFAULT 'new',
    model_version String DEFAULT '',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_id, event_date, risk_level, risk_score, user_id, event_time);

CREATE TABLE IF NOT EXISTS log_ai.ueba_user_daily_features
(
    feature_date Date,
    tenant_id LowCardinality(String) DEFAULT 'default',
    user_id String,
    account_type LowCardinality(String) DEFAULT 'unknown',
    login_count UInt32 DEFAULT 0,
    failed_login_count UInt32 DEFAULT 0,
    success_login_count UInt32 DEFAULT 0,
    distinct_src_ip_count UInt32 DEFAULT 0,
    distinct_host_count UInt32 DEFAULT 0,
    distinct_action_count UInt32 DEFAULT 0,
    first_seen_time DateTime,
    last_seen_time DateTime,
    night_event_count UInt32 DEFAULT 0,
    sensitive_action_count UInt32 DEFAULT 0,
    download_count UInt32 DEFAULT 0,
    permission_change_count UInt32 DEFAULT 0,
    new_source_count UInt32 DEFAULT 0,
    maintenance_window_hit_count UInt32 DEFAULT 0,
    common_src_ips Array(String) DEFAULT [],
    common_ip_prefixes Array(String) DEFAULT [],
    common_hosts Array(String) DEFAULT [],
    common_actions Array(String) DEFAULT [],
    profile_metrics String DEFAULT '{}',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(feature_date)
ORDER BY (tenant_id, user_id, feature_date);

CREATE TABLE IF NOT EXISTS log_ai.ueba_user_baseline
(
    baseline_date Date,
    tenant_id LowCardinality(String) DEFAULT 'default',
    user_id String,
    profile_group LowCardinality(String),
    feature_name LowCardinality(String),
    mean_value Nullable(Float64),
    std_value Nullable(Float64),
    p50_value Nullable(Float64),
    p95_value Nullable(Float64),
    p99_value Nullable(Float64),
    common_values Array(String) DEFAULT [],
    value_histogram String DEFAULT '{}',
    sample_days UInt16 DEFAULT 0,
    sample_count UInt32 DEFAULT 0,
    baseline_confidence Float32 DEFAULT 0,
    trained_from Date,
    trained_to Date,
    fallback_level LowCardinality(String) DEFAULT 'none',
    model_version String DEFAULT '',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(baseline_date)
ORDER BY (tenant_id, user_id, profile_group, feature_name, baseline_date);

CREATE TABLE IF NOT EXISTS log_ai.ai_judgements
(
    judgement_id String,
    event_id String,
    created_at DateTime DEFAULT now(),
    model_name LowCardinality(String),
    model_version String DEFAULT '',
    risk_level LowCardinality(String),
    attack_type LowCardinality(String),
    judgement String,
    key_reasons Array(String) DEFAULT [],
    recommended_actions Array(String) DEFAULT [],
    confidence Float32,
    feedback_suggestions String DEFAULT '{}',
    raw_response String DEFAULT '{}',
    is_mock UInt8 DEFAULT 0
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (created_at, event_id, risk_level);

CREATE TABLE IF NOT EXISTS log_ai.ai_feedback
(
    feedback_id String,
    event_id String,
    judgement_id String DEFAULT '',
    tenant_id LowCardinality(String) DEFAULT 'default',
    user_id String DEFAULT '',
    feedback_type LowCardinality(String),
    suggestion String,
    target_component LowCardinality(String),
    confidence Float32,
    review_status LowCardinality(String),
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, created_at, target_component, review_status);
