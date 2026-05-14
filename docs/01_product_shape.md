# Product Shape

本项目的目标形态是实时日志安全分析工作台。它应该像一个安全运营产品，而不是把日志生成器、脚本输出和临时图表拼在一起。

## Product Principles

- 展示层只展示已进入正式数据链路的数据。
- 前端不生成核心业务数据，不直连 Elasticsearch，不绕过后端 API。
- 后端 API 封装查询、分析、日报和健康检查能力。
- AI 只解释有证据的异常，不凭空判断整段原始日志流。
- Baseline、异常证据链和处置建议是产品主轴。

## Users

| 用户 | 目标 | 需要看到的信息 |
| --- | --- | --- |
| 安全运营人员 | 快速发现和处置异常。 | 实时日志、异常事件、证据链、用户画像、AI 建议。 |
| 项目评审者 | 判断系统是否满足甲方要求。 | 真实链路、场景复现、日报、架构状态和验收清单。 |
| 开发组员 | 分工实现和联调。 | 数据契约、API 契约、需求编号、组件职责。 |

## Core Pages

| 页面 | 对应需求 | 数据来源 | 页面目标 |
| --- | --- | --- | --- |
| 实时日志 | REQ-001, REQ-002, REQ-006 | FastAPI -> Elasticsearch `security-logs` | 查看持续采集和结构化后的日志。 |
| 异常事件 | REQ-004, REQ-006, REQ-008 | FastAPI -> Elasticsearch `security-alerts` | 查看规则命中、风险等级和相关日志。 |
| 用户基线 | REQ-003, REQ-006 | FastAPI -> Elasticsearch `user-baselines` | 查看用户正常行为画像和偏离依据。 |
| AI 研判 | REQ-004, REQ-006 | FastAPI -> AI service + `ai-reports` | 查看攻击类型、解释、置信度和处置建议。 |
| 每日简报 | REQ-005, REQ-006 | FastAPI -> `daily-reports` | 查看整体安全评分、高危用户和主要风险。 |
| 系统状态 | REQ-001, REQ-002, REQ-007 | FastAPI -> Kafka/Flink/ES health | 查看链路是否真实运行。 |

## Streamlit Position

Streamlit 只允许作为调试入口或历史 MVP 保留。它不能作为正式产品前端，不能承载最终验收，也不能继续扩展为主工作台。

## Demo Rule

正式演示必须从日志文件新增或生成开始，经过 `Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React`，最终在 React 页面看到结果。直接从生成器读文件或前端 mock 数据只可用于开发调试，不计入验收。
