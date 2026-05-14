# Acceptance Checklist

项目评审以本清单为准。代码存在不等于功能完成；必须能通过链路、数据、页面和场景验证。

## Stage 0: 口径冻结

- [ ] `docs/00_gold_standard.md` 已维护甲方原始需求编号。
- [ ] 新功能、页面、接口和规则都能追溯到 `REQ-*`。
- [ ] 重大技术选择记录在 `docs/02_architecture_decisions.md`。
- [ ] Streamlit 被标记为调试入口，不作为正式前端。

## Stage 1: 正式实时链路

- [ ] Filebeat 能监听日志文件新增内容。
- [ ] 新增日志能进入 Kafka `raw_logs`。
- [ ] Flink 能消费 `raw_logs` 并写入 `parsed_logs`。
- [ ] 结构化日志能写入 ES `security-logs`。
- [ ] 系统健康检查能显示 Kafka、Flink、ES 状态。
- [ ] Python Producer 和 `process-raw` 仅作为调试路径出现在文档中。

## Stage 2: Baseline 与检测

- [ ] 能从 ES 日志构建 `user-baselines`。
- [ ] Baseline 包含活跃时间、常用 IP、API 频率、常用资源、失败登录和敏感访问率。
- [ ] 告警包含 `rule_hits`、`evidence`、`related_event_ids`。
- [ ] 高质量告警包含或预留 `baseline_deviations`。
- [ ] 风险等级与 `低/中/高/紧急` 口径一致。
- [ ] 至少实现暴力破解、凭证填充、账号接管、数据窃取、权限滥用中的 3 类。

## Stage 3: AI 研判

- [ ] AI 输入包含 alert、baseline、related_logs。
- [ ] AI 输出结构化 JSON，包括攻击类型、风险等级、原因、建议、置信度、后续动作。
- [ ] 无 API Key 时 mock fallback 明确标识，不能伪装成真实模型输出。
- [ ] AI 报告写入 ES `ai-reports`。
- [ ] 告警状态能从 `new` 更新为 `analyzed`。

## Stage 4: React + FastAPI 工作台

- [ ] FastAPI 提供 `docs/05_api_contract.md` 中定义的核心接口。
- [ ] React 页面只通过 FastAPI 读取数据。
- [ ] 前端不生成核心业务数据，不直连 ES。
- [ ] 实时日志页面展示 ES 中的真实结构化日志。
- [ ] 异常事件页面能展示证据链和 AI 研判。
- [ ] 用户基线页面能展示用户画像和偏离依据。
- [ ] 日报页面能展示已生成日报并支持触发生成。
- [ ] 系统状态页面能展示 Kafka/Flink/ES 和最近入库时间。

## Stage 5: 场景复现

- [ ] 正常登录场景：常用 IP、工作时间登录，不触发高危告警。
- [ ] 暴力破解场景：同 IP 或同账号短时间多次失败登录，触发告警。
- [ ] 凭证填充场景：同 IP 对多个用户失败登录，触发告警。
- [ ] 账号接管场景：新 IP 登录成功后出现敏感访问，触发高危告警。
- [ ] 数据窃取场景：短时间大量下载或导出敏感数据，触发高危告警。
- [ ] 权限滥用场景：普通用户访问 admin/config/backup，触发告警。
- [ ] 每个场景都能从原始日志追踪到 Kafka、Flink、ES、FastAPI、React 页面。

## Final Review

- [ ] 运行文档可复现完整链路。
- [ ] 所有核心接口有示例响应或可通过 OpenAPI 查看。
- [ ] 所有核心页面能用真实入库数据展示。
- [ ] 每日安全态势简报能生成、落库、展示。
- [ ] 项目说明清楚标注正式路径和调试路径。
- [ ] 未满足项必须记录原因、影响和后续修复计划。
