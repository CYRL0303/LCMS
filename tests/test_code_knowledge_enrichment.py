from datetime import UTC, datetime
from typing import Any

from legacy_pilot.code_knowledge_core.adapter import GitNexusCliCodeKnowledgeCoreAdapter
from legacy_pilot.code_knowledge_core.enrichment import merge_graph_payloads
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


def test_enrichment_combines_gitnexus_and_extractor_payloads():
    base_payload = {
        "repo_id": "repo-1",
        "graph_id": "GRAPH-repo-1",
        "trace_id": "TRACE-INDEX-repo-1",
        "nodes": [{"id": "Method:DatasetService.getVersion", "type": "Method"}],
        "relationships": [],
    }
    sql_payload = {
        "nodes": [{"id": "SQL:DatasetMapper.selectVersionById", "type": "SQL"}],
        "relationships": [
            {
                "id": "REL-1",
                "source_id": "Method:DatasetService.getVersion",
                "target_id": "SQL:DatasetMapper.selectVersionById",
                "type": "EXECUTES_SQL",
            }
        ],
    }

    enriched = merge_graph_payloads(base_payload, [sql_payload])

    assert [node["id"] for node in enriched["nodes"]] == [
        "Method:DatasetService.getVersion",
        "SQL:DatasetMapper.selectVersionById",
    ]
    assert enriched["relationships"][0]["type"] == "EXECUTES_SQL"


def test_index_repo_applies_configured_enrichers_before_mapping():
    client = _FakeGitNexusClient()
    calls = []

    def sql_enricher(request: RepoIndexRequest) -> dict[str, Any]:
        calls.append(request.repo_id)
        return _sql_payload()

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=client,
        now=lambda: datetime(2026, 6, 16, tzinfo=UTC),
        index_enrichers=[sql_enricher],
    )

    snapshot = adapter.index_repo(_repo_index_request())

    node_ids = {node.node_id for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    source_types = {evidence.source_type for evidence in snapshot.evidence_refs}

    assert calls == ["repo-1"]
    assert "SQL:DatasetMapper.selectVersionById" in node_ids
    assert "EXECUTES_SQL" in edge_types
    assert "sql" in source_types


def test_query_graph_applies_configured_enrichers_before_mapping():
    client = _FakeGitNexusClient()
    calls = []

    def sql_enricher(query: GraphQuery) -> dict[str, Any]:
        calls.append(query.trace_id)
        return _sql_payload()

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=client,
        now=lambda: datetime(2026, 6, 16, tzinfo=UTC),
        query_enrichers=[sql_enricher],
    )

    context = adapter.query_graph(_graph_query())

    node_ids = {node.node_id for node in context.matched_nodes}
    edge_types = {edge.type for edge in context.matched_edges}

    assert calls == ["TRACE-Q-1"]
    assert "SQL:DatasetMapper.selectVersionById" in node_ids
    assert "EXECUTES_SQL" in edge_types


class _FakeGitNexusClient:
    def index_repo(self, request: RepoIndexRequest) -> dict[str, Any]:
        return {
            "repo_id": request.repo_id,
            "graph_id": "GRAPH-repo-1",
            "trace_id": f"TRACE-INDEX-{request.repo_id}",
            "nodes": [_method_node()],
            "relationships": [],
        }

    def query_graph(self, query: GraphQuery) -> dict[str, Any]:
        return {
            "graph_id": query.graph_id,
            "nodes": [_method_node()],
            "relationships": [],
            "paths": [["Method:DatasetService.getVersion"]],
            "not_found": False,
        }


def _repo_index_request() -> RepoIndexRequest:
    return RepoIndexRequest(
        repo_id="repo-1",
        repo_uri="file:///repo-1",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )


def _graph_query() -> GraphQuery:
    return GraphQuery(
        repo_id="repo-1",
        graph_id="GRAPH-repo-1",
        query_terms=["DatasetService.getVersion"],
        max_depth=3,
        trace_id="TRACE-Q-1",
        contract_version="1.0.0",
    )


def _method_node() -> dict[str, Any]:
    return {
        "id": "Method:DatasetService.getVersion",
        "type": "Method",
        "name": "getVersion",
        "filePath": "src/main/java/com/legacy/DatasetService.java",
        "startLine": 10,
        "endLine": 20,
    }


def _sql_payload() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "SQL:DatasetMapper.selectVersionById",
                "type": "SQL",
                "name": "selectVersionById",
                "filePath": "src/main/resources/mapper/DatasetMapper.xml",
                "startLine": 5,
                "endLine": 9,
                "source_type": "sql",
                "extraction_method": "regex",
            }
        ],
        "relationships": [
            {
                "id": "REL-METHOD-SQL",
                "source_id": "Method:DatasetService.getVersion",
                "target_id": "SQL:DatasetMapper.selectVersionById",
                "type": "EXECUTES_SQL",
                "source_type": "sql",
                "extraction_method": "regex",
                "confidence": 0.84,
            }
        ],
    }
