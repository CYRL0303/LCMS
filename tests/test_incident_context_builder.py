from datetime import UTC, datetime

from legacy_pilot.contracts.models import AlertEvent
from legacy_pilot.incident_context_builder.adapter import (
    MockIncidentContextBuilderAdapter,
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
