# 最终质量标准

本文件定义项目达到目标形态时应满足的质量标准。

代码存在不等于功能完成。系统必须能从数据、模型、异常、AI 和页面多个层面证明其安全分析价值。

## 架构标准

- [ ] 主链路为 `Filebeat -> Kafka -> Flink -> ClickHouse -> FastAPI -> React`。
- [ ] ClickHouse 是唯一主存储和分析引擎。
- [ ] Elasticsearch 不作为运行时依赖。
- [ ] React 只通过 FastAPI 获取业务数据。
- [ ] FastAPI 不把底层表结构作为前端依赖。
- [ ] Python Producer 和前端 mock 数据只作为调试工具。

## 数据规模标准

- [ ] 每日原始增量日志不少于 1GB。
- [ ] 能记录原始日志大小和原始日志条数。
- [ ] 能记录 Kafka、Flink、ClickHouse 的处理数量。
- [ ] 能记录字段缺失率。
- [ ] 能记录异常注入数量。
- [ ] 能记录 ClickHouse 表大小和实测压缩率。

## 数据契约标准

- [ ] 标准化日志包含 `event_id`, `event_time`, `ingest_time`, `source_type`, `user_id`, `src_ip`, `action`, `result`, `raw_log`。
- [ ] 异常事件包含 `risk_score`, `risk_level`, `rule_hits`, `baseline_deviations`, `reason_codes`, `evidence`。
- [ ] AI 研判和 AI 反馈分别落入独立数据对象。
- [ ] 时间字段语义一致。
- [ ] API、前端和表结构对同一字段的含义一致。

## ClickHouse 标准

- [ ] 存在 `security_logs` 主日志表。
- [ ] 存在用户日级特征表。
- [ ] 存在用户 baseline 表。
- [ ] 存在异常事件表。
- [ ] 存在 AI 研判表和反馈表。
- [ ] 核心查询字段显式成列。
- [ ] 表结构包含分区、排序键和 TTL 设计。
- [ ] 支持按时间、用户、IP、行为、日志类型查询。
- [ ] 支持按用户、行为、结果、风险等级聚合。

## 行为建模标准

- [ ] baseline 基于历史日志 T+1 生成。
- [ ] baseline 至少覆盖 Who、When、Where、What、How。
- [ ] Why 维度至少支持维护窗口、白名单或业务上下文中的一种。
- [ ] 每个用户有可查询的日级特征和 baseline。
- [ ] baseline 包含样本天数和模型版本。
- [ ] 样本不足时有 peer group 或全局 baseline 兜底。
- [ ] 异常事件能展示 baseline 偏离原因。

## 检测与评分标准

- [ ] 支持暴力破解、凭证填充、账号接管、数据窃取、权限滥用中的至少 3 类。
- [ ] 风险分范围为 0 到 100。
- [ ] 风险等级包含 `low`, `medium`, `high`, `critical`。
- [ ] 每个高风险事件包含 reason codes。
- [ ] 非工作时间登录但无敏感行为，不应直接升为 `critical`。
- [ ] 命中维护窗口或白名单时，风险应被合理修正。

## AI 标准

- [ ] AI 只分析高可疑异常事件。
- [ ] AI 输入为结构化证据包。
- [ ] AI 输出为结构化 JSON。
- [ ] AI 输出包含风险等级、攻击类型、关键原因、处置建议和置信度。
- [ ] AI 研判写入 `ai_judgements`。
- [ ] AI 反馈写入 `ai_feedback`。
- [ ] AI 反馈不直接自动修改生产规则。
- [ ] mock 输出必须明确标记。

## 前端标准

- [ ] 实时日志页面展示真实入库数据。
- [ ] 异常事件页面展示风险分、风险等级、reason codes 和证据链。
- [ ] 用户画像页面展示五W1H baseline。
- [ ] AI 研判页面展示结构化 AI 输出。
- [ ] 安全态势简报页面展示真实统计结果。
- [ ] 系统状态页面展示 Kafka、Flink、ClickHouse、baseline 和 AI 状态。

## 场景标准

- [ ] 正常用户场景不会被夸大为高危事件。
- [ ] 暴力破解场景能生成异常事件。
- [ ] 凭证填充场景能生成异常事件。
- [ ] 账号接管场景能生成高风险事件。
- [ ] 数据窃取场景能生成高风险事件。
- [ ] 权限滥用场景能生成异常事件。
- [ ] 每个关键场景都能从原始日志追踪到异常事件和页面结果。

## 已确认的边界标准

- [ ] Filebeat 是正式采集入口，Python Producer 只作为辅助工具。
- [ ] Flink 负责清洗、字段标准化、轻量规则和窗口统计，不承担完整 T+1 baseline。
- [ ] 规则检测、窗口统计和 baseline 偏离统一输出 `AnomalyEvent`。
- [ ] 内部风险等级统一为 `low`, `medium`, `high`, `critical`。
- [ ] 新来源判断基于 baseline、日级特征或持久化 seen 表，不只依赖进程内存。
- [ ] VPN 日志是第一类日志源，不代表全部目标数据集。
- [ ] 生成器画像不直接作为系统行为 baseline。

## 文档标准

- [ ] 项目目标和主架构口径一致。
- [ ] 数据契约、API 契约和表结构一致。
- [ ] 关键技术选择记录在 ADR 中。
- [ ] 文档不把临时做法写成主线要求。
- [ ] 文档不以一次性页面效果替代系统真实能力。
