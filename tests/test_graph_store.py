from datetime import UTC, datetime

import pytest

from legacy_pilot.code_knowledge_core.graph_store import (
    DisabledGraphStore,
    PostgresGraphStore,
    create_graph_store,
    payload_hash,
)


def test_payload_hash_is_stable_for_key_order_changes():
    left = {
        "repo_id": "repo-a",
        "graph_id": "GRAPH-repo-a",
        "nodes": [{"id": "Method:A", "type": "Method", "name": "A"}],
        "relationships": [],
    }
    right = {
        "relationships": [],
        "nodes": [{"name": "A", "type": "Method", "id": "Method:A"}],
        "graph_id": "GRAPH-repo-a",
        "repo_id": "repo-a",
    }

    assert payload_hash(left) == payload_hash(right)


def test_disabled_graph_store_ignores_save_and_loads_nothing():
    store = DisabledGraphStore()

    store.save_payload(
        repo_id="repo-a",
        graph_id="GRAPH-repo-a",
        payload={"repo_id": "repo-a", "graph_id": "GRAPH-repo-a"},
    )

    assert store.load_payload(repo_id="repo-a", graph_id="GRAPH-repo-a") is None


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
        if not self.connection.selected:
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


def test_postgres_graph_store_upserts_payload_with_metadata():
    connector = FakeConnector()
    frozen_now = datetime(2026, 6, 23, tzinfo=UTC)
    store = PostgresGraphStore(
        dsn="postgresql://example/db",
        table_name="legacy_pilot_graph_payloads_test",
        connect=connector,
        now=lambda: frozen_now,
    )
    payload = {
        "repo_id": "repo-a",
        "graph_id": "GRAPH-repo-a",
        "parser_version": "gitnexus_cli+structure1_sql_config_exception_v1",
        "semantic_enrichment_version": "qwen-plus+semantic-v1",
        "nodes": [],
        "relationships": [],
    }

    store.save_payload(repo_id="repo-a", graph_id="GRAPH-repo-a", payload=payload)

    assert connector.connections[0][0] == "postgresql://example/db"
    executed_sql = "\n".join(query for query, _ in connector.connections[0][1].executed)
    assert "CREATE TABLE IF NOT EXISTS legacy_pilot_graph_payloads_test" in executed_sql
    assert "ON CONFLICT (repo_id, graph_id) DO UPDATE" in executed_sql
    insert_params = connector.connections[0][1].executed[1][1]
    assert insert_params[3] == payload_hash(payload)
    assert insert_params[4] == "gitnexus_cli+structure1_sql_config_exception_v1"
    assert insert_params[5] == "qwen-plus+semantic-v1"
    assert insert_params[6] == frozen_now
    assert insert_params[7] == frozen_now


def test_create_graph_store_rejects_unsafe_postgresql_table_name(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_GRAPH_STORE_BACKEND", "postgresql")
    monkeypatch.setenv("LEGACY_PILOT_GRAPH_STORE_DSN", "postgresql://example/db")
    monkeypatch.setenv(
        "LEGACY_PILOT_GRAPH_STORE_TABLE",
        "legacy_pilot_graph_payloads; DROP TABLE users",
    )

    with pytest.raises(ValueError, match="safe SQL identifier"):
        create_graph_store()


def test_postgres_graph_store_loads_payload():
    payload = {"repo_id": "repo-a", "graph_id": "GRAPH-repo-a", "nodes": []}
    connector = FakeConnector(payload_to_return=payload)
    store = PostgresGraphStore(
        dsn="postgresql://example/db",
        table_name="legacy_pilot_graph_payloads_test",
        connect=connector,
    )

    loaded = store.load_payload(repo_id="repo-a", graph_id="GRAPH-repo-a")

    assert loaded == payload
    executed_sql = "\n".join(query for query, _ in connector.connections[0][1].executed)
    assert "SELECT payload_json" in executed_sql
    assert "WHERE repo_id = %s AND graph_id = %s" in executed_sql


def test_create_graph_store_selects_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_GRAPH_STORE_BACKEND", raising=False)
    monkeypatch.delenv("LEGACY_PILOT_GRAPH_STORE_DSN", raising=False)

    store = create_graph_store()

    assert isinstance(store, DisabledGraphStore)


def test_create_graph_store_selects_postgresql_from_env(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_GRAPH_STORE_BACKEND", "postgresql")
    monkeypatch.setenv("LEGACY_PILOT_GRAPH_STORE_DSN", "postgresql://example/db")
    monkeypatch.setenv("LEGACY_PILOT_GRAPH_STORE_TABLE", "legacy_pilot_graph_payloads_test")

    store = create_graph_store()

    assert isinstance(store, PostgresGraphStore)
    assert store.table_name == "legacy_pilot_graph_payloads_test"
