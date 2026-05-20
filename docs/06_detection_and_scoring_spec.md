# 检测与评分规格

本文件定义规则检测、窗口统计、baseline 偏离、风险评分、风险等级和证据链。

## 检测目标

系统需要发现以下安全风险：

- 暴力破解。
- 凭证填充。
- 账号接管。
- 内部数据窃取。
- 权限滥用。
- 横向移动。
- 异常自动化访问。
- 服务账号异常。
- 系统异常组合。

## 统一输出原则

规则检测、窗口统计、baseline 偏离和评分可以由不同内部模块完成，但对外必须统一产出 `AnomalyEvent`。

不得让 RuleEngine、UEBA Scorer、Flink rule job 或其他检测模块分别向前端、AI、日报输出不同形态的告警对象。

统一异常事件必须包含：

- `risk_score`
- `risk_level`
- `risk_components`
- `rule_hits`
- `baseline_deviations`
- `reason_codes`
- `evidence`
- `related_event_ids`
- `ai_status`

## 检测流程

```text
NormalizedLog
  -> rule detection
  -> window statistics
  -> baseline deviation
  -> risk scoring
  -> AnomalyEvent
  -> AI candidate selection
```

Flink 可以承担清洗、窗口统计和轻量规则预处理。完整 T+1 baseline 不在实时流中硬编码完成。

## 规则与 baseline 的关系

规则负责发现明确异常信号。

baseline 负责判断这个信号对具体用户是否异常。

示例：

| 场景 | 规则 | baseline 解释 |
| --- | --- | --- |
| 5 分钟内登录失败 20 次 | 命中失败登录规则 | 该用户历史 p95 为 3 次，明显偏离。 |
| 凌晨登录 | 命中非常用时间规则 | 该用户过去 30 天从未在 0 点到 6 点登录。 |
| 新 IP 登录 | 命中新来源规则 | 该来源 IP 不在常用 IP、常用网段或 seen 表内。 |
| 大量下载 | 命中下载频率规则 | 当日下载量超过历史 p99。 |

只有规则命中也可以形成异常事件，但风险解释必须说明 baseline 证据不足。

只有 baseline 偏离时，应结合敏感行为或多个弱信号再提升风险等级。

## 规则库种子

第一版规则库至少包含以下规则种子：

| 规则 | 目标风险 | reason code |
| --- | --- | --- |
| 同一账号短时间多次登录失败 | 暴力破解 | `failed_login_spike` |
| 同一来源 IP 对多个账号失败登录 | 凭证填充 | `credential_stuffing_pattern` |
| 新来源登录 | 账号接管前置信号 | `new_source_ip` |
| 非常用时间登录 | 账号接管前置信号 | `rare_login_hour` |
| 高频 API 调用 | 异常自动化访问 | `high_api_rate` |
| 短时间敏感资源访问 | 数据窃取或权限滥用 | `sensitive_resource_access` |
| 新来源登录后访问敏感资源 | 账号接管或数据窃取 | `new_source_then_sensitive_access` |
| 普通账号访问管理资源 | 权限滥用 | `admin_resource_access` |
| 系统 error 或 critical 组合 | 系统异常 | `system_error_pattern` |
| 服务账号异常来源或异常时间 | 服务账号异常 | `service_account_anomaly` |
| 同一来源短时间访问多个内网目标 | 横向移动 | `lateral_movement_signal` |

规则库种子可以扩展，但新增规则必须写清楚输入字段、窗口、阈值、reason code 和证据字段。

## 风险评分

风险分范围为 0 到 100。

建议组成：

| 部分 | 权重 | 含义 |
| --- | --- | --- |
| 规则强度 | 25 | 规则本身的确定性。 |
| baseline 偏离 | 35 | 对用户历史行为的偏离程度。 |
| 行为敏感度 | 20 | 是否涉及敏感资源、提权、下载、删除等。 |
| 事件关联度 | 10 | 是否与前后可疑行为组成攻击过程。 |
| 反馈修正 | 10 | 历史反馈、白名单、维护窗口等上下文。 |

权重可以调整，但必须记录版本和理由。

## 风险等级

| 等级 | 分数范围 | 含义 | 典型动作 |
| --- | --- | --- | --- |
| `low` | 1 到 25 | 单一弱信号或轻微偏离。 | 记录并观察。 |
| `medium` | 26 到 50 | 明显偏离或多个弱信号。 | 安全人员复核。 |
| `high` | 51 到 75 | 多项异常叠加或涉及敏感资源。 | 优先调查，限制高危动作。 |
| `critical` | 76 到 100 | 疑似攻击正在发生或影响重大。 | 启动应急处置。 |

内部字段统一使用英文枚举。前端可以映射为中文展示。

## reason codes

每个异常事件必须包含 reason codes。

完整 ReasonCode 注册表以 `03_data_contract.md` 为准。本节列出检测与评分规格必须覆盖的核心 code。新增 code 时，应先更新数据契约，再更新检测逻辑和 API 过滤能力。

核心 reason codes：

| code | 含义 |
| --- | --- |
| `failed_login_spike` | 登录失败次数异常增加。 |
| `credential_stuffing_pattern` | 同一来源尝试多个账号。 |
| `rare_login_hour` | 登录时间偏离历史习惯。 |
| `new_source_ip` | 来源 IP 首次出现或不常见。 |
| `new_geo_location` | 来源地理位置异常。 |
| `new_device_or_host` | 新设备或新主机来源。 |
| `high_api_rate` | API 调用频率异常升高。 |
| `sensitive_resource_access` | 访问敏感资源。 |
| `new_source_then_sensitive_access` | 新来源登录后访问敏感资源。 |
| `download_volume_spike` | 下载量显著增加。 |
| `vpn_traffic_volume_spike` | VPN 会话流量异常增加。 |
| `permission_change` | 权限变更行为。 |
| `admin_resource_access` | 普通账号访问管理资源。 |
| `lateral_movement_signal` | 疑似横向访问多个目标。 |
| `service_account_anomaly` | 服务账号行为异常。 |
| `system_error_pattern` | 系统错误或关键异常组合。 |
| `insufficient_history` | 用户历史样本不足。 |
| `low_baseline_confidence` | baseline 置信度不足。 |
| `peer_group_fallback` | 使用 peer group baseline 降级判断。 |
| `global_baseline_fallback` | 使用全局 baseline 降级判断。 |
| `maintenance_window` | 命中维护窗口。 |
| `allowlisted_context` | 命中白名单上下文。 |

## 新来源判断要求

新来源判断不得只依赖检测进程内存。

目标形态中，新来源应基于以下至少一种持久化依据：

- 用户 baseline 中的常见来源。
- 用户日级特征中的历史来源统计。
- `user_seen_sources` 表。
- peer group 或全局来源统计。

内存缓存只能作为短窗口优化，不能作为最终证据来源。

## VPN 大流量语义

VPN 日志中的大流量会话可以作为数据外传风险信号。

但它不能替代独立的 `file_download`、`file_access`、`database_export` 或 API 导出日志。

目标形态中的数据窃取场景应至少包含一种独立资源访问、下载或导出类日志。

## 异常事件证据链

每个高质量异常事件应包含：

- 命中规则。
- 窗口统计。
- baseline 偏离。
- 相关日志列表。
- 风险分组成。
- reason codes。
- 是否需要 AI 研判。

示例：

```json
{
  "risk_score": 82,
  "risk_level": "critical",
  "reason_codes": [
    "new_source_ip",
    "rare_login_hour",
    "sensitive_resource_access"
  ],
  "risk_components": {
    "rule_strength": 21,
    "baseline_deviation": 31,
    "behavior_sensitivity": 18,
    "event_correlation": 8,
    "feedback_adjustment": 0
  },
  "evidence": {
    "baseline": {
      "usual_login_hours": "09:00-19:00",
      "current_login_hour": "03:12"
    },
    "rule_hits": ["new_source_then_sensitive_access"],
    "related_events": ["evt-1", "evt-2"]
  }
}
```

## 关键场景要求

系统至少支持以下场景：

- 正常工作时间从常用 IP 登录，不应产生高风险事件。
- 同一 IP 短时间多账号失败登录，应识别为凭证填充或暴力破解。
- 新 IP 登录后短时间访问敏感资源，应识别为账号接管或数据窃取风险。
- 非工作时间登录但无敏感行为，风险不得直接升为 `critical`。
- 普通用户访问 admin、config、backup 等资源，应形成高风险事件。
- 服务账号从异常主机登录，应结合账号类型和来源判断风险。

## 误报控制

以下情况应降低风险或标记上下文：

- 命中维护窗口。
- 命中业务任务。
- 命中白名单。
- 用户历史样本不足。
- 只有单一弱信号。
- peer group 中大量用户同时出现类似行为，且有业务解释。

误报控制不能直接删除异常事件。应保留事件并降低风险等级或添加 reason code。
