# 数据契约

本文件定义系统中的正式数据对象、字段语义和消息流。

生产者、消费者、ClickHouse 表、FastAPI 接口和前端页面都必须遵守本契约。

## 命名原则

- 时间字段统一使用 UTC 或明确标注时区。
- 外部接口字段使用 snake_case。
- 事件类对象必须有唯一 ID。
- 结构化日志的核心字段必须显式成列。
- 动态字段进入 `attrs` 或 `raw_log`，不能替代核心字段。
- 字段含义必须稳定，不能在不同模块中复用同名字段表达不同含义。
- 风险等级内部统一使用英文枚举，前端可以映射为中文展示。
- `ReasonCode` 以本文注册表为准，检测与评分文档只能引用已登记的 code。

## Kafka Topics

| Topic | 用途 | 生产者 | 消费者 |
| --- | --- | --- | --- |
| `raw_logs` | 原始日志流。 | Filebeat | Flink parser |
| `parsed_logs` | 标准化日志流。 | Flink | ClickHouse sink、检测服务 |
| `rule_hits` | 轻量规则命中结果。 | Flink、检测服务 | anomaly builder |
| `anomaly_events` | 统一异常事件流。 | anomaly builder | AI 候选筛选、API 服务 |
| `ai_judgements` | AI 研判结果。 | AI 服务 | ClickHouse sink、API 服务 |
| `ai_feedback` | AI 或人工反馈。 | AI 服务、分析人员 | feedback processor |
| `system_metrics` | 系统状态指标。 | health collector | API 服务 |

Python Producer 可以写入测试性输入，但只作为辅助工具，不作为正式采集入口。

## RiskLevel

内部风险等级统一为：

| 枚举 | 展示建议 | 含义 |
| --- | --- | --- |
| `low` | 低 | 单一弱信号或轻微偏离。 |
| `medium` | 中 | 明显偏离或多个弱信号。 |
| `high` | 高 | 多项异常叠加或涉及敏感资源。 |
| `critical` | 紧急 | 疑似攻击正在发生或影响重大。 |

数据表、API 和 AI 输出都使用英文枚举。中文只作为展示映射。

## NormalizedLog

标准化日志是所有行为分析的基础。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 标准化后生成的唯一事件 ID。 |
| `event_time` | 是 | datetime | 原始日志发生时间。 |
| `ingest_time` | 是 | datetime | 系统接收或入库时间。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `source_type` | 是 | enum | `vpn`, `oa`, `api`, `system`, `file`, `database`, `security_device`。 |
| `log_type` | 是 | string | 细分日志类型。 |
| `user_id` | 否 | string | 用户、账号或服务账号。 |
| `account_type` | 否 | string | `employee`, `admin`, `ops`, `service`, `external` 等。 |
| `user_role` | 否 | string | 用户角色。 |
| `department` | 否 | string | 部门或组织信息。 |
| `host` | 否 | string | 主机名或设备名。 |
| `src_ip` | 否 | string | 来源 IP。 |
| `src_port` | 否 | integer | 来源端口。 |
| `dst_ip` | 否 | string | 目标 IP。 |
| `dst_port` | 否 | integer | 目标端口。 |
| `geo` | 否 | object | 地理位置或来源区域。 |
| `action` | 是 | string | 归一化行为，例如 `login`, `download`, `permission_change`。 |
| `object_type` | 否 | string | 被访问对象类型，例如 `file`, `api`, `database`, `host`。 |
| `object_id` | 否 | string | 被访问对象 ID。 |
| `resource` | 否 | string | 资源路径、接口、系统名或文件名。 |
| `result` | 是 | enum | `success`, `fail`, `denied`, `error`。 |
| `severity` | 否 | integer | 原始日志严重级别，建议范围 0 到 10。 |
| `user_agent` | 否 | string | 客户端或 User-Agent。 |
| `protocol` | 否 | string | 协议，例如 `http`, `ssh`, `vpn`, `rdp`。 |
| `auth_method` | 否 | string | 认证方式。 |
| `session_id` | 否 | string | 会话 ID。 |
| `trace_id` | 否 | string | 请求链路 ID。 |
| `scenario_id` | 否 | string | 数据生成或攻击场景 ID。真实业务日志可为空。 |
| `scenario_type` | 否 | string | 数据生成或攻击场景类型，例如 `bruteforce`, `account_takeover`, `normal_login`。真实业务日志可为空。 |
| `attack_chain_id` | 否 | string | 同一攻击过程的关联 ID。真实业务日志可为空。 |
| `step_index` | 否 | integer | 攻击过程中的步骤序号。 |
| `injected_label` | 否 | string | 生成数据中的标签，例如 `normal`, `suspicious`, `attack`。真实业务日志可为空。 |
| `message` | 是 | string | 可读摘要。 |
| `raw_log` | 是 | string | 原始日志文本或原始 JSON。 |
| `risk_tags` | 否 | array | 解析阶段产生的风险标签。 |
| `attrs` | 否 | object | 原始字段和扩展字段。 |

## VPN 字段映射

VPN 日志可以作为第一类结构化日志来源，但不是项目全部日志来源。

| 五W1H | VPN 字段示例 | 说明 |
| --- | --- | --- |
| Who | `user_id`, `department`, `user_role`, `account_type` | 谁在登录或使用 VPN。 |
| When | `event_time` | 行为发生时间。 |
| Where | `src_ip`, `geo`, `dst_ip`, `resource` | 来源和目标位置。 |
| What | `action`, `result`, `log_type` | 登录、失败、登出或会话行为。 |
| Why | `risk_tags`, `fail_reason`, `attrs.context` | 失败原因、风险标签或业务上下文。 |
| How | `protocol`, `auth_method`, `user_agent`, `session_id` | 使用的协议、认证方式和客户端。 |

## UserDailyFeature

日级用户特征用于 T+1 baseline。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `feature_date` | 是 | date | 特征所属日期。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `user_id` | 是 | string | 用户或账号。 |
| `account_type` | 否 | string | 账号类型。 |
| `login_count` | 是 | integer | 登录次数。 |
| `failed_login_count` | 是 | integer | 登录失败次数。 |
| `success_login_count` | 是 | integer | 登录成功次数。 |
| `distinct_src_ip_count` | 是 | integer | 不同来源 IP 数。 |
| `distinct_host_count` | 是 | integer | 不同主机数。 |
| `distinct_action_count` | 是 | integer | 不同行为数。 |
| `first_seen_time` | 是 | datetime | 当日首次活跃时间。 |
| `last_seen_time` | 是 | datetime | 当日最后活跃时间。 |
| `night_event_count` | 是 | integer | 夜间行为次数。 |
| `sensitive_action_count` | 是 | integer | 敏感行为次数。 |
| `download_count` | 是 | integer | 下载次数。 |
| `permission_change_count` | 是 | integer | 权限变更次数。 |
| `new_source_count` | 是 | integer | 相对历史的新增来源数量。 |
| `maintenance_window_hit_count` | 否 | integer | 命中维护窗口的行为数。 |
| `profile_metrics` | 否 | object | 当日 profile 摘要。 |
| `created_at` | 是 | datetime | 特征生成时间。 |

## UserBaseline

用户 baseline 表示历史正常行为画像。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `baseline_date` | 是 | date | baseline 生效日期。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `user_id` | 是 | string | 用户或账号。 |
| `model_version` | 是 | string | baseline 版本。 |
| `trained_from` | 是 | date | 训练窗口开始日期。 |
| `trained_to` | 是 | date | 训练窗口结束日期。 |
| `sample_days` | 是 | integer | 样本天数。 |
| `sample_count` | 是 | integer | 样本事件或样本特征数量。 |
| `baseline_confidence` | 是 | float | baseline 置信度，范围 0 到 1。 |
| `who_profile` | 是 | object | 用户、角色、部门、账号类型和 peer group。 |
| `time_profile` | 是 | object | 小时分布、星期分布、常见活跃时间段。 |
| `location_profile` | 是 | object | 常用 IP、网段、国家、城市、网关。 |
| `access_profile` | 是 | object | 常用协议、认证方式、客户端、资源。 |
| `volume_profile` | 是 | object | 会话时长、下载量、上传量、请求量等统计。 |
| `result_profile` | 是 | object | 成功率、失败率、错误率等结果分布。 |
| `why_profile` | 否 | object | 维护窗口、白名单、工单或业务上下文。 |
| `fallback_level` | 否 | enum | `none`, `peer_group`, `department`, `global`。 |
| `created_at` | 是 | datetime | 生成时间。 |

生成器中的用户画像不得直接写入 `UserBaseline` 作为系统结论。`UserBaseline` 必须来自入库后的历史日志和日级特征。

## SeenSource

新来源判断必须基于持久化历史，而不是检测进程内存。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `user_id` | 是 | string | 用户或账号。 |
| `source_key` | 是 | string | 来源标识，例如 IP、网段、设备、国家城市组合。 |
| `source_type` | 是 | enum | `ip`, `ip_prefix`, `device`, `geo`, `host`。 |
| `first_seen_time` | 是 | datetime | 首次出现时间。 |
| `last_seen_time` | 是 | datetime | 最近出现时间。 |
| `seen_count` | 是 | integer | 历史出现次数。 |

## AnomalyEvent

异常事件是规则、窗口统计、baseline 偏离和评分后的统一业务对象。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `event_id` | 是 | string | 异常事件 ID。 |
| `event_time` | 是 | datetime | 异常发生时间。 |
| `detect_time` | 是 | datetime | 异常生成时间。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `user_id` | 否 | string | 相关用户。 |
| `src_ip` | 否 | string | 相关来源 IP。 |
| `host` | 否 | string | 相关主机。 |
| `source_type` | 否 | string | 相关日志来源类型。 |
| `action` | 否 | string | 相关行为。 |
| `object_type` | 否 | string | 相关对象类型。 |
| `object_id` | 否 | string | 相关对象 ID。 |
| `attack_type` | 否 | string | 检测系统推断的攻击类型。 |
| `risk_score` | 是 | float | 0 到 100 风险分。 |
| `risk_level` | 是 | enum | `low`, `medium`, `high`, `critical`。 |
| `risk_components` | 是 | object | 规则强度、baseline 偏离、敏感度、关联度、反馈修正。 |
| `rule_hits` | 是 | array | 命中的规则 ID。 |
| `baseline_deviations` | 是 | array | baseline 偏离证据。 |
| `reason_codes` | 是 | array | 可解释原因编码。 |
| `evidence` | 是 | object | 证据包。 |
| `related_event_ids` | 是 | array | 相关日志 ID 列表。 |
| `scenario_id` | 否 | string | 生成数据中的场景 ID。真实业务日志可为空。 |
| `scenario_type` | 否 | string | 生成数据中的场景类型。真实业务日志可为空。 |
| `attack_chain_id` | 否 | string | 关联攻击过程 ID。真实业务日志可为空。 |
| `ai_status` | 是 | enum | `not_required`, `pending`, `analyzed`, `failed`。 |
| `status` | 是 | enum | `new`, `investigating`, `closed`, `false_positive`。 |
| `created_at` | 是 | datetime | 创建时间。 |

## ReasonCode

`reason_codes` 是机器可读异常原因，不等同于页面展示文案。

| code | 含义 |
| --- | --- |
| `failed_login_spike` | 登录失败次数异常增加。 |
| `credential_stuffing_pattern` | 同一来源尝试多个账号。 |
| `rare_login_hour` | 登录时间偏离历史习惯。 |
| `new_source_ip` | 来源 IP 首次出现或不常见。 |
| `new_geo_location` | 来源地理位置异常。 |
| `new_device_or_host` | 新设备或新主机来源。 |
| `high_api_rate` | API 调用频率异常升高。 |
| `sensitive_resource_access` | 访问敏感资源。 |
| `new_source_then_sensitive_access` | 新来源登录后访问敏感资源。 |
| `download_volume_spike` | 下载量显著增加。 |
| `vpn_traffic_volume_spike` | VPN 会话流量异常增加。 |
| `permission_change` | 权限变更行为。 |
| `admin_resource_access` | 普通账号访问管理资源。 |
| `lateral_movement_signal` | 疑似横向访问多个目标。 |
| `service_account_anomaly` | 服务账号行为异常。 |
| `system_error_pattern` | 系统错误或关键异常组合。 |
| `insufficient_history` | 用户历史样本不足。 |
| `low_baseline_confidence` | baseline 置信度不足。 |
| `peer_group_fallback` | 使用 peer group baseline 降级判断。 |
| `global_baseline_fallback` | 使用全局 baseline 降级判断。 |
| `maintenance_window` | 命中维护窗口。 |
| `allowlisted_context` | 命中白名单上下文。 |

新增检测规则时，必须先确认其 `reason_code` 是否已经存在。若没有，需要先扩展本注册表，再更新检测与评分规格。

## AIJudgement

AI 研判结果必须结构化。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `judgement_id` | 是 | string | AI 研判 ID。 |
| `event_id` | 是 | string | 关联异常事件 ID。 |
| `created_at` | 是 | datetime | 生成时间。 |
| `model_name` | 是 | string | 模型名称。 |
| `model_version` | 否 | string | 模型版本。 |
| `risk_level` | 是 | enum | AI 判断的风险等级。 |
| `attack_type` | 是 | string | AI 判断的攻击类型。 |
| `judgement` | 是 | string | 总体判断。 |
| `key_reasons` | 是 | array | 关键原因。 |
| `recommended_actions` | 是 | array | 建议处置动作。 |
| `confidence` | 是 | float | 0 到 1 置信度。 |
| `feedback_suggestions` | 否 | object | 对规则、baseline 或阈值的建议。 |
| `raw_response` | 否 | object | 模型原始响应。 |
| `is_mock` | 是 | boolean | 是否为 mock 输出。 |

## AIFeedback

反馈用于后续调优，不直接自动修改生产规则。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `feedback_id` | 是 | string | 反馈 ID。 |
| `event_id` | 是 | string | 关联异常事件 ID。 |
| `judgement_id` | 否 | string | 关联 AI 研判 ID。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `user_id` | 否 | string | 相关用户。 |
| `feedback_type` | 是 | enum | `rule_weight`, `baseline_threshold`, `false_positive`, `new_pattern`, `data_contract`。 |
| `suggestion` | 是 | string | 调整建议。 |
| `target_component` | 是 | enum | `rule`, `baseline`, `scoring`, `data_contract`。 |
| `confidence` | 是 | float | 反馈置信度。 |
| `review_status` | 是 | enum | `pending`, `accepted`, `rejected`。 |
| `created_at` | 是 | datetime | 创建时间。 |

## DataQualityMetric

数据质量指标用于记录生成、采集、解析、入库和字段质量的每日对账结果。

| 字段 | 必填 | 类型 | 含义 |
| --- | --- | --- | --- |
| `metric_date` | 是 | date | 指标所属日期。 |
| `tenant_id` | 是 | string | 租户或项目环境 ID。 |
| `source_type` | 是 | string | 日志来源类型。 |
| `generated_count` | 是 | integer | 生成器或日志源产生的原始记录数。 |
| `injected_anomaly_count` | 是 | integer | 生成数据中注入的异常样本数量。真实业务日志可为 0。 |
| `injected_high_risk_count` | 是 | integer | 生成数据中注入的高危异常样本数量。真实业务日志可为 0。 |
| `raw_logs_count` | 是 | integer | Kafka `raw_logs` 接收条数。 |
| `parsed_logs_count` | 是 | integer | Flink 成功解析条数。 |
| `clickhouse_insert_count` | 是 | integer | ClickHouse sink 写入条数。 |
| `security_logs_count` | 是 | integer | `security_logs` 主日志表最终可查询条数。 |
| `raw_size_bytes` | 是 | integer | 原始日志大小。 |
| `table_size_bytes` | 是 | integer | ClickHouse 表占用空间。 |
| `compression_ratio` | 是 | float | 实测压缩率。 |
| `missing_event_time_rate` | 是 | float | `event_time` 缺失率。 |
| `missing_user_id_rate` | 是 | float | `user_id` 缺失率。 |
| `missing_src_ip_rate` | 是 | float | `src_ip` 缺失率。 |
| `missing_action_rate` | 是 | float | `action` 缺失率。 |
| `missing_result_rate` | 是 | float | `result` 缺失率。 |
| `parse_error_rate` | 是 | float | 无法解析日志比例。 |
| `created_at` | 是 | datetime | 指标生成时间。 |

## Time Semantics

- `event_time`：原始日志发生时间，用于安全分析。
- `ingest_time`：系统接收或入库时间，用于链路状态判断。
- `detect_time`：异常事件生成时间，用于异常排序和处理时效。
- `created_at`：对象创建时间。
- `trained_from` / `trained_to`：baseline 训练窗口。

## 数据来源边界

日志生成器可以提供用户画像、风险标签和场景标签，用于生成有规律的数据集。

这些字段只能作为数据生成先验和质量评估标签。系统的用户 baseline、异常事件和风险评分必须从正式入库数据中计算得出。
