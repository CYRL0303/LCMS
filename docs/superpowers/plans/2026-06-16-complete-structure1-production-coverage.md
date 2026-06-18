# Complete Structure 1 Production Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Structure 1 beyond the current Java/Spring GitNexus CLI MVP by adding SQL, config, exception, semantic graph, and production-grade coverage while preserving LCMS middleware contracts.

**Architecture:** Keep `MiddlewareRouter` as the contract gate and keep `CodeKnowledgeCoreAdapter` as the only Structure 1 boundary. Use real GitNexus CLI for structural Java/Spring graph facts, then enrich the normalized payload with focused Python extractors for SQL/MyBatis, config, and exceptions. Add an opt-in semantic enrichment stage that produces evidence-backed LCMS nodes/edges without making LLM output a trusted structural fact by default.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, subprocess GitNexus CLI, `xml.etree.ElementTree`, `configparser`, optional `PyYAML`, optional LLM backend configured by environment.

---

## Scope

This plan completes the full Structure 1 target from `docs/architecture/legacy-pilot-four-structures.md`:

```text
File / Package / Class / Method / API Endpoint / Service / Mapper / SQL / Table / Config / Exception
DECLARES / CALLS / MAPS_TO_ENDPOINT / USES_MAPPER / EXECUTES_SQL / READS_TABLE / WRITES_TABLE / THROWS_EXCEPTION / MENTIONED_IN_LOG / IMPLEMENTS
```

It does not make RCA decisions, generate RCA reports, save incident memory, or modify production code.

## File Map

Create:

```text
legacy_pilot/code_knowledge_core/enrichment.py
legacy_pilot/code_knowledge_core/extractors/__init__.py
legacy_pilot/code_knowledge_core/extractors/java_sql.py
legacy_pilot/code_knowledge_core/extractors/java_config.py
legacy_pilot/code_knowledge_core/extractors/java_exception.py
legacy_pilot/code_knowledge_core/semantic.py
legacy_pilot/code_knowledge_core/query_planner.py
tests/test_code_knowledge_enrichment.py
tests/test_java_sql_extractor.py
tests/test_java_config_extractor.py
tests/test_java_exception_extractor.py
tests/test_semantic_enrichment.py
tests/test_structure1_production_fixture.py
tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/DatasetController.java
tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/DatasetService.java
tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/DatasetMapper.java
tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/DatasetNotFoundException.java
tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/GlobalExceptionHandler.java
tests/fixtures/java_spring_production_demo/src/main/resources/mapper/DatasetMapper.xml
tests/fixtures/java_spring_production_demo/src/main/resources/application.yml
```

Modify:

```text
legacy_pilot/contracts/models.py
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
legacy_pilot/middleware/router.py
pyproject.toml
README.md
docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
docs/architecture/实现结构1对齐真实gitnexus-api改造.md
```

## Acceptance Criteria

The implementation is complete when these commands pass:

```powershell
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
```

And this opt-in real integration passes on the local GitNexus checkout:

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_TIMEOUT_SECONDS='120'
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -q -rs
```

The production fixture must prove this path:

```text
/api/dataset/version
-> DatasetController.getVersion
-> DatasetService.getVersion
-> DatasetMapper.selectVersionById
-> DatasetMapper.xml selectVersionById
-> dataset_version table
```

And it must also prove:

```text
application.yml config node is indexed.
DatasetNotFoundException node is indexed.
DatasetService.getVersion THROWS_EXCEPTION DatasetNotFoundException.
LLM semantic nodes are absent by default and present only when semantic enrichment is explicitly enabled.
Every returned Edge has evidence_refs.
Every EvidenceRef has the correct source_type: code, sql, config, or llm_semantic_summary.
```

---

## Task 0: Reconfirm Real GitNexus CLI Capabilities

**Files:**
- Review: `legacy_pilot/code_knowledge_core/gitnexus_client.py`
- Review: `tests/test_gitnexus_integration.py`
- Document: `docs/architecture/实现结构1对齐真实gitnexus-api改造.md`

- [ ] **Step 1: Run GitNexus schema inspection commands**

Run:

```powershell
Q:\tmp\gitnexus-local.cmd status
Q:\tmp\gitnexus-local.cmd cypher "MATCH (n) RETURN n.id, n.name, n.filePath LIMIT 20" -r repo-java-spring-demo
Q:\tmp\gitnexus-local.cmd cypher "MATCH (n)-[r]->(m) RETURN n.id, r.type, r.confidence, r.reason, m.id LIMIT 50" -r repo-java-spring-demo
```

Expected:

```text
Commands return JSON wrappers with markdown table output.
Method/Class/File node ids remain stable enough for adapter mapping.
```

- [ ] **Step 2: Record the real CLI contract**

Update `docs/architecture/实现结构1对齐真实gitnexus-api改造.md` with the exact observed fields for:

```text
cypher markdown table headers
context symbol fields
incoming.calls fields
outgoing.calls fields
known GitNexus FTS/query limitations
```

- [ ] **Step 3: Run current baseline**

Run:

```powershell
python -m pytest tests/test_gitnexus_client.py tests/test_gitnexus_mapper.py tests/test_gitnexus_integration.py -q -rs
```

Expected:

```text
Unit tests pass.
Integration tests are skipped unless GitNexus env is set.
```

---

## Task 1: Add Backward-Compatible Structure 1 Contract Metadata

**Files:**
- Modify: `legacy_pilot/contracts/models.py`
- Test: `tests/test_contract_models.py`

- [ ] **Step 1: Write contract tests**

Add tests that assert `GraphSnapshot` can carry parser and semantic metadata without changing required fields:

```python
def test_graph_snapshot_accepts_structure1_versions():
    snapshot = GraphSnapshot(
        graph_id="GRAPH-1",
        repo_id="repo-1",
        nodes=[],
        edges=[],
        evidence_refs=[],
        generated_at=datetime.now(UTC),
        parser_version="gitnexus_cli+structure1_sql_v1",
        semantic_enrichment_version=None,
        metadata={"structure": "code_knowledge_core"},
    )

    assert snapshot.parser_version == "gitnexus_cli+structure1_sql_v1"
    assert snapshot.semantic_enrichment_version is None
    assert snapshot.metadata["structure"] == "code_knowledge_core"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_contract_models.py::test_graph_snapshot_accepts_structure1_versions -q
```

Expected:

```text
FAIL because GraphSnapshot has no parser_version / semantic_enrichment_version / metadata fields.
```

- [ ] **Step 3: Add optional fields**

Modify `GraphSnapshot` in `legacy_pilot/contracts/models.py`:

```python
class GraphSnapshot(ContractModel):
    graph_id: str
    repo_id: str
    nodes: list[Node]
    edges: list[Edge]
    evidence_refs: list[EvidenceRef]
    generated_at: datetime
    parser_version: str | None = None
    semantic_enrichment_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_contract_models.py -q
```

Expected:

```text
All contract model tests pass.
```

---

## Task 2: Generalize Evidence Source Types In The Mapper

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/gitnexus_mapper.py`
- Test: `tests/test_gitnexus_mapper.py`

- [ ] **Step 1: Write mapper tests for non-code evidence**

Add tests:

```python
def test_sql_node_maps_to_sql_evidence_source_type():
    node = map_gitnexus_node(
        {
            "id": "SQL:mapper/DatasetMapper.xml:selectVersionById",
            "type": "SQL",
            "name": "selectVersionById",
            "filePath": "src/main/resources/mapper/DatasetMapper.xml",
            "startLine": 5,
            "endLine": 9,
            "source_type": "sql",
            "extraction_method": "regex",
        },
        graph_id="GRAPH-1",
        repo_id="repo-1",
        trace_id="TRACE-1",
        now=fixed_now,
    )

    assert node.evidence_refs[0].source_type == "sql"
    assert node.evidence_refs[0].extraction_method == "regex"


def test_config_node_maps_to_config_evidence_source_type():
    node = map_gitnexus_node(
        {
            "id": "Config:src/main/resources/application.yml:spring.datasource.url",
            "type": "Config",
            "name": "spring.datasource.url",
            "filePath": "src/main/resources/application.yml",
            "startLine": 2,
            "endLine": 2,
            "source_type": "config",
            "extraction_method": "regex",
        },
        graph_id="GRAPH-1",
        repo_id="repo-1",
        trace_id="TRACE-1",
        now=fixed_now,
    )

    assert node.evidence_refs[0].source_type == "config"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_gitnexus_mapper.py::test_sql_node_maps_to_sql_evidence_source_type tests/test_gitnexus_mapper.py::test_config_node_maps_to_config_evidence_source_type -q
```

Expected:

```text
FAIL because _evidence_ref always uses SourceType.CODE.
```

- [ ] **Step 3: Implement source_type mapping**

Change `_evidence_ref()` to accept `source_type`.

```python
def _source_type(payload: dict[str, Any]) -> SourceType | str:
    properties = _properties(payload)
    return (
        _get_any(payload, "source_type", "sourceType")
        or _get_any(properties, "source_type", "sourceType")
        or SourceType.CODE
    )
```

Pass `source_type=_source_type(payload)` from `map_gitnexus_node()` and `map_gitnexus_edge()`.

- [ ] **Step 4: Run mapper tests**

Run:

```powershell
python -m pytest tests/test_gitnexus_mapper.py -q
```

Expected:

```text
All mapper tests pass.
```

---

## Task 3: Add Enrichment Pipeline

**Files:**
- Create: `legacy_pilot/code_knowledge_core/enrichment.py`
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Test: `tests/test_code_knowledge_enrichment.py`

- [ ] **Step 1: Write tests for payload enrichment**

Add:

```python
def test_enrichment_combines_gitnexus_and_extractor_payloads():
    base_payload = {
        "repo_id": "repo-1",
        "graph_id": "GRAPH-repo-1",
        "trace_id": "TRACE-INDEX-repo-1",
        "nodes": [{"id": "Method:DatasetService.getVersion", "type": "Method"}],
        "relationships": [],
    }
    sql_payload = {
        "nodes": [{"id": "SQL:DatasetMapper.selectVersionById", "type": "SQL"}],
        "relationships": [
            {
                "id": "REL-1",
                "source_id": "Method:DatasetService.getVersion",
                "target_id": "SQL:DatasetMapper.selectVersionById",
                "type": "EXECUTES_SQL",
            }
        ],
    }

    enriched = merge_graph_payloads(base_payload, [sql_payload])

    assert [node["id"] for node in enriched["nodes"]] == [
        "Method:DatasetService.getVersion",
        "SQL:DatasetMapper.selectVersionById",
    ]
    assert enriched["relationships"][0]["type"] == "EXECUTES_SQL"
```

- [ ] **Step 2: Implement merge helper**

Create `legacy_pilot/code_knowledge_core/enrichment.py`:

```python
from typing import Any


def merge_graph_payloads(
    base_payload: dict[str, Any],
    enrichment_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes_by_id = {
        str(node.get("id")): dict(node)
        for node in base_payload.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    relationships_by_id = {
        str(edge.get("id")): dict(edge)
        for edge in base_payload.get("relationships", [])
        if isinstance(edge, dict) and edge.get("id")
    }

    for payload in enrichment_payloads:
        for node in payload.get("nodes", []):
            if isinstance(node, dict) and node.get("id"):
                nodes_by_id.setdefault(str(node["id"]), dict(node))
        for edge in payload.get("relationships", []):
            if isinstance(edge, dict) and edge.get("id"):
                relationships_by_id.setdefault(str(edge["id"]), dict(edge))

    enriched = dict(base_payload)
    enriched["nodes"] = list(nodes_by_id.values())
    enriched["relationships"] = list(relationships_by_id.values())
    return enriched
```

- [ ] **Step 3: Wire adapter constructor but keep behavior unchanged**

Modify `GitNexusCliCodeKnowledgeCoreAdapter` to accept optional enrichment callables:

```python
class GitNexusCliCodeKnowledgeCoreAdapter(CodeKnowledgeCoreAdapter):
    def __init__(
        self,
        *,
        client: Any | None = None,
        now: Callable[[], datetime] | None = None,
        index_enrichers: list[Callable[[RepoIndexRequest], dict[str, Any]]] | None = None,
        query_enrichers: list[Callable[[GraphQuery], dict[str, Any]]] | None = None,
    ):
        self._client = client or GitNexusCliClient()
        self._now = now or (lambda: datetime.now(UTC))
        self._index_enrichers = index_enrichers or []
        self._query_enrichers = query_enrichers or []
```

Use `merge_graph_payloads()` before mapping.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_code_knowledge_enrichment.py tests/test_code_knowledge_core_adapter.py -q
```

Expected:

```text
All tests pass.
Existing adapter behavior stays unchanged when no enrichers are configured.
```

---

## Task 4: Add MyBatis / SQL Extractor

**Files:**
- Create: `legacy_pilot/code_knowledge_core/extractors/java_sql.py`
- Create: `tests/test_java_sql_extractor.py`
- Add fixture: `tests/fixtures/java_spring_production_demo/src/main/resources/mapper/DatasetMapper.xml`

- [ ] **Step 1: Add fixture XML**

Create `DatasetMapper.xml`:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<mapper namespace="com.legacy.DatasetMapper">
  <select id="selectVersionById" resultType="string">
    SELECT version
    FROM dataset_version
    WHERE dataset_id = #{datasetId}
  </select>
</mapper>
```

- [ ] **Step 2: Write extractor tests**

Add:

```python
def test_extracts_mapper_sql_and_table_edges():
    payload = extract_mybatis_sql_graph(FIXTURE_ROOT, repo_id="repo-prod", graph_id="GRAPH-prod")

    node_ids = {node["id"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["relationships"]}

    assert "MapperXml:src/main/resources/mapper/DatasetMapper.xml:selectVersionById" in node_ids
    assert "Table:dataset_version" in node_ids
    assert "EXECUTES_SQL" in edge_types
    assert "READS_TABLE" in edge_types
```

- [ ] **Step 3: Implement XML parsing**

Implement:

```python
from pathlib import Path
from xml.etree import ElementTree


def extract_mybatis_sql_graph(repo_root: Path, *, repo_id: str, graph_id: str) -> dict:
    nodes = []
    relationships = []
    for xml_path in repo_root.rglob("*.xml"):
        tree = ElementTree.parse(xml_path)
        root = tree.getroot()
        if root.tag != "mapper":
            continue
        namespace = root.attrib.get("namespace", "")
        for statement in root:
            if statement.tag not in {"select", "insert", "update", "delete"}:
                continue
            statement_id = statement.attrib.get("id", "")
            sql_text = " ".join("".join(statement.itertext()).split())
            table_names = _table_names(sql_text, statement.tag)
            statement_node_id = f"MapperXml:{_relpath(repo_root, xml_path)}:{statement_id}"
            nodes.append(_sql_node(statement_node_id, statement_id, xml_path, sql_text))
            mapper_method_id = f"Method:src/main/java/com/legacy/DatasetMapper.java:DatasetMapper.{statement_id}#1"
            relationships.append(_edge(mapper_method_id, "EXECUTES_SQL", statement_node_id))
            for table_name in table_names:
                table_node_id = f"Table:{table_name}"
                nodes.append(_table_node(table_node_id, table_name, xml_path, sql_text))
                relationships.append(_edge(statement_node_id, _table_edge_type(statement.tag), table_node_id))
    return {"repo_id": repo_id, "graph_id": graph_id, "nodes": nodes, "relationships": relationships}
```

Use regex helpers for `FROM`, `JOIN`, `UPDATE`, and `INTO` table extraction.

- [ ] **Step 4: Run SQL extractor tests**

Run:

```powershell
python -m pytest tests/test_java_sql_extractor.py -q
```

Expected:

```text
SQL statement node, table node, EXECUTES_SQL edge, and READS_TABLE edge are produced.
```

---

## Task 5: Add Config Extractor

**Files:**
- Create: `legacy_pilot/code_knowledge_core/extractors/java_config.py`
- Create: `tests/test_java_config_extractor.py`
- Add fixture: `tests/fixtures/java_spring_production_demo/src/main/resources/application.yml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

Add to `pyproject.toml` dependencies:

```toml
"PyYAML>=6.0.0",
```

- [ ] **Step 2: Add config fixture**

Create:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/legacy
    username: legacy_user
legacy:
  dataset:
    cache-enabled: true
```

- [ ] **Step 3: Write config extractor tests**

Add:

```python
def test_extracts_application_yml_config_nodes():
    payload = extract_java_config_graph(FIXTURE_ROOT, repo_id="repo-prod", graph_id="GRAPH-prod")

    names = {node["name"] for node in payload["nodes"]}
    assert "spring.datasource.url" in names
    assert "legacy.dataset.cache-enabled" in names
    assert all(node["source_type"] == "config" for node in payload["nodes"])
```

- [ ] **Step 4: Implement extractor**

Implement flattening for `.yml`, `.yaml`, and `.properties`:

```python
def extract_java_config_graph(repo_root: Path, *, repo_id: str, graph_id: str) -> dict:
    nodes = []
    for path in list(repo_root.rglob("application.yml")) + list(repo_root.rglob("application.yaml")):
        for key, value, line in _flatten_yaml_file(path):
            nodes.append(_config_node(repo_root, path, key, value, line))
    for path in repo_root.rglob("application.properties"):
        for key, value, line in _read_properties(path):
            nodes.append(_config_node(repo_root, path, key, value, line))
    return {"repo_id": repo_id, "graph_id": graph_id, "nodes": nodes, "relationships": []}
```

- [ ] **Step 5: Run config tests**

Run:

```powershell
python -m pytest tests/test_java_config_extractor.py -q
```

Expected:

```text
Config nodes are produced with source_type=config and file evidence.
```

---

## Task 6: Add Java Exception Extractor

**Files:**
- Create: `legacy_pilot/code_knowledge_core/extractors/java_exception.py`
- Create: `tests/test_java_exception_extractor.py`
- Add fixtures:
  - `tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/DatasetNotFoundException.java`
  - `tests/fixtures/java_spring_production_demo/src/main/java/com/legacy/GlobalExceptionHandler.java`

- [ ] **Step 1: Add exception fixtures**

Create `DatasetNotFoundException.java`:

```java
package com.legacy;

public class DatasetNotFoundException extends RuntimeException {
    public DatasetNotFoundException(String datasetId) {
        super("Dataset not found: " + datasetId);
    }
}
```

Create `GlobalExceptionHandler.java`:

```java
package com.legacy;

import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(DatasetNotFoundException.class)
    public String handleDatasetNotFound(DatasetNotFoundException exception) {
        return exception.getMessage();
    }
}
```

- [ ] **Step 2: Write exception extractor tests**

Add:

```python
def test_extracts_exception_nodes_and_throw_edges():
    payload = extract_java_exception_graph(FIXTURE_ROOT, repo_id="repo-prod", graph_id="GRAPH-prod")

    node_ids = {node["id"] for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["relationships"]}

    assert "Exception:src/main/java/com/legacy/DatasetNotFoundException.java:DatasetNotFoundException" in node_ids
    assert "THROWS_EXCEPTION" in edge_types
```

- [ ] **Step 3: Implement extractor**

Implement regex-based Java extraction:

```python
EXCEPTION_CLASS_RE = re.compile(r"class\s+(\w+Exception)\s+extends\s+(\w+Exception)")
THROW_RE = re.compile(r"throw\s+new\s+(\w+Exception)\s*\(")
HANDLER_RE = re.compile(r"@ExceptionHandler\s*\(\s*(\w+Exception)\.class\s*\)")
```

Produce:

```text
Exception nodes for exception classes.
THROWS_EXCEPTION edges from method-like source ids to exception nodes.
HANDLES_EXCEPTION edges from handler methods to exception nodes.
```

- [ ] **Step 4: Run exception tests**

Run:

```powershell
python -m pytest tests/test_java_exception_extractor.py -q
```

Expected:

```text
Exception nodes and THROWS_EXCEPTION / HANDLES_EXCEPTION edges are produced with code evidence.
```

---

## Task 7: Integrate SQL / Config / Exception Enrichers Into Real Adapter

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Modify: `legacy_pilot/code_knowledge_core/gitnexus_client.py`
- Modify: `tests/test_code_knowledge_core_adapter.py`
- Test: `tests/test_structure1_production_fixture.py`

- [ ] **Step 1: Add repo_root to normalized index payload**

Modify `GitNexusCliClient.index_repo()` return payload:

```python
payload = self._normalize_cypher_graph_payload(raw_payload, request=request)
payload["repo_path"] = _repo_path(request.repo_uri)
return payload
```

- [ ] **Step 2: Wire default enrichers for gitnexus_cli**

Create factory helper:

```python
def _default_structure1_enrichers():
    return [
        lambda request: extract_mybatis_sql_graph(Path(_repo_path(request.repo_uri)), repo_id=request.repo_id, graph_id=f"GRAPH-{request.repo_id}"),
        lambda request: extract_java_config_graph(Path(_repo_path(request.repo_uri)), repo_id=request.repo_id, graph_id=f"GRAPH-{request.repo_id}"),
        lambda request: extract_java_exception_graph(Path(_repo_path(request.repo_uri)), repo_id=request.repo_id, graph_id=f"GRAPH-{request.repo_id}"),
    ]
```

Use these only for `gitnexus_cli`, not for mock.

- [ ] **Step 3: Write production fixture tests**

Add:

```python
def test_index_repo_includes_sql_config_and_exception_nodes():
    adapter = _gitnexus_adapter_or_skip()
    snapshot = _index_production_fixture(adapter)

    node_types = {node.type for node in snapshot.nodes}
    edge_types = {edge.type for edge in snapshot.edges}
    source_types = {evidence.source_type for evidence in snapshot.evidence_refs}

    assert "SQL" in node_types
    assert "Table" in node_types
    assert "Config" in node_types
    assert "Exception" in node_types
    assert "EXECUTES_SQL" in edge_types
    assert "READS_TABLE" in edge_types
    assert "THROWS_EXCEPTION" in edge_types
    assert {"code", "sql", "config"}.issubset(source_types)
```

- [ ] **Step 4: Run production fixture test**

Run:

```powershell
python -m pytest tests/test_structure1_production_fixture.py -q -rs
```

Expected:

```text
Skipped by default when GitNexus integration env is absent.
Passes when env is configured.
```

---

## Task 8: Add Query Planner For Node And Edge Filters

**Files:**
- Create: `legacy_pilot/code_knowledge_core/query_planner.py`
- Modify: `legacy_pilot/code_knowledge_core/gitnexus_client.py`
- Test: `tests/test_query_planner.py`
- Test: `tests/test_gitnexus_client.py`

- [ ] **Step 1: Write query planner tests**

Add:

```python
def test_query_planner_routes_sql_terms_to_sql_lookup():
    query = GraphQuery(
        repo_id="repo-prod",
        graph_id="GRAPH-prod",
        query_terms=["dataset_version"],
        node_filters=["Table"],
        edge_filters=["READS_TABLE"],
        max_depth=4,
        trace_id="TRACE-SQL",
        contract_version="1.0.0",
    )

    plan = plan_graph_query(query)

    assert plan.kind == "sql"
    assert plan.term == "dataset_version"
```

Also cover:

```text
route term -> route_context
DatasetService.getVersion -> symbol_context
node_filters=["Exception"] -> exception_lookup
edge_filters contains "impact" -> impact_query
```

- [ ] **Step 2: Implement planner dataclass**

Implement:

```python
@dataclass(frozen=True)
class GraphQueryPlan:
    kind: Literal["route_context", "symbol_context", "sql", "config", "exception", "impact", "keyword"]
    term: str
```

Use deterministic rules:

```text
term starts with "/" -> route_context
node_filters contains "Table" or "SQL" -> sql
node_filters contains "Config" -> config
node_filters contains "Exception" -> exception
edge_filters contains "impact" -> impact
term contains "." -> symbol_context
otherwise -> keyword
```

- [ ] **Step 3: Wire planner into GitNexus client**

`GitNexusCliClient.query_graph()` should use planner before resolving UID. Initial implementation can return not_found for config/sql/exception until Task 9 adds local query index.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_query_planner.py tests/test_gitnexus_client.py -q
```

Expected:

```text
Planner behavior is deterministic.
Existing route/symbol query behavior remains unchanged.
```

---

## Task 9: Add Local Enriched Graph Query Index

**Files:**
- Create: `legacy_pilot/code_knowledge_core/local_graph_index.py`
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Test: `tests/test_local_graph_index.py`
- Test: `tests/test_structure1_production_fixture.py`

- [ ] **Step 1: Write local query tests**

Add:

```python
def test_local_graph_index_finds_table_and_path():
    index = LocalGraphIndex.from_payload(
        {
            "nodes": [
                {"id": "Method:DatasetService.getVersion", "type": "Method", "name": "getVersion"},
                {"id": "SQL:selectVersionById", "type": "SQL", "name": "selectVersionById"},
                {"id": "Table:dataset_version", "type": "Table", "name": "dataset_version"},
            ],
            "relationships": [
                {"id": "R1", "source_id": "Method:DatasetService.getVersion", "target_id": "SQL:selectVersionById", "type": "EXECUTES_SQL"},
                {"id": "R2", "source_id": "SQL:selectVersionById", "target_id": "Table:dataset_version", "type": "READS_TABLE"},
            ],
        }
    )

    result = index.query(term="dataset_version", node_filters=["Table"], edge_filters=["READS_TABLE"], max_depth=4)

    assert result["nodes"][0]["id"] == "Table:dataset_version"
    assert result["paths"][0] == [
        "Method:DatasetService.getVersion",
        "SQL:selectVersionById",
        "Table:dataset_version",
    ]
```

- [ ] **Step 2: Implement in-memory graph index**

Implement:

```python
class LocalGraphIndex:
    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LocalGraphIndex": ...
    def query(self, *, term: str, node_filters: list[str], edge_filters: list[str], max_depth: int) -> dict[str, Any]: ...
```

Use BFS up to `max_depth`, filter nodes by `type`, filter edges by `type`, and return mapper-ready payload.

- [ ] **Step 3: Store enriched payload per adapter instance**

When `index_repo()` succeeds, keep the enriched payload in memory by `repo_id` and `graph_id`.

When `query_graph()` planner returns `sql`, `config`, or `exception`, query the local enriched graph index before falling back to GitNexus context.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_local_graph_index.py tests/test_structure1_production_fixture.py -q -rs
```

Expected:

```text
SQL/table/config/exception queries return GraphContext using enriched graph data.
```

---

## Task 10: Add Optional Semantic Enrichment

**Files:**
- Create: `legacy_pilot/code_knowledge_core/semantic.py`
- Create: `tests/test_semantic_enrichment.py`
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Modify: `README.md`

- [ ] **Step 1: Add disabled-by-default behavior test**

Add:

```python
def test_semantic_enrichment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)

    enricher = create_semantic_enricher()

    assert isinstance(enricher, DisabledSemanticEnricher)
    assert enricher.enrich([]) == {"nodes": [], "relationships": []}
```

- [ ] **Step 2: Add deterministic mock semantic test**

Add:

```python
def test_mock_semantic_enricher_creates_pending_summary_node(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "mock")
    enricher = create_semantic_enricher()

    payload = enricher.enrich(
        [
            {
                "id": "Method:DatasetService.getVersion",
                "type": "Method",
                "name": "getVersion",
                "filePath": "src/main/java/com/legacy/DatasetService.java",
                "startLine": 10,
                "endLine": 20,
            }
        ]
    )

    assert payload["nodes"][0]["type"] == "Function Semantic Summary"
    assert payload["nodes"][0]["source_type"] == "llm_semantic_summary"
    assert payload["nodes"][0]["properties"]["verification_status"] == "pending"
```

- [ ] **Step 3: Implement semantic interfaces**

Implement:

```python
class SemanticEnricher(Protocol):
    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]: ...


class DisabledSemanticEnricher:
    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {"nodes": [], "relationships": []}


class MockSemanticEnricher:
    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        ...
```

Environment:

```text
LEGACY_PILOT_SEMANTIC_BACKEND=disabled|mock|qwen_api
LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP=0.7
```

`qwen_api` is the real LLM backend for this milestone. `ollama` is reserved for
future local-model experiments and is not part of the Structure 1 production
coverage acceptance path.

- [ ] **Step 4: Enforce semantic safety**

Semantic nodes must use:

```text
source_type = llm_semantic_summary
extraction_method = llm
confidence <= LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP
metadata.verification_status = pending
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_semantic_enrichment.py tests/test_gitnexus_mapper.py -q
```

Expected:

```text
Semantic enrichment is opt-in and evidence-backed.
```

---

## Task 11: Add Production Hardening

**Files:**
- Modify: `legacy_pilot/code_knowledge_core/gitnexus_client.py`
- Modify: `legacy_pilot/code_knowledge_core/adapter.py`
- Test: `tests/test_gitnexus_client.py`
- Test: `tests/test_code_knowledge_core_adapter.py`

- [ ] **Step 1: Add path and repo validation tests**

Add tests for:

```text
repo_uri must resolve to a local path.
repo_uri path must exist before GitNexus analyze.
GitNexus failures do not return mock data.
GitNexus diagnostics are stored but not exposed as HTTP message text.
```

- [ ] **Step 2: Add graph size limit tests**

Add:

```python
def test_index_payload_respects_node_and_edge_limits():
    client = GitNexusCliClient(max_graph_nodes=2, max_graph_edges=1, runner=runner_with_large_cypher_result)
    payload = client.index_repo(repo_index_request())

    assert len(payload["nodes"]) <= 2
    assert len(payload["relationships"]) <= 1
```

- [ ] **Step 3: Add stable index mode**

Support:

```text
LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE=0|1
```

Behavior:

```text
1: always run analyze before cypher.
0: run cypher first; if no graph rows are returned, run analyze and retry cypher once.
```

- [ ] **Step 4: Add timeout categories**

Support:

```text
GITNEXUS_INDEX_TIMEOUT_SECONDS=120
GITNEXUS_QUERY_TIMEOUT_SECONDS=30
```

Use index timeout for `analyze`; use query timeout for `cypher/context/trace/impact`.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_gitnexus_client.py tests/test_code_knowledge_core_adapter.py -q
```

Expected:

```text
Hardening behavior is deterministic and does not require real GitNexus.
```

---

## Task 12: Add Production-Grade Integration And CI Profiles

**Files:**
- Modify: `tests/test_gitnexus_integration.py`
- Modify: `tests/test_structure1_production_fixture.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: Add pytest markers**

Modify `pyproject.toml`:

```toml
markers = [
  "gitnexus_integration: requires local GitNexus runtime and is skipped by default",
  "structure1_production: runs full Structure 1 Java/Spring fixture coverage",
  "slow: longer-running integration or performance tests",
]
```

- [ ] **Step 2: Add production integration tests**

Add tests that assert:

```text
GraphSnapshot contains Method, Mapper, SQL, Table, Config, Exception nodes.
GraphSnapshot contains CALLS, EXECUTES_SQL, READS_TABLE, THROWS_EXCEPTION edges.
QueryGraph by endpoint returns controller-service-mapper-sql-table path.
QueryGraph by table name returns table and upstream SQL/mapper/service context.
QueryGraph by config key returns Config node with config evidence.
QueryGraph by exception name returns Exception node and throwing method.
Every edge has evidence_refs.
Every graph-level evidence_ref is deduplicated.
```

- [ ] **Step 3: Add cache ignore rules**

Modify `.gitignore`:

```text
tests/fixtures/java_spring_demo/.gitnexus/
tests/fixtures/java_spring_production_demo/.gitnexus/
.pytest_cache/
```

- [ ] **Step 4: Add CI instructions**

Document two profiles:

```text
Default CI:
python -m pytest -q

GitNexus integration CI:
build GitNexus
set GITNEXUS_BIN
set GITNEXUS_REPO_ROOT
set LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -q -rs
```

- [ ] **Step 5: Run final verification**

Run:

```powershell
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
```

Expected:

```text
All default tests pass.
Real GitNexus tests are skipped unless enabled.
No whitespace errors.
```

---

## Delivery Milestones

### Milestone 1: Contract And Enrichment Foundation

Includes Tasks 0-3.

Acceptance:

```text
Existing MVP still passes.
Mapper supports code/sql/config/llm evidence source types.
Adapter can merge GitNexus payload with enrichment payloads.
```

### Milestone 2: SQL / Config / Exception Structural Coverage

Includes Tasks 4-7.

Acceptance:

```text
Production fixture index returns SQL, Table, Config, and Exception nodes.
Edges include EXECUTES_SQL, READS_TABLE, THROWS_EXCEPTION.
No semantic enrichment is required.
```

### Milestone 3: Query Coverage

Includes Tasks 8-9.

Acceptance:

```text
GraphQuery can retrieve endpoint, method, table, config, and exception contexts.
graph_paths include controller-service-mapper-sql-table where fixture supports it.
```

### Milestone 4: Semantic Graph

Includes Task 10.

Acceptance:

```text
Semantic enrichment is disabled by default.
Mock semantic backend is deterministic.
LLM semantic nodes are pending, confidence-capped, and evidence-backed.
```

### Milestone 5: Production Hardening

Includes Tasks 11-12.

Acceptance:

```text
Default tests pass without GitNexus.
Opt-in real GitNexus tests pass on local runtime.
Docs state exact real GitNexus paths and coverage boundaries.
```

## Risks And Controls

```text
Risk: GitNexus CLI markdown output changes.
Control: Keep CLI parsing isolated in gitnexus_client.py and cover table parsing with unit tests.

Risk: SQL extraction via regex misses complex SQL.
Control: First support simple MyBatis XML SELECT/INSERT/UPDATE/DELETE, then add optional sqlparse or dialect parser after fixture coverage is stable.

Risk: LLM semantic graph pollutes structural facts.
Control: Keep semantic enrichment opt-in, confidence-capped, pending verification, and source_type=llm_semantic_summary.

Risk: In-memory local graph index is not durable across process restarts.
Control: Treat it as first production fixture coverage; add persistent cache only after behavior is stable.

Risk: Production repos are large.
Control: Add node/edge limits, query timeout categories, and production fixture before broad repo testing.
```
