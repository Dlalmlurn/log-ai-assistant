# 日志分析 AI 助手（企业原型）

## 0. 项目构建口径

本项目后续开发以 `docs` 中的约束文档为准，甲方原始需求来自 `docs/初始需求文档.xlsx` 和 `docs/日志分析.xlsx`。其中：

- `docs/00_gold_standard.md`：甲方需求基线和 `REQ-*` 编号。
- `docs/01_product_shape.md`：产品形态、用户角色和核心页面。
- `docs/02_architecture_decisions.md`：关键架构决策。
- `docs/03_data_contract.md`：Kafka、Elasticsearch 和核心数据模型契约。
- `docs/04_security_analysis_spec.md`：baseline、规则、风险分级和 AI 研判边界。
- `docs/05_api_contract.md`：React 前端与 FastAPI 后端接口契约。
- `docs/06_acceptance_checklist.md`：阶段验收清单。

正式项目形态固定为：`日志源 -> Filebeat -> Kafka -> Flink -> Elasticsearch -> FastAPI -> React`。

Streamlit 只作为历史 MVP 或调试入口保留，不再作为正式产品前端。Python Producer 和 `process-raw` 只作为调试兜底，不作为正式验收路径。

面向企业日志安全分析的端到端原型系统：
- 接入导师提供的 `log-generator`（优先保留其字段与输出格式）
- Kafka 流式传输
- Flink/PyFlink 实时结构化
- Elasticsearch 存储与检索
- UEBA 用户行为基线
- 规则检测 + LLM（通义千问 / mock）研判
- FastAPI API 层（规划中的正式后端）
- React + TypeScript 工作台（规划中的正式前端）
- Streamlit 调试看板（历史 MVP）
- 每日安全态势简报

## 1. 项目架构

正式目标架构：

```text
日志源 / log-generator 输出文件
    |
    v
Filebeat
    |
    v
Kafka: raw_logs
    |
    v
Flink: raw_to_parsed / window stats
    |
    v
Kafka: parsed_logs / alert_events
    |
    v
Elasticsearch: security-logs / security-alerts / user-baselines / ai-reports / daily-reports
    |
    v
FastAPI
    |
    v
React + TypeScript 工作台
```

当前 MVP/调试链路：

```text
mentor log-generator
    |
    v
日志文件(jsonl/syslog/csv)
    |
    v
Python Producer（调试兜底）/ Filebeat（正式入口）
    |
    v
Kafka: raw_logs
    |
    v
PyFlink: raw_to_parsed
    |
    +--> Kafka: parsed_logs
    +--> (Python规则引擎) Kafka: alert_events

Kafka parsed_logs/alert_events -> Python consumer -> Elasticsearch
    |
    +--> security-logs
    +--> security-alerts
    +--> ai-reports
    +--> daily-reports

Elasticsearch -> UEBA基线 / 异常查询 / AI研判 / Streamlit调试看板
```

## 2. 已适配的导师 log-generator 结论

`log-generator/gen_vpn_logs.py` 已检查并保持原样：
- 运行方式：`python gen_vpn_logs.py --start --days --count --outdir --format`
- 输出位置：目录文件输出（默认非 stdout）
- 输出格式：`csv` / `jsonl` / `syslog`
- 是否持续生成：默认离线批量，不是持续流式
- 日志类型：当前为 VPN 场景
- 异常场景：登录失败、境外IP、非工作时间、大流量下载等
- 速率控制：按天数和每天条数控制（非实时频率控制）
- JSON 支持：支持 JSONL（每行 JSON）

字段冲突策略：涉及字段冲突时优先采用 `log-generator` 原字段，并映射到标准结构字段。

## 3. 目录结构

```text
log-ai-assistant/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── scripts/
│   ├── create_topics.sh
│   ├── init_es.py
│   └── run_pipeline.sh
├── logs/
├── data/
├── log-generator/
│   └── (导师提供日志生成器，已拷贝)
├── filebeat/
│   └── filebeat.yml
├── flink_jobs/
│   ├── raw_to_parsed.py
│   └── realtime_rules.py
├── src/
│   ├── config.py
│   ├── main.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── models.py
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── file_tail_producer.py
│   │   └── kafka_producer.py
│   ├── parser/
│   │   ├── __init__.py
│   │   └── log_parser.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── elastic_client.py
│   │   └── kafka_es_consumer.py
│   ├── ueba/
│   │   ├── __init__.py
│   │   └── baseline.py
│   ├── detection/
│   │   ├── __init__.py
│   │   └── rules.py
│   ├── ai_engine/
│   │   ├── __init__.py
│   │   ├── llm_client.py
│   │   └── prompts.py
│   ├── report/
│   │   ├── __init__.py
│   │   └── daily_report.py
│   └── dashboard/
│       ├── __init__.py
│       └── app.py
└── tests/
    ├── test_parser.py
    ├── test_rules.py
    └── test_baseline.py
```

## 4. 环境准备

- Miniconda（推荐）
- Python 3.10（与 `apache-flink==1.18.1` 兼容）
- Docker / Docker Compose v2

```bash
cd log-ai-assistant
eval "$(conda shell.bash hook)"
conda create -n log-ai-assistant python=3.10 -y
conda activate log-ai-assistant
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

说明：
- `requirements.txt` 中 `apache-flink==1.18.1` 仅在 Python `<3.11` 时安装。
- 若你使用 Python `3.11/3.12`，可继续使用 `python src/main.py process-raw` 走演示链路（不依赖本地 PyFlink）。

## 5. 启动中间件

```bash
docker compose up -d
```

默认端口：
- Kafka: `9092`
- Elasticsearch: `9200`
- Flink Dashboard: `8081`
- Streamlit: `8501`
- Kibana(可选): `5601`

## 6. Kafka Topics

设计：
- `raw_logs`：原始日志
- `parsed_logs`：结构化日志
- `alert_events`：异常事件
- `ai_reports`：LLM 研判结果
- `system_metrics`：系统指标（预留）

初始化：
```bash
python src/main.py init
# 或
./scripts/create_topics.sh
```

验证：
```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

## 7. Elasticsearch 索引

自动初始化索引：
- `security-logs`
- `security-alerts`
- `ai-reports`
- `daily-reports`
- `user-baselines`

```bash
python src/main.py init
# 或
python scripts/init_es.py
```

## 8. 运行导师 log-generator

```bash
cd log-generator
python gen_vpn_logs.py --start 2026-04-01 --days 1 --count 120 --outdir vpn_output --format jsonl
```

检查输出：
```bash
python src/main.py inspect-generator
```

## 9. 写入 Kafka raw_logs

### 正式路径：Filebeat

Filebeat 监听日志文件并推送 Kafka（`filebeat/filebeat.yml`）。正式验收时应使用这一路径，以满足全量/增量采集和实时链路口径。

### 调试兜底：Python Producer

Python Producer 可读取 `jsonl` 并发送，适合快速调试解析、检测和入库逻辑，但不作为正式验收路径：

```bash
python src/main.py produce --run-generator --format jsonl --days 1 --count 120
# 或者指定文件
python src/main.py produce --path log-generator/vpn_output/vpn_logs.jsonl
```

> 说明：Python Producer 保留为 MVP 调试工具；正式路线必须逐步收敛到 Filebeat。

## 10. 启动 Flink 任务

### raw_logs -> parsed_logs

```bash
# 本地提交示例（需按你的 Flink 环境调整）
flink run -py flink_jobs/raw_to_parsed.py
```

如果暂时不跑 Flink 窗口规则：
- Flink 当前职责：完成 `raw_logs -> parsed_logs` 标准化
- 实时检测先在 Python `consume-to-es` 内执行（规则引擎）
- 后续可把规则逐步迁移到 PyFlink
- 兜底路径：`python src/main.py process-raw`（仅用于演示保底，不替代 Flink 方案）

## 11. parsed_logs / alert_events 写入 Elasticsearch

```bash
python src/main.py consume-to-es
# 可限制消息条数
python src/main.py consume-to-es --max-messages 10000
# 演示模式：空闲5秒自动退出（默认）
python src/main.py consume-to-es --max-messages 500 --idle-timeout-ms 5000
```

若当前未运行 Flink，可先执行：

```bash
python src/main.py process-raw --max-messages 500 --idle-timeout-ms 5000
# 若要持续运行可用 --idle-timeout-ms -1
# 若只消费新消息可加 --from-latest
```

## 12. UEBA 行为基线

```bash
python src/main.py build-baseline
```

生成结果：
- ES 索引：`user-baselines`
- 本地文件：`data/user_baselines.json`

## 13. 异常检测

实时检测：
- 在 `consume-to-es` 中对 `parsed_logs` 按规则实时判定，生成 `alert_events`

离线/准实时补跑：
```bash
python src/main.py detect --hours 24 --size 5000
```

已实现规则（第一版）：
- 新 IP 登录
- 非工作时间登录
- 同一 src_ip 5 分钟登录失败超阈值
- 同一 username 5 分钟登录失败超阈值
- 同一 IP 多用户登录失败
- 同一 username 1 分钟 API 高频调用
- 同一 username 5 分钟敏感资源访问超阈值
- 新 IP 登录后短时间访问敏感资源
- 新 IP 登录后短时间导出/下载接口访问
- 普通用户访问 admin 接口
- 系统日志 error/critical

风险等级：`低/中/高`（对应分数 `30/60/90`）

## 14. AI 研判（通义千问 + mock）

配置 API Key：
```bash
export DASHSCOPE_API_KEY="your_key"
```

无 API Key 时：
- 自动进入 mock 模式
- 返回固定结构 JSON
- 演示可正常运行

执行研判：
```bash
python src/main.py analyze-alerts --limit 100
```

输出字段：
- `attack_type`
- `risk_level`
- `reason`
- `suggestion`
- `confidence`
- `next_steps`

## 15. 每日安全态势简报

```bash
python src/main.py report
# 指定日期
python src/main.py report --date 2026-05-06
```

结果：
- ES: `daily-reports`
- 本地 Markdown: `data/daily_report_YYYY-MM-DD.md`

## 16. 启动 Streamlit 调试看板

```bash
streamlit run src/dashboard/app.py --server.port 8501
```

Streamlit 是历史 MVP 和调试入口，不是正式产品前端。页面包含：
- 系统概览
- 最近日志（多条件过滤）
- 异常事件（过滤 + 明细 + 重新 AI 研判）
- AI 研判
- 用户风险排行
- 规则命中统计
- 每日安全态势简报
- 系统运行状态

## 16.1 启动 React 正式前端

React 工作台从 FastAPI 读取正式 API，不直连 Elasticsearch、Kafka 或本地日志文件。当前已实现：
- 实时日志：`GET /api/v1/logs`
- 异常事件：`GET /api/v1/alerts`, `GET /api/v1/alerts/{alert_id}`
- 系统状态：`GET /api/v1/health`

```bash
# Terminal 1: FastAPI
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: React
cd frontend
npm install
npm run dev
```

Vite 开发服务器默认运行在 `http://localhost:5173/`，并把 `/api` 代理到 `http://127.0.0.1:8000`。如需代理到其他 FastAPI 地址，可设置 `VITE_API_PROXY_TARGET`。

## 17. 命令行入口

```bash
python src/main.py init
python src/main.py inspect-generator
python src/main.py produce
python src/main.py process-raw
python src/main.py consume-to-es
python src/main.py build-baseline
python src/main.py detect
python src/main.py analyze-alerts
python src/main.py report
python src/main.py health
```

## 18. 当前 MVP 调试流程

1. `docker compose up -d`
2. `python src/main.py health`
3. `python src/main.py init`
4. `python src/main.py inspect-generator`
5. `python src/main.py produce --run-generator --format jsonl --days 1 --count 120`
6. 提交并运行 Flink `raw_to_parsed` 任务（或运行 `python src/main.py process-raw` 兜底）
7. `python src/main.py consume-to-es`
8. `python src/main.py build-baseline`
9. `python src/main.py analyze-alerts`
10. `python src/main.py report`
11. `streamlit run src/dashboard/app.py`

正式验收流程以后续 React + FastAPI 工作台和 `docs/06_acceptance_checklist.md` 为准。

## 19. 常见问题

1. `KafkaNoBrokersAvailable`
- 检查 `docker compose ps`
- 确认 `KAFKA_BOOTSTRAP_SERVERS` 与端口一致

2. Flink 作业提交后无数据
- 先确认 `raw_logs` 有消息
- 检查 job log 的 Kafka connector 依赖
- 可先用 Python 检测模块跑通主链路，再逐步增强 Flink 规则

3. ES 写入失败
- 检查 `http://localhost:9200/_cluster/health`
- 开发模式需保持 `xpack.security.enabled=false`

4. 无 DASHSCOPE_API_KEY
- 属于预期：系统自动 mock 模式

## 20. 后续扩展路线

- 把更多规则迁移到 Flink 窗口计算
- 支持 OA/API/system/security_device 多类型解析器
- 引入规则配置中心与工单联动
- 增加图数据库/时间序列关联分析
- AI 报告增加处置优先级和自动化剧本建议
