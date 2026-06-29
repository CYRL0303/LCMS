from datetime import UTC, datetime

import pytest

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    IncidentQuery,
    Node,
)
from legacy_pilot.incident_context_builder.adapter import (
    GraphBackedIncidentContextBuilderAdapter,
    MockIncidentContextBuilderAdapter,
    create_incident_context_builder_adapter,
)
from legacy_pilot.incident_context_builder.evidence_builder import (
    build_evidence_bundle_from_graph_context,
    build_graph_query,
    graph_id_for_query,
)
from legacy_pilot.incident_context_builder.signals import parse_alert_event


def alert_event(**overrides):
    values = {
        "alert_id": "ALERT-001",
        "repo_id": "repo-demo",
        "graph_id": "GRAPH-repo-demo",
        "raw_log": (
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        "stack_trace": "at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
        "error_description": "NPE while reading dataset version via /api/dataset/version",
        "occurred_at": datetime(2026, 6, 24, tzinfo=UTC),
        "source": "demo-cli",
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return AlertEvent(**values)


def evidence_ref(evidence_id, source_type="code", source_id="DatasetService.java"):
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-ALERT-001",
        source_type=source_type,
        source_id=source_id,
        file_path="src/main/java/DatasetService.java" if source_type == "code" else None,
        start_line=40 if source_type == "code" else None,
        end_line=45 if source_type == "code" else None,
        excerpt="evidence excerpt",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


def test_parse_alert_event_extracts_java_exception_location_and_endpoint():
    signals = parse_alert_event(alert_event())

    assert signals.error_type == "NullPointerException"
    assert signals.suspected_location == "DatasetService.getVersion"
    assert signals.file_path == "DatasetService.java"
    assert signals.line_number == 42
    assert signals.endpoint == "/api/dataset/version"
    assert signals.query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]


def test_parse_alert_event_extracts_slow_query_signal():
    signals = parse_alert_event(
        alert_event(
            raw_log="Slow query detected: select * from dataset_version where dataset_id = ?",
            stack_trace=None,
            error_description="Slow query on dataset_version",
        )
    )

    assert signals.error_type == "SlowQuery"
    assert "dataset_version" in signals.keywords
    assert "dataset_version" in signals.query_terms


def test_parse_alert_event_trims_endpoint_trailing_punctuation():
    signals = parse_alert_event(
        alert_event(
            raw_log="NullPointerException at DatasetService.getVersion. Hit /api/dataset/version.",
            stack_trace="at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
            error_description="Endpoint /api/dataset/version.",
        )
    )

    assert signals.endpoint == "/api/dataset/version"
    assert signals.query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]


def test_parse_alert_event_detects_slow_query_case_insensitively():
    signals = parse_alert_event(
        alert_event(
            raw_log="SLOW QUERY detected: select * from dataset_version",
            stack_trace=None,
            error_description=None,
        )
    )

    assert signals.error_type == "SlowQuery"


def test_parse_alert_event_deduplicates_query_terms_in_order():
    signals = parse_alert_event(
        alert_event(
            raw_log=(
                "Slow query detected: select * from dataset_version "
                "join dataset_version on dataset_version.id = dataset_version.id"
            ),
            stack_trace=None,
            error_description="Slow query on /api/dataset/version and /api/dataset/version",
        )
    )

    assert signals.query_terms == [
        "SlowQuery",
        "/api/dataset/version",
        "dataset_version",
    ]


def test_mock_incident_context_adapter_preserves_submit_alert_behavior():
    adapter = MockIncidentContextBuilderAdapter()

    query = adapter.submit_alert(alert_event())

    assert query.trace_id == "TRACE-ALERT-001"
    assert query.repo_id == "repo-demo"
    assert query.graph_id == "GRAPH-repo-demo"
    assert query.error_type == "NullPointerException"
    assert query.suspected_location == "DatasetService.getVersion"
    assert query.endpoint == "/api/dataset/version"
    assert query.contract_version == "1.0.0"


def test_mock_incident_context_adapter_builds_evidence_bundle():
    adapter = MockIncidentContextBuilderAdapter()
    query = adapter.submit_alert(alert_event())

    bundle = adapter.build_evidence_bundle(query)

    assert bundle.trace_id == query.trace_id
    assert bundle.contract_version == query.contract_version
    assert bundle.code_evidence
    assert bundle.log_evidence
    assert bundle.similar_incidents[0].incident_id == "INC-003"


def test_incident_context_factory_defaults_to_graph_context(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", raising=False)

    adapter = create_incident_context_builder_adapter(
        query_graph=lambda graph_query: GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[],
            matched_edges=[],
            graph_paths=[],
            evidence_refs=[],
            confidence=0.0,
        ),
        find_similar_incidents=lambda query: [],
    )

    assert isinstance(adapter, GraphBackedIncidentContextBuilderAdapter)


def test_incident_context_factory_missing_default_dependencies_fails_loud(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", raising=False)

    with pytest.raises(ValueError) as excinfo:
        create_incident_context_builder_adapter()

    assert "graph_context" in str(excinfo.value)
    assert "query_graph" in str(excinfo.value)


def test_incident_context_factory_unknown_backend_fails_loud(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", "surprise_backend")

    with pytest.raises(ValueError) as excinfo:
        create_incident_context_builder_adapter()

    message = str(excinfo.value)
    assert "surprise_backend" in message
    assert "graph_context" in message
    assert "mock" in message


def test_incident_context_factory_explicit_mock_still_selects_mock(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", "mock")

    adapter = create_incident_context_builder_adapter()

    assert isinstance(adapter, MockIncidentContextBuilderAdapter)


def test_build_graph_query_uses_explicit_graph_id():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-explicit",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    graph_query = build_graph_query(query)

    assert graph_query == GraphQuery(
        repo_id="repo-demo",
        graph_id="GRAPH-explicit",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id="TRACE-ALERT-001",
        contract_version="1.0.0",
    )


def test_graph_id_for_query_falls_back_to_repo_graph():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        error_type="NullPointerException",
        query_terms=["NullPointerException"],
        contract_version="1.0.0",
    )

    assert graph_id_for_query(query) == "GRAPH-repo-demo"


def test_build_evidence_bundle_from_graph_context_partitions_evidence():
    code = evidence_ref("EV-CODE-1", "code")
    sql = evidence_ref("EV-SQL-1", "sql", "SQL:selectVersionById")
    config = evidence_ref("EV-CONFIG-1", "config", "spring.datasource.url")
    graph_context = GraphContext(
        trace_id="TRACE-ALERT-001",
        matched_nodes=[
            Node(
                node_id="Method:DatasetService.getVersion",
                graph_id="GRAPH-repo-demo",
                repo_id="repo-demo",
                type="Method",
                name="DatasetService.getVersion",
                evidence_refs=[code],
            )
        ],
        matched_edges=[],
        graph_paths=[
            [
                "DatasetController.getVersion",
                "DatasetService.getVersion",
                "DatasetMapper.selectVersionById",
                "dataset_version",
            ]
        ],
        evidence_refs=[code, sql, config],
        confidence=0.88,
    )
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    bundle = build_evidence_bundle_from_graph_context(
        query=query,
        graph_context=graph_context,
        similar_incidents=[],
    )

    assert bundle.trace_id == "TRACE-ALERT-001"
    assert bundle.matched_nodes == graph_context.matched_nodes
    assert bundle.graph_paths == graph_context.graph_paths
    assert bundle.code_evidence == [code]
    assert bundle.sql_evidence == [sql]
    assert bundle.config_evidence == [config]
    assert bundle.missing_evidence == []


def test_graph_backed_adapter_queries_graph_and_builds_bundle():
    calls = []
    code = evidence_ref("EV-CODE-1", "code")

    def query_graph(graph_query):
        calls.append(graph_query)
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[
                Node(
                    node_id="Method:DatasetService.getVersion",
                    graph_id=graph_query.graph_id,
                    repo_id=graph_query.repo_id,
                    type="Method",
                    name="DatasetService.getVersion",
                    evidence_refs=[code],
                )
            ],
            matched_edges=[],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                ]
            ],
            evidence_refs=[code],
            confidence=0.88,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )
    query = adapter.submit_alert(alert_event())

    bundle = adapter.build_evidence_bundle(query)

    assert calls[0].graph_id == "GRAPH-repo-demo"
    assert calls[0].query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]
    assert bundle.matched_nodes[0].name == "DatasetService.getVersion"
    assert bundle.code_evidence == [code]
