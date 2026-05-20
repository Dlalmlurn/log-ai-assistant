# 当前项目架构整理

本文是对当前仓库的架构盘点，区分“正式目标口径”和“当前代码实现”。正式目标仍以 `docs/` 下的基准、契约和 ADR 为准。

## 1. 目标主链路

```text
日志源
  -> Filebeat
  -> Kafka
  -> Flink
  -> ClickHouse
  -> FastAPI
  -> React
```

目标口径已经明确：

- ClickHouse 是唯一主存储和分析引擎。
- Elasticsearch 不再作为运行时依赖。
- Python Producer 只作为调试工具，不是正式采集入口。
- Flink 负责清洗、字段标准化、轻量规则和窗口统计，不承担完整 T+1 baseline。
- 规则检测、窗口统计、baseline 偏离和风险评分统一产出 `AnomalyEvent`。
- AI 只处理高可疑事件的结构化证据包，不分析全量日志。

## 2. 当前代码主链路

当前实现仍是上一版 Elasticsearch MVP 链路：

```text
log-generator / 日志文件
  -> Python Producer 或 Filebeat
  -> Kafka raw_logs
  -> Flink raw_to_parsed 或 Python raw_to_parsed worker
  -> Kafka parsed_logs
  -> Python consumer
  -> Elasticsearch
  -> FastAPI
  -> React / Streamlit
```

当前代码中的主要对象仍是：

- `NormalizedLog`
- `AlertEvent`
- `UserBaseline`
- `AIReport`
- `DailyReport`

目标口径中的以下对象尚未在代码层面完成替换：

- `AnomalyEvent`
- `AIJudgement`
- `AIFeedback`
- `UserDailyFeature`
- `SeenSource`
- `DataQualityMetric`

## 3. 目录职责

| 路径 | 当前职责 | 与目标口径的关系 |
| --- | --- | --- |
| `docs/` | 正式目标文档、数据契约、ClickHouse 表结构、ADR。 | 当前项目开发的最高口径。 |
| `src/api/` | FastAPI 接口层。 | 当前仍查询 Elasticsearch；目标应改为 ClickHouse 查询和目标 API 契约。 |
| `src/schemas/` | Pydantic 数据模型和 API 响应模型。 | 当前仍使用 `username`, `AlertEvent`, 中文风险等级；目标应迁移到 `user_id`, `AnomalyEvent`, 英文风险等级。 |
| `src/parser/` | 原始日志解析和标准化。 | 当前输出字段偏旧版契约；目标需补齐 `tenant_id`, `log_type`, `result`, `raw_log`, `attrs` 等字段。 |
| `src/detection/` | 内存规则引擎和批处理检测。 | 当前输出 `AlertEvent`；目标应输出带 reason codes、risk components 和 baseline evidence 的 `AnomalyEvent`。 |
| `src/ueba/` | 从历史日志构建用户基线。 | 当前基于 Elasticsearch 原始日志做简化统计；目标是 T+1 日级特征和 ClickHouse baseline 表。 |
| `src/ai_engine/` | LLM 或 mock AI 研判。 | 当前输入 `AlertEvent`；目标输入 `AnomalyEvent` 证据包，输出 `AIJudgement` 和 `AIFeedback`。 |
| `src/report/` | 每日安全态势简报生成。 | 当前从 Elasticsearch 聚合；目标从 ClickHouse 真实统计和异常事件生成。 |
| `src/storage/` | Elasticsearch 客户端和 Kafka 到 ES consumer。 | 与新口径冲突，是迁移 ClickHouse 时的核心替换点。 |
| `flink_jobs/` | PyFlink 原始日志解析和实时规则示例。 | 可保留为正式流处理入口，但 sink 和输出契约要改为 ClickHouse/AnomalyEvent 口径。 |
| `frontend/` | React + TypeScript 工作台。 | 当前页面覆盖日志、告警、状态；目标需扩展异常事件、用户画像、AI 研判、日报，并替换字段口径。 |
| `log-generator/` | VPN 日志生成器。 | 可作为第一类数据源，但不能代表全部日志类型，也不能直接作为 baseline。 |
| `filebeat/` | Filebeat 采集配置。 | 是目标正式采集入口。 |
| `docker-compose.yml` | Kafka、Flink、Elasticsearch、Filebeat 等本地环境。 | 当前缺少 ClickHouse，且仍包含 Elasticsearch。 |
| `tests/` | 当前 API、解析、规则、baseline 测试。 | 测试仍锚定旧版 ES/AlertEvent 契约，迁移时需要同步改写。 |

## 4. 数据与事件分层

目标数据分层应收敛为：

```text
raw_logs
  -> NormalizedLog / security_logs
  -> UserDailyFeature
  -> UserBaseline + SeenSource
  -> RuleHit / window stats / baseline deviation
  -> AnomalyEvent
  -> AIJudgement + AIFeedback
  -> DailyReport / Stats
```

当前代码分层实际是：

```text
raw_logs
  -> NormalizedLog
  -> AlertEvent
  -> UserBaseline
  -> AIReport
  -> DailyReport
```

关键差异：

- 当前没有统一 `AnomalyEvent` 聚合层。
- 当前新 IP 判断依赖规则引擎进程内存，不符合持久化 seen/baseline 要求。
- 当前 baseline 缺少训练窗口、样本天数、模型版本、置信度和五W1H profile。
- 当前 AI 研判基于 alert + baseline + related logs，而不是完整证据包。
- 当前日报和统计基于 Elasticsearch index，而目标应基于 ClickHouse 表。

## 5. API 分层

目标 API 以 `/api/v1` 暴露业务能力：

- `GET /api/v1/health`
- `GET /api/v1/logs`
- `GET /api/v1/logs/{event_id}`
- `POST /api/v1/logs/aggregate`
- `GET /api/v1/anomalies`
- `GET /api/v1/anomalies/{event_id}`
- `GET /api/v1/baselines/users`
- `GET /api/v1/baselines/users/{user_id}`
- `POST /api/v1/baselines/rebuild`
- `POST /api/v1/ai/judge/{event_id}`
- `GET /api/v1/ai/judgements`
- `POST /api/v1/feedback`
- `GET /api/v1/reports/daily`
- `POST /api/v1/reports/daily`
- `GET /api/v1/stats/overview`
- `GET /api/v1/stats/users/risk`

当前 API 仍是旧版路径：

- `GET /api/v1/logs`
- `GET /api/v1/logs/{event_id}`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{alert_id}`
- `POST /api/v1/alerts/{alert_id}/analyze`
- `GET /api/v1/baselines`
- `GET /api/v1/baselines/{username}`
- `POST /api/v1/baselines/rebuild`
- `GET /api/v1/ai-reports`
- `GET /api/v1/daily-reports`
- `POST /api/v1/daily-reports`
- `GET /api/v1/health`

迁移重点是把 `alerts` 口径收敛为 `anomalies`，把 `username` 收敛为 `user_id`，把 `ai-reports` 收敛为 `ai/judgements`，把 `daily-reports` 收敛为 `reports/daily`。

## 6. 前端工作台

当前 React 已有：

- 实时日志页。
- 告警列表和详情页。
- 系统状态页。

目标工作台应覆盖：

- 实时日志。
- 异常事件和证据链。
- 用户五W1H baseline。
- AI 研判。
- 安全态势简报。
- 系统状态。

当前前端还显示 Elasticsearch 链路和中文风险等级。目标应改为 ClickHouse 链路、英文内部枚举加中文展示映射，并展示 reason codes、risk components、baseline deviations 和 AI status。

## 7. 主要架构差距

| 优先级 | 差距 | 影响 |
| --- | --- | --- |
| P0 | `docker-compose.yml`, `src/storage`, `src/api`, `src/health` 仍以 Elasticsearch 为主。 | 与 ClickHouse 唯一主存储目标直接冲突。 |
| P0 | 代码仍输出 `AlertEvent`，没有统一 `AnomalyEvent`。 | 前端、AI、日报会继续围绕旧告警对象扩展。 |
| P0 | 数据模型仍使用 `username/status/raw_message` 和中文风险等级。 | 与新数据契约的 `user_id/result/raw_log`、英文风险等级不一致。 |
| P1 | baseline 仍是简化统计，没有 T+1 日级特征和五W1H profile。 | 无法支撑可解释的 UEBA 偏离。 |
| P1 | 新来源判断依赖进程内存。 | 重启后证据丢失，不满足新来源持久化要求。 |
| P1 | AI 研判仍以旧 alert 为输入。 | 无法保证 AI 输出可追溯到完整证据包。 |
| P2 | 前端页面覆盖不足。 | 缺少用户画像、AI 研判、日报等目标页面。 |
| P2 | 数据生成仍主要是 VPN。 | 不足以支撑多日志类型和 1GB/日数据规模目标。 |

## 8. 建议迁移顺序

1. 建立 ClickHouse 本地环境和 `security_logs` 最小表。
2. 新增 ClickHouse storage adapter，先让 FastAPI 日志查询走 ClickHouse。
3. 按 `docs/03_data_contract.md` 重构 `NormalizedLog` 字段。
4. 将 `AlertEvent` 替换或并行引入为 `AnomalyEvent`，保留兼容层只用于过渡。
5. 将规则输出补齐 `reason_codes`, `risk_components`, `baseline_deviations`, `ai_status`。
6. 建立 `ueba_user_daily_features`, `ueba_user_baseline`, `user_seen_sources` 生成流程。
7. 改造 AI 输入输出为 `AnomalyEvent -> AIJudgement + AIFeedback`。
8. 改造日报和统计接口为 ClickHouse 聚合。
9. 更新 React API types、页面和链路文案。
10. 移除 Elasticsearch runtime 依赖、旧 ES consumer、旧测试契约。

## 9. 当前结论

当前仓库的“目标架构”已经完成重新定口径：ClickHouse 单主存储、统一异常事件、T+1 baseline、AI 证据化研判。

当前代码的“实现架构”仍处在上一版 Elasticsearch MVP：能跑日志解析、规则告警、简化 baseline、AI report、日报和 React 部分页面，但它们都围绕旧数据契约展开。

下一阶段不宜继续在旧 `AlertEvent + Elasticsearch` 链路上加功能，应该优先做存储层、数据契约和异常对象的迁移，否则前端、AI 和日报都会继续扩大旧口径的维护成本。
