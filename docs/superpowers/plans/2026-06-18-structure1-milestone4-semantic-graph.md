# Structure 1 Milestone4 Semantic Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Milestone4 for Structure 1 by adding an opt-in semantic graph enrichment stage that is disabled by default, deterministic in mock mode, pending verification, confidence-capped, and evidence-backed.

**Architecture:** Keep `MiddlewareRouter` as the contract gate and keep `CodeKnowledgeCoreAdapter` as the only Structure 1 boundary. Semantic enrichment runs inside `GitNexusCliCodeKnowledgeCoreAdapter.index_repo()` after GitNexus and structural enrichers have produced mapper-ready payload nodes, then merges semantic nodes/edges back through `merge_graph_payloads()` so all output still flows through `gitnexus_mapper.py` and LCMS contract models. LLM output is not treated as a trusted structural fact: semantic nodes use `source_type=llm_semantic_summary`, `extraction_method=llm`, `metadata.verification_status=pending`, and confidence no higher than the configured cap.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing `GitNexusCliCodeKnowledgeCoreAdapter`, existing `merge_graph_payloads()`, existing LCMS `GraphSnapshot` / `Node` / `Edge` / `EvidenceRef` contracts, optional semantic backend selected by environment.

## Global Constraints

- Do not modify `legacy_pilot/middleware/router.py`; `contract_version` and `trace_id` gates remain in middleware.
- Do not modify the four-structure interface contract shape; `GraphSnapshot.semantic_enrichment_version` and `GraphSnapshot.metadata` already exist and must be used as backward-compatible optional fields.
- Do not make semantic enrichment run by default; absent `LEGACY_PILOT_SEMANTIC_BACKEND` must mean disabled.
- Do not call real LLM services in default tests; Milestone4 acceptance requires deterministic `mock` semantic behavior only.
- Do not let LLM semantic output become structural truth; semantic facts must be pending, confidence-capped, and evidence-backed.
- Do not add dependencies for Milestone4; use standard library only.
- Preserve current Milestone0-3 behavior and tests.

---

## File Structure

Create:

```text
legacy_pilot/code_knowledge_core/semantic.py
tests/test_semantic_enrichment.py
```

Modify:

```text
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/code_knowledge_core/__init__.py
tests/test_code_knowledge_core_adapter.py
tests/test_structure1_production_fixture.py
README.md
docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
```

Do not modify:

```text
legacy_pilot/middleware/router.py
legacy_pilot/contracts/models.py
legacy_pilot/contracts/enums.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
```

The existing mapper already supports `source_type=llm_semantic_summary`, `extraction_method=llm`, and `semantic_enrichment_version`.

---

### Task 1: Semantic Enricher Module

**Files:**
- Create: `legacy_pilot/code_knowledge_core/semantic.py`
- Create: `tests/test_semantic_enrichment.py`

**Interfaces:**
- Consumes: mapper-ready node payloads: `list[dict[str, Any]]`
- Produces: `create_semantic_enricher(backend: str | None = None, confidence_cap: float | None = None) -> SemanticEnricher`
- Produces: `DisabledSemanticEnricher.enrich(nodes: list[dict[str, Any]]) -> dict[str, Any]`
- Produces: `MockSemanticEnricher.enrich(nodes: list[dict[str, Any]]) -> dict[str, Any]`
- Produces payload shape accepted by `merge_graph_payloads()` and `map_index_payload()`: `{"nodes": [...], "relationships": [...]}`

- [ ] **Step 1: Write disabled-by-default tests**

Add to `tests/test_semantic_enrichment.py`:

```python
from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    create_semantic_enricher,
)


def test_semantic_enrichment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)

    enricher = create_semantic_enricher()

    assert isinstance(enricher, DisabledSemanticEnricher)
    assert enricher.semantic_enrichment_version is None
    assert enricher.enrich([_method_node()]) == {"nodes": [], "relationships": []}
```

- [ ] **Step 2: Write deterministic mock semantic tests**

Continue `tests/test_semantic_enrichment.py`:

```python
def test_mock_semantic_enricher_creates_pending_summary_node(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "mock")
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP", "0.42")

    enricher = create_semantic_enricher()
    payload = enricher.enrich([_method_node()])

    assert payload["nodes"] == [
        {
            "id": "SemanticSummary:Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "type": "Function Semantic Summary",
            "name": "DatasetService.getVersion semantic summary",
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 12,
            "endLine": 18,
            "excerpt": "Mock semantic summary for DatasetService.getVersion.",
            "source_type": "llm_semantic_summary",
            "extraction_method": "llm",
            "confidence": 0.42,
            "properties": {
                "source_node_id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
                "summary": "Mock semantic summary for DatasetService.getVersion.",
                "evidence_span": "DatasetService.getVersion",
                "prompt_version": "mock_semantic_v1",
                "verification_status": "pending",
            },
        }
    ]
    assert payload["relationships"] == [
        {
            "id": "SEM-REL-Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "source_id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "target_id": "SemanticSummary:Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "type": "HAS_SEMANTIC_ACTION",
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 12,
            "endLine": 18,
            "excerpt": "Mock semantic summary for DatasetService.getVersion.",
            "source_type": "llm_semantic_summary",
            "extraction_method": "llm",
            "confidence": 0.42,
            "properties": {
                "verification_status": "pending",
                "prompt_version": "mock_semantic_v1",
            },
        }
    ]


def test_mock_semantic_enricher_skips_nodes_without_file_evidence():
    from legacy_pilot.code_knowledge_core.semantic import MockSemanticEnricher

    enricher = MockSemanticEnricher(confidence_cap=0.7)

    payload = enricher.enrich(
        [
            {
                "id": "Method:NoLocation",
                "type": "Method",
                "name": "NoLocation",
            }
        ]
    )

    assert payload == {"nodes": [], "relationships": []}
```

Use this helper in the same test file:

```python
def _method_node():
    return {
        "id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
        "type": "Method",
        "name": "DatasetService.getVersion",
        "filePath": "src/main/java/com/legacy/DatasetService.java",
        "startLine": 12,
        "endLine": 18,
        "excerpt": "return datasetMapper.selectVersionById(datasetId);",
        "confidence": 0.91,
    }
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_semantic_enrichment.py -q
```

Expected:

```text
FAIL because legacy_pilot.code_knowledge_core.semantic does not exist.
```

- [ ] **Step 4: Implement semantic module**

Create `legacy_pilot/code_knowledge_core/semantic.py`:

```python
import os
from dataclasses import dataclass
from typing import Any, Protocol


SEMANTIC_BACKEND_ENV = "LEGACY_PILOT_SEMANTIC_BACKEND"
SEMANTIC_CONFIDENCE_CAP_ENV = "LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP"
MOCK_SEMANTIC_ENRICHMENT_VERSION = "semantic_mock_v1"
MOCK_PROMPT_VERSION = "mock_semantic_v1"
DEFAULT_CONFIDENCE_CAP = 0.7
SEMANTIC_NODE_TYPE = "Function Semantic Summary"
SEMANTIC_EDGE_TYPE = "HAS_SEMANTIC_ACTION"
SEMANTIC_SOURCE_TYPE = "llm_semantic_summary"


class SemanticEnricher(Protocol):
    semantic_enrichment_version: str | None
    backend_name: str
    confidence_cap: float | None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class DisabledSemanticEnricher:
    semantic_enrichment_version: str | None = None
    backend_name: str = "disabled"
    confidence_cap: float | None = None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {"nodes": [], "relationships": []}


@dataclass(frozen=True)
class MockSemanticEnricher:
    confidence_cap: float = DEFAULT_CONFIDENCE_CAP
    semantic_enrichment_version: str | None = MOCK_SEMANTIC_ENRICHMENT_VERSION
    backend_name: str = "mock"

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        semantic_nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict) or not _is_semantic_candidate(node):
                continue
            file_path = _string_value(_get_nested(node, "filePath", "file_path"))
            if file_path is None:
                continue
            node_id = _string_value(_get_nested(node, "id", "node_id", "nodeId"))
            if node_id is None:
                continue
            name = _string_value(_get_nested(node, "name")) or node_id
            start_line = _int_value(_get_nested(node, "startLine", "start_line"))
            end_line = _int_value(_get_nested(node, "endLine", "end_line"))
            summary = f"Mock semantic summary for {name}."
            semantic_node_id = f"SemanticSummary:{node_id}"
            semantic_nodes.append(
                {
                    "id": semantic_node_id,
                    "type": SEMANTIC_NODE_TYPE,
                    "name": f"{name} semantic summary",
                    "filePath": file_path,
                    "startLine": start_line,
                    "endLine": end_line,
                    "excerpt": summary,
                    "source_type": SEMANTIC_SOURCE_TYPE,
                    "extraction_method": "llm",
                    "confidence": self.confidence_cap,
                    "properties": {
                        "source_node_id": node_id,
                        "summary": summary,
                        "evidence_span": name,
                        "prompt_version": MOCK_PROMPT_VERSION,
                        "verification_status": "pending",
                    },
                }
            )
            relationships.append(
                {
                    "id": f"SEM-REL-{node_id}",
                    "source_id": node_id,
                    "target_id": semantic_node_id,
                    "type": SEMANTIC_EDGE_TYPE,
                    "filePath": file_path,
                    "startLine": start_line,
                    "endLine": end_line,
                    "excerpt": summary,
                    "source_type": SEMANTIC_SOURCE_TYPE,
                    "extraction_method": "llm",
                    "confidence": self.confidence_cap,
                    "properties": {
                        "verification_status": "pending",
                        "prompt_version": MOCK_PROMPT_VERSION,
                    },
                }
            )
        return {"nodes": semantic_nodes, "relationships": relationships}


@dataclass(frozen=True)
class UnsupportedSemanticEnricher:
    backend_name: str
    semantic_enrichment_version: str | None = None
    confidence_cap: float | None = None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        raise ValueError(f"Unsupported semantic backend: {self.backend_name}")


def create_semantic_enricher(
    *,
    backend: str | None = None,
    confidence_cap: float | None = None,
) -> SemanticEnricher:
    selected_backend = (backend or os.getenv(SEMANTIC_BACKEND_ENV) or "disabled").strip().lower()
    cap = _confidence_cap(confidence_cap)
    if selected_backend in {"", "disabled", "none", "off"}:
        return DisabledSemanticEnricher()
    if selected_backend == "mock":
        return MockSemanticEnricher(confidence_cap=cap)
    return UnsupportedSemanticEnricher(backend_name=selected_backend)


def _confidence_cap(value: float | None) -> float:
    if value is None:
        raw = os.getenv(SEMANTIC_CONFIDENCE_CAP_ENV)
        if raw is None:
            return DEFAULT_CONFIDENCE_CAP
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_CONFIDENCE_CAP
    return min(max(float(value), 0.0), 1.0)


def _is_semantic_candidate(node: dict[str, Any]) -> bool:
    node_type = _string_value(_get_nested(node, "type", "node_type", "nodeType"))
    return node_type in {"Method", "Mapper", "API Endpoint", "Service"}


def _get_nested(source: dict[str, Any], *keys: str) -> Any:
    properties = source.get("properties")
    property_source = properties if isinstance(properties, dict) else {}
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
        value = property_source.get(key)
        if value is not None:
            return value
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 5: Run semantic tests**

Run:

```powershell
python -m pytest tests/test_semantic_enrichment.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add legacy_pilot/code_knowledge_core/semantic.py tests/test_semantic_enrichment.py
git commit -m "feat(code-knowledge): add semantic enricher module"
```

---

### Task 2: Adapter Semantic Integration

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Modify: `legacy_pilot/code_knowledge_core/__init__.py`
- Modify: `tests/test_code_knowledge_core_adapter.py`

**Interfaces:**
- Consumes from Task 1: `SemanticEnricher`, `DisabledSemanticEnricher`, `MockSemanticEnricher`, `create_semantic_enricher`
- Produces: `GitNexusCliCodeKnowledgeCoreAdapter(..., semantic_enricher: SemanticEnricher | None = None)`
- Produces: `_with_semantic_enrichment(payload: dict[str, Any], semantic_enricher: SemanticEnricher) -> dict[str, Any]`
- Keeps adapter public boundary unchanged: `index_repo(RepoIndexRequest) -> GraphSnapshot`, `query_graph(GraphQuery) -> GraphContext`

- [ ] **Step 1: Write adapter tests for default disabled behavior**

Add to `tests/test_code_knowledge_core_adapter.py`:

```python
def test_gitnexus_adapter_does_not_add_semantic_nodes_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    assert "Function Semantic Summary" not in {node.type for node in snapshot.nodes}
    assert "HAS_SEMANTIC_ACTION" not in {edge.type for edge in snapshot.edges}
    assert snapshot.semantic_enrichment_version is None
```

- [ ] **Step 2: Write adapter tests for explicit mock semantic behavior**

Add below the previous test:

```python
def test_gitnexus_adapter_adds_mock_semantic_nodes_when_enabled():
    from legacy_pilot.code_knowledge_core.semantic import MockSemanticEnricher

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        semantic_enricher=MockSemanticEnricher(confidence_cap=0.42),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    snapshot = adapter.index_repo(request)

    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    semantic_evidence = [
        evidence
        for evidence in snapshot.evidence_refs
        if evidence.source_type == "llm_semantic_summary"
    ]

    assert "Function Semantic Summary" in node_types
    assert "HAS_SEMANTIC_ACTION" in edge_types
    assert snapshot.semantic_enrichment_version == "semantic_mock_v1"
    assert snapshot.metadata["semantic_enrichment"] == {
        "backend": "mock",
        "version": "semantic_mock_v1",
        "verification_status": "pending",
        "confidence_cap": 0.42,
    }
    assert semantic_evidence
    assert all(evidence.extraction_method == "llm" for evidence in semantic_evidence)
    assert all(evidence.confidence <= 0.42 for evidence in semantic_evidence)
```

- [ ] **Step 3: Write adapter error conversion test**

Add:

```python
def test_gitnexus_adapter_wraps_semantic_failures_as_indexing_error():
    class RaisingSemanticEnricher:
        semantic_enrichment_version = "semantic_raising_v1"
        backend_name = "raising"
        confidence_cap = 0.7

        def enrich(self, nodes: list[dict]) -> dict:
            raise RuntimeError("semantic backend failed")

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeGitNexusClient(),
        index_enrichers=[],
        semantic_enricher=RaisingSemanticEnricher(),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    request = RepoIndexRequest(
        repo_id="repo-real",
        repo_uri="file:///repo-real",
        language_hint="java",
        parser_profile="spring-boot",
        contract_version="1.0.0",
    )

    with pytest.raises(IndexingError) as excinfo:
        adapter.index_repo(request)

    assert excinfo.value.message == "Structure 1 semantic enrichment failed while indexing repo."
    assert excinfo.value.recoverable is True
    assert excinfo.value.diagnostics == {
        "semantic_backend": "raising",
        "error_type": "RuntimeError",
    }
```

- [ ] **Step 4: Run adapter tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_does_not_add_semantic_nodes_by_default tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_adds_mock_semantic_nodes_when_enabled tests/test_code_knowledge_core_adapter.py::test_gitnexus_adapter_wraps_semantic_failures_as_indexing_error -q
```

Expected:

```text
FAIL because GitNexusCliCodeKnowledgeCoreAdapter does not accept semantic_enricher and does not run semantic enrichment.
```

- [ ] **Step 5: Wire semantic enrichment into adapter**

Modify imports in `legacy_pilot/code_knowledge_core/adapter.py`:

```python
from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    SemanticEnricher,
    create_semantic_enricher,
)
```

Modify `GitNexusCliCodeKnowledgeCoreAdapter.__init__` signature and body:

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
    ):
        self._client = client or GitNexusCliClient()
        self._now = now or (lambda: datetime.now(UTC))
        uses_default_index_enrichers = index_enrichers is None
        self._index_enrichers = (
            index_enrichers
            if not uses_default_index_enrichers
            else _default_structure1_enrichers()
        )
        self._index_enrichment_sources = (
            list(DEFAULT_STRUCTURE1_ENRICHMENT_SOURCES)
            if uses_default_index_enrichers
            else [_enricher_name(enricher) for enricher in self._index_enrichers]
        )
        self._index_parser_version = (
            STRUCTURE1_ENRICHED_PARSER_VERSION if uses_default_index_enrichers else None
        )
        self._query_enrichers = query_enrichers or []
        self._semantic_enricher = semantic_enricher or create_semantic_enricher()
        self._local_indexes: dict[tuple[str, str], LocalGraphIndex] = {}
```

Modify `GitNexusCliCodeKnowledgeCoreAdapter.index_repo()` before storing `_local_indexes`:

```python
        payload = _with_semantic_enrichment(payload, self._semantic_enricher)
        self._local_indexes[
            (request.repo_id, _payload_graph_id(payload, request.repo_id))
        ] = LocalGraphIndex.from_payload(payload)
        return map_index_payload(payload, now=self._now)
```

Add helper functions in `legacy_pilot/code_knowledge_core/adapter.py` after `_with_enrichment_metadata()`:

```python
def _with_semantic_enrichment(
    payload: dict[str, Any],
    semantic_enricher: SemanticEnricher,
) -> dict[str, Any]:
    if isinstance(semantic_enricher, DisabledSemanticEnricher):
        enriched = dict(payload)
        enriched.setdefault("semantic_enrichment_version", None)
        return enriched
    try:
        semantic_payload = semantic_enricher.enrich(
            [
                node
                for node in payload.get("nodes", [])
                if isinstance(node, dict)
            ]
        )
    except CodeKnowledgeCoreError:
        raise
    except Exception as exc:
        raise IndexingError(
            "Structure 1 semantic enrichment failed while indexing repo.",
            recoverable=True,
            diagnostics={
                "semantic_backend": getattr(semantic_enricher, "backend_name", semantic_enricher.__class__.__name__),
                "error_type": exc.__class__.__name__,
            },
        ) from exc

    enriched = merge_graph_payloads(payload, [semantic_payload])
    version = getattr(semantic_enricher, "semantic_enrichment_version", None)
    enriched["semantic_enrichment_version"] = version
    metadata = enriched.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata["semantic_enrichment"] = {
        "backend": getattr(semantic_enricher, "backend_name", semantic_enricher.__class__.__name__),
        "version": version,
        "verification_status": "pending",
        "confidence_cap": getattr(semantic_enricher, "confidence_cap", None),
    }
    enriched["metadata"] = metadata
    return enriched
```

- [ ] **Step 6: Export semantic helpers**

Modify `legacy_pilot/code_knowledge_core/__init__.py`:

```python
from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    MockSemanticEnricher,
    SemanticEnricher,
    create_semantic_enricher,
)
```

Add to `__all__`:

```python
    "DisabledSemanticEnricher",
    "MockSemanticEnricher",
    "SemanticEnricher",
    "create_semantic_enricher",
```

- [ ] **Step 7: Run adapter and semantic tests**

Run:

```powershell
python -m pytest tests/test_semantic_enrichment.py tests/test_code_knowledge_core_adapter.py tests/test_gitnexus_mapper.py -q
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add legacy_pilot/code_knowledge_core/adapter.py legacy_pilot/code_knowledge_core/__init__.py tests/test_code_knowledge_core_adapter.py
git commit -m "feat(code-knowledge): wire semantic enrichment into adapter"
```

---

### Task 3: Production Fixture Semantic Coverage

**Files:**
- Modify: `tests/test_structure1_production_fixture.py`

**Interfaces:**
- Consumes from Task 2: `GitNexusCliCodeKnowledgeCoreAdapter(..., semantic_enricher=MockSemanticEnricher(...))`
- Produces tests proving semantic nodes are absent by default and present only when explicitly enabled.

- [ ] **Step 1: Add datetime imports for semantic fixture tests**

Modify the imports at the top of `tests/test_structure1_production_fixture.py`:

```python
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
```

- [ ] **Step 2: Write production fixture default-disabled assertion**

In `tests/test_structure1_production_fixture.py`, add or extend the existing production fixture index test:

```python
def test_production_fixture_has_no_semantic_nodes_by_default():
    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeProductionGitNexusClient(),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    snapshot = adapter.index_repo(_production_fixture_request())

    assert "Function Semantic Summary" not in {node.type for node in snapshot.nodes}
    assert "HAS_SEMANTIC_ACTION" not in {edge.type for edge in snapshot.edges}
    assert snapshot.semantic_enrichment_version is None
```

- [ ] **Step 3: Write production fixture explicit mock semantic assertion**

Add:

```python
def test_production_fixture_has_mock_semantic_nodes_when_explicitly_enabled():
    from legacy_pilot.code_knowledge_core.semantic import MockSemanticEnricher

    adapter = GitNexusCliCodeKnowledgeCoreAdapter(
        client=FakeProductionGitNexusClient(),
        semantic_enricher=MockSemanticEnricher(confidence_cap=0.55),
        now=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    snapshot = adapter.index_repo(_production_fixture_request())

    semantic_nodes = [
        node for node in snapshot.nodes if node.type == "Function Semantic Summary"
    ]
    semantic_edges = [
        edge for edge in snapshot.edges if edge.type == "HAS_SEMANTIC_ACTION"
    ]
    semantic_evidence = [
        evidence
        for evidence in snapshot.evidence_refs
        if evidence.source_type == "llm_semantic_summary"
    ]

    assert semantic_nodes
    assert semantic_edges
    assert snapshot.semantic_enrichment_version == "semantic_mock_v1"
    assert snapshot.metadata["semantic_enrichment"] == {
        "backend": "mock",
        "version": "semantic_mock_v1",
        "verification_status": "pending",
        "confidence_cap": 0.55,
    }
    assert all(
        node.metadata["gitnexus"]["properties"]["verification_status"] == "pending"
        for node in semantic_nodes
    )
    assert semantic_evidence
    assert all(evidence.extraction_method == "llm" for evidence in semantic_evidence)
    assert all(evidence.confidence <= 0.55 for evidence in semantic_evidence)
```

- [ ] **Step 4: Run production fixture tests to verify they fail before implementation**

Run:

```powershell
python -m pytest tests/test_structure1_production_fixture.py::test_production_fixture_has_no_semantic_nodes_by_default tests/test_structure1_production_fixture.py::test_production_fixture_has_mock_semantic_nodes_when_explicitly_enabled -q
```

Expected:

```text
FAIL until adapter semantic integration from Task 2 is present.
```

- [ ] **Step 5: Run production fixture tests**

Run:

```powershell
python -m pytest tests/test_structure1_production_fixture.py -q -rs
```

Expected:

```text
All default production fixture tests pass; real GitNexus tests remain skipped unless integration env is enabled.
```

- [ ] **Step 6: Run real GitNexus integration with semantic disabled**

Run:

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_TIMEOUT_SECONDS='120'
Remove-Item Env:\LEGACY_PILOT_SEMANTIC_BACKEND -ErrorAction SilentlyContinue
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -vv -x -rs
```

Expected:

```text
All enabled real GitNexus tests pass with semantic enrichment disabled by default.
```

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add tests/test_structure1_production_fixture.py
git commit -m "test(code-knowledge): cover semantic production fixture behavior"
```

---

### Task 4: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/code-knowledge-core-gitnexus-adapter-design.md`

**Interfaces:**
- Documents environment variables:
  - `LEGACY_PILOT_SEMANTIC_BACKEND=disabled|mock`
  - `LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP=0.7`
- Documents that `ollama` and `qwen_api` are reserved backend names and are not accepted as Milestone4 verified behavior unless implemented with tests in a separate task.

- [ ] **Step 1: Update README semantic section**

Add to `README.md` near the Structure 1 backend notes:

````markdown
### Structure 1 semantic enrichment

Semantic enrichment is disabled by default.

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='disabled'
```

The deterministic test backend can be enabled explicitly:

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='mock'
$env:LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP='0.7'
```

Semantic nodes are LCMS graph nodes with `type="Function Semantic Summary"`.
They are always evidence-backed with `source_type="llm_semantic_summary"`,
`extraction_method="llm"`, `verification_status="pending"`, and confidence no
higher than `LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP`.
They are not trusted structural facts and do not replace GitNexus structural
nodes or SQL/config/exception enrichers.
````

- [ ] **Step 2: Update architecture doc**

Add to `docs/architecture/code-knowledge-core-gitnexus-adapter-design.md`:

````markdown
## Semantic Enrichment Boundary

Milestone4 keeps semantic enrichment inside Code Knowledge Core. The HTTP
middleware still sees only LCMS contract models and continues to own
`contract_version` and `trace_id` validation.

Index flow:

```text
GitNexusCliClient.index_repo()
-> structural enrichers: SQL / config / exception
-> semantic enricher: disabled by default, mock when explicitly enabled
-> merge_graph_payloads()
-> gitnexus_mapper.map_index_payload()
-> GraphSnapshot
```

Semantic enrichment is not a parser replacement. It creates pending semantic
nodes and `HAS_SEMANTIC_ACTION` edges with `source_type=llm_semantic_summary`,
`extraction_method=llm`, and capped confidence. Structural graph facts continue
to come from GitNexus plus deterministic SQL/config/exception extractors.
````

- [ ] **Step 3: Run targeted verification**

Run:

```powershell
python -m pytest tests/test_semantic_enrichment.py tests/test_code_knowledge_core_adapter.py tests/test_gitnexus_mapper.py tests/test_structure1_production_fixture.py -q -rs
```

Expected:

```text
All selected tests pass; opt-in GitNexus tests skip unless integration env is enabled.
```

- [ ] **Step 4: Run full default verification**

Run:

```powershell
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
```

Expected:

```text
All default tests pass.
compileall succeeds.
git diff --check reports no whitespace errors.
```

- [ ] **Step 5: Confirm middleware and contract files were not changed**

Run:

```powershell
git diff --name-only HEAD -- legacy_pilot/middleware legacy_pilot/contracts
```

Expected:

```text
No output.
```

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add README.md docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
git commit -m "docs(code-knowledge): document semantic enrichment boundary"
```

---

## Milestone4 Acceptance

Milestone4 is complete when these are true:

```text
Semantic enrichment is disabled by default.
Mock semantic backend is deterministic.
Semantic graph nodes and HAS_SEMANTIC_ACTION edges appear only when semantic enrichment is explicitly enabled.
Semantic EvidenceRef.source_type is llm_semantic_summary.
Semantic EvidenceRef.extraction_method is llm.
Semantic confidence is capped by LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP.
Semantic node metadata has verification_status=pending.
GraphSnapshot.semantic_enrichment_version is None when disabled and semantic_mock_v1 when mock is enabled.
No middleware/router changes.
No four-structure contract shape changes.
```

Verification commands:

```powershell
python -m pytest tests/test_semantic_enrichment.py tests/test_code_knowledge_core_adapter.py tests/test_gitnexus_mapper.py tests/test_structure1_production_fixture.py -q -rs
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
git diff --name-only HEAD -- legacy_pilot/middleware legacy_pilot/contracts
```

Optional real GitNexus verification:

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_TIMEOUT_SECONDS='120'
Remove-Item Env:\LEGACY_PILOT_SEMANTIC_BACKEND -ErrorAction SilentlyContinue
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -vv -x -rs
```

## Self-Review Notes

Spec coverage:

```text
Disabled by default: Task 1 and Task 2 tests.
Deterministic mock backend: Task 1 tests and implementation.
Pending verification: Task 1 payload properties and Task 3 production assertions.
Confidence cap: Task 1, Task 2, and Task 3 assertions.
Evidence-backed LLM source type: Task 2 and Task 3 evidence assertions.
Middleware/contract boundary: Global Constraints and Task 4 verification.
Production fixture proof: Task 3.
Docs: Task 4.
```

Type consistency:

```text
SemanticEnricher.enrich() returns mapper-ready payload dict.
GitNexusCliCodeKnowledgeCoreAdapter constructor keeps existing parameters and adds optional semantic_enricher.
GraphSnapshot.semantic_enrichment_version uses existing optional contract field.
Node metadata receives semantic properties through existing gitnexus mapper metadata path.
```
