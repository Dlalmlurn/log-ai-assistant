# ADR-002: ClickHouse 作为主存储和分析引擎

**Status:** accepted

## Decision

项目使用 ClickHouse 作为唯一主存储和分析引擎。

Elasticsearch 不作为运行时依赖。

## Context

项目日志主要是结构化安全日志。后续重点是用户行为分析、聚合统计、日报生成、大规模数据压缩和 SQL 查询。

原有 Elasticsearch 方案更偏日志搜索和文档检索。当前项目更强调结构化字段分析和历史行为建模。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 继续使用 Elasticsearch | 不采用 | 与当前结构化日志聚合分析目标不匹配。 |
| Elasticsearch 和 ClickHouse 双主 | 不采用 | 增加维护成本和数据一致性问题。 |
| ClickHouse 单主存储 | 采用 | 更适合结构化日志聚合、压缩存储和 SQL 查询。 |

## Rationale

ClickHouse 是面向 OLAP 的列式 SQL 数据库，适合大规模过滤、聚合和分析查询。

本项目的核心对象包括结构化日志、日级用户特征、baseline、异常事件、AI 研判和反馈。这些对象天然适合使用表结构和 SQL 查询来表达。

## Consequences

- 数据契约以 ClickHouse 表和 Kafka topic 为主。
- API 不暴露 Elasticsearch index 或 query DSL。
- 日报、baseline、用户画像和异常统计都基于 ClickHouse。
- 主线代码不新增 Elasticsearch sink、index 或 adapter。
- 压缩率以项目实测为准，不写成固定承诺。
