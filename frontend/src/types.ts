export type SourceType = "vpn" | "oa" | "api" | "system" | "security_device";

export type HealthResponse = {
  kafka: boolean;
  flink: boolean;
  elasticsearch: boolean;
  dashscope_configured: boolean;
  latest_log_ingest_time: string | null;
  consumer_lag: Record<string, number>;
};

export type NormalizedLog = {
  event_id: string;
  event_time: string;
  ingest_time: string;
  source_type: SourceType;
  username?: string | null;
  src_ip?: string | null;
  src_port?: number | null;
  dst_ip?: string | null;
  dst_port?: number | null;
  action: string;
  resource?: string | null;
  status: string;
  http_method?: string | null;
  user_agent?: string | null;
  message: string;
  raw_message: string;
  risk_tags: string[];
  trace_id?: string | null;
  original_fields: Record<string, unknown>;
};

export type ListResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type LogsQuery = {
  source_type?: SourceType | "";
  username?: string;
  src_ip?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  limit: number;
  offset: number;
};

export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};
