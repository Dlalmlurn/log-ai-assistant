# Data Contract

本文件定义正式数据契约。生产、消费、入库、API 和前端展示都必须遵守这里的字段语义。

## Kafka Topics

| Topic | 用途 | 正式性 | 生产者 | 消费者 |
| --- | --- | --- | --- | --- |
| `raw_logs` | 原始日志流 | 正式 | Filebeat | Flink raw parser |
| `parsed_logs` | 标准化日志流 | 正式 | Flink | ES sink / detection service |
| `alert_events` | 异常事件流 | 正式 | detection service / Flink rules | ES sink / AI analyzer |
| `ai_reports` | AI 研判结果 | 正式 | AI analyzer | ES sink / API |
| `system_metrics` | 系统指标预留 | 预留 | health collector | API / dashboard |

Python Producer 可以写入 `raw_logs`，但只作为调试兜底。

## Elasticsearch Indices

| Index | 用途 | 对应模型 |
| --- | --- | --- |
| `security-logs` | 标准化日志 | `NormalizedLog` |
| `security-alerts` | 异常事件 | `AlertEvent` |
| `user-baselines` | 用户行为基线 | `UserBaseline` |
| `ai-reports` | AI 研判报告 | `AIReport` |
| `daily-reports` | 每日安全态势简报 | `DailyReport` |

## Normalized Log

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 标准化后生成的唯一事件 ID。 |
| `event_time` | 是 | datetime | 日志原始发生时间。 |
| `ingest_time` | 是 | datetime | 系统采集/处理入库时间。 |
| `source_type` | 是 | enum | `vpn`, `oa`, `api`, `system`, `security_device`。 |
| `username` | 否 | string | 用户名或账号。 |
| `src_ip` | 否 | ip | 来源 IP。 |
| `src_port` | 否 | integer | 来源端口。 |
| `dst_ip` | 否 | ip | 目标 IP。 |
| `dst_port` | 否 | integer | 目标端口。 |
| `action` | 是 | string | 归一化行为，例如 `login`, `api_call`, `download`, `access`。 |
| `resource` | 否 | string | 访问资源、接口、网关或目标系统。 |
| `status` | 是 | string | `success`, `failed`, `denied`, `error` 等。 |
| `message` | 是 | text | 可读摘要。 |
| `raw_message` | 是 | text | 原始日志内容或原始 JSON。 |
| `risk_tags` | 否 | string[] | 原始日志或解析阶段带出的风险标签。 |
| `trace_id` | 否 | string | 会话 ID、请求 ID 或链路追踪 ID。 |
| `original_fields` | 否 | object | 原始字段保留区。 |

## Alert Event

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `alert_id` | 是 | string | 唯一告警 ID。 |
| `event_time` | 是 | datetime | 关联日志发生时间。 |
| `detect_time` | 是 | datetime | 检测时间。 |
| `username` | 否 | string | 相关用户。 |
| `src_ip` | 否 | ip | 相关来源 IP。 |
| `source_type` | 是 | enum | 日志类型。 |
| `risk_level` | 是 | enum | `低`, `中`, `高`, `紧急`。 |
| `risk_score` | 是 | integer | 0-100 风险分。 |
| `rule_hits` | 是 | string[] | 命中的规则名称。 |
| `baseline_deviations` | 否 | object[] | 偏离用户基线的证据，后续实现必须补齐。 |
| `evidence` | 是 | object | 规则证据、窗口统计、字段取值。 |
| `related_event_ids` | 是 | string[] | 相关日志 ID 列表。 |
| `related_logs_summary` | 否 | text | 面向 AI 和页面的摘要。 |
| `status` | 是 | string | `new`, `analyzed`, `closed` 等。 |
| `llm_analysis_id` | 否 | string | 对应 AI 报告 ID。 |

当前代码只支持 `低/中/高`，后续要扩展 `紧急`，并保持前后端一致。

## User Baseline

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `username` | 是 | string | 用户名。 |
| `active_hours` | 是 | string[] | 常见活跃时间段。 |
| `common_ips` | 是 | string[] | 常用 IP 或网段。 |
| `common_user_agents` | 否 | string[] | 常见客户端。 |
| `avg_api_calls_per_minute` | 是 | float | 平均 API 调用频率。 |
| `common_resources` | 否 | string[] | 常访问资源。 |
| `failed_login_count_7d` | 是 | integer | 7 日失败登录数。 |
| `sensitive_access_rate` | 是 | float | 敏感访问占比。 |
| `updated_at` | 是 | datetime | 基线更新时间。 |

## AI Report

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `ai_report_id` | 是 | string | AI 报告 ID。 |
| `alert_id` | 是 | string | 关联告警 ID。 |
| `created_at` | 是 | datetime | 生成时间。 |
| `attack_type` | 是 | string | 攻击类型。 |
| `risk_level` | 是 | enum | AI 研判后的风险等级。 |
| `reason` | 是 | text | 判断依据。 |
| `suggestion` | 是 | text | 处置建议。 |
| `confidence` | 是 | float | 0-1 置信度。 |
| `next_steps` | 否 | string[] | 后续动作。 |
| `raw_response` | 否 | object | 模型原始响应。 |

## Daily Report

日报必须包含日期、总体安全评分、日志总量、异常数量、高危数量、主要风险、高危用户、典型事件、AI 总结、处置建议和 Markdown 正文。

## Time Semantics

- `event_time`: 原始日志发生时间，用于安全分析。
- `ingest_time`: 系统接收或入库时间，用于实时链路健康检查。
- `detect_time`: 告警生成时间，用于告警排序和处理时效。
- `created_at`: 报告生成时间。
