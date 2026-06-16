# GitNexus CLI Adapter Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LegacyPilot Structure 1 actually run against the real GitNexus CLI and return LCMS `GraphSnapshot` / `GraphContext` objects.

**Architecture:** Keep `MiddlewareRouter` as the contract gate and keep `CodeKnowledgeCoreAdapter` as the Structure 1 boundary. Replace the current assumed `gitnexus index --repo-id ...` / `gitnexus query --repo-id ...` command shape with the real CLI flow: `analyze` builds the index, `cypher` extracts graph nodes/edges, and `context` / `trace` / `cypher` support query graph results. Mapper output remains LCMS-only.

**Tech Stack:** Python 3.13, pytest, Pydantic v2, subprocess-based GitNexus CLI, real GitNexus commands `analyze`, `cypher`, `context`, and `trace`.

---

## Current Evidence

Real CLI was built and tested with `Q:\tmp\gitnexus-local.cmd`.

Observed real CLI behavior:

```text
gitnexus analyze . --skip-git --index-only --name legacy-pilot-java-spring-demo --force
-> Repository indexed successfully
-> 21 nodes | 30 edges | 1 clusters | 1 flows
```

LegacyPilot integration currently fails because the client calls:

```text
gitnexus index --repo-id ... --repo-path ...
```

Real GitNexus rejects that with:

```text
error: unknown option '--repo-id'
```

Real Graph evidence exists and can be queried:

```text
DatasetController.getVersion
-> DatasetService.getVersion
-> DatasetMapper.selectVersionById
```

---

## File Structure

Modify:

```text
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_gitnexus_client.py
tests/test_gitnexus_mapper.py
tests/test_gitnexus_integration.py
docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
README.md
```

No changes:

```text
legacy_pilot/middleware/router.py
legacy_pilot/middleware/app.py
legacy_pilot/contracts/models.py
```

Generated test artifacts:

```text
tests/fixtures/java_spring_demo/.gitnexus
```

Decision needed during implementation: either ignore this generated folder in `.gitignore` or remove it after integration testing. Do not commit `.gitnexus`.

---

## Task 1: Capture Real CLI Command Contract In Unit Tests

**Files:**

```text
Modify: tests/test_gitnexus_client.py
Modify: legacy_pilot/code_knowledge_core/gitnexus_client.py
```

- [ ] **Step 1: Write failing test for real index command shape**

Change the existing index command test so it expects `analyze`, not `index --repo-id`.

Expected command shape:

```python
assert command[:2] == ["custom-gitnexus", "analyze"]
assert "/workspace/legacy-demo" in command
assert "--skip-git" in command
assert "--index-only" in command
assert "--name" in command
assert "repo-demo" in command
```

- [ ] **Step 2: Run test and verify it fails**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_index_command_uses_real_gitnexus_analyze_shape -q
```

Expected: fails because current command starts with `["gitnexus", "index"]`.

- [ ] **Step 3: Implement minimal command change**

In `GitNexusCliClient.index_repo()`, replace current `index` command with:

```python
command = [
    self.gitnexus_bin,
    "analyze",
    _repo_path(request.repo_uri),
    "--skip-git",
    "--index-only",
    "--name",
    request.repo_id,
]
```

Keep `--force` optional behind a constructor/env flag if needed; do not force by default in production.

- [ ] **Step 4: Run test and verify it passes**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_index_command_uses_real_gitnexus_analyze_shape -q
```

Expected: pass.

---

## Task 2: Extract GraphSnapshot From Real GitNexus Cypher

**Files:**

```text
Modify: legacy_pilot/code_knowledge_core/gitnexus_client.py
Modify: tests/test_gitnexus_client.py
```

- [ ] **Step 1: Write failing test for post-analyze cypher extraction**

Use `RecordingRunner` with two subprocess results:

1. `analyze` returns human stdout.
2. `cypher` returns JSON containing markdown rows from:

```text
MATCH (n)-[r]->(m) RETURN n.id, r.type, r.confidence, r.reason, m.id LIMIT 200
```

Expected normalized payload:

```python
assert payload["repo_id"] == "repo-demo"
assert payload["graph_id"] == "GRAPH-repo-demo"
assert payload["relationships"][0]["type"] == "CALLS"
assert payload["relationships"][0]["source_id"].startswith("Method:")
assert payload["relationships"][0]["target_id"].startswith("Method:")
```

- [ ] **Step 2: Run test and verify it fails**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_index_repo_runs_analyze_then_cypher_and_normalizes_graph -q
```

Expected: fails because current client expects JSON from `index`.

- [ ] **Step 3: Implement `analyze` then `cypher`**

Add internal methods:

```python
def _run_text(self, command: list[str], *, operation: str) -> str
def _run_tool_json(self, command: list[str], *, operation: str) -> dict[str, Any]
def _cypher_graph_payload(self, request: RepoIndexRequest) -> dict[str, Any]
```

For `index_repo()`:

```python
self._run_text(analyze_command, operation="index")
raw_graph = self._run_tool_json(cypher_command, operation="index")
return self._normalize_cypher_graph_payload(raw_graph, request=request)
```

- [ ] **Step 4: Parse cypher markdown safely**

GitNexus `cypher` returns:

```json
{"markdown": "| n.id | r.type | ... |"}
```

Implement a small parser for the GitNexus markdown table into dictionaries. Keep it scoped to the columns this adapter requests.

- [ ] **Step 5: Run unit test**

```powershell
python -m pytest tests/test_gitnexus_client.py -q
```

Expected: client tests pass.

---

## Task 3: QueryGraph Through Exact Context And Trace

**Files:**

```text
Modify: legacy_pilot/code_knowledge_core/gitnexus_client.py
Modify: legacy_pilot/code_knowledge_core/gitnexus_mapper.py
Modify: tests/test_gitnexus_client.py
Modify: tests/test_gitnexus_mapper.py
```

- [ ] **Step 1: Write failing test for service method query using context**

Input:

```python
GraphQuery(query_terms=["DatasetService.getVersion"], trace_id="TRACE-Q-001")
```

Fake CLI `context --uid Method:...DatasetService.getVersion#1` returns:

```json
{
  "status": "found",
  "symbol": {"uid": "...DatasetService.getVersion#1", "name": "getVersion", "kind": "Method"},
  "incoming": {"calls": [{"uid": "...DatasetController.getVersion#1"}]},
  "outgoing": {"calls": [{"uid": "...DatasetMapper.selectVersionById#1"}]},
  "processes": [{"id": "proc_0_getversion", "name": "GetVersion \u2192 SelectVersionById"}]
}
```

Expected payload contains service node, controller node, mapper node, and CALLS edges.

- [ ] **Step 2: Run test and verify it fails**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_query_graph_uses_context_for_exact_method_query -q
```

- [ ] **Step 3: Implement exact method UID resolver**

For the first pass, support Java fixture-style method terms:

```text
DatasetService.getVersion
```

Resolve by `cypher`:

```text
MATCH (n) WHERE n.id CONTAINS 'DatasetService.getVersion' RETURN n.id, n.name, n.filePath, n.startLine, n.endLine LIMIT 10
```

Pick the exact method node whose id contains the class and method token.

- [ ] **Step 4: Implement context-to-query payload normalization**

Normalize context JSON into mapper-ready payload:

```python
{
    "graph_id": query.graph_id,
    "nodes": [...],
    "relationships": [...],
    "paths": [[controller_uid, service_uid, mapper_uid]],
    "not_found": False,
}
```

- [ ] **Step 5: Run mapper and client tests**

```powershell
python -m pytest tests/test_gitnexus_client.py tests/test_gitnexus_mapper.py -q
```

Expected: pass.

---

## Task 4: Route Query Support For `/api/dataset/version`

**Files:**

```text
Modify: legacy_pilot/code_knowledge_core/gitnexus_client.py
Modify: tests/test_gitnexus_client.py
Modify: tests/test_gitnexus_integration.py
```

- [ ] **Step 1: Write failing test for route query fallback**

Input:

```python
GraphQuery(query_terms=["/api/dataset/version"])
```

Expected behavior:

1. Try route lookup via cypher against file content or node content.
2. If no explicit route node exists, return controller method context if the route literal is found in `DatasetController.java`.

- [ ] **Step 2: Run test and verify it fails**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_query_graph_route_term_falls_back_to_controller_method_context -q
```

- [ ] **Step 3: Implement route literal lookup**

Use `cypher`:

```text
MATCH (n) WHERE n.content CONTAINS '/api/dataset/version' RETURN n.id, n.name, n.filePath, n.content LIMIT 5
```

Then resolve the controller method from the same file by method node id containing `DatasetController.getVersion`.

- [ ] **Step 4: Run route tests**

```powershell
python -m pytest tests/test_gitnexus_client.py::test_query_graph_route_term_falls_back_to_controller_method_context tests/test_gitnexus_integration.py -q
```

Default expected: integration real tests still skip without env; unit route test passes.

---

## Task 5: Real Integration Test Must Pass With Built GitNexus CLI

**Files:**

```text
Modify: tests/test_gitnexus_integration.py
Modify: README.md
Modify: docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
```

- [ ] **Step 1: Update integration env documentation**

Document that `GITNEXUS_BIN` can point to a wrapper:

```text
Q:\tmp\gitnexus-local.cmd
```

or a global `gitnexus`.

- [ ] **Step 2: Run default integration test**

```powershell
python -m pytest tests/test_gitnexus_integration.py -q -rs
```

Expected:

```text
2 passed, 3 skipped
```

- [ ] **Step 3: Run real integration test**

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
python -m pytest tests/test_gitnexus_integration.py -q -rs
```

Expected:

```text
5 passed
```

Acceptable warning:

```text
FTS extension unavailable; keyword search degraded
```

The adapter must not depend on BM25/FTS for the Java fixture path.

---

## Task 6: Final Verification

**Files:**

```text
Review: legacy_pilot/code_knowledge_core/*
Review: tests/*
Review: docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
Review: README.md
```

- [ ] **Step 1: Run default suite**

```powershell
python -m pytest -q
```

Expected:

```text
All default tests pass; real GitNexus tests skip when env is absent.
```

- [ ] **Step 2: Run real integration**

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
python -m pytest tests/test_gitnexus_integration.py -q -rs
```

Expected:

```text
5 passed
```

- [ ] **Step 3: Run static checks**

```powershell
python -m compileall legacy_pilot
git diff --check
git status --short --branch
```

Expected:

```text
compileall passes.
git diff --check has no output.
Only intentional source/docs/test changes are present.
```

---

## Non-Goals

Do not implement in this pass:

```text
gitnexus_http backend
MyBatis XML extractor
SQL table graph
RCA Engine direct GitNexus access
Incident Context Builder direct GitNexus access
LLM semantic graph
```
