import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
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
  UserRound,
  XCircle
} from "lucide-react";

import {
  analyzeAlert,
  ApiRequestError,
  createDailyReport,
  createFeedback,
  fetchAIReports,
  fetchAlertDetail,
  fetchAlerts,
  fetchBaselines,
  fetchDailyReports,
  fetchHealth,
  fetchLogs,
  fetchStatsOverview,
  fetchUserRiskStats
} from "./api";
import type {
  AIJudgement,
  AnomalyDetailResponse,
  AnomalyEvent,
  AlertsQuery,
  DailyReport,
  HealthResponse,
  LogsQuery,
  NormalizedLog,
  StatsOverview,
  UserBaseline,
  UserRiskStats,
  RiskLevel,
  SourceType
} from "./types";

type PageKey = "logs" | "anomalies" | "users" | "ai" | "reports" | "status";

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
  { label: "All sources", value: "" },
  { label: "VPN", value: "vpn" },
  { label: "OA", value: "oa" },
  { label: "API", value: "api" },
  { label: "System", value: "system" },
  { label: "File", value: "file" },
  { label: "Database", value: "database" },
  { label: "Security device", value: "security_device" }
];

const resultOptions = ["", "success", "fail", "denied", "error"];
const alertStatusOptions = ["", "new", "investigating", "closed", "false_positive"];
const riskLevelOptions: Array<{ label: string; value: RiskLevel | "" }> = [
  { label: "All risk levels", value: "" },
  { label: "Low", value: "low" },
  { label: "Medium", value: "medium" },
  { label: "High", value: "high" },
  { label: "Critical", value: "critical" }
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

function App() {
  const [page, setPage] = useState<PageKey>("logs");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>Log AI Assistant</strong>
            <span>Security operations</span>
          </div>
        </div>

        <nav className="nav" aria-label="Main navigation">
          <button className={page === "logs" ? "active" : ""} type="button" onClick={() => setPage("logs")}>
            <TerminalSquare aria-hidden="true" />
            Realtime Logs
          </button>
          <button className={page === "anomalies" ? "active" : ""} type="button" onClick={() => setPage("anomalies")}>
            <AlertCircle aria-hidden="true" />
            Anomalies
          </button>
          <button className={page === "users" ? "active" : ""} type="button" onClick={() => setPage("users")}>
            <UserRound aria-hidden="true" />
            User Profiles
          </button>
          <button className={page === "ai" ? "active" : ""} type="button" onClick={() => setPage("ai")}>
            <Brain aria-hidden="true" />
            AI Judgement
          </button>
          <button className={page === "reports" ? "active" : ""} type="button" onClick={() => setPage("reports")}>
            <FileText aria-hidden="true" />
            Daily Reports
          </button>
          <button className={page === "status" ? "active" : ""} type="button" onClick={() => setPage("status")}>
            <Activity aria-hidden="true" />
            System Status
          </button>
        </nav>

        <div className="chain">
          <span>Filebeat</span>
          <span>Kafka</span>
          <span>Flink</span>
          <span>ClickHouse</span>
          <span>FastAPI</span>
          <span>React</span>
        </div>
      </aside>

      <main className="workspace">
        {page === "logs" ? <RealtimeLogsPage /> : null}
        {page === "anomalies" ? <AlertsPage /> : null}
        {page === "users" ? <UserProfilesPage /> : null}
        {page === "ai" ? <AIJudgementPage /> : null}
        {page === "reports" ? <DailyReportsPage /> : null}
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
  const [statsState, setStatsState] = useState<LoadState<StatsOverview>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [riskState, setRiskState] = useState<LoadState<{ items: UserRiskStats[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });

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

  const loadStats = useCallback((signal?: AbortSignal) => {
    setStatsState((current) => ({ ...current, loading: true, error: null }));
    setRiskState((current) => ({ ...current, loading: true, error: null }));
    fetchStatsOverview({}, signal)
      .then((data) => setStatsState({ data, loading: false, error: null, updatedAt: new Date() }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setStatsState((current) => ({ ...current, loading: false, error: formatError(error) }));
      });
    fetchUserRiskStats({ limit: 5, offset: 0 }, signal)
      .then((data) => setRiskState({ data: { items: data.items, total: data.total }, loading: false, error: null, updatedAt: new Date() }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setRiskState((current) => ({ ...current, loading: false, error: formatError(error) }));
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    loadStats(controller.signal);
    const interval = window.setInterval(() => {
      load();
      loadStats();
    }, 15000);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [load, loadStats]);

  const services = useMemo(() => {
    const health = state.data;
    return [
      {
        name: "Kafka",
        ok: health?.kafka ?? false,
        description: "raw_logs, parsed_logs and anomaly transport",
        icon: RadioTower
      },
      {
        name: "Flink",
        ok: health?.flink ?? false,
        description: "raw_logs to normalized parsed_logs processing",
        icon: Activity
      },
      {
        name: "ClickHouse",
        ok: health?.clickhouse ?? false,
        description: "security_logs persistence and analytics",
        icon: Database
      },
      {
        name: "DashScope",
        ok: health?.dashscope_configured ?? false,
        description: "AI analysis configuration",
        icon: Sparkles
      }
    ];
  }, [state.data]);

  const onlineCount = services.filter((service) => service.ok).length;
  const pipelineReady = state.data ? state.data.kafka && state.data.flink && state.data.clickhouse : false;

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-001 / REQ-002"
        title="System Status"
        description="Live FastAPI health for the formal Filebeat to React pipeline."
        action={
          <button className="icon-button primary" type="button" onClick={() => load()} disabled={state.loading}>
            <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
            Refresh
          </button>
        }
      />

      {state.error ? <ErrorBanner message={state.error} /> : null}

      <div className="status-summary">
        <div>
          <span className="eyebrow">Pipeline readiness</span>
          <strong>{pipelineReady ? "Operational" : "Attention needed"}</strong>
          <p>{onlineCount} of {services.length} checks are currently passing.</p>
        </div>
        <StatusPill ok={pipelineReady} label={pipelineReady ? "Data path available" : "Data path degraded"} />
      </div>

      <div className="status-grid">
        {services.map((service) => (
          <ServiceCard key={service.name} {...service} loading={state.loading && !state.data} />
        ))}
      </div>

      <div className="metrics-band">
        <Metric
          icon={Clock3}
          label="Latest ingest"
          value={formatDateTime(state.data?.latest_log_ingest_time)}
          hint="Most recent security_logs ingest_time"
        />
        <Metric
          icon={BarChart3}
          label="Anomalies"
          value={formatNumber(statsState.data?.anomaly_count)}
          hint={`${formatNumber(statsState.data?.high_risk_count)} high or critical`}
        />
        <Metric
          icon={Server}
          label="Log volume"
          value={formatNumber(statsState.data?.log_count)}
          hint={`Latest ${formatDateTime(statsState.data?.latest_log_ingest_time)}`}
        />
      </div>

      <div className="metrics-band">
        <Metric
          icon={Brain}
          label="AI pending"
          value={formatNumber(statsState.data?.ai_pending_count)}
          hint="Anomalies awaiting AI judgement"
        />
        <Metric
          icon={UserRound}
          label="Baseline coverage"
          value={formatNumber(statsState.data?.baseline_user_count)}
          hint="Users with a stored behavior baseline"
        />
        <Metric
          icon={FileText}
          label="Latest daily report"
          value={statsState.data?.latest_report_date ?? "none"}
          hint="Most recent daily_security_reports date"
        />
      </div>

      {statsState.error ? <ErrorBanner message={statsState.error} /> : null}

      <div className="section-title">
        <h2>User Risk Ranking</h2>
        <span>Top users from /api/v1/stats/users/risk</span>
      </div>
      <div className="compact-list">
        {riskState.data?.items.map((item) => (
          <article key={item.user_id} className="compact-row">
            <div>
              <strong>{item.user_id}</strong>
              <span>{formatDateTime(item.latest_event_time)}</span>
            </div>
            <div className="tag-list">
              <span>{item.anomaly_count} anomalies</span>
              <span>{item.high_risk_count} high+</span>
              <span>max {item.max_risk_score}</span>
            </div>
          </article>
        ))}
        {!riskState.loading && riskState.data?.items.length === 0 ? <EmptyState title="No ranked users" detail="User risk ranking is empty until anomaly events include user_id." /> : null}
        {riskState.error ? <ErrorBanner message={riskState.error} /> : null}
      </div>

      <div className="section-title">
        <h2>Consumer Lag</h2>
        <span>Kafka groups from /api/v1/health</span>
      </div>
      <div className="lag-table" role="table" aria-label="Consumer lag">
        <div role="row" className="lag-row lag-head">
          <span role="columnheader">Group</span>
          <span role="columnheader">Lag</span>
          <span role="columnheader">State</span>
        </div>
        {Object.entries(state.data?.consumer_lag ?? {}).map(([group, lag]) => (
          <div role="row" className="lag-row" key={group}>
            <span role="cell">{group}</span>
            <span role="cell">{lag.toLocaleString()}</span>
            <span role="cell">
              <StatusPill ok={lag === 0} label={lag === 0 ? "Caught up" : "Backlog"} />
            </span>
          </div>
        ))}
        {state.data && Object.keys(state.data.consumer_lag).length === 0 ? (
          <EmptyState title="No lag groups reported" detail="The health endpoint returned an empty consumer_lag object." />
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
        title="Realtime Logs"
        description="Structured events queried through FastAPI from the ClickHouse-backed runtime path."
        action={
          <div className="header-actions">
            <button className="icon-button" type="button" onClick={() => setLive((value) => !value)}>
              {live ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {live ? "Pause live" : "Resume live"}
            </button>
            <button className="icon-button primary" type="button" onClick={() => load(query)} disabled={state.loading}>
              <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
              Refresh
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
          <span>Source</span>
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
          <span>User ID</span>
          <input
            value={draft.user_id}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, user_id: event.target.value }))}
          />
        </label>

        <label>
          <span>Source IP</span>
          <input
            value={draft.src_ip}
            placeholder="10.0.1.20"
            onChange={(event) => setDraft((current) => ({ ...current, src_ip: event.target.value }))}
          />
        </label>

        <label>
          <span>Result</span>
          <select value={draft.result} onChange={(event) => setDraft((current) => ({ ...current, result: event.target.value as LogsQuery["result"] }))}>
            {resultOptions.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "All results"}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Start time</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.start_time)}
            onChange={(event) => setDraft((current) => ({ ...current, start_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>End time</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.end_time)}
            onChange={(event) => setDraft((current) => ({ ...current, end_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>Limit</span>
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
            Apply
          </button>
          <button className="icon-button" type="button" onClick={clearFilters}>
            <Filter aria-hidden="true" />
            Clear
          </button>
        </div>
      </form>

      <div className="table-toolbar">
        <div>
          <strong>{state.data?.total.toLocaleString() ?? "0"} events</strong>
          <span>{formatResultRange(query.offset, query.limit, state.data?.total ?? 0, state.data?.items.length ?? 0)} from /api/v1/logs</span>
        </div>
        <div className="toolbar-meta">
          <StatusPill ok={live} label={live ? "Live polling" : "Paused"} />
          <span>{state.updatedAt ? `Updated ${state.updatedAt.toLocaleTimeString()}` : "Waiting for data"}</span>
        </div>
      </div>

      <div className="log-table-wrap">
        <table className="log-table">
          <thead>
            <tr>
              <th>Event time</th>
              <th>Source</th>
              <th>User</th>
              <th>Source IP</th>
              <th>Action</th>
              <th>Result</th>
              <th>Message</th>
              <th>Risk tags</th>
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
                <td>{log.user_id || "unknown"}</td>
                <td>{log.src_ip || "n/a"}</td>
                <td>{log.action}</td>
                <td>
                  <span className={`status-chip ${statusTone(log.result)}`}>{log.result}</span>
                </td>
                <td className="message-cell">{log.message}</td>
                <td>
                  <div className="tag-list">
                    {log.risk_tags.length > 0 ? log.risk_tags.map((tag) => <span key={tag}>{tag}</span>) : <span className="muted">none</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {state.loading && !state.data ? <TableSkeleton /> : null}
        {!state.loading && state.data?.items.length === 0 ? (
          <EmptyState title="No logs matched" detail="Adjust filters or confirm that Filebeat, Flink, and ClickHouse are moving current data." />
        ) : null}
      </div>

      <div className="pagination">
        <button
          className="icon-button"
          type="button"
          disabled={!canGoPrevious}
          onClick={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
        >
          Previous
        </button>
        <span>Offset {query.offset.toLocaleString()}</span>
        <button
          className="icon-button"
          type="button"
          disabled={!canGoNext}
          onClick={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
        >
          Next
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

  const loadDetail = useCallback((alertId: string, signal?: AbortSignal) => {
    setDetailState((current) => ({ ...current, loading: true, error: null }));
    fetchAlertDetail(alertId, signal)
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
  }, []);

  useEffect(() => {
    if (!selectedAlertId) {
      setDetailState({ data: null, loading: false, error: null, updatedAt: null });
      return;
    }

    const controller = new AbortController();
    loadDetail(selectedAlertId, controller.signal);
    return () => controller.abort();
  }, [loadDetail, selectedAlertId]);

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
        title="Anomalies"
        description="Abnormal events queried through FastAPI from the formal ClickHouse target path."
        action={
          <button className="icon-button primary" type="button" onClick={() => loadAlerts(query)} disabled={listState.loading}>
            <RefreshCcw aria-hidden="true" className={listState.loading ? "spin" : ""} />
            Refresh
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
          <span>Risk</span>
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
          <span>User ID</span>
          <input
            value={draft.user_id}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, user_id: event.target.value }))}
          />
        </label>

        <label>
          <span>Reason code</span>
          <input
            value={draft.reason_code}
            placeholder="new_source_ip"
            onChange={(event) => setDraft((current) => ({ ...current, reason_code: event.target.value }))}
          />
        </label>

        <label>
          <span>Status</span>
          <select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>
            {alertStatusOptions.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "All statuses"}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Start time</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.start_time)}
            onChange={(event) => setDraft((current) => ({ ...current, start_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>End time</span>
          <input
            type="datetime-local"
            value={toDatetimeLocalInput(draft.end_time)}
            onChange={(event) => setDraft((current) => ({ ...current, end_time: toApiDateTime(event.target.value) }))}
          />
        </label>

        <label>
          <span>Limit</span>
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
            Apply
          </button>
          <button className="icon-button" type="button" onClick={clearFilters}>
            <Filter aria-hidden="true" />
            Clear
          </button>
        </div>
      </form>

      <div className="alerts-layout">
        <section className="alerts-list-panel" aria-label="Anomaly list">
          <div className="table-toolbar">
            <div>
              <strong>{listState.data?.total.toLocaleString() ?? "0"} anomalies</strong>
              <span>{formatResultRange(query.offset, query.limit, listState.data?.total ?? 0, listState.data?.items.length ?? 0)} from /api/v1/anomalies</span>
            </div>
            <div className="toolbar-meta">
              <span>{listState.updatedAt ? `Updated ${listState.updatedAt.toLocaleTimeString()}` : "Waiting for data"}</span>
            </div>
          </div>

          <div className="log-table-wrap alerts-table-wrap">
            <table className="log-table alerts-table">
              <thead>
                <tr>
                  <th>Detect time</th>
                  <th>Risk</th>
                  <th>User</th>
                  <th>Source IP</th>
                  <th>Rule hits</th>
                  <th>Status</th>
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
                    <td>{alert.user_id || "unknown"}</td>
                    <td>{alert.src_ip || "n/a"}</td>
                    <td>
                      <div className="tag-list">
                        {alert.rule_hits.length > 0 ? alert.rule_hits.map((rule) => <span key={rule}>{rule}</span>) : <span className="muted">none</span>}
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
              <EmptyState title="No anomalies matched" detail="Adjust filters or confirm that the detection pipeline has written anomaly events." />
            ) : null}
          </div>

          <div className="pagination">
            <button
              className="icon-button"
              type="button"
              disabled={!canGoPrevious}
              onClick={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
            >
              Previous
            </button>
            <span>Offset {query.offset.toLocaleString()}</span>
            <button
              className="icon-button"
              type="button"
              disabled={!canGoNext}
              onClick={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
            >
              Next
            </button>
          </div>
        </section>

        <AlertDetailPanel
          state={detailState}
          selectedAlertId={selectedAlertId}
          onRefresh={() => {
            if (selectedAlertId) {
              loadDetail(selectedAlertId);
            }
            loadAlerts(query);
          }}
        />
      </div>
    </section>
  );
}

function AlertDetailPanel({
  state,
  selectedAlertId,
  onRefresh
}: {
  state: LoadState<AnomalyDetailResponse>;
  selectedAlertId: string | null;
  onRefresh: () => void;
}) {
  const detail = state.data;
  const [actionState, setActionState] = useState<{ loading: boolean; message: string | null; error: string | null }>({
    loading: false,
    message: null,
    error: null
  });

  const runAIJudgement = () => {
    if (!selectedAlertId) {
      return;
    }
    setActionState({ loading: true, message: null, error: null });
    analyzeAlert(selectedAlertId)
      .then((report) => {
        setActionState({
          loading: false,
          message: `AI judgement stored (${report.is_mock ? "mock" : report.model_name}).`,
          error: null
        });
        onRefresh();
      })
      .catch((error: unknown) => setActionState({ loading: false, message: null, error: formatError(error) }));
  };

  const submitFalsePositiveFeedback = () => {
    if (!detail) {
      return;
    }
    setActionState({ loading: true, message: null, error: null });
    createFeedback({
      event_id: detail.anomaly.event_id,
      tenant_id: detail.anomaly.tenant_id,
      user_id: detail.anomaly.user_id,
      judgement_id: typeof detail.ai_judgement.judgement_id === "string" ? detail.ai_judgement.judgement_id : undefined,
      feedback_type: "false_positive",
      target_component: "scoring",
      suggestion: "Analyst marked this anomaly for false-positive review.",
      confidence: 1
    })
      .then((feedback) => {
        setActionState({ loading: false, message: `Feedback ${feedback.review_status}.`, error: null });
      })
      .catch((error: unknown) => setActionState({ loading: false, message: null, error: formatError(error) }));
  };

  if (!selectedAlertId) {
    return (
      <aside className="detail-panel">
        <EmptyState title="Select an anomaly" detail="Anomaly detail will show the evidence chain, related logs, baseline, and AI report from FastAPI." />
      </aside>
    );
  }

  return (
    <aside className="detail-panel">
      <div className="detail-panel-header">
        <div>
          <span className="eyebrow">Anomaly detail</span>
          <h2>{detail?.anomaly.event_id ?? selectedAlertId}</h2>
        </div>
        {detail ? <StatusPill ok={detail.anomaly.ai_status === "analyzed"} label={detail.anomaly.ai_status} /> : null}
      </div>

      {state.error ? <ErrorBanner message={state.error} /> : null}
      {actionState.error ? <ErrorBanner message={actionState.error} /> : null}
      {actionState.message ? <div className="success-banner">{actionState.message}</div> : null}
      {state.loading && !detail ? <TableSkeleton /> : null}

      {detail ? (
        <div className="detail-stack">
          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Actions</h3>
              <span>{detail.anomaly.ai_status}</span>
            </div>
            <div className="inline-actions">
              <button className="icon-button primary" type="button" onClick={runAIJudgement} disabled={actionState.loading}>
                <Brain aria-hidden="true" />
                Analyze
              </button>
              <button className="icon-button" type="button" onClick={submitFalsePositiveFeedback} disabled={actionState.loading}>
                <CheckCircle2 aria-hidden="true" />
                False positive
              </button>
            </div>
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Risk Summary</h3>
              <span>{detail.anomaly.risk_level}</span>
            </div>
            <div className="metrics-band compact-metrics">
              <Metric icon={BarChart3} label="Risk score" value={String(detail.anomaly.risk_score)} hint="0 to 100" />
              <Metric icon={ListFilter} label="Reason codes" value={String(detail.anomaly.reason_codes.length)} hint={detail.anomaly.reason_codes.slice(0, 2).join(", ") || "none"} />
              <Metric icon={Sparkles} label="AI status" value={detail.anomaly.ai_status} hint={isEmptyRecord(detail.ai_judgement) ? "No judgement stored" : "Judgement available"} />
            </div>
            <JsonBlock value={detail.anomaly.risk_components} />
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Rule Hits</h3>
              <span>{detail.evidence_chain.rule_hits.length} rules</span>
            </div>
            <div className="tag-list">
              {detail.evidence_chain.rule_hits.length > 0 ? (
                detail.evidence_chain.rule_hits.map((rule) => <span key={rule}>{rule}</span>)
              ) : (
                <span className="muted">none</span>
              )}
            </div>
            <div className="tag-list">
              {detail.evidence_chain.reason_codes.length > 0 ? (
                detail.evidence_chain.reason_codes.map((code) => <span key={code}>{code}</span>)
              ) : (
                <span className="muted">no reason codes</span>
              )}
            </div>
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Evidence Chain</h3>
              <span>{detail.anomaly.baseline_deviations.length} baseline deviations</span>
            </div>
            <p className="risk-reason">{detail.evidence_chain.risk_reason || "No risk reason returned."}</p>
            {detail.anomaly.baseline_deviations.length > 0 ? (
              <ul className="evidence-list">
                {detail.anomaly.baseline_deviations.map((deviation) => {
                  const feature = String(deviation.feature ?? deviation.name ?? "unknown");
                  const actual = String(deviation.actual ?? deviation.value ?? "—");
                  const source = String(deviation.evidence_source ?? "");
                  const sourceLabel = formatEvidenceSource(source);
                  const sampleDays = deviation.sample_days != null ? Number(deviation.sample_days) : undefined;
                  return (
                    <li key={`${feature}-${actual}`}>
                      <strong>{feature}</strong>: {actual}
                      <span className="evidence-meta">
                        <span className="evidence-source">{sourceLabel}</span>
                        {sampleDays !== undefined ? <span className="evidence-days">{sampleDays} days</span> : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="muted">No baseline deviations returned.</p>
            )}
            <JsonBlock value={detail.anomaly.evidence} />
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Related Logs</h3>
              <span>{detail.related_logs.length} events</span>
            </div>
            <div className="related-log-list">
              {detail.related_logs.map((log) => (
                <article key={log.event_id} className="related-log-item">
                  <div>
                    <strong>{log.action}</strong>
                    <span>{formatDateTime(log.event_time)}</span>
                  </div>
                  <p>{log.message}</p>
                  <small>{log.event_id}</small>
                </article>
              ))}
              {detail.related_logs.length === 0 ? <p className="muted">No related logs returned.</p> : null}
            </div>
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Baseline</h3>
              <span>{isEmptyRecord(detail.baseline) ? "missing" : "available"}</span>
            </div>
            {isEmptyRecord(detail.baseline) ? <p className="muted">No baseline returned for this anomaly.</p> : <JsonBlock value={detail.baseline} />}
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>AI Judgement</h3>
              <span>{isEmptyRecord(detail.ai_judgement) ? "not generated" : "stored"}</span>
            </div>
            {isEmptyRecord(detail.ai_judgement) ? (
              <p className="muted">No AI judgement returned for this anomaly.</p>
            ) : (
              <JsonBlock value={detail.ai_judgement} />
            )}
          </section>
        </div>
      ) : null}
    </aside>
  );
}

function UserProfilesPage() {
  const [query, setQuery] = useState({ limit: 25, offset: 0 });
  const [state, setState] = useState<LoadState<{ items: UserBaseline[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });

  const load = useCallback((activeQuery = query, signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    fetchBaselines(activeQuery, signal)
      .then((data) => setState({ data: { items: data.items, total: data.total }, loading: false, error: null, updatedAt: new Date() }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState((current) => ({ ...current, loading: false, error: formatError(error) }));
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    load(query, controller.signal);
    return () => controller.abort();
  }, [load, query]);

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-003 / REQ-006"
        title="User Profiles"
        description="Behavior baseline profiles from ClickHouse-backed user baseline APIs."
        action={
          <button className="icon-button primary" type="button" onClick={() => load()} disabled={state.loading}>
            <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
            Refresh
          </button>
        }
      />
      {state.error ? <ErrorBanner message={state.error} /> : null}
      <div className="profile-grid">
        {state.data?.items.map((profile) => (
          <article className="profile-card" key={`${profile.tenant_id}:${profile.user_id}:${profile.baseline_date}`}>
            <div className="profile-card-head">
              <div>
                <span className="eyebrow">{profile.tenant_id}</span>
                <h2>{profile.user_id}</h2>
              </div>
              <StatusPill ok={profile.baseline_confidence >= 0.7} label={`confidence ${profile.baseline_confidence}`} />
            </div>
            <div className="profile-meta">
              <span>{profile.baseline_date}</span>
              <span>{profile.sample_days} days</span>
              <span>{profile.sample_count} samples</span>
              <span>{profile.fallback_level ?? "none"}</span>
              <span>模型 {profile.model_version}</span>
              <span>训练窗口 {profile.trained_from} ~ {profile.trained_to}</span>
            </div>
            <FiveW1HSections profile={profile} />
            <details className="profile-raw">
              <summary>Raw profiles (debug)</summary>
              <div className="profile-sections">
                <ProfileSection title="who_profile" value={profile.who_profile} />
                <ProfileSection title="time_profile" value={profile.time_profile} />
                <ProfileSection title="location_profile" value={profile.location_profile} />
                <ProfileSection title="access_profile" value={profile.access_profile} />
                <ProfileSection title="volume_profile" value={profile.volume_profile} />
                <ProfileSection title="result_profile" value={profile.result_profile} />
                <ProfileSection title="why_profile" value={profile.why_profile} />
              </div>
            </details>
          </article>
        ))}
        {!state.loading && state.data?.items.length === 0 ? <EmptyState title="No user profiles" detail="No baseline records are available yet." /> : null}
      </div>
      <PaginationControls
        limit={query.limit}
        offset={query.offset}
        total={state.data?.total ?? 0}
        onPrevious={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
        onNext={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
      />
    </section>
  );
}

function formatEvidenceSource(source: string): string {
  const labels: Record<string, string> = {
    user_baseline: "来自用户历史基线",
    user_history: "来自用户历史基线",
    daily_feature: "来自日级行为特征",
    seen_sources: "来自持久化已见来源表",
    peer_group: "来自同组用户基线",
    global: "来自全局基线"
  };
  return (labels[source] ?? source) || "未知来源";
}

function ProfileSection({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <section>
      <h3>{title}</h3>
      <JsonBlock value={value} />
    </section>
  );
}

type ProfileFeature = { name: string; display: string };

// Keyword routing: access_profile feeds both "What" (resources/actions) and
// "How" (device/agent/auth/protocol); these names go to How, the rest to What.
const HOW_FEATURE_HINTS = ["agent", "auth", "device", "protocol"];

function FiveW1HSections({ profile }: { profile: UserBaseline }) {
  const access = flattenProfileFeatures(profile.access_profile);
  const howFromAccess = access.filter((feature) =>
    HOW_FEATURE_HINTS.some((hint) => feature.name.toLowerCase().includes(hint))
  );
  const whatFromAccess = access.filter((feature) => !howFromAccess.includes(feature));

  const whoItems = flattenProfileFeatures(profile.who_profile);
  const whoWithMeta: ProfileFeature[] = [
    { name: "user_id", display: profile.user_id },
    { name: "user_role", display: String(profile.who_profile?.user_role ?? profile.user_id ?? "unknown") },
    ...whoItems
  ];

  const whyItems = flattenProfileFeatures(profile.why_profile);
  const whyWithMeta: ProfileFeature[] = [
    { name: "baseline_confidence", display: `${Math.round(profile.baseline_confidence * 100)}%` },
    { name: "fallback_level", display: profile.fallback_level ?? "none" },
    ...whyItems
  ];

  const dimensionEmptyLabels: Record<string, string> = {
    who: "尚无用户身份与角色数据",
    when: "尚无活跃时间分布数据",
    where: "尚无登录源 IP / 地理位置记录",
    what: "尚无资源访问与行为体量数据",
    why: "尚无业务上下文数据",
    how: "尚无接入设备与认证方式数据"
  };

  const dimensions: Array<{ key: string; title: string; subtitle: string; icon: typeof Activity; items: ProfileFeature[] }> = [
    { key: "who", title: "Who", subtitle: "User, role, department, account type", icon: UserRound, items: whoWithMeta },
    { key: "when", title: "When", subtitle: "Active hours and weekdays", icon: Clock3, items: flattenProfileFeatures(profile.time_profile) },
    { key: "where", title: "Where", subtitle: "Common IPs and locations", icon: RadioTower, items: flattenProfileFeatures(profile.location_profile) },
    {
      key: "what",
      title: "What",
      subtitle: "Resources, actions, volume and outcomes",
      icon: ListFilter,
      items: [...whatFromAccess, ...flattenProfileFeatures(profile.volume_profile), ...flattenProfileFeatures(profile.result_profile)]
    },
    { key: "why", title: "Why", subtitle: "Business context and resource purpose", icon: Sparkles, items: whyWithMeta },
    { key: "how", title: "How", subtitle: "Device, user-agent and auth method", icon: Server, items: howFromAccess }
  ];

  return (
    <div className="w1h-grid">
      {dimensions.map(({ key, title, subtitle, icon: Icon, items }) => (
        <section key={key} className="w1h-card">
          <header className="w1h-card-head">
            <Icon aria-hidden="true" />
            <div>
              <h3>{title}</h3>
              <span>{subtitle}</span>
            </div>
          </header>
          {items.length > 0 ? (
            <dl className="w1h-list">
              {items.map((item) => (
                <div key={item.name} className="w1h-row">
                  <dt>{item.name}</dt>
                  <dd>{item.display}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">{dimensionEmptyLabels[key] ?? "暂无数据"}</p>
          )}
        </section>
      ))}
    </div>
  );
}

function flattenProfileFeatures(profile: Record<string, unknown> | undefined | null): ProfileFeature[] {
  if (!profile || typeof profile !== "object") {
    return [];
  }
  return Object.entries(profile)
    .map(([name, value]) => ({ name, display: displayFeatureValue(value) }))
    .filter((feature) => feature.display !== "");
}

function displayFeatureValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value
      .filter((item) => item !== null && item !== undefined && item !== "")
      .map((item) => String(item))
      .join(", ");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (Array.isArray(record.common_values) && record.common_values.length > 0) {
      return (record.common_values as unknown[]).map((item) => String(item)).join(", ");
    }
    if (typeof record.mean_value === "number") {
      const parts = [`avg ${roundNumber(record.mean_value)}`];
      if (typeof record.p95_value === "number") {
        parts.push(`p95 ${roundNumber(record.p95_value)}`);
      }
      return parts.join(", ");
    }
    const entries = Object.entries(record).filter(([, item]) => item !== null && item !== undefined && item !== "");
    if (entries.length === 0) {
      return "";
    }
    return entries
      .map(([entryKey, item]) => `${entryKey}: ${Array.isArray(item) ? item.join("/") : String(item)}`)
      .join("; ");
  }
  return String(value);
}

function roundNumber(value: number): number {
  return Math.round(value * 100) / 100;
}

function AIJudgementPage() {
  const [query, setQuery] = useState({ limit: 25, offset: 0 });
  const [state, setState] = useState<LoadState<{ items: AIJudgement[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });

  const load = useCallback((activeQuery = query, signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    fetchAIReports(activeQuery, signal)
      .then((data) => setState({ data: { items: data.items, total: data.total }, loading: false, error: null, updatedAt: new Date() }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState((current) => ({ ...current, loading: false, error: formatError(error) }));
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    load(query, controller.signal);
    return () => controller.abort();
  }, [load, query]);

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-004 / REQ-006"
        title="AI Judgement"
        description="Stored AI anomaly judgements and explicit mock markers."
        action={
          <button className="icon-button primary" type="button" onClick={() => load()} disabled={state.loading}>
            <RefreshCcw aria-hidden="true" className={state.loading ? "spin" : ""} />
            Refresh
          </button>
        }
      />
      {state.error ? <ErrorBanner message={state.error} /> : null}
      <div className="compact-list">
        {state.data?.items.map((item) => (
          <article className="judgement-card" key={item.judgement_id}>
            <div className="profile-card-head">
              <div>
                <span className="eyebrow">{item.event_id}</span>
                <h2>{item.attack_type || "unknown attack"}</h2>
              </div>
              <span className={`risk-chip ${riskTone(item.risk_level)}`}>{item.risk_level}</span>
            </div>
            <p>{item.judgement}</p>
            <div className="tag-list">
              <span>{item.model_name}</span>
              {item.is_mock && <span className="mock-badge" aria-label="Mock result">⚠ MOCK</span>}
              <span>confidence {item.confidence}</span>
            </div>
            <JsonBlock value={{ key_reasons: item.key_reasons, recommended_actions: item.recommended_actions, feedback_suggestions: item.feedback_suggestions }} />
          </article>
        ))}
        {!state.loading && state.data?.items.length === 0 ? <EmptyState title="No AI judgements" detail="AI judgement records will appear after anomaly analysis writes ai_judgements." /> : null}
      </div>
      <PaginationControls
        limit={query.limit}
        offset={query.offset}
        total={state.data?.total ?? 0}
        onPrevious={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
        onNext={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
      />
    </section>
  );
}

function DailyReportsPage() {
  const [query, setQuery] = useState({ limit: 20, offset: 0 });
  const [date, setDate] = useState(todayInShanghai());
  const [state, setState] = useState<LoadState<{ items: DailyReport[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [createState, setCreateState] = useState<{ loading: boolean; message: string | null; error: string | null }>({
    loading: false,
    message: null,
    error: null
  });

  const load = useCallback((activeQuery = query, signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    fetchDailyReports(activeQuery, signal)
      .then((data) => setState({ data: { items: data.items, total: data.total }, loading: false, error: null, updatedAt: new Date() }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState((current) => ({ ...current, loading: false, error: formatError(error) }));
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    load(query, controller.signal);
    return () => controller.abort();
  }, [load, query]);

  const generate = () => {
    if (createState.loading) {
      return;
    }
    setCreateState({ loading: true, message: null, error: null });
    createDailyReport({ date })
      .then((report) => {
        setCreateState({ loading: false, message: `Report ready for ${report.date}.`, error: null });
        load();
      })
      .catch((error: unknown) => setCreateState({ loading: false, message: null, error: formatError(error) }));
  };

  return (
    <section className="page">
      <PageHeader
        kicker="REQ-005 / REQ-006"
        title="Daily Reports"
        description="Daily security posture reports generated from logs, anomalies, and AI judgements."
        action={
          <div className="header-actions">
            <input className="date-input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            <button className="icon-button primary" type="button" onClick={generate} disabled={createState.loading}>
              <FileText aria-hidden="true" />
              Generate
            </button>
          </div>
        }
      />
      {state.error ? <ErrorBanner message={state.error} /> : null}
      {createState.error ? <ErrorBanner message={createState.error} /> : null}
      {createState.message ? <div className="success-banner">{createState.message}</div> : null}
      <div className="report-grid">
        {state.data?.items.map((report) => (
          <article className="report-card" key={report.report_id}>
            <div className="profile-card-head">
              <div>
                <span className="eyebrow">{report.date}</span>
                <h2>Score {report.overall_score}</h2>
              </div>
              <StatusPill ok={report.high_risk_count === 0} label={`${report.high_risk_count} high risk`} />
            </div>
            <div className="metrics-band compact-metrics">
              <Metric icon={Database} label="Logs" value={formatNumber(report.log_count)} hint="security_logs" />
              <Metric icon={AlertCircle} label="Anomalies" value={formatNumber(report.alert_count)} hint="anomaly_events" />
              <Metric icon={UserRound} label="Risk users" value={String(report.high_risk_users.length)} hint={report.high_risk_users.slice(0, 2).join(", ") || "none"} />
            </div>
            <p>{report.ai_summary}</p>
            <p className="risk-reason">{report.recommendation}</p>
            <JsonBlock value={{ major_risks: report.major_risks, typical_alerts: report.typical_alerts }} />
          </article>
        ))}
        {!state.loading && state.data?.items.length === 0 ? <EmptyState title="No daily reports" detail="Generate a report for the selected date after ClickHouse has source data." /> : null}
      </div>
      <PaginationControls
        limit={query.limit}
        offset={query.offset}
        total={state.data?.total ?? 0}
        onPrevious={() => setQuery((current) => ({ ...current, offset: Math.max(0, current.offset - current.limit) }))}
        onNext={() => setQuery((current) => ({ ...current, offset: current.offset + current.limit }))}
      />
    </section>
  );
}

function PaginationControls({
  limit,
  offset,
  total,
  onPrevious,
  onNext
}: {
  limit: number;
  offset: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="pagination">
      <button className="icon-button" type="button" disabled={offset <= 0} onClick={onPrevious}>
        Previous
      </button>
      <span>Offset {offset.toLocaleString()}</span>
      <button className="icon-button" type="button" disabled={offset + limit >= total} onClick={onNext}>
        Next
      </button>
    </div>
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
          <StatusPill ok={ok} label={loading ? "Checking" : ok ? "Healthy" : "Unavailable"} />
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
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function formatNumber(value?: number | null): string {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

function todayInShanghai(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function formatSource(value: SourceType): string {
  return sourceTypes.find((source) => source.value === value)?.label ?? value;
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
  if (riskLevel === "critical") {
    return "critical";
  }
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
    return "Showing 0-0";
  }
  return `Showing ${offset + 1}-${Math.min(offset + limit, total)}`;
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
