# Code Knowledge Core GitNexus Adapter 设计文档

## 1. 目标

结构 1 是 LegacyPilot 的 Code Knowledge Core。它负责把 legacy repo 解析成可查询、可审计、可追溯的代码知识图谱，并通过现有 Interface Contract Middleware 暴露给其他结构。

本设计采用方案 B：

```text
LegacyPilot Python/FastAPI Middleware
-> Python CodeKnowledgeCoreAdapter
-> GitNexus TypeScript/Node engine
-> GitNexus graph/index/query result
-> LCMS contract mapper
-> GraphSnapshot / GraphContext / EvidenceRef
```

核心原则：

- 外部 HTTP 接口不变。
- 跨结构对象仍使用 `legacy_pilot.contracts.models` 中的 Pydantic contract。
- GitNexus 只作为 Code Knowledge Core 的内部算法引擎。
- 任何 GitNexus 输出进入中间件前，都必须转换成 LCMS 的 `Node`、`Edge`、`EvidenceRef`、`GraphSnapshot` 或 `GraphContext`。
- 中间件继续负责 `contract_version`、`trace_id`、`confidence`、`evidence_refs` 和统一错误 envelope。

## 2. 非目标

本阶段不实现 RCA 推理，不保存 incident memory，不让 RCA Engine 直接读取 GitNexus，也不把 GitNexus 的内部类型暴露给 Incident Context Builder、RCA Reasoning Engine 或 Incident Memory & Report Store。

本阶段也不把 GitNexus 源码完整重写成 Python。Python 只负责中间件契约、adapter 编排、数据归一化和错误转换；GitNexus 保留 TypeScript/Node 原生执行环境。

## 3. 技术选择

默认实现采用：

```text
Python / FastAPI / Pydantic:
  - Middleware HTTP boundary
  - CodeKnowledgeCoreAdapter interface
  - LCMS contract validation
  - GitNexus result mapping

TypeScript / Node / GitNexus:
  - repo indexing
  - tree-sitter parsing
  - scope resolution
  - route extraction
  - graph search / context / trace / impact
```

选择理由：

- 之前中间件已经按 Python/FastAPI 建立，结构 1 接入不应改变外部 contract。
- GitNexus 的核心算法是 TypeScript/Node 实现，直接调用比重写风险低。
- Python adapter 可以把 GitNexus 的非契约化输出收敛成 LegacyPilot 的严格契约。

实施时优先使用 GitNexus CLI 或本地 HTTP server 作为执行边界。后续如需更高性能，再增加 TypeScript thin bridge，但 Python 中间件对外契约保持不变。

## 4. 现有中间件接口边界

结构 1 只接管两个接口：

```text
POST /v1/repos/index
Request: RepoIndexRequest
Response: GraphSnapshot
Owner: Code Knowledge Core
```

```text
POST /v1/graph/query
Request: GraphQuery
Response: GraphContext
Owner: Code Knowledge Core
```

其他接口仍归对应结构所有：

```text
SubmitAlert -> Incident Context Builder
BuildEvidenceBundle -> Incident Context Builder
GenerateRCA -> RCA Reasoning Engine
ReviewRCA -> RCA Reasoning Engine
FindSimilarIncidents -> Incident Memory & Report Store
SaveIncident -> Incident Memory & Report Store
```

Code Knowledge Core 的输出只能成为 evidence 和 graph context，不能直接输出最终根因。

## 5. 模块设计

推荐新增目录：

```text
legacy_pilot/
  code_knowledge_core/
    __init__.py
    adapter.py
    gitnexus_client.py
    gitnexus_mapper.py
    errors.py
```

各文件职责：

```text
adapter.py
  定义 CodeKnowledgeCoreAdapter 抽象接口。
  中间件只依赖该接口，不依赖 GitNexus 具体调用方式。

gitnexus_client.py
  当前只调用 GitNexus CLI。
  IndexRepo 使用 analyze 构建索引，再用 cypher 抽取图节点和边。
  QueryGraph 使用 cypher 解析符号或 route，再用 context 读取调用上下文。
  HTTP server / TS bridge 是后续扩展，不属于首版已实现 backend。
  负责命令执行、超时、进程错误、JSON 解析和 GitNexus 运行状态检查。

gitnexus_mapper.py
  把 GitNexus node/relationship/tool payload 转成 LCMS contract model。
  负责 EvidenceRef 生成、confidence 映射、source_location 映射和 metadata 归一化。

errors.py
  定义 Code Knowledge Core 内部异常。
  MiddlewareRouter 捕获后转换为 ContractViolation / ContractError。
```

`MiddlewareRouter` 构造函数增加可选依赖：

```text
MiddlewareRouter(
  code_knowledge_core_adapter: CodeKnowledgeCoreAdapter | None = None,
  incident_context_builder_adapter: IncidentContextBuilderAdapter | None = None,
  rca_reasoning_engine_adapter: RCAReasoningEngineAdapter | None = None,
  incident_memory_store_adapter: IncidentMemoryStoreAdapter | None = None,
  now: Callable[[], datetime] | None = None
)
```

结构 1 首版只实现 `code_knowledge_core_adapter`，另外三个 adapter 槽位保留给 Phase 2-4，和中间件总设计保持一致。未注入 adapter 时继续使用当前 deterministic mock，便于测试和演示。注入 GitNexus adapter 后，`index_repo()` 和 `query_graph()` 调用真实结构 1。

## 6. IndexRepo 数据流

输入：

```text
RepoIndexRequest
- repo_id
- repo_uri
- language_hint
- parser_profile
- contract_version
```

处理流程：

```text
FastAPI route
-> Pydantic validates RepoIndexRequest
-> MiddlewareRouter.index_repo()
-> ensure_supported_contract_version()
-> CodeKnowledgeCoreAdapter.index_repo()
-> GitNexus analyze/index
-> GitNexus index metadata and graph summary
-> gitnexus_mapper.to_graph_snapshot()
-> GraphSnapshot returned
```

契约要求：

- `contract_version` 必须由中间件先校验。
- `repo_uri` 必须指向允许访问的本地路径或受控 repo URI。
- `GraphSnapshot.graph_id` 必须稳定，可用 `gitnexus:{repo_id}:{index_commit_or_timestamp}`。
- `GraphSnapshot.nodes` 和 `GraphSnapshot.edges` 可以在首版限制数量，完整图保留在 GitNexus index 中。
- `GraphSnapshot.evidence_refs` 必须至少覆盖返回的节点和边。
- 每条 `Edge` 必须至少有一个 `EvidenceRef`。
- parser/tree-sitter 产生的结构事实使用 `extraction_method = tree_sitter`，confidence 通常落在 `0.85 - 1.0`。

首版 `IndexRepo` 可以返回摘要型 snapshot：

```text
nodes:
  - route nodes
  - controller/service/method nodes
  - high-confidence graph entry nodes

edges:
  - HANDLES_ROUTE
  - CALLS
  - IMPORTS
  - HAS_METHOD
  - QUERIES if later补充 SQL extractor
```

完整图查询交给 `QueryGraph`。

## 7. QueryGraph 数据流

输入：

```text
GraphQuery
- repo_id
- graph_id
- query_terms[]
- node_filters[]
- edge_filters[]
- max_depth
- trace_id
- contract_version
```

处理流程：

```text
FastAPI route
-> Pydantic validates GraphQuery
-> MiddlewareRouter.query_graph()
-> ensure_trace_id()
-> ensure_supported_contract_version(trace_id=query.trace_id)
-> CodeKnowledgeCoreAdapter.query_graph()
-> GitNexus query/context/trace/impact
-> gitnexus_mapper.to_graph_context()
-> GraphContext returned
```

契约要求：

- `trace_id` 必须沿用调用方传入值。
- `GraphContext.trace_id` 必须等于 `GraphQuery.trace_id`。
- `GraphContext.confidence` 必须在 `0.0 - 1.0`。
- `matched_edges[]` 每条边必须携带 `evidence_refs`。
- `graph_paths[]` 使用 LCMS 稳定节点名或 node_id，不直接暴露 GitNexus 内部临时对象。
- GitNexus ambiguous / not_found / no_path 不能直接透传，必须转成可恢复的 LCMS 响应或 `ContractError`。

GitNexus 工具选择规则：

```text
query_terms 只有关键词:
  使用 GitNexus query，返回 processes、process_symbols、definitions 三类结果。

query_terms 包含精确符号名，如 DatasetService.getVersion:
  先使用 GitNexus context，拿 incoming/outgoing references。

query_terms 表示 from/to 或 node_filters 指定起止节点:
  使用 GitNexus trace，返回 path。

edge_filters 包含 impact/upstream/downstream:
  使用 GitNexus impact，返回影响面并映射为 matched_nodes、matched_edges、graph_paths。
```

首版可以支持关键词和符号上下文，trace/impact 作为第二批能力接入。当前 `GraphContext` contract 没有 `metadata` 字段，因此 `gitnexus_tool` 这类诊断信息只写入 adapter 内部日志或后续 contract 扩展，不进入首版 HTTP 响应。

## 8. GitNexus 到 LCMS 的对象映射

### 8.1 Node 映射

```text
GitNexus GraphNode
- id
- label
- properties.name
- properties.filePath
- properties.startLine
- properties.endLine

LCMS Node
- node_id = GitNexus id
- graph_id = request.graph_id 或 index 生成值
- repo_id = request.repo_id
- type = GitNexus label
- name = properties.name
- qualified_name = properties.qualifiedName；若缺失且有 file_path/name，则使用 file_path::name；否则为 null
- source_location = filePath/startLine/endLine
- metadata.gitnexus = 原始 label、properties 子集、tool 信息
- evidence_refs = 至少一个 node evidence
```

不能把 `qualified_name` 简单回退为 `name`。不同作用域内可能存在同名符号，盲目回退会让 `ServiceA.getVersion` 和 `ServiceB.getVersion` 这类节点失去区分度。

节点 evidence 生成规则：

```text
source_type = code
source_id = GitNexus node id
file_path = properties.filePath
start_line = properties.startLine
end_line = properties.endLine
extraction_method = tree_sitter
confidence = 0.95 for parser-defined node, lower for inferred nodes
created_at = datetime.now(UTC)
```

### 8.2 Edge 映射

```text
GitNexus GraphRelationship, 经 gitnexus_client 归一化后的中间表示
- id
- sourceId
- targetId
- type
- confidence
- reason
- evidence[] optional

LCMS Edge
- edge_id = GitNexus relationship id
- graph_id = request.graph_id 或 index 生成值
- source_node_id = sourceId
- target_node_id = targetId
- type = GitNexus relationship type
- confidence = 归一化后的 confidence，来源可以是 GitNexus shared graph、scope-resolution evidence 或 relation-type fallback
- extraction_method = tree_sitter
- evidence_refs = 至少一个 edge evidence
- metadata.gitnexus = { reason, evidence_signals, source_relationship_type }
```

底层 `CodeRelation` 存储和 GitNexus shared graph 类型不完全等价。adapter 不直接依赖底层表结构，而是通过 `gitnexus_client` 先归一化出稳定 JSON，再映射到 LCMS `Edge`。

边 evidence 生成规则：

```text
优先使用 source node 的 source_location。
如果 source node 没有位置，则使用 target node 的 source_location。
如果两者都没有位置，则仍使用 source_type=code，file_path/start_line/end_line 为空，extraction_method=system_generated，confidence 降至 0.5-0.6。
created_at = datetime.now(UTC)
```

禁止返回没有 evidence_refs 的 `Edge`。无法生成证据的边必须丢弃，或返回 recoverable `ContractError`。当前 `GraphContext` contract 没有 `missing_evidence` 字段，Code Knowledge Core 不能通过成功响应把缺证据信号传给 Incident Context Builder；如需显式传递，后续 contract 版本需要扩展字段。

### 8.3 GraphSnapshot 映射

```text
GraphSnapshot
- graph_id
- repo_id
- nodes
- edges
- evidence_refs
- generated_at
```

`evidence_refs` 是 `nodes[].evidence_refs` 和 `edges[].evidence_refs` 按 `evidence_id` 去重后的合集。

### 8.4 GraphContext 映射

```text
GraphContext
- trace_id = GraphQuery.trace_id
- matched_nodes
- matched_edges
- graph_paths
- evidence_refs
- confidence
```

`confidence` 计算规则：

```text
若有 matched_edges:
  min(平均 edge confidence, max(所有 matched_edges 中所有 evidence_refs 的 confidence))

若只有 matched_nodes:
  平均 node evidence confidence

若 GitNexus 返回 ambiguous:
  不返回 GraphContext，返回 ContractError 或 recoverable query clarification error

若 not_found:
  返回空 GraphContext，confidence = 0.0，不写任何强结论
```

当前 `GraphContext` contract 没有 `metadata` 字段，因此首版 not_found 可以返回空 `matched_nodes`、空 `matched_edges`、空 `graph_paths`、空 `evidence_refs`、`confidence = 0.0`。如果需要表达更丰富 query 状态，后续 contract 版本再增加可选字段。

## 9. Evidence 规范

所有由结构 1 生成的证据都必须符合 `EvidenceRef`：

```text
evidence_id
trace_id
source_type
source_id
file_path
start_line
end_line
excerpt
excerpt_hash
extraction_method
confidence
created_at
```

`trace_id` 规则：

```text
IndexRepo:
  当前请求没有 trace_id，使用 TRACE-INDEX-{repo_id} 作为 indexing trace。

QueryGraph:
  必须使用 GraphQuery.trace_id。
```

`evidence_id` 规则：

```text
EV-GN-{short_hash(trace_id, source_id, file_path, start_line, end_line)}
short_hash = sha256(joined_fields).hexdigest()[:12]
```

`created_at` 由 adapter 在生成 `EvidenceRef` 时统一设置为当前 UTC 时间，即 `datetime.now(UTC)`。

`excerpt` 规则：

```text
如果文件可读:
  取 start_line 到 end_line 的代码片段，限制最大长度。

如果文件不可读:
  excerpt = null
  excerpt_hash = null
  confidence 最高不超过 0.75
```

`source_type` 映射：

```text
File/Class/Method/Function/Route/Process/Community -> code
SQL table / mapper XML / query extraction -> sql
application.yml / config 文件 -> config
GitNexus markdown section -> document
LLM 语义增强 -> llm_semantic_summary
```

`extraction_method` 映射：

```text
tree-sitter parser result -> tree_sitter
JavaParser result -> java_parser
regex fallback -> regex
GitNexus semantic/vector search -> vector_retrieval
LLM enrichment -> llm
system-generated graph summary -> system_generated
```

## 10. Error Envelope 规范

GitNexus 侧错误不能直接暴露给调用方。adapter 必须转换为 `ContractViolation`，最终由 FastAPI 返回 `ContractError`。

建议错误映射：

```text
GitNexus executable not found:
  error_code = VALIDATION_ERROR
  source_module = code_knowledge_core
  recoverable = true
  message = GitNexus runtime is not configured.

repo_uri 不存在或不可读:
  error_code = VALIDATION_ERROR
  source_module = code_knowledge_core
  recoverable = true
  missing_fields = ["repo_uri"]

contract_version 不支持:
  由 MiddlewareRouter 在调用 adapter 前返回 UNSUPPORTED_CONTRACT_VERSION

trace_id 缺失:
  由 MiddlewareRouter 在调用 adapter 前返回 TRACE_REQUIRED

GitNexus query ambiguous:
  error_code = VALIDATION_ERROR
  source_module = code_knowledge_core
  recoverable = true
  message = Query matched multiple symbols; narrow with node_filters or file path.

GitNexus no index found:
  error_code = VALIDATION_ERROR
  source_module = code_knowledge_core
  recoverable = true
  message = Repository has not been indexed; call IndexRepo first.

Edge 无法生成 evidence_refs:
  error_code = EVIDENCE_REQUIRED
  source_module = code_knowledge_core
  recoverable = true
```

## 11. GitNexus 调用方式

首版实现优先级：

### 11.1 CLI subprocess

Python adapter 使用 `subprocess.run()` 调用 GitNexus CLI 或本地 checkout 中的 package script。

优点：

- 实现最快。
- 不需要长期运行 Node server。
- 和 FastAPI 生命周期解耦。

约束：

- 每次调用要设置 timeout。
- stdout 必须是可解析 JSON，stderr 只用于日志。
- 命令路径通过环境变量配置。

### 11.2 Local HTTP server

运行 `gitnexus serve`，Python adapter 通过 HTTP 调用。

优点：

- 查询延迟更低。
- 适合 demo server 和持续交互。

约束：

- 需要健康检查。
- 需要处理 server 未启动、端口冲突、index stale。
- HTTP payload 仍需经过 LCMS mapper。

### 11.3 TypeScript thin bridge

后续可以在 LegacyPilot repo 内增加一个很薄的 TS bridge，只负责把 GitNexus internal API 包装成稳定 JSON。

优点：

- 可以避免 CLI 文本格式不稳定。
- 可以直接调用 GitNexus `LocalBackend` 或 pipeline API。

约束：

- 需要 Node 22 运行环境。
- 需要额外构建和测试链。
- Python 仍然是中间件主控，TS bridge 不暴露给其他结构。

## 12. 配置

建议环境变量：

```text
LEGACY_PILOT_CODE_CORE_BACKEND=mock|gitnexus_cli
GITNEXUS_BIN=gitnexus
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus
GITNEXUS_TIMEOUT_SECONDS=60
LEGACY_PILOT_MAX_GRAPH_NODES=200
LEGACY_PILOT_MAX_GRAPH_EDGES=400
LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1
```

默认值：

```text
LEGACY_PILOT_CODE_CORE_BACKEND=mock
GITNEXUS_TIMEOUT_SECONDS=60
LEGACY_PILOT_MAX_GRAPH_NODES=200
LEGACY_PILOT_MAX_GRAPH_EDGES=400
```

这样测试环境不需要 GitNexus，集成环境通过配置启用真实结构 1。
当前真实 backend 只有 `gitnexus_cli`。`gitnexus_http` 不在首版实现范围内。
当选择 `gitnexus_cli` 且 GitNexus 不可用时，系统返回 recoverable `ContractError`，不静默回退到 mock。

## Semantic Enrichment Boundary

Milestone4 keeps semantic enrichment inside Code Knowledge Core. The HTTP
middleware still sees only LCMS contract models and continues to own
`contract_version` and `trace_id` validation.

Index flow:

```text
GitNexusCliClient.index_repo()
-> structural enrichers: SQL / config / exception
-> semantic enricher: disabled by default, mock when explicitly enabled
-> merge_graph_payloads()
-> gitnexus_mapper.map_index_payload()
-> GraphSnapshot
```

Semantic enrichment is not a parser replacement. It creates pending semantic
nodes and `HAS_SEMANTIC_ACTION` edges with `source_type=llm_semantic_summary`,
`extraction_method=llm`, and capped confidence. Structural graph facts continue
to come from GitNexus plus deterministic SQL/config/exception extractors.

Supported semantic backends:

```text
LEGACY_PILOT_SEMANTIC_BACKEND=disabled|mock|qwen_api
LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP=0.7
LEGACY_PILOT_SEMANTIC_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
LEGACY_PILOT_SEMANTIC_MODEL=qwen-plus
DASHSCOPE_API_KEY=<set outside git>
```

The `qwen_api` backend uses DashScope's OpenAI-compatible Chat Completions API
and remains opt-in. API keys must be injected through the environment and must
not be committed to repository files.

## 13. Java/Spring 首版范围

首版结构 1 面向 Java/Spring Boot legacy repo，优先覆盖：

```text
Route / Controller
Controller method
Service class / method
Mapper interface method
普通 CALLS / IMPORTS / HAS_METHOD / HANDLES_ROUTE
```

GitNexus 已具备 Spring route extraction 和 Java scope-resolution 能力，因此首版可以直接复用。

Milestone2-Milestone5 当前状态：MyBatis / Mapper XML / SQL table 已接入：

```text
Mapper interface -> XML statement
XML statement -> SQL table
Service method -> Mapper method -> SQL table
```

SQL/config/exception facts come from deterministic Python enrichers merged
after the GitNexus structural graph. This stays inside Code Knowledge Core and
does not change middleware contracts.

## 14. 与其他三个结构的约束

### 14.1 Incident Context Builder

Incident Context Builder 可以通过中间件调用 `QueryGraph`，但不能直接调用 GitNexus。

它接收的是：

```text
GraphContext
matched_nodes
matched_edges
graph_paths
evidence_refs
```

它输出 `EvidenceBundle` 时必须沿用：

```text
IncidentQuery.trace_id
IncidentQuery.contract_version
GraphContext.evidence_refs
```

### 14.2 RCA Reasoning Engine

RCA Engine 只能读取 `EvidenceBundle`，不能直接读取 repo、GitNexus index 或 GitNexus HTTP API。

如果 RCA Engine 需要更多代码上下文，必须通过 Incident Context Builder 重新请求中间件组装 EvidenceBundle，而不是绕过结构边界。

### 14.3 Incident Memory & Report Store

Incident Memory 只能保存用户确认后的 `ReviewedRCAReport` 和 `IncidentRecord`。

从结构 1 来的 node_id、edge_id、file_path 可以进入：

```text
IncidentRecord.related_nodes
IncidentRecord.related_files
IncidentRecord.evidence_refs
```

但不能保存 GitNexus 内部不稳定对象作为唯一事实来源。必须保存 LCMS `EvidenceRef`。

## 15. 测试策略

### 15.1 Contract tests

验证 adapter 输出满足 Pydantic contract：

```text
GraphSnapshot can be validated.
GraphContext can be validated.
Every Edge has evidence_refs.
Every EvidenceRef confidence is within 0.0 - 1.0.
GraphQuery missing trace_id returns TRACE_REQUIRED at HTTP boundary.
Unsupported contract_version returns UNSUPPORTED_CONTRACT_VERSION.
```

### 15.2 Mapper tests

使用固定 GitNexus-like payload，不启动 GitNexus，测试：

```text
GraphNode -> Node
GraphRelationship -> Edge
source location -> EvidenceRef
relationship.evidence -> Edge.metadata.gitnexus.evidence_signals
missing source location lowers confidence
edge without evidence source is rejected or omitted
```

### 15.3 Adapter tests

使用 fake `GitNexusClient` 测试：

```text
index_repo returns GraphSnapshot.
query_graph returns GraphContext.
query_graph propagates trace_id.
GitNexus ambiguous becomes recoverable ContractError.
GitNexus not indexed becomes recoverable ContractError.
```

### 15.4 Integration tests

启用真实 GitNexus 时，使用小型 Java/Spring fixture：

```text
@RestController + @GetMapping
Controller method calls Service method
Service method calls Mapper method
Mapper XML statement reads dataset_version table
application.yml config and Java exception nodes are extracted
```

首版 integration 验收：

```text
IndexRepo creates non-empty GraphSnapshot.
QueryGraph("DatasetService.getVersion") returns Method node.
QueryGraph("/api/dataset/version") returns Route or Controller context.
Route ENTRY_POINT_OF + Method STEP_IN_PROCESS is normalized to MAPS_TO_ENDPOINT.
Production fixture proves endpoint -> controller -> service -> mapper -> SQL -> table.
Returned edges have EvidenceRef.
GraphContext.trace_id equals request.trace_id.
```

## 16. 开发顺序

### Step 1: Adapter interface

新增 `CodeKnowledgeCoreAdapter` 抽象接口，保持 MiddlewareRouter 只依赖该接口。

契约检查：

```text
输入仍是 RepoIndexRequest / GraphQuery。
输出仍是 GraphSnapshot / GraphContext。
不允许返回 GitNexus 原始对象。
```

### Step 2: Mock adapter extraction

把当前 `MiddlewareRouter.index_repo()` 和 `query_graph()` 中的 mock 逻辑抽到 `MockCodeKnowledgeCoreAdapter`。

契约检查：

```text
现有测试继续通过。
HTTP response shape 不变。
trace_id 和 contract_version gate 仍在 MiddlewareRouter 层执行。
```

### Step 3: GitNexus mapper

实现 GitNexus payload 到 LCMS contract 的纯函数映射。

契约检查：

```text
每个 Node 有 source_location 或 metadata 说明来源。
每个 Edge 有 evidence_refs。
EvidenceRef 使用 LCMS 枚举值。
confidence 合法。
```

### Step 4: GitNexus client

实现 CLI 或 HTTP 调用封装。

契约检查：

```text
超时和执行错误被转换为 Code Knowledge Core 内部异常。
内部异常最终由中间件包装成 ContractError。
stderr、stack trace、Node exception 不直接返回给调用方。
```

### Step 5: MiddlewareRouter injection

把 `MiddlewareRouter` 改成可注入真实 adapter。

契约检查：

```text
contract_version gate 在 adapter 前执行。
trace_id gate 在 adapter 前执行。
adapter 输出再次经过 Pydantic response_model 校验。
```

### Step 6: Integration fixture

加入 Java/Spring fixture 和可选 GitNexus integration test。

契约检查：

```text
无 GitNexus 环境时跳过 integration，不影响单元测试。
启用 GitNexus 环境时跑真实索引和查询。
启用 integration 需要同时设置 LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1、GITNEXUS_BIN、GITNEXUS_REPO_ROOT。
源码 checkout 测试时，GITNEXUS_BIN 可以指向类似 Q:\tmp\gitnexus-local.cmd 的 wrapper。
在受限 sandbox 中运行真实 GitNexus 可能需要提升权限，因为 GitNexus 会写入 fixture .gitnexus 和用户级 registry。
```

## 17. 运行与降级

默认运行模式仍是 mock：

```text
LEGACY_PILOT_CODE_CORE_BACKEND=mock
```

启用真实结构 1：

```text
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
GITNEXUS_BIN=gitnexus
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus
GITNEXUS_TIMEOUT_SECONDS=120
```

如果 GitNexus 不可用：

```text
IndexRepo:
  返回 recoverable ContractError，不生成假 GraphSnapshot。

QueryGraph:
  返回 recoverable ContractError，提示先配置或启动 GitNexus。
```

不要在真实模式下静默回退 mock，否则 RCA 可能基于假证据生成误导性结论。

## 18. 验收标准

结构 1 首版完成后必须满足：

```text
1. 现有 middleware HTTP contract 不破坏。
2. IndexRepo 可以通过 adapter 返回 GraphSnapshot。
3. QueryGraph 可以通过 adapter 返回 GraphContext。
4. GraphContext.trace_id 严格沿用 GraphQuery.trace_id。
5. 所有 Edge 都有 evidence_refs。
6. GitNexus 内部错误被转换成 ContractError envelope。
7. Incident Context Builder 只消费 GraphContext，不直接依赖 GitNexus。
8. RCA Engine 只消费 EvidenceBundle，不直接读取 repo 或 GitNexus。
9. Mock 模式和 GitNexus 模式都可测试。
10. Java/Spring 首版 fixture 能证明 route/controller/service 图谱查询闭环。
```

## 19. 默认决策与实施前确认点

默认决策：

```text
语言边界:
  Python 保持中间件主控，TypeScript/Node 保持 GitNexus 算法执行。

首版调用方式:
  已实现 gitnexus_cli adapter；gitnexus_http 不属于首版。

首版领域:
  Java/Spring Boot route/controller/service 图谱。

Milestone2+ SQL 能力:
  MyBatis/Mapper XML/SQL table 已接入 Structure 1 enrichers，并由 production fixture 覆盖。

真实模式降级:
  GitNexus 不可用时返回 ContractError，不静默回退 mock。
```

实施前需要确认的选择：

```text
1. Java/Spring fixture 默认使用 tests/fixtures/java_spring_demo。
2. MyBatis/SQL extractor 已完成最小 production fixture 覆盖；后续仅扩展复杂 SQL、多模块和 dialect parser。
```
