# LegacyPilot Interface Contract Middleware

LegacyPilot is a hackathon MVP for incident-driven legacy system analysis. This repository currently contains the first slice: a Python/FastAPI interface contract middleware that standardizes communication between the four planned LegacyPilot structures.

## What This Middleware Does

- Defines shared Pydantic contracts for cross-structure requests and responses.
- Enforces `contract_version`, `trace_id`, `confidence`, and `evidence_refs` gates.
- Returns a unified `ContractError` envelope for middleware-level failures.
- Exposes FastAPI routes for the MVP incident analysis flow.
- Routes the MVP flow through real Structure 1 `gitnexus_cli`, Structure 2
  `graph_context`, Structure 3 `qwen_api`, and Structure 4 PostgreSQL incident
  memory by default. Runtime mock backend selection is disabled.

Default configured flow:

```text
SubmitAlert
-> BuildEvidenceBundle (Structure2 graph_context -> QueryGraph)
-> GenerateRCA (Structure3 qwen_api)
-> ReviewRCA
-> SaveIncident (Structure4 postgresql)
```

## Current Progress

Structure 1-4 are wired through the middleware contract with real opt-in
integration coverage:

- `repo_id` is the user/project-level repository alias. `graph_id` is the
  concrete graph snapshot ID produced by a real `IndexRepo` run or selected
  from persisted graphs.
- Structure 1 uses real `gitnexus_cli` indexing/query integration, MyBatis SQL
  extraction, table/config/exception evidence, local graph indexing, and
  optional PostgreSQL graph payload persistence.
- Structure 1 accepts local paths, `file://` URIs, GitHub HTTPS repo URLs, and
  GitLab HTTPS repo URLs. Private GitHub/GitLab imports use the runtime tokens
  supplied by the frontend settings modal or equivalent request headers.
- Structure 1 semantic enrichment remains disabled by default, with opt-in real
  DashScope Qwen `qwen_api` mode.
- Structure 2 owns `IncidentContextBuilderAdapter`. Default backend is
  `graph_context`, which builds `EvidenceBundle` from Structure 1
  `GraphContext`. Unknown backends fail loudly.
- Structure 3 owns `RCAReasoningEngineAdapter`. Default backend is real
  DashScope Qwen `qwen_api`; no default mock RCA path remains in middleware.
- Structure 3 enforces evidence-backed RCA output, rejects unknown evidence
  IDs, retries invalid JSON/schema Qwen responses with bounded repair prompts,
  and records retry metadata without storing secrets.
- Structure 4 owns PostgreSQL incident memory persistence for confirmed RCA
  records. The production factory only allows the real `postgresql` backend.
- `RCAReport`, `ReviewedRCAReport`, and `IncidentRecord` carry `graph_id` so
  saved incident memory remains tied to the graph snapshot that produced the
  evidence.
- The middleware exposes persisted graph listing/deletion. Deleting a graph is
  blocked when Structure 4 has incident memory records referencing that graph.
- Middleware routes SubmitAlert -> EvidenceBundle -> RCA generation/review ->
  incident save through Structure2, Structure3, and Structure4 boundaries, converting
  lower-structure failures into `ContractError` envelopes.
- Reusable PowerShell scripts start Docker Desktop/PostgreSQL, load the
  persisted Qwen key, and run the real GitNexus + PostgreSQL + Structure2 +
  Structure3 + Structure4 E2E chain.
- Production fixture coverage proves `/api/dataset/version -> controller ->
  service -> mapper -> Mapper XML SQL -> dataset_version`, plus config and
  exception evidence.

Latest local verification:

```text
Default suite: 230 passed, 8 skipped, 1 warning
Real Structure1/PostgreSQL/Structure2/Structure3/Structure4 E2E: 3 passed, 2 warnings
Real GitNexus + Structure1 production fixture: 12 passed, 2 warnings
Real PostgreSQL graph store integration: 1 passed, 2 warnings
Real Qwen semantic integration: 1 passed, 2 warnings
Frontend build: passed
Manual real browser E2E with existing graph: passed
  - frontend: http://127.0.0.1:5173
  - backend: gitnexus_cli / graph_context / qwen_api / postgresql
  - existing graph: IBM / GRAPH-IBM
  - saved incident: INC-ALERT-UI-OBS-1782822984366
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
  incident_memory_store/
    adapter.py
  middleware/
    app.py
    router.py
tests/
  fixtures/
    java_spring_demo/
frontend/
  src/                  # React Incident Workbench
  tests/                # Playwright real frontend E2E
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

Frontend workbench dependencies:

```bash
cd frontend
npm install --cache .npm-cache
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
- `RepoIndexRequest.repo_uri` may be a local path, `file://` URI, or public
  GitHub/GitLab repository URL in the form `https://github.com/<owner>/<repo>`
  or `https://gitlab.com/<group>/<repo>`. Remote URLs are cloned with
  `git clone --depth 1` into `LEGACY_PILOT_REPO_IMPORT_ROOT` before GitNexus
  analyzes the local checkout.
- Private GitHub imports use `X-LegacyPilot-GitHub-Token`; private GitLab
  imports use `X-LegacyPilot-GitLab-Token`. The frontend settings modal stores
  those tokens locally and sends them only to the middleware request.
- `LEGACY_PILOT_REPO_IMPORT_ROOT`: optional clone cache directory for remote
  imports. Defaults to the OS temp directory under `legacy-pilot-repos`.
- `LEGACY_PILOT_REPO_IMPORT_TIMEOUT_SECONDS`: timeout for remote clone.

Default backend: `gitnexus_cli`.
There is no silent fallback to `mock`; GitNexus runtime failures become recoverable contract errors.

### Structure 1 Semantic Enrichment

Semantic enrichment is disabled by default.

```powershell
$env:LEGACY_PILOT_SEMANTIC_BACKEND='disabled'
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

Persisted graph records can be listed through `GET /v1/graphs`. `DELETE
/v1/graphs/{repo_id}/{graph_id}` removes a graph payload only when no incident
memory row references that graph. A blocked delete returns a recoverable
`RESOURCE_IN_USE` contract error with the referencing incident count.

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

### Structure 4 Incident Memory Store

Default backend:

```powershell
$env:LEGACY_PILOT_INCIDENT_MEMORY_BACKEND='postgresql'
$env:LEGACY_PILOT_INCIDENT_MEMORY_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_INCIDENT_MEMORY_TABLE='legacy_pilot_incident_records'
```

`SaveIncident` stores user-confirmed RCA records through Structure 4. PostgreSQL
rows keep the full `IncidentRecord` JSON plus `incident_id`, `repo_id`,
`graph_id`, and `dedup_key` columns for lookup/upsert.
`FindSimilarIncidents` and `GET /v1/incidents/{incident_id}` read through the
same Structure 4 store; the product path no longer returns hardcoded incident
matches. Missing PostgreSQL DSN fails loudly; there is no in-memory production
fallback.

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

## Run The Frontend Workbench

The frontend is a React/Vite single-page `Incident Workbench`. It calls only the
middleware HTTP API through the Vite `/api` proxy; it does not connect directly
to GitNexus, PostgreSQL, or DashScope.

Start the middleware:

```bash
python -m uvicorn legacy_pilot.middleware.app:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

Run the real browser E2E chain:

```powershell
.\scripts\run-real-frontend-e2e.ps1 -InstallFrontendDeps
```

That script starts Docker Desktop/PostgreSQL, loads the persisted Qwen key,
starts middleware, starts the frontend through Playwright, and runs the real
Structure1 -> PostgreSQL -> Structure2 -> Structure3 Qwen -> Structure4 flow
from the browser.

Keep the real backend and frontend running for manual browser testing:

```powershell
.\scripts\run-real-frontend-e2e.ps1 -StartOnly
```

Then open `http://127.0.0.1:5173`. A product-path manual run can either:

- Enter a local path or `file://` URI in `Repo URI` and click `Index repo`.
- Enter a GitHub/GitLab HTTPS repo URL in `Repo URI`; add a token in Settings
  only for private repositories.
- Select a persisted graph from `Existing graphs`, click `Use existing graph`,
  fill `Alert ID` and `Raw log`, then click `Run full pipeline`.

The settings modal stores the Qwen API key and GitHub/GitLab tokens in browser
localStorage. The frontend does not call GitNexus, PostgreSQL, DashScope,
GitHub, or GitLab directly; it forwards credentials to the middleware headers.

## Dockerized deployment

The production-like Docker path runs the real chain:

```text
web container
-> /api reverse proxy
-> api container
-> gitnexus_cli mounted at /opt/gitnexus
-> PostgreSQL graph payload store
-> graph_context evidence builder
-> qwen_api RCA generation
-> PostgreSQL incident memory store
```

Create a private env file:

```powershell
Copy-Item .env.prod.example .env.prod
```

Set these private values in `.env.prod`, or inject them as process env vars
when running Compose:

```dotenv
DASHSCOPE_API_KEY=
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus
```

`GITNEXUS_REPO_ROOT` must point to a real GitNexus runtime with
`dist/cli/index.js`. The API container mounts that directory read-only at
`/opt/gitnexus` and executes it through `/usr/local/bin/gitnexus`. This is a
real GitNexus CLI path, not a mock.

Run the stack:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Open:

```text
http://127.0.0.1:8080
```

Smoke test:

```powershell
.\scripts\smoke-prod-compose.ps1 -TimeoutSeconds 240
```

The smoke script fails loudly if `GITNEXUS_REPO_ROOT/dist/cli/index.js` is
missing. It also verifies the mounted CLI from inside the API container before
checking same-origin API health through `http://127.0.0.1:8080/api/health`.

Stop while keeping data:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

Delete the local database and repo cache:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down -v
```

### Alibaba Cloud ECS

Fast hackathon deployment:

1. Create an Alibaba Cloud ECS instance with Docker and Docker Compose.
2. Clone this repository on the ECS instance.
3. Clone or build GitNexus on the ECS instance at `/opt/legacy-pilot/gitnexus`.
4. Copy `.env.prod.example` to `.env.prod`.
5. Set `DASHSCOPE_API_KEY` and `GITNEXUS_REPO_ROOT=/opt/legacy-pilot/gitnexus`.
6. Run `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`.
7. Put Nginx, Caddy, or SLB in front of port `8080` and expose HTTPS only.

For a hackathon demo, the bundled PostgreSQL container can use an ECS cloud disk
volume. For durable product data, use RDS PostgreSQL and point both
`LEGACY_PILOT_GRAPH_STORE_DSN` and `LEGACY_PILOT_INCIDENT_MEMORY_DSN` at the RDS
internal endpoint through a Compose override or ACK Secret.

### Alibaba Cloud product path

Production path:

- Build `legacy-pilot-api` and `legacy-pilot-web` images in CI.
- Push images to Alibaba Cloud ACR.
- Run `api` and `web` as ACK Deployments.
- Use RDS PostgreSQL for graph payloads and incident memory.
- Use SLB/Ingress for HTTPS.
- Store `DASHSCOPE_API_KEY`, GitHub/GitLab tokens, and PostgreSQL passwords in
  Alibaba Cloud Secret Manager or Kubernetes Secrets.
- Store repo clone cache on NAS/PVC, or keep it ephemeral with a cleanup policy.
- Send container logs to Alibaba Cloud SLS.

Network rule:

- Public: only HTTPS to `web`.
- Internal: `web -> api:8000`, `api -> PostgreSQL`.
- Outbound: DashScope, GitHub, GitLab, and remote Git clone endpoints.

ACR + ACK + RDS is the recommended product deployment shape after the ECS
Compose demo is stable.

## API Surface

- `GET /health`
- `POST /v1/repos/index`
- `POST /v1/graph/query`
- `GET /v1/graphs`
- `DELETE /v1/graphs/{repo_id}/{graph_id}`
- `POST /v1/alerts/submit`
- `POST /v1/evidence-bundles/build`
- `POST /v1/incidents/similar`
- `GET /v1/incidents/{incident_id}`
- `POST /v1/rca/generate`
- `POST /v1/rca/review`
- `POST /v1/incidents/save`

## Current Limits

- Real Structure 1 execution uses the `gitnexus_cli` backend.
- `gitnexus_http` is not implemented.
- Real Qwen semantic enrichment is available only through the opt-in `qwen_api` backend.
- Semantic graph output is pending and confidence-capped; it is not treated as a trusted structural fact.
- Structure 2 defaults to `graph_context`, which requires queryable Structure 1 graph context for useful evidence bundles.
- GitHub/GitLab repo import supports HTTPS clone URLs through `git clone
  --depth 1`; branch/tag/commit pinning is not implemented yet.
- Natural-language incidents must still produce enough graph evidence for
  Structure 3. Very broad or poorly-matched incident text can fail at
  `GenerateRCA` if Qwen returns conclusions without valid `evidence_ids`.
