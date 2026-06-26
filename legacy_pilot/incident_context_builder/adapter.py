from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceBundle,
    EvidenceRef,
    IncidentMatch,
    IncidentQuery,
    Node,
)
from legacy_pilot.incident_context_builder.signals import parse_alert_event


class IncidentContextBuilderAdapter(ABC):
    @abstractmethod
    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        ...

    @abstractmethod
    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        ...


class MockIncidentContextBuilderAdapter(IncidentContextBuilderAdapter):
    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(UTC))

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        signals = parse_alert_event(alert)
        endpoint = signals.endpoint or (
            "/api/dataset/version" if "Dataset" in alert.raw_log else None
        )
        query_terms = signals.query_terms
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=alert.graph_id,
            error_type=signals.error_type,
            suspected_location=signals.suspected_location,
            endpoint=endpoint,
            keywords=signals.keywords or query_terms,
            query_terms=query_terms,
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
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
            graph_id=query.graph_id or "GRAPH-DEMO",
            repo_id=query.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="com.legacy.DatasetService.getVersion",
            evidence_refs=[code_evidence],
        )
        return EvidenceBundle(
            trace_id=query.trace_id,
            repo_id=query.repo_id,
            contract_version=query.contract_version,
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


def create_incident_context_builder_adapter(
    *,
    backend: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> IncidentContextBuilderAdapter:
    selected_backend = backend or "mock"
    if selected_backend.strip().lower() == "mock":
        return MockIncidentContextBuilderAdapter(now=now)
    return MockIncidentContextBuilderAdapter(now=now)
