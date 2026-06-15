# ADR-010: 周期 baseline 与审核覆盖层

**Status:** accepted

## Decision

用户行为 baseline 在 T+1 日级特征之上建立多周期统计画像，至少支持全局、滚动、星期和月度周期。

人工调整和审核通过的 AI 反馈不修改历史统计 baseline，而是写入独立、版本化、可撤销的 baseline override 层。检测时解析周期 baseline，并合并当前有效的 override，形成 effective baseline。

## Context

单一历史平均会掩盖企业行为中的周期规律。例如：

- 同一用户在星期一和周末的正常登录量不同。
- 财务用户在月末可能具有固定的报表导出高峰。
- 值班、维护窗口或阶段性业务任务可能只在特定日期范围内有效。

如果直接用 AI 或人工反馈改写统计 baseline，将无法区分“历史事实”和“策略例外”，也难以审计、解释和回滚。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 所有历史数据生成唯一 baseline | 不采用 | 无法表达星期、月末和近期行为变化。 |
| AI 反馈直接更新 baseline 行 | 不采用 | 污染历史统计，缺少审核和回滚能力。 |
| 每次反馈后重新训练并覆盖旧版本 | 不采用 | 成本高，且反馈与统计样本边界不清晰。 |
| 多周期统计 baseline + 独立 override | 采用 | 保留事实、支持业务例外、可审计且可回滚。 |

## Rationale

周期 baseline 能减少由于业务节奏造成的误报，并使偏离判断更贴近事件发生时的上下文。

独立 override 层允许系统吸收人工知识和 AI 建议，同时保持统计模型的来源可信。版本、有效期和状态使调整可以逐步生效、撤销和审计。

## Consequences

- `ueba_user_baseline` 需要增加 `period_type` 和 `period_key`。
- 需要新增 `ueba_baseline_overrides` 表。
- baseline 构建任务需要按周期切分训练样本并计算置信度。
- 检测器需要实现 effective baseline 解析和确定性的 fallback 顺序。
- 异常证据需要记录使用的周期、模型版本、fallback 和 override ID。
- AI 反馈需要人工审核接口；接受 baseline 建议时生成 override。
- 授权用户可以手动创建 override，但必须记录理由、操作者、有效期和版本。
- override 必须支持拒绝、撤销和到期失效。
- 历史统计 baseline 不得被反馈原地修改。
