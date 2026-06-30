from collections.abc import Callable
from datetime import UTC, datetime

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
    create_code_knowledge_core_adapter,
)
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
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
                now=self._now,
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
        evidence = self._evidence_ref(
            evidence_id="EV-INC-003",
            trace_id=query.trace_id,
            source_type="incident",
            source_id="INC-003",
            excerpt="Previous NPE caused by missing request validation for datasetId.",
            extraction_method="manual_confirm",
            confidence=0.9,
        )
        return [
            IncidentMatch(
                incident_id="INC-003",
                similarity=0.86,
                previous_root_cause="missing request validation for datasetId",
                previous_fix="add @NotNull and service-level null guard",
                related_files=[
                    "DatasetController.java",
                    "DatasetService.java",
                    "DatasetMapper.xml",
                ],
                evidence_refs=[evidence],
                confirmed_by_user=True,
            )
        ]

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
        if not evidence_refs:
            raise self._evidence_required(
                trace_id=reviewed_report.trace_id,
                message="IncidentRecord requires at least one evidence_ref.",
            )
        now = self._now()
        root_cause = reviewed_report.approved_findings[0].summary
        fix = reviewed_report.approved_findings[1].summary if len(reviewed_report.approved_findings) > 1 else ""
        record = IncidentRecord(
            incident_id=f"INC-{reviewed_report.trace_id.removeprefix('TRACE-')}",
            repo_id=reviewed_report.repo_id,
            module="dataset-service",
            error_type="NullPointerException",
            symptom="NPE in DatasetService.getVersion",
            root_cause=root_cause,
            fix=fix,
            related_files=[
                "DatasetController.java",
                "DatasetService.java",
                "DatasetMapper.xml",
            ],
            related_nodes=["DatasetService.getVersion", "DatasetMapper.selectVersionById"],
            evidence_refs=evidence_refs,
            confirmed_by_user=True,
            fix_outcome=fix_outcome,
            dedup_key=f"{reviewed_report.repo_id}:NullPointerException:DatasetService.getVersion",
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

    def _evidence_ref(
        self,
        *,
        evidence_id: str,
        trace_id: str,
        source_type: str,
        source_id: str,
        extraction_method: str,
        confidence: float,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        excerpt: str | None = None,
    ) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=evidence_id,
            trace_id=trace_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            excerpt=excerpt,
            excerpt_hash=f"mock-{evidence_id.lower()}",
            extraction_method=extraction_method,
            confidence=confidence,
            created_at=self._now(),
        )

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
