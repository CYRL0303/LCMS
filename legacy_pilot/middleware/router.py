from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
    Edge,
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentMatch,
    IncidentQuery,
    IncidentRecord,
    Node,
    RCAReport,
    RepoIndexRequest,
    ReviewedRCAReport,
)
from legacy_pilot.contracts.validators import ensure_supported_contract_version


class MiddlewareRouter:
    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(UTC))

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        ensure_supported_contract_version(request.contract_version)
        trace_id = f"TRACE-INDEX-{request.repo_id}"
        evidence = self._evidence_ref(
            evidence_id="EV-REPO-001",
            trace_id=trace_id,
            source_type="code",
            source_id=request.repo_uri,
            file_path="src/main/java/DatasetService.java",
            start_line=1,
            end_line=80,
            excerpt="class DatasetService { ... }",
            extraction_method="java_parser",
            confidence=0.95,
        )
        controller = Node(
            node_id="NODE-DATASET-CONTROLLER",
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            type="Class",
            name="DatasetController",
            qualified_name="com.legacy.DatasetController",
            evidence_refs=[evidence],
        )
        service = Node(
            node_id="NODE-DATASET-SERVICE",
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="com.legacy.DatasetService.getVersion",
            evidence_refs=[evidence],
        )
        edge = Edge(
            edge_id="EDGE-CONTROLLER-SERVICE",
            graph_id="GRAPH-DEMO",
            source_node_id=controller.node_id,
            target_node_id=service.node_id,
            type="CALLS",
            confidence=0.92,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        return GraphSnapshot(
            graph_id="GRAPH-DEMO",
            repo_id=request.repo_id,
            nodes=[controller, service],
            edges=[edge],
            evidence_refs=[evidence],
            generated_at=self._now(),
        )

    def query_graph(self, query: GraphQuery) -> GraphContext:
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        evidence = self._evidence_ref(
            evidence_id="EV-GRAPH-001",
            trace_id=query.trace_id,
            source_type="code",
            source_id="DatasetService.java",
            file_path="src/main/java/DatasetService.java",
            start_line=40,
            end_line=45,
            excerpt="return datasetMapper.selectVersionById(req.getDatasetId());",
            extraction_method="java_parser",
            confidence=0.95,
        )
        controller = Node(
            node_id="NODE-DATASET-CONTROLLER-GET-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="API Endpoint",
            name="/api/dataset/version",
            qualified_name="DatasetController.getVersion",
            evidence_refs=[evidence],
        )
        service = Node(
            node_id="NODE-DATASET-SERVICE-GET-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="DatasetService.getVersion",
            evidence_refs=[evidence],
        )
        mapper = Node(
            node_id="NODE-DATASET-MAPPER-SELECT-VERSION",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="Mapper",
            name="selectVersionById",
            qualified_name="DatasetMapper.selectVersionById",
            evidence_refs=[evidence],
        )
        controller_to_service = Edge(
            edge_id="EDGE-CONTROLLER-SERVICE-GET-VERSION",
            graph_id=query.graph_id,
            source_node_id=controller.node_id,
            target_node_id=service.node_id,
            type="CALLS",
            confidence=0.9,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        service_to_mapper = Edge(
            edge_id="EDGE-SERVICE-MAPPER-SELECT-VERSION",
            graph_id=query.graph_id,
            source_node_id=service.node_id,
            target_node_id=mapper.node_id,
            type="USES_MAPPER",
            confidence=0.86,
            extraction_method="java_parser",
            evidence_refs=[evidence],
        )
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[controller, service, mapper],
            matched_edges=[controller_to_service, service_to_mapper],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            evidence_refs=[evidence],
            confidence=0.88,
        )

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        ensure_supported_contract_version(alert.contract_version)
        trace_id = f"TRACE-{alert.alert_id}"
        error_type = self._detect_error_type(alert)
        suspected_location = self._detect_location(alert)
        query_terms = [error_type]
        if suspected_location:
            query_terms.append(suspected_location)
        return IncidentQuery(
            trace_id=trace_id,
            repo_id=alert.repo_id,
            error_type=error_type,
            suspected_location=suspected_location,
            endpoint="/api/dataset/version" if "Dataset" in alert.raw_log else None,
            keywords=[term for term in query_terms if term],
            query_terms=query_terms,
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        code_evidence = self._evidence_ref(
            evidence_id="EV-CODE-001",
            trace_id=query.trace_id,
            source_type="code",
            source_id="DatasetService.java",
            file_path="src/main/java/DatasetService.java",
            start_line=40,
            end_line=45,
            excerpt="return datasetMapper.selectVersionById(req.getDatasetId());",
            extraction_method="java_parser",
            confidence=0.95,
        )
        log_evidence = self._evidence_ref(
            evidence_id="EV-LOG-001",
            trace_id=query.trace_id,
            source_type="log",
            source_id=query.trace_id,
            excerpt="NullPointerException at DatasetService.getVersion(DatasetService.java:42)",
            extraction_method="regex",
            confidence=0.88,
        )
        service_node = Node(
            node_id="NODE-DATASET-SERVICE-GET-VERSION",
            graph_id="GRAPH-DEMO",
            repo_id=query.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="com.legacy.DatasetService.getVersion",
            evidence_refs=[code_evidence],
        )
        return EvidenceBundle(
            trace_id=query.trace_id,
            repo_id=query.repo_id,
            alert_summary=f"{query.error_type} near {query.suspected_location}",
            incident_query=query,
            matched_nodes=[service_node],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            code_evidence=[code_evidence],
            log_evidence=[log_evidence],
            similar_incidents=self.find_similar_incidents(query),
        )

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        primary_evidence = [*bundle.code_evidence, *bundle.log_evidence]
        if not primary_evidence:
            raise self._evidence_required(
                trace_id=bundle.trace_id,
                message="EvidenceBundle must contain evidence before RCA generation.",
            )
        root_cause = EvidenceBackedItem(
            summary="DatasetService.getVersion dereferences datasetId without a validated input guard.",
            evidence_refs=primary_evidence,
            confidence=0.82,
        )
        suggested_fix = EvidenceBackedItem(
            summary="Add request-level @NotNull validation and a service-level null guard for datasetId.",
            evidence_refs=primary_evidence,
            confidence=0.8,
        )
        migration_impact = EvidenceBackedItem(
            summary="Medium risk: the endpoint depends on DatasetService, DatasetMapper, and dataset_version.",
            evidence_refs=primary_evidence,
            confidence=0.76,
        )
        return RCAReport(
            report_id=f"RCA-{bundle.trace_id.removeprefix('TRACE-')}",
            trace_id=bundle.trace_id,
            repo_id=bundle.repo_id,
            hypotheses=[root_cause],
            selected_root_cause=root_cause,
            evidence_chain=primary_evidence,
            affected_path=bundle.graph_paths[0] if bundle.graph_paths else [],
            suggested_fix=[suggested_fix],
            migration_impact=migration_impact,
            migration_checklist=[
                "Add a missing datasetId regression test.",
                "Check DTO validation for every endpoint reusing DatasetReqVO.",
                "Verify DatasetMapper SQL behavior for null datasetId.",
            ],
            confidence=0.82,
            open_questions=[],
        )

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        if not self._has_evidence(report.selected_root_cause):
            raise self._evidence_required(
                trace_id=report.trace_id,
                message="selected_root_cause must include evidence_refs.",
            )
        for fix in report.suggested_fix:
            if not self._has_evidence(fix):
                raise self._evidence_required(
                    trace_id=report.trace_id,
                    message="suggested_fix must include evidence_refs.",
                )
        if not self._has_evidence(report.migration_impact):
            raise self._evidence_required(
                trace_id=report.trace_id,
                message="migration_impact must include evidence_refs.",
            )
        return ReviewedRCAReport(
            report_id=report.report_id,
            trace_id=report.trace_id,
            repo_id=report.repo_id,
            approved_findings=[report.selected_root_cause, *report.suggested_fix],
            rejected_findings=[],
            missing_evidence=[],
            risk_notes=[
                "RCA is based on mock evidence; replace Code Knowledge Core and RCA Engine adapters later."
            ],
            final_confidence=report.confidence,
        )

    def find_similar_incidents(self, query: IncidentQuery) -> list[IncidentMatch]:
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
        return IncidentRecord(
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

    def _detect_error_type(self, alert: AlertEvent) -> str:
        text = f"{alert.raw_log}\n{alert.stack_trace or ''}\n{alert.error_description or ''}"
        if "NullPointerException" in text:
            return "NullPointerException"
        if "Slow query" in text or "slow query" in text:
            return "SlowQuery"
        return "UnknownError"

    def _detect_location(self, alert: AlertEvent) -> str | None:
        text = f"{alert.raw_log}\n{alert.stack_trace or ''}"
        if "DatasetService.getVersion" in text:
            return "DatasetService.getVersion"
        return None

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

    def _has_evidence(self, value: Any) -> bool:
        if isinstance(value, dict):
            return bool(value.get("evidence_refs"))
        return bool(getattr(value, "evidence_refs", None))

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
