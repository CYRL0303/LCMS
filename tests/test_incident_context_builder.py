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
    assert signals.query_terms[:3] == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]
    for term in ["DatasetService", "Dataset"]:
        assert term in signals.query_terms


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
    assert signals.query_terms[:3] == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]
    assert "DatasetService" in signals.query_terms


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


def test_parse_alert_event_extracts_natural_language_code_terms_for_graph_query():
    signals = parse_alert_event(
        alert_event(
            raw_log=(
                "java.lang.NullPointerException in BookInfoService while handling "
                "GET /api/books/deleteBook/TestBook. BookInfoController called "
                "BookInfoRepository and copiesAvailable was null for BookInfo."
            ),
            stack_trace=None,
            error_description=(
                "Deleting a borrowed book fails in BookInfoService.deleteBook."
            ),
        )
    )

    assert signals.error_type == "NullPointerException"
    assert signals.endpoint == "/api/books/deleteBook"
    for term in [
        "BookInfoService",
        "BookInfoController",
        "BookInfoRepository",
        "BookInfoService.deleteBook",
        "BookInfo",
        "deleteBook",
        "copiesAvailable",
    ]:
        assert term in signals.query_terms

    graph_query = build_graph_query(
        IncidentQuery(
            trace_id="TRACE-ALERT-BOOK",
            repo_id="IBM",
            graph_id="GRAPH-IBM",
            error_type=signals.error_type,
            suspected_location=signals.suspected_location,
            endpoint=signals.endpoint,
            keywords=signals.keywords,
            query_terms=signals.query_terms,
            contract_version="1.0.0",
        )
    )

    assert graph_query.query_terms[:2] == [
        "/api/books/deleteBook",
        "BookInfoService.deleteBook",
    ]
    assert "BookInfoRepository" in graph_query.query_terms
    assert "copiesAvailable" in graph_query.query_terms


def test_parse_alert_event_keeps_broad_code_terms_when_stack_frame_exists():
    signals = parse_alert_event(
        alert_event(
            raw_log=(
                "org.springframework.dao.BadSqlGrammarException: failed query "
                "for BookInfoRepository and BookInfoService at /api/books/search"
            ),
            stack_trace=(
                "at com.example.demo.controller.BookInfoController.searchBooks"
                "(BookInfoController.java:88)"
            ),
            error_description="Book search failed for BookInfo records.",
        )
    )

    assert signals.error_type == "BadSqlGrammarException"
    assert signals.suspected_location == "BookInfoController.searchBooks"
    for term in [
        "BookInfoController.searchBooks",
        "BookInfoController",
        "BookInfoRepository",
        "BookInfoService",
        "BookInfo",
        "Book",
    ]:
        assert term in signals.query_terms


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


def test_incident_context_factory_rejects_runtime_mock_backend(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", "mock")

    with pytest.raises(ValueError) as excinfo:
        create_incident_context_builder_adapter()

    assert "Unsupported incident context backend: mock" in str(excinfo.value)


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
        query_terms=["DatasetService.getVersion", "NullPointerException"],
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
    assert calls[0].query_terms[:3] == [
        "/api/dataset/version",
        "DatasetService.getVersion",
        "NullPointerException",
    ]
    for term in ["DatasetService", "Dataset"]:
        assert term in calls[0].query_terms
    assert bundle.matched_nodes[0].name == "DatasetService.getVersion"
    assert bundle.code_evidence == [code]


def test_graph_backed_adapter_retries_low_recall_and_merges_evidence():
    calls = []
    first = evidence_ref("EV-CODE-FIRST", "code", "DatasetService.java")
    recalled = evidence_ref("EV-CODE-RECALL", "code", "DatasetMapper.java")

    def query_graph(graph_query):
        calls.append(graph_query)
        if len(calls) == 1:
            return GraphContext(
                trace_id=graph_query.trace_id,
                matched_nodes=[
                    Node(
                        node_id="Method:DatasetService.getVersion",
                        graph_id=graph_query.graph_id,
                        repo_id=graph_query.repo_id,
                        type="Method",
                        name="DatasetService.getVersion",
                        evidence_refs=[first],
                    )
                ],
                matched_edges=[],
                graph_paths=[],
                evidence_refs=[first],
                confidence=0.42,
            )
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[
                Node(
                    node_id="Method:DatasetMapper.selectVersionById",
                    graph_id=graph_query.graph_id,
                    repo_id=graph_query.repo_id,
                    type="Method",
                    name="DatasetMapper.selectVersionById",
                    evidence_refs=[recalled],
                )
            ],
            matched_edges=[],
            graph_paths=[
                [
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                ]
            ],
            evidence_refs=[recalled],
            confidence=0.74,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )

    bundle = adapter.build_evidence_bundle(
        IncidentQuery(
            trace_id="TRACE-ALERT-001",
            repo_id="repo-demo",
            graph_id="GRAPH-repo-demo",
            error_type="NullPointerException",
            suspected_location="DatasetService.getVersion",
            endpoint="/api/dataset/version",
            keywords=["dataset_version"],
            query_terms=[
                "NullPointerException",
                "DatasetService.getVersion",
                "DatasetMapper.selectVersionById",
                "dataset_version",
            ],
            contract_version="1.0.0",
        )
    )

    assert len(calls) == 2
    assert calls[1].max_depth > calls[0].max_depth
    assert "DatasetMapper" in calls[1].query_terms
    assert [ref.evidence_id for ref in bundle.code_evidence] == [
        "EV-CODE-FIRST",
        "EV-CODE-RECALL",
    ]
    assert bundle.graph_paths == [
        [
            "DatasetService.getVersion",
            "DatasetMapper.selectVersionById",
        ]
    ]
    assert bundle.missing_evidence == []


def test_low_recall_retry_uses_broad_terms_instead_of_noisy_stack_terms():
    calls = []
    recalled = evidence_ref("EV-CODE-BOOK", "code", "BookInfoService.java")

    def query_graph(graph_query):
        calls.append(graph_query)
        if len(calls) == 1:
            return GraphContext(
                trace_id=graph_query.trace_id,
                matched_nodes=[],
                matched_edges=[],
                graph_paths=[],
                evidence_refs=[],
                confidence=0.0,
            )
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[
                Node(
                    node_id="File:BookInfoService.java",
                    graph_id=graph_query.graph_id,
                    repo_id=graph_query.repo_id,
                    type="File",
                    name="BookInfoService.java",
                    evidence_refs=[recalled],
                )
            ],
            matched_edges=[],
            graph_paths=[["BookInfoController.java", "BookInfoService.java"]],
            evidence_refs=[recalled],
            confidence=0.8,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )

    bundle = adapter.build_evidence_bundle(
        IncidentQuery(
            trace_id="TRACE-BOOK-001",
            repo_id="ibm-demo",
            graph_id="GRAPH-ibm-demo",
            error_type="BadSqlGrammarException",
            suspected_location="BookMapper.selectAvailableBooks",
            endpoint="/api/books/search",
            keywords=["book"],
            query_terms=[
                "BadSqlGrammarException",
                "BookMapper.selectAvailableBooks",
                "/api/books/search",
                "book",
                "BookController",
                "SQLSyntaxErrorException",
                "PreparedStatementHandler",
                "DispatcherServlet.doDispatch",
                "Book",
                "Prepared",
            ],
            contract_version="1.0.0",
        )
    )

    assert len(calls) == 2
    for term in ["Book", "book", "BookController", "BookMapper"]:
        assert term in calls[1].query_terms
    for noisy in [
        "/api/books/search",
        "BadSqlGrammarException",
        "PreparedStatementHandler",
        "DispatcherServlet",
    ]:
        assert noisy not in calls[1].query_terms
    assert bundle.code_evidence == [recalled]
    assert bundle.missing_evidence == []


def test_low_recall_retry_ranks_repeated_domain_roots_first():
    calls = []

    def query_graph(graph_query):
        calls.append(graph_query)
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[],
            matched_edges=[],
            graph_paths=[],
            evidence_refs=[],
            confidence=0.0,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )

    adapter.build_evidence_bundle(
        IncidentQuery(
            trace_id="TRACE-LOGIN-001",
            repo_id="ibm-demo",
            graph_id="GRAPH-ibm-demo",
            error_type="NullPointerException",
            suspected_location="LoginController.login",
            endpoint="/api/login",
            keywords=[],
            query_terms=[
                "NullPointerException",
                "LoginController.login",
                "/api/login",
                "LoginController",
                "UserService",
                "User.getPassword",
                "UserService.checkPassword",
                "UserService.login",
                "Login",
                "User",
            ],
            contract_version="1.0.0",
        )
    )

    assert len(calls) == 2
    assert calls[1].query_terms[:2] == ["User", "Login"]
