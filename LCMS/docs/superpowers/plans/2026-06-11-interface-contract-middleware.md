# Interface Contract Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Python/FastAPI middleware slice for LegacyPilot contracts, validation, trace propagation, unified errors, version gates, and mock routing.

**Architecture:** The middleware owns only contracts and orchestration. Pydantic models define the shared data objects, validators enforce evidence/confidence/trace/version gates, and a mock router runs the MVP incident pipeline without doing real parsing, RCA reasoning, or long-term storage.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, FastAPI, httpx, uvicorn.

---

## File Structure

- `pyproject.toml`: package metadata, dependencies, pytest path config.
- `legacy_pilot/contracts/enums.py`: controlled vocabularies for source types, extraction methods, verification status, and error codes.
- `legacy_pilot/contracts/errors.py`: `ContractError` envelope and exception used by validators/router.
- `legacy_pilot/contracts/models.py`: Pydantic request/response and shared contract models.
- `legacy_pilot/contracts/validators.py`: reusable gate checks for contract version, trace, evidence, and confidence.
- `legacy_pilot/middleware/router.py`: mock route handlers for `IndexRepo`, `SubmitAlert`, `BuildEvidenceBundle`, `GenerateRCA`, `ReviewRCA`, `FindSimilarIncidents`, and `SaveIncident`.
- `legacy_pilot/middleware/app.py`: FastAPI app factory and HTTP routes.
- `legacy_pilot/__init__.py`, `legacy_pilot/contracts/__init__.py`, `legacy_pilot/middleware/__init__.py`: package exports.
- `tests/test_contract_models.py`: contract validation tests.
- `tests/test_router_pipeline.py`: mock pipeline behavior tests.
- `tests/test_api.py`: FastAPI route tests.

## Task 1: Scaffold Package And Model Tests

- [ ] Write failing tests for required contract fields, confidence range, evidence refs, and contract version behavior in `tests/test_contract_models.py`.
- [ ] Run `python -m pytest tests/test_contract_models.py -q` and verify tests fail because modules are missing.
- [ ] Create package files and Pydantic contract models.
- [ ] Run the same tests and verify they pass.

## Task 2: Implement Mock Router Pipeline

- [ ] Write failing tests for `submit_alert`, `build_evidence_bundle`, `generate_rca`, `review_rca`, `find_similar_incidents`, and `save_incident` in `tests/test_router_pipeline.py`.
- [ ] Run `python -m pytest tests/test_router_pipeline.py -q` and verify tests fail because router behavior is missing.
- [ ] Implement deterministic mock router methods with trace propagation and evidence-backed outputs.
- [ ] Run the router tests and verify they pass.

## Task 3: Add FastAPI Boundary

- [ ] Write failing API tests in `tests/test_api.py` for happy-path endpoints and unified validation error envelopes.
- [ ] Install FastAPI/uvicorn if missing.
- [ ] Run `python -m pytest tests/test_api.py -q` and verify tests fail for missing API routes.
- [ ] Implement FastAPI app and routes that call the router and return `ContractError` envelopes on middleware failures.
- [ ] Run API tests and verify they pass.

## Task 4: Verify Full Slice

- [ ] Run `python -m pytest -q`.
- [ ] Optionally run `python -m uvicorn legacy_pilot.middleware.app:app --reload` and open `/docs` if uvicorn is available.
- [ ] Review created files against `docs/architecture/interface-contract-middleware-development.md`.
- [ ] Because this directory is not a git repository, list changed files instead of committing.

## Scope Notes

- No real Java parser in this slice.
- No real Qwen/LLM call in this slice.
- No persistent database in this slice.
- The mock pipeline must prove the acceptance criteria in the middleware spec: trace continuity, evidence-gated RCA review, user-confirmed incident save, and consistent contract errors.
