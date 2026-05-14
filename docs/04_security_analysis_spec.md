# Security Analysis Spec

本文件定义 baseline、规则、风险分级、攻击类型和 AI 研判边界。后续检测逻辑必须围绕证据链构建，不能只靠单条规则或一句 prompt。

## Analysis Pipeline

```text
NormalizedLog
  -> rule/window detection
  -> baseline deviation check
  -> AlertEvent with evidence
  -> AI analysis with alert + baseline + related_logs
  -> AIReport + dashboard + daily report
```

## Baseline Dimensions

| 维度 | 字段 | 用途 |
| --- | --- | --- |
| 活跃时间 | `active_hours` | 判断非工作时间、异常时间段登录。 |
| 常用来源 | `common_ips` | 判断新 IP、异地或非常用网段。 |
| 客户端 | `common_user_agents` | 判断异常客户端或工具化访问。 |
| API 频率 | `avg_api_calls_per_minute` | 判断请求频率突增。 |
| 常用资源 | `common_resources` | 判断陌生系统、敏感接口访问。 |
| 失败登录 | `failed_login_count_7d` | 识别暴力破解和凭证风险背景。 |
| 敏感访问率 | `sensitive_access_rate` | 判断导出、下载、后台管理访问异常。 |

## Rule and Baseline Relationship

- 规则负责发现明确异常信号，例如 5 分钟内登录失败过多。
- Baseline 负责解释该信号对具体用户是否异常，例如该用户从未在凌晨登录。
- 告警必须尽量同时包含 `rule_hits` 和 `baseline_deviations`。
- 如果只有规则命中，仍可告警，但风险解释必须说明缺少 baseline 证据。
- 如果只有 baseline 偏离，需达到明确阈值或与敏感资源行为组合后再生成高危告警。

## Risk Levels

| 等级 | 分数区间 | 含义 | 示例处置 |
| --- | --- | --- | --- |
| 低 | 1-25 | 轻微偏离或单一弱信号。 | 记录并持续观察。 |
| 中 | 26-50 | 明显偏离或多次弱信号。 | 通知安全人员复核。 |
| 高 | 51-75 | 多项异常叠加或涉及敏感资源。 | 立即调查，限制高危操作。 |
| 紧急 | 76-100 | 疑似攻击正在发生或影响重大。 | 锁定账号，启动应急响应。 |

当前 MVP 中 `低/中/高` 对应 `30/60/90`，后续应调整为上表并补齐 `紧急`。

## Attack Types

| 攻击类型 | 典型证据 |
| --- | --- |
| 暴力破解 | 同一 IP 或同一账号短时间多次登录失败。 |
| 凭证填充 | 同一 IP 对多个账号进行失败登录尝试。 |
| 账号接管 | 新 IP、异地、非工作时间登录成功，随后出现异常访问。 |
| 内部数据窃取 | 大量下载、导出敏感数据、访问平时不访问的资源。 |
| 横向移动 | 短时间访问多个内网目标或管理接口。 |
| 权限滥用 | 普通用户访问 admin、config、backup 等高敏资源。 |
| 系统异常 | 系统日志中出现 error、critical 或服务异常组合。 |

## Evidence Chain

每个高质量告警应包含：

- 触发规则：哪些规则或窗口统计命中。
- 偏离基线：偏离了该用户哪些历史习惯。
- 相关日志：原始事件、后续行为、同窗口其他事件。
- 风险解释：为什么这个行为危险。
- 处置建议：建议检查、限制、封禁或回溯什么。

## AI Prompt Contract

AI 输入必须至少包含：

- `alert`: 完整 `AlertEvent`。
- `baseline`: 相关用户的 `UserBaseline`，若缺失必须显式传空对象。
- `related_logs`: 相关日志列表或摘要。
- `window_stats`: 同窗口统计数据，若无则传空对象。

AI 输出必须是 JSON，字段包括：

- `attack_type`
- `risk_level`
- `reason`
- `suggestion`
- `confidence`
- `next_steps`

禁止只把一句自然语言异常描述交给模型并直接采信结论。

## Scenario Requirements

验收场景至少包括：

- 正常工作时间从常用 IP 登录，不应产生高危告警。
- 同一 IP 5 分钟内多账号失败登录，识别为凭证填充或暴力破解。
- 新 IP 登录后短时间访问导出接口，识别为账号接管或数据窃取。
- 非工作时间登录但无敏感行为，风险不得被夸大为紧急。
- 普通用户访问 admin/config/backup 资源，生成高危或紧急告警。
