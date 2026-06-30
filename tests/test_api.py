from datetime import UTC, datetime

from fastapi.testclient import TestClient

from legacy_pilot.code_knowledge_core.adapter import (
    CodeKnowledgeCoreAdapter,
)
from legacy_pilot.code_knowledge_core.graph_store import GraphStoreRecord
from legacy_pilot.contracts.models import (
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    IncidentMatch,
    IncidentQuery,
    IncidentRecord,
    RepoIndexRequest,
)
from legacy_pilot.incident_memory_store.adapter import IncidentMemoryStoreAdapter
from legacy_pilot.middleware.app import create_app
from legacy_pilot.middleware.router import MiddlewareRouter
from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter
from tests.fakes import TestCodeKnowledgeCoreAdapter


def alert_payload(
    contract_version: str = "1.0.0",
    graph_id: str | None = "GRAPH-DEMO",
) -> dict:
    payload = {
        "alert_id": "ALERT-001",
        "repo_id": "repo-demo",
        "raw_log": (
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        "stack_trace": "DatasetService.getVersion(DatasetService.java:42)",
        "error_description": "NPE while reading dataset version",
        "occurred_at": datetime(2026, 6, 11, tzinfo=UTC).isoformat(),
        "source": "demo-cli",
        "contract_version": contract_version,
    }
    if graph_id is not None:
        payload["graph_id"] = graph_id
    return payload


class ApiFakeAdapter(CodeKnowledgeCoreAdapter):
    def __init__(self):
        self.query_called = False
        self.deleted_graphs = []

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        raise AssertionError("index_repo was not expected")

    def query_graph(self, query: GraphQuery) -> GraphContext:
        self.query_called = True
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[],
            matched_edges=[],
            graph_paths=[["custom-router"]],
            evidence_refs=[],
            confidence=0.0,
        )

    def list_graphs(self) -> list[GraphStoreRecord]:
        return [
            GraphStoreRecord(
                repo_id="repo-demo",
                graph_id="GRAPH-X",
                parser_version="parser-v1",
                semantic_enrichment_version="semantic-v1",
                created_at=datetime(2026, 6, 30, 10, 0, tzinfo=UTC),
                updated_at=datetime(2026, 6, 30, 10, 5, tzinfo=UTC),
                node_count=3,
                edge_count=2,
            )
        ]

    def delete_graph(self, *, repo_id: str, graph_id: str) -> bool:
        self.deleted_graphs.append((repo_id, graph_id))
        return True


class ApiMemoryStoreAdapter(IncidentMemoryStoreAdapter):
    def __init__(self):
        self.saved_records = []

    def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        self.saved_records.append(record)
        return record

    def load_incident(self, incident_id: str) -> IncidentRecord | None:
        for record in self.saved_records:
            if record.incident_id == incident_id:
                return record
        return None

    def find_similar_incidents(
        self,
        query: IncidentQuery,
        *,
        limit: int = 5,
    ) -> list[IncidentMatch]:
        matches = []
        for record in self.saved_records:
            if record.repo_id != query.repo_id or not record.confirmed_by_user:
                continue
            matches.append(
                IncidentMatch(
                    incident_id=record.incident_id,
                    similarity=0.91,
                    previous_root_cause=record.root_cause,
                    previous_fix=record.fix,
                    related_files=record.related_files,
                    evidence_refs=record.evidence_refs,
                    confirmed_by_user=record.confirmed_by_user,
                )
            )
        return matches[:limit]

    def count_incidents_for_graph(self, *, repo_id: str, graph_id: str) -> int:
        return sum(
            1
            for record in self.saved_records
            if record.repo_id == repo_id and record.graph_id == graph_id
        )


def qwen_rca_adapter_for_existing_mock_bundle() -> QwenApiRCAReasoningEngineAdapter:
    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-GRAPH-001"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-GRAPH-001","EV-LOG-001"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-GRAPH-001"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-GRAPH-001"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    return QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)


def qwen_rca_adapter_with_unknown_evidence() -> QwenApiRCAReasoningEngineAdapter:
    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"selected_root_cause":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"suggested_fix":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"migration_impact":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"migration_checklist":[],"affected_path":[],'
                            '"open_questions":[],"confidence":0.9}'
                        )
                    }
                }
            ]
        }

    return QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)


def test_health_endpoint_exposes_middleware_identity():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "legacy-pilot-interface-contract-middleware"
    assert body["contract_version"] == "1.0.0"
    assert body["backends"]["code_knowledge_core"] == "gitnexus_cli"
    assert body["backends"]["incident_context_builder"] == "graph_context"
    assert body["backends"]["rca_reasoning_engine"] == "qwen_api"
    assert body["backends"]["incident_memory_store"] == "postgresql"


def test_submit_alert_endpoint_returns_incident_query():
    client = TestClient(create_app())

    response = client.post("/v1/alerts/submit", json=alert_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "TRACE-ALERT-001"
    assert body["error_type"] == "NullPointerException"
    assert "DatasetService.getVersion" in body["query_terms"]


def test_submit_alert_endpoint_preserves_optional_graph_id():
    client = TestClient(create_app())

    response = client.post(
        "/v1/alerts/submit",
        json=alert_payload(graph_id="GRAPH-repo-demo"),
    )

    assert response.status_code == 200
    assert response.json()["graph_id"] == "GRAPH-repo-demo"


def test_generate_rca_endpoint_converts_unknown_qwen_evidence_id_to_contract_error():
    memory_store = ApiMemoryStoreAdapter()
    router = MiddlewareRouter(
        code_knowledge_core_adapter=TestCodeKnowledgeCoreAdapter(),
        incident_memory_store_adapter=memory_store,
        rca_reasoning_engine_adapter=qwen_rca_adapter_with_unknown_evidence()
    )
    client = TestClient(create_app(router=router))
    query = client.post("/v1/alerts/submit", json=alert_payload()).json()
    bundle = client.post("/v1/evidence-bundles/build", json=query).json()

    response = client.post("/v1/rca/generate", json=bundle)

    assert response.status_code == 400
    body = response.json()
    assert body["trace_id"] == "TRACE-ALERT-001"
    assert body["source_module"] == "rca_reasoning_engine"
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "EV-UNKNOWN" in body["message"]


def test_http_pipeline_builds_qwen_reviews_and_saves_incident():
    memory_store = ApiMemoryStoreAdapter()
    router = MiddlewareRouter(
        code_knowledge_core_adapter=TestCodeKnowledgeCoreAdapter(),
        rca_reasoning_engine_adapter=qwen_rca_adapter_for_existing_mock_bundle(),
        incident_memory_store_adapter=memory_store,
    )
    client = TestClient(create_app(router=router))

    query = client.post("/v1/alerts/submit", json=alert_payload()).json()
    bundle_response = client.post("/v1/evidence-bundles/build", json=query)
    report_response = client.post("/v1/rca/generate", json=bundle_response.json())
    reviewed_response = client.post("/v1/rca/review", json=report_response.json())
    record_response = client.post(
        "/v1/incidents/save",
        json={
            "reviewed_report": reviewed_response.json(),
            "user_confirmation": True,
            "fix_outcome": "fixed by adding validation",
            "retention_policy": "demo-30-days",
            "contract_version": "1.0.0",
        },
    )

    assert bundle_response.status_code == 200
    assert report_response.status_code == 200
    assert (
        report_response.json()["selected_root_cause"]["summary"]
        == "datasetId guard missing"
    )
    assert reviewed_response.status_code == 200
    assert record_response.status_code == 200
    record = record_response.json()
    assert record["incident_id"] == "INC-ALERT-001"
    assert record["confirmed_by_user"] is True
    assert record["evidence_refs"]
    assert memory_store.saved_records[0].incident_id == "INC-ALERT-001"
    assert bundle_response.json()["contract_version"] == "1.0.0"
    assert report_response.json()["contract_version"] == "1.0.0"


def test_incident_read_endpoint_loads_saved_record_through_structure4():
    memory_store = ApiMemoryStoreAdapter()
    router = MiddlewareRouter(
        code_knowledge_core_adapter=TestCodeKnowledgeCoreAdapter(),
        rca_reasoning_engine_adapter=qwen_rca_adapter_for_existing_mock_bundle(),
        incident_memory_store_adapter=memory_store,
    )
    client = TestClient(create_app(router=router))
    query = client.post("/v1/alerts/submit", json=alert_payload()).json()
    bundle = client.post("/v1/evidence-bundles/build", json=query).json()
    report = client.post("/v1/rca/generate", json=bundle).json()
    reviewed = client.post("/v1/rca/review", json=report).json()
    saved = client.post(
        "/v1/incidents/save",
        json={
            "reviewed_report": reviewed,
            "user_confirmation": True,
            "fix_outcome": "fixed by adding validation",
            "retention_policy": "demo-30-days",
            "contract_version": "1.0.0",
        },
    ).json()

    response = client.get(f"/v1/incidents/{saved['incident_id']}")

    assert response.status_code == 200
    assert response.json() == saved


def test_query_graph_endpoint_returns_graph_context():
    router = MiddlewareRouter(code_knowledge_core_adapter=TestCodeKnowledgeCoreAdapter())
    client = TestClient(create_app(router=router))

    response = client.post(
        "/v1/graph/query",
        json={
            "repo_id": "repo-demo",
            "graph_id": "GRAPH-DEMO",
            "query_terms": ["NullPointerException", "DatasetService.getVersion"],
            "node_filters": ["Method"],
            "edge_filters": ["CALLS"],
            "max_depth": 3,
            "trace_id": "TRACE-ALERT-001",
            "contract_version": "1.0.0",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "TRACE-ALERT-001"
    assert body["matched_nodes"]
    assert body["matched_edges"]
    assert body["graph_paths"] == [
        [
            "DatasetController.getVersion",
            "DatasetService.getVersion",
            "DatasetMapper.selectVersionById",
            "dataset_version",
        ]
    ]
    assert body["evidence_refs"]
    assert body["confidence"] == 0.88


def test_create_app_with_custom_router_preserves_injection_path():
    adapter = ApiFakeAdapter()
    router = MiddlewareRouter(code_knowledge_core_adapter=adapter)
    client = TestClient(create_app(router=router))

    response = client.post(
        "/v1/graph/query",
        json={
            "repo_id": "repo-demo",
            "graph_id": "GRAPH-CUSTOM",
            "query_terms": ["x"],
            "node_filters": [],
            "edge_filters": [],
            "max_depth": 2,
            "trace_id": "TRACE-CUSTOM",
            "contract_version": "1.0.0",
        },
    )

    assert response.status_code == 200
    assert adapter.query_called is True
    assert response.json()["graph_paths"] == [["custom-router"]]


def test_graph_list_endpoint_returns_stored_graphs_with_incident_counts():
    adapter = ApiFakeAdapter()
    memory_store = ApiMemoryStoreAdapter()
    memory_store.save_incident(api_incident_record(graph_id="GRAPH-X"))
    router = MiddlewareRouter(
        code_knowledge_core_adapter=adapter,
        incident_memory_store_adapter=memory_store,
    )
    client = TestClient(create_app(router=router))

    response = client.get("/v1/graphs")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "repo_id": "repo-demo",
            "graph_id": "GRAPH-X",
            "parser_version": "parser-v1",
            "semantic_enrichment_version": "semantic-v1",
            "created_at": "2026-06-30T10:00:00Z",
            "updated_at": "2026-06-30T10:05:00Z",
            "node_count": 3,
            "edge_count": 2,
            "incident_memory_count": 1,
        }
    ]


def test_graph_delete_endpoint_blocks_graph_referenced_by_incident_memory():
    adapter = ApiFakeAdapter()
    memory_store = ApiMemoryStoreAdapter()
    memory_store.save_incident(api_incident_record(graph_id="GRAPH-X"))
    router = MiddlewareRouter(
        code_knowledge_core_adapter=adapter,
        incident_memory_store_adapter=memory_store,
    )
    client = TestClient(create_app(router=router))

    response = client.delete("/v1/graphs/repo-demo/GRAPH-X")

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "RESOURCE_IN_USE"
    assert "1 incident memory" in body["message"]
    assert adapter.deleted_graphs == []


def test_graph_delete_endpoint_deletes_unreferenced_graph():
    adapter = ApiFakeAdapter()
    router = MiddlewareRouter(
        code_knowledge_core_adapter=adapter,
        incident_memory_store_adapter=ApiMemoryStoreAdapter(),
    )
    client = TestClient(create_app(router=router))

    response = client.delete("/v1/graphs/repo-demo/GRAPH-X")

    assert response.status_code == 200
    assert response.json() == {
        "repo_id": "repo-demo",
        "graph_id": "GRAPH-X",
        "deleted": True,
        "incident_memory_count": 0,
    }
    assert adapter.deleted_graphs == [("repo-demo", "GRAPH-X")]


def test_unsupported_contract_version_returns_contract_error_envelope():
    client = TestClient(create_app())

    response = client.post("/v1/alerts/submit", json=alert_payload(contract_version="2.0.0"))

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "UNSUPPORTED_CONTRACT_VERSION"
    assert body["source_module"] == "interface_contract_middleware"
    assert body["recoverable"] is False


def test_missing_contract_version_returns_validation_error_envelope():
    client = TestClient(create_app())
    payload = alert_payload()
    del payload["contract_version"]

    response = client.post("/v1/alerts/submit", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "contract_version" in body["missing_fields"]


def test_missing_trace_id_returns_trace_required_error_envelope():
    client = TestClient(create_app())

    response = client.post(
        "/v1/graph/query",
        json={
            "repo_id": "repo-demo",
            "graph_id": "GRAPH-DEMO",
            "query_terms": ["DatasetService.getVersion"],
            "node_filters": [],
            "edge_filters": [],
            "max_depth": 3,
            "contract_version": "1.0.0",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "TRACE_REQUIRED"
    assert body["source_module"] == "interface_contract_middleware"
    assert body["recoverable"] is True
    assert body["missing_fields"] == ["trace_id"]


def api_incident_record(*, graph_id: str) -> IncidentRecord:
    created_at = datetime(2026, 6, 30, tzinfo=UTC)
    evidence = EvidenceRef(
        evidence_id="EV-API-1",
        trace_id="TRACE-API-1",
        source_type="code",
        source_id="DatasetService.java",
        file_path="src/main/java/DatasetService.java",
        start_line=40,
        end_line=45,
        excerpt="datasetId evidence",
        excerpt_hash="hash-api-1",
        extraction_method="java_parser",
        confidence=0.9,
        created_at=created_at,
    )
    return IncidentRecord(
        incident_id=f"INC-{graph_id}",
        repo_id="repo-demo",
        graph_id=graph_id,
        module="dataset-service",
        error_type="NullPointerException",
        symptom="NPE in DatasetService.getVersion",
        root_cause="datasetId guard missing",
        fix="add validation",
        related_files=["DatasetService.java"],
        related_nodes=["DatasetService.getVersion"],
        evidence_refs=[evidence],
        confirmed_by_user=True,
        fix_outcome="verified",
        dedup_key=f"repo-demo:NullPointerException:{graph_id}",
        retention_policy="api-test",
        created_at=created_at,
        updated_at=created_at,
    )
