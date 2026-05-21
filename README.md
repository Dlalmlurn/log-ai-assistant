# Log AI Assistant

本项目是一个面向企业安全日志分析的 AI 助手原型。

项目目标是构建从日志采集、结构化处理、ClickHouse 存储、行为基线建模、异常检测、AI 研判反馈到前端工作台的完整安全分析系统。

## 当前主链路

Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React

ClickHouse 是当前唯一主存储和分析引擎。
Elasticsearch 不再作为当前目标形态的一部分。

## 正式目标文档

当前项目目标形态、架构约束、数据契约、行为建模方式、AI 使用边界和最终质量标准以 `docs/` 为准。

建议优先阅读：

- `docs/00_project_baseline.md`
- `docs/02_architecture_overview.md`
- `docs/03_data_contract.md`
- `docs/04_clickhouse_schema.md`
- `docs/05_behavior_modeling_spec.md`
- `docs/06_detection_and_scoring_spec.md`
- `docs/07_ai_judgement_feedback_spec.md`
- `docs/09_data_generation_and_scenarios.md`
- `docs/10_final_quality_criteria.md`

## 文档索引

完整文档索引见：

- `docs/README.md`

架构决策记录见：

- `docs/adr/README.md`

## 正式运行环境

项目正式运行环境以 Docker Compose 为准。开发者本机只要求安装：

- Git
- Docker / Docker Compose
- 编辑器
- 浏览器

不要求组员本机安装 Miniconda、Python、Node、Flink、Kafka、ClickHouse 或 Filebeat。本地 Python、Node 或 Conda 环境只能作为个人开发便利，不作为项目正式运行依赖。

## Docker-first 启动

首次启动：

```bash
cp .env.example .env
docker compose up --build
```

默认 Compose 会拉起当前正式运行基线中的主要服务：

| 服务 | 作用 | 默认访问 |
| --- | --- | --- |
| `kafka` | 流式传输和缓冲层 | `localhost:9092` |
| `flink-jobmanager` / `flink-taskmanager` | Flink 运行环境 | `http://localhost:8081` |
| `clickhouse` | 主存储和分析引擎 | `http://localhost:8123` |
| `filebeat` | 采集 `logs/vpn_logs.log` 并写入 Kafka | 容器内运行 |
| `backend` | FastAPI API 层 | `http://localhost:8000` |
| `frontend` | React + Vite 工作台 | `http://localhost:5173` |
| `log-generator` | 小规模持续生成 VPN syslog 样例 | 写入 `logs/vpn_logs.log` |

默认日志生成器是小流量开发配置，避免压垮普通开发机。大规模日志生成不随默认启动运行，需要显式启用 profile：

```bash
docker compose --profile scale up --build
```

Flink 作业提交通过 Compose service 预留：

```bash
docker compose --profile jobs up flink-submit
```

测试入口不随默认启动运行，可以按需执行：

```bash
docker compose run --rm tester
```

Elasticsearch / Kibana 仅保留在 `legacy-es` profile 中，供旧代码兼容或迁移对照使用，不属于当前正式主链路。
