# ClickHouse 表结构规格

本文件定义 ClickHouse 作为主存储时的表结构和设计约束。

ClickHouse 用于承载结构化日志、用户特征、baseline、异常事件、AI 研判、反馈和安全态势统计。

## 设计原则

- 核心查询字段必须显式成列。
- 动态字段可以进入 `attrs` 或 JSON 字段，但不能替代标准字段。
- 日志表以时间和租户作为主要管理维度。
- 用户行为分析优先保证按用户、日期、行为、来源聚合的效率。
- 表结构要支持 T+1 baseline 和历史窗口统计。
- 新来源判断需要持久化历史依据。
- 压缩效果以实测数据为准，不在设计中承诺固定压缩比。
- 数据契约中标为可选的字段，落库时必须使用稳定默认值或 `Nullable` 类型，避免字段语义和表结构冲突。

## 字段默认值和 Nullable 规则

ClickHouse 表结构需要同时满足两类要求。第一类是查询效率，第二类是数据契约中的可选语义。

本项目采用以下规则：

- 用于排序键和高频过滤的字段，即使在数据契约中是可选字段，也优先使用非 Nullable 类型，并设置稳定默认值。
- 字符串类可选字段默认使用空字符串，账号类型默认使用 `unknown`。
- 数值类可选字段优先使用 `Nullable`，例如 `src_port`, `dst_port`, `step_index`。
- 数组类可选字段默认使用空数组。
- JSON 类可选字段默认使用空对象。
- 默认值只表示未知或缺失，不能被解释成真实业务取值。
- 解析和入库模块必须统一这些默认值，不能在同一字段中混用 `null`、空字符串和特殊字符串表达不同语义。

## 主日志表

```sql
CREATE TABLE security_logs
(
    event_id String,
    event_time DateTime64(3),
    event_date Date MATERIALIZED toDate(event_time),
    ingest_time DateTime64(3),

    tenant_id LowCardinality(String),
    source_type LowCardinality(String),
    log_type LowCardinality(String),

    user_id String DEFAULT '',
    account_type LowCardinality(String) DEFAULT 'unknown',
    user_role LowCardinality(String) DEFAULT '',
    department LowCardinality(String) DEFAULT '',
    host String DEFAULT '',

    src_ip String DEFAULT '',
    src_port Nullable(UInt16),
    dst_ip String DEFAULT '',
    dst_port Nullable(UInt16),
    geo JSON DEFAULT '{}',

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
    attrs JSON DEFAULT '{}'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_id, event_date, user_id, src_ip, source_type, event_time)
TTL event_time + INTERVAL 90 DAY DELETE;
```

### 排序键说明

排序键优先支持以下查询：

- 按租户和时间范围查询日志。
- 按用户查询历史行为。
- 按来源 IP 分析异常来源。
- 按日志类型过滤。
- 按时间排序查看事件过程。

`user_id` 和 `src_ip` 在数据契约中可以为空，但它们是高频过滤字段，所以表中使用空字符串作为缺失默认值，而不是 `Nullable`。

### 分区说明

默认按月分区。若单日数据量显著扩大，可以追加 ADR 调整为更细粒度分区。

TTL 使用 `event_time`，分区字段也来自 `event_time`，便于后续过期数据管理。

## 日级用户特征表

```sql
CREATE TABLE ueba_user_daily_features
(
    feature_date Date,
    tenant_id LowCardinality(String),
    user_id String,
    account_type LowCardinality(String) DEFAULT 'unknown',

    login_count UInt32,
    failed_login_count UInt32,
    success_login_count UInt32,
    distinct_src_ip_count UInt32,
    distinct_host_count UInt32,
    distinct_action_count UInt32,

    first_seen_time DateTime,
    last_seen_time DateTime,

    night_event_count UInt32,
    sensitive_action_count UInt32,
    download_count UInt32,
    permission_change_count UInt32,
    new_source_count UInt32,
    maintenance_window_hit_count UInt32 DEFAULT 0,

    common_src_ips Array(String) DEFAULT [],
    common_ip_prefixes Array(String) DEFAULT [],
    common_hosts Array(String) DEFAULT [],
    common_actions Array(String) DEFAULT [],
    profile_metrics JSON DEFAULT '{}',

    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(feature_date)
ORDER BY (tenant_id, user_id, feature_date);
```

## 用户 baseline 表

用户 baseline 可以按 profile 和 feature 存储，以便扩展不同类型的统计特征。

```sql
CREATE TABLE ueba_user_baseline
(
    baseline_date Date,
    tenant_id LowCardinality(String),
    user_id String,

    profile_group LowCardinality(String),
    feature_name LowCardinality(String),

    mean_value Nullable(Float64),
    std_value Nullable(Float64),
    p50_value Nullable(Float64),
    p95_value Nullable(Float64),
    p99_value Nullable(Float64),
    common_values Array(String) DEFAULT [],
    value_histogram JSON DEFAULT '{}',

    sample_days UInt16,
    sample_count UInt32,
    baseline_confidence Float32,
    trained_from Date,
    trained_to Date,
    fallback_level LowCardinality(String) DEFAULT 'none',

    model_version String,
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(baseline_date)
ORDER BY (tenant_id, user_id, profile_group, feature_name, baseline_date);
```

`profile_group` 建议包含：

- `who`
- `time`
- `location`
- `access`
- `volume`
- `result`
- `why`

## 持久化来源历史表

新 IP、新设备和新来源地判断不得只依赖进程内存。需要至少保留一张持久化历史表。

```sql
CREATE TABLE user_seen_sources
(
    tenant_id LowCardinality(String),
    user_id String,
    source_type LowCardinality(String),
    source_key String,

    first_seen_time DateTime64(3),
    last_seen_time DateTime64(3),
    seen_count UInt32,

    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, user_id, source_type, source_key);
```

## 异常事件表

```sql
CREATE TABLE anomaly_events
(
    event_id String,
    event_time DateTime64(3),
    event_date Date MATERIALIZED toDate(event_time),
    detect_time DateTime64(3),

    tenant_id LowCardinality(String),
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
    risk_components JSON DEFAULT '{}',

    rule_hits Array(String) DEFAULT [],
    baseline_deviations JSON DEFAULT '[]',
    reason_codes Array(String) DEFAULT [],
    evidence JSON DEFAULT '{}',
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
```

`risk_level` 只使用 `low`, `medium`, `high`, `critical`。

## AI 研判表

```sql
CREATE TABLE ai_judgements
(
    judgement_id String,
    event_id String,
    created_at DateTime DEFAULT now(),

    model_name LowCardinality(String),
    model_version String DEFAULT '',

    risk_level LowCardinality(String),
    attack_type LowCardinality(String),
    judgement String,
    key_reasons Array(String),
    recommended_actions Array(String),
    confidence Float32,

    feedback_suggestions JSON DEFAULT '{}',
    raw_response JSON DEFAULT '{}',
    is_mock UInt8
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (created_at, event_id, risk_level);
```

## AI 反馈表

```sql
CREATE TABLE ai_feedback
(
    feedback_id String,
    event_id String,
    judgement_id String DEFAULT '',
    tenant_id LowCardinality(String),
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
```

## 每日简报表

```sql
CREATE TABLE daily_security_reports
(
    report_date Date,
    tenant_id LowCardinality(String),

    total_logs UInt64,
    anomaly_count UInt64,
    high_count UInt64,
    critical_count UInt64,
    overall_score Float32,

    top_risk_users Array(String),
    top_attack_types Array(String),
    key_events Array(String),
    ai_summary String DEFAULT '',
    recommended_actions Array(String) DEFAULT [],
    markdown_body String,

    created_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(report_date)
ORDER BY (tenant_id, report_date);
```

## 数据质量指标表

```sql
CREATE TABLE data_quality_metrics
(
    metric_date Date,
    tenant_id LowCardinality(String),
    source_type LowCardinality(String),

    generated_count UInt64,
    injected_anomaly_count UInt64 DEFAULT 0,
    injected_high_risk_count UInt64 DEFAULT 0,
    raw_logs_count UInt64,
    parsed_logs_count UInt64,
    clickhouse_insert_count UInt64,
    security_logs_count UInt64,

    raw_size_bytes UInt64,
    table_size_bytes UInt64,
    compression_ratio Float32,

    missing_event_time_rate Float32,
    missing_user_id_rate Float32,
    missing_src_ip_rate Float32,
    missing_action_rate Float32,
    missing_result_rate Float32,
    parse_error_rate Float32,

    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(metric_date)
ORDER BY (tenant_id, metric_date, source_type);
```

`clickhouse_insert_count` 表示写入 ClickHouse sink 的记录数，`security_logs_count` 表示最终可在 `security_logs` 中查询到的记录数。两者可能因为解析失败、去重、过滤或补写重试产生差异，但差异必须能解释。

`injected_anomaly_count` 和 `injected_high_risk_count` 来自生成器或场景适配器的注入记录，用于证明异常样本比例和高危样本比例。

## 系统指标表

```sql
CREATE TABLE system_metrics
(
    metric_time DateTime,
    component LowCardinality(String),
    metric_name LowCardinality(String),
    metric_value Float64,
    labels JSON DEFAULT '{}'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(metric_time)
ORDER BY (component, metric_name, metric_time);
```

## 表设计边界

- `security_logs` 是事实日志表，不直接存最终安全结论。
- `ueba_user_daily_features` 是 T+1 特征层，不替代 baseline。
- `ueba_user_baseline` 是历史画像层，必须记录样本量和置信度。
- `user_seen_sources` 是新来源判断依据，不应由进程内存替代。
- `anomaly_events` 是统一异常事件层，规则和 UEBA 不得向外输出两套告警对象。
- `ai_feedback` 是调优候选，不直接自动改变规则配置。
