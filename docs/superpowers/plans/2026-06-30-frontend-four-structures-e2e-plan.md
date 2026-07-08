# Frontend Four-Structure Workbench Plan

## Goal

做一个单页前端工作台，把四结构和 Interface Contract Middleware 串成可观察、可操作、可真实 E2E 验证的闭环。

闭环：

```text
UI
-> Middleware HTTP API
-> Structure1 GitNexus + PostgreSQL graph store
-> Structure2 graph_context
-> Structure3 real DashScope Qwen RCA
-> Structure4 PostgreSQL incident memory
-> UI result
```

前端只调用 Middleware HTTP API。前端不直连 GitNexus、PostgreSQL、DashScope Qwen，也不读取本地文件系统。

## Current Backend Facts

- Middleware FastAPI 已暴露 `/health` 和 `/v1/*` contract routes。
- Structure1 真实 `gitnexus_cli` 可 opt-in，支持 PostgreSQL graph payload persistence。
- Structure2 默认 `graph_context`，通过 middleware 内部 `QueryGraph` 消费 Structure1 `GraphContext`。
- Structure3 默认真实 `qwen_api`，RCA 输出必须 evidence-backed。
- Structure4 默认真实 `postgresql`，`SaveIncident` 保存用户确认后的 `IncidentRecord`。
- 最新真实 E2E 已覆盖 GitNexus、PostgreSQL、Structure2、real Qwen、Structure4 保存和读回。

## Product Shape

页面名：`Incident Workbench`

首屏即工作台，不做 landing page。

主布局：

- 左侧：输入和运行控制。
- 中间：四结构流水线状态。
- 右侧：RCA、evidence、incident memory 结果。
- 底部：contract/error/trace 调试抽屉。

视觉风格：

- 运维/诊断工具风格，密集但清楚。
- 不用营销 hero，不用装饰卡片堆叠。
- 用 tabs、segmented controls、icon buttons、status badges、compact panels。
- 所有长文本用 fixed-height scroll panel，避免撑坏布局。
- 关键状态用颜色加文本，不只靠颜色表达。

## Page Sections

### 1. Backend Status Bar

目的：确认 UI 正连 middleware，不误连 mock 或错误环境。

显示：

- API base URL。
- `/health` service。
- contract version。
- 当前 run mode：`real` 或 `unknown`。
- 最后一次 run trace_id。

行为：

- 页面加载调用 `GET /health`。
- health 失败时禁用 Run 按钮。
- contract version 不是 `1.x.x` 时显示 blocking error。

### 2. Repo Index Panel

对应 Structure1 `IndexRepo`。

输入：

- `repo_id`
- `repo_uri`
- `language_hint`
- `parser_profile`
- `contract_version`

默认示例：

- `language_hint=java`
- `parser_profile=spring-boot`
- `contract_version=1.0.0`

操作：

- `Index Repo`
- `Skip Index, Use Existing graph_id`

输出：

- `graph_id`
- node count
- edge count
- evidence count
- parser version
- semantic enrichment version

契约：

- `POST /v1/repos/index`
- request `RepoIndexRequest`
- response `GraphSnapshot`

UI 规则：

- `graph_id` 成功后自动填入 Alert panel。
- 不展示内部 PostgreSQL table 或 GitNexus raw payload。

### 3. Alert Input Panel

对应 Structure2 `SubmitAlert` 起点。

输入：

- `alert_id`
- `repo_id`
- optional `graph_id`
- `raw_log`
- optional `stack_trace`
- optional `error_description`
- `occurred_at`
- `source`
- `contract_version`

操作：

- `Submit Alert`

输出：

- `trace_id`
- `error_type`
- `suspected_location`
- `endpoint`
- `keywords`
- `query_terms`

契约：

- `POST /v1/alerts/submit`
- request `AlertEvent`
- response `IncidentQuery`

UI 规则：

- `trace_id` 成功后锁定并传给后续步骤。
- 用户可以手动编辑 `graph_id`，但 UI 要标明这是 contract 字段，不是 DB id。

### 4. Evidence Bundle Panel

对应 Structure2 `BuildEvidenceBundle`。

操作：

- `Build Evidence`

输出：

- alert summary
- matched nodes
- graph paths
- code evidence
- SQL evidence
- config evidence
- log evidence
- similar incidents
- missing evidence

契约：

- `POST /v1/evidence-bundles/build`
- request `IncidentQuery`
- response `EvidenceBundle`

UI 规则：

- evidence 按 `source_type` 分组。
- 每条 evidence 展示 `evidence_id`、file path、line range、confidence、excerpt。
- `missing_evidence` 非空时，在 RCA 生成前显示 warning，但不强制阻断。
- graph path 用紧凑路径视图，不画复杂图谱。

### 5. RCA Panel

对应 Structure3 `GenerateRCA` 和 `ReviewRCA`。

操作：

- `Generate RCA`
- `Review RCA`

输出：

- hypotheses
- selected root cause
- evidence chain
- affected path
- suggested fix
- migration impact
- migration checklist
- confidence
- open questions
- approved findings
- rejected findings
- risk notes

契约：

- `POST /v1/rca/generate`
- request `EvidenceBundle`
- response `RCAReport`
- `POST /v1/rca/review`
- request `RCAReport`
- response `ReviewedRCAReport`

UI 规则：

- RCA 结论旁必须显示 evidence count。
- 点击结论能展开对应 evidence_refs。
- `Review RCA` 成功前禁用 `Save Incident`。
- Qwen invalid JSON/repair retry 不暴露原始 secret，只显示 recoverable contract error 或 retry metadata。

### 6. Incident Save Panel

对应 Structure4 `SaveIncident`。

输入：

- `user_confirmation`
- `fix_outcome`
- `retention_policy`

操作：

- `Save Incident`

输出：

- `incident_id`
- `dedup_key`
- `confirmed_by_user`
- `created_at`
- `updated_at`
- evidence refs

契约：

- `POST /v1/incidents/save`
- request `SaveIncidentRequest`
- response `IncidentRecord`

UI 规则：

- `user_confirmation=false` 时不允许保存。
- 保存前展示 confirmation checkbox。
- 保存成功后显示 `IncidentRecord` 摘要和 raw contract JSON tab。
- 不显示 PostgreSQL DSN、table、API key。

### 7. Contract Debug Drawer

目的：让 hackathon demo 和 E2E 调试可审计。

内容：

- 每一步 request JSON。
- 每一步 response JSON。
- HTTP status。
- elapsed ms。
- `trace_id`。
- `ContractError` envelope。

错误展示：

- `error_code`
- `message`
- `source_module`
- `recoverable`
- `missing_fields`
- `evidence_refs`

UI 规则：

- 默认折叠。
- 错误时自动打开对应 step。
- JSON viewer 可复制，但不包含环境变量或 secret。

## Workflow States

Pipeline steps：

1. Health
2. IndexRepo
3. SubmitAlert
4. BuildEvidenceBundle
5. GenerateRCA
6. ReviewRCA
7. SaveIncident

每步状态：

- idle
- running
- passed
- failed
- skipped

按钮规则：

- Run full pipeline：按顺序执行全部可执行步骤。
- Run from here：从当前 step 继续。
- Retry failed step：只重跑失败 step，保留下游结果标记 stale。
- Reset run：清空当前 pipeline state。

数据规则：

- 上游 request 改动后，下游结果全部标记 stale。
- `trace_id` 必须在 SubmitAlert 后贯穿 EvidenceBundle、RCAReport、ReviewedRCAReport、IncidentRecord。
- `contract_version` 默认 `1.0.0`，用户可改，用于验证 unsupported version error。

## API Contract Mapping

| UI action | Endpoint | Request | Response | Structure owner |
| --- | --- | --- | --- | --- |
| Health | `GET /health` | none | service/version object | Middleware |
| Index Repo | `POST /v1/repos/index` | `RepoIndexRequest` | `GraphSnapshot` | Structure1 |
| Query Graph | `POST /v1/graph/query` | `GraphQuery` | `GraphContext` | Structure1 |
| Submit Alert | `POST /v1/alerts/submit` | `AlertEvent` | `IncidentQuery` | Structure2 |
| Build Evidence | `POST /v1/evidence-bundles/build` | `IncidentQuery` | `EvidenceBundle` | Structure2 |
| Similar Incidents | `POST /v1/incidents/similar` | `IncidentQuery` | `IncidentMatch[]` | Structure4 |
| Generate RCA | `POST /v1/rca/generate` | `EvidenceBundle` | `RCAReport` | Structure3 |
| Review RCA | `POST /v1/rca/review` | `RCAReport` | `ReviewedRCAReport` | Structure3 |
| Save Incident | `POST /v1/incidents/save` | `SaveIncidentRequest` | `IncidentRecord` | Structure4 |

Primary UI pipeline does not need direct `QueryGraph`; Structure2 `graph_context` calls it through middleware internals. Keep `Query Graph` as optional diagnostics tab only.

## Frontend Tech Plan

Recommended stack:

- Vite
- React
- TypeScript
- Playwright
- Existing lightweight CSS or Tailwind only if repo adopts it during implementation

Rationale:

- Fast local dev.
- Strong contract typing can mirror Pydantic response shapes.
- Playwright gives real browser E2E against real backend.

No frontend code in this planning task.

## Component Plan

Core components:

- `ApiStatusBar`
- `PipelineStepper`
- `RepoIndexForm`
- `AlertForm`
- `EvidenceBundleView`
- `RCAReportView`
- `ReviewedReportView`
- `IncidentSaveForm`
- `IncidentRecordView`
- `ContractDebugDrawer`
- `ContractErrorBanner`

State model:

- One pipeline run object.
- Step result objects contain request, response, status, started_at, finished_at, error.
- Derived selectors compute enabled actions and stale downstream steps.

## Playwright Real E2E Plan

Test target：真实 browser + 真实 middleware + 真实 PostgreSQL + real Qwen。

Required environment:

- Docker daemon running.
- PostgreSQL container from reusable E2E script.
- Middleware running with real env:
  - `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli`
  - `LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql`
  - `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context`
  - `LEGACY_PILOT_RCA_BACKEND=qwen_api`
  - `LEGACY_PILOT_INCIDENT_MEMORY_BACKEND=postgresql`
  - `DASHSCOPE_API_KEY`
- Frontend dev server running.

Happy-path Playwright test:

1. Open workbench.
2. Assert `/health` passed and contract version visible.
3. Fill repo fields using Java/Spring production fixture.
4. Click `Index Repo`.
5. Assert `graph_id`, node count, edge count, evidence count visible.
6. Fill alert log for `/api/dataset/version` NPE.
7. Click `Run full pipeline`.
8. Assert Structure2 evidence visible.
9. Assert Structure3 RCA root cause visible and evidence-backed.
10. Check user confirmation.
11. Save incident.
12. Assert `incident_id` visible.
13. Assert debug drawer shows same `trace_id` across steps.

Negative Playwright tests:

- Missing `contract_version` returns `VALIDATION_ERROR`.
- Unsupported `contract_version=2.0.0` returns `UNSUPPORTED_CONTRACT_VERSION`.
- Missing `trace_id` in diagnostic QueryGraph returns `TRACE_REQUIRED`.
- `user_confirmation=false` blocks save in UI.
- Backend down disables Run and shows health failure.

Real persistence assertion:

- Preferred: add test-only backend endpoint later for incident readback by `incident_id`, still through middleware.
- Until then: keep DB readback in backend real E2E pytest, and Playwright asserts `SaveIncident` response.
- Do not make browser connect directly to PostgreSQL.

## One-Command E2E Target

Future script goal:

```text
scripts/run-real-frontend-e2e.ps1
-> start Docker daemon
-> start PostgreSQL
-> load Qwen key from env/.env.local/User env
-> start middleware
-> start frontend dev server
-> run Playwright
-> stop child processes
```

This script should reuse `scripts/run-real-e2e.ps1` env defaults where possible.

## Acceptance Criteria

- Workbench can run real four-structure chain from UI.
- UI never requires users to paste Qwen key.
- UI never connects directly to PostgreSQL, GitNexus, or DashScope.
- Every displayed RCA conclusion has visible evidence references.
- Save Incident requires explicit user confirmation.
- Contract errors display exact `error_code`, `source_module`, and `message`.
- Playwright happy path passes against real backend.
- Negative contract tests pass in browser.
- No mock backend needed for acceptance path.
- Secret scan finds no `DASHSCOPE_API_KEY` value in committed files.

## Implementation Tasks

1. Add frontend app scaffold.
2. Add typed API client for middleware endpoints.
3. Build workbench layout and forms.
4. Build pipeline state machine.
5. Build evidence/RCA/incident result views.
6. Build contract debug drawer.
7. Add Playwright config.
8. Add real frontend E2E script.
9. Run visual checks desktop and mobile.
10. Run real Playwright E2E.

## Open Decisions

- Whether frontend lives under `frontend/` or `apps/web/`.
- Whether UI uses plain CSS modules, Tailwind, or existing repo design system if added.
- Whether backend should add read-only `GET /v1/incidents/{incident_id}` for Structure4 readback through contract.
- Whether `FindSimilarIncidents` should become part of primary flow before RCA or remain diagnostics until real retrieval is implemented.
