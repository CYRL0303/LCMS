import os
from hashlib import sha256
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.adapter import GitNexusCliCodeKnowledgeCoreAdapter
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import GraphContext, RepoIndexRequest, GraphQuery


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_demo"
JAVA_ROOT = FIXTURE_ROOT / "src" / "main" / "java" / "com" / "legacy"
RUN_ENV = "LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION"
GITNEXUS_ENV_KEYS = ("GITNEXUS_BIN", "GITNEXUS_REPO_ROOT")


def test_java_spring_fixture_contains_controller_service_mapper_contract():
    controller = JAVA_ROOT / "DatasetController.java"
    service = JAVA_ROOT / "DatasetService.java"
    mapper = JAVA_ROOT / "DatasetMapper.java"

    assert controller.exists()
    assert service.exists()
    assert mapper.exists()
    assert not list(FIXTURE_ROOT.rglob("*.xml"))

    controller_text = controller.read_text(encoding="utf-8")
    service_text = service.read_text(encoding="utf-8")
    mapper_text = mapper.read_text(encoding="utf-8")

    assert '@GetMapping("/api/dataset/version")' in controller_text
    assert "datasetService.getVersion" in controller_text
    assert "datasetMapper.selectVersionById" in service_text
    assert "interface DatasetMapper" in mapper_text
    assert "String selectVersionById" in mapper_text


def test_gitnexus_integration_skip_reason_is_clear_when_env_absent(monkeypatch):
    monkeypatch.delenv(RUN_ENV, raising=False)
    monkeypatch.delenv("GITNEXUS_BIN", raising=False)
    monkeypatch.delenv("GITNEXUS_REPO_ROOT", raising=False)

    reason = _gitnexus_integration_skip_reason()

    assert RUN_ENV in reason
    assert "GITNEXUS_BIN" in reason
    assert "GITNEXUS_REPO_ROOT" in reason
    assert "set" in reason.lower()


@pytest.mark.gitnexus_integration
def test_index_repo_against_java_spring_fixture_returns_graph_snapshot():
    adapter = _gitnexus_adapter_or_skip()
    request = _repo_index_request()

    snapshot = _index_fixture(adapter)

    assert snapshot.repo_id == request.repo_id
    assert snapshot.nodes
    assert all(edge.evidence_refs for edge in snapshot.edges)


@pytest.mark.gitnexus_integration
def test_query_graph_by_service_method_returns_traceable_graph_context():
    adapter = _gitnexus_adapter_or_skip()
    snapshot = _index_fixture(adapter)
    query = GraphQuery(
        repo_id=snapshot.repo_id,
        graph_id=snapshot.graph_id,
        query_terms=["DatasetService.getVersion"],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id="TRACE-GITNEXUS-SERVICE",
        contract_version="1.0.0",
    )

    context = _call_gitnexus(lambda: adapter.query_graph(query))

    assert isinstance(context, GraphContext)
    assert context.trace_id == query.trace_id


@pytest.mark.gitnexus_integration
def test_query_graph_by_route_returns_route_or_controller_context_when_available():
    adapter = _gitnexus_adapter_or_skip()
    snapshot = _index_fixture(adapter)
    query = GraphQuery(
        repo_id=snapshot.repo_id,
        graph_id=snapshot.graph_id,
        query_terms=["/api/dataset/version"],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id="TRACE-GITNEXUS-ROUTE",
        contract_version="1.0.0",
    )

    context = _call_gitnexus(lambda: adapter.query_graph(query))

    assert isinstance(context, GraphContext)
    assert context.trace_id == query.trace_id
    if not context.matched_nodes:
        pytest.skip("GitNexus did not expose route nodes for this fixture.")

    labels = {
        value
        for node in context.matched_nodes
        for value in (node.type, node.name, node.qualified_name or "")
    }
    assert any(
        "DatasetController" in label or "/api/dataset/version" in label
        for label in labels
    )


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


def _gitnexus_adapter_or_skip() -> GitNexusCliCodeKnowledgeCoreAdapter:
    reason = _gitnexus_integration_skip_reason()
    if reason:
        pytest.skip(reason)
    client = GitNexusCliClient(
        gitnexus_bin=os.environ["GITNEXUS_BIN"],
        repo_root=os.environ["GITNEXUS_REPO_ROOT"],
    )
    return GitNexusCliCodeKnowledgeCoreAdapter(client=client)


def _repo_index_request() -> RepoIndexRequest:
    return RepoIndexRequest(
        repo_id=_repo_id("repo-java-spring-demo", FIXTURE_ROOT),
        repo_uri=FIXTURE_ROOT.resolve().as_uri(),
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )


def _repo_id(base_name: str, fixture_root: Path) -> str:
    path_hash = sha256(str(fixture_root.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{base_name}-{path_hash}"


def _index_fixture(adapter: GitNexusCliCodeKnowledgeCoreAdapter):
    request = _repo_index_request()
    return _call_gitnexus(lambda: adapter.index_repo(request))


def _call_gitnexus(operation):
    try:
        return operation()
    except CodeKnowledgeCoreError as exc:
        pytest.fail(
            "GitNexus integration failed without mock fallback: "
            f"{exc.message}; diagnostics={exc.diagnostics}"
        )
