# ADR-003: Filebeat + Kafka + Flink 作为正式数据链路

**Status:** accepted

## Decision

项目正式数据链路为：

```text
Filebeat -> Kafka -> Flink -> ClickHouse
```

Filebeat 是正式采集入口。Python Producer 只能作为辅助工具。

Flink 负责日志清洗、字段标准化、轻量规则、窗口统计和写入前处理，不负责完整 T+1 baseline 建模。

## Context

项目需要体现日志采集、流式传输、清洗处理和持久分析存储的完整能力。

Filebeat、Kafka 和 Flink 已经在项目中形成初步链路。由于项目后续要做行为建模和结构化分析，需要把正式采集路径固定下来，避免脚本直接发送 Kafka 成为主路径。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| Python Producer 直接写 Kafka | 仅辅助 | 适合本地调试和链路隔离验证，不能代表正式采集路径。 |
| Filebeat 直接写 ClickHouse | 暂不采用 | 缺少中间缓冲和流处理层。 |
| ClickHouse Kafka Engine 直接消费 Kafka | 可作为备选 | 能简化链路，但会弱化 Flink 的清洗和规则能力。 |
| Filebeat + Kafka + Flink + ClickHouse | 采用 | 组件职责清晰，便于清洗、规则、窗口统计和后续扩展。 |

## Rationale

Filebeat 负责采集，Kafka 负责缓冲，Flink 负责清洗和轻量规则，ClickHouse 负责分析存储。

这条链路能把采集、处理、存储和查询分离，适合逐步扩展。

## Consequences

- 正式数据必须经过 Filebeat、Kafka 和 Flink。
- Python Producer 只能作为辅助工具。
- Flink 第一阶段主要负责字段标准化、轻量规则、窗口统计和写入前处理。
- 完整 baseline 不在实时流中硬编码完成。
- API、前端和 AI 不能依赖辅助工具产生核心业务结果。
