from pathlib import Path

from legacy_pilot.code_knowledge_core.extractors.java_config import (
    extract_java_config_graph,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"


def test_extracts_application_yml_config_nodes():
    payload = extract_java_config_graph(
        FIXTURE_ROOT,
        repo_id="repo-prod",
        graph_id="GRAPH-prod",
    )

    names = {node["name"] for node in payload["nodes"]}

    assert "spring.datasource.url" in names
    assert "legacy.dataset.cache-enabled" in names
    assert all(node["source_type"] == "config" for node in payload["nodes"])
