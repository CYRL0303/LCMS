# Structure 1 (Code Knowledge Core) - Step 3 实现记录

## 结论

Step 3 功能性已达到当前 implementation plan 的预期。

本步骤只实现 GitNexus normalized payload 到 LCMS contract models 的纯映射层，不包含 GitNexus CLI 调用、环境变量读取、router 注入、backend selection 或真实集成测试。

## 本次新增文件

```text
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_gitnexus_mapper.py
```

没有修改 `MiddlewareRouter`、FastAPI app、adapter factory 或 GitNexus client。

## Mapper 对外入口

`gitnexus_mapper.py` 暴露 4 个纯函数：

```python
map_gitnexus_node(payload, graph_id, repo_id, trace_id, now=None) -> Node
map_gitnexus_edge(payload, graph_id, trace_id, nodes_by_id, now=None) -> Edge | None
map_index_payload(payload, now=None) -> GraphSnapshot
map_query_payload(payload, query, now=None) -> GraphContext
```

后续 Step 4 的 `gitnexus_client.py` 可以把 CLI stdout normalization 后的 dict 直接传给这些函数。

## 已实现的契约规则

- `GraphNode-like dict -> Node`
- `GraphRelationship-like dict -> Edge`
- `index payload -> GraphSnapshot`
- `query payload -> GraphContext`
- `node_id` 使用 GitNexus `id`
- `qualified_name` 优先使用 `properties.qualifiedName`，否则使用 `file_path::name`，否则为 `None`
- GitNexus 细节放入 `metadata["gitnexus"]`
- 节点存在 source location 时生成 `EvidenceRef`
- `created_at` 使用注入 clock；未注入时使用 `datetime.now(UTC)`
- Edge 一定返回至少一个 `EvidenceRef`
- Edge evidence 的 `source_type` 固定为 `code`，没有 `document` fallback
- Edge confidence clamp 到 `0.0-1.0`
- evidence id 使用 deterministic hash：

```text
EV-GN-{sha256(trace_id, source_id, file_path, start_line, end_line).hexdigest()[:12]}
```

- `GraphSnapshot.evidence_refs` 和 `GraphContext.evidence_refs` 按 `evidence_id` 去重
- `GraphContext.trace_id` 使用输入 `GraphQuery.trace_id`
- query payload 标记 `not_found=True` 时返回空 `GraphContext`，`confidence=0.0`
- `GraphContext.confidence` 在有边时使用 `min(average edge confidence, max edge evidence confidence)`

## 无越界行为

Step 3 mapper 中没有：

- `subprocess`
- `os.environ` / `getenv`
- FastAPI import
- `MiddlewareRouter` import
- mock fallback
- GitNexus runtime dependency
- RCA / incident memory 逻辑
- `GraphContext.metadata` 或 `GraphContext.missing_evidence` 扩展字段

这保持了 middleware contract 文档要求的边界：结构之间只共享 LCMS contract objects。

## 测试覆盖

`tests/test_gitnexus_mapper.py` 覆盖：

- qualifiedName 映射
- `file_path::name` fallback
- injected clock
- deterministic evidence id
- edge gitnexus metadata
- source node 无 location 时使用 target node location
- source/target 都无 location 时生成低置信度 code evidence
- graph-level evidence 去重
- query trace_id 继承
- query confidence 计算
- `not_found` 空结果

## 验证结果

已运行：

```powershell
python -m pytest tests/test_gitnexus_mapper.py tests/test_contract_models.py -q
python -m pytest -q
python -m compileall legacy_pilot
git diff --check
```

结果：

```text
17 passed
52 passed, 1 existing FastAPI/TestClient deprecation warning
compileall passed
git diff --check clean
```

## 给后续开发的接口说明

Step 4 应负责：

- 执行 `gitnexus_cli`
- 处理 timeout / executable missing / non-zero exit / invalid JSON
- 把 GitNexus raw stdout normalize 成 Step 3 mapper 接受的 dict shape
- 不直接创建 LCMS Pydantic response model

Step 5 应负责：

- adapter injection
- backend selection
- `gitnexus_cli` adapter 调用 Step 4 client 和 Step 3 mapper
- 保持默认 mock backend
- 真实 backend 失败时不得 silent fallback 到 mock

如果 GitNexus 输出中包含大字段、内部诊断或敏感字段，建议在 Step 4 normalization 阶段先做 allowlist，再交给 mapper。
