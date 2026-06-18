from datetime import UTC, datetime
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
    GitNexusCliCodeKnowledgeCoreAdapter,
    MockCodeKnowledgeCoreAdapter,
    UnsupportedCodeKnowledgeCoreBackendAdapter,
    create_code_knowledge_core_adapter,
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


PRODUCTION_FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "java_spring_production_demo"
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


class FakeGitNexusClient:
    def __init__(self):
        self.index_called = False
        self.query_called = False

    def index_repo(self, request: RepoIndexRequest) -> dict:
        self.index_called = True
        return {
            "repo_id": request.repo_id,
            "graph_id": "GRAPH-GN",
            "trace_id": f"TRACE-INDEX-{request.repo_id}",
            "nodes": [
                {
                    "id": "GN-NODE-SERVICE",
                    "type": "Method",
                    "name": "getVersion",
                    "properties": {
                        "qualifiedName": "DatasetService.getVersion",
                        "filePath": "src/main/java/DatasetService.java",
                        "startLine": 40,
                        "endLine": 45,
                    },
                }
            ],
            "relationships": [],
        }

    def query_graph(self, query: GraphQuery) -> dict:
        self.query_called = True
        return {
            "graph_id": query.graph_id,
            "nodes": [
                {
                    "id": "GN-NODE-SERVICE",
                    "type": "Method",
                    "name": "getVersion",
                    "properties": {
                        "qualifiedName": "DatasetService.getVersion",
                        "filePath": "src/main/java/DatasetService.java",
                        "startLine": 40,
                        "endLine": 45,
                    },
                }
            ],
            "relationships": [],
            "paths": [["GN-NODE-SERVICE"]],
            "not_found": False,
        }


class TestGitNexusCliAdapter:
    def test_index_repo_maps_client_payload_to_graph_snapshot(self):
        client = FakeGitNexusClient()
        adapter = GitNexusCliCodeKnowledgeCoreAdapter(
            client=client,
            now=lambda: datetime(2026, 6, 15, tzinfo=UTC),
        )
        request = RepoIndexRequest(
            repo_id="repo-real",
            repo_uri="file:///repo-real",
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        snapshot = adapter.index_repo(request)

        assert client.index_called is True
        assert isinstance(snapshot, GraphSnapshot)
        assert snapshot.graph_id == "GRAPH-GN"
        assert snapshot.repo_id == "repo-real"
        assert snapshot.nodes[0].qualified_name == "DatasetService.getVersion"
        assert snapshot.evidence_refs

    def test_query_graph_maps_client_payload_to_graph_context(self):
        client = FakeGitNexusClient()
        adapter = GitNexusCliCodeKnowledgeCoreAdapter(
            client=client,
            now=lambda: datetime(2026, 6, 15, tzinfo=UTC),
        )
        query = GraphQuery(
            repo_id="repo-real",
            graph_id="GRAPH-GN",
            query_terms=["DatasetService.getVersion"],
            max_depth=3,
            trace_id="TRACE-Q-REAL",
            contract_version="1.0.0",
        )

        context = adapter.query_graph(query)

        assert client.query_called is True
        assert isinstance(context, GraphContext)
        assert context.trace_id == "TRACE-Q-REAL"
        assert context.matched_nodes[0].qualified_name == "DatasetService.getVersion"
        assert context.graph_paths == [["DatasetService.getVersion"]]

    def test_index_repo_wraps_enricher_failures_as_indexing_error(self):
        def malformed_config_enricher(request: RepoIndexRequest) -> dict:
            raise ValueError("malformed YAML")

        adapter = GitNexusCliCodeKnowledgeCoreAdapter(
            client=FakeGitNexusClient(),
            index_enrichers=[malformed_config_enricher],
            now=lambda: datetime(2026, 6, 15, tzinfo=UTC),
        )
        request = RepoIndexRequest(
            repo_id="repo-real",
            repo_uri="file:///repo-real",
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        with pytest.raises(IndexingError) as excinfo:
            adapter.index_repo(request)

        error = excinfo.value
        assert error.message == "Structure 1 enrichment failed while indexing repo."
        assert error.recoverable is True
        assert error.diagnostics == {
            "enricher": "malformed_config_enricher",
            "error_type": "ValueError",
        }

    def test_query_graph_wraps_enricher_failures_as_query_error(self):
        def unreadable_query_enricher(query: GraphQuery) -> dict:
            raise PermissionError("repo cache denied")

        adapter = GitNexusCliCodeKnowledgeCoreAdapter(
            client=FakeGitNexusClient(),
            query_enrichers=[unreadable_query_enricher],
            now=lambda: datetime(2026, 6, 15, tzinfo=UTC),
        )
        query = GraphQuery(
            repo_id="repo-real",
            graph_id="GRAPH-GN",
            query_terms=["DatasetService.getVersion"],
            max_depth=3,
            trace_id="TRACE-Q-REAL",
            contract_version="1.0.0",
        )

        with pytest.raises(QueryError) as excinfo:
            adapter.query_graph(query)

        error = excinfo.value
        assert error.message == "Structure 1 enrichment failed while querying graph."
        assert error.recoverable is True
        assert error.diagnostics == {
            "enricher": "unreadable_query_enricher",
            "error_type": "PermissionError",
        }


def test_gitnexus_adapter_does_not_add_semantic_nodes_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    assert "Function Semantic Summary" not in {node.type for node in snapshot.nodes}
    assert "HAS_SEMANTIC_ACTION" not in {edge.type for edge in snapshot.edges}
    assert snapshot.semantic_enrichment_version is None


def test_gitnexus_adapter_adds_mock_semantic_nodes_when_enabled():
    from legacy_pilot.code_knowledge_core.semantic import MockSemanticEnricher

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        semantic_enricher=MockSemanticEnricher(confidence_cap=0.42),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    semantic_evidence = [
        evidence
        for evidence in snapshot.evidence_refs
        if evidence.source_type == "llm_semantic_summary"
    ]

    assert "Function Semantic Summary" in node_types
    assert "HAS_SEMANTIC_ACTION" in edge_types
    assert snapshot.semantic_enrichment_version == "semantic_mock_v1"
    assert snapshot.metadata["semantic_enrichment"] == {
        "backend": "mock",
        "version": "semantic_mock_v1",
        "verification_status": "pending",
        "confidence_cap": 0.42,
    }
    assert semantic_evidence
    assert all(evidence.extraction_method == "llm" for evidence in semantic_evidence)
    assert all(evidence.confidence <= 0.42 for evidence in semantic_evidence)


def test_gitnexus_adapter_wraps_semantic_failures_as_indexing_error():
    class RaisingSemanticEnricher:
        semantic_enrichment_version = "semantic_raising_v1"
        backend_name = "raising"
        confidence_cap = 0.7

        def enrich(self, nodes: list[dict]) -> dict:
            raise RuntimeError("semantic backend failed")

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        semantic_enricher=RaisingSemanticEnricher(),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    with pytest.raises(IndexingError) as excinfo:
        adapter.index_repo(request)

    assert (
        excinfo.value.message
        == "Structure 1 semantic enrichment failed while indexing repo."
    )
    assert excinfo.value.recoverable is True
    assert excinfo.value.diagnostics == {
        "semantic_backend": "raising",
        "error_type": "RuntimeError",
    }


def test_gitnexus_adapter_qwen_env_backend_maps_semantic_graph(monkeypatch):
    from legacy_pilot.code_knowledge_core import semantic as semantic_module

    requests = []

    def fake_http_post_json(url: str, *, headers: dict[str, str], body: dict) -> dict:
        requests.append({"url": url, "headers": headers, "body": body})
        return {
            "choices": [
                {"message": {"content": "Qwen summary from adapter path."}}
            ]
        }

    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "qwen_api")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP", "0.31")
    monkeypatch.setattr(semantic_module, "_http_post_json", fake_http_post_json)
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    semantic_nodes = [
        node for node in snapshot.nodes if node.type == "Function Semantic Summary"
    ]
    semantic_evidence = [
        evidence
        for evidence in snapshot.evidence_refs
        if evidence.source_type == "llm_semantic_summary"
    ]
    assert requests
    assert requests[0]["headers"]["Authorization"] == "Bearer test-key"
    assert semantic_nodes
    assert semantic_nodes[0].metadata["gitnexus"]["properties"]["summary"] == (
        "Qwen summary from adapter path."
    )
    assert snapshot.semantic_enrichment_version == "qwen_api:qwen-plus"
    assert snapshot.metadata["semantic_enrichment"] == {
        "backend": "qwen_api",
        "version": "qwen_api:qwen-plus",
        "verification_status": "pending",
        "confidence_cap": 0.31,
    }
    assert semantic_evidence
    assert all(evidence.extraction_method == "llm" for evidence in semantic_evidence)
    assert all(evidence.confidence <= 0.31 for evidence in semantic_evidence)


class TestBackendFactory:
    def test_missing_backend_selects_mock_adapter(self, monkeypatch):
        monkeypatch.delenv("LEGACY_PILOT_CODE_CORE_BACKEND", raising=False)

        adapter = create_code_knowledge_core_adapter()

        assert isinstance(adapter, MockCodeKnowledgeCoreAdapter)

    def test_mock_backend_selects_mock_adapter(self, monkeypatch):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "mock")

        adapter = create_code_knowledge_core_adapter()

        assert isinstance(adapter, MockCodeKnowledgeCoreAdapter)

    def test_gitnexus_cli_backend_selects_real_adapter_without_running_gitnexus(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "gitnexus_cli")

        adapter = create_code_knowledge_core_adapter()

        assert isinstance(adapter, GitNexusCliCodeKnowledgeCoreAdapter)

    def test_gitnexus_cli_backend_uses_default_structure1_enrichers(self):
        adapter = create_code_knowledge_core_adapter(
            backend="gitnexus_cli",
            gitnexus_client=FakeGitNexusClient(),
            now=lambda: datetime(2026, 6, 16, tzinfo=UTC),
        )
        request = RepoIndexRequest(
            repo_id="repo-prod",
            repo_uri=PRODUCTION_FIXTURE_ROOT.resolve().as_uri(),
            language_hint="java",
            parser_profile="spring-boot",
            contract_version="1.0.0",
        )

        snapshot = adapter.index_repo(request)

        node_types = {node.type for node in snapshot.nodes}
        edge_types = {edge.type for edge in snapshot.edges}
        source_types = {evidence.source_type for evidence in snapshot.evidence_refs}

        assert snapshot.parser_version == "gitnexus_cli+structure1_sql_config_exception_v1"
        assert snapshot.semantic_enrichment_version is None
        assert snapshot.metadata["code_knowledge_core_backend"] == "gitnexus_cli"
        assert snapshot.metadata["graph_source"] == "gitnexus_cypher_markdown"
        assert snapshot.metadata["enrichment_sources"] == [
            "mybatis_sql",
            "java_config",
            "java_exception",
        ]
        assert {"SQL", "Table", "Config", "Exception"}.issubset(node_types)
        assert {"EXECUTES_SQL", "READS_TABLE", "THROWS_EXCEPTION"}.issubset(edge_types)
        assert {"code", "sql", "config"}.issubset(source_types)

    def test_unsupported_backend_selects_recoverable_failing_adapter(self, monkeypatch):
        monkeypatch.setenv("LEGACY_PILOT_CODE_CORE_BACKEND", "bad-backend")

        adapter = create_code_knowledge_core_adapter()

        assert isinstance(adapter, UnsupportedCodeKnowledgeCoreBackendAdapter)
