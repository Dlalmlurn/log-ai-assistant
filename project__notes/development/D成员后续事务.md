# D 成员后续事务

本文件记录本轮 `feature/zike-workbench-ai-report-p2` 先不展开、但后续必须补齐的事项。

## 命名清理

- 前端本轮只把用户可见文案从 Alerts 迁到 Anomalies。
- 后续需要把内部组件、函数、类型和 CSS 命名里的 `Alert` / `Alerts` / `alerts` 逐步改为 `Anomaly` / `Anomalies` / `anomalies`。
- 清理时不得恢复旧 `/api/v1/alerts` 路径。

## feedback 来源

- 本轮不改 ClickHouse schema，`POST /api/v1/feedback` 复用现有 `ai_feedback` 表。
- 后续如果改表成本可接受，应增加反馈来源字段，例如 `feedback_source`，区分 `human` 和 `ai_suggestion`。
- 增加来源字段后，需要同步更新 `AIFeedback`、ClickHouse 初始化 SQL、storage insert、API 测试和前端提交模型。

## 用户画像产品化

- 本轮用户画像页按数据契约直接展示七个 profile：`who_profile`、`time_profile`、`location_profile`、`access_profile`、`volume_profile`、`result_profile`、`why_profile`。
- B 成员 baseline 完成后，需要把七个 profile 产品化映射为五W1H 视图，并保留原始 JSON 作为排障视图。

## 系统状态与工作台

- 本轮把 `stats/overview` 和用户风险排行接入 System Status。
- 后续需要评估是否拆出独立 Overview 工作台首页，并补充 AI pending、baseline coverage、日报生成状态等指标。

## 用户风险排行增强

- 本轮 `GET /api/v1/stats/users/risk` 仅基于 `anomaly_events` 聚合。
- B 成员 baseline 完成后，需要接入 `baseline_confidence`、`fallback_level`、`sample_days` 等字段，并明确低置信度 baseline 的展示方式。
