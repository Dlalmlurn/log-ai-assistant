import type {
  AIFeedback,
  AIJudgement,
  AnomalyDetailResponse,
  AnomalyEvent,
  AlertsQuery,
  ApiError,
  BaselineRebuildResponse,
  DailyReport,
  DailyReportCreateQuery,
  FeedbackCreateRequest,
  HealthResponse,
  ListResponse,
  LogsQuery,
  NormalizedLog,
  PaginationQuery,
  StatsOverview,
  UserRiskStats,
  UserBaseline
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = payload.code;
    this.details = payload.details ?? {};
  }
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/v1/health", { signal });
}

export async function fetchLogs(query: LogsQuery, signal?: AbortSignal): Promise<ListResponse<NormalizedLog>> {
  return apiFetch<ListResponse<NormalizedLog>>(withQuery("/api/v1/logs", query), { signal });
}

export async function fetchLog(eventId: string, signal?: AbortSignal): Promise<NormalizedLog> {
  return apiFetch<NormalizedLog>(`/api/v1/logs/${encodeURIComponent(eventId)}`, { signal });
}

export async function fetchAlerts(query: AlertsQuery, signal?: AbortSignal): Promise<ListResponse<AnomalyEvent>> {
  return apiFetch<ListResponse<AnomalyEvent>>(withQuery("/api/v1/anomalies", query), { signal });
}

export async function fetchAlertDetail(alertId: string, signal?: AbortSignal): Promise<AnomalyDetailResponse> {
  return apiFetch<AnomalyDetailResponse>(`/api/v1/anomalies/${encodeURIComponent(alertId)}`, { signal });
}

export async function analyzeAlert(alertId: string, signal?: AbortSignal): Promise<AIJudgement> {
  return apiFetch<AIJudgement>(`/api/v1/ai/judge/${encodeURIComponent(alertId)}`, {
    method: "POST",
    signal
  });
}

export async function fetchBaselines(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<UserBaseline>> {
  return apiFetch<ListResponse<UserBaseline>>(withQuery("/api/v1/baselines/users", query), { signal });
}

export async function fetchBaseline(userId: string, signal?: AbortSignal): Promise<UserBaseline> {
  return apiFetch<UserBaseline>(`/api/v1/baselines/users/${encodeURIComponent(userId)}`, { signal });
}

export async function rebuildBaselines(signal?: AbortSignal): Promise<BaselineRebuildResponse> {
  return apiFetch<BaselineRebuildResponse>("/api/v1/baselines/rebuild", {
    method: "POST",
    signal
  });
}

export async function fetchAIReports(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<AIJudgement>> {
  return apiFetch<ListResponse<AIJudgement>>(withQuery("/api/v1/ai/judgements", query), { signal });
}

export async function fetchDailyReports(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<DailyReport>> {
  return apiFetch<ListResponse<DailyReport>>(withQuery("/api/v1/reports/daily", query), { signal });
}

export async function createDailyReport(
  query: DailyReportCreateQuery = {},
  signal?: AbortSignal
): Promise<DailyReport> {
  return apiFetch<DailyReport>(withQuery("/api/v1/reports/daily", query), {
    method: "POST",
    signal
  });
}

export async function createFeedback(request: FeedbackCreateRequest, signal?: AbortSignal): Promise<AIFeedback> {
  return apiFetch<AIFeedback>("/api/v1/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal
  });
}

export async function fetchStatsOverview(
  query: Partial<{ tenant_id: string; start_time: string; end_time: string }> = {},
  signal?: AbortSignal
): Promise<StatsOverview> {
  return apiFetch<StatsOverview>(withQuery("/api/v1/stats/overview", query), { signal });
}

export async function fetchUserRiskStats(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<UserRiskStats>> {
  return apiFetch<ListResponse<UserRiskStats>>(withQuery("/api/v1/stats/users/risk", query), { signal });
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const payload = await readError(response);
    throw new ApiRequestError(response.status, payload);
  }

  return response.json() as Promise<T>;
}

function withQuery(path: string, query: Record<string, unknown>): string {
  const params = new URLSearchParams();

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });

  const queryString = params.toString();
  return queryString ? `${path}?${queryString}` : path;
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const payload = (await response.json()) as Partial<ApiError>;
    if (payload.code && payload.message) {
      return {
        code: payload.code,
        message: payload.message,
        details: payload.details ?? {}
      };
    }
  } catch {
    // Fall through to the HTTP status fallback.
  }

  return {
    code: "http_error",
    message: `Request failed with HTTP ${response.status}`,
    details: {}
  };
}
