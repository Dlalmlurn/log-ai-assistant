# 架构目标形态

本文件定义当前项目的目标架构和组件职责。

## 主架构

```text
日志源
  -> Filebeat
  -> Kafka
  -> Flink
  -> ClickHouse
  -> FastAPI
  -> React
```

ClickHouse 是唯一主存储和分析引擎。

## 组件职责

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| 日志源 | 产生 VPN、OA、API、系统、文件、数据库、安全设备等日志。 | 不直接生成异常结论。 |
| Filebeat | 采集日志文件增量，写入 Kafka。 | 不做复杂安全分析，不替代 Flink 和 ClickHouse。 |
| Kafka | 作为流式传输和缓冲层。 | 不承担持久分析存储。 |
| Flink | 完成日志清洗、字段标准化、轻量规则、窗口统计和写入前处理。 | 不在实时流中硬编码完整 baseline，不调用大模型。 |
| ClickHouse | 存储和查询结构化日志、用户特征、baseline、异常事件、AI 结果和反馈。 | 不直接调用大模型。 |
| FastAPI | 封装查询、分析、状态、AI 研判和反馈接口。 | 不把数据库细节暴露给前端。 |
| React | 提供安全运营工作台。 | 不生成核心业务数据，不直连底层组件。 |
| AI 服务 | 对高可疑事件进行证据化研判，并产出反馈建议。 | 不分析全量日志，不替代规则和 baseline。 |

## 数据路径

### 原始日志路径

```text
log_file -> Filebeat -> Kafka raw_logs
```

### 标准化日志路径

```text
Kafka raw_logs -> Flink parser -> Kafka parsed_logs -> ClickHouse security_logs
```

### 异常事件路径

```text
security_logs
  + rule detection
  + window statistics
  + baseline deviation
  + risk scoring
  -> anomaly_events
  -> FastAPI
  -> React
```

规则检测、窗口统计和 baseline 偏离可以由不同内部模块完成，但对外只产出统一的 `AnomalyEvent`。

### 行为建模路径

```text
security_logs
  -> T+1 feature job
  -> ueba_user_daily_features
  -> ueba_user_baseline
  -> anomaly scoring
```

### AI 研判和反馈路径

```text
anomaly_events
  -> evidence package
  -> AI judgement
  -> ai_judgements
  -> ai_feedback
  -> rule and baseline tuning candidates
```

## 正式路径和辅助工具

正式数据路径是：

```text
Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React
```

辅助工具可以存在，但必须满足：

- 不替代正式路径。
- 不作为核心业务结果来源。
- 不改变数据契约。
- 不让前端绕过 FastAPI 读取数据。

Python Producer 可以用于调试 Kafka 输入。前端 mock 数据可以用于开发界面，但不能作为核心业务结果。

## 存储边界

ClickHouse 存储以下正式数据：

- 标准化日志。
- 日级用户特征。
- 用户行为 baseline。
- 持久化 seen 数据。
- 异常事件。
- AI 研判结果。
- AI 或人工反馈。
- 每日安全态势简报。
- 系统指标。

Elasticsearch 不进入运行时依赖。

## 检测边界

实时流负责：

- 清洗字段。
- 统一 schema。
- 补充事件 ID。
- 标记轻量规则命中。
- 产生部分窗口统计。

历史建模负责：

- 生成日级用户特征。
- 更新用户 baseline。
- 提供常见来源、常见时间、常见行为和样本置信度。
- 提供新来源、新设备、新地点判断所需的持久化依据。

异常构建负责：

- 合并规则、窗口统计和 baseline 偏离。
- 计算风险分和风险等级。
- 生成 reason codes 和证据链。
- 统一写入 `AnomalyEvent`。

AI 负责：

- 对高可疑事件进行解释。
- 给出处置建议。
- 产出可进入反馈表的校准建议。

## 设计原则

- 前端不感知底层数据库类型。
- API 不绑定 ClickHouse 表名作为外部契约。
- baseline 必须来自历史数据统计，而不是硬编码结论。
- 生成器画像不能直接作为用户 baseline。
- 新来源判断不能只依赖进程内存。
- 风险评分必须可解释。
- AI 输出必须可追踪到输入证据。
- 数据规模必须能支撑行为分析。
