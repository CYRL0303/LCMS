# Structure3 RCA Reasoning Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Structure3 as a real Qwen-backed RCA Reasoning Engine and verify it only through the middleware using real GitNexus CLI, real PostgreSQL graph persistence, and real Qwen API.

**Architecture:** `MiddlewareRouter` remains the only cross-structure boundary. Structure1 indexes and restores graph context through GitNexus CLI plus PostgreSQL; Structure2 builds `EvidenceBundle` through middleware `QueryGraph`; Structure3 is invoked only by middleware `GenerateRCA` / `ReviewRCA` and consumes only the `EvidenceBundle` contract. `GenerateRCA` calls the real Qwen API; `ReviewRCA` is a deterministic Structure3 reviewer/evidence gate that validates Qwen output against the same input evidence. Structure3 must not import or call GitNexus, PostgreSQL graph store, Structure1 adapters, repo files, or Structure2 internals.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI middleware routes, pytest, PostgreSQL via existing graph store, GitNexus CLI via existing Structure1 adapter, DashScope/OpenAI-compatible Qwen chat completions via `urllib`.

## Global Constraints

- Structure3 tests must use real GitNexus CLI, real PostgreSQL, and real Qwen API for acceptance.
- Do not make Structure3 default to mock. `LEGACY_PILOT_RCA_BACKEND` must default to `qwen_api` or fail clearly when Qwen config is missing.
- Existing deterministic RCA code inside `MiddlewareRouter` must be removed or demoted to non-default legacy test support only.
- Structure3 only talks to middleware contracts: input is `EvidenceBundle`, output is `RCAReport` / `ReviewedRCAReport`.
- Structure3 must not call `MiddlewareRouter.query_graph()`, `CodeKnowledgeCoreAdapter`, GitNexus client, `PostgresGraphStore`, psycopg, or local repo file readers.
- The full acceptance test must drive Structure3 via HTTP middleware endpoints or `MiddlewareRouter.generate_rca()` / `MiddlewareRouter.review_rca()`, not by directly calling Structure3 from Structure2.
- Every RCA conclusion must reference `EvidenceRef` objects already present in the input `EvidenceBundle`.
- If Qwen returns evidence IDs not in the bundle, Structure3 must reject the output with `ContractError(source_module="rca_reasoning_engine")`.
- Missing GitNexus/PostgreSQL/Qwen configuration is a test environment failure when the real acceptance gate is enabled, not a reason to silently fall back to mock.
- `GenerateRCA` is the real Qwen call boundary. `ReviewRCA` is deterministic but still belongs to Structure3; it is not mock RCA generation and must never invent or add evidence.
- Default `python -m pytest -q` may skip the real E2E when the opt-in gate is absent, but any Structure3 acceptance run with the gate enabled must fail loudly if GitNexus, PostgreSQL, or Qwen credentials are missing.

---

## File Structure

Create:
- `legacy_pilot/rca_reasoning_engine/__init__.py`: exports Structure3 adapter/factory/errors.
- `legacy_pilot/rca_reasoning_engine/errors.py`: internal errors converted by middleware to `ContractError`.
- `legacy_pilot/rca_reasoning_engine/evidence.py`: evidence collection and evidence-backed report validation.
- `legacy_pilot/rca_reasoning_engine/adapter.py`: Qwen RCA adapter and backend factory. No mock default.
- `tests/test_real_structure1_structure2_e2e.py`: extend the existing real Structure1/PostgreSQL/Structure2 E2E through real Qwen Structure3.
- `tests/test_structure3_boundary.py`: static/runtime boundary tests proving Structure3 does not import or call lower structures.

Modify:
- `legacy_pilot/middleware/router.py`: inject `RCAReasoningEngineAdapter`; delegate `generate_rca()` and `review_rca()` after middleware gates.
- `legacy_pilot/middleware/app.py`: keep existing `/v1/rca/generate` and `/v1/rca/review` endpoints; no new direct Structure3 endpoint.
- `.env.example`: document real Structure3 env vars with `LEGACY_PILOT_RCA_BACKEND=qwen_api`.
- `pyproject.toml`: update the existing real E2E marker description to include Structure3/Qwen.
- `tests/test_router_pipeline.py`: remove or revise assertions that Structure3 defaults to mock.
- `tests/test_api.py`: keep API tests but configure real dependencies for Structure3 acceptance or limit old mock checks to pre-Structure3 contract compatibility.
- `tests/test_real_structure1_structure2_e2e_config.py`: require Structure3 env vars in the real chain documentation/config tests.
- `docs/architecture/interface-contract-middleware-implementation.md`: document Structure3 as real Qwen adapter behind middleware.
- `docs/architecture/structure1-postgres-structure2-real-e2e-verification.md`: extend the verified chain through Structure3.

---

### Task 1: Add Structure3 Evidence Gates

**Files:**
- Create: `legacy_pilot/rca_reasoning_engine/errors.py`
- Create: `legacy_pilot/rca_reasoning_engine/evidence.py`
- Test: `tests/test_structure3_boundary.py`

**Interfaces:**
- Consumes: `EvidenceBundle`, `RCAReport`, `EvidenceBackedItem`.
- Produces: `collect_bundle_evidence(bundle: EvidenceBundle) -> list[EvidenceRef]`, `evidence_by_id(bundle: EvidenceBundle) -> dict[str, EvidenceRef]`, `assert_report_is_evidence_backed(report: RCAReport) -> None`.

- [ ] **Step 1: Write failing evidence-gate tests**

Create `tests/test_structure3_boundary.py`:

```python
from datetime import UTC, datetime

import pytest

from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    IncidentQuery,
    RCAReport,
)
from legacy_pilot.rca_reasoning_engine.errors import (
    RCAGenerationError,
    RCAEvidenceRequiredError,
)
from legacy_pilot.rca_reasoning_engine.evidence import (
    assert_report_is_evidence_backed,
    collect_bundle_evidence,
    evidence_by_id,
)


def test_collect_bundle_evidence_deduplicates_bundle_sources():
    code = evidence_ref("EV-CODE-1", "code")
    sql = evidence_ref("EV-SQL-1", "sql")
    log = evidence_ref("EV-LOG-1", "log")
    bundle = evidence_bundle(
        code_evidence=[code],
        sql_evidence=[sql],
        log_evidence=[log, code],
    )

    collected = collect_bundle_evidence(bundle)

    assert [ref.evidence_id for ref in collected] == [
        "EV-CODE-1",
        "EV-SQL-1",
        "EV-LOG-1",
    ]
    assert evidence_by_id(bundle)["EV-CODE-1"] == code


def test_report_gate_rejects_unsupported_strong_conclusion():
    evidence = evidence_ref("EV-CODE-1", "code")
    report = valid_report(evidence)
    unsupported = EvidenceBackedItem.model_construct(
        summary="unsupported conclusion",
        evidence_refs=[],
        confidence=0.9,
    )
    invalid = RCAReport.model_construct(
        **{**report.model_dump(), "selected_root_cause": unsupported}
    )

    with pytest.raises(RCAEvidenceRequiredError) as excinfo:
        assert_report_is_evidence_backed(invalid)

    assert excinfo.value.error_code == "EVIDENCE_REQUIRED"
    assert "selected_root_cause" in excinfo.value.message
```

Add helpers in the same file:

```python
def evidence_ref(evidence_id: str, source_type: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-STRUCTURE3-001",
        source_type=source_type,
        source_id=evidence_id,
        file_path="src/main/java/com/legacy/DatasetService.java"
        if source_type == "code"
        else None,
        start_line=40 if source_type == "code" else None,
        end_line=45 if source_type == "code" else None,
        excerpt=f"{source_type} evidence",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 29, tzinfo=UTC),
    )


def incident_query() -> IncidentQuery:
    return IncidentQuery(
        trace_id="TRACE-STRUCTURE3-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )


def evidence_bundle(**updates) -> EvidenceBundle:
    values = {
        "trace_id": "TRACE-STRUCTURE3-001",
        "repo_id": "repo-demo",
        "contract_version": "1.0.0",
        "alert_summary": "NullPointerException near DatasetService.getVersion",
        "incident_query": incident_query(),
    }
    values.update(updates)
    return EvidenceBundle(**values)


def backed(summary: str, evidence: EvidenceRef) -> EvidenceBackedItem:
    return EvidenceBackedItem(
        summary=summary,
        evidence_refs=[evidence],
        confidence=0.8,
    )


def valid_report(evidence: EvidenceRef) -> RCAReport:
    root = backed("DatasetService uses datasetId without a guard.", evidence)
    fix = backed("Add request validation and service guard for datasetId.", evidence)
    impact = backed("Dataset version endpoint and mapper SQL are affected.", evidence)
    return RCAReport(
        report_id="RCA-STRUCTURE3-001",
        trace_id="TRACE-STRUCTURE3-001",
        repo_id="repo-demo",
        contract_version="1.0.0",
        hypotheses=[root],
        selected_root_cause=root,
        evidence_chain=[evidence],
        affected_path=["DatasetController.getVersion", "DatasetService.getVersion"],
        suggested_fix=[fix],
        migration_impact=impact,
        migration_checklist=["Add null datasetId regression coverage."],
        confidence=0.8,
    )
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_structure3_boundary.py -q`

Expected: FAIL because `legacy_pilot.rca_reasoning_engine` does not exist.

- [ ] **Step 3: Implement Structure3 errors**

Create `legacy_pilot/rca_reasoning_engine/errors.py`:

```python
from legacy_pilot.contracts.enums import ErrorCode


SOURCE_MODULE = "rca_reasoning_engine"


class RCAReasoningEngineError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = ErrorCode.VALIDATION_ERROR,
        recoverable: bool = True,
        missing_fields: list[str] | None = None,
        diagnostics: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.recoverable = recoverable
        self.source_module = SOURCE_MODULE
        self.missing_fields = missing_fields or []
        self.diagnostics = diagnostics or {}


class RCAGenerationError(RCAReasoningEngineError):
    pass


class RCAReviewError(RCAReasoningEngineError):
    pass


class RCAEvidenceRequiredError(RCAReasoningEngineError):
    def __init__(self, message: str):
        super().__init__(
            message,
            error_code=ErrorCode.EVIDENCE_REQUIRED,
            recoverable=True,
        )
```

- [ ] **Step 4: Implement evidence helpers**

Create `legacy_pilot/rca_reasoning_engine/evidence.py`:

```python
from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    RCAReport,
)
from legacy_pilot.rca_reasoning_engine.errors import RCAEvidenceRequiredError


def collect_bundle_evidence(bundle: EvidenceBundle) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for ref in [
        *bundle.code_evidence,
        *bundle.sql_evidence,
        *bundle.config_evidence,
        *bundle.log_evidence,
    ]:
        _append_once(refs, seen, ref)
    for incident in bundle.similar_incidents:
        for ref in incident.evidence_refs:
            _append_once(refs, seen, ref)
    return refs


def evidence_by_id(bundle: EvidenceBundle) -> dict[str, EvidenceRef]:
    return {ref.evidence_id: ref for ref in collect_bundle_evidence(bundle)}


def assert_bundle_has_evidence(bundle: EvidenceBundle) -> list[EvidenceRef]:
    evidence = collect_bundle_evidence(bundle)
    if not evidence:
        raise RCAEvidenceRequiredError(
            "EvidenceBundle must contain evidence before RCA generation."
        )
    return evidence


def assert_report_is_evidence_backed(report: RCAReport) -> None:
    _require_item_evidence("selected_root_cause", report.selected_root_cause)
    for index, hypothesis in enumerate(report.hypotheses):
        _require_item_evidence(f"hypotheses[{index}]", hypothesis)
    for index, fix in enumerate(report.suggested_fix):
        _require_item_evidence(f"suggested_fix[{index}]", fix)
    _require_item_evidence("migration_impact", report.migration_impact)
    if not report.evidence_chain:
        raise RCAEvidenceRequiredError("evidence_chain must include evidence_refs.")


def _require_item_evidence(field_name: str, item: EvidenceBackedItem) -> None:
    if not getattr(item, "evidence_refs", None):
        raise RCAEvidenceRequiredError(f"{field_name} must include evidence_refs.")


def _append_once(refs: list[EvidenceRef], seen: set[str], ref: EvidenceRef) -> None:
    if ref.evidence_id in seen:
        return
    seen.add(ref.evidence_id)
    refs.append(ref)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_structure3_boundary.py -q`

Expected: PASS for evidence-gate tests.

- [ ] **Step 6: Commit**

Run:

```bash
git add legacy_pilot/rca_reasoning_engine/errors.py legacy_pilot/rca_reasoning_engine/evidence.py tests/test_structure3_boundary.py
git commit -m "feat: add structure3 evidence gates"
```

---

### Task 2: Add Real Qwen RCA Adapter With No Mock Default

**Files:**
- Create: `legacy_pilot/rca_reasoning_engine/adapter.py`
- Create: `legacy_pilot/rca_reasoning_engine/__init__.py`
- Modify: `tests/test_structure3_boundary.py`

**Interfaces:**
- Consumes: `LEGACY_PILOT_RCA_BACKEND=qwen_api`, `LEGACY_PILOT_RCA_BASE_URL`, `LEGACY_PILOT_RCA_MODEL`, `LEGACY_PILOT_RCA_CONFIDENCE_CAP`, `DASHSCOPE_API_KEY`.
- Produces: `QwenApiRCAReasoningEngineAdapter.generate_rca(bundle: EvidenceBundle) -> RCAReport`, `review_rca(report: RCAReport) -> ReviewedRCAReport`.

- [ ] **Step 1: Add failing adapter config and boundary tests**

Append to `tests/test_structure3_boundary.py`:

```python
import ast
import builtins
import subprocess
from pathlib import Path

from legacy_pilot.rca_reasoning_engine.adapter import (
    QwenApiRCAReasoningEngineAdapter,
    create_rca_reasoning_engine_adapter,
)


def test_rca_factory_defaults_to_qwen_api_not_mock(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_RCA_BACKEND", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    adapter = create_rca_reasoning_engine_adapter()

    assert isinstance(adapter, QwenApiRCAReasoningEngineAdapter)


def test_structure3_package_imports_only_contracts_and_own_package():
    root = Path(__file__).resolve().parents[1] / "legacy_pilot" / "rca_reasoning_engine"
    allowed_legacy_prefixes = (
        "legacy_pilot.contracts",
        "legacy_pilot.rca_reasoning_engine",
    )
    forbidden_imports = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if module.startswith("legacy_pilot") and not module.startswith(
                    allowed_legacy_prefixes
                ):
                    forbidden_imports.append(f"{path.name}:{module}")

    assert forbidden_imports == []


def test_structure3_generation_does_not_touch_files_processes_or_lower_structures(monkeypatch):
    def forbidden_call(*args, **kwargs):
        raise AssertionError("Structure3 must not touch files, subprocesses, or lower structures")

    monkeypatch.setattr(builtins, "open", forbidden_call)
    monkeypatch.setattr(Path, "read_text", forbidden_call)
    monkeypatch.setattr(Path, "read_bytes", forbidden_call)
    monkeypatch.setattr(subprocess, "run", forbidden_call)

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)
    bundle = evidence_bundle(code_evidence=[evidence_ref("EV-CODE-1", "code")])

    report = adapter.generate_rca(bundle)
    reviewed = adapter.review_rca(report)

    assert report.selected_root_cause.evidence_refs
    assert reviewed.approved_findings
```

Also add a plain forbidden-token guard for names that should never appear in the Structure3 package:

```python
def test_structure3_package_has_no_lower_structure_runtime_tokens():
    root = Path(__file__).resolve().parents[1] / "legacy_pilot" / "rca_reasoning_engine"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = [
        "PostgresGraphStore",
        "GitNexus",
        "psycopg",
        "query_graph",
        "repo_uri",
        "subprocess",
        "Path(",
    ]
    for token in forbidden:
        assert token not in text
```

- [ ] **Step 2: Add failing Qwen response mapping test**

Append:

```python
def test_qwen_adapter_maps_real_api_shape_to_evidence_backed_report():
    requests = []

    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        requests.append({"url": url, "headers": headers, "body": body})
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId is missing before mapper read",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.72}],'
                            '"selected_root_cause":{"summary":"datasetId guard is missing in the service path",'
                            '"evidence_ids":["EV-CODE-1","EV-LOG-1"],"confidence":0.74},'
                            '"suggested_fix":[{"summary":"validate datasetId before service and mapper calls",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"dataset version endpoint and mapper SQL need regression coverage",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.66},'
                            '"migration_checklist":["Add null datasetId endpoint regression test"],'
                            '"affected_path":["DatasetController.getVersion","DatasetService.getVersion"],'
                            '"open_questions":[],"confidence":0.74}'
                        )
                    }
                }
            ]
        }

    code = evidence_ref("EV-CODE-1", "code")
    log = evidence_ref("EV-LOG-1", "log")
    adapter = QwenApiRCAReasoningEngineAdapter(
        api_key="test-key",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        confidence_cap=0.5,
        http_post=fake_post,
    )

    report = adapter.generate_rca(evidence_bundle(code_evidence=[code], log_evidence=[log]))

    assert requests[0]["url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert requests[0]["headers"]["Authorization"] == "Bearer test-key"
    prompt = requests[0]["body"]["messages"][1]["content"]
    assert "EV-CODE-1" in prompt
    assert "EV-LOG-1" in prompt
    assert report.selected_root_cause.summary == "datasetId guard is missing in the service path"
    assert [ref.evidence_id for ref in report.selected_root_cause.evidence_refs] == [
        "EV-CODE-1",
        "EV-LOG-1",
    ]
    assert report.confidence == 0.5
```

Also add the required negative adapter test:

```python
def test_qwen_adapter_rejects_unknown_evidence_ids():
    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"selected_root_cause":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"suggested_fix":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"migration_impact":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"migration_checklist":[],"affected_path":[],'
                            '"open_questions":[],"confidence":0.9}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(
        api_key="test-key",
        http_post=fake_post,
    )
    bundle = evidence_bundle(code_evidence=[evidence_ref("EV-CODE-1", "code")])

    with pytest.raises(RCAGenerationError) as excinfo:
        adapter.generate_rca(bundle)

    assert "unknown evidence_ids" in excinfo.value.message
    assert "EV-UNKNOWN" in excinfo.value.message
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest tests/test_structure3_boundary.py -q`

Expected: FAIL because the Qwen adapter and factory do not exist.

- [ ] **Step 4: Implement Qwen-only adapter**

Create `legacy_pilot/rca_reasoning_engine/adapter.py`:

```python
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from json import dumps, loads
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    RCAReport,
    ReviewedRCAReport,
)
from legacy_pilot.rca_reasoning_engine.errors import (
    RCAGenerationError,
    RCAReasoningEngineError,
)
from legacy_pilot.rca_reasoning_engine.evidence import (
    assert_bundle_has_evidence,
    assert_report_is_evidence_backed,
    evidence_by_id,
)


RCA_BACKEND_ENV = "LEGACY_PILOT_RCA_BACKEND"
RCA_BASE_URL_ENV = "LEGACY_PILOT_RCA_BASE_URL"
RCA_MODEL_ENV = "LEGACY_PILOT_RCA_MODEL"
RCA_CONFIDENCE_CAP_ENV = "LEGACY_PILOT_RCA_CONFIDENCE_CAP"
DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_RCA_BACKEND = "qwen_api"
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_RCA_CONFIDENCE_CAP = 0.75


class RCAReasoningEngineAdapter(ABC):
    @abstractmethod
    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        ...

    @abstractmethod
    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        ...
```

Add Qwen class:

```python
@dataclass(frozen=True)
class QwenApiRCAReasoningEngineAdapter(RCAReasoningEngineAdapter):
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_QWEN_BASE_URL
    model: str = DEFAULT_QWEN_MODEL
    confidence_cap: float = DEFAULT_RCA_CONFIDENCE_CAP
    http_post: Any | None = None
    backend_name: str = "qwen_api"

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        evidence = assert_bundle_has_evidence(bundle)
        api_key = self.api_key or os.getenv(DASHSCOPE_API_KEY_ENV)
        if not api_key:
            raise RCAGenerationError(
                "DASHSCOPE_API_KEY is required for qwen_api RCA backend.",
                recoverable=True,
            )
        response = self._post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are LegacyPilot Structure3 RCA Reasoning Engine. "
                            "Use only evidence IDs from the supplied EvidenceBundle. "
                            "Return strict JSON and never invent evidence IDs."
                        ),
                    },
                    {"role": "user", "content": _qwen_rca_prompt(bundle, evidence)},
                ],
                "temperature": 0,
            },
        )
        raw = _chat_completion_content(response)
        payload = _loads_json_object(raw)
        return _report_from_qwen_payload(
            bundle=bundle,
            payload=payload,
            evidence_lookup=evidence_by_id(bundle),
            confidence_cap=self.confidence_cap,
        )

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        assert_report_is_evidence_backed(report)
        return ReviewedRCAReport(
            report_id=report.report_id,
            trace_id=report.trace_id,
            repo_id=report.repo_id,
            approved_findings=[
                report.selected_root_cause,
                *report.suggested_fix,
                report.migration_impact,
            ],
            rejected_findings=[],
            missing_evidence=list(report.open_questions),
            risk_notes=[],
            final_confidence=report.confidence,
        )

    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if self.http_post is not None:
            return self.http_post(url, headers, body)
        return _http_post_json(url, headers=headers, body=body)
```

Add factory:

```python
class UnsupportedRCAReasoningEngineAdapter(RCAReasoningEngineAdapter):
    def __init__(self, backend: str):
        self._backend = backend

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        raise RCAGenerationError(
            f"Unsupported RCA Reasoning Engine backend: {self._backend}",
            recoverable=True,
        )

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        raise RCAGenerationError(
            f"Unsupported RCA Reasoning Engine backend: {self._backend}",
            recoverable=True,
        )


def create_rca_reasoning_engine_adapter(
    *,
    backend: str | None = None,
) -> RCAReasoningEngineAdapter:
    selected = (backend or os.getenv(RCA_BACKEND_ENV) or DEFAULT_RCA_BACKEND).strip().lower()
    if selected == "qwen_api":
        return QwenApiRCAReasoningEngineAdapter(
            base_url=os.getenv(RCA_BASE_URL_ENV, DEFAULT_QWEN_BASE_URL),
            model=os.getenv(RCA_MODEL_ENV, DEFAULT_QWEN_MODEL),
            confidence_cap=_confidence_cap(),
        )
    return UnsupportedRCAReasoningEngineAdapter(selected)
```

Add mapping/prompt helpers:

```python
def _qwen_rca_prompt(bundle: EvidenceBundle, evidence: list[EvidenceRef]) -> str:
    evidence_lines = [
        (
            f"- {ref.evidence_id}: source_type={ref.source_type}; "
            f"source_id={ref.source_id}; file={ref.file_path}; "
            f"lines={ref.start_line}-{ref.end_line}; excerpt={ref.excerpt}"
        )
        for ref in evidence
    ]
    return (
        f"trace_id: {bundle.trace_id}\n"
        f"repo_id: {bundle.repo_id}\n"
        f"alert_summary: {bundle.alert_summary}\n"
        f"error_type: {bundle.incident_query.error_type}\n"
        f"suspected_location: {bundle.incident_query.suspected_location}\n"
        f"graph_paths: {bundle.graph_paths}\n"
        f"missing_evidence: {bundle.missing_evidence}\n"
        "Evidence IDs:\n"
        + "\n".join(evidence_lines)
        + "\nReturn JSON with keys hypotheses, selected_root_cause, suggested_fix, "
        "migration_impact, migration_checklist, affected_path, open_questions, confidence. "
        "Each conclusion object must contain summary, evidence_ids, confidence."
    )


def _report_from_qwen_payload(
    *,
    bundle: EvidenceBundle,
    payload: dict[str, Any],
    evidence_lookup: dict[str, EvidenceRef],
    confidence_cap: float,
) -> RCAReport:
    hypotheses = [
        _item_from_qwen(raw, evidence_lookup, "hypotheses")
        for raw in payload.get("hypotheses", [])
    ]
    selected_root_cause = _item_from_qwen(
        payload.get("selected_root_cause"),
        evidence_lookup,
        "selected_root_cause",
    )
    suggested_fix = [
        _item_from_qwen(raw, evidence_lookup, "suggested_fix")
        for raw in payload.get("suggested_fix", [])
    ]
    migration_impact = _item_from_qwen(
        payload.get("migration_impact"),
        evidence_lookup,
        "migration_impact",
    )
    evidence_chain = _dedupe_evidence(
        [
            ref
            for item in [*hypotheses, selected_root_cause, *suggested_fix, migration_impact]
            for ref in item.evidence_refs
        ]
    )
    report = RCAReport(
        report_id=f"RCA-{bundle.trace_id.removeprefix('TRACE-')}",
        trace_id=bundle.trace_id,
        repo_id=bundle.repo_id,
        contract_version=bundle.contract_version,
        hypotheses=hypotheses,
        selected_root_cause=selected_root_cause,
        evidence_chain=evidence_chain,
        affected_path=[str(value) for value in payload.get("affected_path", [])],
        suggested_fix=suggested_fix,
        migration_impact=migration_impact,
        migration_checklist=[str(value) for value in payload.get("migration_checklist", [])],
        confidence=min(float(payload.get("confidence", confidence_cap)), confidence_cap),
        open_questions=[str(value) for value in payload.get("open_questions", [])],
    )
    assert_report_is_evidence_backed(report)
    return report


def _item_from_qwen(
    raw: Any,
    evidence_lookup: dict[str, EvidenceRef],
    field_name: str,
) -> EvidenceBackedItem:
    if not isinstance(raw, dict):
        raise RCAGenerationError(f"{field_name} must be an object.")
    evidence_ids = raw.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise RCAGenerationError(f"{field_name} must include evidence_ids.")
    unknown = [str(eid) for eid in evidence_ids if str(eid) not in evidence_lookup]
    if unknown:
        raise RCAGenerationError(
            f"{field_name} referenced unknown evidence_ids: {', '.join(unknown)}"
        )
    return EvidenceBackedItem(
        summary=str(raw.get("summary", "")).strip(),
        evidence_refs=[evidence_lookup[str(eid)] for eid in evidence_ids],
        confidence=min(float(raw.get("confidence", 0.0)), 1.0),
    )
```

Add HTTP/json helpers:

```python
def _chat_completion_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content).strip() if content is not None else ""


def _loads_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
    try:
        payload = loads(cleaned)
    except ValueError as exc:
        raise RCAGenerationError("Qwen RCA backend returned non-JSON content.") from exc
    if not isinstance(payload, dict):
        raise RCAGenerationError("Qwen RCA backend returned JSON that is not an object.")
    return payload


def _http_post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
) -> dict[str, Any]:
    request = Request(
        url,
        data=dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RCAGenerationError(f"Qwen RCA API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RCAGenerationError(f"Qwen RCA API request failed: {exc.reason}") from exc


def _dedupe_evidence(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    result: list[EvidenceRef] = []
    seen: set[str] = set()
    for ref in refs:
        if ref.evidence_id in seen:
            continue
        seen.add(ref.evidence_id)
        result.append(ref)
    return result


def _confidence_cap() -> float:
    raw = os.getenv(RCA_CONFIDENCE_CAP_ENV)
    if raw is None:
        return DEFAULT_RCA_CONFIDENCE_CAP
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RCA_CONFIDENCE_CAP
    return min(max(value, 0.0), 1.0)
```

- [ ] **Step 5: Implement exports**

Create `legacy_pilot/rca_reasoning_engine/__init__.py`:

```python
from legacy_pilot.rca_reasoning_engine.adapter import (
    QwenApiRCAReasoningEngineAdapter,
    RCAReasoningEngineAdapter,
    UnsupportedRCAReasoningEngineAdapter,
    create_rca_reasoning_engine_adapter,
)
from legacy_pilot.rca_reasoning_engine.errors import (
    RCAGenerationError,
    RCAEvidenceRequiredError,
    RCAReasoningEngineError,
)

__all__ = [
    "QwenApiRCAReasoningEngineAdapter",
    "RCAReasoningEngineAdapter",
    "UnsupportedRCAReasoningEngineAdapter",
    "create_rca_reasoning_engine_adapter",
    "RCAGenerationError",
    "RCAEvidenceRequiredError",
    "RCAReasoningEngineError",
]
```

- [ ] **Step 6: Run boundary tests**

Run: `python -m pytest tests/test_structure3_boundary.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add legacy_pilot/rca_reasoning_engine tests/test_structure3_boundary.py
git commit -m "feat: add real qwen structure3 adapter"
```

---

### Task 3: Route Structure3 Only Through Middleware

**Files:**
- Modify: `legacy_pilot/middleware/router.py`
- Modify: `tests/test_router_pipeline.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `RCAReasoningEngineAdapter`.
- Produces: middleware `generate_rca()` and `review_rca()` that delegate to Structure3 and convert Structure3 errors into `ContractError`.

- [ ] **Step 1: Add failing middleware delegation tests**

Modify `tests/test_router_pipeline.py` to remove any expectation that default RCA is mock. Add:

```python
def test_generate_rca_requires_qwen_configuration_when_no_mock_backend(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("LEGACY_PILOT_RCA_BACKEND", raising=False)
    router = MiddlewareRouter()
    bundle = router.build_evidence_bundle(router.submit_alert(alert_event()))

    with pytest.raises(ContractViolation) as excinfo:
        router.generate_rca(bundle)

    error = excinfo.value.error
    assert error.trace_id == bundle.trace_id
    assert error.source_module == "rca_reasoning_engine"
    assert error.recoverable is True
    assert "DASHSCOPE_API_KEY" in error.message
```

Add a middleware-only success test using a local fake HTTP transport injected into the Structure3 adapter, not a mock Structure3 backend:

```python
def test_router_delegates_generate_and_review_to_qwen_structure3_adapter():
    from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001","EV-LOG-001"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)
    router = MiddlewareRouter(rca_reasoning_engine_adapter=adapter)
    bundle = router.build_evidence_bundle(router.submit_alert(alert_event()))

    report = router.generate_rca(bundle)
    reviewed = router.review_rca(report)

    assert report.trace_id == bundle.trace_id
    assert report.selected_root_cause.evidence_refs
    assert reviewed.approved_findings
```

Add router-level unknown evidence ID coverage:

```python
def test_router_converts_unknown_qwen_evidence_id_to_structure3_contract_error():
    from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"selected_root_cause":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"suggested_fix":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"migration_impact":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"migration_checklist":[],"affected_path":[],'
                            '"open_questions":[],"confidence":0.9}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)
    router = MiddlewareRouter(rca_reasoning_engine_adapter=adapter)
    bundle = router.build_evidence_bundle(router.submit_alert(alert_event()))

    with pytest.raises(ContractViolation) as excinfo:
        router.generate_rca(bundle)

    error = excinfo.value.error
    assert error.trace_id == bundle.trace_id
    assert error.source_module == "rca_reasoning_engine"
    assert error.error_code == "VALIDATION_ERROR"
    assert "EV-UNKNOWN" in error.message
```

Replace the existing `test_mock_pipeline_produces_evidence_backed_rca_and_incident_record()` with a Qwen-injected pipeline test:

```python
def qwen_rca_adapter_for_existing_mock_bundle():
    from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001","EV-LOG-001"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    return QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)


def test_pipeline_produces_qwen_evidence_backed_rca_and_incident_record():
    router = MiddlewareRouter(rca_reasoning_engine_adapter=qwen_rca_adapter_for_existing_mock_bundle())

    query = router.submit_alert(alert_event())
    bundle = router.build_evidence_bundle(query)
    report = router.generate_rca(bundle)
    reviewed = router.review_rca(report)
    record = router.save_incident(
        reviewed_report=reviewed,
        user_confirmation=True,
        fix_outcome="fixed by adding validation",
        retention_policy="demo-30-days",
        contract_version="1.0.0",
    )

    assert report.selected_root_cause.summary == "datasetId guard missing"
    assert {ref.evidence_id for ref in report.evidence_chain}.issubset(
        {ref.evidence_id for ref in [*bundle.code_evidence, *bundle.log_evidence]}
    )
    assert reviewed.approved_findings
    assert record.confirmed_by_user is True
```

Modify `tests/test_api.py` with explicit Qwen adapter injection, not default mock:

```python
def test_generate_rca_endpoint_converts_unknown_qwen_evidence_id_to_contract_error():
    from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"selected_root_cause":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"suggested_fix":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"migration_impact":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"migration_checklist":[],"affected_path":[],'
                            '"open_questions":[],"confidence":0.9}'
                        )
                    }
                }
            ]
        }

    router = MiddlewareRouter(
        rca_reasoning_engine_adapter=QwenApiRCAReasoningEngineAdapter(
            api_key="test-key",
            http_post=fake_post,
        )
    )
    client = TestClient(create_app(router=router))
    query = client.post("/v1/alerts/submit", json=alert_payload()).json()
    bundle = client.post("/v1/evidence-bundles/build", json=query).json()

    response = client.post("/v1/rca/generate", json=bundle)

    assert response.status_code == 400
    body = response.json()
    assert body["trace_id"] == "TRACE-ALERT-001"
    assert body["source_module"] == "rca_reasoning_engine"
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "EV-UNKNOWN" in body["message"]
```

Replace the existing `test_http_pipeline_builds_reviews_and_saves_incident()` with a `create_app(router=...)` version that injects the same fake Qwen adapter. The test must assert the report came from the fake Qwen JSON, not from router-local deterministic RCA:

```python
def test_http_pipeline_builds_qwen_reviews_and_saves_incident():
    from legacy_pilot.rca_reasoning_engine.adapter import QwenApiRCAReasoningEngineAdapter

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-001","EV-LOG-001"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-CODE-001"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    router = MiddlewareRouter(
        rca_reasoning_engine_adapter=QwenApiRCAReasoningEngineAdapter(
            api_key="test-key",
            http_post=fake_post,
        )
    )
    client = TestClient(create_app(router=router))
    query = client.post("/v1/alerts/submit", json=alert_payload()).json()
    bundle = client.post("/v1/evidence-bundles/build", json=query).json()
    report_response = client.post("/v1/rca/generate", json=bundle)
    reviewed_response = client.post("/v1/rca/review", json=report_response.json())
    record_response = client.post(
        "/v1/incidents/save",
        json={
            "reviewed_report": reviewed_response.json(),
            "user_confirmation": True,
            "fix_outcome": "fixed by adding validation",
            "retention_policy": "demo-30-days",
            "contract_version": "1.0.0",
        },
    )

    assert report_response.status_code == 200
    assert report_response.json()["selected_root_cause"]["summary"] == "datasetId guard missing"
    assert reviewed_response.status_code == 200
    assert record_response.status_code == 200
```

- [ ] **Step 2: Wire router**

Modify `legacy_pilot/middleware/router.py` imports:

```python
from legacy_pilot.rca_reasoning_engine.adapter import (
    RCAReasoningEngineAdapter,
    create_rca_reasoning_engine_adapter,
)
from legacy_pilot.rca_reasoning_engine.errors import RCAReasoningEngineError
```

Change constructor:

```python
def __init__(
    self,
    now: Callable[[], datetime] | None = None,
    *,
    code_knowledge_core_adapter: CodeKnowledgeCoreAdapter | None = None,
    incident_context_builder_adapter: IncidentContextBuilderAdapter | None = None,
    rca_reasoning_engine_adapter: RCAReasoningEngineAdapter | None = None,
):
```

Initialize:

```python
self._rca_reasoning_engine_adapter = (
    rca_reasoning_engine_adapter or create_rca_reasoning_engine_adapter()
)
```

Replace router-local RCA implementation:

```python
def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
    ensure_trace_id(bundle.trace_id)
    ensure_supported_contract_version(bundle.contract_version, trace_id=bundle.trace_id)
    try:
        return self._rca_reasoning_engine_adapter.generate_rca(bundle)
    except RCAReasoningEngineError as exc:
        raise self._rca_reasoning_error(trace_id=bundle.trace_id, error=exc) from exc


def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
    ensure_trace_id(report.trace_id)
    ensure_supported_contract_version(report.contract_version, trace_id=report.trace_id)
    try:
        return self._rca_reasoning_engine_adapter.review_rca(report)
    except RCAReasoningEngineError as exc:
        raise self._rca_reasoning_error(trace_id=report.trace_id, error=exc) from exc
```

Add:

```python
def _rca_reasoning_error(
    self,
    *,
    trace_id: str,
    error: RCAReasoningEngineError,
) -> ContractViolation:
    return ContractViolation(
        ContractError(
            trace_id=trace_id,
            error_code=error.error_code,
            message=error.message,
            source_module=error.source_module,
            recoverable=error.recoverable,
            missing_fields=error.missing_fields,
        )
    )
```

- [ ] **Step 3: Run focused middleware tests**

Run: `python -m pytest tests/test_router_pipeline.py tests/test_api.py tests/test_structure3_boundary.py -q`

Expected: PASS after revising old mock expectations.

- [ ] **Step 4: Commit**

Run:

```bash
git add legacy_pilot/middleware/router.py tests/test_router_pipeline.py tests/test_api.py
git commit -m "feat: route structure3 through middleware"
```

---

### Task 4: Extend Existing Real Structure1/PostgreSQL/Structure2 E2E Through Structure3

**Files:**
- Modify: `tests/test_real_structure1_structure2_e2e.py`
- Modify: `tests/test_real_structure1_structure2_e2e_config.py`

**Interfaces:**
- Consumes real env:
  - `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli`
  - `GITNEXUS_BIN`
  - `GITNEXUS_REPO_ROOT`
  - `LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql`
  - `LEGACY_PILOT_GRAPH_STORE_DSN`
  - `LEGACY_PILOT_GRAPH_STORE_TABLE`
  - `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context`
  - `LEGACY_PILOT_RCA_BACKEND=qwen_api`
  - `LEGACY_PILOT_RCA_BASE_URL`
  - `LEGACY_PILOT_RCA_MODEL`
  - `DASHSCOPE_API_KEY`
- Produces real `ReviewedRCAReport` through middleware.

- [ ] **Step 1: Extend the existing real E2E environment contract**

Modify `tests/test_real_structure1_structure2_e2e.py`:

```python
# Add to REQUIRED_ENV_KEYS:
REQUIRED_ENV_KEYS = (
    "GITNEXUS_BIN",
    "GITNEXUS_REPO_ROOT",
    "LEGACY_PILOT_GRAPH_STORE_DSN",
    "DASHSCOPE_API_KEY",
)

# Add to REQUIRED_ENV_VALUES:
REQUIRED_ENV_VALUES = {
    "LEGACY_PILOT_CODE_CORE_BACKEND": "gitnexus_cli",
    "LEGACY_PILOT_GRAPH_STORE_BACKEND": "postgresql",
    "LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND": "graph_context",
    "LEGACY_PILOT_RCA_BACKEND": "qwen_api",
}
```

- [ ] **Step 2: Extend the existing real E2E assertions**

In `test_real_gitnexus_postgres_structure2_e2e()`, keep the existing Structure1/PostgreSQL restore setup and existing `QueryForbiddenClient`. Replace the RCA assertion block with:

```python
    report = router.generate_rca(bundle)
    reviewed = router.review_rca(report)
    record = router.save_incident(
        reviewed_report=reviewed,
        user_confirmation=True,
        fix_outcome="verified_by_real_structure3_e2e",
        retention_policy="e2e-test",
        contract_version="1.0.0",
    )

    bundle_evidence_ids = _bundle_evidence_ids(bundle)
    report_evidence_ids = _report_evidence_ids(report)
    reviewed_evidence_ids = _reviewed_evidence_ids(reviewed)

    assert report.trace_id == query.trace_id
    assert report.contract_version == bundle.contract_version
    assert report.selected_root_cause.evidence_refs
    assert report.suggested_fix[0].evidence_refs
    assert report.migration_impact.evidence_refs
    assert report.evidence_chain
    assert report_evidence_ids.issubset(bundle_evidence_ids)
    assert reviewed.report_id == report.report_id
    assert reviewed.approved_findings
    assert reviewed.final_confidence == report.confidence
    assert reviewed_evidence_ids.issubset(bundle_evidence_ids)
    assert record.confirmed_by_user is True
    assert record.evidence_refs
```

Add helpers:

```python
def _bundle_evidence_ids(bundle) -> set[str]:
    refs = [
        *bundle.code_evidence,
        *bundle.sql_evidence,
        *bundle.config_evidence,
        *bundle.log_evidence,
    ]
    for incident in bundle.similar_incidents:
        refs.extend(incident.evidence_refs)
    return {ref.evidence_id for ref in refs}


def _report_evidence_ids(report) -> set[str]:
    refs = [
        *report.evidence_chain,
        *report.selected_root_cause.evidence_refs,
        *report.migration_impact.evidence_refs,
    ]
    for item in [*report.hypotheses, *report.suggested_fix]:
        refs.extend(item.evidence_refs)
    return {ref.evidence_id for ref in refs}


def _reviewed_evidence_ids(reviewed) -> set[str]:
    refs = []
    for item in reviewed.approved_findings:
        refs.extend(item.evidence_refs)
    return {ref.evidence_id for ref in refs}
```

- [ ] **Step 3: Update real E2E config tests**

Modify `tests/test_real_structure1_structure2_e2e_config.py` so `REQUIRED_ENV_KEYS` includes:

```python
"LEGACY_PILOT_RCA_BACKEND",
"LEGACY_PILOT_RCA_BASE_URL",
"LEGACY_PILOT_RCA_MODEL",
"LEGACY_PILOT_RCA_CONFIDENCE_CAP",
"DASHSCOPE_API_KEY",
```

The env example assertion must require:

```python
assert env_values["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
```

- [ ] **Step 4: Run real E2E**

Run only after PostgreSQL is running and Qwen credentials are configured:

```powershell
$env:LEGACY_PILOT_RUN_REAL_E2E='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
$env:LEGACY_PILOT_RCA_BACKEND='qwen_api'
$env:LEGACY_PILOT_RCA_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
$env:LEGACY_PILOT_RCA_MODEL='qwen-plus'
python -m pytest tests/test_real_structure1_structure2_e2e.py -q -s
```

Expected: PASS with real GitNexus CLI, PostgreSQL, Structure2 `graph_context`, and real Qwen API. If `LEGACY_PILOT_RUN_REAL_E2E=1` is set and any required real dependency is missing, the test must fail or error clearly; it must not pass through mock. If the opt-in gate is absent, the existing skip-reason contract may skip the real E2E.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_real_structure1_structure2_e2e.py tests/test_real_structure1_structure2_e2e_config.py
git commit -m "test: extend real e2e through structure3"
```

---

### Task 5: Update Runtime Config And Docs

**Files:**
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Modify: `docs/architecture/interface-contract-middleware-implementation.md`
- Modify: `docs/architecture/structure1-postgres-structure2-real-e2e-verification.md`

**Interfaces:**
- Produces: documented real-only Structure3 runtime path.

- [ ] **Step 1: Update `.env.example`**

Add:

```text
# Structure3 RCA Reasoning Engine. Real Qwen is the default; no default mock.
LEGACY_PILOT_RCA_BACKEND=qwen_api
LEGACY_PILOT_RCA_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
LEGACY_PILOT_RCA_MODEL=qwen-plus
LEGACY_PILOT_RCA_CONFIDENCE_CAP=0.75

# Required for Structure1 semantic enrichment and Structure3 RCA when Qwen is enabled.
DASHSCOPE_API_KEY=<secret>
```

- [ ] **Step 2: Update `pyproject.toml` marker**

Change the existing `real_structure1_structure2_e2e` marker description to include Structure3:

```toml
"real_structure1_structure2_e2e: requires real GitNexus CLI, PostgreSQL graph store, Structure2 graph_context, and Qwen Structure3 RCA; skipped unless explicitly enabled",
```

- [ ] **Step 3: Update architecture docs**

In `docs/architecture/interface-contract-middleware-implementation.md`, replace mock RCA wording with:

```text
GenerateRCA and ReviewRCA delegate to Structure3 `RCAReasoningEngineAdapter`.
The default Structure3 backend is `qwen_api`; missing Qwen configuration returns a `ContractError` from `source_module=rca_reasoning_engine`.
Structure3 consumes only `EvidenceBundle` and does not query Structure1, PostgreSQL, GitNexus, or repo files.
```

In `docs/architecture/structure1-postgres-structure2-real-e2e-verification.md`, add:

```text
Structure3 acceptance chain:

GitNexus real index_repo
-> Structure1 GraphSnapshot
-> PostgreSQL graph payload persistence
-> fresh Structure1 adapter restores payload from PostgreSQL
-> MiddlewareRouter.query_graph()
-> Structure2 graph_context backend
-> EvidenceBundle
-> MiddlewareRouter.generate_rca()
-> Structure3 Qwen RCAReport
-> MiddlewareRouter.review_rca()
-> ReviewedRCAReport evidence gate
```

- [ ] **Step 4: Commit**

Run:

```bash
git add .env.example pyproject.toml docs/architecture/interface-contract-middleware-implementation.md docs/architecture/structure1-postgres-structure2-real-e2e-verification.md
git commit -m "docs: require real structure3 middleware e2e"
```

---

## Final Verification

Run boundary/unit tests:

```bash
python -m pytest tests/test_structure3_boundary.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected: PASS after old Structure3 mock-default expectations are removed or revised.

Run real Structure3 middleware E2E:

```powershell
docker compose -f docker-compose.e2e.yml up -d postgres
$env:LEGACY_PILOT_RUN_REAL_E2E='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
$env:LEGACY_PILOT_RCA_BACKEND='qwen_api'
$env:GITNEXUS_BIN='<path-to-real-gitnexus-cli>'
$env:GITNEXUS_REPO_ROOT='<path-to-real-gitnexus-runtime-root>'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_GRAPH_STORE_TABLE='legacy_pilot_graph_payloads_structure3_e2e'
$env:LEGACY_PILOT_RCA_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
$env:LEGACY_PILOT_RCA_MODEL='qwen-plus'
# DASHSCOPE_API_KEY must already be set in the shell or secret manager.
python -m pytest tests/test_real_structure1_structure2_e2e.py -q -s
```

Expected: PASS only with real `GITNEXUS_BIN`, `GITNEXUS_REPO_ROOT`, PostgreSQL, and `DASHSCOPE_API_KEY` configured. Missing config must fail loudly, not skip or mock.

## Self-Review

- Spec coverage: Structure3 is real Qwen-backed, not default mock; test acceptance depends on real GitNexus CLI, PostgreSQL, and Qwen API; Structure3 is invoked through middleware and consumes only `EvidenceBundle`.
- Boundary coverage: AST import and runtime guard tests prevent Structure3 from importing or calling Structure1/Structure2/PostgreSQL/GitNexus/file/process internals; real E2E uses middleware entry points for `IndexRepo`, `SubmitAlert`, `BuildEvidenceBundle`, `GenerateRCA`, and `ReviewRCA`.
- Type consistency: uses existing `EvidenceBundle`, `RCAReport`, `ReviewedRCAReport`, `EvidenceBackedItem`, and `EvidenceRef` contracts.
- Residual risk: Qwen output may need JSON repair/retry after empirical failures, but first implementation must fail safely rather than inventing evidence or falling back to mock.
