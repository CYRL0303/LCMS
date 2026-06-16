from datetime import UTC, datetime
from hashlib import sha256

from legacy_pilot.code_knowledge_core.gitnexus_mapper import (
    map_gitnexus_edge,
    map_gitnexus_node,
    map_index_payload,
    map_query_payload,
)
from legacy_pilot.contracts.models import GraphQuery


NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def fixed_now() -> datetime:
    return NOW


def evidence_id(
    *,
    trace_id: str,
    source_id: str | None,
    file_path: str | None,
    start_line: int | None,
    end_line: int | None,
) -> str:
    identity = "|".join(
        [
            trace_id,
            source_id or "",
            file_path or "",
            str(start_line or ""),
            str(end_line or ""),
        ]
    )
    return f"EV-GN-{sha256(identity.encode('utf-8')).hexdigest()[:12]}"


def graph_query(trace_id: str = "TRACE-Q-001") -> GraphQuery:
    return GraphQuery(
        repo_id="repo-demo",
        graph_id="GRAPH-GN",
        query_terms=["DatasetService.getVersion"],
        max_depth=3,
        trace_id=trace_id,
        contract_version="1.0.0",
    )


def service_node_payload(**overrides):
    payload = {
        "id": "GN-NODE-SERVICE",
        "type": "Method",
        "name": "getVersion",
        "properties": {
            "qualifiedName": "com.legacy.DatasetService.getVersion",
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 40,
            "endLine": 45,
            "excerpt": "String getVersion() { return mapper.selectVersionById(id); }",
        },
    }
    payload.update(overrides)
    return payload


def mapper_node_payload(**overrides):
    payload = {
        "id": "GN-NODE-MAPPER",
        "type": "Mapper",
        "name": "selectVersionById",
        "properties": {
            "filePath": "src/main/java/com/legacy/DatasetMapper.java",
            "startLine": 10,
            "endLine": 12,
        },
    }
    payload.update(overrides)
    return payload


def relationship_payload(**overrides):
    payload = {
        "id": "GN-REL-CALLS",
        "type": "CALLS",
        "source_id": "GN-NODE-SERVICE",
        "target_id": "GN-NODE-MAPPER",
        "confidence": 1.25,
        "reason": "service delegates to mapper",
        "evidence_signals": ["method_invocation", "same_method_name"],
        "properties": {
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 42,
            "endLine": 42,
            "excerpt": "mapper.selectVersionById(id)",
        },
    }
    payload.update(overrides)
    return payload


def test_graph_node_with_qualified_name_maps_to_node_qualified_name():
    node = map_gitnexus_node(
        service_node_payload(),
        graph_id="GRAPH-GN",
        repo_id="repo-demo",
        trace_id="TRACE-INDEX-repo-demo",
        now=fixed_now,
    )

    assert node.node_id == "GN-NODE-SERVICE"
    assert node.qualified_name == "com.legacy.DatasetService.getVersion"
    assert node.metadata["gitnexus"]["id"] == "GN-NODE-SERVICE"
    assert node.evidence_refs[0].created_at == NOW


def test_graph_node_without_qualified_name_maps_to_file_path_and_name():
    node = map_gitnexus_node(
        mapper_node_payload(),
        graph_id="GRAPH-GN",
        repo_id="repo-demo",
        trace_id="TRACE-INDEX-repo-demo",
        now=fixed_now,
    )

    assert (
        node.qualified_name
        == "src/main/java/com/legacy/DatasetMapper.java::selectVersionById"
    )


def test_node_evidence_uses_created_at_from_injected_clock_and_deterministic_id():
    node = map_gitnexus_node(
        service_node_payload(),
        graph_id="GRAPH-GN",
        repo_id="repo-demo",
        trace_id="TRACE-INDEX-repo-demo",
        now=fixed_now,
    )
    evidence = node.evidence_refs[0]

    assert evidence.created_at == NOW
    assert evidence.evidence_id == evidence_id(
        trace_id="TRACE-INDEX-repo-demo",
        source_id="GN-NODE-SERVICE",
        file_path="src/main/java/com/legacy/DatasetService.java",
        start_line=40,
        end_line=45,
    )


def test_relationship_evidence_maps_to_edge_gitnexus_metadata():
    nodes_by_id = {
        "GN-NODE-SERVICE": map_gitnexus_node(
            service_node_payload(),
            graph_id="GRAPH-GN",
            repo_id="repo-demo",
            trace_id="TRACE-Q-001",
            now=fixed_now,
        ),
        "GN-NODE-MAPPER": map_gitnexus_node(
            mapper_node_payload(),
            graph_id="GRAPH-GN",
            repo_id="repo-demo",
            trace_id="TRACE-Q-001",
            now=fixed_now,
        ),
    }

    edge = map_gitnexus_edge(
        relationship_payload(),
        graph_id="GRAPH-GN",
        trace_id="TRACE-Q-001",
        nodes_by_id=nodes_by_id,
        now=fixed_now,
    )

    assert edge is not None
    assert edge.metadata["gitnexus"] == {
        "reason": "service delegates to mapper",
        "evidence_signals": ["method_invocation", "same_method_name"],
        "source_relationship_type": "CALLS",
    }
    assert edge.evidence_refs[0].source_type == "code"
    assert edge.evidence_refs[0].source_id == "GN-REL-CALLS"
    assert edge.confidence == 1.0


def test_edge_with_no_source_node_location_uses_target_node_location():
    source = map_gitnexus_node(
        {
            "id": "GN-NODE-SOURCE",
            "type": "Class",
            "name": "DatasetService",
            "properties": {},
        },
        graph_id="GRAPH-GN",
        repo_id="repo-demo",
        trace_id="TRACE-Q-001",
        now=fixed_now,
    )
    target = map_gitnexus_node(
        mapper_node_payload(id="GN-NODE-TARGET"),
        graph_id="GRAPH-GN",
        repo_id="repo-demo",
        trace_id="TRACE-Q-001",
        now=fixed_now,
    )

    edge = map_gitnexus_edge(
        {
            "id": "GN-REL-HANDLES",
            "type": "HANDLES_ROUTE",
            "source_id": "GN-NODE-SOURCE",
            "target_id": "GN-NODE-TARGET",
            "properties": {},
        },
        graph_id="GRAPH-GN",
        trace_id="TRACE-Q-001",
        nodes_by_id={
            source.node_id: source,
            target.node_id: target,
        },
        now=fixed_now,
    )

    assert edge is not None
    assert edge.evidence_refs[0].file_path == "src/main/java/com/legacy/DatasetMapper.java"
    assert edge.evidence_refs[0].source_type == "code"


def test_edge_with_no_source_or_target_location_receives_low_confidence_code_evidence():
    nodes_by_id = {
        "A": map_gitnexus_node(
            {"id": "A", "type": "Class", "name": "A", "properties": {}},
            graph_id="GRAPH-GN",
            repo_id="repo-demo",
            trace_id="TRACE-Q-001",
            now=fixed_now,
        ),
        "B": map_gitnexus_node(
            {"id": "B", "type": "Class", "name": "B", "properties": {}},
            graph_id="GRAPH-GN",
            repo_id="repo-demo",
            trace_id="TRACE-Q-001",
            now=fixed_now,
        ),
    }

    edge = map_gitnexus_edge(
        {
            "id": "GN-REL-IMPORTS",
            "type": "IMPORTS",
            "source_id": "A",
            "target_id": "B",
            "confidence": 0.7,
            "properties": {},
        },
        graph_id="GRAPH-GN",
        trace_id="TRACE-Q-001",
        nodes_by_id=nodes_by_id,
        now=fixed_now,
    )

    assert edge is not None
    assert edge.evidence_refs[0].source_type == "code"
    assert edge.evidence_refs[0].file_path is None
    assert edge.evidence_refs[0].confidence == 0.2


def test_graph_snapshot_evidence_refs_deduplicate_by_evidence_id():
    payload = {
        "graph_id": "GRAPH-GN",
        "repo_id": "repo-demo",
        "trace_id": "TRACE-INDEX-repo-demo",
        "nodes": [service_node_payload()],
        "relationships": [
            relationship_payload(
                source_id="GN-NODE-SERVICE",
                target_id="GN-NODE-SERVICE",
                properties={
                    "filePath": "src/main/java/com/legacy/DatasetService.java",
                    "startLine": 40,
                    "endLine": 45,
                },
            )
        ],
    }

    snapshot = map_index_payload(payload, now=fixed_now)

    all_evidence_ids = [ref.evidence_id for ref in snapshot.evidence_refs]
    assert all_evidence_ids == list(dict.fromkeys(all_evidence_ids))


def test_graph_context_trace_id_equals_input_query_trace_id():
    context = map_query_payload(
        {
            "nodes": [service_node_payload(), mapper_node_payload()],
            "relationships": [relationship_payload(confidence=0.8)],
            "paths": [["GN-NODE-SERVICE", "GN-NODE-MAPPER"]],
        },
        query=graph_query(trace_id="TRACE-QUERY-A"),
        now=fixed_now,
    )

    assert context.trace_id == "TRACE-QUERY-A"
    assert context.graph_paths == [
        [
            "com.legacy.DatasetService.getVersion",
            "src/main/java/com/legacy/DatasetMapper.java::selectVersionById",
        ]
    ]


def test_graph_context_confidence_uses_edge_average_and_max_edge_evidence_confidence():
    context = map_query_payload(
        {
            "nodes": [service_node_payload(), mapper_node_payload()],
            "relationships": [
                relationship_payload(id="R1", confidence=0.9),
                relationship_payload(
                    id="R2",
                    confidence=0.5,
                    properties={
                        "filePath": "src/main/java/com/legacy/DatasetService.java",
                        "startLine": 44,
                        "endLine": 44,
                    },
                ),
            ],
        },
        query=graph_query(),
        now=fixed_now,
    )

    assert context.confidence == 0.7


def test_not_found_query_payload_returns_empty_graph_context_with_zero_confidence():
    context = map_query_payload(
        {"not_found": True, "nodes": [service_node_payload()]},
        query=graph_query(trace_id="TRACE-NOT-FOUND"),
        now=fixed_now,
    )

    assert context.trace_id == "TRACE-NOT-FOUND"
    assert context.matched_nodes == []
    assert context.matched_edges == []
    assert context.graph_paths == []
    assert context.evidence_refs == []
    assert context.confidence == 0.0
