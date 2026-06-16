# Structure 1 (Code Knowledge Core) - Step 4-5 实现记录

## 结论

Step 4 和 Step 5 已按 `code-knowledge-core-gitnexus-adapter-implementation-plan.md` 的边界完成。

本阶段把 GitNexus CLI 接入拆成两层：

```text
MiddlewareRouter
  -> CodeKnowledgeCoreAdapter
    -> GitNexusCliCodeKnowledgeCoreAdapter
      -> GitNexusCliClient
        -> gitnexus_cli subprocess
      -> gitnexus_mapper
        -> LCMS contract models
```

中间件契约仍然保持在 `MiddlewareRouter`：

- `contract_version` gate 仍在 router 层。
- `trace_id` gate 仍在 router 层。
- FastAPI response model 仍验证 `GraphSnapshot` / `GraphContext`。
- GitNexus raw payload 不直接离开 Code Knowledge Core。
- 真实 backend 失败不会 silent fallback 到 mock。

## Step 4: Implement GitNexus CLI Client

### 本次新增/修改文件

```text
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/errors.py
tests/test_gitnexus_client.py
```

### Client 对外入口

`GitNexusCliClient` 暴露两个方法：

```python
index_repo(RepoIndexRequest) -> dict
query_graph(GraphQuery) -> dict
```

返回值是 mapper-ready `dict`，不是 Pydantic response model。这样符合 Step 4 边界：client 只负责 CLI 执行、stdout JSON 解析和 GitNexus raw output normalization，不负责创建 `GraphSnapshot` / `GraphContext`。

### 配置来源

client 按计划支持 constructor 参数优先、环境变量其次：

```text
GITNEXUS_BIN
GITNEXUS_REPO_ROOT
GITNEXUS_TIMEOUT_SECONDS
LEGACY_PILOT_MAX_GRAPH_NODES
LEGACY_PILOT_MAX_GRAPH_EDGES
```

constructor 显式传入的值会覆盖环境变量。

### 已实现行为

- 构造 `gitnexus_cli index` 命令，包含 repo path、repo id、language、parser profile、max nodes、max edges。
- 构造 `gitnexus_cli query` 命令，包含 repo id、graph id、query terms、node filters、edge filters、max depth、max nodes、max edges。
- 捕获 timeout，并转换为 recoverable `IndexingError` / `QueryError`。
- 捕获 missing executable，并转换为 recoverable `IndexingError` / `QueryError`。
- 捕获 non-zero exit，并转换为 recoverable Code Knowledge Core error。
- 捕获 invalid JSON stdout，并转换为 recoverable Code Knowledge Core error。
- `stderr`、`stdout`、`returncode` 保存在 `error.diagnostics` 或 `client.last_diagnostics`，但不直接拼进用户-facing error message。
- valid index JSON 归一化为 Step 3 mapper 可消费的 index payload。
- valid query JSON 归一化为 Step 3 mapper 可消费的 query payload。

### 错误模型扩展

`CodeKnowledgeCoreError` 增加：

```python
diagnostics: dict[str, str]
```

用途是保留内部诊断信息，例如 `stderr` 和 `returncode`。`MiddlewareRouter` 仍只把 `message`、`source_module`、`recoverable` 转为 `ContractError` envelope，不把内部 stack trace 或 stderr 泄露到 HTTP response text。

### 无越界行为

Step 4 client 中没有：

- FastAPI dependency
- `MiddlewareRouter` dependency
- Pydantic response model creation
- contract_version validation
- trace_id validation
- mock fallback
- GitNexus HTTP server dependency
- MyBatis / SQL extractor 逻辑

## Step 5: Wire Adapter Injection And Backend Selection

### 本次新增/修改文件

```text
legacy_pilot/code_knowledge_core/adapter.py
legacy_pilot/code_knowledge_core/__init__.py
legacy_pilot/middleware/router.py
tests/test_code_knowledge_core_adapter.py
tests/test_router_pipeline.py
tests/test_api.py
```

`legacy_pilot/middleware/app.py` 没有行为变更；`create_app(router=custom_router)` 的原有注入路径保留。

### 新增 adapter

```python
class GitNexusCliCodeKnowledgeCoreAdapter(CodeKnowledgeCoreAdapter):
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot: ...
    def query_graph(self, query: GraphQuery) -> GraphContext: ...
```

职责：

```text
RepoIndexRequest / GraphQuery
  -> GitNexusCliClient
  -> normalized dict payload
  -> gitnexus_mapper
  -> GraphSnapshot / GraphContext
```

这个 adapter 是 Step 5 的真实 backend 连接层。它只返回 LCMS contract models，不把 GitNexus raw object 暴露给 router 或 HTTP 层。

### Backend factory

新增：

```python
create_code_knowledge_core_adapter(...)
```

选择规则：

```text
LEGACY_PILOT_CODE_CORE_BACKEND missing or "mock"
  -> MockCodeKnowledgeCoreAdapter

LEGACY_PILOT_CODE_CORE_BACKEND="gitnexus_cli"
  -> GitNexusCliCodeKnowledgeCoreAdapter

unsupported value
  -> UnsupportedCodeKnowledgeCoreBackendAdapter
```

unsupported backend 使用 failing adapter，而不是在 factory 创建阶段直接抛异常。这样可以保证 `MiddlewareRouter` 的 contract gates 仍然先执行。

### Router 接入

`MiddlewareRouter.__init__()` 的默认 adapter 改为：

```python
self._code_knowledge_core_adapter = (
    code_knowledge_core_adapter
    or create_code_knowledge_core_adapter(now=self._now)
)
```

显式注入仍优先：

```python
MiddlewareRouter(code_knowledge_core_adapter=fake)
```

### Contract gate 保持不变

`index_repo()`：

```python
ensure_supported_contract_version(request.contract_version)
return self._code_knowledge_core_adapter.index_repo(request)
```

`query_graph()`：

```python
ensure_trace_id(query.trace_id)
ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
return self._code_knowledge_core_adapter.query_graph(query)
```

也就是说：

- unsupported `contract_version` 仍在 adapter 调用前被拦截。
- missing / empty `trace_id` 仍在 adapter 调用前被拦截。
- unsupported backend 只有在通过 contract gate 后才会转换为 recoverable Code Knowledge Core error。

### Error envelope 行为

Code Knowledge Core 内部错误仍通过 router 转换为 `ContractViolation(ContractError)`：

```text
trace_id       -> ContractError.trace_id
message        -> ContractError.message
source_module  -> "code_knowledge_core"
recoverable    -> true/false
```

当前仍沿用既有 `VALIDATION_ERROR` error_code，未在 Step 5 新增 error enum。这样避免扩大中间件契约 surface。

## 测试覆盖

### Step 4 client tests

`tests/test_gitnexus_client.py` 覆盖：

- CLI command includes repo path, repo id, and requested operation。
- query command includes graph id、query terms、filters、limits。
- timeout -> recoverable Code Knowledge Core error。
- missing executable -> recoverable Code Knowledge Core error。
- non-zero exit -> recoverable Code Knowledge Core error，且不泄露 stderr 到 message。
- invalid JSON stdout -> recoverable Code Knowledge Core error。
- valid index JSON -> mapper-ready index payload。
- valid query JSON -> mapper-ready query payload。
- stderr retained for diagnostics。
- constructor config overrides environment config。

### Step 5 adapter / router / API tests

`tests/test_code_knowledge_core_adapter.py` 覆盖：

- `GitNexusCliCodeKnowledgeCoreAdapter.index_repo()` 调用 client 并映射为 `GraphSnapshot`。
- `GitNexusCliCodeKnowledgeCoreAdapter.query_graph()` 调用 client 并映射为 `GraphContext`。
- missing backend 选择 mock adapter。
- `mock` backend 选择 mock adapter。
- `gitnexus_cli` backend 选择 real adapter，但不运行 GitNexus。
- unsupported backend 选择 recoverable failing adapter。

`tests/test_router_pipeline.py` 覆盖：

- `MiddlewareRouter()` 在缺省 backend 下使用 mock adapter。
- `MiddlewareRouter(code_knowledge_core_adapter=fake)` 仍委托 structure 1 calls 到 fake adapter。
- `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli` 选择 real adapter，不运行 GitNexus。
- unsupported backend 在 contract gate 之后返回 recoverable Code Knowledge Core error。
- unsupported contract version 仍先于 backend error 被拦截。

`tests/test_api.py` 覆盖：

- `create_app()` 默认 mock endpoint 仍可工作。
- `create_app(router=custom_router)` 保留已有测试注入路径。
- FastAPI response model 继续验证 `GraphContext`。

## 验证结果

已运行：

```powershell
python -m pytest tests/test_gitnexus_client.py -q
python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
python -m pytest tests/test_gitnexus_client.py tests/test_gitnexus_mapper.py -q
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
```

结果：

```text
tests/test_gitnexus_client.py: 9 passed
Step 5 target tests: 47 passed, 1 existing FastAPI/TestClient deprecation warning
GitNexus client + mapper regression: 19 passed
Full suite: 73 passed, 1 existing FastAPI/TestClient deprecation warning
compileall passed
git diff --check clean
```

## 中间件契约合规性

| 约束 | 状态 |
|---|---|
| `contract_version` gate 在 `MiddlewareRouter` | 合规 |
| `trace_id` gate 在 `MiddlewareRouter` | 合规 |
| adapter 只暴露 LCMS contract models | 合规 |
| GitNexus raw payload 不离开 Code Knowledge Core | 合规 |
| FastAPI response models 仍验证输出 | 合规 |
| real backend failure 不 silent fallback 到 mock | 合规 |
| default backend 不依赖 GitNexus | 合规 |
| unsupported backend 是 recoverable Code Core error | 合规 |
| `GraphContext` 未新增 `metadata` / `missing_evidence` | 合规 |
| MyBatis / SQL extractor 未引入 | 合规 |

## 无越界行为

Step 4-5 没有实现：

- `gitnexus_http` backend
- MyBatis XML extractor
- SQL table graph
- Java/Spring fixture integration tests
- RCA Engine direct GitNexus access
- Incident Context Builder direct GitNexus access
- LLM semantic graph enrichment
- automatic code repair

这些仍然属于后续 step 或 phase。

## 当前能力

完成 Step 4-5 后，Structure 1 具备：

- 默认 mock backend，可继续支持现有 HTTP demo 和 full default suite。
- 可选择 `gitnexus_cli` backend。
- GitNexus CLI stdout 可归一化并映射为 LCMS contract models。
- backend 配置错误和 GitNexus 运行错误可被转换为 recoverable Code Knowledge Core error。
- router/app 仍保持中间件 contract gate 和 response model 验证。

## 后续 Step 6 注意事项

Step 6 应继续保持：

- integration test opt-in。
- 缺少 GitNexus env 时默认 skip。
- 不引入 MyBatis XML 或 SQL table acceptance。
- 不允许 real backend failure silent fallback 到 mock。
- fixture 只验证 Java/Spring Controller、Service、Mapper interface 及 GitNexus 可提供的调用/路由连续性。
