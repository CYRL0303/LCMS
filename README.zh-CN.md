# LegacyPilot 接口契约中间件

[English README](README.md)

LegacyPilot 是面向事故驱动旧系统分析的 hackathon MVP。本仓库当前实现第一条产品化切片：一个 Python/FastAPI 接口契约中间件，用来标准化四个 LegacyPilot 结构之间的请求、响应和错误边界。

## 中间件职责

- 定义跨结构请求/响应的 Pydantic 契约。
- 强制校验 `contract_version`、`trace_id`、`confidence`、`evidence_refs`。
- 对中间件层失败返回统一 `ContractError` envelope。
- 暴露 MVP 事故分析流程的 FastAPI 路由。
- 默认链路走真实后端：Structure 1 `gitnexus_cli`、Structure 2 `graph_context`、Structure 3 `qwen_api`、Structure 4 PostgreSQL incident memory。
- 运行时 mock backend 选择已关闭。

默认链路：

```text
SubmitAlert
-> BuildEvidenceBundle (Structure2 graph_context -> QueryGraph)
-> GenerateRCA (Structure3 qwen_api)
-> ReviewRCA
-> SaveIncident (Structure4 postgresql)
```

## 当前进度

Structure 1-4 已通过中间件契约串起来，并有真实 opt-in 集成覆盖：

- `repo_id` 是用户/项目维度的仓库别名。
- `graph_id` 是某次真实 `IndexRepo` 产出的 graph snapshot ID，或用户从已持久化 graph 中选择的 ID。
- Structure 1 使用真实 `gitnexus_cli` 索引/查询集成，包含 MyBatis SQL 提取、table/config/exception evidence、本地 graph index、可选 PostgreSQL graph payload 持久化。
- Structure 1 支持本地路径、`file://` URI、GitHub HTTPS repo URL、GitLab HTTPS repo URL。
- 私有 GitHub/GitLab 仓库通过前端 Settings modal 或等价 HTTP header 传 runtime token。
- Structure 1 semantic enrichment 默认关闭，可 opt-in 真实 DashScope Qwen `qwen_api`。
- Structure 2 拥有 `IncidentContextBuilderAdapter`，默认 `graph_context`，从 Structure 1 `GraphContext` 构建 `EvidenceBundle`。
- Structure 3 拥有 `RCAReasoningEngineAdapter`，默认真实 DashScope Qwen `qwen_api`，没有默认 mock RCA path。
- Structure 3 强制 evidence-backed RCA，拒绝未知 `evidence_ids`，对无效 JSON/schema 做有限 repair retry，不存 secret。
- Structure 4 使用 PostgreSQL 持久化用户确认后的 RCA incident memory。生产 factory 只允许 `postgresql`。
- `RCAReport`、`ReviewedRCAReport`、`IncidentRecord` 都携带 `graph_id`，incident memory 与生成 evidence 的 graph snapshot 绑定。
- 中间件暴露 graph list/delete。若 Structure 4 已有 incident memory 引用 graph，删除会被阻止。
- PowerShell 脚本可启动 Docker Desktop/PostgreSQL，读取持久化 Qwen key，运行真实 GitNexus + PostgreSQL + Structure2 + Structure3 + Structure4 E2E。
- 生产 fixture 覆盖 `/api/dataset/version -> controller -> service -> mapper -> Mapper XML SQL -> dataset_version`，并覆盖 config/exception evidence。

最近本地验证示例：

```text
Default suite: 230 passed, 8 skipped, 1 warning
Real Structure1/PostgreSQL/Structure2/Structure3/Structure4 E2E: 3 passed, 2 warnings
Real GitNexus + Structure1 production fixture: 12 passed, 2 warnings
Real PostgreSQL graph store integration: 1 passed, 2 warnings
Real Qwen semantic integration: 1 passed, 2 warnings
Frontend build: passed
Manual real browser E2E with existing graph: passed
Secret scan: no persisted Qwen key in repository
```

## 目录结构

```text
legacy_pilot/
  contracts/              # Pydantic models, enums, validators, runtime credentials
  middleware/             # FastAPI app and contract router
  code_knowledge_core/    # Structure 1 adapter, GitNexus client, graph store
  incident_context_builder/ # Structure 2 evidence bundle builder
  rca_reasoning_engine/   # Structure 3 Qwen RCA adapter
  incident_memory_store/  # Structure 4 PostgreSQL incident memory
frontend/
  src/                    # React/Vite Incident Workbench
  tests/                  # Playwright real frontend E2E
scripts/                  # real E2E, Qwen env, Docker smoke scripts
tests/                    # contract/unit/integration tests
```

## 安装

Python：

```bash
python -m pip install -e .[dev]
```

Frontend：

```bash
cd frontend
npm install
```

## 运行测试

默认测试不访问外部系统：

```bash
python -m pytest -q
```

Docker 部署配置测试：

```bash
python -m pytest tests/test_docker_deployment_config.py -q
```

Frontend build：

```bash
cd frontend
npm run build
```

## 真实后端配置

### Structure 1 GitNexus CLI

启用真实 GitNexus：

```powershell
$env:LEGACY_PILOT_CODE_CORE_BACKEND='gitnexus_cli'
$env:GITNEXUS_BIN='Q:\tmp\gitnexus-local.cmd'
$env:GITNEXUS_REPO_ROOT='Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus'
$env:GITNEXUS_TIMEOUT_SECONDS='60'
$env:GITNEXUS_INDEX_TIMEOUT_SECONDS='120'
$env:GITNEXUS_QUERY_TIMEOUT_SECONDS='30'
$env:GITNEXUS_CYPHER_RETRY_EDGE_LIMIT='100'
```

`GITNEXUS_CYPHER_RETRY_EDGE_LIMIT` 用于 `IndexRepo` 的大图 `cypher`
响应被截断、无法解析 JSON 时，降到较小 edge limit 后重试一次。

远端仓库支持：

- GitHub: `https://github.com/<owner>/<repo>`
- GitLab: `https://gitlab.com/<group>/<repo>`
- 私有仓库：通过 `X-LegacyPilot-GitHub-Token` 或 `X-LegacyPilot-GitLab-Token` 传 token。

### Structure 1 PostgreSQL Graph Store

启动本地 E2E PostgreSQL：

```bash
docker compose -f docker-compose.e2e.yml up -d postgres
```

环境变量：

```powershell
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND='postgresql'
$env:LEGACY_PILOT_GRAPH_STORE_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_GRAPH_STORE_TABLE='legacy_pilot_graph_payloads'
```

Graph store 只属于 Structure 1。其他结构不能直接读 PostgreSQL graph store，只能通过 middleware/contract 调用。

### Structure 2 Incident Context Builder

默认：

```powershell
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND='graph_context'
```

`graph_context` 通过中间件内部 `/v1/graph/query` 构建 evidence bundle。

### Structure 3 Qwen RCA

默认：

```powershell
$env:LEGACY_PILOT_RCA_BACKEND='qwen_api'
$env:LEGACY_PILOT_RCA_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
$env:LEGACY_PILOT_RCA_MODEL='qwen-plus'
$env:LEGACY_PILOT_RCA_CONFIDENCE_CAP='0.75'
$env:LEGACY_PILOT_RCA_REPAIR_ATTEMPTS='2'
$env:LEGACY_PILOT_RCA_TIMEOUT_SECONDS='120'
$env:LEGACY_PILOT_RCA_TRANSPORT_RETRIES='1'
$env:LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS='1'
$env:DASHSCOPE_API_KEY='<set outside git>'
```

Qwen adapter 会对无效 JSON/schema 做有限 repair retry；transport timeout 单独处理。
`LEGACY_PILOT_RCA_TIMEOUT_SECONDS` 控制 DashScope read timeout，
`LEGACY_PILOT_RCA_TRANSPORT_RETRIES` 控制 timeout/临时 transport 失败重试次数，
`LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS` 控制指数 backoff。重试耗尽后返回
recoverable contract error，不再冒成裸 HTTP 500。

持久化 Qwen key 到 Windows User env：

```powershell
.\scripts\set-qwen-user-env.ps1 -WriteDotEnvLocal
```

替换 key：

```powershell
[Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', '<new-key>', 'User')
$env:DASHSCOPE_API_KEY='<new-key>'
```

`.env.local` 已 gitignored。不要提交真实 key。

### Structure 4 Incident Memory

默认：

```powershell
$env:LEGACY_PILOT_INCIDENT_MEMORY_BACKEND='postgresql'
$env:LEGACY_PILOT_INCIDENT_MEMORY_DSN='postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5'
$env:LEGACY_PILOT_INCIDENT_MEMORY_TABLE='legacy_pilot_incident_records'
```

`SaveIncident` 通过 Structure 4 保存用户确认后的 RCA。表中保存完整 `IncidentRecord` JSON，并带 `incident_id`、`repo_id`、`graph_id`、`dedup_key` 列。缺少 PostgreSQL DSN 会 fail loud；生产没有 in-memory fallback。

## 运行 API

```bash
python -m uvicorn legacy_pilot.middleware.app:app --host 127.0.0.1 --port 8000
```

OpenAPI：

```text
http://127.0.0.1:8000/docs
```

Health：

```text
http://127.0.0.1:8000/health
```

## 运行 Frontend Workbench

Frontend 是 React/Vite 单页 `Incident Workbench`。它只通过 `/api` proxy 调 middleware HTTP API，不直接连接 GitNexus、PostgreSQL、DashScope。

启动 middleware：

```bash
python -m uvicorn legacy_pilot.middleware.app:app --host 127.0.0.1 --port 8000
```

启动 frontend：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

真实浏览器 E2E：

```powershell
.\scripts\run-real-frontend-e2e.ps1 -InstallFrontendDeps
```

只启动真实后端和前端，便于手动测试：

```powershell
.\scripts\run-real-frontend-e2e.ps1 -StartOnly
```

手动产品链路：

- 本地仓库：在 `Repo URI` 输入本地路径或 `file://` URI，点 `Index repo`。
- 远端仓库：在 `Repo URI` 输入 GitHub/GitLab HTTPS URL；私有仓库先在 Settings 填 token。
- 已有 graph：在 `Existing graphs` 选择 graph，点 `Use existing graph`，填 `Alert ID` 和 `Raw log`，点 `Run full pipeline`。

Structure2 alert 输入支持三种模式：

- `Manual`：手动粘贴 `Raw log`、`Stack trace`、`Error description`。
- `Import local log`：选择本地 `.log`、`.txt`、`.json` 文件或日志目录；浏览器读取文件并填入 `AlertEvent.raw_log`，后端不会读取用户电脑上的本地路径。
- `Webhook`：监控系统向 middleware 推送 generic JSON alert；后端 normalize 成 `AlertEvent`，再走同一条 `SubmitAlert -> BuildEvidenceBundle -> RCA` 链路。

Generic webhook 示例：

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/alerts/webhook/generic?repo_id=ibm-demo&graph_id=GRAPH-..." \
  -H "Content-Type: application/json" \
  -H "X-LegacyPilot-Webhook-Secret: dev-secret" \
  -d '{"id":"alert-1","source":"grafana","message":"NullPointerException at BookController.java:31","title":"Book API failed"}'
```

生产环境设置 `LEGACY_PILOT_WEBHOOK_SECRET` 后，webhook 必须带 `X-LegacyPilot-Webhook-Secret` header。本地开发可留空。

Settings modal 把 Qwen API key、GitHub/GitLab token 存在浏览器 localStorage。Frontend 不直接调用 GitNexus、PostgreSQL、DashScope、GitHub、GitLab；只转发 credentials 到 middleware headers。

## Dockerized deployment

Docker 产品化路径跑真实链路：

```text
web container
-> /api reverse proxy
-> api container
-> gitnexus_cli built into /opt/gitnexus
-> PostgreSQL graph payload store
-> graph_context evidence builder
-> qwen_api RCA generation
-> PostgreSQL incident memory store
```

创建私有 env：

```powershell
Copy-Item .env.prod.example .env.prod
```

设置私有值，也可用 process env 注入：

```dotenv
DASHSCOPE_API_KEY=
GITNEXUS_SOURCE_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main
GITNEXUS_PACKAGE_DIR=gitnexus
GITNEXUS_CYPHER_RETRY_EDGE_LIMIT=100
LEGACY_PILOT_RCA_TIMEOUT_SECONDS=120
LEGACY_PILOT_RCA_TRANSPORT_RETRIES=1
LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS=1
LEGACY_PILOT_WEBHOOK_SECRET=
```

`GITNEXUS_SOURCE_ROOT` 必须指向真实 GitNexus 源码 checkout。
`GITNEXUS_PACKAGE_DIR` 是 checkout 内的 package 目录，通常是 `gitnexus`。
API Docker build 会把源码作为 BuildKit named context 复制进镜像，在 Linux
里运行 `npm ci` 和 `npm run build`，再把构建好的 package 暴露到
`/opt/gitnexus`，通过 `/usr/local/bin/gitnexus` 执行。这样 Windows 本机的
`node_modules` 不会被挂载进 Linux 容器，native binary 不会跨平台污染。

启动：

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

打开：

```text
http://127.0.0.1:8080
```

Smoke：

```powershell
.\scripts\smoke-prod-compose.ps1 -TimeoutSeconds 240
```

Smoke 脚本会先检查 GitNexus 源码 package，再进入 API 容器检查
`/opt/gitnexus/dist/cli/index.js`，校验 LadybugDB native module 是 Linux ELF，
并运行一个极小真实 `gitnexus analyze`，最后检查
`http://127.0.0.1:8080/api/health`。

停止但保留数据：

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

删除本地数据库和 repo cache：

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down -v
```

## Alibaba Cloud 部署

### ECS 快速部署

1. 创建 Alibaba Cloud ECS，安装 Docker 和 Docker Compose。
2. 在 ECS 上 clone 本仓库。
3. 在 ECS 上 clone GitNexus 源码到 `/opt/legacy-pilot/GitNexus`。
4. `Copy-Item .env.prod.example .env.prod`。
5. 设置 `DASHSCOPE_API_KEY`、`GITNEXUS_SOURCE_ROOT=/opt/legacy-pilot/GitNexus` 和 `GITNEXUS_PACKAGE_DIR=gitnexus`。
6. 运行 `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`。
7. 用 Nginx、Caddy 或 SLB 放到 `8080` 前面，只暴露 HTTPS。

Hackathon demo 可用 compose 内 PostgreSQL + ECS cloud disk。产品数据建议用 RDS PostgreSQL，并通过 compose override 或 ACK Secret 把 `LEGACY_PILOT_GRAPH_STORE_DSN`、`LEGACY_PILOT_INCIDENT_MEMORY_DSN` 指到 RDS 内网 endpoint。

### 产品化路径

- CI 构建 `legacy-pilot-api` 和 `legacy-pilot-web` 镜像。
- 镜像推到 Alibaba Cloud ACR。
- ACK 跑 `api` 和 `web` Deployment。
- RDS PostgreSQL 存 graph payload 和 incident memory。
- SLB/Ingress 提供 HTTPS。
- `DASHSCOPE_API_KEY`、GitHub/GitLab token、PostgreSQL password 存 Alibaba Cloud Secret Manager 或 Kubernetes Secrets。
- Repo clone cache 用 NAS/PVC，或 ephemeral volume + 清理策略。
- 容器日志进入 Alibaba Cloud SLS。

网络边界：

- Public：只暴露 HTTPS 到 `web`。
- Internal：`web -> api:8000`，`api -> PostgreSQL`。
- Outbound：DashScope、GitHub、GitLab、remote Git clone endpoints。

`ACR + ACK + RDS` 是 ECS Compose demo 稳定后的推荐产品形态。

## API Surface

- `GET /health`
- `POST /v1/repos/index`
- `POST /v1/graph/query`
- `GET /v1/graphs`
- `DELETE /v1/graphs/{repo_id}/{graph_id}`
- `POST /v1/alerts/submit`
- `POST /v1/alerts/webhook/generic`
- `POST /v1/evidence-bundles/build`
- `POST /v1/incidents/similar`
- `GET /v1/incidents/{incident_id}`
- `POST /v1/rca/generate`
- `POST /v1/rca/review`
- `POST /v1/incidents/save`

## 当前限制

- Structure 1 真实执行使用 `gitnexus_cli` backend。
- `gitnexus_http` 尚未实现。
- Qwen semantic enrichment 只通过 opt-in `qwen_api` backend 开启。
- Semantic graph 输出仍是待完善能力，confidence-capped，不作为可信结构事实。
- Structure 2 默认 `graph_context`，需要可查询的 Structure 1 graph context 才能构建有用 evidence bundle。
- GitHub/GitLab repo import 通过 `git clone --depth 1` 支持 HTTPS clone URL；branch/tag/commit pinning 尚未实现。
- 自然语言 incident 必须能召回足够 graph evidence。过宽或匹配差的 incident text 可能在 `GenerateRCA` 失败，因为 Qwen 返回结论但没有有效 `evidence_ids`。
