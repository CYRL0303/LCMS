from datetime import UTC, datetime

import pytest

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
    GitNexusCliCodeKnowledgeCoreAdapter,
    MockCodeKnowledgeCoreAdapter,
)
from legacy_pilot.code_knowledge_core.errors import IndexingError, QueryError
from legacy_pilot.contracts.errors import ContractViolation
from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceBackedItem,
    EvidenceBundle,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentQuery,
    RCAReport,
    RepoIndexRequest,
)
from legacy_pilot.incident_context_builder.adapter import (
    IncidentContextBuilderAdapter,
    MockIncidentContextBuilderAdapter,
)
from legacy_pilot.middleware.router import MiddlewareRouter


class RecordingFakeAdapter(CodeKnowledgeCoreAdapter):
    """An adapter that records whether index_repo / query_graph were called."""

    def __init__(self):
        self.index_called = False
        self.query_called = False

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        self.index_called = True
        return GraphSnapshot(
            graph_id="GRAPH-REC",
            repo_id=request.repo_id,
            nodes=[],
            edges=[],
            evidence_refs=[],
            generated_at=datetime(2026, 6, 15, tzinfo=UTC),
        )

    def query_graph(self, query: GraphQuery) -> GraphContext:
        self.query_called = True
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[],
            matched_edges=[],
            graph_paths=[],
            evidence_refs=[],
            confidence=0.0,
        )


class FailingFakeAdapter(CodeKnowledgeCoreAdapter):
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        raise IndexingError("repo path is not readable", recoverable=True)

    def query_graph(self, query: GraphQuery) -> GraphContext:
        raise QueryError("graph backend unavailable", recoverable=True)


class DiagnosticFailingFakeAdapter(CodeKnowledgeCoreAdapter):
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        raise IndexingError(
            "GitNexus CLI failed while indexing repo.",
            recoverable=True,
            diagnostics={"stderr": "Traceback: internal secret", "returncode": "17"},
        )

    def query_graph(self, query: GraphQuery) -> GraphContext:
        raise QueryError(
            "GitNexus CLI failed while querying graph.",
            recoverable=True,
            diagnostics={"stderr": "Traceback: internal secret", "returncode": "17"},
        )


class RecordingIncidentContextAdapter(IncidentContextBuilderAdapter):
    def __init__(self):
        self.submit_called = False
        self.bundle_called = False

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        self.submit_called = True
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=alert.graph_id,
            error_type="InjectedError",
            suspected_location="Injected.location",
            query_terms=["InjectedError", "Injected.location"],
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        self.bundle_called = True
        return EvidenceBundle(
            trace_id=query.trace_id,
            repo_id=query.repo_id,
            contract_version=query.contract_version,
            alert_summary="InjectedError near Injected.location",
            incident_query=query,
        )


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
    assert bundle.contract_version == query.contract_version
    assert bundle.code_evidence
    assert bundle.log_evidence
    assert report.trace_id == query.trace_id
    assert report.contract_version == bundle.contract_version
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


def test_router_delegates_structure2_calls_to_incident_context_adapter():
    adapter = RecordingIncidentContextAdapter()
    router = MiddlewareRouter(incident_context_builder_adapter=adapter)

    query = router.submit_alert(alert_event())
    bundle = router.build_evidence_bundle(query)

    assert adapter.submit_called is True
    assert adapter.bundle_called is True
    assert query.error_type == "InjectedError"
    assert bundle.alert_summary == "InjectedError near Injected.location"


def test_default_router_uses_mock_incident_context_adapter():
    router = MiddlewareRouter()

    assert isinstance(
        router._incident_context_builder_adapter,
        MockIncidentContextBuilderAdapter,
    )


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


def test_generate_rca_rejects_unsupported_bundle_contract_version():
    router = MiddlewareRouter()
    bundle = router.build_evidence_bundle(router.submit_alert(alert_event()))
    unsupported_bundle = bundle.model_copy(update={"contract_version": "2.0.0"})

    with pytest.raises(ContractViolation) as excinfo:
        router.generate_rca(unsupported_bundle)

    assert excinfo.value.error.error_code == "UNSUPPORTED_CONTRACT_VERSION"
    assert excinfo.value.error.trace_id == bundle.trace_id


def test_review_rca_rejects_unsupported_report_contract_version():
    router = MiddlewareRouter()
    report = router.generate_rca(router.build_evidence_bundle(router.submit_alert(alert_event())))
    unsupported_report = report.model_copy(update={"contract_version": "2.0.0"})

    with pytest.raises(ContractViolation) as excinfo:
        router.review_rca(unsupported_report)

    assert excinfo.value.error.error_code == "UNSUPPORTED_CONTRACT_VERSION"
    assert excinfo.value.error.trace_id == report.trace_id


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


# ---------------------------------------------------------------------------
# Step 2: default mock preservation + gate-before-adapter
# ---------------------------------------------------------------------------


class TestDefaultRouterPreservesMockBehavior:
    def test_default_router_uses_mock_adapter_when_backend_is_missing(self, monkeypatch):
        monkeypatch.delenv("LEGACY_PILOT_CODE_CORE_BACKEND", raising=False)

        router = MiddlewareRouter()

        assert isinstance(router._code_knowledge_core_adapter, MockCodeKnowledgeCoreAdapter)

    def test_default_router_index_repo_returns_same_mock_snapshot(self):
        router = MiddlewareRouter()
        request = RepoIndexRequest(
            repo_id="repo-legacy",
            repo_uri="file:///legacy",
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        snapshot = router.index_repo(request)

        assert snapshot.graph_id == "GRAPH-DEMO"
        assert snapshot.repo_id == "repo-legacy"
        assert snapshot.nodes[0].node_id == "NODE-DATASET-CONTROLLER"
        assert snapshot.nodes[1].node_id == "NODE-DATASET-SERVICE"
        assert len(snapshot.edges) == 1

    def test_default_router_query_graph_returns_same_mock_context(self):
        router = MiddlewareRouter()
        query = GraphQuery(
            repo_id="repo-legacy",
            graph_id="GRAPH-DEMO",
            query_terms=["NullPointerException"],
            max_depth=3,
            trace_id="TRACE-ALERT-001",
            contract_version="1.0.0",
        )

        context = router.query_graph(query)

        assert context.trace_id == "TRACE-ALERT-001"
        assert len(context.matched_nodes) == 3
        assert context.confidence == 0.88


class TestGateInterceptsBeforeAdapter:
    def test_unsupported_contract_version_blocks_index_repo_before_adapter(self):
        adapter = RecordingFakeAdapter()
        router = MiddlewareRouter(code_knowledge_core_adapter=adapter)
        request = RepoIndexRequest(
            repo_id="r",
            repo_uri="file:///r",
            language_hint="java",
            parser_profile="default",
            contract_version="2.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.index_repo(request)

        assert excinfo.value.error.error_code == "UNSUPPORTED_CONTRACT_VERSION"
        assert adapter.index_called is False

    def test_missing_trace_id_blocks_query_graph_before_adapter(self):
        adapter = RecordingFakeAdapter()
        router = MiddlewareRouter(code_knowledge_core_adapter=adapter)
        query = GraphQuery(
            repo_id="r",
            graph_id="GRAPH-REC",
            query_terms=["x"],
            max_depth=2,
            trace_id="",
            contract_version="1.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.query_graph(query)

        assert excinfo.value.error.error_code == "TRACE_REQUIRED"
        assert adapter.query_called is False

    def test_unsupported_contract_version_blocks_query_graph_before_adapter(self):
        adapter = RecordingFakeAdapter()
        router = MiddlewareRouter(code_knowledge_core_adapter=adapter)
        query = GraphQuery(
            repo_id="r",
            graph_id="GRAPH-REC",
            query_terms=["x"],
            max_depth=2,
            trace_id="TRACE-T",
            contract_version="2.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.query_graph(query)

        assert excinfo.value.error.error_code == "UNSUPPORTED_CONTRACT_VERSION"
        assert adapter.query_called is False

    def test_unsupported_backend_error_is_returned_only_after_contract_gate(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "bad-backend")
        router = MiddlewareRouter()
        request = RepoIndexRequest(
            repo_id="r",
            repo_uri="file:///r",
            language_hint="java",
            parser_profile="default",
            contract_version="2.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.index_repo(request)

        assert excinfo.value.error.error_code == "UNSUPPORTED_CONTRACT_VERSION"


class TestBackendSelection:
    def test_router_with_custom_adapter_delegates_structure_1_calls(self):
        adapter = RecordingFakeAdapter()
        router = MiddlewareRouter(code_knowledge_core_adapter=adapter)
        request = RepoIndexRequest(
            repo_id="repo-custom",
            repo_uri="file:///repo-custom",
            language_hint="java",
            parser_profile="default",
            contract_version="1.0.0",
        )
        query = GraphQuery(
            repo_id="repo-custom",
            graph_id="GRAPH-REC",
            query_terms=["x"],
            max_depth=2,
            trace_id="TRACE-CUSTOM",
            contract_version="1.0.0",
        )

        snapshot = router.index_repo(request)
        context = router.query_graph(query)

        assert adapter.index_called is True
        assert adapter.query_called is True
        assert snapshot.graph_id == "GRAPH-REC"
        assert context.trace_id == "TRACE-CUSTOM"

    def test_router_selects_gitnexus_cli_adapter_without_running_gitnexus(self, monkeypatch):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "gitnexus_cli")

        router = MiddlewareRouter()

        assert isinstance(
            router._code_knowledge_core_adapter,
            GitNexusCliCodeKnowledgeCoreAdapter,
        )

    def test_unsupported_backend_returns_recoverable_code_core_error(self, monkeypatch):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "bad-backend")
        router = MiddlewareRouter()
        request = RepoIndexRequest(
            repo_id="repo-bad",
            repo_uri="file:///repo-bad",
            language_hint="java",
            parser_profile="default",
            contract_version="1.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.index_repo(request)

        error = excinfo.value.error
        assert error.trace_id == "TRACE-INDEX-repo-bad"
        assert error.source_module == "code_knowledge_core"
        assert error.recoverable is True
        assert error.message == "Unsupported Code Knowledge Core backend: bad-backend"


class TestCodeKnowledgeCoreErrorConversion:
    def test_indexing_error_becomes_contract_violation(self):
        router = MiddlewareRouter(code_knowledge_core_adapter=FailingFakeAdapter())
        request = RepoIndexRequest(
            repo_id="repo-fail",
            repo_uri="file:///missing",
            language_hint="java",
            parser_profile="default",
            contract_version="1.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.index_repo(request)

        error = excinfo.value.error
        assert error.error_code == "VALIDATION_ERROR"
        assert error.trace_id == "TRACE-INDEX-repo-fail"
        assert error.message == "repo path is not readable"
        assert error.source_module == "code_knowledge_core"
        assert error.recoverable is True

    def test_query_error_becomes_contract_violation(self):
        router = MiddlewareRouter(code_knowledge_core_adapter=FailingFakeAdapter())
        query = GraphQuery(
            repo_id="repo-fail",
            graph_id="GRAPH-FAIL",
            query_terms=["DatasetService.getVersion"],
            max_depth=2,
            trace_id="TRACE-Q-FAIL",
            contract_version="1.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.query_graph(query)

        error = excinfo.value.error
        assert error.error_code == "VALIDATION_ERROR"
        assert error.trace_id == "TRACE-Q-FAIL"
        assert error.message == "graph backend unavailable"
        assert error.source_module == "code_knowledge_core"
        assert error.recoverable is True

    def test_gitnexus_diagnostics_are_not_exposed_as_contract_message_text(self):
        router = MiddlewareRouter(
            code_knowledge_core_adapter=DiagnosticFailingFakeAdapter()
        )
        request = RepoIndexRequest(
            repo_id="repo-fail",
            repo_uri="file:///missing",
            language_hint="java",
            parser_profile="default",
            contract_version="1.0.0",
        )

        with pytest.raises(ContractViolation) as excinfo:
            router.index_repo(request)

        error = excinfo.value.error
        assert error.message == "GitNexus CLI failed while indexing repo."
        assert "Traceback" not in error.message
        assert "internal secret" not in error.message
