import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.adapter import GitNexusCliCodeKnowledgeCoreAdapter
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"
JAVA_ROOT = FIXTURE_ROOT / "src" / "main" / "java" / "com" / "legacy"
RUN_ENV = "LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION"
GITNEXUS_ENV_KEYS = ("GITNEXUS_BIN", "GITNEXUS_REPO_ROOT")
pytestmark = pytest.mark.structure1_production
ENDPOINT_ID = "Route:/api/dataset/version"
CONTROLLER_ID = (
    "Method:src/main/java/com/legacy/DatasetController.java:"
    "DatasetController.getVersion#1"
)
SERVICE_ID = (
    "Method:src/main/java/com/legacy/DatasetService.java:"
    "DatasetService.getVersion#1"
)
MAPPER_ID = (
    "Method:src/main/java/com/legacy/DatasetMapper.java:"
    "DatasetMapper.selectVersionById#1"
)
SQL_ID = "MapperXml:src/main/resources/mapper/DatasetMapper.xml:selectVersionById"
TABLE_ID = "Table:dataset_version"
CONFIG_ID = (
    "Config:src/main/resources/application.yml:legacy.dataset.cache-enabled"
)
EXCEPTION_ID = (
    "Exception:src/main/java/com/legacy/DatasetNotFoundException.java:"
    "DatasetNotFoundException"
)


def test_production_fixture_contains_structure1_inputs():
    assert (JAVA_ROOT / "DatasetController.java").exists()
    assert (JAVA_ROOT / "DatasetService.java").exists()
    assert (JAVA_ROOT / "DatasetMapper.java").exists()
    assert (JAVA_ROOT / "DatasetNotFoundException.java").exists()
    assert (JAVA_ROOT / "GlobalExceptionHandler.java").exists()
    assert (
        FIXTURE_ROOT / "src" / "main" / "resources" / "mapper" / "DatasetMapper.xml"
    ).exists()
    assert (FIXTURE_ROOT / "src" / "main" / "resources" / "application.yml").exists()


def test_query_graph_returns_local_enriched_contexts_after_indexing_production_fixture():
    client = FakeProductionGitNexusClient()
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(client=client)
    request = _production_fixture_request()

    adapter.index_repo(request)

    table_context, config_context, exception_context = _query_production_contexts(
        adapter,
        request,
    )

    assert client.query_called is False
    _assert_production_query_contexts(table_context, config_context, exception_context)


def test_query_graph_by_endpoint_returns_full_structure_chain_after_indexing_fixture():
    client = FakeProductionGitNexusClient()
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(client=client)
    request = _production_fixture_request()

    adapter.index_repo(request)

    context = adapter.query_graph(
        GraphQuery(
            repo_id=request.repo_id,
            graph_id=f"GRAPH-{request.repo_id}",
            query_terms=["/api/dataset/version"],
            node_filters=["API Endpoint"],
            edge_filters=[],
            max_depth=6,
            trace_id="TRACE-ENDPOINT",
            contract_version="1.0.0",
        )
    )

    assert client.query_called is False
    assert {
        (edge.source_node_id, edge.type, edge.target_node_id)
        for edge in context.matched_edges
    } >= {
        (ENDPOINT_ID, "MAPS_TO_ENDPOINT", CONTROLLER_ID),
        (CONTROLLER_ID, "CALLS", SERVICE_ID),
        (SERVICE_ID, "CALLS", MAPPER_ID),
        (MAPPER_ID, "EXECUTES_SQL", SQL_ID),
        (SQL_ID, "READS_TABLE", TABLE_ID),
    }
    assert context.graph_paths
    assert any(
        path[0] == "/api/dataset/version" and path[-1].endswith("dataset_version")
        for path in context.graph_paths
    )


def test_production_fixture_has_no_semantic_nodes_by_default():
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeProductionGitNexusClient(),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    snapshot = adapter.index_repo(_production_fixture_request())

    assert "Function Semantic Summary" not in {node.type for node in snapshot.nodes}
    assert "HAS_SEMANTIC_ACTION" not in {edge.type for edge in snapshot.edges}
    assert snapshot.semantic_enrichment_version is None


def test_production_fixture_has_qwen_semantic_nodes_when_explicitly_enabled():
    from legacy_pilot.code_knowledge_core.semantic import QwenApiSemanticEnricher

    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": "Summarizes production fixture method semantics."
                    }
                }
            ]
        }

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeProductionGitNexusClient(),
        semantic_enricher=QwenApiSemanticEnricher(
            api_key="test-key",
            confidence_cap=0.55,
            http_post=fake_post,
        ),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    snapshot = adapter.index_repo(_production_fixture_request())

    semantic_nodes = [
        node for node in snapshot.nodes if node.type == "Function Semantic Summary"
    ]
    semantic_edges = [
        edge for edge in snapshot.edges if edge.type == "HAS_SEMANTIC_ACTION"
    ]
    semantic_evidence = [
        evidence
        for evidence in snapshot.evidence_refs
        if evidence.source_type == "llm_semantic_summary"
    ]

    assert semantic_nodes
    assert semantic_edges
    assert snapshot.semantic_enrichment_version == "qwen_api:qwen-plus"
    assert snapshot.metadata["semantic_enrichment"] == {
        "backend": "qwen_api",
        "version": "qwen_api:qwen-plus",
        "verification_status": "pending",
        "confidence_cap": 0.55,
    }
    assert all(
        node.metadata["gitnexus"]["properties"]["verification_status"] == "pending"
        for node in semantic_nodes
    )
    assert semantic_evidence
    assert all(evidence.extraction_method == "llm" for evidence in semantic_evidence)
    assert all(evidence.confidence <= 0.55 for evidence in semantic_evidence)


@pytest.mark.gitnexus_integration
@pytest.mark.slow
def test_real_gitnexus_index_supports_local_enriched_production_queries():
    adapter = _gitnexus_adapter_or_skip()
    request = _production_fixture_request()

    _call_gitnexus(lambda: adapter.index_repo(request))

    table_context, config_context, exception_context = _call_gitnexus(
        lambda: _query_production_contexts(adapter, request)
    )

    _assert_production_query_contexts(table_context, config_context, exception_context)


def _query_production_contexts(
    adapter: GitNexusCliCodeKnowledgeCoreAdapter,
    request: RepoIndexRequest,
):
    table_context = adapter.query_graph(
        GraphQuery(
            repo_id=request.repo_id,
            graph_id=f"GRAPH-{request.repo_id}",
            query_terms=["dataset_version"],
            node_filters=["Table"],
            edge_filters=["READS_TABLE"],
            max_depth=5,
            trace_id="TRACE-TABLE",
            contract_version="1.0.0",
        )
    )
    config_context = adapter.query_graph(
        GraphQuery(
            repo_id=request.repo_id,
            graph_id=f"GRAPH-{request.repo_id}",
            query_terms=["legacy.dataset.cache-enabled"],
            node_filters=["Config"],
            edge_filters=[],
            max_depth=3,
            trace_id="TRACE-CONFIG",
            contract_version="1.0.0",
        )
    )
    exception_context = adapter.query_graph(
        GraphQuery(
            repo_id=request.repo_id,
            graph_id=f"GRAPH-{request.repo_id}",
            query_terms=["DatasetNotFoundException"],
            node_filters=["Exception"],
            edge_filters=[],
            max_depth=5,
            trace_id="TRACE-EXCEPTION",
            contract_version="1.0.0",
        )
    )
    return table_context, config_context, exception_context


def _assert_production_query_contexts(
    table_context,
    config_context,
    exception_context,
) -> None:
    assert {
        (edge.source_node_id, edge.type, edge.target_node_id)
        for edge in table_context.matched_edges
    } >= {
        (CONTROLLER_ID, "CALLS", SERVICE_ID),
        (SERVICE_ID, "CALLS", MAPPER_ID),
        (MAPPER_ID, "EXECUTES_SQL", SQL_ID),
        (SQL_ID, "READS_TABLE", TABLE_ID),
    }
    assert any(node.node_id == TABLE_ID for node in table_context.matched_nodes)
    assert table_context.graph_paths

    assert [node.node_id for node in config_context.matched_nodes] == [CONFIG_ID]
    assert config_context.graph_paths
    assert config_context.graph_paths[0][0].endswith("legacy.dataset.cache-enabled")

    assert any(node.node_id == EXCEPTION_ID for node in exception_context.matched_nodes)
    assert {
        (edge.source_node_id, edge.type, edge.target_node_id)
        for edge in exception_context.matched_edges
    } >= {
        (SERVICE_ID, "THROWS_EXCEPTION", EXCEPTION_ID),
    }


@pytest.mark.gitnexus_integration
@pytest.mark.slow
def test_index_repo_includes_sql_config_and_exception_nodes():
    adapter = _gitnexus_adapter_or_skip()
    snapshot = _index_production_fixture(adapter)

    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    source_types = {evidence.source_type for evidence in snapshot.evidence_refs}

    assert snapshot.parser_version == "gitnexus_cli+structure1_sql_config_exception_v1"
    assert snapshot.semantic_enrichment_version is None
    assert snapshot.metadata["enrichment_sources"] == [
        "mybatis_sql",
        "java_config",
        "java_exception",
    ]
    assert "SQL" in node_types
    assert "Table" in node_types
    assert "Config" in node_types
    assert "Exception" in node_types
    assert "EXECUTES_SQL" in edge_types
    assert "READS_TABLE" in edge_types
    assert "THROWS_EXCEPTION" in edge_types
    assert {"code", "sql", "config"}.issubset(source_types)
    assert all(edge.evidence_refs for edge in snapshot.edges)
    assert all(evidence.source_type for edge in snapshot.edges for evidence in edge.evidence_refs)
    evidence_ids = [evidence.evidence_id for evidence in snapshot.evidence_refs]
    assert len(evidence_ids) == len(set(evidence_ids))

    node_ids = {node.node_id for node in snapshot.nodes}
    edge_pairs = {
        (edge.source_node_id, edge.type, edge.target_node_id)
        for edge in snapshot.edges
    }
    edges_by_pair = {
        (edge.source_node_id, edge.type, edge.target_node_id): edge
        for edge in snapshot.edges
    }
    assert {
        ENDPOINT_ID,
        CONTROLLER_ID,
        SERVICE_ID,
        MAPPER_ID,
        SQL_ID,
        TABLE_ID,
        EXCEPTION_ID,
    }.issubset(node_ids)
    assert (ENDPOINT_ID, "MAPS_TO_ENDPOINT", CONTROLLER_ID) in edge_pairs
    assert (CONTROLLER_ID, "CALLS", SERVICE_ID) in edge_pairs
    assert (SERVICE_ID, "CALLS", MAPPER_ID) in edge_pairs
    assert (MAPPER_ID, "EXECUTES_SQL", SQL_ID) in edge_pairs
    assert (SQL_ID, "READS_TABLE", TABLE_ID) in edge_pairs
    assert (SERVICE_ID, "THROWS_EXCEPTION", EXCEPTION_ID) in edge_pairs

    expected_edge_source_types = {
        (CONTROLLER_ID, "CALLS", SERVICE_ID): {"code"},
        (SERVICE_ID, "CALLS", MAPPER_ID): {"code"},
        (MAPPER_ID, "EXECUTES_SQL", SQL_ID): {"sql"},
        (SQL_ID, "READS_TABLE", TABLE_ID): {"sql"},
        (SERVICE_ID, "THROWS_EXCEPTION", EXCEPTION_ID): {"code"},
    }
    for edge_pair, expected_source_types in expected_edge_source_types.items():
        edge = edges_by_pair[edge_pair]
        assert {evidence.source_type for evidence in edge.evidence_refs} == expected_source_types
    assert {
        evidence.source_type
        for evidence in edges_by_pair[
            (ENDPOINT_ID, "MAPS_TO_ENDPOINT", CONTROLLER_ID)
        ].evidence_refs
    } == {"code"}


def _gitnexus_adapter_or_skip() -> GitNexusCliCodeKnowledgeCoreAdapter:
    reason = _gitnexus_integration_skip_reason()
    if reason:
        pytest.skip(reason)
    client = GitNexusCliClient(
        gitnexus_bin=os.environ["GITNEXUS_BIN"],
        repo_root=os.environ["GITNEXUS_REPO_ROOT"],
    )
    return GitNexusCliCodeKnowledgeCoreAdapter(client=client)


class FakeProductionGitNexusClient:
    def __init__(self):
        self.query_called = False

    def index_repo(self, request: RepoIndexRequest) -> dict:
        return {
            "repo_id": request.repo_id,
            "graph_id": f"GRAPH-{request.repo_id}",
            "trace_id": f"TRACE-INDEX-{request.repo_id}",
            "nodes": [
                _endpoint_node(),
                _method_node(
                    CONTROLLER_ID,
                    "getVersion",
                    "src/main/java/com/legacy/DatasetController.java",
                    "DatasetController.getVersion",
                ),
                _method_node(
                    SERVICE_ID,
                    "getVersion",
                    "src/main/java/com/legacy/DatasetService.java",
                    "DatasetService.getVersion",
                ),
                _method_node(
                    MAPPER_ID,
                    "selectVersionById",
                    "src/main/java/com/legacy/DatasetMapper.java",
                    "DatasetMapper.selectVersionById",
                ),
            ],
            "relationships": [
                _code_edge(ENDPOINT_ID, "MAPS_TO_ENDPOINT", CONTROLLER_ID),
                _code_edge(CONTROLLER_ID, "CALLS", SERVICE_ID),
                _code_edge(SERVICE_ID, "CALLS", MAPPER_ID),
            ],
        }

    def query_graph(self, query: GraphQuery) -> dict:
        self.query_called = True
        return {
            "graph_id": query.graph_id,
            "nodes": [],
            "relationships": [],
            "paths": [],
            "not_found": True,
        }


def _endpoint_node() -> dict:
    return {
        "id": ENDPOINT_ID,
        "type": "API Endpoint",
        "name": "/api/dataset/version",
        "filePath": "src/main/java/com/legacy/DatasetController.java",
        "startLine": 10,
        "endLine": 16,
        "source_type": "code",
        "extraction_method": "java_parser",
        "confidence": 0.9,
        "properties": {"qualifiedName": "/api/dataset/version"},
    }


def _method_node(
    node_id: str,
    name: str,
    file_path: str,
    qualified_name: str,
) -> dict:
    return {
        "id": node_id,
        "type": "Method",
        "name": name,
        "filePath": file_path,
        "startLine": 1,
        "endLine": 10,
        "source_type": "code",
        "extraction_method": "java_parser",
        "confidence": 0.9,
        "properties": {"qualifiedName": qualified_name},
    }


def _code_edge(source_id: str, edge_type: str, target_id: str) -> dict:
    return {
        "id": f"{edge_type}:{source_id}->{target_id}",
        "source_id": source_id,
        "target_id": target_id,
        "type": edge_type,
        "filePath": "src/main/java/com/legacy/DatasetService.java",
        "startLine": 1,
        "endLine": 10,
        "source_type": "code",
        "extraction_method": "java_parser",
        "confidence": 0.86,
    }


def _gitnexus_integration_skip_reason() -> str | None:
    missing_keys = [key for key in GITNEXUS_ENV_KEYS if not os.getenv(key)]
    if os.getenv(RUN_ENV) != "1":
        missing_keys.insert(0, RUN_ENV)
    if not missing_keys:
        return None
    return (
        "GitNexus integration is opt-in; set "
        f"{', '.join(missing_keys)} to run against the local GitNexus runtime."
    )


def _index_production_fixture(adapter: GitNexusCliCodeKnowledgeCoreAdapter):
    return _call_gitnexus(lambda: adapter.index_repo(_production_fixture_request()))


def _production_fixture_request() -> RepoIndexRequest:
    return RepoIndexRequest(
        repo_id=_repo_id("repo-java-spring-production-demo", FIXTURE_ROOT),
        repo_uri=FIXTURE_ROOT.resolve().as_uri(),
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )


def _repo_id(base_name: str, fixture_root: Path) -> str:
    path_hash = sha256(str(fixture_root.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{base_name}-{path_hash}"


def _call_gitnexus(operation):
    try:
        return operation()
    except CodeKnowledgeCoreError as exc:
        pytest.fail(
            "GitNexus integration failed without mock fallback: "
            f"{exc.message}; diagnostics={exc.diagnostics}"
        )
