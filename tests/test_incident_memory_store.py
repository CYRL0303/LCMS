from datetime import UTC, datetime

import pytest

from legacy_pilot.contracts.models import EvidenceRef, IncidentRecord
from legacy_pilot.incident_memory_store.adapter import (
    InMemoryIncidentMemoryStoreAdapter,
    IncidentMemoryStoreError,
    PostgresIncidentMemoryStoreAdapter,
    create_incident_memory_store_adapter,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.last_query = ""
        self.last_params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.last_query = str(query)
        self.last_params = tuple(params or ())
        self.connection.executed.append((self.last_query, self.last_params))
        if self.last_query.lstrip().upper().startswith("SELECT"):
            self.connection.selected = True

    def fetchone(self):
        if not self.connection.selected or self.connection.payload_to_return is None:
            return None
        return (self.connection.payload_to_return,)


class FakeConnection:
    def __init__(self, payload_to_return=None):
        self.executed = []
        self.selected = False
        self.payload_to_return = payload_to_return

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self)


class FakeConnector:
    def __init__(self, payload_to_return=None):
        self.connections = []
        self.payload_to_return = payload_to_return

    def __call__(self, dsn):
        connection = FakeConnection(payload_to_return=self.payload_to_return)
        self.connections.append((dsn, connection))
        return connection


def test_postgres_incident_memory_store_upserts_record_json():
    connector = FakeConnector()
    store = PostgresIncidentMemoryStoreAdapter(
        dsn="postgresql://example/db",
        table_name="legacy_pilot_incident_records_test",
        connect=connector,
    )
    record = incident_record()

    stored = store.save_incident(record)

    assert stored == record
    assert connector.connections[0][0] == "postgresql://example/db"
    executed_sql = "\n".join(query for query, _ in connector.connections[0][1].executed)
    assert "CREATE TABLE IF NOT EXISTS legacy_pilot_incident_records_test" in executed_sql
    assert "ON CONFLICT (incident_id) DO UPDATE" in executed_sql
    insert_params = connector.connections[0][1].executed[1][1]
    assert insert_params[0] == "INC-ALERT-001"
    assert insert_params[1] == "repo-demo"
    assert insert_params[2] == "repo-demo:NullPointerException:DatasetService.getVersion"


def test_postgres_incident_memory_store_loads_record_json():
    record = incident_record()
    connector = FakeConnector(payload_to_return=record.model_dump(mode="json"))
    store = PostgresIncidentMemoryStoreAdapter(
        dsn="postgresql://example/db",
        table_name="legacy_pilot_incident_records_test",
        connect=connector,
    )

    loaded = store.load_incident("INC-ALERT-001")

    assert loaded == record
    executed_sql = "\n".join(query for query, _ in connector.connections[0][1].executed)
    assert "SELECT record_json" in executed_sql
    assert "WHERE incident_id = %s" in executed_sql


def test_incident_memory_factory_defaults_to_postgresql_and_requires_dsn(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_INCIDENT_MEMORY_BACKEND", raising=False)
    monkeypatch.delenv("LEGACY_PILOT_INCIDENT_MEMORY_DSN", raising=False)

    with pytest.raises(IncidentMemoryStoreError) as excinfo:
        create_incident_memory_store_adapter()

    assert "LEGACY_PILOT_INCIDENT_MEMORY_DSN" in excinfo.value.message


def test_incident_memory_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_INCIDENT_MEMORY_BACKEND", "surprise")

    with pytest.raises(IncidentMemoryStoreError) as excinfo:
        create_incident_memory_store_adapter()

    message = excinfo.value.message
    assert "surprise" in message
    assert "postgresql" in message
    assert "memory" in message


def test_incident_memory_factory_explicit_memory_backend():
    adapter = create_incident_memory_store_adapter(backend="memory")

    assert isinstance(adapter, InMemoryIncidentMemoryStoreAdapter)


def incident_record() -> IncidentRecord:
    created_at = datetime(2026, 6, 30, tzinfo=UTC)
    evidence = EvidenceRef(
        evidence_id="EV-CODE-1",
        trace_id="TRACE-ALERT-001",
        source_type="code",
        source_id="DatasetService.java",
        file_path="src/main/java/DatasetService.java",
        start_line=40,
        end_line=45,
        excerpt="datasetId evidence",
        excerpt_hash="hash-code-1",
        extraction_method="java_parser",
        confidence=0.9,
        created_at=created_at,
    )
    return IncidentRecord(
        incident_id="INC-ALERT-001",
        repo_id="repo-demo",
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
        dedup_key="repo-demo:NullPointerException:DatasetService.getVersion",
        retention_policy="e2e-test",
        created_at=created_at,
        updated_at=created_at,
    )
