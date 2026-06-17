import os
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.adapter import GitNexusCliCodeKnowledgeCoreAdapter
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import RepoIndexRequest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"
JAVA_ROOT = FIXTURE_ROOT / "src" / "main" / "java" / "com" / "legacy"
RUN_ENV = "LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION"
GITNEXUS_ENV_KEYS = ("GITNEXUS_BIN", "GITNEXUS_REPO_ROOT")


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


@pytest.mark.gitnexus_integration
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

    node_ids = {node.node_id for node in snapshot.nodes}
    edge_pairs = {
        (edge.source_node_id, edge.type, edge.target_node_id)
        for edge in snapshot.edges
    }
    edges_by_pair = {
        (edge.source_node_id, edge.type, edge.target_node_id): edge
        for edge in snapshot.edges
    }
    controller_id = (
        "Method:src/main/java/com/legacy/DatasetController.java:"
        "DatasetController.getVersion#1"
    )
    service_id = (
        "Method:src/main/java/com/legacy/DatasetService.java:"
        "DatasetService.getVersion#1"
    )
    mapper_id = (
        "Method:src/main/java/com/legacy/DatasetMapper.java:"
        "DatasetMapper.selectVersionById#1"
    )
    sql_id = "MapperXml:src/main/resources/mapper/DatasetMapper.xml:selectVersionById"
    table_id = "Table:dataset_version"
    exception_id = (
        "Exception:src/main/java/com/legacy/DatasetNotFoundException.java:"
        "DatasetNotFoundException"
    )

    assert {controller_id, service_id, mapper_id, sql_id, table_id, exception_id}.issubset(
        node_ids
    )
    assert (controller_id, "CALLS", service_id) in edge_pairs
    assert (service_id, "CALLS", mapper_id) in edge_pairs
    assert (mapper_id, "EXECUTES_SQL", sql_id) in edge_pairs
    assert (sql_id, "READS_TABLE", table_id) in edge_pairs
    assert (service_id, "THROWS_EXCEPTION", exception_id) in edge_pairs

    expected_edge_source_types = {
        (controller_id, "CALLS", service_id): {"code"},
        (service_id, "CALLS", mapper_id): {"code"},
        (mapper_id, "EXECUTES_SQL", sql_id): {"sql"},
        (sql_id, "READS_TABLE", table_id): {"sql"},
        (service_id, "THROWS_EXCEPTION", exception_id): {"code"},
    }
    for edge_pair, expected_source_types in expected_edge_source_types.items():
        edge = edges_by_pair[edge_pair]
        assert {evidence.source_type for evidence in edge.evidence_refs} == expected_source_types


def _gitnexus_adapter_or_skip() -> GitNexusCliCodeKnowledgeCoreAdapter:
    reason = _gitnexus_integration_skip_reason()
    if reason:
        pytest.skip(reason)
    client = GitNexusCliClient(
        gitnexus_bin=os.environ["GITNEXUS_BIN"],
        repo_root=os.environ["GITNEXUS_REPO_ROOT"],
    )
    return GitNexusCliCodeKnowledgeCoreAdapter(client=client)


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
    request = RepoIndexRequest(
        repo_id="repo-java-spring-production-demo",
        repo_uri=FIXTURE_ROOT.resolve().as_uri(),
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )
    return _call_gitnexus(lambda: adapter.index_repo(request))


def _call_gitnexus(operation):
    try:
        return operation()
    except CodeKnowledgeCoreError as exc:
        pytest.fail(
            "GitNexus integration failed without mock fallback: "
            f"{exc.message}; diagnostics={exc.diagnostics}"
        )
