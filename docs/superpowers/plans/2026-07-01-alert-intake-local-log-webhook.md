# Alert Intake Local Log Webhook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Structure2 alert intake from local log files and real webhook sources while preserving the existing `AlertEvent -> SubmitAlert -> IncidentQuery` contract path.

**Architecture:** Manual form, local log import, and webhook payloads all normalize into `AlertEvent`. Webhook endpoints live at middleware edge and call the same `MiddlewareRouter.submit_alert()` method as `/v1/alerts/submit`. Frontend local import reads browser-selected files only; backend never reads a user's local filesystem path.

**Tech Stack:** FastAPI, Pydantic contract models, React/Vite/TypeScript, Playwright, pytest.

---

## File Map

- Create: `legacy_pilot/alert_intake/__init__.py`
  - Package boundary for alert intake code.
- Create: `legacy_pilot/alert_intake/normalizer.py`
  - Generic webhook JSON/text field extraction and `AlertEvent` construction.
- Modify: `legacy_pilot/middleware/app.py`
  - Add `POST /v1/alerts/webhook/generic` endpoint.
- Modify: `frontend/src/api.ts`
  - Add optional webhook secret header support.
- Modify: `frontend/src/App.tsx`
  - Add Structure2 input modes: manual, local log import, webhook.
- Modify: `frontend/src/contracts.ts`
  - Add TypeScript type for webhook API result only if endpoint response shape differs; otherwise keep `IncidentQuery`.
- Modify: `tests/test_api.py`
  - Add webhook API tests.
- Modify: `frontend/tests/real-four-structures.spec.ts`
  - Add local file import UI smoke test.
- Modify: `README.md`, `README.zh-CN.md`
  - Document local log import and webhook use.

---

### Task 1: Backend Generic Webhook Normalizer

**Files:**
- Create: `legacy_pilot/alert_intake/__init__.py`
- Create: `legacy_pilot/alert_intake/normalizer.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API test**

Add tests to `tests/test_api.py`:

```python
def test_generic_webhook_normalizes_payload_into_incident_query():
    client = TestClient(create_app())

    response = client.post(
        "/v1/alerts/webhook/generic",
        params={"repo_id": "repo-demo", "graph_id": "GRAPH-DEMO"},
        json={
            "id": "grafana-alert-1",
            "source": "grafana",
            "message": "java.lang.NullPointerException at DatasetService.getVersion(DatasetService.java:42)",
            "stack": "DatasetService.getVersion(DatasetService.java:42)",
            "title": "Dataset version endpoint failed",
            "timestamp": "2026-07-01T16:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["repo_id"] == "repo-demo"
    assert body["graph_id"] == "GRAPH-DEMO"
    assert body["trace_id"] == "TRACE-grafana-alert-1"
    assert body["error_type"] == "NullPointerException"
    assert "DatasetService.getVersion" in body["query_terms"]
```

Add auth test:

```python
def test_generic_webhook_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_WEBHOOK_SECRET", "expected-secret")
    client = TestClient(create_app())

    response = client.post(
        "/v1/alerts/webhook/generic",
        params={"repo_id": "repo-demo", "graph_id": "GRAPH-DEMO"},
        headers={"X-LegacyPilot-Webhook-Secret": "wrong-secret"},
        json={"message": "NullPointerException"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "AUTHENTICATION_ERROR"
    assert body["source_module"] == "alert_intake"
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```powershell
python -m pytest tests/test_api.py::test_generic_webhook_normalizes_payload_into_incident_query tests/test_api.py::test_generic_webhook_rejects_wrong_secret -q
```

Expected: fail because route does not exist.

- [ ] **Step 3: Implement normalizer**

Create `legacy_pilot/alert_intake/normalizer.py`:

```python
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import AlertEvent

MAX_WEBHOOK_TEXT_CHARS = 120_000


def normalize_generic_webhook_payload(
    payload: Mapping[str, Any],
    *,
    repo_id: str,
    graph_id: str | None,
    contract_version: str,
    now: datetime,
) -> AlertEvent:
    raw_log = _first_text(payload, "raw_log", "log", "message", "text", "body", "error")
    stack_trace = _first_text(payload, "stack_trace", "stack", "trace", "stacktrace")
    error_description = _first_text(payload, "error_description", "description", "title", "summary", "alertname")
    if not raw_log:
        raw_log = error_description or stack_trace
    if not raw_log:
        raise ContractViolation(
            ContractError(
                trace_id=None,
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Webhook payload must contain raw_log, log, message, text, body, error, title, description, stack, or stack_trace.",
                source_module="alert_intake",
                recoverable=True,
            )
        )
    raw_log = raw_log[:MAX_WEBHOOK_TEXT_CHARS]
    if stack_trace:
        stack_trace = stack_trace[:MAX_WEBHOOK_TEXT_CHARS]
    alert_id = _first_text(payload, "alert_id", "id", "event_id", "incident_id")
    if not alert_id:
        digest = sha256(f"{repo_id}:{graph_id or ''}:{raw_log}".encode("utf-8")).hexdigest()[:12]
        alert_id = f"webhook-{digest}"
    source = _first_text(payload, "source", "provider", "integration") or "generic-webhook"
    occurred_at = _parse_datetime(_first_text(payload, "occurred_at", "timestamp", "time", "startsAt"), now)
    return AlertEvent(
        alert_id=alert_id,
        repo_id=repo_id,
        graph_id=graph_id,
        raw_log=raw_log,
        stack_trace=stack_trace,
        error_description=error_description,
        occurred_at=occurred_at,
        source=source,
        contract_version=contract_version,
    )
```

- [ ] **Step 4: Implement route and auth**

Modify `legacy_pilot/middleware/app.py`:

```python
from typing import Any

from legacy_pilot.alert_intake.normalizer import normalize_generic_webhook_payload
from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
```

Add endpoint:

```python
    @app.post("/v1/alerts/webhook/generic", response_model=IncidentQuery)
    async def submit_generic_webhook(
        payload: dict[str, Any],
        repo_id: str,
        graph_id: str | None = None,
        contract_version: str = "1.0.0",
        webhook_secret: str | None = Header(default=None, alias="X-LegacyPilot-Webhook-Secret"),
    ) -> IncidentQuery:
        _ensure_webhook_secret(webhook_secret)
        alert = normalize_generic_webhook_payload(
            payload,
            repo_id=repo_id,
            graph_id=graph_id,
            contract_version=contract_version,
            now=middleware_router._now(),
        )
        return middleware_router.submit_alert(alert)
```

Add helper:

```python
def _ensure_webhook_secret(actual_secret: str | None) -> None:
    expected_secret = os.environ.get("LEGACY_PILOT_WEBHOOK_SECRET", "").strip()
    if expected_secret and actual_secret != expected_secret:
        raise ContractViolation(
            ContractError(
                trace_id=None,
                error_code=ErrorCode.AUTHENTICATION_ERROR,
                message="Webhook secret is missing or invalid.",
                source_module="alert_intake",
                recoverable=True,
            )
        )
```

- [ ] **Step 5: Run backend tests**

Run:

```powershell
python -m pytest tests/test_api.py::test_generic_webhook_normalizes_payload_into_incident_query tests/test_api.py::test_generic_webhook_rejects_wrong_secret -q
```

Expected: 2 passed.

---

### Task 2: Frontend Local Log Import

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests/real-four-structures.spec.ts`

- [ ] **Step 1: Add UI test**

Add Playwright step that uploads a generated log file to local import mode:

```ts
const logPath = testInfo.outputPath("sample-incident.log");
await fs.promises.writeFile(
  logPath,
  "java.lang.IllegalStateException: Failed to create BookController\nat BookController.list(BookController.java:31)\n",
  "utf8",
);
await page.getByRole("button", { name: "Import local log" }).click();
await page.setInputFiles('[data-testid="local-log-file-input"]', logPath);
await expect(page.getByTestId("raw-log-input")).toContainText("IllegalStateException");
await expect(page.getByTestId("alert-id-input")).toHaveValue(/sample-incident/);
```

- [ ] **Step 2: Run frontend test and verify fail**

Run:

```powershell
cd frontend
npx playwright test tests/real-four-structures.spec.ts --grep "local log"
```

Expected: fail because UI controls do not exist.

- [ ] **Step 3: Implement input mode state**

Modify `frontend/src/App.tsx`:

```ts
type AlertInputMode = "manual" | "local-log" | "webhook";
```

Add state:

```ts
const [alertInputMode, setAlertInputMode] = useState<AlertInputMode>("manual");
const [localLogImportStatus, setLocalLogImportStatus] = useState<string | null>(null);
```

- [ ] **Step 4: Implement file import handler**

Add function:

```ts
async function importLocalLogFiles(files: FileList | null) {
  if (!files || files.length === 0) {
    return;
  }
  const selected = Array.from(files)
    .filter((file) => file.name.toLowerCase().match(/\.(log|txt|json)$/))
    .slice(0, 5);
  if (selected.length === 0) {
    setLocalLogImportStatus("No .log, .txt, or .json files selected.");
    return;
  }
  const chunks = await Promise.all(
    selected.map(async (file) => `===== ${file.name} =====\n${await file.text()}`),
  );
  const first = selected[0];
  const importedText = chunks.join("\n\n").slice(0, 120_000);
  setAlertEvent((current) => ({
    ...current,
    alert_id: current.alert_id || `local-${first.name.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]+/g, "-")}`,
    raw_log: importedText,
    source: "local-log",
    occurred_at: new Date(first.lastModified || Date.now()).toISOString(),
  }));
  setLocalLogImportStatus(`Imported ${selected.length} file(s).`);
  clearPipelineAfter("index");
}
```

- [ ] **Step 5: Render local import controls**

In `AlertForm`, add mode buttons and controls:

```tsx
<div className="segmented-control" aria-label="Alert input mode">
  <button type="button" onClick={() => onModeChange("manual")}>Manual</button>
  <button type="button" onClick={() => onModeChange("local-log")}>Import local log</button>
  <button type="button" onClick={() => onModeChange("webhook")}>Webhook</button>
</div>
```

Local log panel:

```tsx
{mode === "local-log" && (
  <div className="inline-panel">
    <input
      data-testid="local-log-file-input"
      type="file"
      multiple
      accept=".log,.txt,.json,text/plain,application/json"
      onChange={(event) => onImportLocalLogs(event.target.files)}
    />
    <input
      data-testid="local-log-folder-input"
      type="file"
      multiple
      // @ts-expect-error Chromium directory picker attribute
      webkitdirectory=""
      onChange={(event) => onImportLocalLogs(event.target.files)}
    />
    {localLogImportStatus && <p className="field-help">{localLogImportStatus}</p>}
  </div>
)}
```

- [ ] **Step 6: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: pass.

---

### Task 3: Frontend Webhook Panel

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add API credential support**

Modify `RuntimeCredentials`:

```ts
export interface RuntimeCredentials {
  qwenApiKey?: string;
  githubToken?: string;
  gitlabToken?: string;
  webhookSecret?: string;
}
```

Set header:

```ts
if (credentials?.webhookSecret) {
  headers.set("X-LegacyPilot-Webhook-Secret", credentials.webhookSecret);
  hasHeaders = true;
}
```

- [ ] **Step 2: Add settings field**

Extend `WorkbenchSettings`:

```ts
type WorkbenchSettings = {
  qwenApiKey: string;
  githubToken: string;
  gitlabToken: string;
  webhookSecret: string;
};
```

Persist it in localStorage, same as other settings.

- [ ] **Step 3: Add webhook panel**

Render when mode is `webhook`:

```tsx
{mode === "webhook" && (
  <div className="inline-panel">
    <label>
      Webhook URL
      <input readOnly value={`${apiBase}/v1/alerts/webhook/generic?repo_id=${encodeURIComponent(value.repo_id)}&graph_id=${encodeURIComponent(value.graph_id || "")}`} />
    </label>
    <button type="button" onClick={onSendWebhookTest}>Send test webhook</button>
  </div>
)}
```

- [ ] **Step 4: Add test webhook sender**

Add function:

```ts
async function sendWebhookTest() {
  const payload = {
    id: alertEvent.alert_id || `webhook-test-${Date.now()}`,
    source: "frontend-webhook-test",
    message: alertEvent.raw_log || "java.lang.IllegalStateException: frontend webhook test",
    stack: alertEvent.stack_trace || "",
    title: alertEvent.error_description || "Frontend webhook test",
    timestamp: new Date().toISOString(),
  };
  const path = `/v1/alerts/webhook/generic?repo_id=${encodeURIComponent(alertEvent.repo_id)}&graph_id=${encodeURIComponent(alertEvent.graph_id || "")}&contract_version=${encodeURIComponent(alertEvent.contract_version)}`;
  const result = await postJson<IncidentQuery>(path, payload, apiOptions);
  setIncidentQuery(result.data);
}
```

Wrap through `runStep("submit", payload, ...)` so debug panel shows request/response under `SubmitAlert`.

- [ ] **Step 5: Build**

Run:

```powershell
cd frontend
npm run build
```

Expected: pass.

---

### Task 4: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Document local log import**

Add:

```markdown
Structure2 supports three alert input modes:

- Manual: paste `raw_log`, `stack_trace`, and description.
- Import local log: browser reads selected `.log`, `.txt`, or `.json` files and fills `AlertEvent.raw_log`.
- Webhook: external systems POST generic alert payloads to `/v1/alerts/webhook/generic`.
```

- [ ] **Step 2: Document webhook curl**

Add:

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/alerts/webhook/generic?repo_id=ibm-demo&graph_id=GRAPH-..." \
  -H "Content-Type: application/json" \
  -H "X-LegacyPilot-Webhook-Secret: dev-secret" \
  -d '{"id":"alert-1","source":"grafana","message":"NullPointerException at BookController.java:31","title":"Book API failed"}'
```

- [ ] **Step 3: Run full fast verification**

Run:

```powershell
python -m pytest tests/test_api.py -q
npm run build --prefix frontend
```

Expected: backend API tests pass, frontend build passes.

---

## Self-Review

- Spec coverage: manual input remains; local log import added to frontend; webhook added to backend and frontend; all paths normalize into `AlertEvent`.
- Contract safety: `SubmitAlert`, `IncidentQuery`, EvidenceBundle, RCA, and incident memory contracts stay unchanged.
- Security: webhook secret is enforced only when `LEGACY_PILOT_WEBHOOK_SECRET` exists, so local dev stays easy and production can lock endpoint.
- Scope: provider-specific webhook adapters like Sentry/Grafana/Alibaba SLS remain future work; generic webhook covers MVP.
