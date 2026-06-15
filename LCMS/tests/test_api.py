from datetime import UTC, datetime

from fastapi.testclient import TestClient

from legacy_pilot.middleware.app import create_app


def alert_payload(contract_version: str = "1.0.0") -> dict:
    return {
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


def test_health_endpoint_exposes_middleware_identity():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "legacy-pilot-interface-contract-middleware",
        "contract_version": "1.0.0",
    }


def test_submit_alert_endpoint_returns_incident_query():
    client = TestClient(create_app())

    response = client.post("/v1/alerts/submit", json=alert_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "TRACE-ALERT-001"
    assert body["error_type"] == "NullPointerException"
    assert "DatasetService.getVersion" in body["query_terms"]


def test_http_pipeline_builds_reviews_and_saves_incident():
    client = TestClient(create_app())

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
    assert reviewed_response.status_code == 200
    assert record_response.status_code == 200
    record = record_response.json()
    assert record["incident_id"] == "INC-ALERT-001"
    assert record["confirmed_by_user"] is True
    assert record["evidence_refs"]
    assert bundle_response.json()["contract_version"] == "1.0.0"
    assert report_response.json()["contract_version"] == "1.0.0"


def test_query_graph_endpoint_returns_graph_context():
    client = TestClient(create_app())

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
