from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from legacy_pilot.contracts.errors import ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
    Edge,
    EvidenceBackedItem,
    EvidenceRef,
    GraphSnapshot,
    GraphQuery,
    IncidentQuery,
    RCAReport,
)
from legacy_pilot.contracts.validators import ensure_supported_contract_version, ensure_trace_id


def evidence_ref(evidence_id: str = "EV-001") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-001",
        source_type="code",
        source_id="DatasetService.java",
        file_path="src/main/java/DatasetService.java",
        start_line=40,
        end_line=45,
        excerpt="req.getDatasetId().toString()",
        excerpt_hash="hash-001",
        extraction_method="java_parser",
        confidence=0.95,
        created_at=datetime(2026, 6, 11, tzinfo=UTC),
    )


def test_evidence_ref_rejects_confidence_outside_zero_to_one():
    with pytest.raises(ValidationError) as excinfo:
        EvidenceRef(
            evidence_id="EV-001",
            trace_id="TRACE-001",
            source_type="code",
            source_id="DatasetService.java",
            extraction_method="java_parser",
            confidence=1.1,
            created_at=datetime(2026, 6, 11, tzinfo=UTC),
        )

    assert "less than or equal to 1" in str(excinfo.value)


def test_edge_requires_at_least_one_evidence_ref():
    with pytest.raises(ValidationError) as excinfo:
        Edge(
            edge_id="EDGE-001",
            graph_id="GRAPH-001",
            source_node_id="NODE-001",
            target_node_id="NODE-002",
            type="CALLS",
            confidence=0.91,
            extraction_method="java_parser",
            evidence_refs=[],
        )

    assert "at least 1 item" in str(excinfo.value)


def test_runtime_requests_require_trace_and_contract_version():
    with pytest.raises(ValidationError) as excinfo:
        GraphQuery(
            repo_id="repo-demo",
            graph_id="GRAPH-001",
            query_terms=["NullPointerException"],
            node_filters=[],
            edge_filters=[],
            max_depth=3,
            contract_version="1.0.0",
        )

    assert "trace_id" in str(excinfo.value)


def test_unsupported_major_contract_version_raises_contract_error():
    with pytest.raises(ContractViolation) as excinfo:
        ensure_supported_contract_version("2.0.0", trace_id="TRACE-001")

    error = excinfo.value.error
    assert error.error_code == "UNSUPPORTED_CONTRACT_VERSION"
    assert error.trace_id == "TRACE-001"
    assert error.recoverable is False


def test_missing_trace_id_raises_trace_required_contract_error():
    with pytest.raises(ContractViolation) as excinfo:
        ensure_trace_id("")

    error = excinfo.value.error
    assert error.error_code == "TRACE_REQUIRED"
    assert error.missing_fields == ["trace_id"]
    assert error.recoverable is True


def test_rca_report_rejects_root_cause_without_evidence():
    with pytest.raises(ValidationError) as excinfo:
        RCAReport(
            report_id="RCA-001",
            trace_id="TRACE-001",
            repo_id="repo-demo",
            contract_version="1.0.0",
            hypotheses=[
                EvidenceBackedItem(
                    summary="datasetId is missing",
                    evidence_refs=[evidence_ref()],
                )
            ],
            selected_root_cause=EvidenceBackedItem(
                summary="service dereferences a missing datasetId",
                evidence_refs=[],
            ),
            evidence_chain=[evidence_ref("EV-002")],
            affected_path=["DatasetController.getVersion", "DatasetService.getVersion"],
            suggested_fix=[
                EvidenceBackedItem(
                    summary="Add request validation for datasetId",
                    evidence_refs=[evidence_ref("EV-003")],
                )
            ],
            migration_impact=EvidenceBackedItem(
                summary="Medium risk around DatasetMapper and dataset_version",
                evidence_refs=[evidence_ref("EV-004")],
            ),
            migration_checklist=["Add null datasetId regression test"],
            confidence=0.82,
        )

    assert "at least 1 item" in str(excinfo.value)


def test_alert_event_accepts_contract_version_and_required_fields():
    alert = AlertEvent(
        alert_id="ALERT-001",
        repo_id="repo-demo",
        raw_log="NullPointerException at DatasetService.getVersion",
        stack_trace="DatasetService.java:42",
        error_description="NPE while reading dataset version",
        occurred_at=datetime(2026, 6, 11, tzinfo=UTC),
        source="demo",
        contract_version="1.0.0",
    )

    assert alert.contract_version == "1.0.0"


def test_alert_event_accepts_optional_graph_id():
    alert = AlertEvent(
        alert_id="ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        raw_log="java.lang.NullPointerException at DatasetService.getVersion",
        stack_trace="DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version",
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        source="demo-cli",
        contract_version="1.0.0",
    )

    assert alert.graph_id == "GRAPH-repo-demo"


def test_incident_query_accepts_missing_graph_id_for_compatibility():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    assert query.graph_id is None


def test_incident_query_accepts_optional_graph_id():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    assert query.graph_id == "GRAPH-repo-demo"


def test_graph_snapshot_accepts_structure1_versions():
    snapshot = GraphSnapshot(
        graph_id="GRAPH-1",
        repo_id="repo-1",
        nodes=[],
        edges=[],
        evidence_refs=[],
        generated_at=datetime.now(UTC),
        parser_version="gitnexus_cli+structure1_sql_v1",
        semantic_enrichment_version=None,
        metadata={"structure": "code_knowledge_core"},
    )

    assert snapshot.parser_version == "gitnexus_cli+structure1_sql_v1"
    assert snapshot.semantic_enrichment_version is None
    assert snapshot.metadata["structure"] == "code_knowledge_core"
