import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.adapter import GitNexusCliCodeKnowledgeCoreAdapter
from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.code_knowledge_core.graph_store import PostgresGraphStore
from legacy_pilot.contracts.models import AlertEvent, GraphQuery, RepoIndexRequest
from legacy_pilot.middleware.router import MiddlewareRouter


pytestmark = [pytest.mark.real_structure1_structure2_e2e, pytest.mark.slow]

RUN_ENV = "LEGACY_PILOT_RUN_REAL_E2E"
REQUIRED_ENV_KEYS = (
    "GITNEXUS_BIN",
    "GITNEXUS_REPO_ROOT",
    "LEGACY_PILOT_GRAPH_STORE_DSN",
    "DASHSCOPE_API_KEY",
)
REQUIRED_ENV_VALUES = {
    "LEGACY_PILOT_CODE_CORE_BACKEND": "gitnexus_cli",
    "LEGACY_PILOT_GRAPH_STORE_BACKEND": "postgresql",
    "LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND": "graph_context",
    "LEGACY_PILOT_RCA_BACKEND": "qwen_api",
}
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_production_demo"


def test_real_e2e_skip_reason_lists_required_environment(monkeypatch):
    monkeypatch.delenv(RUN_ENV, raising=False)
    for key in REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in REQUIRED_ENV_VALUES:
        monkeypatch.delenv(key, raising=False)

    reason = _real_e2e_skip_reason()

    assert RUN_ENV in reason
    for key in REQUIRED_ENV_KEYS:
        assert key in reason
    for key in REQUIRED_ENV_VALUES:
        assert key in reason
    assert "DASHSCOPE_API_KEY" in reason
    assert "LEGACY_PILOT_RCA_BACKEND=qwen_api" in reason


def test_real_e2e_enabled_missing_environment_fails_loudly(monkeypatch):
    monkeypatch.setenv(RUN_ENV, "1")

    with pytest.raises(pytest.fail.Exception):
        _skip_or_fail_real_e2e("missing DASHSCOPE_API_KEY")


def test_real_gitnexus_postgres_structure2_e2e():
    reason = _real_e2e_skip_reason()
    _skip_or_fail_real_e2e(reason)

    table_name = os.getenv(
        "LEGACY_PILOT_GRAPH_STORE_TABLE",
        "legacy_pilot_graph_payloads_e2e",
    )
    graph_store = PostgresGraphStore(
        dsn=os.environ["LEGACY_PILOT_GRAPH_STORE_DSN"],
        table_name=table_name,
    )
    index_adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=GitNexusCliClient(
            gitnexus_bin=os.environ["GITNEXUS_BIN"],
            repo_root=os.environ["GITNEXUS_REPO_ROOT"],
        ),
        graph_store=graph_store,
    )
    request = _production_fixture_request()

    snapshot = _call_structure1(lambda: index_adapter.index_repo(request))

    _assert_structure1_snapshot(snapshot)

    restore_adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=QueryForbiddenClient(),
        graph_store=graph_store,
    )
    router = MiddlewareRouter(code_knowledge_core_adapter=restore_adapter)

    query = router.submit_alert(_alert_event(request.repo_id, snapshot.graph_id))
    bundle = router.build_evidence_bundle(query)
    report = router.generate_rca(bundle)
    reviewed = router.review_rca(report)
    record = router.save_incident(
        reviewed_report=reviewed,
        user_confirmation=True,
        fix_outcome="verified_by_real_structure3_e2e",
        retention_policy="e2e-test",
        contract_version="1.0.0",
    )
    bundle_evidence_ids = _bundle_evidence_ids(bundle)
    report_evidence_ids = _report_evidence_ids(report)
    reviewed_evidence_ids = _reviewed_evidence_ids(reviewed)

    assert query.graph_id == snapshot.graph_id
    assert query.query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]
    assert bundle.trace_id == query.trace_id
    assert bundle.contract_version == query.contract_version
    assert bundle.matched_nodes
    assert bundle.graph_paths
    assert bundle.code_evidence
    assert bundle.missing_evidence == []
    assert report.trace_id == query.trace_id
    assert report.contract_version == bundle.contract_version
    assert report.selected_root_cause.evidence_refs
    assert report.suggested_fix
    assert report.suggested_fix[0].evidence_refs
    assert report.migration_impact.evidence_refs
    assert report.evidence_chain
    assert report_evidence_ids.issubset(bundle_evidence_ids)
    assert reviewed.report_id == report.report_id
    assert reviewed.approved_findings
    assert reviewed.final_confidence == report.confidence
    assert reviewed_evidence_ids.issubset(bundle_evidence_ids)
    assert record.incident_id == "INC-ALERT-PG-GITNEXUS-E2E"
    assert record.confirmed_by_user is True
    assert record.evidence_refs


class QueryForbiddenClient:
    def index_repo(self, request: RepoIndexRequest) -> dict:
        raise AssertionError("Real E2E restore adapter must not re-index GitNexus.")

    def query_graph(self, query: GraphQuery) -> dict:
        raise AssertionError(
            "Real E2E must restore GraphContext from PostgreSQL before GitNexus fallback."
        )


def _real_e2e_skip_reason() -> str | None:
    missing_keys = [key for key in REQUIRED_ENV_KEYS if not os.getenv(key)]
    if os.getenv(RUN_ENV) != "1":
        missing_keys.insert(0, RUN_ENV)
    wrong_values = [
        f"{key}={expected}"
        for key, expected in REQUIRED_ENV_VALUES.items()
        if os.getenv(key) != expected
    ]
    missing_keys.extend(wrong_values)
    if not missing_keys:
        return None
    return (
        "Real Structure1/PostgreSQL/Structure2/Structure3 E2E is opt-in; set "
        f"{', '.join(missing_keys)} to run against local GitNexus, PostgreSQL, "
        "and Qwen."
    )


def _skip_or_fail_real_e2e(reason: str | None) -> None:
    if not reason:
        return
    if os.getenv(RUN_ENV) == "1":
        pytest.fail(reason)
    pytest.skip(reason)


def _bundle_evidence_ids(bundle) -> set[str]:
    refs = [
        *bundle.code_evidence,
        *bundle.sql_evidence,
        *bundle.config_evidence,
        *bundle.log_evidence,
    ]
    for incident in bundle.similar_incidents:
        refs.extend(incident.evidence_refs)
    return {ref.evidence_id for ref in refs}


def _report_evidence_ids(report) -> set[str]:
    refs = [
        *report.evidence_chain,
        *report.selected_root_cause.evidence_refs,
        *report.migration_impact.evidence_refs,
    ]
    for item in [*report.hypotheses, *report.suggested_fix]:
        refs.extend(item.evidence_refs)
    return {ref.evidence_id for ref in refs}


def _reviewed_evidence_ids(reviewed) -> set[str]:
    refs = []
    for item in reviewed.approved_findings:
        refs.extend(item.evidence_refs)
    return {ref.evidence_id for ref in refs}


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


def _alert_event(repo_id: str, graph_id: str) -> AlertEvent:
    return AlertEvent(
        alert_id="ALERT-PG-GITNEXUS-E2E",
        repo_id=repo_id,
        graph_id=graph_id,
        raw_log=(
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42). "
            "Hit /api/dataset/version."
        ),
        stack_trace="at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version via /api/dataset/version",
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        source="real-e2e",
        contract_version="1.0.0",
    )


def _assert_structure1_snapshot(snapshot) -> None:
    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}

    assert snapshot.nodes
    assert snapshot.edges
    assert snapshot.parser_version == "gitnexus_cli+structure1_sql_config_exception_v1"
    assert {"SQL", "Table", "Config", "Exception"}.issubset(node_types)
    assert {"EXECUTES_SQL", "READS_TABLE", "THROWS_EXCEPTION"}.issubset(edge_types)


def _call_structure1(operation):
    try:
        return operation()
    except CodeKnowledgeCoreError as exc:
        pytest.fail(
            "Real Structure1/PostgreSQL/Structure2 E2E failed at Structure1: "
            f"{exc.message}; diagnostics={exc.diagnostics}"
        )
