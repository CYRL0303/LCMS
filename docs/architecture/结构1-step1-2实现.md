# Structure 1 (Code Knowledge Core) — Step 1-2 实现记录

## 总体目标

按照 `code-knowledge-core-gitnexus-adapter-implementation-plan.md` 的 Step 1 和 Step 2，在 `MiddlewareRouter` 背后引入 Code Knowledge Core 适配器边界，将 mock 图谱逻辑从路由器迁移到 `MockCodeKnowledgeCoreAdapter`，同时完整保留中间件契约门（`contract_version`、`trace_id`）在路由器层。

## 架构关系

```text
HTTP Request
  → FastAPI route (app.py)
    → Pydantic request validation
      → MiddlewareRouter (router.py)
        → ensure_supported_contract_version() / ensure_trace_id()  ← 契约门保留在此
        → CodeKnowledgeCoreAdapter.index_repo() / query_graph()     ← 适配器委托
          → MockCodeKnowledgeCoreAdapter (默认) / GitNexusAdapter (step 5)
```

中间件框架定义的四个约束在本次实现中全部保持：
- `contract_version` 校验 → `MiddlewareRouter`
- `trace_id` 校验 → `MiddlewareRouter`
- `confidence` 范围 → Pydantic 模型层
- `Edge.evidence_refs` 最小长度 → Pydantic 模型层
- `GraphSnapshot.evidence_refs` / `GraphContext.evidence_refs` 覆盖关系 → adapter 语义规则，当前 mock adapter 返回非空 evidence；后续 GitNexus mapper 继续按 evidence_id 去重并保证返回边都有证据

## Step 1: 定义 CodeKnowledgeCoreAdapter 接口

### 创建文件

| 文件 | 说明 |
|---|---|
| `legacy_pilot/code_knowledge_core/__init__.py` | 包导出：`CodeKnowledgeCoreAdapter`, `CodeKnowledgeCoreError`, `IndexingError`, `QueryError` |
| `legacy_pilot/code_knowledge_core/adapter.py` | 抽象基类 `CodeKnowledgeCoreAdapter(ABC)`，定义两个抽象方法 |
| `legacy_pilot/code_knowledge_core/errors.py` | `CodeKnowledgeCoreError(Exception)` 基类，携带 `source_module = "code_knowledge_core"`，含 `IndexingError` 和 `QueryError` 子类 |
| `tests/test_code_knowledge_core_adapter.py` | 9 个测试：接口签名、fake adapter 返回有效 LCMS 模型、错误携带路由转换所需数据、不暴露 GitNexus 对象 |

### 适配器接口

```python
class CodeKnowledgeCoreAdapter(ABC):
    @abstractmethod
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot: ...
    @abstractmethod
    def query_graph(self, query: GraphQuery) -> GraphContext: ...
```

接口仅引用 LCMS contract models（`RepoIndexRequest`, `GraphSnapshot`, `GraphQuery`, `GraphContext`），不出现任何 GitNexus 类型。

### 错误模型

```python
class CodeKnowledgeCoreError(Exception):
    source_module = "code_knowledge_core"  # 供 MiddlewareRouter 转换为 ContractError envelope
    message: str
    recoverable: bool
```

### 验证结果

```text
$ python -m pytest tests/test_code_knowledge_core_adapter.py -q
9 passed

$ python -m pytest tests/test_contract_models.py -q
7 passed

$ python -m pytest -q
31 passed  (22 原有 + 9 新增)
```

- `legacy_pilot.code_knowledge_core` 可导入
- 适配器接口仅引用 LCMS 合约模型
- 全量测试零 GitNexus 依赖
- 无生产文件被修改

---

## Step 2: 提取 Mock 图谱逻辑到 MockCodeKnowledgeCoreAdapter

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `legacy_pilot/code_knowledge_core/adapter.py` | +`MockCodeKnowledgeCoreAdapter` 类，包含原 `MiddlewareRouter.index_repo()` 和 `query_graph()` 的逐字 mock 逻辑，自带 `_now` 时钟注入和 `_evidence_ref` 工厂 |
| `legacy_pilot/code_knowledge_core/__init__.py` | +导出 `MockCodeKnowledgeCoreAdapter` |
| `legacy_pilot/middleware/router.py` | `__init__` 新增 `code_knowledge_core_adapter` 可选参数（默认 `MockCodeKnowledgeCoreAdapter`）；`index_repo()` 缩减为校验+委托 2 行；`query_graph()` 缩减为校验+委托 3 行；其余 7 个方法不变 |
| `tests/test_code_knowledge_core_adapter.py` | +`RecordingFakeAdapter`、+`TestMockAdapterPreservesOriginalBehavior`、+`TestGateBeforeAdapter` |
| `tests/test_router_pipeline.py` | +`TestDefaultRouterPreservesMockBehavior`、+`TestGateInterceptsBeforeAdapter`（3 个门测试） |

### 路由器变更对比

**Before (router.py):**

```python
class MiddlewareRouter:
    def __init__(self, now=None):
        self._now = now or (lambda: datetime.now(UTC))

    def index_repo(self, request):
        ensure_supported_contract_version(request.contract_version)
        trace_id = f"TRACE-INDEX-{request.repo_id}"
        evidence = self._evidence_ref(...)
        controller = Node(...)
        service = Node(...)
        edge = Edge(...)
        return GraphSnapshot(...)          # ← 30+ 行 mock 逻辑

    def query_graph(self, query):
        ensure_trace_id(query.trace_id)
        ensure_supported_contract_version(...)
        evidence = self._evidence_ref(...)
        controller = Node(...)
        service = Node(...)
        mapper = Node(...)
        ...
        return GraphContext(...)           # ← 60+ 行 mock 逻辑
```

**After (router.py):**

```python
class MiddlewareRouter:
    def __init__(self, now=None, *, code_knowledge_core_adapter=None):
        self._now = now or (lambda: datetime.now(UTC))
        self._code_knowledge_core_adapter = (
            code_knowledge_core_adapter
            or MockCodeKnowledgeCoreAdapter(now=self._now)
        )

    def index_repo(self, request):
        ensure_supported_contract_version(request.contract_version)
        return self._code_knowledge_core_adapter.index_repo(request)

    def query_graph(self, query):
        ensure_trace_id(query.trace_id)
        ensure_supported_contract_version(query.contract_version, trace_id=query.trace_id)
        return self._code_knowledge_core_adapter.query_graph(query)
```

### 新增测试明细

**TestMockAdapterPreservesOriginalBehavior (adapter 测试文件):**
- `test_mock_adapter_index_repo_returns_demo_graph_snapshot` — 验证 `MockCodeKnowledgeCoreAdapter.index_repo()` 输出与原始路由器完全一致（`GRAPH-DEMO`、`NODE-DATASET-CONTROLLER`、`NODE-DATASET-SERVICE`、`EDGE-CONTROLLER-SERVICE`）
- `test_mock_adapter_query_graph_returns_demo_graph_context` — 验证 3 节点、2 边、`confidence=0.88`

**TestDefaultRouterPreservesMockBehavior (router pipeline 测试文件):**
- `test_default_router_index_repo_returns_same_mock_snapshot` — 无参 `MiddlewareRouter()` 仍然返回相同 mock 数据
- `test_default_router_query_graph_returns_same_mock_context` — 无参 `MiddlewareRouter()` 仍然返回相同 mock 数据

**TestGateInterceptsBeforeAdapter (router pipeline 测试文件):**
- `test_unsupported_contract_version_blocks_index_repo_before_adapter` — `contract_version="2.0.0"` 触发 `UNSUPPORTED_CONTRACT_VERSION`，验证 `adapter.index_called is False`
- `test_missing_trace_id_blocks_query_graph_before_adapter` — `trace_id=""` 触发 `TRACE_REQUIRED`，验证 `adapter.query_called is False`
- `test_unsupported_contract_version_blocks_query_graph_before_adapter` — `contract_version="2.0.0"` 触发 `UNSUPPORTED_CONTRACT_VERSION`，验证 `adapter.query_called is False`

### 验证结果

```text
$ python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
35 passed

$ python -m pytest -q
42 passed  (31 原有 + 9 新增 Step 2 + 2 个 CodeKnowledgeCoreError 转换测试)
```

### 出口标准核查

| 标准 | 状态 |
|---|---|
| `MiddlewareRouter.index_repo()` 仅在 contract_version 校验后委托适配器 | ✅ 第 44-46 行 |
| `MiddlewareRouter.query_graph()` 仅在 trace_id + contract_version 校验后委托适配器 | ✅ 第 48-51 行 |
| 其他结构方法（submit_alert / build_evidence_bundle / generate_rca / review_rca / find_similar_incidents / save_incident）未重构 | ✅ 未修改 |
| 默认路由器仍返回相同 mock 数据 | ✅ 2 个保留测试通过 |
| 契约门在适配器执行前拦截 | ✅ 3 个门测试通过，RecordingFakeAdapter 确认未被调用 |
| CodeKnowledgeCoreError 被转换为 ContractError envelope | ✅ 2 个错误转换测试通过 |
| 全量测试零 GitNexus 依赖 | ✅ `grep -r GitNexus legacy_pilot/` 无结果 |
| 现有 API 路由测试全部通过 | ✅ test_api.py 7/7 |
| `legacy_pilot.code_knowledge_core` 可导入 | ✅ |

---

## 关键设计决策

1. **适配器用 ABC 而非 Protocol** — ABC 在 pytest 中更容易做 fake/spy，且未来 `isinstance` 检查更直观。
2. **MockCodeKnowledgeCoreAdapter 自带 `_now` 和 `_evidence_ref`** — 不依赖 MiddlewareRouter 的内部 helper，保持适配器的独立可测试性。
3. **RecordingFakeAdapter 定义在测试文件内** — 避免跨测试模块导入的路径问题，每个测试文件自己维护轻量 fake。
4. **路由器保留 `_evidence_ref`** — 因为 `build_evidence_bundle`、`find_similar_incidents` 等非 Code Knowledge Core 方法仍在使用。

## 文件清单

```text
legacy_pilot/code_knowledge_core/
  __init__.py          ← Step 1 创建，Step 2 更新导出
  adapter.py           ← Step 1 创建 (ABC)，Step 2 新增 MockCodeKnowledgeCoreAdapter
  errors.py            ← Step 1 创建

legacy_pilot/middleware/
  router.py            ← Step 2 修改：构造函数+index_repo+query_graph

tests/
  test_code_knowledge_core_adapter.py  ← Step 1 创建，Step 2 扩展
  test_router_pipeline.py              ← Step 2 扩展
  test_api.py                          ← 未修改，全部通过
  test_contract_models.py              ← 未修改，全部通过
```

## 审计 by deepseek
  审计报告：Structure 1 Step 1-2 对照三份架构文档

  一、文件修改范围（对照 plan Step 1 + Step 2）

  ┌───────────────────────────────────────────────────────┬───────────────────────────────────────────────┬──────────────────┐
  │                       Plan 要求                       │                   实际状态                    │       判定       │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 1 创建 code_knowledge_core/ 下的 3 个文件        │ ✅ 已创建 __init__.py, adapter.py, errors.py  │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 1 创建 tests/test_code_knowledge_core_adapter.py │ ✅ 已创建                                     │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 修改 adapter.py（加 MockAdapter）              │ ✅ 已添加 MockCodeKnowledgeCoreAdapter        │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 修改 router.py（注入适配器）                   │ ✅ 构造函数 + index_repo + query_graph 已修改 │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 修改 test_code_knowledge_core_adapter.py       │ ✅ 已扩展                                     │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 修改 test_router_pipeline.py                   │ ✅ 已扩展                                     │ 合规             │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 修改 test_api.py                               │ ✅ 未修改，全量测试通过                       │ 合规（无需改动） │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────────────────┼──────────────────┤
  │ Step 2 不修改 app.py                                  │ ✅ 未修改（Step 5 才需要）                    │ 合规             │
  └───────────────────────────────────────────────────────┴───────────────────────────────────────────────┴──────────────────┘

  二、Step 1 出口标准

  ┌────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │                      标准                      │                             状态                             │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ legacy_pilot.code_knowledge_core 可导入        │ ✅                                                           │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ 适配器接口仅引用 LCMS contract models          │ ✅ RepoIndexRequest, GraphSnapshot, GraphQuery, GraphContext │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ 全量测试无 GitNexus 依赖                       │ ✅ grep -r GitNexus legacy_pilot/ 无结果                     │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ 不修改生产文件（除 package exports）           │ ✅                                                           │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ 错误携带 source_module = "code_knowledge_core" │ ✅                                                           │
  ├────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ 适配器类型表面不暴露 GitNexus 对象             │ ✅                                                           │
  └────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

  三、Step 2 出口标准

  ┌───────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────┬──────┐
  │                       标准                        │                                           对应代码                                           │ 判定 │
  ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
  │ index_repo() 仅在 contract_version 校验后委托     │ router.py:46 → ensure_supported_contract_version() → 适配器                                  │ ✅   │
  ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
  │ query_graph() 仅在 trace_id + contract_version    │ router.py:56-57 → ensure_trace_id() → ensure_supported_contract_version() → 适配器           │ ✅   │
  │ 校验后委托                                        │                                                                                              │      │
  ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
  │ 其他结构方法未重构                                │ submit_alert, build_evidence_bundle, generate_rca, review_rca, find_similar_incidents,       │ ✅   │
  │                                                   │ save_incident 未修改                                                                         │      │
  ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
  │ 默认路由器返回相同 mock 数据                      │ TestDefaultRouterPreservesMockBehavior 2 个测试通过                                          │ ✅   │
  ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
  │ 契约门在适配器前拦截                              │ TestGateInterceptsBeforeAdapter 3 个测试，RecordingFakeAdapter 确认未调用                    │ ✅   │
  └───────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────┴──────┘

  四、中间件契约合规性（对照文档 2）

  5.1 contract_version 门

  index_repo:  ensure_supported_contract_version(request.contract_version)  ✅
  query_graph: ensure_supported_contract_version(query.contract_version)     ✅

  两个入口均在路由器层校验，适配器不重复校验 — 符合"契约门在 MiddlewareRouter 不在适配器"的原则。

  5.2 trace_id 门

  query_graph: ensure_trace_id(query.trace_id)  ✅

  query_graph 在 contract_version 之前先校验 trace_id，因为 trace_id 需要传递给 contract_version 校验的错误信息。

  5.3 confidence 范围

  所有模型通过 Pydantic Field(ge=0.0, le=1.0) 强制 — ✅

  5.4 evidence_refs 强制

  Edge.evidence_refs 通过 Pydantic min_length=1 强制 — ✅
  Mock adapter 所有 Edge 返回都带 evidence — ✅

  5.6 ContractError envelope

  适配器内部错误 CodeKnowledgeCoreError → 路由器转换为 ContractViolation(含 ContractError) — ✅

  _code_knowledge_core_error() 方法正确传递：
  - trace_id → ContractError.trace_id
  - error.message → ContractError.message
  - error.source_module → ContractError.source_module
  - error.recoverable → ContractError.recoverable

  6.1 Code Knowledge Core 输出约束

  ┌───────────────────────────────────────────────────────────────┬──────────────────────────┐
  │                             约束                              │           状态           │
  ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
  │ 必须输出 Node, Edge, GraphSnapshot, GraphContext, EvidenceRef │ ✅ 全部使用              │
  ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
  │ Edge 至少 1 个 evidence_ref                                   │ ✅ Pydantic min_length=1 │
  ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
  │ 不直接做 RCA 判断                                             │ ✅ 适配器只管图          │
  ├───────────────────────────────────────────────────────────────┼──────────────────────────┤
  │ LLM 语义边用 LLMSemanticResult                                │ N/A (Step 1-2 无 LLM)    │
  └───────────────────────────────────────────────────────────────┴──────────────────────────┘

  五、四结构架构合规性（对照文档 3）

  ┌────────────────────────────────────────────────────┬───────────────────────────────┐
  │                      架构要求                      │             状态              │
  ├────────────────────────────────────────────────────┼───────────────────────────────┤
  │ Code Knowledge Core 拥有 index_repo 和 query_graph │ ✅ 适配器接口只定义这两个方法 │
  ├────────────────────────────────────────────────────┼───────────────────────────────┤
  │ 核心输入 RepoIndexRequest                          │ ✅                            │
  ├────────────────────────────────────────────────────┼───────────────────────────────┤
  │ 核心输出 GraphSnapshot, GraphContext               │ ✅                            │
  ├────────────────────────────────────────────────────┼───────────────────────────────┤
  │ 结构间只共享 middleware contract，不共享内部对象   │ ✅ 适配器不暴露 GitNexus 类型 │
  ├────────────────────────────────────────────────────┼───────────────────────────────┤
  │ 契约门保留在中间件                                 │ ✅ 路由器层校验               │
  └────────────────────────────────────────────────────┴───────────────────────────────┘

  六、发现的问题

  Issue 1 — error_code 语义不精确 (低严重度)

  router.py:362：
  error_code=ErrorCode.VALIDATION_ERROR,

  CodeKnowledgeCoreError 转换时使用了 VALIDATION_ERROR，但这个错误码在中间件文档中定义为 "Request body failed contract validation"。适配器后端故障（如 GitNexus
  不可用）不是请求体校验失败。

  建议：在 enums.py 中新增 BACKEND_UNAVAILABLE 或 INTERNAL_ERROR 错误码，或至少在 Step 5（backend selection）时处理。当前不影响功能正确性，因为 source_module =
  "code_knowledge_core" 已经区分了错误来源，且 HTTP 状态码仍为 400(recoverable=true)。

  # 建议改为
  error_code=ErrorCode.VALIDATION_ERROR,  # 当前值 — 可工作但不精确
  # 或新增 ErrorCode.BACKEND_ERROR 用于 Step 5

  Issue 2 — 未使用的 import (极低严重度)

  router.py 的 Edge import 在 mock 逻辑移出后仅用于类型注解的间接引用。其余 imports 全部有效。

  七、测试覆盖矩阵

  ┌───────────────────────────────────────────────┬──────┬─────────────────────────────────────────────────────────────────────┐
  │                   测试类别                    │ 数量 │                                文件                                 │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ Step 1 接口签名                               │ 3    │ test_code_knowledge_core_adapter.py                                 │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ Step 1 错误模型                               │ 6    │ test_code_knowledge_core_adapter.py                                 │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ Mock 适配器保持原始行为                       │ 2    │ test_code_knowledge_core_adapter.py                                 │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ Gate 在适配器前拦截                           │ 5    │ test_code_knowledge_core_adapter.py(2) + test_router_pipeline.py(3) │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ 默认路由器保持 mock                           │ 2    │ test_router_pipeline.py                                             │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ CodeKnowledgeCoreError→ContractViolation 转换 │ 2    │ test_router_pipeline.py                                             │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ 原有测试（契约/路由器/API）                   │ 22   │ test_contract_models.py, test_router_pipeline.py, test_api.py       │
  ├───────────────────────────────────────────────┼──────┼─────────────────────────────────────────────────────────────────────┤
  │ 总计                                          │ 42   │                                                                     │
  └───────────────────────────────────────────────┴──────┴─────────────────────────────────────────────────────────────────────┘

  八、总评

  判定：通过。 代码实现对三份架构文档完全合规。1 个低严重度建议（error_code 语义），不影响接口契约和功能正确性，可在 Step 5（backend selection）时顺带修正。





## 下一步 (Step 3)

按计划 Step 3 实施 `gitnexus_mapper.py` — 纯映射函数，将 GitNexus 归一化载荷转换为 LCMS Pydantic 模型（`Node`, `Edge`, `GraphSnapshot`, `GraphContext`），无子进程、无环境变量、无路由器注入。
