# D 部分学习计划 — AI 研判与可视化

> 组员 D 负责项目最后一环：从 Elasticsearch 查询异常日志 → LangChain + 通义千问智能研判 → Streamlit 可视化看板 + 每日简报

---

## 学习顺序总览

| 顺序 | 模块 | 内容 | 预计学时 | 建议天数 |
| ---- | ---- | ---- | ------- | ------- |
| 1 | 二 | 通义千问 API | 4h | 1 天 |
| 2 | 一 | ES 查询基础 | 8h | 1-2 天 |
| 3 | 三 | Prompt Engineering | 8h | 1-2 天 |
| 4 | 四 | LangChain 框架 | 11h | 2-3 天 |
| 5 | 五 | Streamlit 可视化 | 13.5h | 2-3 天 |
| 6 | 六 | 每日简报生成 | 5.5h | 1 天 |
| | | **合计** | **50h** | **8-12 天** |

> 先通千问 API（最快出成果，建立信心）→ ES 查询（拿到数据）→ Prompt + LangChain（核心能力）→ Streamlit 搭界面串起来

---

## 上游数据 Schema（C 部分写入 ES 的数据结构）

D 部分所有工作都基于这个数据结构，先熟悉：

```json
{
  "timestamp": "2026-04-01 09:40:16",
  "username": "wang.jian",
  "dept": "运维部",
  "role": "ops",
  "src_ip": "101.89.15.190",
  "src_country": "中国",
  "src_city": "上海",
  "vpn_gateway": "vpn-gw-bj01",
  "dst_internal_ip": "10.2.140.10",
  "event_type": "LOGIN_SUCCESS",
  "protocol": "IPSec",
  "auth_method": "password+OTP",
  "client_software": "GlobalProtect 6.1",
  "session_id": "639174A3-EB41-4B",
  "result": "SUCCESS",
  "fail_reason": null,
  "session_duration_sec": 4265,
  "bytes_sent": 6098105,
  "bytes_recv": 190737046,
  "is_off_hours": false,
  "is_unusual_ip": false,
  "risk_score": 0,
  "risk_tags": "正常"
}
```

关键字段用途：
- `risk_score` (0-100)：排序、筛选、阈值判断
- `risk_tags`：异常分类标签，喂给 LLM 做上下文
- `timestamp`：时间聚合、热力图
- `username` + `dept`：用户维度统计
- `bytes_recv/sent`：检测异常数据传输量

---

## 模块一：Elasticsearch 查询基础（8h）

> D 不负责 ES 运维，只需要会**读数据**。掌握 4 种查询模式即可。

### 1.1 ES Python 客户端连接（1h）

- **目标**：用 `elasticsearch` 库连接本地 ES，执行一次查询
- **验收**：运行脚本返回集群健康状态
- **资源**：https://www.elastic.co/guide/en/elasticsearch/client/python-api/8.13/connecting.html

```python
from elasticsearch import Elasticsearch
es = Elasticsearch("http://localhost:9200")
print(es.info())
```

### 1.2 match / range 查询（2h）

- **目标**：按用户名搜索日志、按时间范围过滤
- **验收**：查出 "admin 最近 24 小时的所有日志"
- **资源**：https://www.elastic.co/guide/en/elasticsearch/reference/8.13/query-dsl-match-query.html

```python
# 按用户名查
es.search(index="vpn-logs", query={"match": {"username": "admin"}})

# 按时间范围查
es.search(index="vpn-logs", query={"range": {"timestamp": {"gte": "now-24h"}}})
```

### 1.3 bool 组合查询（2h）

- **目标**：多条件 AND/OR 查询（must + filter + should）
- **验收**：查出 "risk_score >= 50 且 src_country != 中国" 的日志
- **资源**：https://www.elastic.co/guide/en/elasticsearch/reference/8.13/query-dsl-bool-query.html

```python
es.search(index="vpn-logs", query={
    "bool": {
        "must": [{"range": {"risk_score": {"gte": 50}}}],
        "must_not": [{"match": {"src_country": "中国"}}]
    }
})
```

### 1.4 aggs 聚合统计（3h）

- **目标**：terms 分桶 + date_histogram 时间聚合
- **验收**：统计出 "每个用户的异常次数 TOP 10" 和 "按小时的异常分布"
- **资源**：https://www.elastic.co/guide/en/elasticsearch/reference/8.13/search-aggregations.html

```python
# 用户异常次数 TOP 10
es.search(index="vpn-logs", size=0, query={"range": {"risk_score": {"gte": 50}}},
    aggs={"by_user": {"terms": {"field": "username.keyword", "size": 10}}})

# 按小时分布
es.search(index="vpn-logs", size=0,
    aggs={"by_hour": {"date_histogram": {"field": "timestamp", "calendar_interval": "hour"}}})
```

---

## 模块二：通义千问 API 调用（4h）

> 最先学这个，半天就能跑通，建立信心。

### 2.1 注册并获取 API Key（0.5h）

- **目标**：在阿里云开通 DashScope，拿到 DASHSCOPE_API_KEY
- **验收**：环境变量配好 `export DASHSCOPE_API_KEY="sk-xxx"`
- **资源**：https://dashscope.console.aliyun.com/
- 推荐模型：`qwen-plus`（性价比最优，够用）

### 2.2 dashscope SDK 基本调用（1h）

- **目标**：用 SDK 发一条消息并收到回复
- **验收**：成功打印模型返回
- **资源**：https://help.aliyun.com/zh/dashscope/developer-reference/use-qwen-by-api

```python
import dashscope
from dashscope import Generation

response = Generation.call(
    model="qwen-plus",
    messages=[{"role": "user", "content": "你好，请介绍一下自己"}]
)
print(response.output.text)
```

### 2.3 system / user / assistant 三角色（1h）

- **目标**：搞清楚 system prompt 设定角色、user 提问、assistant 回答的结构
- **验收**：写一个 system prompt 让模型扮演安全分析师，分析一条异常日志

```python
messages = [
    {"role": "system", "content": "你是一名企业网络安全分析师，擅长分析VPN日志异常。"},
    {"role": "user",   "content": "用户admin在凌晨03:15从荷兰IP登录，下载了1.5GB数据，该用户平时只在9-18点从北京登录。请分析风险。"}
]
```

### 2.4 控制输出格式 — JSON mode（1.5h）

- **目标**：让模型返回结构化 JSON 而非自由文本
- **验收**：返回包含 `threat_type / risk_level / reason / suggestion` 四个字段的 JSON

```python
messages = [
    {"role": "system", "content": "你是安全分析师。请严格按以下JSON格式返回：\n{\"threat_type\": \"...\", \"risk_level\": \"低/中/高/紧急\", \"reason\": \"...\", \"suggestion\": \"...\"}"},
    {"role": "user",   "content": "...异常日志描述..."}
]
response = Generation.call(model="qwen-plus", messages=messages, result_format="message")
```

---

## 模块三：Prompt Engineering — 安全场景（8h）

### 3.1 Prompt 四段式结构（2h）

- **目标**：掌握 "角色设定 → 背景信息 → 任务指令 → 输出格式" 的标准写法
- **验收**：写出一个完整的安全分析 Prompt 模板
- **资源**：https://help.aliyun.com/zh/dashscope/use-cases/prompt-best-practice

```
[角色] 你是一名资深企业网络安全分析师，专注于UEBA用户行为分析。

[背景] 以下是从VPN日志系统检测到的异常事件：
{anomaly_context}

该用户的正常行为基线：
{user_baseline}

[任务] 请分析该事件：
1. 判断属于哪种攻击类型
2. 给出风险等级（低/中/高/紧急）
3. 说明判断依据
4. 给出处置建议

[格式] 请严格按JSON格式输出：
{"threat_type": "...", "risk_level": "...", "reason": "...", "suggestion": "..."}
```

### 3.2 上下文注入（2h）

- **目标**：把异常日志 + 用户行为基线拼接进 Prompt
- **验收**：Prompt 包含类似 "该用户平时 9-18 点活跃，常用 IP 段为北京，本次凌晨 3 点从荷兰登录" 的对比

要点：
- 日志原始字段 → 翻译成自然语言描述
- 基线数据 → 作为参照系
- 偏离程度 → 让 LLM 有判断依据

### 3.3 攻击类型知识（3h）

- **目标**：了解导师提到的攻击场景
- **验收**：能为每种攻击写出对应的日志特征

| 攻击类型 | 日志特征 |
| -------- | ------- |
| 暴力破解 | 短时间多次登录失败，不同密码/相同账号 |
| 账号接管 | 异地 IP 登录成功，偏离常用地点 |
| 内部数据窃取 | 登录后大量下载（bytes_recv 异常高） |
| 横向移动 | 访问多个不同 dst_internal_ip |
| 凭证填充 | 多个账号从同一 IP 短时间登录失败 |

- **资源**：MITRE ATT&CK 框架 https://attack.mitre.org/

### 3.4 风险等级定义（1h）

- **目标**：设计四级风险分级标准
- **验收**：输出一份分级表

| 等级 | risk_score | 特征 | 建议动作 |
| ---- | ---------- | ---- | ------- |
| 低 | 0-25 | 轻微偏离基线 | 记录，无需处理 |
| 中 | 26-50 | 明显偏离基线 | 通知安全团队关注 |
| 高 | 51-75 | 多项异常叠加 | 立即调查，限制账号 |
| 紧急 | 76-100 | 疑似攻击进行中 | 立即锁定账号，启动应急响应 |

---

## 模块四：LangChain 框架（11h）

### 4.1 LCEL 核心概念（2h）

- **目标**：理解 LangChain 0.2.x 的管道语法 `prompt | llm | parser`
- **验收**：能口述数据流全过程
- **资源**：https://python.langchain.com/docs/concepts/

```
输入 dict → PromptTemplate 填充变量 → LLM 生成文本 → OutputParser 解析成对象
```

### 4.2 PromptTemplate（2h）

- **目标**：用 `ChatPromptTemplate` 创建可复用的模板
- **验收**：创建接受 `{anomaly_context}` 和 `{user_baseline}` 两个变量的模板
- **资源**：https://python.langchain.com/docs/concepts/prompt_templates/

```python
from langchain.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是企业安全分析师，专注UEBA分析。"),
    ("human", "异常事件：\n{anomaly_context}\n\n用户基线：\n{user_baseline}\n\n请分析风险。")
])
```

### 4.3 接入通义千问（1.5h）

- **目标**：用 `langchain-community` 的 `ChatTongyi` 类调用千问
- **验收**：通过 LangChain 调千问并获得返回
- **资源**：https://python.langchain.com/docs/integrations/llms/tongyi/

```python
from langchain_community.chat_models import ChatTongyi

llm = ChatTongyi(model="qwen-plus", dashscope_api_key="sk-xxx")
response = llm.invoke("你好")
```

### 4.4 PydanticOutputParser（2h）

- **目标**：用 Pydantic 定义输出 schema，自动解析 LLM 返回的 JSON
- **验收**：定义 `ThreatAnalysis` 模型，链式调用后直接拿到 Python 对象
- **资源**：https://python.langchain.com/docs/concepts/output_parsers/

```python
from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser

class ThreatAnalysis(BaseModel):
    threat_type: str = Field(description="攻击类型")
    risk_level: str = Field(description="风险等级：低/中/高/紧急")
    reason: str = Field(description="判断依据")
    suggestion: str = Field(description="处置建议")

parser = PydanticOutputParser(pydantic_object=ThreatAnalysis)
```

### 4.5 完整链构建（2h）

- **目标**：将 4.2 + 4.3 + 4.4 串成完整分析链
- **验收**：输入异常日志 dict → 输出 ThreatAnalysis 对象

```python
chain = prompt | llm | parser

result = chain.invoke({
    "anomaly_context": "用户admin在03:15从荷兰IP 185.220.101.45登录，下载1.5GB...",
    "user_baseline": "该用户平时9-18点活跃，常用IP段为北京221.130.45.x..."
})

print(result.threat_type)   # "账号接管"
print(result.risk_level)    # "紧急"
```

### 4.6 错误处理与重试（1.5h）

- **目标**：处理 JSON 解析失败、API 超时、rate limit
- **验收**：加入 retry 机制，解析失败自动重试

```python
from langchain.schema import OutputParserException
import time

def safe_analyze(chain, inputs, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            return chain.invoke(inputs)
        except OutputParserException:
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise
```

---

## 模块五：Streamlit 可视化（13.5h）

### 5.1 基础入门（1h）

- **目标**：理解 Streamlit 运行模型（每次交互重新执行整个脚本）
- **验收**：`streamlit run app.py` 启动 Hello World
- **资源**：https://docs.streamlit.io/get-started

```python
import streamlit as st
st.title("日志分析 AI 助手")
st.write("Hello World")
```

### 5.2 多页面应用（1.5h）

- **目标**：用 pages/ 目录构建多页面应用
- **验收**：创建 4 个页面的侧边栏导航
- **资源**：https://docs.streamlit.io/develop/concepts/multipage-apps

```
dashboard/
├── app.py                      # 主入口
└── pages/
    ├── 1_实时日志.py
    ├── 2_异常排行.py
    ├── 3_AI分析.py
    └── 4_每日简报.py
```

### 5.3 数据展示组件（2h）

- **目标**：掌握 `st.dataframe` / `st.metric` / `st.table` / `st.json`
- **验收**：展示日志表格 + 指标卡片（今日异常数 / 高危用户数 / 平均风险分）

```python
col1, col2, col3 = st.columns(3)
col1.metric("今日异常事件", "23", "+5")
col2.metric("高危用户", "3")
col3.metric("平均风险分", "42.5", "-3.2")

st.dataframe(df, use_container_width=True)
```

### 5.4 图表绘制（3h）

- **目标**：掌握内置图表 + Plotly 集成
- **验收**：画出 "用户异常 TOP 10 柱状图" + "24h 风险趋势折线图"

```python
import plotly.express as px

# 柱状图
fig = px.bar(df_top10, x="count", y="username", orientation="h", title="异常次数 TOP 10")
st.plotly_chart(fig)

# 折线图
fig2 = px.line(df_hourly, x="hour", y="risk_count", title="24小时风险趋势")
st.plotly_chart(fig2)
```

### 5.5 交互组件（2h）

- **目标**：掌握选择器 / 输入框 / 按钮 / spinner
- **验收**：完成交互流程 — 选用户 → 选日期 → 点分析 → 等待 → 展示结果

```python
user = st.selectbox("选择用户", ["admin", "zhang.wei", "li.fang"])
date_range = st.date_input("日期范围", [])
if st.button("开始分析"):
    with st.spinner("AI 正在分析中..."):
        result = chain.invoke(...)
    st.success("分析完成")
    with st.expander("查看详细分析"):
        st.json(result.dict())
```

### 5.6 状态管理与缓存（2h）

- **目标**：理解 `st.session_state` 和 `st.cache_data(ttl=)`
- **验收**：ES 查询缓存 60 秒，页面切换不丢数据
- **资源**：https://docs.streamlit.io/develop/concepts/architecture/session-state

```python
@st.cache_data(ttl=60)
def query_es_logs(index, query):
    return es.search(index=index, query=query)

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
```

### 5.7 自动刷新（1h）

- **目标**：实时日志面板定时刷新
- **验收**：每 10 秒自动拉取最新日志

```python
# 方法一：streamlit-autorefresh
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=10000, key="log_refresh")

# 方法二：内置 fragment
@st.fragment(run_every="10s")
def live_logs():
    logs = query_latest_logs()
    st.dataframe(logs)
```

### 5.8 导出功能（1h）

- **目标**：用 `st.download_button` 导出简报
- **验收**：点击下载，浏览器得到文件

```python
report_text = generate_report(date)
st.download_button(
    label="下载简报",
    data=report_text,
    file_name=f"安全简报_{date}.txt",
    mime="text/plain"
)
```

---

## 模块六：每日安全简报生成（5.5h）

### 6.1 简报数据聚合（2h）

- **目标**：从 ES 聚合一天的统计 — 总日志数、异常数、TOP 用户、攻击类型分布
- **验收**：输出一个 dict 包含所有统计项

```python
def aggregate_daily_stats(date: str) -> dict:
    return {
        "date": date,
        "total_logs": 350,
        "anomaly_count": 23,
        "high_risk_users": [{"username": "admin", "score": 85}, ...],
        "attack_distribution": {"暴力破解": 8, "账号接管": 3, ...},
        "overall_score": 72
    }
```

### 6.2 简报 Prompt 设计（2h）

- **目标**：让 LLM 根据统计数据生成自然语言简报
- **验收**：输出包含 "概述 → 高危事件 → 排行 → 评分 → 建议" 的完整简报

```
[角色] 你是安全运营中心(SOC)的日报撰写员。

[数据] 以下是{date}的安全统计：
{daily_stats_json}

[任务] 请生成一份《每日安全态势简报》，包含：
1. 今日概述（一段话总结）
2. 高危事件TOP 3（详细描述）
3. 用户风险排行
4. 整体安全评分（0-100）
5. 明日关注建议
```

### 6.3 简报自动化（1.5h）

- **目标**：定时触发生成
- **验收**：每天自动生成并存储

```python
import schedule

def daily_job():
    today = datetime.now().strftime("%Y-%m-%d")
    stats = aggregate_daily_stats(today)
    report = report_chain.invoke({"date": today, "daily_stats_json": json.dumps(stats)})
    save_report(today, report)

schedule.every().day.at("23:30").do(daily_job)
```

---

## 学习资源汇总

| 技术 | 官方文档 |
| ---- | ------- |
| Elasticsearch 8.13 | https://www.elastic.co/guide/en/elasticsearch/reference/8.13/ |
| ES Python 客户端 | https://www.elastic.co/guide/en/elasticsearch/client/python-api/8.13/ |
| 通义千问 API | https://help.aliyun.com/zh/dashscope/ |
| LangChain 0.2 | https://python.langchain.com/docs/ |
| Streamlit | https://docs.streamlit.io/ |
| MITRE ATT&CK | https://attack.mitre.org/ |

> 导师建议：首选官方文档，其次 B 站/YouTube 教学视频 + AI，建议 AI + 官方手册交叉验证。
