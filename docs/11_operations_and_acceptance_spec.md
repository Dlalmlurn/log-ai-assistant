# 运营自动化与量化验收规格

本文定义 ADR-011 的实施边界。目标是把已经存在的采集、建模、检测、AI 和日报能力转化为可自动运行、可审计和可重复验收的系统。

## 1. 范围

本阶段覆盖：

- 周期 baseline 自动构建。
- 每日安全态势简报自动生成。
- 数据质量和阶段计数自动对账。
- 正常与攻击场景的量化评测。
- 高危和紧急异常的可靠通知。
- 运行状态、失败原因和验收报告的 API 与前端管理入口。

本阶段不覆盖：

- 替换 Kafka、Flink、ClickHouse、FastAPI 或 React。
- 使用 LLM 替代规则、baseline 或风险评分。
- 完整动态规则 DSL 和任意代码执行。
- 以 PDF 文件替代 ClickHouse 中的日报事实数据。

## 2. 运营控制面

Compose 新增 `operations-runner`。它负责领取到期任务、检查依赖、调用现有领域服务、记录结果和安排重试。

控制面不得重新实现 baseline、日报、质量计算或异常检测。业务逻辑继续位于现有模块中，并提供可重复调用的 Python service function。

### 2.1 首批任务

| 任务 | 默认周期 | 依赖 | 幂等键 |
| --- | --- | --- | --- |
| `daily_feature_aggregate` | 每日 | 目标日期日志水位完成 | `tenant + task + target_date` |
| `baseline_rebuild` | 每日 T+1 | 日级特征完成 | `tenant + task + baseline_date + model_version` |
| `data_quality_reconcile` | 每日 | 采集窗口关闭 | `tenant + task + metric_date` |
| `daily_report_generate` | 每日 | baseline 与质量任务完成 | `tenant + task + report_date` |
| `scenario_evaluate` | 按需、CI 或发布前 | 场景数据和检测结果可用 | `commit + scenario_version + policy_version` |
| `notification_deliver` | 持续 | outbox 中存在待投递记录 | `channel + event_id + destination` |

默认调度时间必须可通过环境变量配置。所有业务日期使用显式时区，存储时间使用 UTC。

### 2.2 运行状态

任务运行状态统一为：

- `queued`
- `running`
- `succeeded`
- `failed`
- `needs_review`
- `cancelled`

每条运行记录至少包含：

- `run_id`
- `task_name`
- `tenant_id`
- `target_date`
- `idempotency_key`
- `scheduled_at`
- `started_at`
- `finished_at`
- `status`
- `attempt`
- `input_watermark`
- `output_refs`
- `code_version`
- `error_code`
- `error_message`

首版只允许一个长期运行的 scheduler。scheduler 和手动 `run-once` 通过 Compose 共享锁卷上的文件锁避免并发执行同一幂等键。ClickHouse 不承担分布式锁职责；如果后续需要多副本调度，应单独引入具备租约或事务能力的协调存储并追加 ADR。

最终成功结果以持久化运行记录和领域表中的幂等业务键为准。

### 2.3 持久化对象

首批逻辑对象包括：

| 对象 | 用途 |
| --- | --- |
| `operations_task_runs` | 保存任务、attempt、数据水位、状态、版本和输出引用。 |
| `acceptance_reports` | 保存一次发布或场景验收的版本信息和总体结论。 |
| `acceptance_metrics` | 保存按场景和指标拆分的数值、阈值与通过状态。 |
| `notification_outbox` | 保存通知意图、渠道、目标和当前投递状态。 |
| `notification_attempts` | 保存每次投递请求、响应、耗时和失败原因。 |

这些对象可以映射为 ClickHouse 表。状态变化使用带版本号的追加记录和 `ReplacingMergeTree` 最新态查询，不依赖高频 mutation。

## 3. 数据水位与依赖

周期任务不能只按墙上时钟盲目运行。每个数据日期需要记录或计算：

- 生成器窗口是否关闭。
- Filebeat 是否已经读取到窗口末尾。
- Kafka consumer lag 是否低于阈值。
- Flink 是否处理到目标 event time。
- ClickHouse 最新入库时间是否越过目标水位。

水位未满足时，任务保持 `queued` 或延迟重试。超过最大等待时间后进入 `needs_review`，不得用不完整数据生成正式 baseline 或日报。

## 4. 数据质量门禁

对账必须按同一租户、来源和时间窗口比较：

```text
generated -> raw_logs -> parsed_logs -> ClickHouse insert -> security_logs
```

报告必须区分：

- 可解释差异：重放、ReplacingMergeTree 折叠、窗口仍在处理。
- 不可解释差异：解析静默丢弃、消费者停滞、窗口错位、字段损坏。

每个阶段输出总数、差值、差异率和解释代码。只有全部阻断指标通过时，质量任务才能标记为 `succeeded`；存在无法解释的差异时标记为 `needs_review`。

阈值至少包括：

- `parse_error_rate_max`
- `required_field_missing_rate_max`
- `raw_to_parsed_loss_rate_max`
- `event_id_traceability_rate_min`
- `consumer_lag_max`

## 5. 场景评测

生成器标签只用于验收评测，不得直接作为检测输入。

评测集至少包含 3 类正常场景和 3 类高危攻击场景。攻击样本使用 `scenario_id`、`attack_chain_id` 和 `injected_label` 与异常事件关联。

### 5.1 指标

| 指标 | 定义 |
| --- | --- |
| 正常场景误报率 | 被判为 high/critical 的正常场景窗口或正常用户窗口占比。 |
| 攻击检出率 | 至少产生一个 `AnomalyEvent` 的攻击链占比。 |
| 高危检出率 | 至少产生一个 high/critical 事件的高危攻击链占比。 |
| 端到端可追踪率 | 能从 manifest 追踪到 `security_logs` 和 `anomaly_events` 的攻击链占比。 |
| AI 覆盖率 | 符合 AI 候选条件且形成研判记录的异常占比，真实与 mock 必须分开统计。 |
| 检测延迟 | 原始事件时间到异常 `detect_time` 的 p50、p95 和最大值。 |
| 通知延迟 | 异常 `detect_time` 到成功投递时间的 p50、p95 和最大值。 |

总体 accuracy 可以作为附加指标，但不能替代误报率和检出率。

### 5.2 版本与阈值

每份验收报告必须保存：

- Git commit。
- Compose 配置摘要。
- 场景配置版本。
- 规则或策略版本。
- baseline 模型版本。
- AI 模型和是否 mock。
- 阈值配置版本。
- 样本数量和评测时间范围。

初始阈值应进入版本化配置文件，由项目验收负责人确认后生效。阈值变更必须保留历史，不允许只修改报告中的显示结果。

## 6. 高危通知

检测器在写入 high/critical `AnomalyEvent` 后，按通知策略写入 outbox。通知 worker 从 outbox 领取任务并调用渠道 adapter。

首个正式渠道为 webhook。通知载荷至少包含：

- `event_id`
- `event_time`
- `risk_level`
- `risk_score`
- `attack_type`
- `user_id`
- `src_ip`
- `reason_codes`
- 前端详情链接

投递状态统一为 `pending`、`delivering`、`delivered`、`retry_wait`、`dead_letter`。重试使用有上限的指数退避。

同一事件、渠道和目标地址必须幂等。敏感原始日志不得默认放入外部通知载荷。

## 7. 日报与导出

日报仍以 ClickHouse 中的结构化字段和 Markdown 正文为事实来源。

自动任务成功后，前端应能查询日报生成时间、数据水位、关联运行 ID 和质量状态。Markdown 下载是必须能力；PDF 是可选 adapter，生成失败不得影响日报本身成功。

## 8. API 与前端

后端至少提供：

- 任务定义和最近运行列表。
- 单次运行详情和失败原因。
- 允许授权用户重试失败或 `needs_review` 任务。
- 验收报告列表和详情。
- 通知投递状态和失败重试入口。
- 日报 Markdown 下载。

前端系统状态页增加运营任务状态；验收页展示指标、阈值、版本和通过结论。任何“通过”标签都必须来自后端保存的验收结果，不能由前端自行推断。

## 9. Docker 验收

本阶段完成时至少执行：

```bash
docker compose run --rm tester
docker compose up -d --build
SKIP_COMPOSE_UP=1 scripts/p0_e2e_check.sh
docker compose run --rm operations-runner run-once --task data_quality_reconcile
docker compose run --rm operations-runner run-once --task baseline_rebuild
docker compose run --rm operations-runner run-once --task daily_report_generate
docker compose run --rm operations-runner run-once --task scenario_evaluate
```

验收必须证明：

- 重复运行同一幂等键不会生成重复业务结果。
- 失败任务能重试并保留每次 attempt。
- 数据水位不足时不会生成正式 baseline 或日报。
- 场景报告能区分误报率、检出率和检测延迟。
- high/critical 事件产生 outbox，模拟渠道失败后可以重试成功。
- 前端能查询运行状态、验收结论和通知状态。
