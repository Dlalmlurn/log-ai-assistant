# 行为建模规格

本文件定义用户行为 baseline 的建模目标、五W1H 特征、T+1 计算方式和样本处理原则。

行为建模的目标不是用固定规则标记异常，而是从历史数据中形成用户正常行为画像，并为异常事件提供可解释证据。

## 建模原则

- baseline 必须来自入库后的历史日志和日级特征。
- baseline 优先采用 T+1 历史数据建模。
- 实时流不负责完整 baseline 计算。
- 生成器中的用户画像是数据生成先验，不等于系统 baseline。
- baseline 必须记录样本量、训练窗口、模型版本和置信度。
- 样本不足时不能简单认为没有风险，应使用降级 baseline 并写明 reason code。

## 建模路径

```text
security_logs
  -> daily feature calculation
  -> ueba_user_daily_features
  -> historical baseline calculation
  -> ueba_user_baseline
  -> anomaly scoring
```

`security_logs` 提供原始事实。`ueba_user_daily_features` 负责把每日行为压缩成可统计特征。`ueba_user_baseline` 负责记录历史正常画像。

## 五W1H 特征框架

| 维度 | 含义 | 示例特征 |
| --- | --- | --- |
| Who | 谁在操作。 | 用户、部门、角色、账号类型、peer group、常用主机。 |
| When | 什么时间操作。 | 小时分布、星期分布、常用活跃时间、夜间行为次数、首次和最后活跃时间。 |
| Where | 从哪里操作。 | 常用 IP、常用网段、常用国家城市、VPN 网关、来源主机。 |
| What | 做了什么。 | 登录、下载、导出、访问敏感资源、提权、失败操作。 |
| Why | 为什么操作。 | 维护窗口、工单、白名单、业务任务、已知上下文。 |
| How | 怎么操作。 | 协议、认证方式、客户端、User-Agent、设备类型、会话特征。 |

## Profile 分组

为了让 baseline 更清楚，可以把五W1H 落到以下 profile：

| Profile | 内容 | 主要对应维度 |
| --- | --- | --- |
| `who_profile` | 用户、角色、部门、账号类型、peer group。 | Who |
| `time_profile` | 小时分布、星期分布、常见活跃时间。 | When |
| `location_profile` | 常用 IP、IP 前缀、国家、城市、网关、来源主机。 | Where |
| `access_profile` | 常用资源、协议、认证方式、客户端、接口。 | What, How |
| `volume_profile` | 请求量、会话时长、上传量、下载量、访问量。 | What, How |
| `result_profile` | 成功率、失败率、错误率、拒绝率。 | What |
| `why_profile` | 维护窗口、白名单、工单、业务任务。 | Why |

这些 profile 可以作为 `UserBaseline` 的结构化字段，也可以拆成 `profile_group + feature_name` 的表结构。

## 数值特征要求

数值特征应尽量包含：

- 均值。
- 标准差。
- p50。
- p95。
- p99。
- 样本天数。
- 样本数量。
- 训练窗口。

示例：

| 特征 | 说明 |
| --- | --- |
| `failed_login_count` | 每日失败登录次数。 |
| `login_count` | 每日登录次数。 |
| `download_count` | 每日下载次数。 |
| `sensitive_action_count` | 每日敏感行为次数。 |
| `session_duration` | 会话时长。 |
| `traffic_volume` | 上传和下载流量。 |

## 类别特征要求

类别特征应记录常见集合和频率分布。

示例：

| 特征 | 说明 |
| --- | --- |
| `common_src_ips` | 常见来源 IP。 |
| `common_ip_prefixes` | 常见来源网段。 |
| `common_hosts` | 常见主机或设备。 |
| `common_countries` | 常见国家或地区。 |
| `common_auth_methods` | 常见认证方式。 |
| `common_clients` | 常见客户端。 |
| `common_resources` | 常见资源。 |

如果某个类别值第一次出现，必须能通过历史 baseline 或持久化 seen 表说明其新颖性。

## 训练样本过滤

baseline 训练数据必须区分正常样本和异常样本。

以下数据不得直接进入正常 baseline 训练集：

- 已命中高风险规则的日志。
- 带有明确攻击标签的生成样本。
- 人工或 AI 反馈标记为异常的事件。
- 攻击链中的异常步骤。
- 明显失败爆破、批量下载、异常提权等高危行为。

异常样本可以进入异常分析和质量评估流程，但不能污染正常用户画像。

## 样本置信度

baseline 必须记录 `sample_days`、`sample_count` 和 `baseline_confidence`。

置信度可以按样本量、样本天数、行为稳定性和字段完整性综合计算。

当置信度不足时，异常事件需要添加对应 reason code：

- `insufficient_history`
- `low_baseline_confidence`
- `peer_group_fallback`
- `global_baseline_fallback`

样本不足不等于没有风险。系统应使用 peer group、部门、角色或全局 baseline 作为降级参考。

## 新来源判断

新 IP、新设备、新地理位置和新来源主机判断必须基于持久化历史。

允许使用短期内存缓存提升性能，但最终证据必须来自：

- 用户历史 baseline。
- 用户日级特征。
- 持久化 seen 表。
- peer group 或全局历史。

如果只能依赖内存状态，不得把该判断作为强证据。

## 生成器画像边界

日志生成器可以包含用户常用 IP、常用时间、角色和部门等配置。

这些配置只用于生成有规律的数据，不能直接作为系统 baseline。系统必须先接收、清洗并入库日志，再从历史数据中统计 baseline。

文档、接口和页面不得把生成器配置回显为用户行为 baseline。

## baseline 输出要求

每个用户 baseline 至少应包含：

- `model_version`
- `trained_from`
- `trained_to`
- `sample_days`
- `sample_count`
- `baseline_confidence`
- 五W1H profile
- fallback 信息

baseline 必须能为异常事件提供证据，例如：

```json
{
  "feature": "login_hour",
  "expected": "09:00-19:00",
  "actual": "03:12",
  "deviation_type": "rare_login_hour",
  "confidence": 0.91
}
```

## 不允许的做法

- 直接用生成器画像作为用户 baseline。
- 找不到 baseline 时直接认定没有异常。
- 只在代码中写固定阈值，而不记录历史分布。
- 只用实时流中的瞬时计数替代历史行为画像。
- 不记录训练窗口和样本量。
