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

import { ApiRequestError, fetchAlertDetail, fetchAlerts, fetchHealth, fetchLogs } from "./api";
import type {
  AlertDetailResponse,
  AlertEvent,
  AlertsQuery,
  HealthResponse,
  LogsQuery,
  NormalizedLog,
  RiskLevel,
  SourceType
} from "./types";

type PageKey = "logs" | "alerts" | "status";

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  updatedAt: Date | null;
};

const initialLogsQuery: LogsQuery = {
  source_type: "",
  username: "",
  src_ip: "",
  status: "",
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
  { label: "Security device", value: "security_device" }
];

const statusOptions = ["", "success", "failed", "blocked", "error"];
const alertStatusOptions = ["", "new", "analyzed", "closed"];
const riskLevelOptions: Array<{ label: string; value: RiskLevel | "" }> = [
  { label: "All risk levels", value: "" },
  { label: "低", value: "低" },
  { label: "中", value: "中" },
  { label: "高", value: "高" },
  { label: "紧急", value: "紧急" }
];

const initialAlertsQuery: AlertsQuery = {
  risk_level: "",
  username: "",
  rule: "",
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
          <button className={page === "alerts" ? "active" : ""} type="button" onClick={() => setPage("alerts")}>
            <AlertCircle aria-hidden="true" />
            Alerts
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
          <span>Elasticsearch</span>
          <span>FastAPI</span>
          <span>React</span>
        </div>
      </aside>

      <main className="workspace">
        {page === "logs" ? <RealtimeLogsPage /> : null}
        {page === "alerts" ? <AlertsPage /> : null}
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
        description: "raw_logs, parsed_logs and alert_events transport",
        icon: RadioTower
      },
      {
        name: "Flink",
        ok: health?.flink ?? false,
        description: "raw_logs to normalized parsed_logs processing",
        icon: Activity
      },
      {
        name: "Elasticsearch",
        ok: health?.elasticsearch ?? false,
        description: "security-logs persistence and search",
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
  const pipelineReady = state.data ? state.data.kafka && state.data.flink && state.data.elasticsearch : false;

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
          hint="Most recent security-logs ingest_time"
        />
        <Metric
          icon={ListFilter}
          label="Consumer groups"
          value={String(Object.keys(state.data?.consumer_lag ?? {}).length)}
          hint="Tracked Kafka lag groups"
        />
        <Metric
          icon={Server}
          label="Last refreshed"
          value={state.updatedAt ? state.updatedAt.toLocaleTimeString() : "Waiting"}
          hint="Health page refresh cadence is 15 seconds"
        />
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
        description="Structured events queried from FastAPI, backed by Elasticsearch security-logs."
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
          <span>Username</span>
          <input
            value={draft.username}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))}
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
          <span>Status</span>
          <select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>
            {statusOptions.map((option) => (
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
          <span>
            Showing {query.offset + 1}-{Math.min(query.offset + query.limit, state.data?.total ?? 0)} from /api/v1/logs
          </span>
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
              <th>Status</th>
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
                <td>{log.username || "unknown"}</td>
                <td>{log.src_ip || "n/a"}</td>
                <td>{log.action}</td>
                <td>
                  <span className={`status-chip ${statusTone(log.status)}`}>{log.status}</span>
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
          <EmptyState title="No logs matched" detail="Adjust filters or confirm that Filebeat, Flink, and Elasticsearch are moving current data." />
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
  const [listState, setListState] = useState<LoadState<{ items: AlertEvent[]; total: number }>>({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [detailState, setDetailState] = useState<LoadState<AlertDetailResponse>>({
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
          if (current && data.items.some((alert) => alert.alert_id === current)) {
            return current;
          }
          return data.items[0]?.alert_id ?? null;
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
        title="Alerts"
        description="Abnormal events queried from FastAPI, backed by Elasticsearch security-alerts and related evidence."
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
          <span>Username</span>
          <input
            value={draft.username}
            placeholder="alice"
            onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))}
          />
        </label>

        <label>
          <span>Rule</span>
          <input
            value={draft.rule}
            placeholder="新IP登录"
            onChange={(event) => setDraft((current) => ({ ...current, rule: event.target.value }))}
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
        <section className="alerts-list-panel" aria-label="Alert list">
          <div className="table-toolbar">
            <div>
              <strong>{listState.data?.total.toLocaleString() ?? "0"} alerts</strong>
              <span>
                Showing {listState.data?.items.length ? query.offset + 1 : 0}-
                {Math.min(query.offset + query.limit, listState.data?.total ?? 0)} from /api/v1/alerts
              </span>
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
                    key={alert.alert_id}
                    className={selectedAlertId === alert.alert_id ? "selected-row" : ""}
                    tabIndex={0}
                    onClick={() => setSelectedAlertId(alert.alert_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedAlertId(alert.alert_id);
                      }
                    }}
                  >
                    <td>
                      <time dateTime={alert.detect_time}>{formatDateTime(alert.detect_time)}</time>
                      <small>{alert.alert_id}</small>
                    </td>
                    <td>
                      <span className={`risk-chip ${riskTone(alert.risk_level)}`}>{alert.risk_level}</span>
                      <small>score {alert.risk_score}</small>
                    </td>
                    <td>{alert.username || "unknown"}</td>
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
              <EmptyState title="No alerts matched" detail="Adjust filters or confirm that the detection pipeline has written security-alerts." />
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

        <AlertDetailPanel state={detailState} selectedAlertId={selectedAlertId} />
      </div>
    </section>
  );
}

function AlertDetailPanel({
  state,
  selectedAlertId
}: {
  state: LoadState<AlertDetailResponse>;
  selectedAlertId: string | null;
}) {
  const detail = state.data;

  if (!selectedAlertId) {
    return (
      <aside className="detail-panel">
        <EmptyState title="Select an alert" detail="Alert detail will show the evidence chain, related logs, baseline, and AI report from FastAPI." />
      </aside>
    );
  }

  return (
    <aside className="detail-panel">
      <div className="detail-panel-header">
        <div>
          <span className="eyebrow">Alert detail</span>
          <h2>{detail?.alert.alert_id ?? selectedAlertId}</h2>
        </div>
        {detail ? <StatusPill ok={detail.alert.status === "analyzed"} label={detail.alert.status} /> : null}
      </div>

      {state.error ? <ErrorBanner message={state.error} /> : null}
      {state.loading && !detail ? <TableSkeleton /> : null}

      {detail ? (
        <div className="detail-stack">
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
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>Evidence Chain</h3>
              <span>{detail.evidence_chain.baseline_deviations.length} baseline deviations</span>
            </div>
            <p className="risk-reason">{detail.evidence_chain.risk_reason || "No risk reason returned."}</p>
            {detail.evidence_chain.baseline_deviations.length > 0 ? (
              <ul className="evidence-list">
                {detail.evidence_chain.baseline_deviations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">No baseline deviations returned.</p>
            )}
            <JsonBlock value={detail.alert.evidence} />
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
            {isEmptyRecord(detail.baseline) ? <p className="muted">No baseline returned for this alert.</p> : <JsonBlock value={detail.baseline} />}
          </section>

          <section className="detail-section">
            <div className="detail-section-title">
              <h3>AI Report</h3>
              <span>{isEmptyRecord(detail.ai_report) ? "not generated" : "stored"}</span>
            </div>
            {isEmptyRecord(detail.ai_report) ? <p className="muted">No AI report returned for this alert.</p> : <JsonBlock value={detail.ai_report} />}
          </section>
        </div>
      ) : null}
    </aside>
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
  if (riskLevel === "紧急") {
    return "critical";
  }
  if (riskLevel === "高") {
    return "high";
  }
  if (riskLevel === "中") {
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
