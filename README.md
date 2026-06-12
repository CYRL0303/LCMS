# LegacyPilot Interface Contract Middleware

LegacyPilot is a hackathon MVP for incident-driven legacy system analysis. This repository currently contains the first slice: a Python/FastAPI interface contract middleware that standardizes communication between the four planned LegacyPilot structures.

## What This Middleware Does

- Defines shared Pydantic contracts for cross-structure requests and responses.
- Enforces `contract_version`, `trace_id`, `confidence`, and `evidence_refs` gates.
- Returns a unified `ContractError` envelope for middleware-level failures.
- Exposes FastAPI routes for the MVP incident analysis flow.
- Uses deterministic mock routing to prove the pipeline before real parser, LLM, and memory adapters are connected.

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
  contracts/
    enums.py
    errors.py
    models.py
    validators.py
  middleware/
    app.py
    router.py
tests/
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

- No real Java parser is connected yet.
- No real Qwen/LLM call is connected yet.
- No persistent incident database is connected yet.
- Router outputs are deterministic mock responses used to validate the middleware contract and MVP flow.
