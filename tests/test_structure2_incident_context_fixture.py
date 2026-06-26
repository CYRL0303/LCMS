from datetime import UTC, datetime

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceRef,
    GraphContext,
    Node,
)
from legacy_pilot.incident_context_builder.adapter import (
    GraphBackedIncidentContextBuilderAdapter,
)


def evidence_ref(evidence_id, source_type, source_id, file_path=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-ALERT-PROD-001",
        source_type=source_type,
        source_id=source_id,
        file_path=file_path,
        start_line=40 if file_path else None,
        end_line=45 if file_path else None,
        excerpt="fixture evidence",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


def test_structure2_builds_evidence_bundle_from_java_production_context():
    code = evidence_ref(
        "EV-CODE-DATASET-SERVICE",
        "code",
        "DatasetService.java",
        "src/main/java/com/legacy/DatasetService.java",
    )
    sql = evidence_ref("EV-SQL-DATASET-VERSION", "sql", "SQL:selectVersionById")
    config = evidence_ref("EV-CONFIG-DATASOURCE", "config", "spring.datasource.url")
    graph_queries = []

    def query_graph(graph_query):
        graph_queries.append(graph_query)
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
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            evidence_refs=[code, sql, config],
            confidence=0.88,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )
    alert = AlertEvent(
        alert_id="ALERT-PROD-001",
        repo_id="repo-prod",
        graph_id="GRAPH-repo-prod",
        raw_log=(
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        stack_trace="at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version via /api/dataset/version",
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        source="fixture",
        contract_version="1.0.0",
    )

    query = adapter.submit_alert(alert)
    bundle = adapter.build_evidence_bundle(query)

    assert graph_queries[0].repo_id == "repo-prod"
    assert graph_queries[0].graph_id == "GRAPH-repo-prod"
    assert graph_queries[0].trace_id == "TRACE-ALERT-PROD-001"
    assert "DatasetService.getVersion" in graph_queries[0].query_terms
    assert bundle.trace_id == query.trace_id
    assert bundle.contract_version == "1.0.0"
    assert bundle.code_evidence == [code]
    assert bundle.sql_evidence == [sql]
    assert bundle.config_evidence == [config]
    assert bundle.graph_paths == [
        [
            "DatasetController.getVersion",
            "DatasetService.getVersion",
            "DatasetMapper.selectVersionById",
            "dataset_version",
        ]
    ]
