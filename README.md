# LegacyPilot Interface Contract Middleware

LegacyPilot is a hackathon MVP for incident-driven legacy system analysis. This repository currently contains the first slice: a Python/FastAPI interface contract middleware that standardizes communication between the four planned LegacyPilot structures.

## What This Middleware Does

- Defines shared Pydantic contracts for cross-structure requests and responses.
- Enforces `contract_version`, `trace_id`, `confidence`, and `evidence_refs` gates.
- Returns a unified `ContractError` envelope for middleware-level failures.
- Exposes FastAPI routes for the MVP incident analysis flow.
- Uses deterministic mock routing by default, with an opt-in `gitnexus_cli` backend for Structure 1 integration checks.

Current mock flow:

```text
SubmitAlert
-> BuildEvidenceBundle
-> GenerateRCA
-> ReviewRCA
-> SaveIncident
```

## Current Progress

Structure 1 is implemented through Milestone4 while preserving the middleware
contract boundary:

- Milestone0-2: real `gitnexus_cli` indexing/query integration plus Structure 1
  enrichment for MyBatis SQL, tables, Java config, and Java exceptions.
- Milestone3: query planner and local enriched graph index for endpoint,
  method/symbol, table, config, and exception contexts.
- Milestone4: semantic graph enrichment is disabled by default, has a
  deterministic mock backend, and supports opt-in DashScope Qwen API semantic
  summaries through `qwen_api`.
- Production fixture coverage proves `/api/dataset/version -> controller ->
  service -> mapper -> Mapper XML SQL -> dataset_version`, plus config and
  exception evidence.
- Middleware/router and the four-structure contract models were not changed for
  Milestone0-4 beyond backward-compatible Structure 1 metadata fields already
  present on `GraphSnapshot`.

Latest local verification:

```text
Default suite: 129 passed, 6 skipped
Real GitNexus opt-in suite: 11 passed
Real Qwen semantic opt-in test: 1 passed
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

```bash
python -m pytest -q
```

GitNexus integration tests are skipped by default. To run them against a local GitNexus runtime:

```bash
LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1 \
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli \
GITNEXUS_BIN=gitnexus \
GITNEXUS_REPO_ROOT=Q:/Hackathons/GitNexus-main/GitNexus-main/gitnexus \
GITNEXUS_TIMEOUT_SECONDS=120 \
python -m pytest tests/test_gitnexus_integration.py -q
```

`GITNEXUS_BIN` may also point to a local wrapper such as `Q:/tmp/gitnexus-local.cmd` when testing a source checkout build.

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
structural nodes or SQL/config/exception enrichers. `ollama` remains reserved;
`qwen_api` is supported through the OpenAI-compatible DashScope Chat API.

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
- No persistent incident database is connected yet.
- Structures 2-4 still use deterministic mock responses used to validate the middleware contract and MVP flow.
