# Architecture Decisions

本文件记录项目关键架构决策。新增重大技术栈、替换主链路组件、改变正式展示方式时，必须追加 ADR。

## ADR-001: React + TypeScript + Vite 作为正式前端

**Status:** Accepted

**Decision:** 正式前端采用 React + TypeScript + Vite。Streamlit 只保留为调试或历史 MVP。

**Rationale:**

- React 更适合长期维护的安全运营工作台。
- TypeScript 能约束日志、告警、报告等复杂数据结构。
- Vite 启动快，适合团队协作和课程/竞赛原型。
- 与后端 API 分层后，页面不需要每次从脚本重新生成展示数据。

**Consequences:**

- 所有正式页面必须通过 FastAPI 获取数据。
- 不允许新增 Streamlit 页面作为正式交付。

## ADR-002: FastAPI 作为后端 API 层

**Status:** Accepted

**Decision:** 后端 API 采用 FastAPI，复用现有 Python 解析、UEBA、规则检测、AI 研判和日报模块。

**Rationale:**

- 当前核心业务代码已经是 Python。
- 项目包含 AI、数据分析和 ES 查询，FastAPI 与现有代码贴合。
- 与 Spring Boot 相比，FastAPI 在本项目中迁移成本更低、迭代更快。

**Consequences:**

- React 前端不得直连 ES。
- 后端必须暴露稳定 API，并在 `docs/05_api_contract.md` 中维护契约。
- 如果未来切换 Spring Boot，必须新增 ADR，说明迁移收益、成本和边界。

## ADR-003: Elasticsearch 作为主查询存储

**Status:** Accepted

**Decision:** Elasticsearch 作为日志、告警、AI 报告、日报和用户 baseline 的主查询中心。

**Rationale:**

- 原始需求允许 ClickHouse 或 Elasticsearch 二选一。
- 本项目强调日志检索、字段过滤、异常详情、全文消息和看板联动，ES 更贴合。
- 当前 MVP 已经完成 ES 索引和查询模块。

**Consequences:**

- 不引入 ClickHouse 作为并行主存储，除非新增 ADR。
- ES index 和字段契约以 `docs/03_data_contract.md` 为准。

## ADR-004: Filebeat + Kafka + Flink 作为正式实时链路

**Status:** Accepted

**Decision:** 正式数据链路固定为 `日志源 -> Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React`。

**Rationale:**

- Filebeat 满足全量/增量采集口径。
- Kafka 提供流式缓冲和上下游解耦。
- Flink 负责实时结构化、清洗和窗口统计，符合原始技术要求。
- Python Producer 和 `process-raw` 能帮助调试，但不能替代正式实时链路。

**Consequences:**

- 正式验收必须走 Filebeat 和 Flink。
- Python fallback 必须在文档和脚本中标为调试路径。

## ADR-005: LLM 只做研判与解释

**Status:** Accepted

**Decision:** LLM 不直接负责原始日志检测，只对规则、窗口统计或 baseline 偏离产生的异常上下文做研判。

**Rationale:**

- 安全检测需要可解释、可复现、可追踪的证据链。
- LLM 直接判断原始日志容易产生不可控结论。
- 把 LLM 放在研判层，更符合 SOC 工作流。

**Consequences:**

- AI prompt 输入必须包含 alert、baseline 和 related_logs。
- AI 输出必须是结构化 JSON，并落库到 `ai-reports`。

## New ADR Template

```md
## ADR-XXX: Title

**Status:** Proposed | Accepted | Rejected | Superseded

**Decision:** One-sentence decision.

**Rationale:**

- Why this decision exists.
- What alternatives were considered.

**Consequences:**

- What developers must do differently.
- What risks or costs are accepted.
```
