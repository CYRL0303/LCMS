from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from legacy_pilot.contracts.enums import (
    ExtractionMethod,
    SourceType,
    VerificationStatus,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class EvidenceRef(ContractModel):
    evidence_id: str
    trace_id: str
    source_type: SourceType
    source_id: str | None = None
    file_path: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    excerpt: str | None = None
    excerpt_hash: str | None = None
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime

    @model_validator(mode="after")
    def end_line_must_follow_start_line(self) -> "EvidenceRef":
        if self.start_line is not None and self.end_line is not None:
            if self.end_line < self.start_line:
                raise ValueError("end_line must be greater than or equal to start_line")
        return self


class EvidenceBackedItem(ContractModel):
    summary: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SourceLocation(ContractModel):
    file_path: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class Node(ContractModel):
    node_id: str
    graph_id: str
    repo_id: str
    type: str
    name: str
    qualified_name: str | None = None
    source_location: SourceLocation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class Edge(ContractModel):
    edge_id: str
    graph_id: str
    source_node_id: str
    target_node_id: str
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: ExtractionMethod
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepoIndexRequest(ContractModel):
    repo_id: str
    repo_uri: str
    language_hint: str
    parser_profile: str
    contract_version: str


class GraphSnapshot(ContractModel):
    graph_id: str
    repo_id: str
    nodes: list[Node]
    edges: list[Edge]
    evidence_refs: list[EvidenceRef]
    generated_at: datetime
    parser_version: str | None = None
    semantic_enrichment_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphQuery(ContractModel):
    repo_id: str
    graph_id: str
    query_terms: list[str]
    node_filters: list[str] = Field(default_factory=list)
    edge_filters: list[str] = Field(default_factory=list)
    max_depth: int = Field(ge=1, le=10)
    trace_id: str
    contract_version: str


class GraphContext(ContractModel):
    trace_id: str
    matched_nodes: list[Node]
    matched_edges: list[Edge]
    graph_paths: list[list[str]]
    evidence_refs: list[EvidenceRef]
    confidence: float = Field(ge=0.0, le=1.0)


class AlertEvent(ContractModel):
    alert_id: str
    repo_id: str
    graph_id: str | None = None
    raw_log: str
    stack_trace: str | None = None
    error_description: str | None = None
    occurred_at: datetime
    source: str
    contract_version: str


class IncidentQuery(ContractModel):
    trace_id: str
    repo_id: str
    graph_id: str | None = None
    error_type: str
    suspected_location: str | None = None
    endpoint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    contract_version: str


class IncidentMatch(ContractModel):
    incident_id: str
    similarity: float = Field(ge=0.0, le=1.0)
    previous_root_cause: str
    previous_fix: str
    related_files: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confirmed_by_user: bool


class EvidenceBundle(ContractModel):
    trace_id: str
    repo_id: str
    contract_version: str
    alert_summary: str
    incident_query: IncidentQuery
    matched_nodes: list[Node] = Field(default_factory=list)
    graph_paths: list[list[str]] = Field(default_factory=list)
    code_evidence: list[EvidenceRef] = Field(default_factory=list)
    sql_evidence: list[EvidenceRef] = Field(default_factory=list)
    config_evidence: list[EvidenceRef] = Field(default_factory=list)
    log_evidence: list[EvidenceRef] = Field(default_factory=list)
    similar_incidents: list[IncidentMatch] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class RCAReport(ContractModel):
    report_id: str
    trace_id: str
    repo_id: str
    contract_version: str
    hypotheses: list[EvidenceBackedItem] = Field(min_length=1)
    selected_root_cause: EvidenceBackedItem
    evidence_chain: list[EvidenceRef] = Field(min_length=1)
    affected_path: list[str] = Field(default_factory=list)
    suggested_fix: list[EvidenceBackedItem] = Field(min_length=1)
    migration_impact: EvidenceBackedItem
    migration_checklist: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    open_questions: list[str] = Field(default_factory=list)


class ReviewedRCAReport(ContractModel):
    report_id: str
    trace_id: str
    repo_id: str
    approved_findings: list[EvidenceBackedItem] = Field(default_factory=list)
    rejected_findings: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    final_confidence: float = Field(ge=0.0, le=1.0)


class SaveIncidentRequest(ContractModel):
    reviewed_report: ReviewedRCAReport
    user_confirmation: bool
    fix_outcome: str
    retention_policy: str
    contract_version: str


class IncidentRecord(ContractModel):
    incident_id: str
    repo_id: str
    module: str | None = None
    error_type: str
    symptom: str
    root_cause: str
    fix: str
    related_files: list[str] = Field(default_factory=list)
    related_nodes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    confirmed_by_user: bool
    fix_outcome: str
    dedup_key: str
    retention_policy: str
    created_at: datetime
    updated_at: datetime


class LLMSemanticResult(ContractModel):
    evidence_span: str
    source_location: SourceLocation
    prompt_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: ExtractionMethod = ExtractionMethod.LLM
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @field_validator("extraction_method")
    @classmethod
    def extraction_method_must_be_llm(cls, value: str) -> str:
        if value != ExtractionMethod.LLM:
            raise ValueError("LLM semantic results must use extraction_method='llm'")
        return value
