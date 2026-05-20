# ADR-001: 平台服务栈

**Status:** accepted

## Decision

项目正式前端采用 React + TypeScript + Vite，后端 API 采用 FastAPI，核心分析、规则、baseline 和 AI 服务以 Python 生态为主。

## Context

项目已有 Python 后端骨架、AI 研判模块、规则检测和 baseline 代码。前端已有 React 初步页面。

系统目标是形成安全运营工作台，而不是脚本页面集合。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| React + FastAPI | 采用 | 与当前代码基础匹配，前后端边界清晰。 |
| Streamlit 作为正式前端 | 不采用 | 更适合调试和早期原型，不适合作为正式工作台。 |
| Spring Boot 后端 | 暂不采用 | 可行，但与当前 Python 分析和 AI 模块衔接成本更高。 |

## Rationale

React + TypeScript 适合构建多页面安全运营工作台。FastAPI 能较好承接 Python 分析、规则检测、baseline 和 AI 模块。

## Consequences

- React 不直接访问 ClickHouse、Kafka、Flink 或本地日志文件。
- FastAPI 封装业务查询和分析能力。
- Streamlit 可作为历史或调试工具，但不作为正式产品前端。
- API 契约必须长期维护。
