# AI 研判与反馈规格

本文件定义 AI 在日志安全分析中的边界、输入、输出和反馈机制。

AI 不负责原始检测。AI 只对已经筛选出的高可疑事件进行证据化研判。

AI 的输入对象必须来自统一的 `AnomalyEvent` 证据包。旧式 `AlertEvent` 或单独规则告警不能作为目标形态中的 AI 输入契约。

## AI 使用原则

- AI 不分析全量日志。
- AI 不直接决定是否存在异常。
- AI 输入必须是结构化证据包。
- AI 输出必须是结构化 JSON。
- AI 结论必须能追溯到输入证据。
- AI 输出应进入反馈表，用于辅助校准规则、baseline 和评分。
- AI 反馈不能未经确认直接修改生产规则。

## AI 候选事件

进入 AI 的事件应满足至少一个条件：

- 风险等级为 `high` 或 `critical`。
- 风险分超过配置阈值。
- 同时命中规则和 baseline 偏离。
- 涉及敏感资源、提权、批量下载、异常来源等高价值对象。
- 当前事件属于攻击链中的关键步骤。

低风险事件默认不进入 AI，除非用于抽样分析或策略评估。

## 证据包格式

AI 输入不是原始日志列表，而是结构化证据包。

```json
{
  "event_id": "anom-001",
  "tenant_id": "tenant_alpha",
  "event_time": "2026-05-19T03:12:00Z",
  "user": {
    "user_id": "alice",
    "role": "employee",
    "department": "finance"
  },
  "anomaly": {
    "risk_score": 87.5,
    "risk_level": "critical",
    "reason_codes": [
      "rare_login_hour",
      "new_source_ip",
      "sensitive_resource_access"
    ],
    "rule_hits": ["new_ip_sensitive_access"]
  },
  "baseline_evidence": {
    "usual_login_hours": "09:00-19:00",
    "current_login_hour": "03:12",
    "common_src_ips": ["10.1.2.3", "10.1.2.4"],
    "current_src_ip": "203.0.113.10",
    "historical_failed_login_p95": 5,
    "current_failed_login_count": 18
  },
  "related_logs": [
    {
      "event_time": "2026-05-19T03:10:00Z",
      "action": "login",
      "result": "success",
      "src_ip": "203.0.113.10"
    },
    {
      "event_time": "2026-05-19T03:12:00Z",
      "action": "download_sensitive_file",
      "result": "success"
    }
  ],
  "window_stats": {
    "failed_login_count_5m": 18,
    "sensitive_access_count_10m": 3
  }
}
```

## AI 输出格式

AI 输出必须符合固定结构。

```json
{
  "risk_level": "critical",
  "attack_type": "account_takeover",
  "judgement": "该事件疑似账号被盗用后访问敏感资源。",
  "key_reasons": [
    "登录时间显著偏离历史习惯",
    "来源 IP 不在用户常用来源中",
    "登录后短时间内访问敏感资源"
  ],
  "recommended_actions": [
    "临时冻结该账号的高危操作",
    "核查来源 IP 和登录设备",
    "回溯该账号最近 24 小时访问记录"
  ],
  "confidence": 0.86,
  "feedback_suggestions": {
    "rule_weight": [
      {
        "rule_id": "new_ip_sensitive_access",
        "suggestion": "保持高权重"
      }
    ],
    "baseline_threshold": [
      {
        "feature": "rare_login_hour",
        "suggestion": "对财务用户夜间敏感访问提高风险加成"
      }
    ]
  }
}
```

## 反馈机制

AI 输出应写入两个对象：

- `ai_judgements`：保存本次 AI 研判结果。
- `ai_feedback`：保存可用于后续校准的建议。

反馈类型包括：

| 类型 | 含义 |
| --- | --- |
| `rule_weight` | 调整规则权重建议。 |
| `baseline_threshold` | 调整 baseline 阈值建议。 |
| `false_positive` | 疑似误报建议。 |
| `new_pattern` | 新攻击模式建议。 |
| `data_contract` | 字段缺失或证据不足建议。 |

## 反馈治理

AI 反馈不得直接自动修改生产规则。

可采用以下流程：

```text
AI feedback
  -> pending
  -> accepted or rejected
  -> rule config / baseline config update
  -> new model_version or rule_version
```

当反馈被采纳时，必须记录：

- 关联事件。
- 采纳时间。
- 影响组件。
- 新版本号。
- 影响说明。

## mock 输出要求

无模型密钥或模型不可用时，可以使用 mock 输出。

mock 输出必须明确标记，不能伪装成真实模型结果。

## 不允许的做法

- 将全量日志直接输入 AI。
- 让 AI 单独决定异常是否成立。
- 不提供 baseline 证据就要求 AI 判断攻击类型。
- AI 输出自然语言长文但不落结构化字段。
- AI 反馈直接修改生产规则。
