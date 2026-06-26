# Structure1 PostgreSQL Persistence to Structure2 Real E2E Verification

## 验证目标

本次验证证明以下真实链路可以闭环：

```text
GitNexus real index_repo
-> Structure1 GraphSnapshot
-> PostgreSQL graph payload persistence
-> fresh Structure1 adapter restores payload from PostgreSQL
-> MiddlewareRouter.query_graph()
-> Structure2 graph_context backend
-> EvidenceBundle
-> GenerateRCA
-> ReviewRCA
-> SaveIncident
```

关键边界仍然成立：

- Structure1 负责 GitNexus、graph enrichment、PostgreSQL graph payload。
- Middleware 是跨结构唯一入口，负责 contract gate、trace、version、error envelope。
- Structure2 只通过 `MiddlewareRouter.query_graph()` 消费 `GraphContext`。
- Structure2 不直连 PostgreSQL graph store。
- Structure2 不读取 GitNexus raw payload。
- Structure2 不生成 RCA 结论。

## 验证结果

真实 GitNexus + Structure1 生产 fixture：

```text
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -vv -x -rs
12 passed, 2 pytest cache warnings
```

真实 PostgreSQL graph store：

```text
python -m pytest tests/test_postgres_graph_store_integration.py -q -rs
1 passed
```

一条龙脚本 sentinel：

```text
E2E_REAL_GITNEXUS_POSTGRES_STRUCTURE2_PASS
```

PostgreSQL row 证据：

```text
repo_id: repo-java-spring-production-demo-bc1b619a
graph_id: GRAPH-repo-java-spring-production-demo-bc1b619a
parser_version: gitnexus_cli+structure1_sql_config_exception_v1
nodes: 38
edges: 52
```

Structure2 输出证据：

```text
query: TRACE-ALERT-PG-GITNEXUS-E2E
bundle: 4 matched_nodes, 1 graph_path, 6 code_evidence
record: INC-ALERT-PG-GITNEXUS-E2E, confirmed_by_user=True, 6 evidence_refs
```

## 验证前环境准备

### Python 依赖

真实 PostgreSQL graph store 需要 `psycopg`：

```powershell
python -m pip install "psycopg[binary]"
```

这是后续产品运行也需要的依赖，除非产品换成别的 PostgreSQL driver。

### GitNexus runtime

本次验证使用本机 GitNexus checkout：

```powershell
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_INDEX_TIMEOUT_SECONDS='120'
$env:GITNEXUS_QUERY_TIMEOUT_SECONDS='30'
```

`Q:\tmp\gitnexus-local.cmd` 内容：

```bat
@echo off
node "Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus\dist\cli\index.js" %*
```

注意：`Q:\tmp\gitnexus-local.cmd` 和 `Q:\Hackathons\GitNexus-main\...` 是本机验证路径，不是产品路径。产品环境需要稳定发布的 GitNexus CLI/runtime 路径，或等价的 Structure1 backend。

### PostgreSQL

本次验证使用 Docker Desktop 临时 PostgreSQL：

```powershell
docker run --name legacy-pilot-pg-e2e `
  -e POSTGRES_USER=legacy_pilot `
  -e POSTGRES_PASSWORD=legacy_pilot `
  -e POSTGRES_DB=legacy_pilot `
  -p 55432:5432 `
  -d postgres:16-alpine
```

等待 ready：

```powershell
docker exec legacy-pilot-pg-e2e pg_isready -U legacy_pilot -d legacy_pilot
```

环境变量：

```powershell
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_GRAPH_STORE_TABLE='legacy_pilot_graph_payloads_e2e_full'
```

清理临时容器：

```powershell
docker rm -f legacy-pilot-pg-e2e
```

注意：Docker 容器、端口 `55432`、表名 `legacy_pilot_graph_payloads_e2e_full` 都是本次验证专用。产品环境需要真实 PostgreSQL 服务、正式 DSN、正式表名、权限和迁移策略。

### Structure1 和 Structure2 backend

真实链路需要同时启用：

```powershell
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
```

含义：

- `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli`：Structure1 使用真实 GitNexus CLI。
- `LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql`：Structure1 `IndexRepo` 保存 graph payload，`QueryGraph` 在无进程内 index 时可恢复。
- `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context`：Structure2 通过中间件内部 `QueryGraph` 消费 `GraphContext`。

## 真实验证步骤

### 1. 验证 PostgreSQL graph store

```powershell
$env:LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE='1'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_GRAPH_STORE_TEST_TABLE='legacy_pilot_graph_payloads_e2e_probe'
python -m pytest tests/test_postgres_graph_store_integration.py -q -rs
```

预期：

```text
1 passed
```

### 2. 验证真实 GitNexus + Structure1

```powershell
$env:LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION='1'
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_INDEX_TIMEOUT_SECONDS='120'
$env:GITNEXUS_QUERY_TIMEOUT_SECONDS='30'
python -m pytest tests/test_gitnexus_integration.py tests/test_structure1_production_fixture.py -vv -x -rs
```

预期：

```text
12 passed
```

如果出现类似错误：

```text
EPERM: operation not permitted, open 'C:\Users\Administrator\.gitnexus\registry.json.tmp'
```

说明 GitNexus runtime 需要写用户目录，但当前 shell/sandbox 权限不足。解决方式是调整目录权限、改变 GitNexus registry/cache 位置，或在受控环境中提权运行。

### 3. 验证一条龙恢复和 Structure2 调用

本次脚本执行的关键动作：

1. 使用真实 `GitNexusCliCodeKnowledgeCoreAdapter.index_repo()` 生成 `GraphSnapshot`。
2. 由 `PostgresGraphStore.save_payload()` 写入 PostgreSQL。
3. 创建 fresh `GitNexusCliCodeKnowledgeCoreAdapter`，不保留进程内 `LocalGraphIndex`。
4. 给 fresh adapter 注入 `QueryForbiddenClient`，如果 fallback 到 GitNexus query 会直接失败。
5. 创建 `MiddlewareRouter(code_knowledge_core_adapter=restore_adapter)`。
6. 使用 Structure2 `graph_context` backend 提交 `AlertEvent`。
7. `build_evidence_bundle()` 通过 `MiddlewareRouter.query_graph()` 触发 PostgreSQL restore。
8. 后续执行 mock RCA/review/save，证明证据包可进入闭环。

核心断言：

```text
snapshot.nodes and snapshot.edges
SQL/Table/Config/Exception nodes exist
EXECUTES_SQL/READS_TABLE/THROWS_EXCEPTION edges exist
query.graph_id == snapshot.graph_id
bundle.trace_id == query.trace_id
bundle.contract_version == query.contract_version
bundle.matched_nodes
bundle.graph_paths
bundle.code_evidence
not bundle.missing_evidence
record.confirmed_by_user is True
record.evidence_refs
```

成功输出：

```text
E2E_REAL_GITNEXUS_POSTGRES_STRUCTURE2_PASS
```

### 4. 确认 PostgreSQL row

```powershell
docker exec legacy-pilot-pg-e2e psql -U legacy_pilot -d legacy_pilot -c "SELECT repo_id, graph_id, parser_version, jsonb_array_length(payload_json->'nodes') AS nodes, jsonb_array_length(payload_json->'relationships') AS edges FROM legacy_pilot_graph_payloads_e2e_full;"
```

预期：

```text
repo-java-spring-production-demo-bc1b619a | GRAPH-repo-java-spring-production-demo-bc1b619a | gitnexus_cli+structure1_sql_config_exception_v1 | 38 | 52
```

## 后续完整产品也需要保留的能力

### GitNexus 或等价 Structure1 backend

产品需要稳定的 Structure1 graph 生成 backend：

- 可运行的 GitNexus CLI/runtime，或等价服务化 backend。
- 可配置的 runtime 路径，而不是本机 `Q:\tmp` wrapper。
- 可写索引/cache/registry 目录。
- index/query timeout 配置。
- 失败时必须变成 recoverable Code Knowledge Core error，再由 Middleware 包成 `ContractError`。

### PostgreSQL graph store

产品需要真实 PostgreSQL graph payload 持久化：

- 正式 DSN 和凭据管理。
- 表名配置或迁移工具。
- 最小权限账号。
- schema migration / table creation 策略。
- 备份、清理、容量和 retention 策略。
- repo_id + graph_id 的 latest payload 语义。
- 明确是否需要历史 graph version；当前实现只承诺 latest payload restore。

### Middleware contract boundary

产品必须保留：

- `IndexRepo -> GraphSnapshot`
- `QueryGraph -> GraphContext`
- `SubmitAlert -> IncidentQuery`
- `BuildEvidenceBundle -> EvidenceBundle`
- `contract_version` gate
- `trace_id` gate
- `ContractError` envelope
- evidence-backed downstream requirement

Structure2、RCA、Memory 不应共享 Structure1 内部 PostgreSQL 连接或 GitNexus raw payload。

### Structure2 graph_context backend

产品需要保留：

- `LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context`
- `AlertEvent.graph_id` / `IncidentQuery.graph_id` 可选字段
- 缺省 `graph_id` fallback：`GRAPH-{repo_id}`
- `BuildEvidenceBundle` 只消费 `GraphContext`
- EvidenceBundle 分区：code/sql/config/log
- `missing_evidence` 标记缺失上下文
- similar incidents 仍通过中间件/Structure4 contract

## 端到端验证依赖的产品化处置清单

### 一定需要保留到产品里的东西

这些是产品能力的一部分，不是一次性验证脚手架：

- Structure1 真实 graph 生成能力：GitNexus CLI/runtime，或等价的服务化 Code Knowledge Core backend。
- Structure1 graph enrichment 产物：`GraphSnapshot` 中的 code/sql/config/log/exception/table 节点和关系。
- PostgreSQL graph payload 持久化能力：`IndexRepo` 写入，`QueryGraph` 可从持久化 payload 恢复。
- Middleware contract boundary：所有跨结构调用继续走 `MiddlewareRouter` 和契约模型。
- Structure2 `graph_context` backend：只消费 `GraphContext`，不直连 Structure1 内部实现。
- `graph_id` 贯穿：`AlertEvent.graph_id`、`IncidentQuery.graph_id`、`GraphQuery.graph_id`、`GraphContext.graph_id`。
- `contract_version`、`trace_id`、错误 envelope、evidence refs 这些接口契约字段。
- 正式配置入口：backend 选择、GitNexus runtime、PostgreSQL DSN、表名、timeout 都必须可配置。
- 凭据和密钥管理：真实 DSN、密码、token 必须走 secret/env，不能写死在代码和文档示例之外。
- 可重复的端到端验证：保留为 opt-in 自动化测试，用环境变量显式打开。

### 一定要删掉或替换的东西

这些只能存在于本机验证过程，不能进入完整产品部署假设：

- 删掉对 `Q:\tmp\gitnexus-local.cmd` 的产品依赖；产品要用正式 GitNexus release、容器、sidecar 或服务地址。
- 删掉对 `Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus` 的产品依赖；产品不能依赖开发机 checkout 路径。
- 删掉对 Docker Desktop 的产品依赖；产品连接正式 PostgreSQL，Docker 只可用于本地/dev/test。
- 删掉固定端口 `127.0.0.1:55432`；产品 DSN 由环境或 secret 注入。
- 删掉测试表 `legacy_pilot_graph_payloads_e2e_full` 的产品语义；产品使用正式迁移管理的表名。
- 删掉明文 demo 密码作为产品配置；示例可以保留占位符，真实部署必须用 secret。
- 删掉内联 Python 一条龙脚本作为唯一验证方式；它要转成仓库内 opt-in pytest。
- 删掉本机提权运行作为前提；产品运行账号要有明确、最小、可审计权限。
- 删掉对 pytest cache warning 的接受标准；warning 可以记录，但不能当成产品健康信号。

### 临时验证项要怎么产品化

- `psycopg[binary]`：加入项目依赖或 PostgreSQL optional extra，不能只靠手动 `pip install`。
- 临时 PostgreSQL 容器：沉淀成 `docker-compose.e2e.yml` 或 CI service，用于开发/CI 验证，不用于生产。
- GitNexus wrapper：替换成正式 runtime 发现机制，例如 `GITNEXUS_BIN` 指向发布包，或 Structure1 调用 GitNexus 服务 API。
- 本机 GitNexus cache/registry：改成可配置目录，并在部署文档写明读写权限。
- 一条龙脚本：转成 `tests/test_real_structure1_structure2_e2e.py`，默认 skip，只有 `LEGACY_PILOT_RUN_REAL_E2E=1` 时执行。
- 测试表：测试中使用专用表名或测试 database/schema，执行后清理，避免污染产品数据。
- 环境变量：补 `.env.example` 和部署文档，区分 dev/test/prod。
- 数据库表：补迁移/init 策略，明确 schema、索引、唯一键、latest graph 语义和历史版本策略。
- PostgreSQL 启动检查：CI/dev 可以用 `pg_isready`；产品应接入健康检查和重试策略。

### 其他必须写清楚的边界

- Structure2 已实现的是 incident context / evidence bundle，不是 Structure3 RCA 推理。
- 当前 `GenerateRCA` / `ReviewRCA` 仍是 deterministic/mock 闭环，不代表真实 RCA 产品完成。
- 当前 `SaveIncident` 仍不是 Structure4 真实 incident memory persistence。
- PostgreSQL restore miss 现在允许 fallback 到 GitNexus query；产品要决定这是允许的降级路径，还是必须返回可恢复错误。
- 如果允许 fallback，日志和 trace 必须能区分 `postgres_restore_hit`、`postgres_restore_miss`、`gitnexus_fallback_hit`。
- 如果不允许 fallback，`QueryGraph` 必须在 restore miss 时返回明确 `ContractError`。
- E2E 验证必须继续证明 Structure2 不读取 PostgreSQL、不读取 GitNexus raw payload，只通过 middleware 拿 `GraphContext`。
- GitNexus 写用户目录的问题要在产品里消失：要么配置工作目录，要么容器隔离，要么服务化。

## 只属于本次验证的临时项

这些不应被写进产品部署假设：

- `legacy-pilot-pg-e2e` 临时 Docker 容器。
- `postgres:16-alpine` 本机临时镜像。
- `127.0.0.1:55432` 临时端口。
- `legacy_pilot_graph_payloads_e2e_full` 测试表。
- `Q:\tmp\gitnexus-local.cmd` wrapper。
- `Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus` 本机 checkout 路径。
- 内联 Python E2E script。
- pytest cache warnings。
- 本机提权运行。

## 风险和注意事项

- GitNexus 会写用户目录或自己的 registry/cache；受限 sandbox 下可能失败。
- PostgreSQL 测试会真实写表；必须使用隔离表名或测试数据库。
- DSN 示例包含 demo 凭据；真实凭据必须走 secret/env，不提交到代码或文档。
- Docker 只是验证手段；产品应连接托管或正式部署的 PostgreSQL。
- `GitNexusCliCodeKnowledgeCoreAdapter.query_graph()` 在 PostgreSQL restore miss 后允许 fallback 到 GitNexus query；本次 E2E 用 `QueryForbiddenClient` 证明恢复命中，没有走 fallback。
- 当前 `SaveIncident` 仍是中间件 deterministic implementation，不等于 Structure4 持久化 incident DB 已实现。
- 当前 `GenerateRCA` / `ReviewRCA` 仍是 mock/deterministic RCA，不等于 Structure3 真实推理已实现。

## 最小产品化环境清单

```text
Python runtime
Python deps: fastapi, uvicorn, pydantic, pytest for tests, psycopg[binary]
GitNexus CLI/runtime or service backend
Writable GitNexus index/cache/registry location
PostgreSQL database
Secure env/secret injection for DSN and runtime paths
Middleware service process
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql
LEGACY_PILOT_GRAPH_STORE_DSN=<secret>
LEGACY_PILOT_GRAPH_STORE_TABLE=<managed table>
LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context
GITNEXUS_BIN=<product runtime path>
GITNEXUS_REPO_ROOT=<product runtime path if CLI requires it>
GITNEXUS_INDEX_TIMEOUT_SECONDS=<configured>
GITNEXUS_QUERY_TIMEOUT_SECONDS=<configured>
```

## 当前结论

Structure1 和 Structure2 的真实集成链路已经被验证到 middleware contract 边界：

```text
real GitNexus graph generation
-> PostgreSQL graph payload persistence
-> persisted GraphContext restore
-> Structure2 EvidenceBundle construction
-> downstream RCA/review/save mock closure
```

这证明 Structure1 graph 产物可以经持久化跨进程恢复，并被 Structure2 按契约消费。完整产品仍需继续实现 Structure3 真实 RCA、Structure4 真实 incident memory persistence，以及产品级 GitNexus/PostgreSQL 运维配置。
