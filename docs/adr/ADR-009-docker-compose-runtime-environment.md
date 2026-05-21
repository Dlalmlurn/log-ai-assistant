# ADR-009: Docker Compose 正式运行环境

**Status:** accepted

## Decision

项目正式运行环境以 Docker Compose 为基准。

开发者本机只要求 Git、Docker、编辑器和浏览器。Miniconda、Python、Node、Flink、Kafka、ClickHouse、Filebeat、FastAPI、React 和 log-generator 等运行依赖由 Docker Compose 管理。

## Context

项目主链路已经明确为：

```text
Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React
```

该链路包含多个运行时和中间件。如果继续要求组员在本机分别安装 Python、Node、PyFlink、Kafka、ClickHouse 或 Filebeat，环境差异会成为主要风险，也会让正式运行路径和个人开发便利混在一起。

当前项目还存在旧的 Elasticsearch、Streamlit、Python Producer 和本机脚本入口。它们可以作为迁移期兼容或调试工具存在，但不能继续作为正式运行环境要求。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 继续要求本机安装 Miniconda 和各类运行时 | 不采用 | 依赖重、版本漂移大，不适合作为组员统一基线。 |
| 只容器化中间件，前后端仍本机运行 | 不采用 | 仍要求本机 Python 和 Node，不能形成统一运行入口。 |
| Docker Compose 管理完整运行依赖 | 采用 | 能统一中间件、前后端、日志生成器和测试入口。 |

## Rationale

Docker Compose 能把 Kafka、Flink、ClickHouse、Filebeat、FastAPI、React 和 log-generator 固定在同一运行环境中，降低本机环境差异，并让日常开发入口稳定为：

```bash
cp .env.example .env
docker compose up --build
```

默认日志生成器只提供小规模持续日志。1GB/day 或更高规模生成通过 Compose profile 显式启用，避免默认启动压垮开发机。

## Consequences

- README 和正式 docs 不再要求 Miniconda 作为运行前置条件。
- Python、Node 和 PyFlink 依赖安装发生在容器构建或 Compose service 中。
- backend、frontend、ClickHouse、Kafka、Flink、Filebeat 和 log-generator 必须在 Compose 中存在。
- 测试入口应通过 `docker compose run --rm tester` 或等价 service 提供。
- Elasticsearch 和 Kibana 如保留，只能作为 legacy profile 或迁移辅助，不进入默认主链路。
- 本地 Python、Node 或 Conda 环境只能作为个人便利，不作为项目正式依赖。
