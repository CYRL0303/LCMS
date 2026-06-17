from pathlib import Path

from legacy_pilot.code_knowledge_core.extractors.java_sql import (
    extract_mybatis_sql_graph,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"


def test_extracts_mapper_sql_and_table_edges():
    payload = extract_mybatis_sql_graph(
        FIXTURE_ROOT,
        repo_id="repo-prod",
        graph_id="GRAPH-prod",
    )

    node_ids = {node["id"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["relationships"]}

    assert (
        "MapperXml:src/main/resources/mapper/DatasetMapper.xml:selectVersionById"
        in node_ids
    )
    assert "Table:dataset_version" in node_ids
    assert "EXECUTES_SQL" in edge_types
    assert "READS_TABLE" in edge_types


def test_extracts_mapper_method_node_and_no_dangling_edges():
    payload = extract_mybatis_sql_graph(
        FIXTURE_ROOT,
        repo_id="repo-prod",
        graph_id="GRAPH-prod",
    )

    node_ids = {node["id"] for node in payload["nodes"]}
    relationship_endpoints = {
        endpoint
        for relationship in payload["relationships"]
        for endpoint in (relationship["source_id"], relationship["target_id"])
    }

    assert (
        "Method:src/main/java/com/legacy/DatasetMapper.java:"
        "DatasetMapper.selectVersionById#1"
        in node_ids
    )
    assert relationship_endpoints.issubset(node_ids)
