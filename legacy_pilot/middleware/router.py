from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
import os
import re

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
    create_code_knowledge_core_adapter,
)
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
    DeleteGraphResponse,
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentMatch,
    IncidentQuery,
    IncidentRecord,
    RCAReport,
    RepoIndexRequest,
    ReviewedRCAReport,
    StoredGraph,
)
from legacy_pilot.contracts.validators import ensure_supported_contract_version, ensure_trace_id
from legacy_pilot.incident_context_builder.adapter import (
    IncidentContextBuilderAdapter,
    create_incident_context_builder_adapter,
)
from legacy_pilot.incident_memory_store.adapter import (
    IncidentMemoryStoreAdapter,
    IncidentMemoryStoreError,
    create_incident_memory_store_adapter,
)
from legacy_pilot.rca_reasoning_engine.adapter import (
    RCAReasoningEngineAdapter,
    create_rca_reasoning_engine_adapter,
)
from legacy_pilot.rca_reasoning_engine.errors import RCAReasoningEngineError


class MiddlewareRouter:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
        *,
        code_knowledge_core_adapter: CodeKnowledgeCoreAdapter | None = None,
        incident_context_builder_adapter: IncidentContextBuilderAdapter | None = None,
        incident_memory_store_adapter: IncidentMemoryStoreAdapter | None = None,
        rca_reasoning_engine_adapter: RCAReasoningEngineAdapter | None = None,
    ):
        self._now = now or (lambda: datetime.now(UTC))
        self._code_knowledge_core_adapter = (
            code_knowledge_core_adapter
            or create_code_knowledge_core_adapter(now=self._now)
        )
        self._incident_context_builder_adapter = (
            incident_context_builder_adapter
            or create_incident_context_builder_adapter(
                query_graph=lambda graph_query: self.query_graph(graph_query),
                find_similar_incidents=lambda incident_query: self.find_similar_incidents(
                    incident_query
                ),
            )
        )
        self._rca_reasoning_engine_adapter = (
            rca_reasoning_engine_adapter or create_rca_reasoning_engine_adapter()
        )
        self._incident_memory_store_adapter = incident_memory_store_adapter

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        ensure_supported_contract_version(request.contract_version)
        try:
            return self._code_knowledge_core_adapter.index_repo(request)
        except CodeKnowledgeCoreError as exc:
            raise self._code_knowledge_core_error(
                trace_id=f"TRACE-INDEX-{request.repo_id}",
                error=exc,
            ) from exc

    def query_graph(self, query: GraphQuery) -> GraphContext:
        ensure_trace_id(query.trace_id)
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        try:
            return self._code_knowledge_core_adapter.query_graph(query)
        except CodeKnowledgeCoreError as exc:
            raise self._code_knowledge_core_error(
                trace_id=query.trace_id,
                error=exc,
            ) from exc

    def list_graphs(self) -> list[StoredGraph]:
        try:
            records = self._code_knowledge_core_adapter.list_graphs()
        except CodeKnowledgeCoreError as exc:
            raise self._code_knowledge_core_error(
                trace_id=None,
                error=exc,
            ) from exc
        return [
            StoredGraph(
                repo_id=record.repo_id,
                graph_id=record.graph_id,
                parser_version=record.parser_version,
                semantic_enrichment_version=record.semantic_enrichment_version,
                created_at=record.created_at,
                updated_at=record.updated_at,
                node_count=record.node_count,
                edge_count=record.edge_count,
                incident_memory_count=self._incident_count_for_graph(
                    repo_id=record.repo_id,
                    graph_id=record.graph_id,
                ),
            )
            for record in records
        ]

    def delete_graph(self, *, repo_id: str, graph_id: str) -> DeleteGraphResponse:
        incident_count = self._incident_count_for_graph(
            repo_id=repo_id,
            graph_id=graph_id,
        )
        if incident_count > 0:
            noun = "incident memory" if incident_count == 1 else "incident memories"
            raise ContractViolation(
                ContractError(
                    trace_id=None,
                    error_code=ErrorCode.RESOURCE_IN_USE,
                    message=(
                        f"GraphSnapshot {repo_id}/{graph_id} is used by "
                        f"{incident_count} {noun}; delete is blocked."
                    ),
                    source_module="incident_memory_store",
                    recoverable=True,
                )
            )
        try:
            deleted = self._code_knowledge_core_adapter.delete_graph(
                repo_id=repo_id,
                graph_id=graph_id,
            )
        except CodeKnowledgeCoreError as exc:
            raise self._code_knowledge_core_error(
                trace_id=None,
                error=exc,
            ) from exc
        return DeleteGraphResponse(
            repo_id=repo_id,
            graph_id=graph_id,
            deleted=deleted,
            incident_memory_count=incident_count,
        )

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        ensure_supported_contract_version(alert.contract_version)
        return self._incident_context_builder_adapter.submit_alert(alert)

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        ensure_trace_id(query.trace_id)
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        return self._incident_context_builder_adapter.build_evidence_bundle(query)

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        ensure_trace_id(bundle.trace_id)
        ensure_supported_contract_version(bundle.contract_version, trace_id=bundle.trace_id)
        try:
            return self._rca_reasoning_engine_adapter.generate_rca(bundle)
        except RCAReasoningEngineError as exc:
            raise self._rca_reasoning_error(trace_id=bundle.trace_id, error=exc) from exc

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        ensure_trace_id(report.trace_id)
        ensure_supported_contract_version(report.contract_version, trace_id=report.trace_id)
        try:
            return self._rca_reasoning_engine_adapter.review_rca(report)
        except RCAReasoningEngineError as exc:
            raise self._rca_reasoning_error(trace_id=report.trace_id, error=exc) from exc

    def find_similar_incidents(self, query: IncidentQuery) -> list[IncidentMatch]:
        ensure_trace_id(query.trace_id)
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        try:
            return self._incident_memory_store().find_similar_incidents(query)
        except IncidentMemoryStoreError as exc:
            raise self._incident_memory_store_error(
                trace_id=query.trace_id,
                error=exc,
            ) from exc

    def load_incident(self, incident_id: str) -> IncidentRecord:
        try:
            record = self._incident_memory_store().load_incident(incident_id)
        except IncidentMemoryStoreError as exc:
            raise self._incident_memory_store_error(
                trace_id=None,
                error=exc,
            ) from exc
        if record is None:
            raise ContractViolation(
                ContractError(
                    trace_id=None,
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=f"IncidentRecord not found: {incident_id}",
                    source_module="incident_memory_store",
                    recoverable=True,
                )
            )
        return record

    def save_incident(
        self,
        *,
        reviewed_report: ReviewedRCAReport,
        user_confirmation: bool,
        fix_outcome: str,
        retention_policy: str,
        contract_version: str,
    ) -> IncidentRecord:
        ensure_trace_id(reviewed_report.trace_id)
        ensure_supported_contract_version(
            contract_version,
            trace_id=reviewed_report.trace_id,
        )
        if not user_confirmation:
            raise ContractViolation(
                ContractError(
                    trace_id=reviewed_report.trace_id,
                    error_code=ErrorCode.USER_CONFIRMATION_REQUIRED,
                    message="Incident memory can only store user-confirmed RCA results.",
                    source_module="incident_memory_store",
                    recoverable=True,
                    missing_fields=["user_confirmation"],
                )
            )
        evidence_refs = self._collect_evidence(reviewed_report.approved_findings)
        if not reviewed_report.graph_id:
            raise ContractViolation(
                ContractError(
                    trace_id=reviewed_report.trace_id,
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="IncidentRecord requires reviewed_report.graph_id.",
                    source_module="incident_memory_store",
                    recoverable=True,
                    missing_fields=["graph_id"],
                )
            )
        if not evidence_refs:
            raise self._evidence_required(
                trace_id=reviewed_report.trace_id,
                message="IncidentRecord requires at least one evidence_ref.",
            )
        now = self._now()
        root_cause = reviewed_report.approved_findings[0].summary
        fix = reviewed_report.approved_findings[1].summary if len(reviewed_report.approved_findings) > 1 else ""
        related_files = _related_files(evidence_refs)
        related_nodes = _related_nodes(evidence_refs)
        error_type = _derive_error_type(reviewed_report.approved_findings, evidence_refs)
        symptom = _derive_symptom(reviewed_report.approved_findings, evidence_refs)
        module = _derive_module(related_files)
        record = IncidentRecord(
            incident_id=f"INC-{reviewed_report.trace_id.removeprefix('TRACE-')}",
            repo_id=reviewed_report.repo_id,
            graph_id=reviewed_report.graph_id,
            module=module,
            error_type=error_type,
            symptom=symptom,
            root_cause=root_cause,
            fix=fix,
            related_files=related_files,
            related_nodes=related_nodes,
            evidence_refs=evidence_refs,
            confirmed_by_user=True,
            fix_outcome=fix_outcome,
            dedup_key=_dedup_key(
                repo_id=reviewed_report.repo_id,
                error_type=error_type,
                related_nodes=related_nodes,
                related_files=related_files,
                symptom=symptom,
            ),
            retention_policy=retention_policy,
            created_at=now,
            updated_at=now,
        )
        try:
            return self._incident_memory_store().save_incident(record)
        except IncidentMemoryStoreError as exc:
            raise self._incident_memory_store_error(
                trace_id=reviewed_report.trace_id,
                error=exc,
            ) from exc

    def _evidence_required(self, *, trace_id: str, message: str) -> ContractViolation:
        return ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.EVIDENCE_REQUIRED,
                message=message,
                source_module="interface_contract_middleware",
                recoverable=True,
            )
        )

    def _code_knowledge_core_error(
        self,
        *,
        trace_id: str,
        error: CodeKnowledgeCoreError,
    ) -> ContractViolation:
        return ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=error.message,
                source_module=error.source_module,
                recoverable=error.recoverable,
            )
        )

    def _rca_reasoning_error(
        self,
        *,
        trace_id: str,
        error: RCAReasoningEngineError,
    ) -> ContractViolation:
        return ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=error.error_code,
                message=error.message,
                source_module=error.source_module,
                recoverable=error.recoverable,
                missing_fields=error.missing_fields,
            )
        )

    def _incident_memory_store_error(
        self,
        *,
        trace_id: str,
        error: IncidentMemoryStoreError,
    ) -> ContractViolation:
        return ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=error.message,
                source_module="incident_memory_store",
                recoverable=True,
            )
        )

    def _incident_memory_store(self) -> IncidentMemoryStoreAdapter:
        if self._incident_memory_store_adapter is None:
            self._incident_memory_store_adapter = create_incident_memory_store_adapter()
        return self._incident_memory_store_adapter

    def _incident_count_for_graph(self, *, repo_id: str, graph_id: str) -> int:
        try:
            return self._incident_memory_store().count_incidents_for_graph(
                repo_id=repo_id,
                graph_id=graph_id,
            )
        except IncidentMemoryStoreError as exc:
            raise self._incident_memory_store_error(
                trace_id=None,
                error=exc,
            ) from exc

    def runtime_config(self) -> dict[str, str]:
        return {
            "code_knowledge_core": _adapter_backend_name(
                self._code_knowledge_core_adapter,
                env_key="LEGACY_PILOT_CODE_CORE_BACKEND",
                default="gitnexus_cli",
            ),
            "incident_context_builder": _adapter_backend_name(
                self._incident_context_builder_adapter,
                env_key="LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND",
                default="graph_context",
            ),
            "rca_reasoning_engine": _adapter_backend_name(
                self._rca_reasoning_engine_adapter,
                env_key="LEGACY_PILOT_RCA_BACKEND",
                default="qwen_api",
            ),
            "incident_memory_store": _adapter_backend_name(
                self._incident_memory_store_adapter,
                env_key="LEGACY_PILOT_INCIDENT_MEMORY_BACKEND",
                default="postgresql",
                allowed_env_values={"postgresql"},
            ),
        }

    def _collect_evidence(self, items: list[EvidenceBackedItem]) -> list[EvidenceRef]:
        evidence: list[EvidenceRef] = []
        seen: set[str] = set()
        for item in items:
            for ref in item.evidence_refs:
                if ref.evidence_id in seen:
                    continue
                seen.add(ref.evidence_id)
                evidence.append(ref)
        return evidence


_ERROR_TYPE_RE = re.compile(r"\b([A-Za-z_$][\w$]*(?:Exception|Error))\b")
_JAVA_LOCATION_RE = re.compile(
    r"\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\("
    r"[^)]*\.java(?::\d+)?\)"
)


def _derive_error_type(
    findings: list[EvidenceBackedItem],
    evidence_refs: list[EvidenceRef],
) -> str:
    text = _combined_text(findings, evidence_refs)
    match = _ERROR_TYPE_RE.search(text)
    if match:
        return match.group(1)
    return "UnknownError"


def _derive_symptom(
    findings: list[EvidenceBackedItem],
    evidence_refs: list[EvidenceRef],
) -> str:
    for ref in evidence_refs:
        if ref.source_type in {"log", "stack_trace"} and ref.excerpt:
            return _compact(ref.excerpt)
    if findings:
        return _compact(findings[0].summary)
    return "No symptom summary available"


def _related_files(evidence_refs: list[EvidenceRef]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for ref in evidence_refs:
        if not ref.file_path or ref.file_path in seen:
            continue
        seen.add(ref.file_path)
        files.append(ref.file_path)
    return files


def _related_nodes(evidence_refs: list[EvidenceRef]) -> list[str]:
    nodes: list[str] = []
    seen: set[str] = set()
    for ref in evidence_refs:
        for node in _nodes_from_evidence(ref):
            if node in seen:
                continue
            seen.add(node)
            nodes.append(node)
    return nodes


def _nodes_from_evidence(ref: EvidenceRef) -> list[str]:
    nodes = []
    if ref.source_id and not _looks_like_file(ref.source_id):
        nodes.append(ref.source_id)
    if ref.excerpt:
        for match in _JAVA_LOCATION_RE.finditer(ref.excerpt):
            nodes.append(f"{match.group(1)}.{match.group(2)}")
    return nodes


def _derive_module(related_files: list[str]) -> str | None:
    if not related_files:
        return None
    path = related_files[0].replace("\\", "/")
    if "/src/main/java/" in f"/{path}":
        java_tail = f"/{path}".split("/src/main/java/", 1)[1]
        if "/" not in java_tail:
            return None
        package_path = java_tail.rsplit("/", 1)[0]
        return package_path.replace("/", ".") if package_path else None
    parts = [part for part in path.split("/")[:-1] if part]
    return ".".join(parts[-2:]) if parts else None


def _dedup_key(
    *,
    repo_id: str,
    error_type: str,
    related_nodes: list[str],
    related_files: list[str],
    symptom: str,
) -> str:
    location = (
        related_nodes[0]
        if related_nodes
        else related_files[0]
        if related_files
        else sha256(symptom.encode("utf-8")).hexdigest()[:12]
    )
    return f"{repo_id}:{error_type}:{location}"


def _combined_text(
    findings: list[EvidenceBackedItem],
    evidence_refs: list[EvidenceRef],
) -> str:
    parts = [item.summary for item in findings]
    parts.extend(ref.excerpt or "" for ref in evidence_refs)
    parts.extend(ref.source_id or "" for ref in evidence_refs)
    return "\n".join(parts)


def _compact(value: str) -> str:
    return " ".join(value.split())[:500]


def _looks_like_file(value: str) -> bool:
    leaf = value.rsplit("/", 1)[-1].lower()
    return leaf.endswith(
        (
            ".java",
            ".xml",
            ".yml",
            ".yaml",
            ".properties",
            ".sql",
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".go",
            ".cs",
            ".c",
            ".cpp",
            ".h",
        )
    )


def _adapter_backend_name(
    adapter: object | None,
    *,
    env_key: str,
    default: str,
    allowed_env_values: set[str] | None = None,
) -> str:
    if adapter is None:
        selected = os.getenv(env_key, default)
        if allowed_env_values is None or selected.strip().lower() in allowed_env_values:
            return selected
        return f"unsupported:{selected}"
    if backend_name := getattr(adapter, "backend_name", None):
        return str(backend_name)
    name = adapter.__class__.__name__
    normalized = {
        "GitNexusCliCodeKnowledgeCoreAdapter": "gitnexus_cli",
        "GraphBackedIncidentContextBuilderAdapter": "graph_context",
        "QwenApiRCAReasoningEngineAdapter": "qwen_api",
        "PostgresIncidentMemoryStoreAdapter": "postgresql",
    }
    return normalized.get(name, name)
