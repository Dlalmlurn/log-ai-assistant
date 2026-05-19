import type { ApiError, HealthResponse, ListResponse, LogsQuery, NormalizedLog } from "./types";

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
  const params = new URLSearchParams();

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });

  return apiFetch<ListResponse<NormalizedLog>>(`/api/v1/logs?${params.toString()}`, { signal });
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
