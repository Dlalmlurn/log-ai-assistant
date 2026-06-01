import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  Database,
  Filter,
  ListFilter,
  Pause,
  Play,
  RadioTower,
  RefreshCcw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  XCircle
} from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiRequestError, fetchAlertDetail, fetchAlerts, fetchBaseline, fetchBaselines, fetchHealth, fetchLogs, rebuildBaselines, runAccuracyTest } from "./api";
import type { AccuracyTestResult } from "./api";
import type {
  AnomalyDetailResponse,
  AnomalyEvent,
  AlertsQuery,
  EvidenceChain,
  HealthResponse,
  LogsQuery,
  NormalizedLog,
  RiskLevel,
  SourceType,
  UserBaseline
} from "./types";

type PageKey = "logs" | "alerts" | "baselines" | "status";

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  updatedAt: Date | null;
};

const initialLogsQuery: LogsQuery = {
  source_type: "",
  user_id: "",
  src_ip: "",
  result: "",
  start_time: "",
  end_time: "",
  limit: 50,
  offset: 0
};

const sourceTypes: Array<{ label: string; value: SourceType | "" }> = [
  { label: "全部来源", value: "" },
  { label: "VPN", value: "vpn" },
  { label: "OA", value: "oa" },
  { label: "API", value: "api" },
  { label: "系统", value: "system" },
  { label: "文件", value: "file" },
  { label: "数据库", value: "database" },
  { label: "安全设备", value: "security_device" }
];

const resultOptions = ["", "success", "fail", "denied", "error"];
const alertStatusOptions = ["", "new", "investigating", "closed", "false_positive"];
const riskLevelOptions: Array<{ label: string; value: RiskLevel | "" }> = [
  { label: "全部等级", value: "" },
  { label: "低", value: "low" },
  { label: "中", value: "medium" },
  { label: "高", value: "high" }
];

const initialAlertsQuery: AlertsQuery = {
  risk_level: "",
  user_id: "",
  reason_code: "",
  status: "",
  start_time: "",
  end_time: "",
  limit: 50,
  offset: 0
};

function UserBaselinesPage() {
  const [listState, setListState] = useState<LoadState<{ items: UserBaseline[]; total: number }>>({
    data: null, loading: true, error: null, updatedAt: null,
  });
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildMsg, setRebuildMsg] = useState<string | null>(null);

  const loadList = useCallback((signal?: AbortSignal) => {
    setListState((cur) => ({ ...cur, loading: true, error: null }));
    fetchBaselines({ limit: 50, offset: 0 }, signal)
      .then((res) => setListState({ data: res, loading: false, error: null, updatedAt: new Date() }))
      .catch((err) => {
        if (signal?.aborted) return;
        setListState({ data: null, loading: false, error: err instanceof ApiRequestError ? `${err.code}: ${err.message}` : String(err), updatedAt: null });
      });
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    loadList(ctrl.signal);
    return () => ctrl.abort();
  }, [loadList]);

  const handleRebuild = useCallback(async () => {
    setRebuilding(true);
    try {
      const res = await rebuildBaselines();
      setRebuildMsg(`基线刷新完成: ${res.rebuilt_count} 位用户`);
      loadList();
    } catch (err) {
      setRebuildMsg(`刷新失败: ${err instanceof ApiRequestError ? err.message : String(err)}`);
    } finally {
      setRebuilding(false);
      setTimeout(() => setRebuildMsg(null), 5000);
    }
  }, [loadList]);

  const baselineList = listState.data?.items ?? [];
  const selectedBaseline = baselineList.find((b) => b.user_id === selectedUserId) ?? null;

  return (
    <div className="workspace-inner">
      <PageHeader
        kicker="UEBA"
        heading="用户基线"
        description={`基于全部历史日志自动构建的行为画像，每个用户拥有唯一基线。${listState.data ? `共 ${listState.data.total} 位用户` : ""}`}
        action={
          <>
            <button className="btn btn-ghost" type="button" onClick={() => loadList()} disabled={listState.loading}>
              <RefreshCcw aria-hidden="true" />
              刷新列表
            </button>
            <button className="btn btn-primary" type="button" onClick={handleRebuild} disabled={rebuilding}>
              <RefreshCcw aria-hidden="true" />
              {rebuilding ? "重建中…" : "重建基线"}
            </button>
          </>
        }
      />

      {listState.error ? <ErrorBanner message={listState.error} onRetry={() => loadList()} /> : null}
      {rebuildMsg ? <div className="toast toast-success">{rebuildMsg}</div> : null}

      <div className="split-layout">
        <section className="split-list">
          {listState.loading ? (
            <TableSkeleton rows={8} />
          ) : baselineList.length === 0 ? (
            <EmptyState icon={<Database aria-hidden="true" />} title="暂无基线" description="点击「重建基线」从存储的日志中生成用户基线。" />
          ) : (
            <div className="log-table-wrap">
              <table className="log-table">
                <thead>
                  <tr>
                    <th>用户 ID</th>
                    <th>部门</th>
                    <th>角色</th>
                    <th title="采样天数">天数</th>
                    <th title="样本数量">样本数</th>
                    <th title="置信度">置信度</th>
                  </tr>
                </thead>
                <tbody>
                  {baselineList.map((b) => {
                    const dept = (b.who_profile as Record<string,any>|null)?.department?.common_values?.[0] ?? "-";
                    const role = (b.who_profile as Record<string,any>|null)?.role?.common_values?.[0] ?? "-";
                    return (
                    <tr
                      key={b.user_id}
                      className={b.user_id === selectedUserId ? "row-selected" : ""}
                      onClick={() => setSelectedUserId(b.user_id === selectedUserId ? null : b.user_id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td className="cell-code">{b.user_id}</td>
                      <td>{dept}</td>
                      <td>{role}</td>
                      <td>{b.sample_days}</td>
                      <td>{b.sample_count}</td>
                      <td><StatusPill ok={b.baseline_confidence >= 0.5} label={b.baseline_confidence.toFixed(2)} /></td>
                    </tr>
                  );})}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedBaseline ? (
          <section className="split-detail">
            <div className="detail-head">
              <strong className="cell-code">{selectedBaseline.user_id}</strong>
              <span>v={selectedBaseline.model_version}</span>
              <span>confidence={selectedBaseline.baseline_confidence.toFixed(2)}</span>
              <span>fallback={selectedBaseline.fallback_level ?? "无"}</span>
            </div>
            <div className="detail-body">
              <ProfileSection title="身份 (Who)" profile={selectedBaseline.who_profile} />
              <ProfileSection title="时间 (When)" profile={selectedBaseline.time_profile} />
              <ProfileSection title="位置 (Where)" profile={selectedBaseline.location_profile} />
              <ProfileSection title="访问 (What)" profile={selectedBaseline.access_profile} />
              <ProfileSection title="容量 (How Much)" profile={selectedBaseline.volume_profile} />
              <ProfileSection title="结果 (Result)" profile={selectedBaseline.result_profile} />
              {selectedBaseline.why_profile && Object.keys(selectedBaseline.why_profile).length > 0 ? (
                <ProfileSection title="原因 (Why)" profile={selectedBaseline.why_profile} />
              ) : null}
            </div>
          </section>
        ) : (
          <section className="split-detail">
            <EmptyState icon={<Database aria-hidden="true" />} title="选择用户" description="点击左侧用户行查看五维画像详情。" />
          </section>
        )}
      </div>
    </div>
  );
}

function ProfileSection({ title, profile }: { title: string; profile: Record<string, unknown> }) {
  const entries = Object.entries(profile ?? {});
  if (entries.length === 0) return null;
  return (
    <details open style={{ marginBottom: "0.5em" }}>
      <summary style={{ fontWeight: 600, cursor: "pointer" }}>{title} 画像</summary>
      <table className="log-table" style={{ marginTop: "0.4em" }}>
        <thead>
          <tr>
            <th>特征</th>
            <th>均值</th>
            <th>标准差</th>
            <th>P50</th>
            <th>P95</th>
            <th>P99</th>
            <th>高频值</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([name, value]) => {
            const v = value as Record<string, unknown> | undefined;
            return (
              <tr key={name}>
                <td className="cell-code">{name}</td>
                <td>{formatNum(v?.mean_value)}</td>
                <td>{formatNum(v?.std_value)}</td>
                <td>{formatNum(v?.p50_value)}</td>
                <td>{formatNum(v?.p95_value)}</td>
                <td>{formatNum(v?.p99_value)}</td>
                <td className="cell-mono">{formatCommon(v?.common_values)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </details>
  );
}

function formatNum(v: unknown): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : "-";
}

function formatCommon(v: unknown): string {
  if (Array.isArray(v)) return v.slice(0, 3).join(", ");
  return String(v ?? "-");
}

function App() {
  const [page, setPage] = useState<PageKey>("logs");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>日志分析 AI 助手</strong>
            <span>安全运营中心</span>
          </div>
        </div>

        <nav className="nav" aria-label="主导航">
          <button className={page === "logs" ? "active" : ""} type="button" onClick={() => setPage("logs")}>
            <TerminalSquare aria-hidden="true" />
            实时日志
          </button>
          <button className={page === "alerts" ? "active" : ""} type="button" onClick={() => setPage("alerts")}>
            <AlertCircle aria-hidden="true" />
            异常事件
          </button>
          <button className={page === "baselines" ? "active" : ""} type="button" onClick={() => setPage("baselines")}>
            <Database aria-hidden="true" />
            用户基线
          </button>
          <button className={page === "status" ? "active" : ""} type="button" onClick={() => setPage("status")}>
            <Activity aria-hidden="true" />
            系统状态
          </button>
        </nav>

        <div className="chain">
          <span>Filebeat</span>
          <span>Kafka</span>
          <span>Flink</span>
          <span>ClickHouse</span>
          <span>Anomaly</span>
          <span>AI-Engine</span>
          <span>FastAPI</span>
          <span>React</span>
        </div>
      </aside>

      <main className="workspace">
        {page === "logs" ? <RealtimeLogsPage /> : null}
        {page === "alerts" ? <AlertsPage /> : null}
        {page === "baselines" ? <UserBaselinesPage /> : null}
        {page === "status" ? <SystemStatusPage /> : null}
      </main>
    </div>
  );
}

function SystemStatusPage() {
  const [state, setState] = useState<LoadState<HealthResponse>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });

  const [testState, setTestState] = useState<{
    running: boolean;
    result: AccuracyTestResult | null;
    error: string | null;
  }>({ running: false, result: null, error: null });

  const load = useCallback((signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    fetchHealth(signal)
      .then((data) => {
        setState({ data, loading: false, error: null, updatedAt: new Date() });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          error: formatError(error)
        }));
      });
  }, []);

  const handleRunTest = useCallback(() => {
    setTestState({ running: true, result: null, error: null });
    runAccuracyTest()
      .then((result) => {
        setTestState({ running: false, result, error: null });
      })
      .catch((error: unknown) => {
        setTestState({ running: false, result: null, error: formatError(error) });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const interval = window.setInterval(() => load(), 15000);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [load]);

  const services = useMemo(() => {
    const health = state.data;
    return [
      {
        name: "Kafka",
        ok: health?.kafka ?? false,
        description: "raw_logs、parsed_logs 消息队列传输",
        icon: RadioTower
      },
      {
        name: "Flink",
        ok: health?.flink ?? false,
        description: "raw_logs → parsed_logs 实时流处理",
        icon: Activity
      },
      {
        name: "ClickHouse",
        ok: health?.clickhouse ?? false,
        description: "日志持久化、基线聚合与异常查询",
        icon: Database
      },
      {
        name: "异常检测",
        ok: health?.anomaly_detector_active ?? false,
        description: "RuleEngine + UEBA 双引擎实时检测",
        icon: ShieldCheck
      },
      {
        name: "AI 引擎",
        ok: (health?.deepseek_configured ?? false) || (health?.dashscope_configured ?? false),
        description: health?.deepseek_configured ? "DeepSeek 已配置" : health?.dashscope_configured ? "DashScope 已配置" : "未配置 AI API Key",
        icon: Sparkles
      }
    ];
  }, [state.data]);

  const onlineCount = services.filter((service) => service.ok).length;
  const pipelineReady = state.data
    ? state.data.kafka && state.data.flink && state.data.clickhouse && state.data.anomaly_detector_active
    : false;

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-001 / REQ-002"
        title="系统状态"
        description="FastAPI 健康状态监控，覆盖 Filebeat → React 全链路。"
        action={
          <button className="icon-button primary" type="button" onClick={() => load()} disabled={state.loading}>
            <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
            刷新
          </button>
        }
      />

      {state.error ? <ErrorBanner message={state.error} /> : null}

      <div className="status-summary">
        <div>
          <span className="eyebrow">流水线状态</span>
          <strong>{pipelineReady ? "运行正常" : "需要注意"}</strong>
          <p>{onlineCount}/{services.length} 项检查通过</p>
        </div>
        <StatusPill ok={pipelineReady} label={pipelineReady ? "数据通路可用" : "数据通路降级"} />
      </div>

      <div className="status-grid">
        {services.map((service) => (
          <ServiceCard key={service.name} {...service} loading={state.loading && !state.data} />
        ))}
      </div>

      <div className="metrics-band">
        <Metric
          icon={Clock3}
          label="最近数据"
          value={formatDateTime(state.data?.latest_log_ingest_time)}
          hint="最近一条 security_logs 写入时间"
        />
        <Metric
          icon={Sparkles}
          label="AI 模型"
          value={state.data?.deepseek_configured ? "DeepSeek" : state.data?.dashscope_configured ? "DashScope" : "未配置"}
          hint={state.data?.deepseek_configured ? "DeepSeek API 已接入" : state.data?.dashscope_configured ? "DashScope 备用" : "AI 研判已降级为 Mock"}
        />
        <Metric
          icon={ListFilter}
          label="消费者组"
          value={String(Object.keys(state.data?.consumer_lag ?? {}).length)}
          hint="已监控的 Kafka 消费者组数量"
        />
        <Metric
          icon={Server}
          label="上次刷新"
          value={state.updatedAt ? state.updatedAt.toLocaleTimeString() : "等待中"}
          hint="状态页每 15 秒自动刷新"
        />
      </div>

      <div className="section-title">
        <h2>消费者延迟</h2>
        <span>来自 /api/v1/health 的 Kafka 消费者组</span>
      </div>
      <div className="lag-table" role="table" aria-label="消费者延迟">
        <div role="row" className="lag-row lag-head">
          <span role="columnheader">消费者组</span>
          <span role="columnheader">延迟</span>
          <span role="columnheader">状态</span>
        </div>
        {Object.entries(state.data?.consumer_lag ?? {}).map(([group, lag]) => (
          <div role="row" className="lag-row" key={group}>
            <span role="cell">{group}</span>
            <span role="cell">{lag.toLocaleString()}</span>
            <span role="cell">
              <StatusPill ok={lag === 0} label={lag === 0 ? "已同步" : "积压中"} />
            </span>
          </div>
        ))}
        {state.data && Object.keys(state.data.consumer_lag).length === 0 ? (
          <EmptyState title="无消费者组数据" detail="health 接口返回了空的 consumer_lag 对象。" />
        ) : null}
      </div>

      {/* -- UEBA Accuracy Test -------------------------------------------------- */}

      <div className="section-title" style={{ marginTop: 24 }}>
        <h2>UEBA 准确度测试</h2>
        <span>生成确定性日志并评估 UEBA 基线评分准确度</span>
      </div>

      <div className="accuracy-test-area">
        <div className="accuracy-controls">
          <button
            className="icon-button primary"
            type="button"
            onClick={handleRunTest}
            disabled={testState.running}
          >
            {testState.running ? "运行中..." : "运行测试"}
          </button>
          <span className="muted">
            种子=42 · 3天 · 100条/天 · 约30秒
          </span>
        </div>

        {testState.error ? <ErrorBanner message={testState.error} /> : null}

        {testState.result ? (
          <div className="accuracy-result">
            <div className="accuracy-metrics">
              <div className="accuracy-metric">
                <span className="accuracy-metric-label">Precision</span>
                <strong>{(testState.result.precision * 100).toFixed(1)}%</strong>
              </div>
              <div className="accuracy-metric">
                <span className="accuracy-metric-label">Recall</span>
                <strong>{(testState.result.recall * 100).toFixed(1)}%</strong>
              </div>
              <div className="accuracy-metric">
                <span className="accuracy-metric-label">F1</span>
                <strong>{(testState.result.f1 * 100).toFixed(1)}%</strong>
              </div>
              <div className="accuracy-metric">
                <span className="accuracy-metric-label">TP / FP / FN / TN</span>
                <strong>{testState.result.tp} / {testState.result.fp} / {testState.result.fn} / {testState.result.tn}</strong>
              </div>
            </div>
            <div className="accuracy-meta">
              <span>生成 {testState.result.logs_generated} 条日志</span>
              <span>发送 {testState.result.logs_sent} 条</span>
              <span>检测 {testState.result.anomalies_found} 条异常</span>
              {testState.result.warnings.map((w) => <span key={w} className="warning-tag">{w}</span>)}
            </div>

            {Object.keys(testState.result.by_dimension).length > 0 ? (
              <div className="dimension-table" role="table">
                <div className="dimension-row dimension-head">
                  <span>维度</span>
                  <span>Precision</span>
                  <span>Recall</span>
                  <span>F1</span>
                  <span>TP</span>
                  <span>FP</span>
                  <span>FN</span>
                </div>
                {Object.entries(testState.result.by_dimension).map(([dim, m]) => (
                  <div className="dimension-row" key={dim}>
                    <span>{dim}</span>
                    <span>{(m.precision * 100).toFixed(0)}%</span>
                    <span>{(m.recall * 100).toFixed(0)}%</span>
                    <span>{(m.f1 * 100).toFixed(0)}%</span>
                    <span>{m.tp}</span>
                    <span>{m.fp}</span>
                    <span>{m.fn}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function RealtimeLogsPage() {
  const [query, setQuery] = useState<LogsQuery>(initialLogsQuery);
  const [draft, setDraft] = useState<LogsQuery>(initialLogsQuery);
  const [live, setLive] = useState(true);
  const [state, setState] = useState<LoadState<{ items: NormalizedLog[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });

  const load = useCallback((activeQuery: LogsQuery, signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    fetchLogs(activeQuery, signal)
      .then((data) => {
        setState({
          data: { items: data.items, total: data.total },
          loading: false,
          error: null,
          updatedAt: new Date()
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          error: formatError(error)
        }));
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(query, controller.signal);

    return () => controller.abort();
  }, [load, query]);

  useEffect(() => {
    if (!live) {
      return;
    }

    const interval = window.setInterval(() => {
      load(query);
    }, 10000);

    return () => window.clearInterval(interval);
  }, [live, load, query]);

  const applyFilters = () => {
    setQuery({ ...draft, offset: 0 });
  };

  const clearFilters = () => {
    setDraft(initialLogsQuery);
    setQuery(initialLogsQuery);
  };

  const canGoPrevious = query.offset > 0;
  const canGoNext = Boolean(state.data && query.offset + query.limit < state.data.total);

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-002 / REQ-006"
        title="实时日志"
        description="通过 FastAPI 查询 ClickHouse 中的结构化安全日志。"
        action={
          <div className="header-actions">
            <button className="icon-button" type="button" onClick={() => setLive((value) => !value)}>
              {live ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {live ? "暂停自动刷新" : "恢复自动刷新"}
            </button>
            <button className="icon-button primary" type="button" onClick={() => load(query)} disabled={state.loading}>
              <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
              刷新
            </button>
          </div>
        }
      />

      {state.error ? <ErrorBanner message={state.error} /> : null}

      <form
        className="filters"
        onSubmit={(event) => {
          event.preventDefault();
          applyFilters();
        }}
      >
        <label>
          <span>来源</span>
          <select
            value={draft.source_type}
            onChange={(event) => setDraft((current) => ({ ...current, source_type: event.target.value as SourceType | "" }))}
          >
            {sourceTypes.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>用户 ID</span>
          <input
            value={draft.user_id}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, user_id: event.target.value }))}
          />
        </label>

        <label>
          <span>来源 IP</span>
          <input
            value={draft.src_ip}
            placeholder="10.0.1.20"
            onChange={(event) => setDraft((current) => ({ ...current, src_ip: event.target.value }))}
          />
        </label>

        <label>
          <span>结果</span>
          <select value={draft.result} onChange={(event) => setDraft((current) => ({ ...current, result: event.target.value as LogsQuery["result"] }))}>
            {resultOptions.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "全部结果"}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>开始时间</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.start_time)}
            onChange={(event) => setDraft((current) => ({ ...current, start_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>结束时间</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.end_time)}
            onChange={(event) => setDraft((current) => ({ ...current, end_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>条数</span>
          <select
            value={draft.limit}
            onChange={(event) => setDraft((current) => ({ ...current, limit: Number(event.target.value) }))}
          >
            {[25, 50, 100, 200].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <div className="filter-actions">
          <button className="icon-button primary" type="submit">
            <Search aria-hidden="true" />
            查询
          </button>
          <button className="icon-button" type="button" onClick={clearFilters}>
            <Filter aria-hidden="true" />
            清空
          </button>
        </div>
      </form>

      <div className="table-toolbar">
        <div>
          <strong>{state.data?.total.toLocaleString() ?? "0"} 条日志</strong>
          <span>{formatResultRange(query.offset, query.limit, state.data?.total ?? 0, state.data?.items.length ?? 0)} 来自 /api/v1/logs</span>
        </div>
        <div className="toolbar-meta">
          <StatusPill ok={live} label={live ? "自动刷新中" : "已暂停"} />
          <span>{state.updatedAt ? `更新于 ${state.updatedAt.toLocaleTimeString()}` : "等待数据"}</span>
        </div>
      </div>

      <div className="log-table-wrap">
        <table className="log-table">
          <thead>
            <tr>
              <th>事件时间</th>
              <th>来源</th>
              <th>用户</th>
              <th>来源 IP</th>
              <th>操作</th>
              <th>结果</th>
              <th>消息</th>
              <th>风险标签</th>
            </tr>
          </thead>
          <tbody>
            {state.data?.items.map((log) => (
              <tr key={log.event_id}>
                <td>
                  <time dateTime={log.event_time}>{formatDateTime(log.event_time)}</time>
                  <small>{log.event_id}</small>
                </td>
                <td>{formatSource(log.source_type)}</td>
                <td>{log.user_id || "未知"}</td>
                <td>{log.src_ip || "无"}</td>
                <td>{log.action}</td>
                <td>
                  <span className={`status-chip ${statusTone(log.result)}`}>{log.result}</span>
                </td>
                <td className="message-cell">{log.message}</td>
                <td>
                  <div className="tag-list">
                    {log.risk_tags.length > 0 ? log.risk_tags.map((tag) => <span key={tag}>{tag}</span>) : <span className="muted">无</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {state.loading && !state.data ? <TableSkeleton /> : null}
        {!state.loading && state.data?.items.length === 0 ? (
          <EmptyState title="无匹配日志" detail="请调整筛选条件，或确认 Filebeat → Flink → ClickHouse 数据链路是否正常。" />
        ) : null}
      </div>

      <div className="pagination">
        <button
          className="icon-button"
          type="button"
          disabled={!canGoPrevious}
          onClick={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
        >
          上一页
        </button>
        <span>偏移 {query.offset.toLocaleString()}</span>
        <button
          className="icon-button"
          type="button"
          disabled={!canGoNext}
          onClick={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
        >
          下一页
        </button>
      </div>
    </section>
  );
}

function AlertsPage() {
  const [query, setQuery] = useState<AlertsQuery>(initialAlertsQuery);
  const [draft, setDraft] = useState<AlertsQuery>(initialAlertsQuery);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [listState, setListState] = useState<LoadState<{ items: AnomalyEvent[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [detailState, setDetailState] = useState<LoadState<AnomalyDetailResponse>>({
    data: null,
    loading: false,
    error: null,
    updatedAt: null
  });

  const loadAlerts = useCallback((activeQuery: AlertsQuery, signal?: AbortSignal) => {
    setListState((current) => ({ ...current, loading: true, error: null }));
    fetchAlerts(activeQuery, signal)
      .then((data) => {
        setListState({
          data: { items: data.items, total: data.total },
          loading: false,
          error: null,
          updatedAt: new Date()
        });
        setSelectedAlertId((current) => {
          if (current && data.items.some((alert) => alert.event_id === current)) {
            return current;
          }
          return data.items[0]?.event_id ?? null;
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setListState((current) => ({
          ...current,
          loading: false,
          error: formatError(error)
        }));
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadAlerts(query, controller.signal);

    return () => controller.abort();
  }, [loadAlerts, query]);

  useEffect(() => {
    if (!selectedAlertId) {
      setDetailState({ data: null, loading: false, error: null, updatedAt: null });
      return;
    }

    const controller = new AbortController();
    setDetailState((current) => ({ ...current, loading: true, error: null }));
    fetchAlertDetail(selectedAlertId, controller.signal)
      .then((data) => {
        setDetailState({ data, loading: false, error: null, updatedAt: new Date() });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setDetailState((current) => ({
          ...current,
          loading: false,
          error: formatError(error)
        }));
      });

    return () => controller.abort();
  }, [selectedAlertId]);

  const applyFilters = () => {
    setQuery({ ...draft, offset: 0 });
  };

  const clearFilters = () => {
    setDraft(initialAlertsQuery);
    setQuery(initialAlertsQuery);
  };

  const canGoPrevious = query.offset > 0;
  const canGoNext = Boolean(listState.data && query.offset + query.limit < listState.data.total);

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-004 / REQ-006 / REQ-008"
        title="异常事件"
        description="通过 FastAPI 查询 ClickHouse 中的异常检测结果。"
        action={
          <button className="icon-button primary" type="button" onClick={() => loadAlerts(query)} disabled={listState.loading}>
            <RefreshCcw aria-hidden="true" className={listState.loading ? "spin" : ""} />
            刷新
          </button>
        }
      />

      {listState.error ? <ErrorBanner message={listState.error} /> : null}

      <form
        className="filters alerts-filters"
        onSubmit={(event) => {
          event.preventDefault();
          applyFilters();
        }}
      >
        <label>
          <span>风险等级</span>
          <select
            value={draft.risk_level}
            onChange={(event) => setDraft((current) => ({ ...current, risk_level: event.target.value as RiskLevel | "" }))}
          >
            {riskLevelOptions.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>用户 ID</span>
          <input
            value={draft.user_id}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, user_id: event.target.value }))}
          />
        </label>

        <label>
          <span>原因码</span>
          <input
            value={draft.reason_code}
            placeholder="new_source_ip"
            onChange={(event) => setDraft((current) => ({ ...current, reason_code: event.target.value }))}
          />
        </label>

        <label>
          <span>状态</span>
          <select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>
            {alertStatusOptions.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "全部状态"}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>开始时间</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.start_time)}
            onChange={(event) => setDraft((current) => ({ ...current, start_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>结束时间</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.end_time)}
            onChange={(event) => setDraft((current) => ({ ...current, end_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>条数</span>
          <select
            value={draft.limit}
            onChange={(event) => setDraft((current) => ({ ...current, limit: Number(event.target.value) }))}
          >
            {[25, 50, 100].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <div className="filter-actions">
          <button className="icon-button primary" type="submit">
            <Search aria-hidden="true" />
            查询
          </button>
          <button className="icon-button" type="button" onClick={clearFilters}>
            <Filter aria-hidden="true" />
            清空
          </button>
        </div>
      </form>

      <div className="alerts-layout">
        <section className="alerts-list-panel" aria-label="Alert list">
          <div className="table-toolbar">
            <div>
              <strong>{listState.data?.total.toLocaleString() ?? "0"} 条异常</strong>
              <span>{formatResultRange(query.offset, query.limit, listState.data?.total ?? 0, listState.data?.items.length ?? 0)} 来自 /api/v1/anomalies</span>
            </div>
            <div className="toolbar-meta">
              <span>{listState.updatedAt ? `更新于 ${listState.updatedAt.toLocaleTimeString()}` : "等待数据"}</span>
            </div>
          </div>

          <div className="log-table-wrap alerts-table-wrap">
            <table className="log-table alerts-table">
              <thead>
                <tr>
                  <th>检测时间</th>
                  <th>风险等级</th>
                  <th>用户</th>
                  <th>来源 IP</th>
                  <th>命中规则</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {listState.data?.items.map((alert) => (
                  <tr
                    key={alert.event_id}
                    className={selectedAlertId === alert.event_id ? "selected-row" : ""}
                    tabIndex={0}
                    onClick={() => setSelectedAlertId(alert.event_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedAlertId(alert.event_id);
                      }
                    }}
                  >
                    <td>
                      <time dateTime={alert.detect_time}>{formatDateTime(alert.detect_time)}</time>
                      <small>{alert.event_id}</small>
                    </td>
                    <td>
                      <span className={`risk-chip ${riskTone(alert.risk_level)}`}>{alert.risk_level}</span>
                      <small>score {alert.risk_score}</small>
                    </td>
                    <td>{alert.user_id || "未知"}</td>
                    <td>{alert.src_ip || "无"}</td>
                    <td>
                      <div className="tag-list">
                        {alert.rule_hits.length > 0 ? alert.rule_hits.map((rule) => <span key={rule}>{rule}</span>) : <span className="muted">无</span>}
                      </div>
                    </td>
                    <td>
                      <span className={`status-chip ${alertStatusTone(alert.status)}`}>{alert.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {listState.loading && !listState.data ? <TableSkeleton /> : null}
            {!listState.loading && listState.data?.items.length === 0 ? (
              <EmptyState title="无匹配异常" detail="请调整筛选条件，或确认检测流水线是否已写入异常事件。" />
            ) : null}
          </div>

          <div className="pagination">
            <button
              className="icon-button"
              type="button"
              disabled={!canGoPrevious}
              onClick={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
            >
              上一页
            </button>
            <span>偏移 {query.offset.toLocaleString()}</span>
            <button
              className="icon-button"
              type="button"
              disabled={!canGoNext}
              onClick={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
            >
              下一页
            </button>
          </div>
        </section>

        <AlertDetailPanel state={detailState} selectedAlertId={selectedAlertId} />
      </div>
    </section>
  );
}

function AlertDetailPanel({
  state,
  selectedAlertId
}: {
  state: LoadState<AnomalyDetailResponse>;
  selectedAlertId: string | null;
}) {
  const detail = state.data;

  if (!selectedAlertId) {
    return (
      <aside className="detail-panel">
        <EmptyState title="选择一条异常事件" detail="选中后将显示关键信息、证据链、行为画像和 AI 研判结果。" />
      </aside>
    );
  }

  return (
    <aside className="detail-panel">
      <div className="detail-panel-header">
        <div>
          <span className="eyebrow">异常详情</span>
          <h2>{detail?.anomaly.event_id ?? selectedAlertId}</h2>
        </div>
        {detail ? <StatusPill ok={detail.anomaly.ai_status === "analyzed"} label={aiStatusLabel(detail.anomaly.ai_status)} /> : null}
      </div>

      {state.error ? <ErrorBanner message={state.error} /> : null}
      {state.loading && !detail ? <TableSkeleton /> : null}

      {detail ? (
        <div className="detail-stack">
          <SummaryCard anomaly={detail.anomaly} aiJudgement={detail.ai_judgement} />

          <RuleHitsSection ruleHits={detail.evidence_chain.rule_hits} />

          <EvidenceChainSection evidence={detail.evidence_chain} />

          <BaselineSection baseline={detail.baseline} />

          <AIJudgementSection judgement={detail.ai_judgement} />

          <RelatedLogsSection logs={detail.related_logs} />
        </div>
      ) : null}
    </aside>
  );
}

/* ── 关键信息摘要卡 ── */

function SummaryCard({ anomaly, aiJudgement }: { anomaly: AnomalyEvent; aiJudgement: Record<string, unknown> }) {
  const attackType = typeof aiJudgement["attack_type"] === "string" ? aiJudgement["attack_type"] : null;

  return (
    <section className="detail-section summary-card">
      <div className="detail-section-title">
        <h3>关键信息</h3>
      </div>
      <div className="summary-grid">
        <div className="summary-item">
          <span className="summary-label">用户</span>
          <span>{anomaly.user_id || "未知"}</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">来源 IP</span>
          <span>{anomaly.src_ip || "无"}</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">主机</span>
          <span>{anomaly.host || "未知"}</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">操作</span>
          <span>{anomaly.action || "未知"}</span>
        </div>
        {attackType ? (
          <div className="summary-item">
            <span className="summary-label">攻击类型</span>
            <span className="attack-type-tag">{attackType}</span>
          </div>
        ) : null}
        <div className="summary-item">
          <span className="summary-label">风险评分</span>
          <span>{anomaly.risk_score}</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">风险等级</span>
          <span className={`risk-chip ${riskTone(anomaly.risk_level)}`}>{anomaly.risk_level}</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">检测时间</span>
          <span>{formatDateTime(anomaly.detect_time)}</span>
        </div>
        {anomaly.object_type ? (
          <div className="summary-item">
            <span className="summary-label">目标类型</span>
            <span>{anomaly.object_type}</span>
          </div>
        ) : null}
        {anomaly.object_id ? (
          <div className="summary-item">
            <span className="summary-label">目标 ID</span>
            <span>{anomaly.object_id}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

/* ── 命中规则 ── */

function RuleHitsSection({ ruleHits }: { ruleHits: string[] }) {
  return (
    <section className="detail-section">
      <div className="detail-section-title">
        <h3>命中规则</h3>
        <span>{ruleHits.length} 条</span>
      </div>
      {ruleHits.length > 0 ? (
        <div className="tag-list">
          {ruleHits.map((rule) => <span key={rule}>{rule}</span>)}
        </div>
      ) : (
        <p className="muted">无规则命中（由 UEBA 基线偏差触发）。</p>
      )}
    </section>
  );
}

/* ── 证据链 ── */

function EvidenceChainSection({ evidence }: { evidence: EvidenceChain }) {
  return (
    <section className="detail-section">
      <div className="detail-section-title">
        <h3>证据链</h3>
        <span>{evidence.reason_codes.length} 个原因码</span>
      </div>
      <p className="risk-reason">{evidence.risk_reason || "无综合风险原因。"}</p>

      {evidence.baseline_deviations.length > 0 ? (
        <>
          <h4 className="subsection-title">基线偏离项</h4>
          <ul className="evidence-list">
            {evidence.baseline_deviations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {evidence.reason_codes.length > 0 ? (
        <>
          <h4 className="subsection-title">触发原因码</h4>
          <div className="tag-list">
            {evidence.reason_codes.map((rc) => <span key={rc}>{rc}</span>)}
          </div>
        </>
      ) : null}
    </section>
  );
}

/* ── 行为画像（用户基线） ── */

const BAR_COLORS = ["#4f8eff", "#36b3a6", "#ffa941", "#e0685c", "#8b6fce", "#5dbe6e"];

type StatsField = {
  mean_value?: number | null;
  std_value?: number | null;
  p50_value?: number | null;
  p95_value?: number | null;
  p99_value?: number | null;
  common_values?: string[];
  value_histogram?: Record<string, number>;
};

function unwrapField(raw: unknown): { scalar: number | null; list: string[]; hist: Record<string, number> | null } {
  if (!raw || typeof raw !== "object") return { scalar: null, list: [], hist: null };
  const f = raw as Record<string, unknown>;
  const scalar = typeof f.mean_value === "number" ? f.mean_value : null;
  const list: string[] = Array.isArray(f.common_values) ? (f.common_values as string[]) : [];
  const vh = f.value_histogram as Record<string, number> | undefined;
  let hist: Record<string, number> | null = null;
  if (vh && typeof vh === "object") {
    const keys = Object.keys(vh);
    const isStatOnly = keys.length > 0 && keys.every((k) => ["mean", "std", "p50", "p95", "p99"].includes(k));
    if (!isStatOnly && keys.length > 0) hist = vh;
  }
  return { scalar, list, hist };
}

function fieldList(raw: unknown): string[] {
  return unwrapField(raw).list;
}

function fieldScalar(raw: unknown): number | null {
  return unwrapField(raw).scalar;
}

function fieldHist(raw: unknown): Record<string, number> | null {
  return unwrapField(raw).hist;
}

function BaselineSection({ baseline }: { baseline: Record<string, unknown> }) {
  if (!baseline || Object.keys(baseline).length === 0) {
    return (
      <section className="detail-section">
        <div className="detail-section-title"><h3>行为画像</h3><span>缺失</span></div>
        <p className="muted">暂无该用户的基线数据。</p>
      </section>
    );
  }

  const who = (baseline.who_profile ?? {}) as Record<string, unknown>;
  const time = (baseline.time_profile ?? {}) as Record<string, unknown>;
  const location = (baseline.location_profile ?? {}) as Record<string, unknown>;
  const access = (baseline.access_profile ?? {}) as Record<string, unknown>;
  const result = (baseline.result_profile ?? {}) as Record<string, unknown>;
  const fallback = baseline.fallback_level as string | undefined;

  // extract unwrapped values
  const dept = fieldList(who.department)[0] ?? "";
  const role = fieldList(who.user_role)[0] ?? "";
  const acctType = fieldList(who.account_type)[0] ?? "";
  const hasIdentity = dept || role || acctType;

  const hourHist = fieldHist(time.hour_histogram);
  const chartData = hourHist
    ? Object.entries(hourHist)
        .sort((a, b) => Number(a[0]) - Number(b[0]))
        .map(([hour, count]) => ({ hour: `${hour}时`, count }))
    : [];

  const commonIps = fieldList(location.common_ips);
  const commonActions = fieldList(access.common_actions);
  const avgApiCalls = fieldScalar(access.avg_api_calls_per_minute);

  const successRate = fieldScalar(result.login_success_rate);
  const successCount = fieldScalar(result.success_login_count_7d);
  const failedCount = fieldScalar(result.failed_login_count_7d);
  const hasLoginStats = successRate != null || successCount != null || failedCount != null;

  const hasAccess = commonActions.length > 0 || avgApiCalls != null;

  return (
    <section className="detail-section">
      <div className="detail-section-title">
        <h3>行为画像</h3>
        <span>
          {baseline.baseline_confidence != null ? `置信度 ${Math.round(Number(baseline.baseline_confidence) * 100)}%` : ""}
          {fallback && fallback !== "none" ? ` · 降级 ${fallback}` : ""}
        </span>
      </div>

      {/* 用户身份 */}
      {hasIdentity ? (
        <div className="baseline-row">
          <span className="baseline-label">身份</span>
          <span>{[dept, role, acctType].filter(Boolean).join(" · ")}</span>
        </div>
      ) : null}

      {/* 活跃时段柱状图 */}
      {chartData.length > 0 ? (
        <div className="baseline-chart">
          <h4 className="subsection-title">活跃时段分布</h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} interval={2} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {chartData.map((_, idx) => (
                  <Cell key={idx} fill={BAR_COLORS[idx % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      {/* 常用 IP */}
      {commonIps.length > 0 ? (
        <div className="baseline-row">
          <span className="baseline-label">常用 IP</span>
          <div className="tag-list">
            {commonIps.map((ip) => <span key={ip}>{ip}</span>)}
          </div>
        </div>
      ) : null}

      {/* 访问特征 */}
      {hasAccess ? (
        <div className="baseline-row">
          <span className="baseline-label">访问特征</span>
          <span className="baseline-text">
            {commonActions.length > 0 ? `操作: ${commonActions.slice(0, 5).join(", ")}` : ""}
            {avgApiCalls != null ? ` · 平均 ${avgApiCalls.toFixed(1)} 次/分钟` : ""}
          </span>
        </div>
      ) : null}

      {/* 登录结果 */}
      {hasLoginStats ? (
        <div className="baseline-row">
          <span className="baseline-label">登录数据</span>
          <span className="baseline-text">
            {successRate != null ? `成功率 ${Math.round(successRate * 100)}%` : ""}
            {successCount != null ? ` · 成功 ${Math.round(successCount)} 次` : ""}
            {failedCount != null ? ` · 失败 ${Math.round(failedCount)} 次` : ""}
          </span>
        </div>
      ) : null}

      {/* 样本信息 */}
      {(baseline.sample_days != null || baseline.sample_count != null) ? (
        <div className="baseline-row">
          <span className="baseline-label">样本</span>
          <span className="baseline-text">
            {baseline.sample_days != null ? `${baseline.sample_days} 天` : ""}
            {baseline.sample_count != null ? ` · ${baseline.sample_count} 条日志` : ""}
          </span>
        </div>
      ) : null}
    </section>
  );
}

/* ── AI 研判 ── */

function AIJudgementSection({ judgement }: { judgement: Record<string, unknown> }) {
  if (!judgement || Object.keys(judgement).length === 0) {
    return (
      <section className="detail-section">
        <div className="detail-section-title"><h3>AI 研判</h3><span>未生成</span></div>
        <p className="muted">该异常尚未进行 AI 研判。</p>
      </section>
    );
  }

  const attackType = judgement.attack_type as string ?? "未知";
  const riskLevel = judgement.risk_level as string ?? "unknown";
  const keyReasons = judgement.key_reasons as string[] ?? [];
  const recommendedActions = judgement.recommended_actions as string[] ?? [];
  const confidence = Number(judgement.confidence ?? 0);
  const modelName = judgement.model_name as string ?? "unknown";
  const isMock = Boolean(judgement.is_mock);
  const judgementText = judgement.judgement as string ?? "";

  return (
    <section className="detail-section ai-judgement-section">
      <div className="detail-section-title">
        <h3>AI 研判</h3>
        <span className={isMock ? "mock-badge" : "live-badge"}>
          {isMock ? "mock" : modelName}
        </span>
      </div>

      <div className="ai-judgement-body">
        <div className="ai-judgement-header">
          <span className="tag-pill attack">{attackType}</span>
          <span className={`risk-chip ${riskTone(riskLevel as RiskLevel)}`}>{riskLevel}</span>
          <span className="confidence-badge">置信度 {(confidence * 100).toFixed(0)}%</span>
        </div>

        <div className="confidence-bar-container">
          <div
            className="confidence-bar-fill"
            style={{ width: `${Math.round(confidence * 100)}%` }}
          />
        </div>

        <p className="judgement-text">{judgementText || "无详细研判结论。"}</p>

        {keyReasons.length > 0 ? (
          <>
            <h4 className="subsection-title">关键原因</h4>
            <ul className="action-list">
              {keyReasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </>
        ) : null}

        {recommendedActions.length > 0 ? (
          <>
            <h4 className="subsection-title">建议措施</h4>
            <ul className="action-list">
              {recommendedActions.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </>
        ) : null}
      </div>
    </section>
  );
}

/* ── 关联日志 ── */

function RelatedLogsSection({ logs }: { logs: NormalizedLog[] }) {
  return (
    <section className="detail-section">
      <div className="detail-section-title">
        <h3>关联日志</h3>
        <span>{logs.length} 条</span>
      </div>
      {logs.length > 0 ? (
        <div className="related-log-list">
          {logs.map((log) => (
            <article key={log.event_id} className="related-log-item">
              <div className="related-log-header">
                <span>{log.action || "未知操作"}</span>
                <span className={`result-badge ${log.result === "success" ? "ok" : log.result === "fail" ? "fail" : "other"}`}>{log.result}</span>
              </div>
              <div className="related-log-meta">
                <span>{formatDateTime(log.event_time)}</span>
                {log.src_ip ? <span>IP: {log.src_ip}</span> : null}
                {log.user_id ? <span>用户: {log.user_id}</span> : null}
              </div>
              <p className="related-log-msg">{log.message || "无消息"}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted">无关联日志。</p>
      )}
    </section>
  );
}

function PageHeader({
  kicker,
  title,
  description,
  action
}: {
  kicker: string;
  title: string;
  description: string;
  action: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{kicker}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}

function ServiceCard({
  name,
  ok,
  description,
  icon: Icon,
  loading
}: {
  name: string;
  ok: boolean;
  description: string;
  icon: typeof Activity;
  loading: boolean;
}) {
  return (
    <article className="service-card">
      <div className="service-icon">
        <Icon aria-hidden="true" />
      </div>
      <div>
        <div className="service-title">
          <h2>{name}</h2>
          <StatusPill ok={ok} label={loading ? "检测中" : ok ? "正常" : "异常"} />
        </div>
        <p>{description}</p>
      </div>
    </article>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  hint
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="metric">
      <Icon aria-hidden="true" />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{hint}</small>
      </div>
    </div>
  );
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`pill ${ok ? "ok" : "bad"}`}>
      {ok ? <CheckCircle2 aria-hidden="true" /> : <XCircle aria-hidden="true" />}
      {label}
    </span>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="error-banner" role="alert">
      <AlertCircle aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="table-skeleton" aria-hidden="true">
      {Array.from({ length: 7 }).map((_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

function formatError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return `${error.message} (${error.code})`;
  }
  if (error instanceof Error) {
    if (error instanceof TypeError && error.message.toLowerCase().includes("fetch")) {
      return "FastAPI request failed. Confirm the backend is running on 127.0.0.1:8000 and the Vite /api proxy is active.";
    }
    return error.message;
  }
  return "Request failed";
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "无";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function formatSource(value: SourceType): string {
  const labels: Record<string, string> = {
    vpn: "VPN",
    oa: "OA",
    api: "API",
    system: "系统",
    file: "文件",
    database: "数据库",
    security_device: "安全设备",
  };
  return labels[value] ?? value;
}

function statusTone(status: string): string {
  const normalized = status.toLowerCase();
  if (["success", "ok", "allow", "allowed"].includes(normalized)) {
    return "good";
  }
  if (["failed", "fail", "denied", "blocked", "error"].includes(normalized)) {
    return "danger";
  }
  return "neutral";
}

function aiStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    not_required: "无需AI",
    pending: "待分析",
    analyzed: "已分析",
    failed: "分析失败",
  };
  return labels[status] ?? status;
}

function alertStatusTone(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "analyzed" || normalized === "closed") {
    return "good";
  }
  if (normalized === "new") {
    return "danger";
  }
  return "neutral";
}

function riskTone(riskLevel: RiskLevel): string {
  if (riskLevel === "high") {
    return "high";
  }
  if (riskLevel === "medium") {
    return "medium";
  }
  return "low";
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function isEmptyRecord(value: Record<string, unknown>): boolean {
  return Object.keys(value).length === 0;
}

function formatResultRange(offset: number, limit: number, total: number, itemCount: number): string {
  if (itemCount === 0 || total === 0) {
    return "0-0 条";
  }
  return `${offset + 1}-${Math.min(offset + limit, total)} 条`;
}

function toApiDateTime(value: string): string {
  return value ? new Date(value).toISOString() : "";
}

function toDatetimeLocalInput(value?: string): string {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export default App;
