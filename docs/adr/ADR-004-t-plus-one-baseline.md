# ADR-004: T+1 历史数据行为 baseline

**Status:** accepted

## Decision

用户行为 baseline 采用五W1H 框架，并优先基于历史数据进行 T+1 建模。

实时流不承担完整 baseline 计算。

## Context

当前 baseline 和异常评分已有初步实现，但容易被认为是硬编码规则。导师建议基于 Who、When、Where、What、Why、How 构建行为基线，并优先使用历史数据。

行为 baseline 需要统计稳定的用户习惯，实时流中直接计算容易样本不足，也难以解释。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 实时流中直接计算完整 baseline | 不采用 | 复杂度高，样本和解释性不足。 |
| 只用固定规则 | 不采用 | 容易退化为硬编码。 |
| T+1 历史特征和 baseline | 采用 | 更适合行为建模和解释。 |

## Rationale

T+1 建模能利用稳定历史窗口，适合计算均值、分位数、常用来源、活跃时间和行为分布。

五W1H 能让用户行为画像更完整，也方便异常事件解释。

## Consequences

- 需要 `ueba_user_daily_features` 表。
- 需要 `ueba_user_baseline` 表。
- 异常事件必须能展示 baseline 偏离证据。
- 样本不足时需要 peer group 或全局 baseline。
- 评分逻辑必须记录模型版本。
