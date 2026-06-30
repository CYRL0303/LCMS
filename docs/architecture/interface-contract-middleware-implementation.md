# LegacyPilot Interface Contract Middleware 实现说明

## 1. 当前实现目标

本轮实现的是 LegacyPilot 的第一版 Interface Contract Middleware。

它不是业务大脑，也不做真实代码解析、真实根因推理或真实历史记忆存储。当前中间件负责：

- 固定跨结构数据契约。
- 用 Pydantic 做 schema validation。
- 统一 trace_id、contract_version、confidence、evidence_refs 的校验约束。
- 用统一 ContractError envelope 返回中间件错误。
- 暴露 FastAPI HTTP 接口。
- 用 mock router 跑通首版闭环。

首版闭环为：

```text
SubmitAlert
-> BuildEvidenceBundle
-> GenerateRCA
-> ReviewRCA
-> SaveIncident
```

## 2. 代码结构

```text
legacy_pilot/
  contracts/
    enums.py        # source_type、extraction_method、error_code 等枚举
    errors.py       # ContractError 和 ContractViolation
    models.py       # 所有跨结构请求、响应和共享数据对象
    validators.py   # contract_version gate
  middleware/
    app.py          # FastAPI app、HTTP 路由、异常处理器
    router.py       # mock middleware router 和首版闭环
  code_knowledge_core/
    adapter.py       # Structure 1 adapter 边界，负责 IndexRepo / QueryGraph
    graph_store.py   # PostgreSQL-backed graph persistence 层，默认 disabled
```

测试覆盖在：

```text
tests/
  test_contract_models.py   # contract/schema gate
  test_router_pipeline.py   # mock router pipeline
  test_api.py               # FastAPI HTTP boundary
```

## 3. 请求处理流程

HTTP 请求进入中间件后，流程如下：

```text
Client
-> FastAPI route
-> Pydantic request model validation
-> MiddlewareRouter
-> contract_version gate
-> mock structure handler
-> Pydantic response model serialization
-> Client
```

如果请求体缺字段或字段类型不合法，FastAPI 的 `RequestValidationError` 会被转换成统一错误格式：

```json
{
  "trace_id": null,
  "error_code": "VALIDATION_ERROR",
  "message": "Request body failed contract validation.",
  "source_module": "interface_contract_middleware",
  "recoverable": true,
  "missing_fields": ["contract_version"],
  "evidence_refs": []
}
```

如果中间件业务 gate 拦截，例如 contract_version 不支持、RCA 缺证据、用户未确认保存 incident，则抛出 `ContractViolation`，并返回 `ContractError`。

## 4. 当前 HTTP 接口

### 4.1 Health

```text
GET /health
```

返回当前服务身份和支持的 contract version。

### 4.2 IndexRepo

```text
POST /v1/repos/index
Request: RepoIndexRequest
Response: GraphSnapshot
Owner: Code Knowledge Core
```

当前是 mock 实现，用固定 Java/Spring Boot demo 节点和边生成 `GraphSnapshot`。

### 4.3 QueryGraph

```text
POST /v1/graph/query
Request: GraphQuery
Response: GraphContext
Owner: Code Knowledge Core
```

当前是 mock 实现，用固定 Java/Spring Boot demo 路径返回 `matched_nodes`、`matched_edges`、`graph_paths`、`evidence_refs` 和 `confidence`。

### 4.4 SubmitAlert

```text
POST /v1/alerts/submit
Request: AlertEvent
Response: IncidentQuery
Owner: Incident Context Builder
```

当前会从 mock NPE 日志中识别：

- `error_type = NullPointerException`
- `suspected_location = DatasetService.getVersion`
- `trace_id = TRACE-{alert_id}`

### 4.5 BuildEvidenceBundle

```text
POST /v1/evidence-bundles/build
Request: IncidentQuery
Response: EvidenceBundle
Owner: Incident Context Builder
```

当前返回 mock code evidence、log evidence、graph path 和 similar incident。

### 4.6 FindSimilarIncidents

```text
POST /v1/incidents/similar
Request: IncidentQuery
Response: IncidentMatch[]
Owner: Incident Memory & Report Store
```

当前固定返回 `INC-003`，用于证明 incident memory 的契约形态。

### 4.7 GenerateRCA

```text
POST /v1/rca/generate
Request: EvidenceBundle
Response: RCAReport
Owner: RCA Reasoning Engine
```

当前根据 EvidenceBundle 中的 mock evidence 生成 RCA 草稿。这里仍然是 mock，不调用 LLM。

### 4.8 ReviewRCA

```text
POST /v1/rca/review
Request: RCAReport
Response: ReviewedRCAReport
Owner: RCA Reasoning Engine
```

当前会检查：

- selected_root_cause 必须有 evidence_refs。
- suggested_fix 每一项必须有 evidence_refs。
- migration_impact 必须有 evidence_refs。

缺失证据时返回：

```json
{
  "error_code": "EVIDENCE_REQUIRED",
  "recoverable": true
}
```

### 4.9 SaveIncident

```text
POST /v1/incidents/save
Request: SaveIncidentRequest
Response: IncidentRecord
Owner: Incident Memory & Report Store
```

当前要求：

- `user_confirmation = true`
- `contract_version` 支持当前 major version
- approved findings 中可以收集到 evidence_refs

否则不会保存为结构化 incident memory。

## 5. 中间件给四个结构留下的统一约束

### 5.1 所有跨结构请求必须带 contract_version

当前支持：

```text
1.x.x
```

当前策略：

- 缺失版本：拒绝，返回 `MISSING_CONTRACT_VERSION`。
- major version 不等于 1：拒绝，返回 `UNSUPPORTED_CONTRACT_VERSION`。
- 1.x.x：接受。

当前跨结构请求对象中，`AlertEvent`、`GraphQuery`、`IncidentQuery`、`EvidenceBundle`、`RCAReport` 和 `SaveIncidentRequest` 都携带 `contract_version`。其中 `EvidenceBundle` 作为 GenerateRCA 的请求，`RCAReport` 作为 ReviewRCA 的请求，都会在 router 边界再次执行版本校验。

### 5.2 所有运行时对象必须串 trace_id

以下对象必须带 trace_id：

```text
GraphQuery
GraphContext
IncidentQuery
EvidenceBundle
RCAReport
ReviewedRCAReport
IncidentRecord
```

当前 SubmitAlert 入口会生成：

```text
TRACE-{alert_id}
```

后续 EvidenceBundle、RCAReport、ReviewedRCAReport、IncidentRecord 都沿用同一个 trace_id。

如果 HTTP 请求缺少 `trace_id`，中间件返回 `TRACE_REQUIRED`，而不是普通 `VALIDATION_ERROR`。

### 5.3 confidence 必须在合法范围内

所有 confidence 字段由 Pydantic 限定：

```text
0.0 <= confidence <= 1.0
```

### 5.4 关键结论必须有 evidence_refs

当前强制要求 evidence_refs 的对象包括：

```text
Edge
EvidenceBackedItem
RCAReport.hypotheses[]
RCAReport.selected_root_cause
RCAReport.suggested_fix[]
RCAReport.migration_impact
RCAReport.evidence_chain[]
IncidentRecord
```

这意味着 RCA Reasoning Engine 不能输出无证据根因，Incident Memory & Report Store 不能保存无证据结论。

### 5.5 LLM 语义增强必须显式标注来源和状态

`LLMSemanticResult` 约束：

```text
evidence_span
source_location
prompt_version
confidence
extraction_method = llm
verification_status = pending | verified | rejected
```

默认：

```text
verification_status = pending
```

这给 Semantic Graph 和 RCA Engine 留出空间，但禁止把 LLM 结果当成无需审查的结构事实。

### 5.6 所有错误必须使用 ContractError envelope

统一错误对象：

```text
ContractError
- trace_id
- error_code
- message
- source_module
- recoverable
- missing_fields[]
- evidence_refs[]
```

四个结构未来接入时，不应该直接把内部异常透传给前端。

## 6. 四个结构的接口边界

### 6.1 Code Knowledge Core

Code Knowledge Core 负责 repo 结构、图谱和证据来源，不负责 RCA。

已实现的中间件接口：

```text
IndexRepo
Request: RepoIndexRequest
Response: GraphSnapshot
HTTP: POST /v1/repos/index
```

```text
QueryGraph
Request: GraphQuery
Response: GraphContext
HTTP: POST /v1/graph/query
```

Code Knowledge Core 必须输出：

- Node。
- Edge。
- GraphSnapshot。
- GraphContext。
- EvidenceRef。

关键约束：

- Edge 必须至少有一个 evidence_ref。
- parser/tree-sitter/JavaParser 产生的结构事实应使用高 confidence。
- LLM 产生的语义边必须走 `LLMSemanticResult` 或等价字段，保留 evidence span、prompt_version、confidence 和 verification_status。
- Structure 1 可以使用 PostgreSQL 持久化 mapper-ready graph payload，但 PostgreSQL 表结构不得成为跨结构 contract。
- Incident Context Builder、RCA Reasoning Engine 和 Incident Memory & Report Store 不能直接连接 PostgreSQL graph store；它们只能通过 `QueryGraph` 获得 `GraphContext`。

已实现的 PostgreSQL-backed graph persistence 边界：

```text
IndexRepo
-> MiddlewareRouter.index_repo()
-> CodeKnowledgeCoreAdapter.index_repo()
-> GitNexus CLI payload normalization
-> Structure 1 enrichment
-> GraphStore.save_payload(repo_id, graph_id, payload)
-> GraphSnapshot
```

```text
QueryGraph
-> MiddlewareRouter.query_graph()
-> CodeKnowledgeCoreAdapter.query_graph()
-> in-memory LocalGraphIndex
-> GraphStore.load_payload(repo_id, graph_id) only when a locally queryable plan has no process-local index
-> LocalGraphIndex rebuilt from persisted payload
-> GraphContext
```

当前持久化只承诺保存 latest enriched graph payload 并支持重建查询索引，不承诺 graph 历史版本、节点级 SQL 查询接口或跨结构数据库直连。

### 6.2 Incident Context Builder

Incident Context Builder 负责把报警、日志、stack trace 转换为可推理上下文，不负责最终根因判断。

已实现接口：

```text
SubmitAlert
Request: AlertEvent
Response: IncidentQuery
HTTP: POST /v1/alerts/submit
```

```text
BuildEvidenceBundle
Request: IncidentQuery
Response: EvidenceBundle
HTTP: POST /v1/evidence-bundles/build
```

关键约束：

- AlertEvent 必须带 contract_version。
- IncidentQuery 必须带 trace_id。
- EvidenceBundle 必须沿用 IncidentQuery.contract_version。
- EvidenceBundle 必须沿用 IncidentQuery.trace_id。
- EvidenceBundle 只能组合证据，不应直接输出最终根因。
- 调用图谱和历史故障时必须通过中间件契约，不直接读其他结构内部对象。

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

结构2 backend：

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

### 6.3 RCA Reasoning Engine

RCA Reasoning Engine 负责基于 EvidenceBundle 输出根因分析和审查结果，不直接读 repo，不直接写 incident memory。

已实现接口：

```text
GenerateRCA
Request: EvidenceBundle
Response: RCAReport
HTTP: POST /v1/rca/generate
```

```text
ReviewRCA
Request: RCAReport
Response: ReviewedRCAReport
HTTP: POST /v1/rca/review
```

关键约束：

- RCAReport 必须沿用 EvidenceBundle.trace_id。
- RCAReport 必须沿用 EvidenceBundle.contract_version。
- hypotheses、selected_root_cause、suggested_fix、migration_impact 都必须能追溯到 evidence_refs。
- confidence 必须在 0 到 1。
- Reviewer 阶段要拒绝缺证据的强结论。
- RCA Engine 不能绕过 EvidenceBundle 直接读取 repo。

### 6.4 Incident Memory & Report Store

Incident Memory & Report Store 负责保存和召回结构化故障记忆，不负责实时 RCA 判断。

已实现接口：

```text
FindSimilarIncidents
Request: IncidentQuery
Response: IncidentMatch[]
HTTP: POST /v1/incidents/similar
```

```text
SaveIncident
Request: SaveIncidentRequest
Response: IncidentRecord
HTTP: POST /v1/incidents/save
```

关键约束：

- IncidentMatch 必须标记 confirmed_by_user。
- SaveIncidentRequest 必须带 contract_version。
- 只有 user_confirmation=true 才能保存 IncidentRecord。
- IncidentRecord 必须有 evidence_refs。
- IncidentRecord 应保留 dedup_key、fix_outcome、retention_policy、created_at、updated_at。

## 7. 当前 mock 与真实接入点

当前 `MiddlewareRouter` 中的实现都是 deterministic mock：

- `index_repo()` 返回固定 GraphSnapshot。
- `query_graph()` 返回固定 GraphContext，包括 demo 节点、边、调用路径和证据。
- `submit_alert()` 用简单字符串规则识别 NPE。
- `build_evidence_bundle()` 返回固定代码证据、日志证据、调用路径和历史 incident。
- `generate_rca()` 不调用 LLM，只根据 mock evidence 生成固定 RCA。
- `find_similar_incidents()` 固定返回 `INC-003`。
- `save_incident()` 不写数据库，只返回结构化 IncidentRecord。

后续真实接入时，推荐把 `MiddlewareRouter` 改成 adapter 注入：

```text
MiddlewareRouter
- code_knowledge_core_adapter
- incident_context_builder_adapter
- rca_reasoning_engine_adapter
- incident_memory_store_adapter
```

Structure 1 的 PostgreSQL graph store 不作为第五个结构直接暴露给其他结构。它通过 `code_knowledge_core_adapter` 被 Code Knowledge Core 使用；如果未来确实需要独立的 Graph Store 结构，也必须经由 MiddlewareRouter 暴露受控请求/响应模型，不能让其他结构共享数据库连接或内部 payload。

中间件仍然保留：

- request/response schema validation
- contract_version gate
- trace_id propagation
- evidence gate
- error envelope

四个结构只替换内部实现，不改变对外 contract。

## 8. 验证状态

当前测试命令：

```bash
python -m pytest -q
```

当前验证覆盖：

- EvidenceRef confidence 范围。
- Edge evidence_refs gate。
- GraphQuery trace_id gate。
- QueryGraph router 和 HTTP endpoint。
- unsupported contract_version gate。
- RCAReport 缺 evidence_refs 时拒绝。
- mock pipeline trace 连续性。
- mock RCA 和 IncidentRecord 的 evidence_refs。
- FastAPI happy path 和 ContractError envelope。

## 9. 启动方式

```bash
python -m uvicorn legacy_pilot.middleware.app:app --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```text
http://127.0.0.1:8000/health
```

## 2026-06-30 Implementation Update

This section records the current implemented middleware contract and supersedes
older MVP/mock notes elsewhere in this file where they conflict.

Runtime defaults:

```text
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context
LEGACY_PILOT_RCA_BACKEND=qwen_api
LEGACY_PILOT_INCIDENT_MEMORY_BACKEND=postgresql
```

Production Structure 4 only allows PostgreSQL. Missing
`LEGACY_PILOT_INCIDENT_MEMORY_DSN` fails loudly; there is no production memory
fallback.

Current request/response contract additions:

- `AlertEvent.graph_id` is optional and lets the frontend use an existing graph.
- `IncidentQuery.graph_id` carries the selected or indexed graph snapshot.
- `RCAReport.graph_id`, `ReviewedRCAReport.graph_id`, and
  `IncidentRecord.graph_id` preserve the graph snapshot that produced the RCA
  evidence.
- `StoredGraph` is returned by `GET /v1/graphs` and includes
  `incident_memory_count`.
- `DeleteGraphResponse` is returned by
  `DELETE /v1/graphs/{repo_id}/{graph_id}`.

Current HTTP API surface:

```text
GET    /health
POST   /v1/repos/index
POST   /v1/graph/query
GET    /v1/graphs
DELETE /v1/graphs/{repo_id}/{graph_id}
POST   /v1/alerts/submit
POST   /v1/evidence-bundles/build
POST   /v1/incidents/similar
POST   /v1/rca/generate
POST   /v1/rca/review
POST   /v1/incidents/save
GET    /v1/incidents/{incident_id}
```

Runtime credential headers:

```text
X-LegacyPilot-Qwen-Api-Key
X-LegacyPilot-GitHub-Token
X-LegacyPilot-GitLab-Token
```

`repo_id` is the user/project-level repository alias. `graph_id` is a concrete
graph snapshot ID. A single repo alias can have multiple graph snapshots.

Graph deletion rule:

```text
DELETE /v1/graphs/{repo_id}/{graph_id}
-> count Structure 4 incidents for repo_id + graph_id
-> if count > 0, return RESOURCE_IN_USE
-> otherwise delete Structure 1 persisted graph payload
```

The frontend product path uses the middleware only. It never talks directly to
GitNexus, PostgreSQL, DashScope, GitHub, or GitLab.
