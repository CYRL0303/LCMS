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
- MyBatis XML and SQL table extraction are phase 2 scope.
- No real Qwen/LLM call is connected yet.
- No persistent incident database is connected yet.
- Router outputs are deterministic mock responses used to validate the middleware contract and MVP flow.
