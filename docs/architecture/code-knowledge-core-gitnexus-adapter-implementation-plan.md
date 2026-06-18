# Code Knowledge Core GitNexus Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. This document is a planning artifact only; do not write implementation code while editing this plan.

**Goal:** Implement LegacyPilot structure 1 as a Python/FastAPI-controlled Code Knowledge Core adapter that uses GitNexus through `gitnexus_cli`, while preserving the existing middleware contracts.

**Architecture:** `MiddlewareRouter` remains the HTTP-facing contract gate. Code Knowledge Core is introduced behind a Python adapter interface. GitNexus output is normalized by a CLI client and mapped into LCMS `GraphSnapshot`, `GraphContext`, `Node`, `Edge`, and `EvidenceRef` models before it can leave the middleware.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, subprocess-based GitNexus CLI integration, optional Java/Spring fixture for integration validation.

---

## Step 0 Decisions Already Fixed

```text
backend = gitnexus_cli
fixture = self_built_java_spring_demo
sql_extractor = completed in Structure 1 production coverage milestone
```

Consequences:

- First implementation does not start or depend on a GitNexus HTTP server.
- Default test mode stays deterministic and does not require GitNexus.
- MyBatis XML, SQL table extraction, and SQL edge semantics were excluded from the initial GitNexus adapter first-release acceptance, but are now covered by the Structure 1 production coverage milestone.
- GitNexus unavailable in real mode returns a recoverable `ContractError`; it must not silently fall back to mock data.

## Target File Map

Create:

```text
legacy_pilot/code_knowledge_core/__init__.py
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/code_knowledge_core/errors.py
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_code_knowledge_core_adapter.py
tests/test_gitnexus_mapper.py
tests/test_gitnexus_client.py
tests/test_gitnexus_integration.py
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetController.java
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetService.java
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetMapper.java
```

Modify:

```text
legacy_pilot/middleware/router.py
legacy_pilot/middleware/app.py
tests/test_router_pipeline.py
tests/test_api.py
docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
README.md
pyproject.toml
```

`pyproject.toml` is modified only if pytest markers are needed for optional GitNexus integration tests.

## Step 1: Define CodeKnowledgeCoreAdapter Interface

### Boundary

This step creates the structure 1 adapter boundary only. It must not move current mock logic, must not call GitNexus, and must not alter HTTP route behavior.

The adapter interface owns only:

```text
index_repo(RepoIndexRequest) -> GraphSnapshot
query_graph(GraphQuery) -> GraphContext
```

Contract gates remain outside the adapter:

```text
contract_version gate: MiddlewareRouter
trace_id gate: MiddlewareRouter
```

### Local Paths

Create:

```text
legacy_pilot/code_knowledge_core/__init__.py
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/code_knowledge_core/errors.py
tests/test_code_knowledge_core_adapter.py
```

No existing production file should be modified in this step except package exports if needed.

### Tests

Add adapter-interface tests in:

```text
tests/test_code_knowledge_core_adapter.py
```

Required cases:

- A fake adapter can implement `index_repo()` and return a valid `GraphSnapshot`.
- A fake adapter can implement `query_graph()` and return a valid `GraphContext`.
- The adapter type surface does not expose GitNexus-specific objects.
- Code Knowledge Core internal exceptions carry `source_module = "code_knowledge_core"` or enough data for router-level conversion.

### Verification

Run:

```powershell
python -m pytest tests/test_code_knowledge_core_adapter.py -q
python -m pytest tests/test_contract_models.py -q
```

Expected result:

```text
All selected tests pass.
No HTTP response shape changes.
No GitNexus process is invoked.
```

### Exit Criteria

- `legacy_pilot.code_knowledge_core` is importable.
- The adapter interface references only LCMS contract models.
- The existing full test suite still has no required GitNexus dependency.

## Step 2: Extract Current Mock Graph Logic Into Mock Adapter

### Boundary

This step moves only the existing deterministic `index_repo()` and `query_graph()` mock behavior out of `MiddlewareRouter` and into `MockCodeKnowledgeCoreAdapter`.

It must not implement GitNexus mapping, GitNexus CLI execution, or backend selection from environment variables.

`MiddlewareRouter` remains responsible for:

```text
ensure_supported_contract_version()
ensure_trace_id()
ContractViolation conversion for contract gates
```

### Local Paths

Modify:

```text
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/middleware/router.py
tests/test_code_knowledge_core_adapter.py
tests/test_router_pipeline.py
tests/test_api.py
```

### Tests

Add or update tests for:

- `MiddlewareRouter()` with no adapter still returns the same mock `GraphSnapshot`.
- `MiddlewareRouter()` with no adapter still returns the same mock `GraphContext`.
- Unsupported `contract_version` fails before adapter execution.
- Missing or empty `trace_id` fails before adapter execution.
- Existing API route tests for `/v1/repos/index` and `/v1/graph/query` still pass.

The pre-adapter gate tests should use a fake adapter that records whether it was called.

### Verification

Run:

```powershell
python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected result:

```text
Existing middleware behavior is preserved.
Fake adapter is not called when contract_version or trace_id gates fail.
```

### Exit Criteria

- `MiddlewareRouter.index_repo()` delegates to the adapter only after contract version validation.
- `MiddlewareRouter.query_graph()` delegates to the adapter only after trace and contract version validation.
- Other structures' methods in `MiddlewareRouter` are not refactored in this step.

## Step 3: Implement GitNexus-to-LCMS Mapper

### Boundary

This step implements pure mapping functions only. It must not spawn subprocesses, read environment variables, or alter router injection.

Inputs are GitNexus-like normalized payloads. Outputs are LCMS Pydantic models:

```text
GraphNode-like dict -> Node
GraphRelationship-like dict -> Edge
index payload -> GraphSnapshot
query payload -> GraphContext
```

### Local Paths

Create or modify:

```text
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_gitnexus_mapper.py
```

### Mapping Requirements

Node mapping must enforce:

```text
node_id = GitNexus id
qualified_name = properties.qualifiedName, or file_path::name, or null
metadata.gitnexus = nested GitNexus details
evidence_refs includes at least one EvidenceRef when source location exists
created_at = injected clock value or datetime.now(UTC)
```

Edge mapping must enforce:

```text
metadata.gitnexus = { reason, evidence_signals, source_relationship_type }
evidence_refs min_length = 1
source_type = code for code graph edges
no source_type=document fallback for CALLS/HANDLES_ROUTE/IMPORTS/HAS_METHOD
confidence is clamped to 0.0-1.0
```

Evidence identity must be deterministic:

```text
EV-GN-{sha256(trace_id, source_id, file_path, start_line, end_line).hexdigest()[:12]}
```

Graph-level evidence collection must deduplicate by:

```text
evidence_id
```

### Tests

Add mapper tests for:

- `GraphNode` with `qualifiedName` maps to `Node.qualified_name`.
- `GraphNode` without `qualifiedName` maps to `file_path::name`.
- Node evidence uses `created_at` from injected clock.
- Relationship evidence maps to `Edge.metadata["gitnexus"]["evidence_signals"]`.
- Edge with no source node location uses target node location.
- Edge with no source or target location either receives low-confidence code evidence or is omitted according to mapper policy.
- `GraphSnapshot.evidence_refs` deduplicates by `evidence_id`.
- `GraphContext.trace_id` equals the input `GraphQuery.trace_id`.
- `GraphContext.confidence` uses `min(average edge confidence, max edge evidence confidence)` when matched edges exist.
- `not_found` query payload returns empty `GraphContext` with `confidence = 0.0`.

### Verification

Run:

```powershell
python -m pytest tests/test_gitnexus_mapper.py -q
python -m pytest tests/test_contract_models.py -q
```

Expected result:

```text
Mapper outputs validate through existing Pydantic contract models.
Every returned Edge has at least one EvidenceRef.
No mapper test requires GitNexus to be installed.
```

### Exit Criteria

- Mapping is deterministic for the same input and clock.
- Mapper never returns GitNexus raw objects directly to router or HTTP layers.
- Current `GraphContext` contract limitations are respected; no `metadata` or `missing_evidence` fields are added.

## Step 4: Implement GitNexus CLI Client

### Boundary

This step adds `gitnexus_cli` execution and normalized payload parsing. It must not wire the client into production router behavior yet.

The client owns:

```text
subprocess execution
timeout handling
stdout JSON parsing
stderr capture for internal diagnostics
non-zero exit conversion
GitNexus raw output normalization into mapper input
```

The client must not own:

```text
Pydantic response model creation
HTTP error envelope creation
contract_version validation
trace_id validation
```

### Local Paths

Create or modify:

```text
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/errors.py
tests/test_gitnexus_client.py
```

### Configuration Inputs

The client reads configuration from constructor parameters first, then environment values:

```text
GITNEXUS_BIN
GITNEXUS_REPO_ROOT
GITNEXUS_TIMEOUT_SECONDS
LEGACY_PILOT_MAX_GRAPH_NODES
LEGACY_PILOT_MAX_GRAPH_EDGES
```

No real GitNexus process is required for unit tests. Unit tests must monkeypatch subprocess execution.

### Tests

Add client tests for:

- CLI command includes repo path, repo id, and requested operation.
- Timeout becomes recoverable Code Knowledge Core error.
- Missing executable becomes recoverable Code Knowledge Core error.
- Non-zero exit becomes recoverable Code Knowledge Core error without leaking stack trace to caller.
- Invalid JSON stdout becomes recoverable Code Knowledge Core error.
- Valid index JSON is normalized into mapper-ready index payload.
- Valid query JSON is normalized into mapper-ready query payload.
- stderr is retained for diagnostics but not used as HTTP response text directly.

### Verification

Run:

```powershell
python -m pytest tests/test_gitnexus_client.py -q
```

Expected result:

```text
All subprocess paths are tested without invoking real GitNexus.
All client failures are represented as Code Knowledge Core internal errors.
```

### Exit Criteria

- `gitnexus_client.py` has no dependency on FastAPI.
- Unit tests cover success, timeout, missing executable, non-zero exit, and invalid JSON.
- No mock fallback is performed inside the real GitNexus client.

## Step 5: Wire Adapter Injection And Backend Selection

### Boundary

This step connects router injection to real adapter selection. It must preserve default mock behavior and must not require GitNexus during normal tests.

Default behavior:

```text
LEGACY_PILOT_CODE_CORE_BACKEND missing or "mock" -> MockCodeKnowledgeCoreAdapter
LEGACY_PILOT_CODE_CORE_BACKEND="gitnexus_cli" -> GitNexus CLI adapter
```

Rejected behavior:

```text
real mode failure -> silent mock fallback
```

### Local Paths

Modify:

```text
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/middleware/router.py
legacy_pilot/middleware/app.py
tests/test_code_knowledge_core_adapter.py
tests/test_router_pipeline.py
tests/test_api.py
```

### Tests

Add or update tests for:

- `MiddlewareRouter()` defaults to mock adapter.
- `MiddlewareRouter(code_knowledge_core_adapter=fake)` delegates structure 1 calls to fake adapter.
- `create_app()` still returns working default mock endpoints.
- `create_app(router=custom_router)` preserves existing test injection path.
- `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli` selects the real adapter through a factory test without running GitNexus.
- Unsupported backend value returns a recoverable configuration error when structure 1 is called.
- Contract gates still execute before adapter call.

### Verification

Run:

```powershell
python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
python -m pytest -q
```

Expected result:

```text
Full default suite passes without GitNexus.
HTTP contract shapes for existing endpoints are unchanged.
```

### Exit Criteria

- Real adapter is selectable but not required by default.
- Contract gate behavior remains at `MiddlewareRouter`.
- FastAPI response models still validate adapter output.

## Step 6: Add Java/Spring Fixture And Optional GitNexus Integration Test

### Boundary

This step describes the original self-contained fixture and optional integration tests. Current Structure 1 production coverage adds a separate production fixture with MyBatis XML and SQL table acceptance.

The fixture proves only:

```text
Route / Controller
Controller method
Service method
Mapper interface method
CALLS / HANDLES_ROUTE style graph continuity where GitNexus can provide it
```

### Local Paths

Create:

```text
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetController.java
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetService.java
tests/fixtures/java_spring_demo/src/main/java/com/legacy/DatasetMapper.java
tests/test_gitnexus_integration.py
```

Modify:

```text
pyproject.toml
```

`pyproject.toml` modification is limited to registering a pytest marker such as:

```text
gitnexus_integration: requires local GitNexus runtime and is skipped by default
```

### Tests

Integration tests must be skipped unless explicitly enabled by environment:

```text
LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1
GITNEXUS_BIN=<path or command>
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main
```

Required integration cases:

- Skip reason is clear when integration env is absent.
- `IndexRepo` against the fixture returns a non-empty `GraphSnapshot`.
- Returned `GraphSnapshot.repo_id` equals the request repo id.
- Returned edges have `evidence_refs`.
- `QueryGraph("DatasetService.getVersion")` returns a `GraphContext`.
- `GraphContext.trace_id` equals request `trace_id`.
- Query by `/api/dataset/version` returns route or controller context if GitNexus exposes the route.

### Verification

Default verification:

```powershell
python -m pytest tests/test_gitnexus_integration.py -q
python -m pytest -q
```

Expected default result:

```text
Integration tests are skipped when GitNexus env is absent.
Full suite passes without GitNexus.
```

Explicit GitNexus verification:

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:GITNEXUS_BIN='gitnexus'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main'
python -m pytest tests/test_gitnexus_integration.py -q
```

Expected explicit result:

```text
Integration tests pass or fail with a GitNexus-specific diagnostic.
No failure is hidden by mock fallback.
```

### Exit Criteria

- Java/Spring fixture is small and deterministic.
- Integration tests are opt-in.
- Absence of GitNexus does not block normal development tests.

## Step 7: Final Verification, Documentation Sync, And Handoff

### Boundary

This step performs verification and documentation updates only. It must not add new structure 1 behavior.

No new capabilities are introduced here:

```text
No gitnexus_http backend
No new MyBatis XML extractor behavior beyond the Structure 1 production coverage implementation
No new SQL table graph behavior beyond the Structure 1 production coverage implementation
No RCA Engine direct GitNexus access
No Incident Context Builder direct GitNexus access
```

### Local Paths

Modify only if implementation changed behavior or setup instructions:

```text
docs/architecture/code-knowledge-core-gitnexus-adapter-design.md
README.md
```

Review:

```text
legacy_pilot/code_knowledge_core/*
legacy_pilot/middleware/router.py
legacy_pilot/middleware/app.py
tests/*
tests/fixtures/java_spring_demo/*
```

### Verification Checklist

Run default verification:

```powershell
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
git status --short --branch
```

Run targeted contract checks:

```powershell
python -m pytest tests/test_api.py::test_missing_trace_id_returns_trace_required_error_envelope -q
python -m pytest tests/test_api.py::test_unsupported_contract_version_returns_contract_error_envelope -q
python -m pytest tests/test_router_pipeline.py::test_query_graph_returns_traceable_graph_context -q
```

Run optional real integration only when GitNexus is configured:

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='gitnexus'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main'
python -m pytest tests/test_gitnexus_integration.py -q
```

### Documentation Checks

Confirm documentation states:

- Default backend is mock.
- Real backend is `gitnexus_cli`.
- No silent fallback from real backend to mock.
- `GraphContext` has no `metadata` or `missing_evidence` field.
- MyBatis/SQL extractor is implemented by the Structure 1 production coverage milestone; future work is limited to broader SQL dialect and multi-module coverage.
- Other three structures consume only LCMS contract objects.

### Exit Criteria

- Full default test suite passes without GitNexus.
- Optional GitNexus integration has either passed or is explicitly reported as not run.
- `git diff --check` reports no whitespace errors.
- Documentation matches actual environment variable names and backend behavior.
- Worktree contains only intentional implementation and documentation changes.
