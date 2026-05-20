# ADR 说明

ADR 是 Architecture Decision Record，也就是架构决策记录。

它用于记录项目中的核心技术选择，包括：

- 决策是什么。
- 为什么做这个决策。
- 曾经考虑过什么替代方案。
- 这个决策带来了什么约束和影响。

ADR 不是普通备忘录，也不是任务清单。它记录的是会长期影响项目结构的决定。

## 当前 ADR 状态

| 状态 | 含义 |
| --- | --- |
| `proposed` | 已提出，尚未确认。 |
| `accepted` | 已确认，进入主线口径。 |
| `rejected` | 已拒绝，不进入主线。 |
| `superseded` | 已被新 ADR 替代。 |

## 当前核心 ADR

| 文件 | 决策 |
| --- | --- |
| `ADR-001-platform-stack.md` | React、FastAPI 和 Python 服务栈。 |
| `ADR-002-clickhouse-primary-storage.md` | ClickHouse 作为唯一主存储和分析引擎。 |
| `ADR-003-filebeat-kafka-flink-chain.md` | Filebeat、Kafka、Flink 作为正式数据链路。 |
| `ADR-004-t-plus-one-baseline.md` | 行为 baseline 使用 T+1 历史数据建模。 |
| `ADR-005-ai-judgement-and-feedback.md` | AI 只做证据化研判和反馈。 |
| `ADR-006-data-scale-and-synthetic-scenarios.md` | 每日不少于 1GB 原始日志和企业场景生成。 |
| `ADR-007-unified-anomaly-event.md` | 统一异常事件对象和风险等级枚举。 |
| `ADR-008-generated-priors-are-not-baselines.md` | 生成器画像不等于系统行为 baseline。 |

## 追加规则

当出现以下情况时，应追加 ADR：

- 替换主链路组件。
- 改变主存储或查询引擎。
- 改变 baseline 生成方式。
- 改变 AI 服务使用边界。
- 改变前后端分层方式。
- 改变数据契约中的核心对象。
- 引入会长期影响架构的外部服务。

## 模板

```md
# ADR-XXX: 标题

**Status:** proposed | accepted | rejected | superseded

## Decision

一句话说明决策。

## Context

说明背景和问题。

## Alternatives

说明考虑过的替代方案。

## Rationale

说明选择该方案的理由。

## Consequences

说明这个决策带来的约束、收益和风险。
```
