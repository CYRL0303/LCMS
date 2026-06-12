from datetime import UTC, datetime

import pytest

from legacy_pilot.contracts.errors import ContractViolation
from legacy_pilot.contracts.models import AlertEvent, EvidenceBackedItem, GraphQuery, RCAReport
from legacy_pilot.middleware.router import MiddlewareRouter


def alert_event() -> AlertEvent:
    return AlertEvent(
        alert_id="ALERT-001",
        repo_id="repo-demo",
        raw_log=(
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        stack_trace="DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version",
        occurred_at=datetime(2026, 6, 11, tzinfo=UTC),
        source="demo-cli",
        contract_version="1.0.0",
    )


def test_submit_alert_returns_traceable_incident_query():
    router = MiddlewareRouter()

    query = router.submit_alert(alert_event())

    assert query.trace_id == "TRACE-ALERT-001"
    assert query.repo_id == "repo-demo"
    assert query.error_type == "NullPointerException"
    assert "DatasetService.getVersion" in query.query_terms
    assert query.contract_version == "1.0.0"


def test_mock_pipeline_produces_evidence_backed_rca_and_incident_record():
    router = MiddlewareRouter()

    query = router.submit_alert(alert_event())
    bundle = router.build_evidence_bundle(query)
    report = router.generate_rca(bundle)
    reviewed = router.review_rca(report)
    record = router.save_incident(
        reviewed_report=reviewed,
        user_confirmation=True,
        fix_outcome="fixed by adding validation",
        retention_policy="demo-30-days",
        contract_version="1.0.0",
    )

    assert bundle.trace_id == query.trace_id
    assert bundle.code_evidence
    assert bundle.log_evidence
    assert report.trace_id == query.trace_id
    assert report.selected_root_cause.evidence_refs
    assert reviewed.final_confidence == report.confidence
    assert record.confirmed_by_user is True
    assert record.evidence_refs
    assert record.dedup_key == "repo-demo:NullPointerException:DatasetService.getVersion"


def test_find_similar_incidents_returns_confirmed_mock_match():
    router = MiddlewareRouter()
    query = router.submit_alert(alert_event())

    matches = router.find_similar_incidents(query)

    assert matches[0].incident_id == "INC-003"
    assert matches[0].confirmed_by_user is True
    assert matches[0].evidence_refs


def test_query_graph_returns_traceable_graph_context():
    router = MiddlewareRouter()
    query = GraphQuery(
        repo_id="repo-demo",
        graph_id="GRAPH-DEMO",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        node_filters=["Method"],
        edge_filters=["CALLS"],
        max_depth=3,
        trace_id="TRACE-ALERT-001",
        contract_version="1.0.0",
    )

    context = router.query_graph(query)

    assert context.trace_id == query.trace_id
    assert context.matched_nodes
    assert context.matched_edges
    assert context.graph_paths == [
        [
            "DatasetController.getVersion",
            "DatasetService.getVersion",
            "DatasetMapper.selectVersionById",
            "dataset_version",
        ]
    ]
    assert context.evidence_refs
    assert context.confidence == 0.88


def test_review_rca_rejects_report_without_root_cause_evidence():
    router = MiddlewareRouter()
    valid_report = router.generate_rca(router.build_evidence_bundle(router.submit_alert(alert_event())))
    invalid_root_cause = EvidenceBackedItem.model_construct(
        summary="unsupported conclusion",
        evidence_refs=[],
        confidence=0.2,
    )
    invalid_report = RCAReport.model_construct(
        **{**valid_report.model_dump(), "selected_root_cause": invalid_root_cause}
    )

    with pytest.raises(ContractViolation) as excinfo:
        router.review_rca(invalid_report)

    assert excinfo.value.error.error_code == "EVIDENCE_REQUIRED"
    assert excinfo.value.error.recoverable is True


def test_save_incident_requires_user_confirmation():
    router = MiddlewareRouter()
    report = router.generate_rca(router.build_evidence_bundle(router.submit_alert(alert_event())))
    reviewed = router.review_rca(report)

    with pytest.raises(ContractViolation) as excinfo:
        router.save_incident(
            reviewed_report=reviewed,
            user_confirmation=False,
            fix_outcome="not confirmed",
            retention_policy="demo-30-days",
            contract_version="1.0.0",
        )

    assert excinfo.value.error.error_code == "USER_CONFIRMATION_REQUIRED"
