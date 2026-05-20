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
