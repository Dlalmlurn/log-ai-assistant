# ADR-007: 统一异常事件对象

**Status:** accepted

## Decision

规则检测、窗口统计、baseline 偏离和风险评分必须统一产出 `AnomalyEvent`。

内部风险等级统一使用英文枚举：

```text
low, medium, high, critical
```

前端可以映射为中文展示。

## Context

项目中可能存在多个检测来源，例如实时规则、窗口统计、UEBA 偏离评分和离线分析。

如果这些模块分别向前端、AI 或日报输出不同结构的告警对象，系统会出现证据不一致、风险等级不一致和 AI 输入不稳定的问题。

## Alternatives

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| RuleEngine 和 UebaScorer 分别输出告警 | 不采用 | 容易形成两套告警语义，难以统一展示和 AI 研判。 |
| 只保留规则告警 | 不采用 | 无法体现历史 baseline 偏离。 |
| 统一 `AnomalyEvent` | 采用 | 有利于证据链、评分、AI 输入和前端展示统一。 |

## Rationale

统一异常对象可以把规则、窗口统计、baseline 偏离和风险评分汇总成一个可追踪事件。

这能让 AI 输入稳定，也能让前端和日报围绕同一业务对象展示。

## Consequences

- 数据契约必须定义 `AnomalyEvent`。
- `AnomalyEvent` 必须包含 `risk_score`、`risk_level`、`risk_components`、`rule_hits`、`baseline_deviations`、`reason_codes` 和 `evidence`。
- AI 输入必须来自 `AnomalyEvent` 证据包。
- 内部风险等级使用英文枚举。
- 中文风险名称只作为展示映射。
