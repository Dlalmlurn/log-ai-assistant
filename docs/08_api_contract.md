# API 契约

正式前端通过 FastAPI 访问系统能力。

前端不得直连 ClickHouse、Kafka、Flink、本地日志文件或 AI 服务。

## 通用规则

- API 基础路径为 `/api/v1`。
- 响应使用 JSON。
- 分页接口支持 `limit` 和 `offset`。
- 时间过滤使用 ISO 8601 字符串。
- 错误响应包含 `code`, `message`, `details`。
- API 契约表达业务能力，不暴露底层表结构作为外部依赖。
- 每个接口必须能追溯到 `REQ-*`。

## 通用响应

### 列表响应

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

### 错误响应

```json
{
  "code": "invalid_time_range",
  "message": "start_time must be earlier than end_time",
  "details": {}
}
```

## Endpoints

| Method | Path | 对应需求 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | REQ-001, REQ-002, REQ-007 | 查询系统状态。 |
| GET | `/api/v1/logs` | REQ-002, REQ-006 | 查询结构化日志。 |
| GET | `/api/v1/logs/{event_id}` | REQ-002, REQ-006 | 查询单条日志详情。 |
| POST | `/api/v1/logs/aggregate` | REQ-002, REQ-006 | 聚合查询日志。 |
| GET | `/api/v1/anomalies` | REQ-004, REQ-006, REQ-008 | 查询异常事件。 |
| GET | `/api/v1/anomalies/{event_id}` | REQ-004, REQ-006 | 查询异常详情和证据链。 |
| GET | `/api/v1/baselines/users` | REQ-003, REQ-006 | 查询用户 baseline 列表。 |
| GET | `/api/v1/baselines/users/{user_id}` | REQ-003, REQ-006 | 查询单个用户画像。 |
| POST | `/api/v1/baselines/rebuild` | REQ-003 | 触发 baseline 重建任务。 |
| POST | `/api/v1/ai/judge/{event_id}` | REQ-004 | 对异常事件执行 AI 研判。 |
| GET | `/api/v1/ai/judgements` | REQ-004, REQ-006 | 查询 AI 研判结果。 |
| POST | `/api/v1/feedback` | REQ-004 | 写入 AI 或人工反馈。 |
| GET | `/api/v1/reports/daily` | REQ-005, REQ-006 | 查询每日安全态势简报。 |
| POST | `/api/v1/reports/daily` | REQ-005 | 生成指定日期日报。 |
| GET | `/api/v1/stats/overview` | REQ-006 | 查询工作台概览。 |
| GET | `/api/v1/stats/users/risk` | REQ-003, REQ-006 | 查询用户风险排行。 |

## 查询结构化日志

### `GET /api/v1/logs`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | string | 可选，租户或项目环境。 |
| `source_type` | string | 可选，日志来源类型。 |
| `log_type` | string | 可选，日志细分类型。 |
| `user_id` | string | 可选，用户或账号。 |
| `src_ip` | string | 可选，来源 IP。 |
| `action` | string | 可选，行为。 |
| `result` | string | 可选，结果。 |
| `start_time` | datetime | 可选，开始时间。 |
| `end_time` | datetime | 可选，结束时间。 |
| `limit` | integer | 默认 50。 |
| `offset` | integer | 默认 0。 |

响应：

```json
{
  "items": [
    {
      "event_id": "evt-001",
      "event_time": "2026-05-19T03:12:00Z",
      "source_type": "vpn",
      "user_id": "alice",
      "src_ip": "203.0.113.10",
      "action": "login",
      "result": "success",
      "message": "VPN login success"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

## 聚合查询

### `POST /api/v1/logs/aggregate`

请求：

```json
{
  "time_range": {
    "from": "2026-05-18T00:00:00Z",
    "to": "2026-05-19T00:00:00Z"
  },
  "filters": {
    "tenant_id": "tenant-a",
    "source_type": "vpn"
  },
  "group_by": ["user_id", "result"],
  "metrics": ["count"]
}
```

响应：

```json
{
  "items": [
    {
      "user_id": "alice",
      "result": "fail",
      "count": 18
    }
  ]
}
```

## 查询异常事件

### `GET /api/v1/anomalies`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `risk_level` | string | 可选，`low`, `medium`, `high`, `critical`。 |
| `user_id` | string | 可选。 |
| `src_ip` | string | 可选。 |
| `reason_code` | string | 可选。 |
| `status` | string | 可选。 |
| `start_time` | datetime | 可选。 |
| `end_time` | datetime | 可选。 |
| `limit` | integer | 默认 50。 |
| `offset` | integer | 默认 0。 |

### `GET /api/v1/anomalies/{event_id}`

响应：

```json
{
  "anomaly": {},
  "baseline": {},
  "related_logs": [],
  "ai_judgement": {},
  "evidence_chain": {
    "rule_hits": [],
    "baseline_deviations": [],
    "reason_codes": [],
    "risk_components": {},
    "ai_status": "pending"
  }
}
```

## 用户 baseline

### `GET /api/v1/baselines/users/{user_id}`

数据契约中的 `UserBaseline` 以 `who_profile`, `time_profile`, `location_profile`, `access_profile`, `volume_profile`, `result_profile`, `why_profile` 保存。API 展示层会把这些 profile 映射为五W1H 视图，即 `who`, `when`, `where`, `what`, `why`, `how`。其中 `what` 可以综合 `access_profile`, `volume_profile`, `result_profile`，`how` 主要来自 `access_profile`。

响应：

```json
{
  "user_id": "alice",
  "baseline_date": "2026-05-19",
  "model_version": "baseline-v1",
  "sample_days": 30,
  "who": {},
  "when": {},
  "where": {},
  "what": {},
  "why": {},
  "how": {}
}
```

## AI 研判

### `POST /api/v1/ai/judge/{event_id}`

后端必须读取异常事件、baseline、相关日志和窗口统计作为证据包。

响应：

```json
{
  "judgement_id": "ai-001",
  "event_id": "anom-001",
  "risk_level": "critical",
  "attack_type": "account_takeover",
  "judgement": "疑似账号接管后的敏感资源访问。",
  "key_reasons": [],
  "recommended_actions": [],
  "confidence": 0.86
}
```

## 系统状态

### `GET /api/v1/health`

响应：

```json
{
  "kafka": true,
  "flink": true,
  "clickhouse": true,
  "ai_configured": true,
  "latest_log_ingest_time": "2026-05-19T10:00:00Z",
  "latest_baseline_date": "2026-05-18",
  "daily_raw_log_size_bytes": 1073741824,
  "clickhouse_inserted_rows_today": 1500000
}
```

## 前端页面映射

| 页面 | 必须调用的 API |
| --- | --- |
| 实时日志 | `GET /api/v1/logs` |
| 异常事件 | `GET /api/v1/anomalies`, `GET /api/v1/anomalies/{event_id}` |
| 用户画像 | `GET /api/v1/baselines/users`, `GET /api/v1/baselines/users/{user_id}` |
| AI 研判 | `GET /api/v1/ai/judgements`, `POST /api/v1/ai/judge/{event_id}` |
| 安全态势简报 | `GET /api/v1/reports/daily`, `POST /api/v1/reports/daily` |
| 系统状态 | `GET /api/v1/health` |
