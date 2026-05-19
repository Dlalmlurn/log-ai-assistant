import type {
  AIReport,
  AlertDetailResponse,
  AlertEvent,
  AlertsQuery,
  ApiError,
  BaselineRebuildResponse,
  DailyReport,
  DailyReportCreateQuery,
  HealthResponse,
  ListResponse,
  LogsQuery,
  NormalizedLog,
  PaginationQuery,
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

export async function fetchAlerts(query: AlertsQuery, signal?: AbortSignal): Promise<ListResponse<AlertEvent>> {
  return apiFetch<ListResponse<AlertEvent>>(withQuery("/api/v1/alerts", query), { signal });
}

export async function fetchAlertDetail(alertId: string, signal?: AbortSignal): Promise<AlertDetailResponse> {
  return apiFetch<AlertDetailResponse>(`/api/v1/alerts/${encodeURIComponent(alertId)}`, { signal });
}

export async function analyzeAlert(alertId: string, signal?: AbortSignal): Promise<AIReport> {
  return apiFetch<AIReport>(`/api/v1/alerts/${encodeURIComponent(alertId)}/analyze`, {
    method: "POST",
    signal
  });
}

export async function fetchBaselines(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<UserBaseline>> {
  return apiFetch<ListResponse<UserBaseline>>(withQuery("/api/v1/baselines", query), { signal });
}

export async function fetchBaseline(username: string, signal?: AbortSignal): Promise<UserBaseline> {
  return apiFetch<UserBaseline>(`/api/v1/baselines/${encodeURIComponent(username)}`, { signal });
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
): Promise<ListResponse<AIReport>> {
  return apiFetch<ListResponse<AIReport>>(withQuery("/api/v1/ai-reports", query), { signal });
}

export async function fetchDailyReports(
  query: PaginationQuery,
  signal?: AbortSignal
): Promise<ListResponse<DailyReport>> {
  return apiFetch<ListResponse<DailyReport>>(withQuery("/api/v1/daily-reports", query), { signal });
}

export async function createDailyReport(
  query: DailyReportCreateQuery = {},
  signal?: AbortSignal
): Promise<DailyReport> {
  return apiFetch<DailyReport>(withQuery("/api/v1/daily-reports", query), {
    method: "POST",
    signal
  });
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
