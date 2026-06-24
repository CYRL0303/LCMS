# Structure 1 PostgreSQL Graph Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Structure 1 enriched graph payloads in PostgreSQL so `QueryGraph` can recover Java/Spring/MyBatis SQL, config, exception, endpoint, and method context after process restart.

**Architecture:** Keep `MiddlewareRouter` as the contract gate and keep `CodeKnowledgeCoreAdapter` as the only Structure 1 boundary. Add a PostgreSQL-backed `GraphStore` inside `legacy_pilot/code_knowledge_core`; `index_repo()` writes the normalized and enriched mapper-ready payload, while `query_graph()` loads it on local cache misses and rebuilds `LocalGraphIndex`. Other structures never connect to PostgreSQL directly and continue to use `QueryGraph -> GraphContext`.

**Tech Stack:** Python 3.13, Pydantic 2, FastAPI, PostgreSQL, `psycopg[binary]`, pytest.

## Global Constraints

- `requires-python = ">=3.13"` from `pyproject.toml`.
- Middleware contract remains unchanged: no new required fields on `RepoIndexRequest`, `GraphQuery`, `GraphSnapshot`, or `GraphContext`.
- PostgreSQL graph storage is a Structure 1 internal backend detail; Incident Context Builder, RCA Reasoning Engine, and Incident Memory & Report Store must not directly connect to it.
- Persist mapper-ready enriched graph payloads, not GitNexus raw payloads.
- First version stores the latest payload per `(repo_id, graph_id)` and does not implement graph history.
- Query output remains `GraphContext`; index output remains `GraphSnapshot`.
- Default behavior remains compatible with existing tests when graph store env vars are not set.

---

## File Structure

- Create `legacy_pilot/code_knowledge_core/graph_store.py`
  Holds graph store interfaces, disabled store, PostgreSQL store, payload hashing, env-driven factory, and graph store errors.
- Modify `legacy_pilot/code_knowledge_core/adapter.py`
  Inject graph store into `GitNexusCliCodeKnowledgeCoreAdapter`, save enriched payload after index, and load persisted payload on local index cache miss.
- Modify `legacy_pilot/code_knowledge_core/__init__.py`
  Export graph store types and factory where useful for tests and future adapter construction.
- Modify `pyproject.toml`
  Add `psycopg[binary]>=3.2.0`.
- Create `tests/test_graph_store.py`
  Unit-test hashing, disabled store behavior, PostgreSQL SQL boundary with a fake connection, and factory selection.
- Modify `tests/test_code_knowledge_core_adapter.py`
  Unit-test that the adapter saves enriched payloads and can query from a persisted payload after a fresh adapter instance starts.
- Create `tests/test_postgres_graph_store_integration.py`
  Opt-in real PostgreSQL round-trip test gated by env vars.
- Modify `README.md`
  Document env vars and the persistence boundary.
- Modify `docs/architecture/milestone5完成和后续.md`
  Replace “planned” wording with the implemented env variables once the implementation lands.

## Interfaces

```python
class GraphStore(ABC):
    @abstractmethod
    def save_payload(self, *, repo_id: str, graph_id: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    def load_payload(self, *, repo_id: str, graph_id: str) -> dict[str, Any] | None: ...
```

```python
def create_graph_store(
    *,
    backend: str | None = None,
    dsn: str | None = None,
    table_name: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> GraphStore:
    ...
```

Environment variables:

```text
LEGACY_PILOT_GRAPH_STORE_BACKEND=disabled | postgresql
LEGACY_PILOT_GRAPH_STORE_DSN=postgresql://user:password@host:5432/database
LEGACY_PILOT_GRAPH_STORE_TABLE=legacy_pilot_graph_payloads
```

PostgreSQL table:

```sql
CREATE TABLE IF NOT EXISTS legacy_pilot_graph_payloads (
    repo_id TEXT NOT NULL,
    graph_id TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    parser_version TEXT NULL,
    semantic_enrichment_version TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (repo_id, graph_id)
);
```

---

### Task 1: Add Graph Store Interface and Disabled Store

**Files:**
- Create: `legacy_pilot/code_knowledge_core/graph_store.py`
- Test: `tests/test_graph_store.py`

**Interfaces:**
- Consumes: mapper-ready graph payloads shaped like the dictionaries passed to `LocalGraphIndex.from_payload()`.
- Produces: `GraphStore`, `DisabledGraphStore`, `GraphStoreError`, `payload_hash(payload: dict[str, Any]) -> str`.

- [ ] **Step 1: Write failing tests for hash stability and disabled store**

Add `tests/test_graph_store.py`:

```python
from legacy_pilot.code_knowledge_core.graph_store import (
    DisabledGraphStore,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_graph_store.py::test_payload_hash_is_stable_for_key_order_changes tests/test_graph_store.py::test_disabled_graph_store_ignores_save_and_loads_nothing -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'legacy_pilot.code_knowledge_core.graph_store'`.

- [ ] **Step 3: Create minimal graph store module**

Create `legacy_pilot/code_knowledge_core/graph_store.py`:

```python
import json
from abc import ABC, abstractmethod
from hashlib import sha256
from typing import Any


class GraphStoreError(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}


class GraphStore(ABC):
    @abstractmethod
    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        ...

    @abstractmethod
    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        ...


class DisabledGraphStore(GraphStore):
    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        return None


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_graph_store.py::test_payload_hash_is_stable_for_key_order_changes tests/test_graph_store.py::test_disabled_graph_store_ignores_save_and_loads_nothing -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add legacy_pilot/code_knowledge_core/graph_store.py tests/test_graph_store.py
git commit -m "feat: add structure1 graph store interface"
```

---

### Task 2: Add PostgreSQL Graph Store and Factory

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/graph_store.py`
- Modify: `legacy_pilot/code_knowledge_core/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_graph_store.py`

**Interfaces:**
- Consumes: `LEGACY_PILOT_GRAPH_STORE_BACKEND`, `LEGACY_PILOT_GRAPH_STORE_DSN`, `LEGACY_PILOT_GRAPH_STORE_TABLE`.
- Produces: `PostgresGraphStore`, `create_graph_store()`.

- [ ] **Step 1: Write failing tests for PostgreSQL save/load and factory**

Append to `tests/test_graph_store.py`:

```python
from datetime import UTC, datetime

from legacy_pilot.code_knowledge_core.graph_store import (
    PostgresGraphStore,
    create_graph_store,
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
    store = PostgresGraphStore(
        dsn="postgresql://example/db",
        table_name="legacy_pilot_graph_payloads_test",
        connect=connector,
        now=lambda: datetime(2026, 6, 23, tzinfo=UTC),
    )
    payload = {
        "repo_id": "repo-a",
        "graph_id": "GRAPH-repo-a",
        "parser_version": "gitnexus_cli+structure1_sql_config_exception_v1",
        "semantic_enrichment_version": None,
        "nodes": [],
        "relationships": [],
    }

    store.save_payload(repo_id="repo-a", graph_id="GRAPH-repo-a", payload=payload)

    assert connector.connections[0][0] == "postgresql://example/db"
    executed_sql = "\n".join(query for query, _ in connector.connections[0][1].executed)
    assert "CREATE TABLE IF NOT EXISTS legacy_pilot_graph_payloads_test" in executed_sql
    assert "ON CONFLICT (repo_id, graph_id) DO UPDATE" in executed_sql


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_graph_store.py -q
```

Expected: FAIL because `PostgresGraphStore` and `create_graph_store` are not defined.

- [ ] **Step 3: Add dependency**

Modify `pyproject.toml` dependencies:

```toml
dependencies = [
  "fastapi>=0.115.0",
  "pydantic>=2.10.0",
  "psycopg[binary]>=3.2.0",
  "PyYAML>=6.0.0",
  "uvicorn>=0.30.0",
]
```

- [ ] **Step 4: Implement PostgreSQL store and factory**

Extend `legacy_pilot/code_knowledge_core/graph_store.py`:

```python
import os
from collections.abc import Callable
from datetime import UTC, datetime


DEFAULT_GRAPH_STORE_TABLE = "legacy_pilot_graph_payloads"


class PostgresGraphStore(GraphStore):
    def __init__(
        self,
        *,
        dsn: str,
        table_name: str = DEFAULT_GRAPH_STORE_TABLE,
        connect: Callable[[str], Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.dsn = dsn
        self.table_name = table_name
        self._connect = connect or _psycopg_connect
        self._now = now or (lambda: datetime.now(UTC))

    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        parser_version = _text_or_none(payload.get("parser_version"))
        semantic_version = _text_or_none(payload.get("semantic_enrichment_version"))
        now = self._now()
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._upsert_sql(),
                        (
                            repo_id,
                            graph_id,
                            _json_payload(payload),
                            payload_hash(payload),
                            parser_version,
                            semantic_version,
                            now,
                            now,
                        ),
                    )
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while saving graph payload.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc

    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._select_sql(),
                        (repo_id, graph_id),
                    )
                    row = cursor.fetchone()
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while loading graph payload.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload)

    def _create_table_sql(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            repo_id TEXT NOT NULL,
            graph_id TEXT NOT NULL,
            payload_json JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            parser_version TEXT NULL,
            semantic_enrichment_version TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (repo_id, graph_id)
        )
        """

    def _upsert_sql(self) -> str:
        return f"""
        INSERT INTO {self.table_name} (
            repo_id,
            graph_id,
            payload_json,
            payload_hash,
            parser_version,
            semantic_enrichment_version,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (repo_id, graph_id) DO UPDATE SET
            payload_json = EXCLUDED.payload_json,
            payload_hash = EXCLUDED.payload_hash,
            parser_version = EXCLUDED.parser_version,
            semantic_enrichment_version = EXCLUDED.semantic_enrichment_version,
            updated_at = EXCLUDED.updated_at
        """

    def _select_sql(self) -> str:
        return f"""
        SELECT payload_json
        FROM {self.table_name}
        WHERE repo_id = %s AND graph_id = %s
        """


def create_graph_store(
    *,
    backend: str | None = None,
    dsn: str | None = None,
    table_name: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> GraphStore:
    selected_backend = (
        backend
        or os.getenv("LEGACY_PILOT_GRAPH_STORE_BACKEND")
        or ("postgresql" if os.getenv("LEGACY_PILOT_GRAPH_STORE_DSN") else "disabled")
    )
    normalized = selected_backend.strip().lower()
    if normalized in {"disabled", "none", "off"}:
        return DisabledGraphStore()
    if normalized in {"postgres", "postgresql"}:
        selected_dsn = dsn or os.getenv("LEGACY_PILOT_GRAPH_STORE_DSN")
        if not selected_dsn:
            raise GraphStoreError(
                "PostgreSQL graph store requires LEGACY_PILOT_GRAPH_STORE_DSN."
            )
        return PostgresGraphStore(
            dsn=selected_dsn,
            table_name=(
                table_name
                or os.getenv("LEGACY_PILOT_GRAPH_STORE_TABLE")
                or DEFAULT_GRAPH_STORE_TABLE
            ),
            now=now,
        )
    raise GraphStoreError(
        f"Unsupported graph store backend: {selected_backend}",
        diagnostics={"backend": selected_backend},
    )


def _json_payload(payload: dict[str, Any]) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return json.dumps(payload, ensure_ascii=False, default=str)
    return Jsonb(payload)


def _psycopg_connect(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
```

- [ ] **Step 5: Export graph store names**

Modify `legacy_pilot/code_knowledge_core/__init__.py`:

```python
from legacy_pilot.code_knowledge_core.graph_store import (
    DisabledGraphStore,
    GraphStore,
    GraphStoreError,
    PostgresGraphStore,
    create_graph_store,
    payload_hash,
)
```

Add these names to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_graph_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml legacy_pilot/code_knowledge_core/graph_store.py legacy_pilot/code_knowledge_core/__init__.py tests/test_graph_store.py
git commit -m "feat: add postgresql graph store"
```

---

### Task 3: Persist Enriched Payloads From Structure 1 Adapter

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Modify: `tests/test_code_knowledge_core_adapter.py`

**Interfaces:**
- Consumes: `GraphStore.save_payload(repo_id, graph_id, payload)`.
- Produces: enriched payload saved after GitNexus normalization, Structure 1 enrichment, and semantic enrichment.

- [ ] **Step 1: Write failing adapter save test**

Add to `tests/test_code_knowledge_core_adapter.py`:

```python
from legacy_pilot.code_knowledge_core.graph_store import DisabledGraphStore


class RecordingGraphStore(DisabledGraphStore):
    def __init__(self, payload_to_load=None):
        self.saved_payloads = []
        self.payload_to_load = payload_to_load
        self.load_calls = []

    def save_payload(self, *, repo_id, graph_id, payload):
        self.saved_payloads.append(
            {"repo_id": repo_id, "graph_id": graph_id, "payload": payload}
        )

    def load_payload(self, *, repo_id, graph_id):
        self.load_calls.append({"repo_id": repo_id, "graph_id": graph_id})
        return self.payload_to_load


def test_gitnexus_adapter_saves_enriched_payload_to_graph_store():
    graph_store = RecordingGraphStore()
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        graph_store=graph_store,
    )
    request = RepoIndexRequest(
        repo_id="repo-store",
        repo_uri="file:///repo-store",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    assert snapshot.graph_id == "GRAPH-repo-store"
    assert graph_store.saved_payloads
    saved = graph_store.saved_payloads[0]
    assert saved["repo_id"] == "repo-store"
    assert saved["graph_id"] == "GRAPH-repo-store"
    assert saved["payload"]["repo_id"] == "repo-store"
    assert saved["payload"]["graph_id"] == "GRAPH-repo-store"
```

Use the existing fake GitNexus client in that test file. If the file does not expose a matching fake with `index_repo()`, add this local fake near the new test:

```python
class FakeGitNexusClient:
    def __init__(self):
        self.query_called = False

    def index_repo(self, request):
        return {
            "repo_id": request.repo_id,
            "graph_id": f"GRAPH-{request.repo_id}",
            "trace_id": f"TRACE-INDEX-{request.repo_id}",
            "nodes": [
                {
                    "id": "Method:src/main/java/DatasetService.java:DatasetService.getVersion#1",
                    "type": "Method",
                    "name": "getVersion",
                    "filePath": "src/main/java/DatasetService.java",
                    "startLine": 1,
                    "endLine": 10,
                    "source_type": "code",
                    "extraction_method": "java_parser",
                    "confidence": 0.9,
                    "properties": {"qualifiedName": "DatasetService.getVersion"},
                }
            ],
            "relationships": [],
        }

    def query_graph(self, query):
        self.query_called = True
        return {
            "graph_id": query.graph_id,
            "nodes": [],
            "relationships": [],
            "paths": [],
            "not_found": True,
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_saves_enriched_payload_to_graph_store -q
```

Expected: FAIL because `GitNexusCliCodeKnowledgeCoreAdapter.__init__()` does not accept `graph_store`.

- [ ] **Step 3: Modify adapter constructor and index path**

In `legacy_pilot/code_knowledge_core/adapter.py`, add imports:

```python
from legacy_pilot.code_knowledge_core.graph_store import (
    GraphStore,
    GraphStoreError,
    create_graph_store,
)
```

Change `GitNexusCliCodeKnowledgeCoreAdapter.__init__` signature:

```python
def __init__(
    self,
    *,
    client: Any | None = None,
    now: Callable[[], datetime] | None = None,
    index_enrichers: list[
        Callable[[RepoIndexRequest], dict[str, Any]]
    ] | None = None,
    query_enrichers: list[Callable[[GraphQuery], dict[str, Any]]] | None = None,
    semantic_enricher: SemanticEnricher | None = None,
    graph_store: GraphStore | None = None,
):
```

Set the store:

```python
self._graph_store = graph_store or create_graph_store(now=self._now)
```

In `index_repo()`, replace the direct `_local_indexes[...] = LocalGraphIndex.from_payload(payload)` block with:

```python
graph_id = _payload_graph_id(payload, request.repo_id)
self._save_persisted_payload(
    repo_id=request.repo_id,
    graph_id=graph_id,
    payload=payload,
)
self._local_indexes[(request.repo_id, graph_id)] = LocalGraphIndex.from_payload(payload)
return map_index_payload(payload, now=self._now)
```

Add helper:

```python
def _save_persisted_payload(
    self,
    *,
    repo_id: str,
    graph_id: str,
    payload: dict[str, Any],
) -> None:
    try:
        self._graph_store.save_payload(
            repo_id=repo_id,
            graph_id=graph_id,
            payload=payload,
        )
    except GraphStoreError as exc:
        raise IndexingError(
            exc.message,
            recoverable=True,
            diagnostics=exc.diagnostics,
        ) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_saves_enriched_payload_to_graph_store -q
```

Expected: PASS.

- [ ] **Step 5: Run adjacent adapter tests**

Run:

```bash
python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add legacy_pilot/code_knowledge_core/adapter.py tests/test_code_knowledge_core_adapter.py
git commit -m "feat: persist structure1 graph payloads"
```

---

### Task 4: Restore LocalGraphIndex From Persisted Payload on Query

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Modify: `tests/test_code_knowledge_core_adapter.py`

**Interfaces:**
- Consumes: `GraphStore.load_payload(repo_id, graph_id) -> dict[str, Any] | None`.
- Produces: `query_graph()` can answer local enriched contexts after adapter restart.

- [ ] **Step 1: Write failing persisted query test**

Add to `tests/test_code_knowledge_core_adapter.py`:

```python
def test_gitnexus_adapter_loads_persisted_payload_when_local_cache_misses():
    persisted_payload = {
        "repo_id": "repo-store",
        "graph_id": "GRAPH-repo-store",
        "trace_id": "TRACE-INDEX-repo-store",
        "nodes": [
            {
                "id": "Method:DatasetService.getVersion",
                "type": "Method",
                "name": "DatasetService.getVersion",
                "qualifiedName": "DatasetService.getVersion",
                "filePath": "src/main/java/DatasetService.java",
                "startLine": 1,
                "endLine": 10,
                "source_type": "code",
                "extraction_method": "java_parser",
                "confidence": 0.9,
            },
            {
                "id": "SQL:selectVersionById",
                "type": "SQL",
                "name": "selectVersionById",
                "source_type": "sql",
                "extraction_method": "regex",
                "confidence": 0.86,
            },
            {
                "id": "Table:dataset_version",
                "type": "Table",
                "name": "dataset_version",
                "source_type": "sql",
                "extraction_method": "regex",
                "confidence": 0.84,
            },
        ],
        "relationships": [
            {
                "id": "R1",
                "source_id": "Method:DatasetService.getVersion",
                "target_id": "SQL:selectVersionById",
                "type": "EXECUTES_SQL",
                "source_type": "sql",
                "extraction_method": "regex",
                "confidence": 0.86,
            },
            {
                "id": "R2",
                "source_id": "SQL:selectVersionById",
                "target_id": "Table:dataset_version",
                "type": "READS_TABLE",
                "source_type": "sql",
                "extraction_method": "regex",
                "confidence": 0.84,
            },
        ],
    }
    graph_store = RecordingGraphStore(payload_to_load=persisted_payload)
    client = FakeGitNexusClient()
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=client,
        graph_store=graph_store,
    )

    context = adapter.query_graph(
        GraphQuery(
            repo_id="repo-store",
            graph_id="GRAPH-repo-store",
            query_terms=["dataset_version"],
            node_filters=["Table"],
            edge_filters=["READS_TABLE"],
            max_depth=4,
            trace_id="TRACE-Q-STORE",
            contract_version="1.0.0",
        )
    )

    assert graph_store.load_calls == [
        {"repo_id": "repo-store", "graph_id": "GRAPH-repo-store"}
    ]
    assert client.query_called is False
    assert any(node.node_id == "Table:dataset_version" for node in context.matched_nodes)
    assert context.graph_paths == [
        [
            "DatasetService.getVersion",
            "selectVersionById",
            "dataset_version",
        ]
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_loads_persisted_payload_when_local_cache_misses -q
```

Expected: FAIL because `query_graph()` does not consult graph store on local cache miss.

- [ ] **Step 3: Add persisted payload load path**

In `legacy_pilot/code_knowledge_core/adapter.py`, update `query_graph()`:

```python
def query_graph(self, query: GraphQuery) -> GraphContext:
    local_payload = self._query_local_index(query)
    if local_payload is not None and local_payload.get("not_found") is not True:
        return map_query_payload(
            self._with_query_enrichers(local_payload, query),
            query=query,
            now=self._now,
        )

    restored_payload = self._load_persisted_payload(query)
    if restored_payload is not None:
        self._local_indexes[(query.repo_id, query.graph_id)] = LocalGraphIndex.from_payload(
            restored_payload
        )
        local_payload = self._query_local_index(query)
        if local_payload is not None and local_payload.get("not_found") is not True:
            return map_query_payload(
                self._with_query_enrichers(local_payload, query),
                query=query,
                now=self._now,
            )

    payload = self._client.query_graph(query)
    payload = self._with_query_enrichers(payload, query)
    return map_query_payload(payload, query=query, now=self._now)
```

Add helper:

```python
def _load_persisted_payload(self, query: GraphQuery) -> dict[str, Any] | None:
    try:
        return self._graph_store.load_payload(
            repo_id=query.repo_id,
            graph_id=query.graph_id,
        )
    except GraphStoreError as exc:
        raise QueryError(
            exc.message,
            recoverable=True,
            diagnostics=exc.diagnostics,
        ) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_loads_persisted_payload_when_local_cache_misses -q
```

Expected: PASS.

- [ ] **Step 5: Run production fixture tests**

Run:

```bash
python -m pytest tests/test_structure1_production_fixture.py tests/test_local_graph_index.py tests/test_query_planner.py -q -rs
```

Expected: PASS, with GitNexus opt-in tests skipped unless env vars are set.

- [ ] **Step 6: Commit**

```bash
git add legacy_pilot/code_knowledge_core/adapter.py tests/test_code_knowledge_core_adapter.py
git commit -m "feat: restore structure1 graph index from store"
```

---

### Task 5: Add Opt-In PostgreSQL Integration Test and Documentation

**Files:**
- Create: `tests/test_postgres_graph_store_integration.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/architecture/milestone5完成和后续.md`

**Interfaces:**
- Consumes: `LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE=1`, `LEGACY_PILOT_GRAPH_STORE_DSN`.
- Produces: documented opt-in verification for real PostgreSQL.

- [ ] **Step 1: Add pytest marker**

Modify `pyproject.toml` marker list:

```toml
markers = [
  "gitnexus_integration: requires local GitNexus runtime and is skipped by default",
  "postgres_graph_store: requires PostgreSQL and is skipped by default",
  "structure1_production: runs full Structure 1 Java/Spring fixture coverage",
  "slow: longer-running integration or performance tests",
  "qwen_semantic_integration: requires DashScope Qwen API access and is skipped by default",
]
```

- [ ] **Step 2: Add opt-in integration test**

Create `tests/test_postgres_graph_store_integration.py`:

```python
import os
from datetime import UTC, datetime

import pytest

from legacy_pilot.code_knowledge_core.graph_store import PostgresGraphStore


pytestmark = pytest.mark.postgres_graph_store


def test_real_postgres_graph_store_round_trips_payload():
    if os.getenv("LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE") != "1":
        pytest.skip(
            "PostgreSQL graph store integration is opt-in; set "
            "LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE=1 and LEGACY_PILOT_GRAPH_STORE_DSN."
        )
    dsn = os.environ.get("LEGACY_PILOT_GRAPH_STORE_DSN")
    if not dsn:
        pytest.skip("LEGACY_PILOT_GRAPH_STORE_DSN is required.")

    table_name = os.getenv(
        "LEGACY_PILOT_GRAPH_STORE_TEST_TABLE",
        "legacy_pilot_graph_payloads_test",
    )
    store = PostgresGraphStore(
        dsn=dsn,
        table_name=table_name,
        now=lambda: datetime(2026, 6, 23, tzinfo=UTC),
    )
    payload = {
        "repo_id": "repo-postgres-test",
        "graph_id": "GRAPH-repo-postgres-test",
        "parser_version": "test-parser-v1",
        "semantic_enrichment_version": None,
        "nodes": [
            {
                "id": "Method:DatasetService.getVersion",
                "type": "Method",
                "name": "DatasetService.getVersion",
            }
        ],
        "relationships": [],
    }

    store.save_payload(
        repo_id="repo-postgres-test",
        graph_id="GRAPH-repo-postgres-test",
        payload=payload,
    )

    assert store.load_payload(
        repo_id="repo-postgres-test",
        graph_id="GRAPH-repo-postgres-test",
    ) == payload
```

- [ ] **Step 3: Run default graph store tests**

Run:

```bash
python -m pytest tests/test_graph_store.py tests/test_postgres_graph_store_integration.py -q -rs
```

Expected: unit tests PASS; PostgreSQL integration SKIPPED unless env vars are set.

- [ ] **Step 4: Run opt-in PostgreSQL integration**

Run when a test database is available:

```bash
set LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE=1
set LEGACY_PILOT_GRAPH_STORE_DSN=postgresql://legacy_pilot:legacy_pilot@127.0.0.1:5432/legacy_pilot_test
python -m pytest tests/test_postgres_graph_store_integration.py -q -rs
```

Expected: PASS against the configured PostgreSQL database.

- [ ] **Step 5: Document env vars and boundary**

Add to `README.md` under Structure 1 controls:

````markdown
### Structure 1 PostgreSQL Graph Store

Graph persistence is disabled by default. Enable it only for Structure 1:

```powershell
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:5432/legacy_pilot'
$env:LEGACY_PILOT_GRAPH_STORE_TABLE='legacy_pilot_graph_payloads'
```

`IndexRepo` persists the normalized and enriched mapper-ready graph payload.
`QueryGraph` first checks the in-process `LocalGraphIndex`, then reloads the
payload from PostgreSQL and rebuilds the local index on cache miss. Other
LegacyPilot structures must not connect to this database directly; they still
use `/v1/graph/query`.
```
````

Update `docs/architecture/milestone5完成和后续.md` wording from planned to implemented once all tests pass.

- [ ] **Step 6: Run full default suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS for default suite; opt-in GitNexus, Qwen, and PostgreSQL tests SKIPPED unless enabled.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml README.md docs/architecture/milestone5完成和后续.md tests/test_postgres_graph_store_integration.py
git commit -m "test: add postgresql graph store integration coverage"
```

---

## Self-Review

Spec coverage:

- PostgreSQL graph store is inside Structure 1 and not a cross-structure database: covered by Tasks 2, 3, 5.
- Existing middleware contract stays unchanged: covered by adapter-only changes in Tasks 3 and 4.
- Persist latest enriched payload, not raw GitNexus payload: covered by Task 3 save position after enrichment and semantic enrichment.
- Restore query after local cache miss: covered by Task 4.
- Default tests remain compatible without PostgreSQL: covered by disabled default store in Task 2 and skipped integration in Task 5.

Red flag scan:

- No unresolved requirement markers.
- No references to functions missing from earlier tasks.
- Graph store method names are consistent: `save_payload`, `load_payload`, `create_graph_store`.

Execution handoff:

Plan complete and saved to `docs/superpowers/plans/2026-06-23-structure1-postgresql-graph-store.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.
