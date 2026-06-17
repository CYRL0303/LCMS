from pathlib import Path

from legacy_pilot.code_knowledge_core.extractors.java_exception import (
    extract_java_exception_graph,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"


def test_extracts_exception_nodes_and_throw_edges():
    payload = extract_java_exception_graph(
        FIXTURE_ROOT,
        repo_id="repo-prod",
        graph_id="GRAPH-prod",
    )

    node_ids = {node["id"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["relationships"]}

    assert (
        "Exception:src/main/java/com/legacy/DatasetNotFoundException.java:"
        "DatasetNotFoundException"
        in node_ids
    )
    assert "THROWS_EXCEPTION" in edge_types
    assert "HANDLES_EXCEPTION" in edge_types
