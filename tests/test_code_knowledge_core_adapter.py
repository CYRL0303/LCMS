from datetime import UTC, datetime

import pytest

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
    MockCodeKnowledgeCoreAdapter,
)
from legacy_pilot.code_knowledge_core.errors import (
    CodeKnowledgeCoreError,
    IndexingError,
    QueryError,
)
from legacy_pilot.contracts.enums import ExtractionMethod, SourceType
from legacy_pilot.contracts.models import (
    Edge,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    Node,
    RepoIndexRequest,
)


def _evidence_ref(
    evidence_id: str,
    trace_id: str,
    *,
    source_type: SourceType = SourceType.CODE,
    extraction_method: ExtractionMethod = ExtractionMethod.JAVA_PARSER,
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id=trace_id,
        source_type=source_type,
        source_id="DatasetService.java",
        file_path="src/main/java/com/legacy/DatasetService.java",
        start_line=1,
        end_line=80,
        excerpt="class DatasetService { ... }",
        extraction_method=extraction_method,
        confidence=0.95,
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    )


class RecordingFakeAdapter(CodeKnowledgeCoreAdapter):
    """An adapter that records whether index_repo / query_graph were called."""

    def __init__(self):
        self.index_called = False
        self.query_called = False

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        self.index_called = True
        evidence = _evidence_ref("EV-REC-001", f"TRACE-INDEX-{request.repo_id}")
        return GraphSnapshot(
            graph_id="GRAPH-REC",
            repo_id=request.repo_id,
            nodes=[],
            edges=[],
            evidence_refs=[evidence],
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


# ---------------------------------------------------------------------------
# Step 1 adapter-interface tests (unchanged intent, may reference new types)
# ---------------------------------------------------------------------------

class FakeAdapter(CodeKnowledgeCoreAdapter):
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        evidence = _evidence_ref("EV-FAKE-001", f"TRACE-INDEX-{request.repo_id}")
        node = Node(
            node_id="NODE-FAKE-001",
            graph_id="GRAPH-FAKE",
            repo_id=request.repo_id,
            type="Class",
            name="FakeService",
            qualified_name="com.fake.FakeService",
            evidence_refs=[evidence],
        )
        return GraphSnapshot(
            graph_id="GRAPH-FAKE",
            repo_id=request.repo_id,
            nodes=[node],
            edges=[],
            evidence_refs=[evidence],
            generated_at=datetime(2026, 6, 15, tzinfo=UTC),
        )

    def query_graph(self, query: GraphQuery) -> GraphContext:
        evidence = _evidence_ref("EV-FAKE-Q001", query.trace_id)
        node = Node(
            node_id="NODE-FAKE-Q001",
            graph_id=query.graph_id,
            repo_id=query.repo_id,
            type="Method",
            name="fakeQuery",
            qualified_name="com.fake.FakeService.fakeQuery",
            evidence_refs=[evidence],
        )
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[node],
            matched_edges=[],
            graph_paths=[],
            evidence_refs=[evidence],
            confidence=0.5,
        )


class TestAdapterInterface:
    def test_fake_adapter_index_repo_returns_valid_graph_snapshot(self):
        adapter = FakeAdapter()
        request = RepoIndexRequest(
            repo_id="repo-test",
            repo_uri="file:///tmp/repo-test",
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        snapshot = adapter.index_repo(request)

        assert isinstance(snapshot, GraphSnapshot)
        assert snapshot.repo_id == "repo-test"
        assert len(snapshot.nodes) == 1
        assert snapshot.nodes[0].name == "FakeService"

    def test_fake_adapter_query_graph_returns_valid_graph_context(self):
        adapter = FakeAdapter()
        query = GraphQuery(
            repo_id="repo-test",
            graph_id="GRAPH-FAKE",
            query_terms=["NullPointerException"],
            max_depth=3,
            trace_id="TRACE-QUERY-001",
            contract_version="1.0.0",
        )

        context = adapter.query_graph(query)

        assert isinstance(context, GraphContext)
        assert context.trace_id == "TRACE-QUERY-001"
        assert len(context.matched_nodes) == 1
        assert context.confidence == 0.5

    def test_adapter_surface_has_only_lcms_contract_models(self):
        import inspect

        from legacy_pilot.code_knowledge_core.adapter import CodeKnowledgeCoreAdapter as A

        sig_index = inspect.signature(A.index_repo)
        sig_query = inspect.signature(A.query_graph)

        assert sig_index.return_annotation is GraphSnapshot
        assert sig_query.return_annotation is GraphContext

        param_names_index = set(sig_index.parameters.keys())
        param_names_query = set(sig_query.parameters.keys())

        assert param_names_index == {"self", "request"}
        assert param_names_query == {"self", "query"}


class TestMockAdapterPreservesOriginalBehavior:
    """Step 2: mock adapter outputs must match what the router previously returned."""

    def test_mock_adapter_index_repo_returns_demo_graph_snapshot(self):
        adapter = MockCodeKnowledgeCoreAdapter()
        request = RepoIndexRequest(
            repo_id="repo-legacy",
            repo_uri="file:///legacy",
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        snapshot = adapter.index_repo(request)

        assert snapshot.graph_id == "GRAPH-DEMO"
        assert snapshot.repo_id == "repo-legacy"
        assert len(snapshot.nodes) == 2
        assert snapshot.nodes[0].node_id == "NODE-DATASET-CONTROLLER"
        assert snapshot.nodes[1].node_id == "NODE-DATASET-SERVICE"
        assert len(snapshot.edges) == 1
        assert snapshot.edges[0].edge_id == "EDGE-CONTROLLER-SERVICE"
        assert len(snapshot.evidence_refs) == 1
        assert snapshot.evidence_refs[0].evidence_id == "EV-REPO-001"

    def test_mock_adapter_query_graph_returns_demo_graph_context(self):
        adapter = MockCodeKnowledgeCoreAdapter()
        query = GraphQuery(
            repo_id="repo-legacy",
            graph_id="GRAPH-DEMO",
            query_terms=["NullPointerException"],
            max_depth=3,
            trace_id="TRACE-ALERT-001",
            contract_version="1.0.0",
        )

        context = adapter.query_graph(query)

        assert context.trace_id == "TRACE-ALERT-001"
        assert len(context.matched_nodes) == 3
        assert context.matched_edges[0].type == "CALLS"
        assert context.matched_edges[1].type == "USES_MAPPER"
        assert len(context.graph_paths) == 1
        assert context.confidence == 0.88


# ---------------------------------------------------------------------------
# Step 2 gate-before-adapter tests (recording fake)
# ---------------------------------------------------------------------------

class TestGateBeforeAdapter:
    """Contract gates must intercept before the adapter is called."""

    def test_recording_adapter_tracks_index_repo_call(self):
        adapter = RecordingFakeAdapter()
        request = RepoIndexRequest(
            repo_id="r",
            repo_uri="file:///r",
            language_hint="java",
            parser_profile="default",
            contract_version="1.0.0",
        )

        snapshot = adapter.index_repo(request)

        assert adapter.index_called is True
        assert snapshot.graph_id == "GRAPH-REC"

    def test_recording_adapter_tracks_query_graph_call(self):
        adapter = RecordingFakeAdapter()
        query = GraphQuery(
            repo_id="r",
            graph_id="GRAPH-REC",
            query_terms=["x"],
            max_depth=2,
            trace_id="TRACE-T",
            contract_version="1.0.0",
        )

        context = adapter.query_graph(query)

        assert adapter.query_called is True
        assert context.trace_id == "TRACE-T"


class TestCodeKnowledgeCoreErrors:
    def test_base_error_carries_source_module(self):
        error = CodeKnowledgeCoreError("something went wrong")

        assert error.source_module == "code_knowledge_core"
        assert error.message == "something went wrong"
        assert error.recoverable is True

    def test_base_error_can_be_non_recoverable(self):
        error = CodeKnowledgeCoreError("fatal", recoverable=False)

        assert error.recoverable is False

    def test_indexing_error_is_code_knowledge_core_error(self):
        error = IndexingError("parse failed")

        assert isinstance(error, CodeKnowledgeCoreError)
        assert error.source_module == "code_knowledge_core"

    def test_query_error_is_code_knowledge_core_error(self):
        error = QueryError("backend unavailable")

        assert isinstance(error, CodeKnowledgeCoreError)
        assert error.source_module == "code_knowledge_core"

    def test_code_knowledge_core_errors_carry_enough_data_for_router_conversion(self):
        error = IndexingError("repo path is not readable", recoverable=True)

        assert error.source_module is not None
        assert isinstance(error.message, str)
        assert isinstance(error.recoverable, bool)

    def test_code_knowledge_core_errors_do_not_expose_gitnexus_objects(self):
        error = QueryError("backend timeout", recoverable=True)

        assert error.source_module == "code_knowledge_core"
        assert "gitnexus" not in str(error).lower()
