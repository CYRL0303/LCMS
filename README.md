# LegacyPilot Interface Contract Middleware

LegacyPilot is a hackathon MVP for incident-driven legacy system analysis. This repository currently contains the first slice: a Python/FastAPI interface contract middleware that standardizes communication between the four planned LegacyPilot structures.

## What This Middleware Does

- Defines shared Pydantic contracts for cross-structure requests and responses.
- Enforces `contract_version`, `trace_id`, `confidence`, and `evidence_refs` gates.
- Returns a unified `ContractError` envelope for middleware-level failures.
- Exposes FastAPI routes for the MVP incident analysis flow.
- Routes the MVP flow through Structure 2 `graph_context` and Structure 3
  `qwen_api` by default; deterministic mock backends remain explicit test/demo
  choices, and Structure 1 can opt in to the real `gitnexus_cli` backend.

Default configured flow:

```text
SubmitAlert
-> BuildEvidenceBundle (Structure2 graph_context -> QueryGraph)
-> GenerateRCA (Structure3 qwen_api)
-> ReviewRCA
-> SaveIncident
```

## Current Progress

Structure 1-3 are wired through the middleware contract with real opt-in
integration coverage:

- Structure 1 uses real `gitnexus_cli` indexing/query integration, MyBatis SQL
  extraction, table/config/exception evidence, local graph indexing, and
  optional PostgreSQL graph payload persistence.
- Structure 1 semantic enrichment remains disabled by default, with explicit
  deterministic `mock` and opt-in real DashScope Qwen `qwen_api` modes.
- Structure 2 owns `IncidentContextBuilderAdapter`. Default backend is
  `graph_context`, which builds `EvidenceBundle` from Structure 1
  `GraphContext`. Unknown backends fail loudly; deterministic `mock` is
  explicit test/demo mode only.
- Structure 3 owns `RCAReasoningEngineAdapter`. Default backend is real
  DashScope Qwen `qwen_api`; no default mock RCA path remains in middleware.
- Structure 3 enforces evidence-backed RCA output, rejects unknown evidence
  IDs, retries invalid JSON/schema Qwen responses with bounded repair prompts,
  and records retry metadata without storing secrets.
- Middleware routes SubmitAlert -> EvidenceBundle -> RCA generation/review ->
  incident save through Structure2 and Structure3 boundaries, converting
  lower-structure failures into `ContractError` envelopes.
- Reusable PowerShell scripts start Docker Desktop/PostgreSQL, load the
  persisted Qwen key, and run the real GitNexus + PostgreSQL + Structure2 +
  Structure3 E2E chain.
- Production fixture coverage proves `/api/dataset/version -> controller ->
  service -> mapper -> Mapper XML SQL -> dataset_version`, plus config and
  exception evidence.

Latest local verification:

```text
Default suite: 205 passed, 8 skipped, 1 warning
Real Structure1/PostgreSQL/Structure2/Structure3 E2E: 3 passed, 2 warnings
Real GitNexus + Structure1 production fixture: 12 passed, 2 warnings
Real PostgreSQL graph store integration: 1 passed, 2 warnings
Real Qwen semantic integration: 1 passed, 2 warnings
Secret scan: no persisted Qwen key in repository
```

## Repository Layout

```text
docs/
  architecture/
    LegacyPilot_项目大纲与执行流程_审计修订版.docx
    interface-contract-middleware-development.md
    interface-contract-middleware-implementation.md
    legacy-pilot-four-structures.md
  superpowers/
    plans/
legacy_pilot/
  code_knowledge_core/
    adapter.py
    gitnexus_client.py
    gitnexus_mapper.py
    errors.py
  contracts/
    enums.py
    errors.py
    models.py
    validators.py
  incident_context_builder/
    adapter.py
    evidence_builder.py
    signals.py
  middleware/
    app.py
    router.py
tests/
  fixtures/
    java_spring_demo/
pyproject.toml
```

## Local Setup

```bash
python -m pip install -e ".[dev]"
```

If editable install is not needed, installing the runtime dependencies is enough:

```bash
python -m pip install fastapi uvicorn pydantic pytest httpx
```

## Run Tests

Default CI profile:

```bash
python -m pytest -q
```

Structure 1 production fixture profile, with real GitNexus checks skipped by default:

```bash
python -m pytest tests/test_structure1_production_fixture.py -q -rs
```

GitNexus integration CI profile:

1. Build the GitNexus CLI/runtime outside this repository.
2. Set `GITNEXUS_BIN` to `gitnexus` or a wrapper such as `Q:/tmp/gitnexus-local.cmd`.
3. Set `GITNEXUS_REPO_ROOT` to the local GitNexus runtime checkout.
4. Enable opt-in integration tests with `LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1`.
5. Run the GitNexus integration suites.

```bash
LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1 \
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli \
GITNEXUS_BIN=gitnexus \
GITNEXUS_REPO_ROOT=Q:/Hackathons/GitNexus-main/GitNexus-main/gitnexus \
LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE=1 \
GITNEXUS_INDEX_TIMEOUT_SECONDS=120 \
GITNEXUS_QUERY_TIMEOUT_SECONDS=30 \
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -q -rs
```

`GITNEXUS_BIN` may also point to a local wrapper such as `Q:/tmp/gitnexus-local.cmd` when testing a source checkout build.

GitNexus client controls:

- `LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE=1`: always run `gitnexus analyze`
  before reading the graph with `cypher`.
- `LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE=0`: run `cypher` first; if the graph is
  empty, run `analyze` and retry `cypher` once.
- `GITNEXUS_INDEX_TIMEOUT_SECONDS`: timeout for `analyze`.
- `GITNEXUS_QUERY_TIMEOUT_SECONDS`: timeout for `cypher`, `context`, `trace`,
  and `impact` style queries.
- `GITNEXUS_TIMEOUT_SECONDS`: backward-compatible fallback when the more
  specific timeout variables are not set.

Default backend: `mock`.
Real backend: `gitnexus_cli`.
There is no silent fallback from `gitnexus_cli` to `mock`; GitNexus runtime failures become recoverable contract errors.

### Structure 1 Semantic Enrichment

Semantic enrichment is disabled by default.

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='disabled'
```

The deterministic test backend can be enabled explicitly:

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='mock'
$env:LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP='0.7'
```

The real DashScope Qwen backend can be enabled explicitly for opt-in tests:

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='qwen_api'
$env:LEGACY_PILOT_SEMANTIC_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
$env:LEGACY_PILOT_SEMANTIC_MODEL='qwen-plus'
$env:DASHSCOPE_API_KEY='<set outside git>'
```

Semantic nodes are LCMS graph nodes with `type="Function Semantic Summary"`.
They are always evidence-backed with `source_type="llm_semantic_summary"`,
`extraction_method="llm"`, `verification_status="pending"`, and confidence no
higher than `LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP`.

Semantic nodes are not trusted structural facts and do not replace GitNexus
structural nodes or SQL/config/exception enrichers. The real LLM backend for
Structure 1 coverage is `qwen_api` through the OpenAI-compatible DashScope Chat
API; no `ollama` backend is part of the current acceptance path.

### Structure 1 PostgreSQL Graph Store

Graph persistence is disabled by default. Enable it only for Structure 1:

```powershell
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:5432/legacy_pilot'
$env:LEGACY_PILOT_GRAPH_STORE_TABLE='legacy_pilot_graph_payloads'
```

`IndexRepo` persists the normalized and enriched mapper-ready graph payload.
`QueryGraph` first checks the in-process `LocalGraphIndex`; for locally
queryable plans with no process-local index, it reloads the payload from
PostgreSQL and rebuilds the local index. Other LegacyPilot structures must not
connect to this database directly; they still use `/v1/graph/query`.

The real PostgreSQL integration test is opt-in. Set
`LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE=1` and
`LEGACY_PILOT_GRAPH_STORE_DSN`; optionally set
`LEGACY_PILOT_GRAPH_STORE_TEST_TABLE` to isolate test writes from the default
graph-store table.

### Structure 2 Incident Context Builder

Default backend:

```powershell
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
```

Explicit deterministic backend:

```powershell
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='mock'
```

`graph_context` backend calls `/v1/graph/query` through middleware internals and
builds `EvidenceBundle` from `GraphContext`. It never connects to Structure 1
PostgreSQL graph store directly.

### Structure 3 RCA Reasoning Engine

Default backend:

```powershell
$env:LEGACY_PILOT_RCA_BACKEND='qwen_api'
$env:LEGACY_PILOT_RCA_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
$env:LEGACY_PILOT_RCA_MODEL='qwen-plus'
$env:LEGACY_PILOT_RCA_CONFIDENCE_CAP='0.75'
$env:LEGACY_PILOT_RCA_REPAIR_ATTEMPTS='2'
$env:DASHSCOPE_API_KEY='<set outside git>'
```

The Qwen adapter retries invalid JSON or invalid schema responses with a repair
prompt. `LEGACY_PILOT_RCA_REPAIR_ATTEMPTS` is bounded internally so real runs
cannot retry indefinitely.

Persist the Qwen key once for this Windows user:

```powershell
.\scripts\set-qwen-user-env.ps1 -WriteDotEnvLocal
```

Replace the persisted Qwen key later by running the same script again, or by
setting the user environment variable directly:

```powershell
[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', '<new-key>', 'User')
$env:DASHSCOPE_API_KEY='<new-key>'
```

`scripts/run-real-e2e.ps1` reads the current process env first, then
`.env.local`, then the Windows User `DASHSCOPE_API_KEY`, so a one-time persisted
key is reused by later real E2E runs. `.env.local` is gitignored.

## Run The API

```bash
python -m uvicorn legacy_pilot.middleware.app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

## API Surface

- `GET /health`
- `POST /v1/repos/index`
- `POST /v1/graph/query`
- `POST /v1/alerts/submit`
- `POST /v1/evidence-bundles/build`
- `POST /v1/incidents/similar`
- `POST /v1/rca/generate`
- `POST /v1/rca/review`
- `POST /v1/incidents/save`

## Current Limits

- Real Structure 1 execution is available only through the opt-in `gitnexus_cli` backend.
- `gitnexus_http` is not implemented.
- Real Qwen semantic enrichment is available only through the opt-in `qwen_api` backend.
- Semantic graph output is pending and confidence-capped; it is not treated as a trusted structural fact.
- Structure 2 defaults to `graph_context`, which requires queryable Structure 1 graph context for useful evidence bundles.
- No persistent incident database is connected yet.
- Structure 2 deterministic mock responses require explicit `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=mock`.
