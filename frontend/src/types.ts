export type SourceType = "vpn" | "oa" | "api" | "system" | "file" | "database" | "security_device";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type LogResult = "success" | "fail" | "denied" | "error";
export type BaselinePeriodType =
  | "global"
  | "rolling"
  | "weekday"
  | "calendar_month"
  | "month_phase"
  | "weekday_month_phase";
export type BaselineMergeMode = "append" | "replace" | "adjust";

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
  tenant_id: string;
  source_type: SourceType;
  log_type: string;
  user_id?: string | null;
  account_type?: string | null;
  user_role?: string | null;
  department?: string | null;
  host?: string | null;
  src_ip?: string | null;
  src_port?: number | null;
  dst_ip?: string | null;
  dst_port?: number | null;
  geo: Record<string, unknown>;
  action: string;
  object_type?: string | null;
  object_id?: string | null;
  resource?: string | null;
  result: LogResult;
  severity: number;
  user_agent?: string | null;
  protocol?: string | null;
  auth_method?: string | null;
  session_id?: string | null;
  trace_id?: string | null;
  scenario_id?: string | null;
  scenario_type?: string | null;
  attack_chain_id?: string | null;
  step_index?: number | null;
  injected_label?: string | null;
  message: string;
  raw_log: string;
  risk_tags: string[];
  attrs: Record<string, unknown>;
};

export type AnomalyEvent = {
  event_id: string;
  event_time: string;
  detect_time: string;
  tenant_id: string;
  user_id?: string | null;
  src_ip?: string | null;
  host?: string | null;
  source_type?: SourceType | null;
  action?: string | null;
  object_type?: string | null;
  object_id?: string | null;
  attack_type?: string | null;
  risk_score: number;
  risk_level: RiskLevel;
  risk_components: Record<string, unknown>;
  rule_hits: string[];
  baseline_deviations: Array<Record<string, unknown>>;
  reason_codes: string[];
  evidence: Record<string, unknown>;
  related_event_ids: string[];
  scenario_id?: string | null;
  scenario_type?: string | null;
  attack_chain_id?: string | null;
  ai_status: "not_required" | "pending" | "analyzed" | "failed";
  status: "new" | "investigating" | "closed" | "false_positive";
  created_at: string;
};

export type UserBaseline = {
  baseline_date: string;
  tenant_id: string;
  user_id: string;
  model_version: string;
  period_type: BaselinePeriodType;
  period_key: string;
  trained_from: string;
  trained_to: string;
  sample_days: number;
  sample_count: number;
  baseline_confidence: number;
  who_profile: Record<string, unknown>;
  time_profile: Record<string, unknown>;
  location_profile: Record<string, unknown>;
  access_profile: Record<string, unknown>;
  volume_profile: Record<string, unknown>;
  result_profile: Record<string, unknown>;
  why_profile: Record<string, unknown>;
  fallback_level?: "none" | "peer_group" | "department" | "global";
  selected_baseline: {
    period_type: BaselinePeriodType;
    period_key: string;
    fallback_level: string;
    override_ids: string[];
    model_version?: string;
  };
  created_at: string;
};

export type BaselineOverride = {
  override_id: string;
  tenant_id: string;
  user_id: string;
  profile_group: "who" | "time" | "location" | "access" | "volume" | "result" | "why";
  feature_name: string;
  period_type: BaselinePeriodType;
  period_key: string;
  merge_mode: BaselineMergeMode;
  override_value: Record<string, unknown>;
  source_type: "manual" | "ai_feedback";
  source_feedback_id?: string | null;
  reason: string;
  status: "pending" | "active" | "rejected" | "revoked" | "expired";
  effective_from: string;
  effective_to?: string | null;
  created_by: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  model_version: string;
  created_at: string;
  updated_at: string;
};

export type BaselineOverrideCreateRequest = {
  tenant_id?: string;
  user_id: string;
  profile_group: BaselineOverride["profile_group"];
  feature_name: string;
  period_type: BaselinePeriodType;
  period_key: string;
  merge_mode: BaselineMergeMode;
  override_value: Record<string, unknown>;
  reason: string;
  effective_from: string;
  effective_to?: string | null;
  created_by?: string;
};

export type AIJudgement = {
  judgement_id: string;
  event_id: string;
  created_at: string;
  model_name: string;
  model_version?: string | null;
  risk_level: RiskLevel;
  attack_type: string;
  judgement: string;
  key_reasons: string[];
  recommended_actions: string[];
  confidence: number;
  feedback_suggestions: Record<string, unknown>;
  raw_response: Record<string, unknown>;
  is_mock: boolean;
};

export type AIFeedback = {
  feedback_id: string;
  event_id: string;
  judgement_id?: string | null;
  tenant_id: string;
  user_id?: string | null;
  feedback_type: "rule_weight" | "baseline_threshold" | "false_positive" | "new_pattern" | "data_contract";
  suggestion: string;
  target_component: "rule" | "baseline" | "scoring" | "data_contract";
  confidence: number;
  review_status: "pending" | "accepted" | "rejected";
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_reason?: string | null;
  applied_override_id?: string | null;
  applied_version?: string | null;
  created_at: string;
};

export type FeedbackReviewRequest = {
  decision: "accepted" | "rejected";
  reviewed_by?: string;
  review_reason: string;
  override?: Omit<
    BaselineOverrideCreateRequest,
    "tenant_id" | "user_id" | "reason" | "created_by"
  >;
};

export type FeedbackReviewResponse = {
  feedback: AIFeedback;
  override?: BaselineOverride | null;
  applied_override_id?: string | null;
  applied_version?: string | null;
};

export type FeedbackCreateRequest = {
  event_id: string;
  judgement_id?: string | null;
  tenant_id?: string;
  user_id?: string | null;
  feedback_type: AIFeedback["feedback_type"];
  suggestion: string;
  target_component: AIFeedback["target_component"];
  confidence?: number;
};

export type StatsOverview = {
  log_count: number;
  latest_log_ingest_time: string | null;
  anomaly_count: number;
  high_risk_count: number;
  critical_count: number;
  ai_pending_count: number;
  baseline_user_count: number;
  latest_report_date: string | null;
};

export type UserRiskStats = {
  user_id: string;
  anomaly_count: number;
  high_risk_count: number;
  critical_count: number;
  max_risk_score: number;
  latest_event_time: string | null;
};

export type EvidenceChain = {
  rule_hits: string[];
  baseline_deviations: string[];
  reason_codes: string[];
  risk_components: Record<string, unknown>;
  ai_status: "not_required" | "pending" | "analyzed" | "failed";
  risk_reason: string;
};

export type AnomalyDetailResponse = {
  anomaly: AnomalyEvent;
  baseline: Record<string, unknown>;
  related_logs: NormalizedLog[];
  ai_judgement: Record<string, unknown>;
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
  user_id?: string;
  src_ip?: string;
  result?: LogResult | "";
  start_time?: string;
  end_time?: string;
  limit: number;
  offset: number;
};

export type AlertsQuery = {
  risk_level?: RiskLevel | "";
  user_id?: string;
  reason_code?: string;
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
