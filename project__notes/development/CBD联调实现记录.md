# C / B / D 联调实现记录

本文件记录分支 `feature/junjie-cbd-integration` 对 `6.4日最新开发要求.md` 中 C / B / D 三个角色"未完成"项的实现情况，并对照 `docs/00_project_baseline.md` 标注覆盖与仍未覆盖的需求。

- 验证：`docker compose run --rm tester` → **103 passed**（基线 95 passed / 1 failed；本轮新增 8 个测试并修复原失败用例）。
- 验证：`cd frontend && npm run build`（`tsc --noEmit` + `vite build`）→ 通过。

## 一、对照 6.4 文档"未完成"项

### C 角色：数据链路与真实性

| 6.4 未完成项 | 状态 | 实现 |
| --- | --- | --- |
| `raw_to_parsed` 从 Kafka latest offset 起始，Filebeat 先写则漏处理 | ✅ 已实现 | `flink_jobs/raw_to_parsed.py` 改为 `committed_offsets(EARLIEST)`，无提交位点时回退最早，重启不丢/不重复 |
| 默认启动不自动提交 Flink，Kafka 有数据但 ClickHouse 没入库 | ✅ 已实现 | 新增默认开启的轻量 `raw-to-parsed` 服务（复用 backend 镜像 + 已测的 `process-raw` CLI）；Flink 仍是正式路径（`--profile jobs`），event_id 稳定→`ReplacingMergeTree` 折叠重复 |
| data quality 计数主要由 manifest 推导，不是真实分段计数 | ✅ 已实现 | 新增 `ClickHouseStorage.security_logs_daily_counts`，`parsed_logs_count`/`clickhouse_insert_count`/缺失率按"日期+源"直接从 ClickHouse 统计；旧 adapter 自动回退 manifest 路径 |
| 多源解析：`source_type_hint` 硬编码 `vpn` | ✅ 已实现 | 改为 `system` 兜底，信任 Filebeat envelope 的 7 类 `source_type` |
| 未跑完整 P0 E2E | ⛔ 环境受限 | 本环境无法构建/运行重型 PyFlink 全链路；保留为联调任务 |
| scale profile 缺 1GB/day 实测、压缩率、查询耗时记录 | ⛔ 环境受限 | 需真实跑 `--profile scale` 出数，保留为压测任务 |

> 附带修复：`tester` 服务挂载 `docker-compose.yml`（只读），修复 `test_docker_compose_detector.py` 在容器内的 `FileNotFoundError`（原基线唯一失败用例）。

### B 角色：行为 baseline

| 6.4 未完成项 | 状态 | 实现 |
| --- | --- | --- |
| `aggregate_daily_features` 每日最多拉 100000 条进 Python 内存 | ✅ 已实现 | 新增 `ClickHouseStorage.aggregate_daily_features_sql`，日级特征用 `GROUP BY (tenant_id, user_id)` 在 ClickHouse 内聚合；Python 侧只整形少量聚合行 |
| 日级特征写入不幂等，重复 rebuild 会重复插入 | ✅ 已实现 | `insert_user_daily_features` 先按 `(tenant_id, feature_date)` `ALTER … DELETE` 再插；DDL 改 `ReplacingMergeTree(created_at)` 双保险 |
| 五W1H 产品化展示 | ✅ 已实现（前端，见 D） | 用户画像页七 profile → Who/When/Where/What/Why/How |
| `why_profile` 基本为空，维护窗口/白名单/业务上下文未成型 | ⛔ 未覆盖 | 属更大的建模工作，保留为后续 |
| peer/global fallback 仍是字段标记，无真实 peer group/global 计算 | ⛔ 未覆盖 | 同上，保留为后续 |
| baseline 稳定参与异常评分 | ⛔ 未覆盖 | 评分接入在检测侧（A 角色 `rules.py`/`anomaly_builder.py`），见第三节 |

### D 角色：AI / 前端 / 接口

| 6.4 未完成项 | 状态 | 实现 |
| --- | --- | --- |
| `POST /ai/judge/{event_id}` 不把 AI feedback suggestions 拆入 `ai_feedback`，闭环未完成 | ✅ 已实现 | 研判后将 `feedback_suggestions` 拆成 `pending` 的 `ai_feedback` 行（best-effort，失败不影响已落库的研判；不自动改规则/基线） |
| AI 候选门控不严格，可对任意 anomaly 调用 | ✅ 已实现 | 仅 `high`/`critical` 或 `ai_status=pending` 可触发，`?force=true` 越权；非候选返回 409 |
| 用户画像仍展示七个 profile，未产品化为五W1H | ✅ 已实现 | `frontend/src/App.tsx` 新增 `FiveW1HSections`，原始 JSON 收进 debug `<details>` |
| System Status 缺 baseline coverage、AI pending、日报生成状态 | ✅ 已实现 | `get_stats_overview` 单次查询新增 `ai_pending_count`/`baseline_user_count`/`latest_report_date`，前端 System Status 增指标带 |
| 内部命名残留 `Alert`/`Alerts`/`alerts` | 🟡 部分 | 后端函数名被测试直接 import（契约），按 `D成员后续事务.md` 保持稳定、逐步清理；本轮不强改 |

## 二、对照基线需求（REQ-*）覆盖

| REQ | 本轮相关改动 |
| --- | --- |
| REQ-002 日志结构化 | C：Flink 多源兜底 + offset 修复，真实分段数据质量计数 |
| REQ-003 行为建模 | B：日级特征聚合下推 + 幂等；D：五W1H 产品化展示 |
| REQ-004 智能研判 | D：AI 反馈闭环（`ai_feedback`）+ 候选门控（LLM 只吃高可疑事件，符合基线"AI 研判"口径） |
| REQ-006 可视化交互 | D：System Status 新指标、用户画像五W1H |
| REQ-008 实时告警与扩展 | C：默认启动即可端到端入库，异常检测有数据可读 |

## 三、对比基线后发现、本轮未覆盖的要求（建议后续小 PR）

以下为对照 `docs/00_project_baseline.md`「主线约束 / 技术基线」发现、且**不在本轮 C/B/D 改动范围内**的缺口，集中记录便于分工：

1. **新来源判断仍依赖进程内存**（违反主线约束"不得只依赖检测进程内存"）。`user_seen_sources` 表与 `query_user_seen_sources` 已具备（B 已落地持久化），但 `src/detection/rules.py` 的新 IP 规则仍用进程内 `known_login_ips`。建议后续把规则改为查询 `user_seen_sources`。属 A 角色（检测）范围，故本轮仅标注不改。
2. **维护窗口 / 白名单 / 反馈修正未进入评分闭环**（主线约束）。属 A 角色评分逻辑。
3. **baseline 偏离稳定参与 risk_score**。当前 `anomaly_builder` 有 `baseline_deviations` 字段，但多数规则事件未真正接入历史 baseline 偏离证据。属 A 角色。
4. **`system_metrics` 表无写入方**。技术基线列出该表，但目前无组件写入。可作为可观测性小补充（C/运维向）。
5. **真实 Kafka/Flink 分段计数**。本轮数据质量已用真实 ClickHouse 计数；`raw_logs_count` 仍取 manifest，若要"Kafka 收到多少 / Flink 解析多少"的真值需读 Kafka topic offset，留待后续。
6. **场景规则覆盖**（REQ-007）。服务账号异常、横向移动等场景已生成，但规则侧覆盖不完整。属 A 角色。

## 四、关键技术决策

- **不重命名后端 `Alert*` 函数**：`list_alerts`/`analyze_alert`/`get_alert_detail` 等被测试直接 import，且 `D成员后续事务.md` 要求"逐步清理"——内部改名只在前端做，后端保持接口契约稳定。
- **默认入库用轻量 Python worker 而非改 Flink 默认提交**：本环境无法验证 Flink；Python 路径轻、已测，基线允许其作"链路隔离验证/测试数据输入"。Flink 仍是正式处理器。
- **`force` 用 `bool=False` 而非 `Query(...)`**：直连单测时 `Query()` 对象为真值会绕过候选门控（已在测试中暴露并修正）。
- **数据质量"真实计数"做成可选能力**：storage 暴露 `security_logs_daily_counts` 时优先用真值，否则回退旧 manifest 估算，保证旧 adapter/测试不破。
