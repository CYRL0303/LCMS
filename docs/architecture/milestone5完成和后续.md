# Milestone5 结构1实现程度

## 总体状态

Milestone5 当前达到的是 Java/Spring/MyBatis 生产链路可用级覆盖。

真实链路形态：

```text
RepoIndexRequest
-> Middleware contract gate
-> CodeKnowledgeCoreAdapter
-> GitNexus CLI
-> GitNexus payload normalization
-> Structure1 enrichment
-> LCMS GraphSnapshot / GraphContext
```

已验证结果：

- 默认测试：141 passed, 6 skipped
- 真实 GitNexus opt-in：12 passed
- 真实 Qwen semantic opt-in：1 passed
- middleware/router 四结构契约边界未改变

## 已覆盖的真实链路能力

| 范围 | 当前能力 | 实现来源 | 状态 |
| --- | --- | --- | --- |
| Java 文件/类/方法 | 方法节点、文件节点、调用关系、上下文查询 | GitNexus CLI + mapper | 已覆盖 |
| Spring Controller 路由 | `/api/...` endpoint 到 controller method | GitNexus route/process 输出 + adapter 桥接 | 已覆盖 |
| Controller -> Service -> Mapper | 后端调用链 | GitNexus CLI | 已覆盖 |
| MyBatis Mapper XML | mapper XML statement 节点 | enrichment extractor | 已覆盖 |
| SQL statement | `select/insert/update/delete` statement 节点 | enrichment extractor | 已覆盖 |
| SQL table | `READS_TABLE` / `WRITES_TABLE` 到 table 节点 | enrichment regex | 已覆盖 |
| Spring config | `application.yml/yaml/properties` config key 节点 | enrichment extractor | 已覆盖 |
| Java exception | exception class、throw、handler 关系 | enrichment extractor | 已覆盖 |
| Semantic summary | 方法语义摘要节点 | Qwen API 或 mock semantic backend | opt-in 已覆盖 |
| Query context | endpoint/method/sql/config/exception/keyword 查询 | LocalGraphIndex + query planner | 已覆盖 |

## Java / MyBatis / XML / SQL 细节

Java 当前是主支持语言。真实 GitNexus 提供基础代码图，结构1 adapter 负责把 GitNexus 输出转成 LCMS 契约模型，并补齐结构1生产链路需要的证据和元数据。

MyBatis XML 是通过结构1 enrichment 补的，不是 GitNexus 当前原生稳定输出。支持：

- `<mapper namespace="...">`
- `<select>` / `<insert>` / `<update>` / `<delete>`
- mapper method -> SQL statement：`EXECUTES_SQL`
- SQL statement -> table：`READS_TABLE` / `WRITES_TABLE`
- `source_type="sql"` evidence

边界：

- 动态 SQL 只做文本合并和 regex 表名抽取，不是完整 SQL AST。
- `include`、`sql fragment`、`resultMap`、`provider annotation` 这类复杂 MyBatis 语义还不是强覆盖。
- 方言级 SQL、复杂 CTE、schema/alias/子查询列级血缘未实现。

## 非 Java 语言能力

| 类型 | 当前状态 | 说明 |
| --- | --- | --- |
| Python | 未生产覆盖 | adapter 可接 GitNexus 通用节点，但没有 Python AST/route/call extractor 和验收 fixture |
| C++ | 未生产覆盖 | 没有 C++ 函数/类/调用链 extractor，也没有 compile_commands 语义接入 |
| HTML | 未生产覆盖 | 不解析 DOM/template/component 关系 |
| CSS | 未生产覆盖 | 不解析 selector/style/import/asset 关系 |
| JavaScript/TypeScript | 未生产覆盖 | 没有前端 route/component/API call extractor |
| 通用 XML | 部分覆盖 | 只覆盖 MyBatis mapper XML，不覆盖任意 XML schema |
| YAML/properties | 部分覆盖 | 只覆盖 Spring `application.yml/yaml/properties` 配置节点 |

非 Java 文件不会必然导致失败，但当前不承诺解析质量。只有 GitNexus 恰好输出通用节点时，mapper 才能归一化接收；结构1没有针对这些语言的生产级测试。

## 能力边界

当前 Milestone5 不是全语言代码知识图谱，而是结构1 Java 生产链路闭环。

主要边界：

- 不做完整跨语言调用图。
- 不做 C++/Python/前端专用 AST。
- 不做完整 SQL parser，只做 MyBatis SQL 文本和表名抽取。
- 不做 trace/impact 全能力封装，只做当前结构1 query context。
- semantic enrichment 只是辅助摘要，不作为可信结构事实。
- GitNexus raw payload 不暴露给 middleware 或其他三结构。

## 留出的开发接口

可以继续扩展的位置：

- `legacy_pilot/code_knowledge_core/extractors/`
  新增 `python_*`、`cpp_*`、`frontend_*` extractor。
- `legacy_pilot/code_knowledge_core/adapter.py`
  在 `_default_structure1_enrichers()` 中挂新 extractor，继续走统一 merge + mapper。
- `legacy_pilot/code_knowledge_core/gitnexus_client.py`
  扩展 GitNexus CLI normalization，比如 trace/impact/http API、新语言输出格式。
- `legacy_pilot/code_knowledge_core/local_graph_index.py`
  扩展本地 query context 能力。
- `legacy_pilot/code_knowledge_core/query_planner.py`
  增加 Python route、C++ symbol、frontend component/API call 等 query kind。
- `legacy_pilot/code_knowledge_core/gitnexus_mapper.py`
  继续保持唯一出口：把任何 GitNexus/enrichment payload 映射成 LCMS `Node`、`Edge`、`EvidenceRef`。
- `tests/fixtures/`
  新增 `python_fastapi_demo`、`cpp_service_demo`、`frontend_demo` 这类 production fixture，作为新语言验收入口。

## 结论

Milestone5 当前实现程度是：Java/Spring/MyBatis 结构1生产闭环已实现并验证；Python、C++、HTML、CSS 目前只是可扩展方向，不属于已证明能力。

下一阶段如果要扩语言，建议按 fixture 驱动：

1. Python：FastAPI/Flask route -> service/function -> SQL/HTTP。
2. C++：class/function -> call graph -> config/runtime dependency。
3. 前端：route/component -> API call -> backend endpoint 对齐。
