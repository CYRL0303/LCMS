from datetime import UTC, datetime

from legacy_pilot.contracts.models import AlertEvent
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
