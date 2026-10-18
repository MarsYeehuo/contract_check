export type EngineStatus = "pass" | "risk" | "manual";
export type EffectiveStatus = EngineStatus | "not_applicable";
export type AnnotationStatus = "pass" | "risk" | "not_applicable";
export type Severity = "high" | "medium" | "low";

export interface Evidence {
  start: number;
  end: number;
  text: string;
  operator: "keyword" | "regex";
  keyword: string | null;
}

export interface AIInfo {
  mode: "real" | "mock" | "error";
  verdict: "pass" | "risk" | "uncertain";
  reason: string;
  quote: string;
  evidence: Evidence[];
  review_required: boolean;
  model: string;
}

export interface RuleResult {
  rule_id: string;
  name: string;
  description: string;
  severity: Severity;
  operator: "keyword" | "regex";
  status: EngineStatus;
  matched: boolean;
  match_count: number;
  evidence: Evidence[];
  suggestion: string;
  llm_eligible: boolean;
  ai: AIInfo | null;
}

export interface LLMInfo {
  enabled: boolean;
  available: boolean;
  source: "none" | "request" | "env";
  status: "disabled" | "not_needed" | "no_key" | "ok" | "error";
  model: string;
  error: string | null;
}

export interface ReviewResponse {
  review_id: string;
  created_at: string;
  filename: string;
  ruleset_version: string;
  summary: Record<string, number>;
  llm: LLMInfo;
  results: RuleResult[];
}

export interface Annotation {
  rule_id: string;
  reviewer: string;
  status: AnnotationStatus;
  note: string | null;
  timestamp: string;
}

export interface AuditEntry {
  seq: number;
  review_id: string;
  rule_id: string;
  reviewer: string;
  timestamp: string;
  old_status: EffectiveStatus;
  new_status: AnnotationStatus;
  engine_status: EngineStatus;
  note: string | null;
  ruleset_version: string;
}

export interface AnnotationResponse {
  annotation: Annotation;
  effective_status: AnnotationStatus;
  audit_entry: AuditEntry;
}

export interface ReviewDetail {
  review: ReviewResponse;
  annotations: Annotation[];
  audit: AuditEntry[];
}

export interface ReportResponse {
  filename: string;
  mime: string;
  content: string;
}

export type ReportFormat = "markdown" | "json";

export interface HealthResponse {
  status: string;
  version: string;
  llm_configured: boolean;
}

export interface SampleInfo {
  id: string;
  filename: string;
  description: string;
  expected: Record<string, number>;
}

export interface SampleDetail {
  id: string;
  filename: string;
  text: string;
}
