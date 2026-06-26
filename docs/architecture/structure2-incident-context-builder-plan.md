# 结构2 Incident Context Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把结构2从 `MiddlewareRouter` mock 中拆出，形成可替换的 Incident Context Builder，并用结构1 `QueryGraph` 组装真实 `EvidenceBundle`。

**Architecture:** `MiddlewareRouter` 继续做 contract gate、trace gate、error envelope。结构2新增独立 adapter 包，只负责 `SubmitAlert` 与 `BuildEvidenceBundle`；真实实现只能通过 `GraphQuery -> GraphContext` 使用结构1，不直连 GitNexus、不读 PostgreSQL graph store、不生成 RCA 结论。

**Tech Stack:** Python 3.13, Pydantic 2, FastAPI, pytest, existing LegacyPilot contracts.

---

## 当前基线

- 默认测试：`152 passed, 7 skipped`。
- 结构1已完成 Java/Spring/MyBatis 生产链路：GitNexus CLI、Structure1 enrichment、LocalGraphIndex、PostgreSQL graph store opt-in。
- 结构2当前还在 `legacy_pilot/middleware/router.py` 中：
  - `submit_alert()` 用字符串规则识别 `NullPointerException` 与 `DatasetService.getVersion`。
  - `build_evidence_bundle()` 返回固定 code/log evidence、固定 graph path、固定 similar incident。
- 结构2必须遵守现有接口契约：
  - `AlertEvent.contract_version` 必须校验。
  - `IncidentQuery.trace_id` 必须存在。
  - `EvidenceBundle.trace_id` 必须沿用 `IncidentQuery.trace_id`。
  - `EvidenceBundle.contract_version` 必须沿用 `IncidentQuery.contract_version`。
  - `EvidenceBundle` 只能组合证据，不输出最终根因。
  - 调用结构1只能走 `QueryGraph` contract。

## Scope

本计划实现结构2第一版真实接入：

- 抽出结构2 adapter 边界。
- 保留默认 mock 行为，保证现有 HTTP 和 router 测试不破。
- 新增可测试的日志/stack trace 解析器。
- 新增 graph-backed evidence bundle builder。
- 新增可选 `graph_id` 字段，解决结构2构造 `GraphQuery` 时的图版本定位。
- 新增 fixture 驱动验收，证明结构2可消费结构1 `GraphContext`。

本计划不做：

- 不实现结构3 RCA LLM 推理。
- 不实现结构4真实 incident memory DB。
- 不自动修复代码。
- 不允许结构2直接访问 GitNexus raw payload 或 PostgreSQL graph store。

## File Structure

- Modify: `legacy_pilot/contracts/models.py`
  - 给 `AlertEvent` 和 `IncidentQuery` 增加可选 `graph_id: str | None = None`。
- Create: `legacy_pilot/incident_context_builder/__init__.py`
  - 导出结构2 adapter、parser、builder。
- Create: `legacy_pilot/incident_context_builder/signals.py`
  - `IncidentSignals` 模型与 `parse_alert_event()`。
- Create: `legacy_pilot/incident_context_builder/adapter.py`
  - `IncidentContextBuilderAdapter` 抽象类、`MockIncidentContextBuilderAdapter`、`GraphBackedIncidentContextBuilderAdapter`、factory。
- Create: `legacy_pilot/incident_context_builder/evidence_builder.py`
  - `build_graph_query()`、`build_evidence_bundle_from_graph_context()`。
- Modify: `legacy_pilot/middleware/router.py`
  - 注入结构2 adapter；`submit_alert()`、`build_evidence_bundle()` 委托给 adapter。
- Modify: `tests/test_contract_models.py`
  - 覆盖可选 `graph_id` 兼容性。
- Create: `tests/test_incident_context_builder.py`
  - 覆盖 parser、mock adapter、graph-backed bundle builder。
- Modify: `tests/test_router_pipeline.py`
  - 覆盖 router 结构2注入、gate-before-adapter、默认 mock 不变。
- Modify: `tests/test_api.py`
  - 覆盖 HTTP body 中 `graph_id` 可选透传。
- Modify: `docs/architecture/interface-contract-middleware-implementation.md`
  - 记录结构2 adapter 接入和 `graph_id` 兼容策略。

## Contract Strategy

`GraphQuery` 必须带 `graph_id`，但当前 `AlertEvent` / `IncidentQuery` 无 `graph_id`。本计划采用兼容扩展：

```python
class AlertEvent(ContractModel):
    alert_id: str
    repo_id: str
    graph_id: str | None = None
    raw_log: str
    stack_trace: str | None = None
    error_description: str | None = None
    occurred_at: datetime
    source: str
    contract_version: str


class IncidentQuery(ContractModel):
    trace_id: str
    repo_id: str
    graph_id: str | None = None
    error_type: str
    suspected_location: str | None = None
    endpoint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    contract_version: str
```

Fallback rule:

```python
def graph_id_for_query(query: IncidentQuery) -> str:
    return query.graph_id or f"GRAPH-{query.repo_id}"
```

理由：

- 可选字段不破坏现有请求。
- 已有结构1默认 graph_id 形态是 `GRAPH-{repo_id}`。
- 前端或 CLI 拿到 `GraphSnapshot.graph_id` 后可显式传入，避免多图版本歧义。

---

### Task 1: Extend Contract With Optional graph_id

**Files:**
- Modify: `legacy_pilot/contracts/models.py`
- Test: `tests/test_contract_models.py`

- [ ] **Step 1: Write failing contract tests**

Add to `tests/test_contract_models.py`:

```python
from datetime import UTC, datetime

from legacy_pilot.contracts.models import AlertEvent, IncidentQuery


def test_alert_event_accepts_optional_graph_id():
    alert = AlertEvent(
        alert_id="ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        raw_log="java.lang.NullPointerException at DatasetService.getVersion",
        stack_trace="DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version",
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        source="demo-cli",
        contract_version="1.0.0",
    )

    assert alert.graph_id == "GRAPH-repo-demo"


def test_incident_query_accepts_missing_graph_id_for_compatibility():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    assert query.graph_id is None
```

- [ ] **Step 2: Run tests to verify fail**

Run:

```bash
python -m pytest tests/test_contract_models.py::test_alert_event_accepts_optional_graph_id tests/test_contract_models.py::test_incident_query_accepts_missing_graph_id_for_compatibility -q
```

Expected: FAIL with validation error for unknown or missing field behavior depending local Pydantic config.

- [ ] **Step 3: Modify models**

In `legacy_pilot/contracts/models.py`:

```python
class AlertEvent(ContractModel):
    alert_id: str
    repo_id: str
    graph_id: str | None = None
    raw_log: str
    stack_trace: str | None = None
    error_description: str | None = None
    occurred_at: datetime
    source: str
    contract_version: str


class IncidentQuery(ContractModel):
    trace_id: str
    repo_id: str
    graph_id: str | None = None
    error_type: str
    suspected_location: str | None = None
    endpoint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    contract_version: str
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/test_contract_models.py tests/test_api.py::test_submit_alert_endpoint_returns_incident_query -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add legacy_pilot/contracts/models.py tests/test_contract_models.py
git commit -m "feat: add optional incident graph id"
```

---

### Task 2: Add Incident Signal Parser

**Files:**
- Create: `legacy_pilot/incident_context_builder/__init__.py`
- Create: `legacy_pilot/incident_context_builder/signals.py`
- Test: `tests/test_incident_context_builder.py`

- [ ] **Step 1: Write parser tests**

Create `tests/test_incident_context_builder.py`:

```python
from datetime import UTC, datetime

from legacy_pilot.contracts.models import AlertEvent
from legacy_pilot.incident_context_builder.signals import parse_alert_event


def alert_event(**overrides):
    values = {
        "alert_id": "ALERT-001",
        "repo_id": "repo-demo",
        "graph_id": "GRAPH-repo-demo",
        "raw_log": (
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        "stack_trace": "at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
        "error_description": "NPE while reading dataset version via /api/dataset/version",
        "occurred_at": datetime(2026, 6, 24, tzinfo=UTC),
        "source": "demo-cli",
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return AlertEvent(**values)


def test_parse_alert_event_extracts_java_exception_location_and_endpoint():
    signals = parse_alert_event(alert_event())

    assert signals.error_type == "NullPointerException"
    assert signals.suspected_location == "DatasetService.getVersion"
    assert signals.file_path == "DatasetService.java"
    assert signals.line_number == 42
    assert signals.endpoint == "/api/dataset/version"
    assert signals.query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]


def test_parse_alert_event_extracts_slow_query_signal():
    signals = parse_alert_event(
        alert_event(
            raw_log="Slow query detected: select * from dataset_version where dataset_id = ?",
            stack_trace=None,
            error_description="Slow query on dataset_version",
        )
    )

    assert signals.error_type == "SlowQuery"
    assert "dataset_version" in signals.keywords
    assert "dataset_version" in signals.query_terms
```

- [ ] **Step 2: Run tests to verify fail**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py::test_parse_alert_event_extracts_java_exception_location_and_endpoint tests/test_incident_context_builder.py::test_parse_alert_event_extracts_slow_query_signal -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create parser module**

Create `legacy_pilot/incident_context_builder/signals.py`:

```python
import re

from pydantic import BaseModel, Field

from legacy_pilot.contracts.models import AlertEvent


JAVA_FRAME_RE = re.compile(
    r"(?P<class>[A-Za-z_$][\w$]*)\.(?P<method>[A-Za-z_$][\w$]*)"
    r"\((?P<file>[^():]+\.java):(?P<line>\d+)\)"
)
ENDPOINT_RE = re.compile(r"(?P<endpoint>/api/[A-Za-z0-9_./{}-]+)")
SQL_TABLE_RE = re.compile(
    r"\b(?:from|join|update|into)\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)


class IncidentSignals(BaseModel):
    error_type: str
    suspected_location: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    endpoint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)


def parse_alert_event(alert: AlertEvent) -> IncidentSignals:
    text = "\n".join(
        part
        for part in [
            alert.raw_log,
            alert.stack_trace or "",
            alert.error_description or "",
        ]
        if part
    )
    error_type = _detect_error_type(text)
    frame = JAVA_FRAME_RE.search(text)
    endpoint = _first_match(ENDPOINT_RE, text, "endpoint")
    table = _first_match(SQL_TABLE_RE, text, "table")
    suspected_location = None
    file_path = None
    line_number = None
    if frame:
        suspected_location = f"{frame.group('class')}.{frame.group('method')}"
        file_path = frame.group("file")
        line_number = int(frame.group("line"))
    keywords = _dedupe([value for value in [table] if value])
    query_terms = _dedupe(
        [
            error_type,
            suspected_location,
            endpoint,
            *keywords,
        ]
    )
    return IncidentSignals(
        error_type=error_type,
        suspected_location=suspected_location,
        file_path=file_path,
        line_number=line_number,
        endpoint=endpoint,
        keywords=keywords,
        query_terms=query_terms,
    )


def _detect_error_type(text: str) -> str:
    if "NullPointerException" in text:
        return "NullPointerException"
    if "Slow query" in text or "slow query" in text:
        return "SlowQuery"
    return "UnknownError"


def _first_match(pattern: re.Pattern[str], text: str, group_name: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(group_name)


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
```

Create `legacy_pilot/incident_context_builder/__init__.py`:

```python
from legacy_pilot.incident_context_builder.signals import (
    IncidentSignals,
    parse_alert_event,
)

__all__ = [
    "IncidentSignals",
    "parse_alert_event",
]
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add legacy_pilot/incident_context_builder tests/test_incident_context_builder.py
git commit -m "feat: parse incident context signals"
```

---

### Task 3: Extract Structure 2 Adapter and Preserve Mock Behavior

**Files:**
- Create: `legacy_pilot/incident_context_builder/adapter.py`
- Modify: `legacy_pilot/incident_context_builder/__init__.py`
- Modify: `legacy_pilot/middleware/router.py`
- Modify: `tests/test_router_pipeline.py`
- Test: `tests/test_incident_context_builder.py`

- [ ] **Step 1: Add adapter tests**

Append to `tests/test_incident_context_builder.py`:

```python
from legacy_pilot.incident_context_builder.adapter import (
    MockIncidentContextBuilderAdapter,
)


def test_mock_incident_context_adapter_preserves_submit_alert_behavior():
    adapter = MockIncidentContextBuilderAdapter()

    query = adapter.submit_alert(alert_event())

    assert query.trace_id == "TRACE-ALERT-001"
    assert query.repo_id == "repo-demo"
    assert query.graph_id == "GRAPH-repo-demo"
    assert query.error_type == "NullPointerException"
    assert query.suspected_location == "DatasetService.getVersion"
    assert query.endpoint == "/api/dataset/version"
    assert query.contract_version == "1.0.0"


def test_mock_incident_context_adapter_builds_evidence_bundle():
    adapter = MockIncidentContextBuilderAdapter()
    query = adapter.submit_alert(alert_event())

    bundle = adapter.build_evidence_bundle(query)

    assert bundle.trace_id == query.trace_id
    assert bundle.contract_version == query.contract_version
    assert bundle.code_evidence
    assert bundle.log_evidence
    assert bundle.similar_incidents[0].incident_id == "INC-003"
```

- [ ] **Step 2: Add router injection tests**

Append to `tests/test_router_pipeline.py`:

```python
from legacy_pilot.incident_context_builder.adapter import (
    IncidentContextBuilderAdapter,
    MockIncidentContextBuilderAdapter,
)


class RecordingIncidentContextAdapter(IncidentContextBuilderAdapter):
    def __init__(self):
        self.submit_called = False
        self.bundle_called = False

    def submit_alert(self, alert):
        self.submit_called = True
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=getattr(alert, "graph_id", None),
            error_type="InjectedError",
            suspected_location="Injected.location",
            query_terms=["InjectedError", "Injected.location"],
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query):
        self.bundle_called = True
        return EvidenceBundle(
            trace_id=query.trace_id,
            repo_id=query.repo_id,
            contract_version=query.contract_version,
            alert_summary="InjectedError near Injected.location",
            incident_query=query,
        )


def test_router_delegates_structure2_calls_to_incident_context_adapter():
    adapter = RecordingIncidentContextAdapter()
    router = MiddlewareRouter(incident_context_builder_adapter=adapter)

    query = router.submit_alert(alert_event())
    bundle = router.build_evidence_bundle(query)

    assert adapter.submit_called is True
    assert adapter.bundle_called is True
    assert query.error_type == "InjectedError"
    assert bundle.alert_summary == "InjectedError near Injected.location"


def test_default_router_uses_mock_incident_context_adapter():
    router = MiddlewareRouter()

    assert isinstance(
        router._incident_context_builder_adapter,
        MockIncidentContextBuilderAdapter,
    )
```

- [ ] **Step 3: Run tests to verify fail**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py tests/test_router_pipeline.py::test_router_delegates_structure2_calls_to_incident_context_adapter tests/test_router_pipeline.py::test_default_router_uses_mock_incident_context_adapter -q
```

Expected: FAIL because adapter module and router injection do not exist.

- [ ] **Step 4: Create adapter module**

Create `legacy_pilot/incident_context_builder/adapter.py`:

```python
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceBundle,
    EvidenceRef,
    IncidentMatch,
    IncidentQuery,
    Node,
)
from legacy_pilot.incident_context_builder.signals import parse_alert_event


class IncidentContextBuilderAdapter(ABC):
    @abstractmethod
    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        ...

    @abstractmethod
    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        ...


class MockIncidentContextBuilderAdapter(IncidentContextBuilderAdapter):
    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(UTC))

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        signals = parse_alert_event(alert)
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=alert.graph_id,
            error_type=signals.error_type,
            suspected_location=signals.suspected_location,
            endpoint=signals.endpoint,
            keywords=signals.keywords or signals.query_terms,
            query_terms=signals.query_terms,
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        code_evidence = self._evidence_ref(
            evidence_id="EV-CODE-001",
            trace_id=query.trace_id,
            source_type="code",
            source_id="DatasetService.java",
            file_path="src/main/java/DatasetService.java",
            start_line=40,
            end_line=45,
            excerpt="return datasetMapper.selectVersionById(req.getDatasetId());",
            extraction_method="java_parser",
            confidence=0.95,
        )
        log_evidence = self._evidence_ref(
            evidence_id="EV-LOG-001",
            trace_id=query.trace_id,
            source_type="log",
            source_id=query.trace_id,
            excerpt="NullPointerException at DatasetService.getVersion(DatasetService.java:42)",
            extraction_method="regex",
            confidence=0.88,
        )
        service_node = Node(
            node_id="NODE-DATASET-SERVICE-GET-VERSION",
            graph_id=query.graph_id or "GRAPH-DEMO",
            repo_id=query.repo_id,
            type="Method",
            name="getVersion",
            qualified_name="com.legacy.DatasetService.getVersion",
            evidence_refs=[code_evidence],
        )
        return EvidenceBundle(
            trace_id=query.trace_id,
            repo_id=query.repo_id,
            contract_version=query.contract_version,
            alert_summary=f"{query.error_type} near {query.suspected_location}",
            incident_query=query,
            matched_nodes=[service_node],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            code_evidence=[code_evidence],
            log_evidence=[log_evidence],
            similar_incidents=self.find_similar_incidents(query),
        )

    def find_similar_incidents(self, query: IncidentQuery) -> list[IncidentMatch]:
        evidence = self._evidence_ref(
            evidence_id="EV-INC-003",
            trace_id=query.trace_id,
            source_type="incident",
            source_id="INC-003",
            excerpt="Previous NPE caused by missing request validation for datasetId.",
            extraction_method="manual_confirm",
            confidence=0.9,
        )
        return [
            IncidentMatch(
                incident_id="INC-003",
                similarity=0.86,
                previous_root_cause="missing request validation for datasetId",
                previous_fix="add @NotNull and service-level null guard",
                related_files=[
                    "DatasetController.java",
                    "DatasetService.java",
                    "DatasetMapper.xml",
                ],
                evidence_refs=[evidence],
                confirmed_by_user=True,
            )
        ]

    def _evidence_ref(
        self,
        *,
        evidence_id: str,
        trace_id: str,
        source_type: str,
        source_id: str,
        extraction_method: str,
        confidence: float,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        excerpt: str | None = None,
    ) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=evidence_id,
            trace_id=trace_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            excerpt=excerpt,
            excerpt_hash=f"mock-{evidence_id.lower()}",
            extraction_method=extraction_method,
            confidence=confidence,
            created_at=self._now(),
        )


def create_incident_context_builder_adapter(
    *,
    backend: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> IncidentContextBuilderAdapter:
    selected_backend = backend or "mock"
    if selected_backend.strip().lower() == "mock":
        return MockIncidentContextBuilderAdapter(now=now)
    return MockIncidentContextBuilderAdapter(now=now)
```

Update `legacy_pilot/incident_context_builder/__init__.py`:

```python
from legacy_pilot.incident_context_builder.adapter import (
    IncidentContextBuilderAdapter,
    MockIncidentContextBuilderAdapter,
    create_incident_context_builder_adapter,
)
from legacy_pilot.incident_context_builder.signals import (
    IncidentSignals,
    parse_alert_event,
)

__all__ = [
    "IncidentContextBuilderAdapter",
    "IncidentSignals",
    "MockIncidentContextBuilderAdapter",
    "create_incident_context_builder_adapter",
    "parse_alert_event",
]
```

- [ ] **Step 5: Modify router**

In `legacy_pilot/middleware/router.py`, import:

```python
from legacy_pilot.incident_context_builder.adapter import (
    IncidentContextBuilderAdapter,
    create_incident_context_builder_adapter,
)
```

Change `MiddlewareRouter.__init__`:

```python
def __init__(
    self,
    now: Callable[[], datetime] | None = None,
    *,
    code_knowledge_core_adapter: CodeKnowledgeCoreAdapter | None = None,
    incident_context_builder_adapter: IncidentContextBuilderAdapter | None = None,
):
    self._now = now or (lambda: datetime.now(UTC))
    self._code_knowledge_core_adapter = (
        code_knowledge_core_adapter
        or create_code_knowledge_core_adapter(now=self._now)
    )
    self._incident_context_builder_adapter = (
        incident_context_builder_adapter
        or create_incident_context_builder_adapter(now=self._now)
    )
```

Replace `submit_alert()` body:

```python
def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
    ensure_supported_contract_version(alert.contract_version)
    return self._incident_context_builder_adapter.submit_alert(alert)
```

Replace `build_evidence_bundle()` body:

```python
def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
    ensure_trace_id(query.trace_id)
    ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
    return self._incident_context_builder_adapter.build_evidence_bundle(query)
```

Keep `find_similar_incidents()` in router for now. Structure4 not split yet.

- [ ] **Step 6: Run compatibility tests**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add legacy_pilot/incident_context_builder legacy_pilot/middleware/router.py tests/test_incident_context_builder.py tests/test_router_pipeline.py
git commit -m "feat: extract incident context builder adapter"
```

---

### Task 4: Add Graph Query and Evidence Bundle Builder

**Files:**
- Create: `legacy_pilot/incident_context_builder/evidence_builder.py`
- Modify: `legacy_pilot/incident_context_builder/__init__.py`
- Test: `tests/test_incident_context_builder.py`

- [ ] **Step 1: Write builder tests**

Append to `tests/test_incident_context_builder.py`:

```python
from legacy_pilot.contracts.models import (
    EvidenceRef,
    GraphContext,
    GraphQuery,
    Node,
)
from legacy_pilot.incident_context_builder.evidence_builder import (
    build_evidence_bundle_from_graph_context,
    build_graph_query,
    graph_id_for_query,
)


def evidence_ref(evidence_id, source_type="code", source_id="DatasetService.java"):
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-ALERT-001",
        source_type=source_type,
        source_id=source_id,
        file_path="src/main/java/DatasetService.java" if source_type == "code" else None,
        start_line=40 if source_type == "code" else None,
        end_line=45 if source_type == "code" else None,
        excerpt="evidence excerpt",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


def test_build_graph_query_uses_explicit_graph_id():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-explicit",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    graph_query = build_graph_query(query)

    assert graph_query == GraphQuery(
        repo_id="repo-demo",
        graph_id="GRAPH-explicit",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id="TRACE-ALERT-001",
        contract_version="1.0.0",
    )


def test_graph_id_for_query_falls_back_to_repo_graph():
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        error_type="NullPointerException",
        query_terms=["NullPointerException"],
        contract_version="1.0.0",
    )

    assert graph_id_for_query(query) == "GRAPH-repo-demo"


def test_build_evidence_bundle_from_graph_context_partitions_evidence():
    code = evidence_ref("EV-CODE-1", "code")
    sql = evidence_ref("EV-SQL-1", "sql", "SQL:selectVersionById")
    config = evidence_ref("EV-CONFIG-1", "config", "spring.datasource.url")
    graph_context = GraphContext(
        trace_id="TRACE-ALERT-001",
        matched_nodes=[
            Node(
                node_id="Method:DatasetService.getVersion",
                graph_id="GRAPH-repo-demo",
                repo_id="repo-demo",
                type="Method",
                name="DatasetService.getVersion",
                evidence_refs=[code],
            )
        ],
        matched_edges=[],
        graph_paths=[
            [
                "DatasetController.getVersion",
                "DatasetService.getVersion",
                "DatasetMapper.selectVersionById",
                "dataset_version",
            ]
        ],
        evidence_refs=[code, sql, config],
        confidence=0.88,
    )
    query = IncidentQuery(
        trace_id="TRACE-ALERT-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )

    bundle = build_evidence_bundle_from_graph_context(
        query=query,
        graph_context=graph_context,
        similar_incidents=[],
    )

    assert bundle.trace_id == "TRACE-ALERT-001"
    assert bundle.matched_nodes == graph_context.matched_nodes
    assert bundle.graph_paths == graph_context.graph_paths
    assert bundle.code_evidence == [code]
    assert bundle.sql_evidence == [sql]
    assert bundle.config_evidence == [config]
    assert bundle.missing_evidence == []
```

- [ ] **Step 2: Run tests to verify fail**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py::test_build_graph_query_uses_explicit_graph_id tests/test_incident_context_builder.py::test_graph_id_for_query_falls_back_to_repo_graph tests/test_incident_context_builder.py::test_build_evidence_bundle_from_graph_context_partitions_evidence -q
```

Expected: FAIL because `evidence_builder.py` missing.

- [ ] **Step 3: Create builder module**

Create `legacy_pilot/incident_context_builder/evidence_builder.py`:

```python
from legacy_pilot.contracts.models import (
    EvidenceBundle,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    IncidentMatch,
    IncidentQuery,
)


def graph_id_for_query(query: IncidentQuery) -> str:
    return query.graph_id or f"GRAPH-{query.repo_id}"


def build_graph_query(query: IncidentQuery) -> GraphQuery:
    return GraphQuery(
        repo_id=query.repo_id,
        graph_id=graph_id_for_query(query),
        query_terms=query.query_terms or [query.error_type],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id=query.trace_id,
        contract_version=query.contract_version,
    )


def build_evidence_bundle_from_graph_context(
    *,
    query: IncidentQuery,
    graph_context: GraphContext,
    similar_incidents: list[IncidentMatch],
) -> EvidenceBundle:
    code_evidence = _by_source_type(graph_context.evidence_refs, "code")
    sql_evidence = _by_source_type(graph_context.evidence_refs, "sql")
    config_evidence = _by_source_type(graph_context.evidence_refs, "config")
    log_evidence = _by_source_type(graph_context.evidence_refs, "log")
    missing_evidence = []
    if not graph_context.matched_nodes:
        missing_evidence.append("matched_nodes")
    if not graph_context.graph_paths:
        missing_evidence.append("graph_paths")
    if not graph_context.evidence_refs:
        missing_evidence.append("evidence_refs")
    return EvidenceBundle(
        trace_id=query.trace_id,
        repo_id=query.repo_id,
        contract_version=query.contract_version,
        alert_summary=_alert_summary(query),
        incident_query=query,
        matched_nodes=graph_context.matched_nodes,
        graph_paths=graph_context.graph_paths,
        code_evidence=code_evidence,
        sql_evidence=sql_evidence,
        config_evidence=config_evidence,
        log_evidence=log_evidence,
        similar_incidents=similar_incidents,
        missing_evidence=missing_evidence,
    )


def _alert_summary(query: IncidentQuery) -> str:
    if query.suspected_location:
        return f"{query.error_type} near {query.suspected_location}"
    return query.error_type


def _by_source_type(
    evidence_refs: list[EvidenceRef],
    source_type: str,
) -> list[EvidenceRef]:
    return [ref for ref in evidence_refs if ref.source_type == source_type]
```

Update `legacy_pilot/incident_context_builder/__init__.py`:

```python
from legacy_pilot.incident_context_builder.evidence_builder import (
    build_evidence_bundle_from_graph_context,
    build_graph_query,
    graph_id_for_query,
)
```

Add names to `__all__`.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add legacy_pilot/incident_context_builder/evidence_builder.py legacy_pilot/incident_context_builder/__init__.py tests/test_incident_context_builder.py
git commit -m "feat: build incident evidence bundle from graph context"
```

---

### Task 5: Add Graph-Backed Incident Context Adapter

**Files:**
- Modify: `legacy_pilot/incident_context_builder/adapter.py`
- Modify: `legacy_pilot/middleware/router.py`
- Test: `tests/test_incident_context_builder.py`
- Test: `tests/test_router_pipeline.py`

- [ ] **Step 1: Write graph-backed adapter test**

Append to `tests/test_incident_context_builder.py`:

```python
from legacy_pilot.incident_context_builder.adapter import (
    GraphBackedIncidentContextBuilderAdapter,
)


def test_graph_backed_adapter_queries_graph_and_builds_bundle():
    calls = []
    code = evidence_ref("EV-CODE-1", "code")

    def query_graph(graph_query):
        calls.append(graph_query)
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[
                Node(
                    node_id="Method:DatasetService.getVersion",
                    graph_id=graph_query.graph_id,
                    repo_id=graph_query.repo_id,
                    type="Method",
                    name="DatasetService.getVersion",
                    evidence_refs=[code],
                )
            ],
            matched_edges=[],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                ]
            ],
            evidence_refs=[code],
            confidence=0.88,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )
    query = adapter.submit_alert(alert_event())

    bundle = adapter.build_evidence_bundle(query)

    assert calls[0].graph_id == "GRAPH-repo-demo"
    assert calls[0].query_terms == [
        "NullPointerException",
        "DatasetService.getVersion",
        "/api/dataset/version",
    ]
    assert bundle.matched_nodes[0].name == "DatasetService.getVersion"
    assert bundle.code_evidence == [code]
```

- [ ] **Step 2: Write router env selection test**

Append to `tests/test_router_pipeline.py`:

```python
def test_router_selects_graph_backed_incident_context_adapter(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND", "graph_context")

    router = MiddlewareRouter()

    assert router._incident_context_builder_adapter.__class__.__name__ == (
        "GraphBackedIncidentContextBuilderAdapter"
    )
```

- [ ] **Step 3: Run tests to verify fail**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py::test_graph_backed_adapter_queries_graph_and_builds_bundle tests/test_router_pipeline.py::test_router_selects_graph_backed_incident_context_adapter -q
```

Expected: FAIL because graph-backed adapter and env selection missing.

- [ ] **Step 4: Implement graph-backed adapter**

In `legacy_pilot/incident_context_builder/adapter.py`, add imports:

```python
import os

from legacy_pilot.contracts.models import GraphContext, GraphQuery
from legacy_pilot.incident_context_builder.evidence_builder import (
    build_evidence_bundle_from_graph_context,
    build_graph_query,
)
```

Add class:

```python
class GraphBackedIncidentContextBuilderAdapter(IncidentContextBuilderAdapter):
    def __init__(
        self,
        *,
        query_graph: Callable[[GraphQuery], GraphContext],
        find_similar_incidents: Callable[[IncidentQuery], list[IncidentMatch]],
    ):
        self._query_graph = query_graph
        self._find_similar_incidents = find_similar_incidents

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        signals = parse_alert_event(alert)
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=alert.graph_id,
            error_type=signals.error_type,
            suspected_location=signals.suspected_location,
            endpoint=signals.endpoint,
            keywords=signals.keywords,
            query_terms=signals.query_terms,
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        graph_context = self._query_graph(build_graph_query(query))
        return build_evidence_bundle_from_graph_context(
            query=query,
            graph_context=graph_context,
            similar_incidents=self._find_similar_incidents(query),
        )
```

Replace factory:

```python
def create_incident_context_builder_adapter(
    *,
    backend: str | None = None,
    now: Callable[[], datetime] | None = None,
    query_graph: Callable[[GraphQuery], GraphContext] | None = None,
    find_similar_incidents: Callable[[IncidentQuery], list[IncidentMatch]] | None = None,
) -> IncidentContextBuilderAdapter:
    selected_backend = (
        backend
        or os.getenv("LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND")
        or "mock"
    )
    normalized = selected_backend.strip().lower()
    if normalized == "mock":
        return MockIncidentContextBuilderAdapter(now=now)
    if normalized == "graph_context":
        if query_graph is None or find_similar_incidents is None:
            raise ValueError(
                "graph_context incident context backend requires query_graph and find_similar_incidents"
            )
        return GraphBackedIncidentContextBuilderAdapter(
            query_graph=query_graph,
            find_similar_incidents=find_similar_incidents,
        )
    return MockIncidentContextBuilderAdapter(now=now)
```

Update `__all__` to export `GraphBackedIncidentContextBuilderAdapter`.

- [ ] **Step 5: Modify router factory call**

In `legacy_pilot/middleware/router.py`, set structure2 adapter after code adapter:

```python
self._incident_context_builder_adapter = (
    incident_context_builder_adapter
    or create_incident_context_builder_adapter(
        now=self._now,
        query_graph=lambda graph_query: self.query_graph(graph_query),
        find_similar_incidents=lambda incident_query: self.find_similar_incidents(
            incident_query
        ),
    )
)
```

- [ ] **Step 6: Run tests**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add legacy_pilot/incident_context_builder legacy_pilot/middleware/router.py tests/test_incident_context_builder.py tests/test_router_pipeline.py
git commit -m "feat: add graph backed incident context builder"
```

---

### Task 6: Add Structure 2 Production Fixture Flow

**Files:**
- Create: `tests/test_structure2_incident_context_fixture.py`
- Test fixture: `tests/fixtures/java_spring_production_demo`

- [ ] **Step 1: Write fixture test with fake graph context**

Create `tests/test_structure2_incident_context_fixture.py`:

```python
from datetime import UTC, datetime

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceRef,
    GraphContext,
    Node,
)
from legacy_pilot.incident_context_builder.adapter import (
    GraphBackedIncidentContextBuilderAdapter,
)


def evidence_ref(evidence_id, source_type, source_id, file_path=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-ALERT-PROD-001",
        source_type=source_type,
        source_id=source_id,
        file_path=file_path,
        start_line=40 if file_path else None,
        end_line=45 if file_path else None,
        excerpt="fixture evidence",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


def test_structure2_builds_evidence_bundle_from_java_production_context():
    code = evidence_ref(
        "EV-CODE-DATASET-SERVICE",
        "code",
        "DatasetService.java",
        "src/main/java/com/legacy/DatasetService.java",
    )
    sql = evidence_ref("EV-SQL-DATASET-VERSION", "sql", "SQL:selectVersionById")
    config = evidence_ref("EV-CONFIG-DATASOURCE", "config", "spring.datasource.url")
    graph_queries = []

    def query_graph(graph_query):
        graph_queries.append(graph_query)
        return GraphContext(
            trace_id=graph_query.trace_id,
            matched_nodes=[
                Node(
                    node_id="Method:DatasetService.getVersion",
                    graph_id=graph_query.graph_id,
                    repo_id=graph_query.repo_id,
                    type="Method",
                    name="DatasetService.getVersion",
                    evidence_refs=[code],
                )
            ],
            matched_edges=[],
            graph_paths=[
                [
                    "DatasetController.getVersion",
                    "DatasetService.getVersion",
                    "DatasetMapper.selectVersionById",
                    "dataset_version",
                ]
            ],
            evidence_refs=[code, sql, config],
            confidence=0.88,
        )

    adapter = GraphBackedIncidentContextBuilderAdapter(
        query_graph=query_graph,
        find_similar_incidents=lambda query: [],
    )
    alert = AlertEvent(
        alert_id="ALERT-PROD-001",
        repo_id="repo-prod",
        graph_id="GRAPH-repo-prod",
        raw_log=(
            "java.lang.NullPointerException: Cannot invoke getDatasetId "
            "at DatasetService.getVersion(DatasetService.java:42)"
        ),
        stack_trace="at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
        error_description="NPE while reading dataset version via /api/dataset/version",
        occurred_at=datetime(2026, 6, 24, tzinfo=UTC),
        source="fixture",
        contract_version="1.0.0",
    )

    query = adapter.submit_alert(alert)
    bundle = adapter.build_evidence_bundle(query)

    assert graph_queries[0].repo_id == "repo-prod"
    assert graph_queries[0].graph_id == "GRAPH-repo-prod"
    assert graph_queries[0].trace_id == "TRACE-ALERT-PROD-001"
    assert "DatasetService.getVersion" in graph_queries[0].query_terms
    assert bundle.trace_id == query.trace_id
    assert bundle.contract_version == "1.0.0"
    assert bundle.code_evidence == [code]
    assert bundle.sql_evidence == [sql]
    assert bundle.config_evidence == [config]
    assert bundle.graph_paths == [
        [
            "DatasetController.getVersion",
            "DatasetService.getVersion",
            "DatasetMapper.selectVersionById",
            "dataset_version",
        ]
    ]
```

- [ ] **Step 2: Run fixture test**

Run:

```bash
python -m pytest tests/test_structure2_incident_context_fixture.py -q
```

Expected: PASS.

- [ ] **Step 3: Run structure2 and middleware suite**

Run:

```bash
python -m pytest tests/test_incident_context_builder.py tests/test_structure2_incident_context_fixture.py tests/test_router_pipeline.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_structure2_incident_context_fixture.py
git commit -m "test: add structure2 incident context fixture"
```

---

### Task 7: Document Structure 2 Boundary and Backend Switch

**Files:**
- Modify: `docs/architecture/interface-contract-middleware-implementation.md`
- Modify: `docs/architecture/legacy-pilot-four-structures.md`
- Modify: `README.md`

- [ ] **Step 1: Update architecture docs**

Add to `docs/architecture/interface-contract-middleware-implementation.md` under Incident Context Builder:

````markdown
真实接入点：

```text
SubmitAlert
-> MiddlewareRouter.submit_alert()
-> IncidentContextBuilderAdapter.submit_alert()
-> IncidentQuery

BuildEvidenceBundle
-> MiddlewareRouter.build_evidence_bundle()
-> IncidentContextBuilderAdapter.build_evidence_bundle()
-> GraphQuery via MiddlewareRouter.query_graph()
-> GraphContext
-> EvidenceBundle
```

结构2 backend:

```text
LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=mock | graph_context
```

边界：

- `mock` 保留 deterministic demo 行为。
- `graph_context` 调用结构1 `QueryGraph`，只消费 `GraphContext`。
- 结构2不直连 PostgreSQL graph store。
- 结构2不读取 GitNexus raw payload。
- 结构2不生成 RCA 结论。
- `AlertEvent.graph_id` 与 `IncidentQuery.graph_id` 为可选字段；缺省时使用 `GRAPH-{repo_id}`。
```
````

Add to `docs/architecture/legacy-pilot-four-structures.md` Structure 2:

```markdown
当前实现计划：

- 结构2拥有独立 `IncidentContextBuilderAdapter`。
- `SubmitAlert` 解析 raw log、stack trace、error_description，输出 `IncidentQuery`。
- `BuildEvidenceBundle` 通过 `GraphQuery` 请求结构1，消费 `GraphContext` 并组装 `EvidenceBundle`。
- graph version 由可选 `graph_id` 控制；缺省时回退 `GRAPH-{repo_id}`。
```

- [ ] **Step 2: Update README controls**

Add to `README.md`:

````markdown
### Structure 2 Incident Context Builder

Default backend:

```powershell
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='mock'
```

Graph-backed backend:

```powershell
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
```

`graph_context` backend calls `/v1/graph/query` through middleware internals and builds
`EvidenceBundle` from `GraphContext`. It never connects to Structure 1 PostgreSQL graph
store directly.
```
````

- [ ] **Step 3: Run docs-adjacent tests**

Run:

```bash
python -m pytest tests/test_api.py tests/test_router_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/architecture/interface-contract-middleware-implementation.md docs/architecture/legacy-pilot-four-structures.md
git commit -m "docs: describe structure2 incident context backend"
```

---

### Task 8: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run default suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS with opt-in GitNexus, Qwen, PostgreSQL tests skipped unless env enabled.

- [ ] **Step 2: Run graph-backed smoke test**

Run:

```bash
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
python -m pytest tests/test_api.py::test_http_pipeline_builds_reviews_and_saves_incident tests/test_router_pipeline.py::test_mock_pipeline_produces_evidence_backed_rca_and_incident_record -q
```

Expected: PASS. If default mock structure1 cannot satisfy graph-backed bundle, keep this smoke test in fixture scope and document that graph-backed backend requires indexed graph availability.

- [ ] **Step 3: Inspect diff**

Run:

```bash
git diff --stat
git diff -- legacy_pilot/contracts/models.py legacy_pilot/middleware/router.py legacy_pilot/incident_context_builder tests
```

Expected: Diff limited to structure2 adapter, optional graph_id contract extension, tests, docs.

- [ ] **Step 4: Commit final verification note if docs changed**

```bash
git add docs/architecture/structure2-incident-context-builder-plan.md
git commit -m "docs: add structure2 implementation plan"
```

---

## Self-Review

Spec coverage:

- 结构2 adapter 边界：Task 3。
- 保留默认 mock：Task 3 tests。
- `graph_id` 问题：Task 1 + Contract Strategy。
- 通过 `QueryGraph` 消费结构1：Task 4 + Task 5。
- 不直连 GitNexus / PostgreSQL：Scope + Task 7 docs。
- EvidenceBundle 继承 trace/version：Task 3、Task 4、Task 6 tests。
- 不生成 RCA：Scope 明确，结构2输出停在 `EvidenceBundle`。

Placeholder scan:

- 占位词扫描通过。
- 无未定义函数名；计划内首次出现的函数都在同任务或前置任务定义。

Type consistency:

- `AlertEvent.graph_id`、`IncidentQuery.graph_id` 均为 `str | None`。
- `build_graph_query(query: IncidentQuery) -> GraphQuery`。
- `build_evidence_bundle_from_graph_context(...) -> EvidenceBundle`。
- `GraphBackedIncidentContextBuilderAdapter` 只依赖 `GraphQuery -> GraphContext` callable 和 `IncidentQuery -> list[IncidentMatch]` callable。

Execution handoff:

计划已保存到 `docs/architecture/structure2-incident-context-builder-plan.md`。

推荐执行顺序：

1. Task 1-3：先抽边界，保持现有行为。
2. Task 4-5：接结构1 `GraphContext`。
3. Task 6-7：加 fixture 和文档。
4. Task 8：跑默认 suite。
