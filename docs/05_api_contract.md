# API Contract

正式前端通过 FastAPI 访问系统能力。前端不得直连 Elasticsearch、Kafka 或本地日志文件。

## General Rules

- API 基础路径建议为 `/api/v1`。
- 响应统一使用 JSON。
- 分页接口统一支持 `limit` 和 `offset`，默认 `limit=50`。
- 时间过滤统一使用 ISO 8601 字符串。
- 错误响应包含 `code`, `message`, `details`。
- 所有接口必须能追溯到 `docs/00_gold_standard.md` 中的 `REQ-*`。

## Endpoints

| Method | Path | 对应需求 | 用途 | 后端数据源 |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/health` | REQ-001, REQ-002, REQ-007 | 系统健康状态。 | Kafka, Flink, Elasticsearch, DashScope config |
| GET | `/api/v1/logs` | REQ-002, REQ-006 | 查询结构化日志。 | ES `security-logs` |
| GET | `/api/v1/logs/{event_id}` | REQ-002, REQ-006 | 查询单条日志详情。 | ES `security-logs` |
| GET | `/api/v1/alerts` | REQ-004, REQ-006, REQ-008 | 查询异常事件。 | ES `security-alerts` |
| GET | `/api/v1/alerts/{alert_id}` | REQ-004, REQ-006 | 查询告警详情和相关日志。 | ES `security-alerts`, `security-logs`, `user-baselines`, `ai-reports` |
| POST | `/api/v1/alerts/{alert_id}/analyze` | REQ-004 | 对告警执行 AI 研判。 | AI analyzer, ES |
| GET | `/api/v1/baselines` | REQ-003, REQ-006 | 查询用户 baseline 列表。 | ES `user-baselines` |
| GET | `/api/v1/baselines/{username}` | REQ-003, REQ-006 | 查询单个用户画像。 | ES `user-baselines` |
| POST | `/api/v1/baselines/rebuild` | REQ-003 | 重建 baseline。 | ES `security-logs`, baseline builder |
| GET | `/api/v1/ai-reports` | REQ-004, REQ-006 | 查询 AI 研判报告。 | ES `ai-reports` |
| GET | `/api/v1/daily-reports` | REQ-005, REQ-006 | 查询日报列表。 | ES `daily-reports` |
| POST | `/api/v1/daily-reports` | REQ-005 | 生成指定日期日报。 | daily report builder, ES |
| GET | `/api/v1/stats/overview` | REQ-006 | 工作台概览指标。 | ES aggregations |
| GET | `/api/v1/stats/rules` | REQ-006, REQ-008 | 规则命中统计。 | ES `security-alerts` |
| GET | `/api/v1/stats/users/risk` | REQ-003, REQ-006 | 用户风险排行。 | ES `security-alerts`, `user-baselines` |

## Query Parameters

### `GET /api/v1/logs`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `source_type` | string | 可选，日志类型。 |
| `username` | string | 可选，用户名。 |
| `src_ip` | string | 可选，来源 IP。 |
| `status` | string | 可选，状态。 |
| `start_time` | datetime | 可选，默认最近 24 小时。 |
| `end_time` | datetime | 可选，默认当前时间。 |
| `limit` | integer | 默认 50。 |
| `offset` | integer | 默认 0。 |

### `GET /api/v1/alerts`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `risk_level` | string | 可选，`低/中/高/紧急`。 |
| `username` | string | 可选。 |
| `rule` | string | 可选，规则关键词。 |
| `status` | string | 可选，`new/analyzed/closed`。 |
| `start_time` | datetime | 可选。 |
| `end_time` | datetime | 可选。 |
| `limit` | integer | 默认 50。 |
| `offset` | integer | 默认 0。 |

## Response Shapes

### List Response

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

### Health Response

```json
{
  "kafka": true,
  "flink": true,
  "elasticsearch": true,
  "dashscope_configured": false,
  "latest_log_ingest_time": "2026-05-13T10:00:00Z",
  "consumer_lag": {
    "flink-raw-to-parsed": 0,
    "log-ai-consume-to-es": 0
  }
}
```

### Alert Detail Response

```json
{
  "alert": {},
  "baseline": {},
  "related_logs": [],
  "ai_report": {},
  "evidence_chain": {
    "rule_hits": [],
    "baseline_deviations": [],
    "risk_reason": ""
  }
}
```

### Baseline Rebuild Response

```json
{
  "rebuilt_count": 12
}
```

## Frontend Page Mapping

| 页面 | 必须调用的 API |
| --- | --- |
| 实时日志 | `GET /api/v1/logs` |
| 异常事件 | `GET /api/v1/alerts`, `GET /api/v1/alerts/{alert_id}` |
| 用户基线 | `GET /api/v1/baselines`, `GET /api/v1/baselines/{username}` |
| AI 研判 | `GET /api/v1/ai-reports`, `POST /api/v1/alerts/{alert_id}/analyze` |
| 每日简报 | `GET /api/v1/daily-reports`, `POST /api/v1/daily-reports` |
| 系统状态 | `GET /api/v1/health` |
