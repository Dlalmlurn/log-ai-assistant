export type SourceType = "vpn" | "oa" | "api" | "system" | "security_device";
export type RiskLevel = "低" | "中" | "高" | "紧急";

export type HealthResponse = {
  kafka: boolean;
  flink: boolean;
  clickhouse: boolean;
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

export type AlertEvent = {
  alert_id: string;
  event_time: string;
  detect_time: string;
  username?: string | null;
  src_ip?: string | null;
  source_type: SourceType;
  risk_level: RiskLevel;
  risk_score: number;
  rule_hits: string[];
  evidence: Record<string, unknown>;
  related_event_ids: string[];
  related_logs_summary: string;
  status: string;
  llm_analysis_id?: string | null;
};

export type UserBaseline = {
  username: string;
  active_hours: string[];
  common_ips: string[];
  common_user_agents: string[];
  avg_api_calls_per_minute: number;
  common_resources: string[];
  failed_login_count_7d: number;
  sensitive_access_rate: number;
  updated_at: string;
};

export type AIReport = {
  ai_report_id: string;
  alert_id: string;
  created_at: string;
  attack_type: string;
  risk_level: RiskLevel;
  reason: string;
  suggestion: string;
  confidence: number;
  next_steps: string[];
  raw_response: Record<string, unknown>;
};

export type EvidenceChain = {
  rule_hits: string[];
  baseline_deviations: string[];
  risk_reason: string;
};

export type AlertDetailResponse = {
  alert: AlertEvent;
  baseline: Record<string, unknown>;
  related_logs: NormalizedLog[];
  ai_report: Record<string, unknown>;
  evidence_chain: EvidenceChain;
};

export type BaselineRebuildResponse = {
  rebuilt_count: number;
};

export type DailyReport = {
  report_id: string;
  date: string;
  created_at: string;
  overall_score: number;
  log_count: number;
  alert_count: number;
  high_risk_count: number;
  major_risks: string[];
  high_risk_users: string[];
  typical_alerts: Array<Record<string, unknown>>;
  ai_summary: string;
  recommendation: string;
  markdown: string;
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

export type AlertsQuery = {
  risk_level?: RiskLevel | "";
  username?: string;
  rule?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  limit: number;
  offset: number;
};

export type PaginationQuery = {
  limit: number;
  offset: number;
};

export type DailyReportCreateQuery = {
  date?: string;
};

export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};
