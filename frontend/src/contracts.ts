export type ContractVersion = "1.0.0" | string;

export interface ContractError {
  trace_id: string | null;
  error_code: string;
  message: string;
  source_module: string;
  recoverable: boolean;
  missing_fields: string[];
  evidence_refs: EvidenceRef[];
}

export interface HealthResponse {
  service: string;
  contract_version: string;
  backends: Record<string, string>;
}

export interface EvidenceRef {
  evidence_id: string;
  trace_id: string;
  source_type: string;
  source_id?: string | null;
  file_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  excerpt?: string | null;
  excerpt_hash?: string | null;
  extraction_method: string;
  confidence: number;
  created_at: string;
}

export interface EvidenceBackedItem {
  summary: string;
  evidence_refs: EvidenceRef[];
  confidence?: number | null;
}

export interface SourceLocation {
  file_path: string;
  start_line?: number | null;
  end_line?: number | null;
}

export interface Node {
  node_id: string;
  graph_id: string;
  repo_id: string;
  type: string;
  name: string;
  qualified_name?: string | null;
  source_location?: SourceLocation | null;
  metadata: Record<string, unknown>;
  evidence_refs: EvidenceRef[];
}

export interface Edge {
  edge_id: string;
  graph_id: string;
  source_node_id: string;
  target_node_id: string;
  type: string;
  confidence: number;
  extraction_method: string;
  evidence_refs: EvidenceRef[];
  metadata: Record<string, unknown>;
}

export interface RepoIndexRequest {
  repo_id: string;
  repo_uri: string;
  language_hint: string;
  parser_profile: string;
  contract_version: ContractVersion;
}

export interface GraphSnapshot {
  graph_id: string;
  repo_id: string;
  nodes: Node[];
  edges: Edge[];
  evidence_refs: EvidenceRef[];
  generated_at: string;
  parser_version?: string | null;
  semantic_enrichment_version?: string | null;
  metadata: Record<string, unknown>;
}

export interface GraphQuery {
  repo_id: string;
  graph_id: string;
  query_terms: string[];
  node_filters: string[];
  edge_filters: string[];
  max_depth: number;
  trace_id: string;
  contract_version: ContractVersion;
}

export interface GraphContext {
  trace_id: string;
  matched_nodes: Node[];
  matched_edges: Edge[];
  graph_paths: string[][];
  evidence_refs: EvidenceRef[];
  confidence: number;
}

export interface AlertEvent {
  alert_id: string;
  repo_id: string;
  graph_id?: string | null;
  raw_log: string;
  stack_trace?: string | null;
  error_description?: string | null;
  occurred_at: string;
  source: string;
  contract_version: ContractVersion;
}

export interface IncidentQuery {
  trace_id: string;
  repo_id: string;
  graph_id?: string | null;
  error_type: string;
  suspected_location?: string | null;
  endpoint?: string | null;
  keywords: string[];
  query_terms: string[];
  contract_version: ContractVersion;
}

export interface IncidentMatch {
  incident_id: string;
  similarity: number;
  previous_root_cause: string;
  previous_fix: string;
  related_files: string[];
  evidence_refs: EvidenceRef[];
  confirmed_by_user: boolean;
}

export interface EvidenceBundle {
  trace_id: string;
  repo_id: string;
  contract_version: ContractVersion;
  alert_summary: string;
  incident_query: IncidentQuery;
  matched_nodes: Node[];
  graph_paths: string[][];
  code_evidence: EvidenceRef[];
  sql_evidence: EvidenceRef[];
  config_evidence: EvidenceRef[];
  log_evidence: EvidenceRef[];
  similar_incidents: IncidentMatch[];
  missing_evidence: string[];
}

export interface RCAReport {
  report_id: string;
  trace_id: string;
  repo_id: string;
  contract_version: ContractVersion;
  hypotheses: EvidenceBackedItem[];
  selected_root_cause: EvidenceBackedItem;
  evidence_chain: EvidenceRef[];
  affected_path: string[];
  suggested_fix: EvidenceBackedItem[];
  migration_impact: EvidenceBackedItem;
  migration_checklist: string[];
  confidence: number;
  open_questions: string[];
}

export interface ReviewedRCAReport {
  report_id: string;
  trace_id: string;
  repo_id: string;
  approved_findings: EvidenceBackedItem[];
  rejected_findings: string[];
  missing_evidence: string[];
  risk_notes: string[];
  final_confidence: number;
}

export interface SaveIncidentRequest {
  reviewed_report: ReviewedRCAReport;
  user_confirmation: boolean;
  fix_outcome: string;
  retention_policy: string;
  contract_version: ContractVersion;
}

export interface IncidentRecord {
  incident_id: string;
  repo_id: string;
  module?: string | null;
  error_type: string;
  symptom: string;
  root_cause: string;
  fix: string;
  related_files: string[];
  related_nodes: string[];
  evidence_refs: EvidenceRef[];
  confirmed_by_user: boolean;
  fix_outcome: string;
  dedup_key: string;
  retention_policy: string;
  created_at: string;
  updated_at: string;
}

export type StepKey =
  | "health"
  | "index"
  | "submit"
  | "evidence"
  | "generate"
  | "review"
  | "save"
  | "readback";

export type StepStatus = "idle" | "running" | "passed" | "failed" | "skipped";

export interface StepLog {
  key: StepKey;
  label: string;
  status: StepStatus;
  endpoint: string;
  request?: unknown;
  response?: unknown;
  error?: ContractError | GenericApiError;
  httpStatus?: number;
  elapsedMs?: number;
}

export interface GenericApiError {
  message: string;
  status?: number;
  body?: unknown;
}
