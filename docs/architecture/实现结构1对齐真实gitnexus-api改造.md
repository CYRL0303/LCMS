# 实现结构1对齐真实 GitNexus API 改造

## 结论

当前结构 1 已经和真实 `gitnexus_cli` 跑通闭环。

闭环路径是：

```text
Java/Spring repo
-> gitnexus_cli analyze 建索引
-> gitnexus_cli cypher/context 读取真实图和调用上下文
-> GitNexus adapter 归一化输出
-> LCMS mapper 转成 GraphSnapshot / GraphContext / EvidenceRef
-> Interface Contract Middleware 暴露 /v1/repos/index 和 /v1/graph/query
```

这不是 mock backend，也不是假 JSON。真实集成测试已经调用本地 GitNexus CLI，并验证 Java/Spring fixture 的 controller -> service -> mapper 调用链能进入 LCMS 图上下文。

## 实现了什么

本次改造主要完成四件事：

1. `GitNexusCliClient.index_repo()` 改为真实 CLI 建索引。

```text
gitnexus analyze <repo_path> --skip-git --index-only --name <repo_id>
gitnexus cypher "MATCH (n)-[r]->(m) RETURN n.id, r.type, r.confidence, r.reason, m.id LIMIT <N>" -r <repo_id>
```

`analyze` 负责生成 GitNexus 索引，`cypher` 负责从真实索引里抽取节点和边，再交给 mapper 生成 `GraphSnapshot`。

2. `GitNexusCliClient.query_graph()` 改为真实上下文查询。

对方法查询，例如：

```text
DatasetService.getVersion
```

adapter 先用 `cypher` 找 GitNexus UID，再用：

```text
gitnexus context --uid <uid> -r <repo_id> --content
```

读取 incoming/outgoing calls，最后映射成 `GraphContext`。

对 route 查询，例如：

```text
/api/dataset/version
```

adapter 先用 `cypher` 在文件内容里找 route 所在 controller，再推导 controller method，例如 `DatasetController.getVersion`，然后进入同一条 `context --uid` 查询链路。

3. 增加 Java/Spring fixture。

fixture 覆盖：

```text
DatasetController.getVersion
-> DatasetService.getVersion
-> DatasetMapper.selectVersionById
```

它用于验证结构 1 最小 Java/Spring 闭环，不包含 MyBatis XML 或 SQL table。

4. 增加 opt-in 真实集成测试。

默认测试不要求本机安装 GitNexus。只有显式设置环境变量后，才会跑真实 `gitnexus_cli`。

## 真实 GitNexus CLI 的结构和契约

当前对接到的真实 GitNexus 不是一个稳定 HTTP JSON API，而是 CLI 命令面。实际可用契约如下。

### analyze

用途：对 repo 建 GitNexus 索引。

调用形态：

```text
gitnexus analyze <repo_path> --skip-git --index-only --name <repo_id>
```

输出特点：

```text
stdout 是文本状态，不是结构化 GraphSnapshot JSON。
GitNexus 会在被分析 repo 内生成 .gitnexus 索引。
```

adapter 处理方式：

```text
只判断退出码。
成功后再调用 cypher 读取图数据。
失败时转成 Code Knowledge Core recoverable error。
```

### cypher

用途：从 GitNexus 索引读取节点、边或 UID。

调用形态：

```text
gitnexus cypher "<query>" -r <repo_id>
```

真实输出特点：

```json
{
  "markdown": "| n.id | r.type | r.confidence | r.reason | m.id |\n| --- | --- | --- | --- | --- |\n..."
}
```

也就是说，CLI 返回的是 JSON wrapper，但核心结果在 `markdown` 表格里。adapter 需要解析 markdown table，而不能假设 GitNexus 直接返回标准 nodes/edges JSON。

当前使用的 cypher 查询包括：

```text
MATCH (n)-[r]->(m)
RETURN n.id, r.type, r.confidence, r.reason, m.id
LIMIT <max_edges>
```

以及：

```text
MATCH (n)
WHERE n.id CONTAINS '<symbol>'
RETURN n.id, n.name, n.filePath, n.startLine, n.endLine
LIMIT 10
```

route 查询还会使用：

```text
MATCH (n)
WHERE n.content CONTAINS '<route>'
RETURN n.id, n.name, n.filePath
LIMIT 5
```

### context

用途：给定 GitNexus UID，读取某个符号的调用上下文。

调用形态：

```text
gitnexus context --uid <uid> -r <repo_id> --content
```

真实输出结构：

```text
status
symbol.uid/name/kind/filePath/startLine/endLine/content
incoming.calls[]
outgoing.calls[]
```

adapter 处理方式：

```text
symbol -> center Node
incoming.calls[] -> caller nodes + CALLS edge caller -> center
outgoing.calls[] -> callee nodes + CALLS edge center -> callee
incoming + center + outgoing -> graph_paths
```

### query / trace / impact

真实 GitNexus CLI 里存在这些能力，但当前结构 1 首版闭环没有把它们作为主路径：

```text
query: 关键词/BM25 查询。当前本地 GitNexus 在 FTS extension 缺失时会降级，不适合作为结构 1 验收主路径。
trace: 可以做 from UID 到 to UID 路径查询，已人工验证可用，但当前 GraphQuery 首版用 context 形成调用路径。
impact: 可作为后续 upstream/downstream 影响面扩展。
```

## 如何和结构 1 对接

结构 1 对外只暴露中间件契约，不暴露 GitNexus 内部对象。

### IndexRepo 对接

中间件入口：

```text
POST /v1/repos/index
RepoIndexRequest -> GraphSnapshot
```

内部链路：

```text
MiddlewareRouter.index_repo()
-> CodeKnowledgeCoreAdapter.index_repo()
-> GitNexusCliClient.index_repo()
-> gitnexus analyze
-> gitnexus cypher
-> GitNexus mapper
-> GraphSnapshot
```

GitNexus 输出被归一化成 mapper-ready payload：

```text
repo_id
graph_id
trace_id
nodes[]
relationships[]
```

mapper 再生成 LCMS：

```text
Node
Edge
EvidenceRef
GraphSnapshot
```

### QueryGraph 对接

中间件入口：

```text
POST /v1/graph/query
GraphQuery -> GraphContext
```

内部链路：

```text
MiddlewareRouter.query_graph()
-> CodeKnowledgeCoreAdapter.query_graph()
-> GitNexusCliClient.query_graph()
-> gitnexus cypher 解析 route/symbol 到 UID
-> gitnexus context --uid
-> GitNexus mapper
-> GraphContext
```

GitNexus 输出被归一化成：

```text
graph_id
nodes[]
relationships[]
paths[]
not_found
```

mapper 再生成：

```text
GraphContext.trace_id = GraphQuery.trace_id
matched_nodes
matched_edges
graph_paths
evidence_refs
confidence
```

## 如何符合中间件契约

改造后仍然遵守第二个中间件文档的边界：

```text
MiddlewareRouter 负责 contract_version gate。
MiddlewareRouter 负责 GraphQuery.trace_id gate。
Code Knowledge Core adapter 只接受 RepoIndexRequest / GraphQuery。
adapter 不把 GitNexus 原始对象直接暴露给其他结构。
所有成功响应都必须是 LCMS Pydantic contract。
所有 GitNexus 运行错误都转成 Code Knowledge Core error，再由中间件包装成 ContractError envelope。
```

错误处理也保持契约边界：

```text
GitNexus CLI 不存在 -> recoverable CodeKnowledgeCoreError
GitNexus CLI 超时 -> recoverable CodeKnowledgeCoreError
GitNexus 非 0 退出 -> recoverable CodeKnowledgeCoreError
GitNexus stdout 不是 JSON -> recoverable CodeKnowledgeCoreError
not_found 查询 -> 空 GraphContext，confidence = 0.0
```

## 与结构 1 文档的对齐范围

已经完成的结构 1 首版范围：

```text
Java/Spring Controller
Java/Spring Service
Java Mapper interface
方法级 CALLS 关系
route 查询到 controller context
symbol 查询到 service context
GraphSnapshot 生成
GraphContext 生成
EvidenceRef 生成
trace_id 沿用
mock 模式和真实 GitNexus 模式并存
真实 GitNexus 模式不静默回退 mock
```

当前验证过的示例链路：

```text
/api/dataset/version
-> DatasetController.getVersion
-> DatasetService.getVersion
-> DatasetMapper.selectVersionById
```

这满足结构 1 首版验收里的 route/controller/service 图查询闭环。

## 测试情况

### 单元测试

已覆盖：

```text
GitNexus analyze 命令形态
analyze 后继续 cypher 抽图
cypher markdown table 解析
symbol query -> UID lookup -> context
route query -> controller file -> controller method -> context
not_found 查询
timeout / binary missing / non-zero exit / invalid JSON 错误转换
环境变量和构造参数覆盖
UTF-8 subprocess decoding
```

结果：

```text
python -m pytest tests/test_gitnexus_client.py -q
11 passed
```

### Mapper 测试

已覆盖：

```text
GitNexus-like node -> LCMS Node
GitNexus-like relationship -> LCMS Edge
source location -> EvidenceRef
edge evidence_refs
confidence 归一化
GraphSnapshot / GraphContext contract 输出
```

结果：

```text
python -m pytest tests/test_gitnexus_mapper.py -q
10 passed
```

### 默认测试套件

结果：

```text
python -m pytest -q
77 passed, 3 skipped, 1 warning
```

说明：

```text
3 skipped 是 opt-in GitNexus 集成测试默认跳过。
1 warning 是已有 FastAPI/Starlette TestClient deprecation，不是结构 1 功能失败。
```

### 真实 GitNexus 集成测试

运行环境：

```text
LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION=1
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
GITNEXUS_BIN=Q:\tmp\gitnexus-local.cmd
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus
GITNEXUS_TIMEOUT_SECONDS=120
```

本地验证时使用的真实 GitNexus 路径：

```text
GitNexus package / subprocess cwd:
Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus

GitNexus CLI JS entry:
Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus\dist\cli\index.js

LegacyPilot 测试调用的 wrapper:
Q:\tmp\gitnexus-local.cmd
```

`Q:\tmp\gitnexus-local.cmd` 只是测试用包装脚本，实际执行的是上面的 `dist\cli\index.js`。

结果：

```text
python -m pytest tests/test_gitnexus_integration.py -q -rs
5 passed, 2 warnings
```

真实集成测试覆盖：

```text
fixture 结构检查
IndexRepo against Java/Spring fixture -> non-empty GraphSnapshot
QueryGraph("DatasetService.getVersion") -> GraphContext
QueryGraph("/api/dataset/version") -> route/controller context
GraphContext.trace_id == GraphQuery.trace_id
returned edges have EvidenceRef
```

2 个 warning 是提权运行时 pytest cache 写入权限警告，不是 GitNexus 功能失败。

## 是否完全覆盖

按结构 1 首版验收口径：可以认为已覆盖并跑通。

也就是说，下面这些已经覆盖：

```text
真实 GitNexus CLI 建索引
真实 GitNexus CLI 查询上下文
Java/Spring route/controller/service/mapper 最小链路
GitNexus 输出到 LCMS GraphSnapshot / GraphContext 的映射
中间件 contract_version / trace_id / error envelope 边界
默认 mock 模式和 opt-in 真实模式
```

但如果按“完整 GitNexus API 能力”或“完整 Java/Spring 生产项目能力”来定义，则还没有完全覆盖。

未覆盖或只做了预留的范围：

```text
GitNexus HTTP server API
TypeScript thin bridge
GitNexus query 命令作为主查询路径
GitNexus trace 命令接入 GraphQuery from/to 查询
GitNexus impact 命令接入 upstream/downstream 影响面
MyBatis XML
SQL table / SQL statement graph
多模块 Spring Boot 项目
复杂 route annotation 组合
大仓库性能和分页
索引陈旧检测
ambiguous query 的用户澄清协议
CI 环境自动安装和构建 GitNexus
```

所以准确结论是：

```text
结构 1 首版闭环：完成。
真实 gitnexus_cli 对接：完成。
Java/Spring 最小验收链路：完成。
完整 GitNexus 全 API 封装：未完成，也不是当前结构 1 首版目标。
完整生产级 Java/Spring 覆盖：未完成，需要后续扩展 trace/impact/MyBatis/SQL/多模块场景。
```

## 后续建议

下一步如果继续扩展，建议顺序是：

1. 接入 `gitnexus trace`，让 `GraphQuery` 支持明确 from/to UID 的路径查询。
2. 接入 `gitnexus impact`，支持 upstream/downstream 影响面。
3. 扩展 fixture 到 MyBatis XML 和 SQL table。
4. 给真实 GitNexus 集成测试增加 CI profile，但仍保持默认单元测试不依赖 GitNexus。
5. 如果 CLI markdown table 契约不稳定，再增加 TypeScript thin bridge 输出稳定 JSON。
