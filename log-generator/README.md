# VPN 登录日志生成器

模拟真实企业环境的 VPN 登录日志，包含 5W1H 要素和用户行为基线，可用于安全分析、SIEM 规则测试、异常检测模型训练等场景。

---

## 快速开始

项目正式运行环境使用 Docker Compose。日常开发默认由 `log-generator` service 持续追加小规模日志到 `logs/vpn_logs.log`，再由 Filebeat 采集。

```bash
docker compose up --build
```

以下命令仅作为生成器脚本的本地调试方式，不是项目正式运行要求：

```bash
# 默认：生成 7 天，每天 50 条正常登录
python gen_vpn_logs.py

# 自定义参数
python gen_vpn_logs.py --start 2026-04-01 --days 30 --count 100 --outdir ./output

# 只输出 CSV
python gen_vpn_logs.py --format csv

# 固定随机种子（可复现）
python gen_vpn_logs.py --seed 123
```

**依赖**：Python 3.10+ 标准库，无需额外安装。

---

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start` | `2026-04-01` | 起始日期，格式 `YYYY-MM-DD` |
| `--days` | `7` | 生成天数 |
| `--count` | `50` | 每天正常登录条数（工作日；周末自动降为 30%） |
| `--outdir` | `.` | 输出目录（不存在时自动创建） |
| `--format` | `all` | 输出格式：`csv` / `jsonl` / `syslog` / `all` |
| `--seed` | `42` | 随机种子 |

---

## 5W1H 字段设计

| 维度 | 字段 | 说明 |
|------|------|------|
| **Who**（谁） | `username` `dept` `role` | 用户名、部门、角色 |
| **What**（做什么） | `event_type` `result` | 事件类型：LOGIN_SUCCESS / LOGIN_FAIL；结果：SUCCESS / FAIL |
| **When**（何时） | `timestamp` | 精确到秒，格式 `YYYY-MM-DD HH:MM:SS` |
| **Where**（何地） | `src_ip` `src_country` `src_city` `vpn_gateway` `dst_internal_ip` | 来源 IP 及地理位置、接入网关、目标内网 IP |
| **Why**（原因） | `fail_reason` | 失败原因：密码错误 / OTP 验证失败 / 账号锁定 / IP 黑名单等 |
| **How**（方式） | `protocol` `auth_method` `client_software` `session_id` | VPN 协议、认证方式、客户端软件、会话 ID |

---

## 行为基线

每个模拟用户都有预设的行为基线，偏离基线的行为会被标记并计入风险评分。

### 用户基线配置

| 用户 | 部门 | 常用工作时间 | 工作日 | 常用 IP 段 |
|------|------|-------------|--------|-----------|
| zhang.wei | 研发部 | 09:00–18:00 | 周一至周五 | 北京 |
| li.fang | 财务部 | 08:00–17:00 | 周一至周五 | 杭州/广州 |
| wang.jian | 运维部 | 全天 | 全周 | 上海 |
| chen.xiao | 销售部 | 08:00–20:00 | 周一至周六 | 上海 |
| admin | IT部 | 08:00–20:00 | 全周 | 内网 |

### 风险评分规则

| 异常行为 | 加分 | 标签 |
|----------|------|------|
| 非工作时间登录 | +20 | `非工作时间登录` |
| 异常 IP 地址（非常用网段） | +25 | `异常IP地址` |
| 境外 IP 登录 | +30 | `境外登录(国家)` |
| 登录失败 | +15 | `登录失败` |
| 单次下载超过 500MB | +20 | `大量数据下载` |
| 会话时长不足 30 秒 | +10 | `会话时长异常短` |

`risk_score` 范围 0–100，`risk_tags` 为逗号分隔的触发标签，无异常时显示 `正常`。

---

## 输出格式

### CSV（`vpn_logs.csv`）

标准表格，包含全部 23 个字段，适合导入 Excel、Pandas、数据库。

### JSONL（`vpn_logs.jsonl`）

每行一个 JSON 对象，适合流式处理和后续写入 Kafka / ClickHouse 链路。

```json
{"timestamp": "2026-04-01 09:40:16", "username": "wang.jian", "dept": "运维部", "role": "ops", "src_ip": "101.89.15.190", "src_country": "中国", "src_city": "上海", "vpn_gateway": "vpn-gw-bj01", "dst_internal_ip": "10.2.140.10", "event_type": "LOGIN_SUCCESS", "protocol": "IPSec", "auth_method": "password+OTP", "client_software": "GlobalProtect 6.1", "session_id": "639174A3-EB41-4B", "result": "SUCCESS", "fail_reason": null, "session_duration_sec": 4265, "bytes_sent": 6098105, "bytes_recv": 190737046, "is_off_hours": false, "is_unusual_ip": false, "risk_score": 0, "risk_tags": "正常"}
```

### Syslog（`vpn_logs.log`）

模拟真实 VPN 设备 syslog 输出，适合 SIEM 规则调试。

```
2026-04-01 09:40:16 vpn-gw-bj01 vpnd: event=LOGIN_SUCCESS user=wang.jian dept=运维部 src_ip=101.89.15.190 src_geo=中国/上海 proto=IPSec auth=password+OTP client="GlobalProtect 6.1" session=639174A3-EB41-4B result=SUCCESS duration=4265s bytes_recv=190737046 bytes_sent=6098105 risk_score=0 risk_tags="正常"
```

---

## 典型异常场景

脚本会按比例自动注入以下异常事件：

- **境外 IP 登录失败**：来自荷兰、美国、俄罗斯等地的登录尝试
- **非工作时间登录**：凌晨 0–3 点或 22–23 点的登录行为
- **大量数据下载**：单次会话下载 600MB–2GB

---

## 文件结构

```
gen_vpn_logs.py   # 主脚本
README.md         # 本文档
vpn_output/       # 默认输出目录（运行后生成）
  vpn_logs.csv
  vpn_logs.jsonl
  vpn_logs.log
```
