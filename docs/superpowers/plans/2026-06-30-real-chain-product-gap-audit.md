# Real Four-Structure Chain And Product Gap Audit

Date: 2026-06-30

Scope:

- Frontend workbench real browser flow.
- Middleware HTTP/API contract.
- Structure1 GitNexus + PostgreSQL graph store.
- Structure2 `graph_context`.
- Structure3 DashScope Qwen RCA.
- Structure4 PostgreSQL incident memory.

Audit source:

- Local code inspection.
- Prior local verification outputs in this workspace.
- `gpt-5.5` / `xhigh` subagent read-only audit result.

No API key is included in this report.

## Executive Conclusion

The real four-structure chain exists and has been proven locally by two real E2E paths:

```text
Backend E2E:
GitNexus -> PostgreSQL graph store -> Structure2 graph_context
-> real DashScope Qwen -> Structure4 PostgreSQL save/load

Frontend E2E:
Browser UI -> Middleware HTTP -> GitNexus -> PostgreSQL graph store
-> Structure2 graph_context -> real DashScope Qwen -> Structure4 PostgreSQL save response
```

The chain is not universally real by default in every command. It is real when the real E2E scripts set the backend environment correctly and when the test is not skipped. Several product gaps are real and quantifiable, especially Structure4 read/search, similar incident retrieval, active-backend observability, asynchronous jobs, and human-review editing.

## Verified Real Chain Evidence

### Real Backend Selection

`scripts/run-real-e2e.ps1` forces real backends:

- `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli`
- `LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql`
- `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context`
- `LEGACY_PILOT_INCIDENT_MEMORY_BACKEND=postgresql`
- `LEGACY_PILOT_RCA_BACKEND=qwen_api`

Evidence:

- `scripts/run-real-e2e.ps1:210-214`
- `scripts/run-real-frontend-e2e.ps1:236-242`
- `.env.example:10`, `.env.example:21-22`, `.env.example:27`, `.env.example:30-35`

### Real Qwen Gate

Structure3 default RCA backend is `qwen_api`. Missing `DASHSCOPE_API_KEY` fails loudly.

Evidence:

- `legacy_pilot/rca_reasoning_engine/adapter.py:27-38`
- `legacy_pilot/rca_reasoning_engine/adapter.py:65-72`
- `legacy_pilot/rca_reasoning_engine/adapter.py:215-229`
- `tests/test_real_structure1_structure2_e2e.py:20-33`
- `tests/test_real_structure1_structure2_e2e.py:55-59`

Quantified:

- Required real E2E env keys: 5.
- Required real backend env values: 5.
- Qwen repair attempts default: 2, bounded max: 3.

### Real Structure1 And PostgreSQL Restore

Backend real E2E uses `GitNexusCliCodeKnowledgeCoreAdapter`, writes graph payload to PostgreSQL, then creates a restore adapter whose GitNexus client is forbidden. This proves Structure2 gets graph context from persisted PostgreSQL restore instead of re-indexing.

Evidence:

- `tests/test_real_structure1_structure2_e2e.py:62-91`
- `tests/test_real_structure1_structure2_e2e.py:87-90`
- `tests/test_real_structure1_structure2_e2e.py:20-33`

Quantified:

- The test fails if restore path calls GitNexus query/index fallback.
- It asserts Structure1 graph contains SQL/Table/Config/Exception enrichment in `_assert_structure1_snapshot`.

### Real Structure2 `graph_context`

Structure2 default is `graph_context`; mock requires explicit backend.

Evidence:

- `legacy_pilot/incident_context_builder/adapter.py:23-25`
- `legacy_pilot/incident_context_builder/adapter.py:200-224`
- `README.md:36-39`

Quantified:

- Allowed Structure2 backends: 2 (`graph_context`, `mock`).
- Real scripts force `graph_context`.

### Real Structure4 PostgreSQL Save And Backend Readback

Structure4 default backend is PostgreSQL. Backend real E2E saves incident and then loads same incident from PostgreSQL by `incident_id`.

Evidence:

- `legacy_pilot/incident_memory_store/adapter.py:11-17`
- `legacy_pilot/incident_memory_store/adapter.py:49-82`
- `legacy_pilot/incident_memory_store/adapter.py:84-101`
- `legacy_pilot/incident_memory_store/adapter.py:141-171`
- `tests/test_real_structure1_structure2_e2e.py:97-111`

Quantified:

- Structure4 adapter methods: 2 (`save_incident`, `load_incident`).
- PostgreSQL record table stores 6 columns: `incident_id`, `repo_id`, `dedup_key`, `record_json`, `created_at`, `updated_at`.
- Backend E2E asserts `persisted_record == record`.

### Frontend Uses Middleware Only

Frontend API client fetches only through `/api`, and Vite rewrites `/api` to middleware. No frontend source references PostgreSQL, GitNexus, DashScope, `DASHSCOPE_API_KEY`, or `psycopg`.

Evidence:

- `frontend/src/api.ts:3-6`
- `frontend/src/api.ts:39-60`
- `frontend/vite.config.ts:14-19`
- `frontend/src/App.tsx:136-246`

Quantified:

- Primary frontend pipeline uses 6 POST routes plus health:
  - `/v1/repos/index`
  - `/v1/alerts/submit`
  - `/v1/evidence-bundles/build`
  - `/v1/rca/generate`
  - `/v1/rca/review`
  - `/v1/incidents/save`
  - `/health`

### Local Verification Already Passed

Observed local verification results from this workspace:

```text
npm run build: passed
npm run test:e2e -- --project=chromium: 1 skipped by real gate
python -m pytest -q -rs: 211 passed, 8 skipped, 1 warning
scripts/run-real-e2e.ps1: 3 passed, 2 warnings
scripts/run-real-frontend-e2e.ps1: 1 passed
secret scan: no persisted Qwen key in repository
```

The default skipped Playwright result is expected: `frontend/tests/real-four-structures.spec.ts:5-8` requires `LEGACY_PILOT_RUN_REAL_FRONTEND_E2E=1`.

## Mock, Skip, And False-Positive Risks

### Risk 1: Structure1 Default Factory Still Falls Back To Mock

Evidence:

- `legacy_pilot/code_knowledge_core/adapter.py:449-461`

Quantified:

- Default selected backend: `"mock"` when `LEGACY_PILOT_CODE_CORE_BACKEND` is absent.
- Real scripts force `gitnexus_cli`, so acceptance path is real.
- Plain `python -m uvicorn legacy_pilot.middleware.app:app` without env can still use Structure1 mock.

### Risk 2: Real E2E Tests Are Opt-In

Evidence:

- `tests/test_real_structure1_structure2_e2e.py:160-180`
- `frontend/tests/real-four-structures.spec.ts:5-8`

Quantified:

- Default Python full suite skips 8 tests.
- Frontend real E2E defaults to 1 skipped test unless env gate is set.

### Risk 3: Frontend Real Script Can Reuse Existing Middleware

Evidence:

- `scripts/run-real-frontend-e2e.ps1:299-300`
- `/health` only returns service and contract version: `legacy_pilot/middleware/app.py:68-73`.

Quantified:

- Health exposes 2 fields.
- Health exposes 0 active backend fields.
- If a stale server on the same port uses mock Structure1, current health check cannot detect it.

Mitigation:

- Run real frontend E2E on non-default ports.
- Add `/runtime/config` or extend `/health` with active backend names.
- Optionally make `run-real-frontend-e2e.ps1` fail if an existing middleware is already listening unless `-ReuseExistingBackend` is explicit.

### Risk 4: UI Has A Skip Structure1 Path

Evidence:

- `frontend/src/App.tsx:158-171`

Quantified:

- One UI control can set IndexRepo step to `skipped`.
- This is useful for diagnostics but not valid for full-chain acceptance.

### Risk 5: Similar Incidents Are Still Hardcoded

Evidence:

- `legacy_pilot/middleware/router.py:119-145`
- `legacy_pilot/incident_context_builder/adapter.py:221-224`

Quantified:

- `/v1/incidents/similar` always returns one fixed `INC-003` match.
- No current query uses Structure4 PostgreSQL for similarity.

### Risk 6: Structure1 Semantic Enrichment Is Not In The Main Real E2E

Evidence:

- `legacy_pilot/code_knowledge_core/semantic.py:206-213`
- Real scripts do not set `LEGACY_PILOT_SEMANTIC_BACKEND=qwen_api`.

Quantified:

- Semantic backend default: `disabled`.
- Real four-structure E2E validates Structural Graph + SQL/config/exception enrichment, not semantic graph.

## Product Gaps With Quantified Evidence

### Gap 1: Incident Readback API Missing

Current state:

- Structure4 adapter can `load_incident`.
- FastAPI exposes `POST /v1/incidents/save`, but no `GET /v1/incidents/{incident_id}`.

Evidence:

- Adapter read exists: `legacy_pilot/incident_memory_store/adapter.py:84-101`.
- HTTP routes list lacks read endpoint: `legacy_pilot/middleware/app.py:68-110`.

Quantified:

- Incident HTTP endpoints: 2 (`/v1/incidents/similar`, `/v1/incidents/save`).
- Incident readback endpoints: 0.
- Browser E2E can assert save response, but cannot verify persisted DB state through product API.

### Gap 2: Similar Incident Retrieval Is Not Real

Current state:

- Similar incident endpoint exists.
- It returns a fixed hardcoded `INC-003`.
- Structure4 PostgreSQL table has no similarity index/query.

Evidence:

- Hardcoded router response: `legacy_pilot/middleware/router.py:119-145`.
- Table schema: `legacy_pilot/incident_memory_store/adapter.py:103-138`.
- Contract model includes `IncidentMatch`: `legacy_pilot/contracts/models.py:139-146`.

Quantified:

- Real search query methods in Structure4 adapter: 0.
- PostgreSQL indexes for similarity/dedup search: 0.
- Hardcoded match count: 1.

### Gap 3: SaveIncident Record Construction Still Hardcoded

Current state:

- Structure4 persistence is real.
- The `IncidentRecord` content created before persistence still hardcodes module, error type, symptom, files, related nodes, and dedup key shape.

Evidence:

- `legacy_pilot/middleware/router.py:181-199`

Quantified:

- Hardcoded record fields in save path: at least 6.
- Only root cause/fix/evidence are derived from reviewed findings.

### Gap 4: Runtime Backend Observability Missing

Current state:

- UI displays run mode string from frontend proxy config.
- Backend health does not expose active adapter/backend config.

Evidence:

- `legacy_pilot/middleware/app.py:68-73`
- `frontend/src/App.tsx:395-400`

Quantified:

- Health fields: 2.
- Active backend fields: 0.
- UI can say “proxied real backend” but cannot prove `gitnexus_cli/postgresql/graph_context/qwen_api/postgresql` from API.

### Gap 5: RCA Review Is Evidence Gate, Not Independent Reviewer Agent

Current state:

- `generate_rca` calls Qwen.
- `review_rca` validates evidence and approves selected root cause, suggested fixes, and migration impact directly.

Evidence:

- `legacy_pilot/rca_reasoning_engine/adapter.py:152-167`

Quantified:

- Qwen calls in review path: 0.
- Rejected findings always: `[]`.
- Risk notes always: `[]`.

### Gap 6: Async Job Model Missing

Current state:

- API routes are synchronous request/response functions.
- Frontend waits for each step directly.

Evidence:

- FastAPI route handlers return model directly: `legacy_pilot/middleware/app.py:75-110`.
- Frontend `runStep` awaits each fetch call: `frontend/src/App.tsx:174-246`.

Quantified:

- Job endpoints: 0.
- Progress endpoints: 0.
- Cancel/retry job endpoints: 0.

Impact:

- GitNexus indexing and Qwen generation can exceed comfortable interactive request latency.

### Gap 7: Repo And Graph Management Missing

Current state:

- UI can index one repo URI and receive one `graph_id`.
- No repo list, graph history, graph version selector, or reindex history.

Evidence:

- API surface only has `POST /v1/repos/index` and `POST /v1/graph/query`: `legacy_pilot/middleware/app.py:75-81`.

Quantified:

- Repo list endpoints: 0.
- Graph version list endpoints: 0.
- Reindex history endpoints: 0.

### Gap 8: Run History And Replay Missing

Current state:

- Frontend keeps current run in memory.
- No persisted run trace list or replay endpoint.

Evidence:

- Frontend state is local React state: `frontend/src/App.tsx:95-104`.
- No route for run history in `legacy_pilot/middleware/app.py:68-110`.

Quantified:

- Run persistence models: 0.
- Run history endpoints: 0.
- Replay endpoints: 0.

### Gap 9: Human Review Editing Missing

Current state:

- UI can check `user_confirmation`.
- It cannot edit approved findings/root cause/fix/risk notes before save.

Evidence:

- Save form only captures confirmation, fix outcome, retention policy: `frontend/src/App.tsx:229-246`.
- Contract allows `ReviewedRCAReport`, but UI does not modify it.

Quantified:

- Editable RCA fields in UI before save: 0.
- Review confirmation fields: 1 checkbox.

### Gap 10: Report Export Missing

Current state:

- RCA and incident are displayed in UI.
- No export controls or backend export endpoints.

Evidence:

- Frontend route calls do not include export endpoint: `frontend/src/App.tsx:136-246`.
- Backend API surface lacks report export: `legacy_pilot/middleware/app.py:68-110`.

Quantified:

- Export formats supported: 0.
- Export endpoints: 0.

### Gap 11: CI-Grade Real E2E Missing

Current state:

- Real tests pass locally.
- They depend on local Docker Desktop, GitNexus wrapper path, persisted Qwen key, and opt-in env gates.

Evidence:

- Required env keys/values: `tests/test_real_structure1_structure2_e2e.py:20-33`.
- Local wrapper defaults: `scripts/run-real-e2e.ps1:31-33`.

Quantified:

- Required env keys: 5.
- Required backend env values: 5.
- Hardcoded local GitNexus defaults: 2.

## Recommended Acceptance Commands

Strict backend real chain:

```powershell
.\scripts\run-real-e2e.ps1 -DockerWaitSeconds 180 -PostgresWaitSeconds 90
```

Strict frontend real chain on non-default ports to avoid stale server reuse:

```powershell
.\scripts\run-real-frontend-e2e.ps1 `
  -DockerWaitSeconds 180 `
  -PostgresWaitSeconds 90 `
  -BackendWaitSeconds 90 `
  -BackendPort 18000 `
  -FrontendPort 15173
```

Default regression:

```powershell
python -m pytest -q -rs
cd frontend
npm run build
npm run test:e2e -- --project=chromium
```

Secret scan:

```powershell
rg -n "<Qwen key prefix>|<DASHSCOPE_API_KEY assignment carrying a key>" .
```

## Priority Recommendation

Next product task should be Structure4 real memory read/search, not more UI polish.

Minimum acceptance for next task:

1. Add `GET /v1/incidents/{incident_id}` through middleware.
2. Add real `find_similar_incidents` backed by Structure4 PostgreSQL.
3. Add frontend incident history/readback panel.
4. Add backend and frontend E2E assertions that saved incident is read back through product API.
5. Add runtime backend config endpoint or health extension to prove active backends from UI.
