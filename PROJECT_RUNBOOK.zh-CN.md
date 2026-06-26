# LegacyPilot 项目运行与架构说明

## 1. 项目定位

LegacyPilot 是一个面向老旧代码维护场景的代码分析 Agent 平台。它的目标不是简单地展示文件列表，也不是普通的代码问答工具，而是先把遗留项目转换成可追踪、可查询、可引用证据的代码知识层，再在这个基础上支持故障分析、根因分析、迁移评估和后续 Agent 自动化维护。

当前仓库里主要有两个服务：

- `LegacyPilot`：Java Spring Boot 后端，负责项目接入、仓库元数据、任务记录、事故记录，以及前端应该调用的主要 API。
- `LCMS`：Python FastAPI 服务，负责接口契约中间件和 Code Knowledge Core，也就是代码知识图谱相关能力。

当前已经跑通的主流程是：

```text
用户 / Postman
  -> Java Spring Boot /api/onboarding/local-project
  -> Java 检查本地 Git 仓库
  -> Java 扫描项目文件
  -> Java 调用 Python /v1/repos/index
  -> Python 返回 GraphSnapshot
  -> Java 返回 project + repository + files + graph
```

当前版本是本地优先的 hackathon/demo 形态，但结构已经按后续上线方向拆开：

- Java 后端是业务入口。
- Python 是内部代码知识服务。
- GitNexus 后续作为代码图谱构建能力接入 Python。
- 当前 Java 里的内存存储后续可以替换成 SQL。

## 2. 仓库结构

```text
D:\Hackathon
+-- LCMS
|   +-- legacy_pilot
|   |   +-- contracts
|   |   |   +-- Pydantic 请求/响应契约
|   |   +-- middleware
|   |   |   +-- FastAPI 应用和路由编排
|   |   +-- code_knowledge_core
|   |       +-- 代码图谱适配器、GitNexus client/mapper、本地图索引
|   +-- tests
|   +-- docs
|   +-- pyproject.toml
|
+-- LegacyPilot
|   +-- pom.xml
|   +-- src/main/java/com/legacypilot
|       +-- controller
|       +-- dto
|       +-- entity
|       +-- mapper
|       +-- service
|
+-- PROJECT_RUNBOOK.md
+-- PROJECT_RUNBOOK.zh-CN.md
```

## 3. 总体架构

### 3.1 服务边界

```text
前端 / Postman
       |
       v
LegacyPilot Java 后端
       |
       | HTTP JSON
       v
LCMS Python FastAPI 服务
       |
       | Adapter 边界
       v
Code Knowledge Core
       |
       | 当前：mock adapter
       | 后续：GitNexus CLI adapter
       v
GraphSnapshot / GraphContext
```

设计原则是：前端只调用 Java 后端。Python 和 GitNexus 都属于内部能力，不应该让前端直接感知。

### 3.2 Java 后端职责

`LegacyPilot` 当前负责：

- 创建项目。
- 接入本地 Git 仓库。
- 读取仓库元信息：
  - 本地路径
  - 远程 Git URL
  - 当前分支
  - 当前 commit SHA
- 扫描文件列表：
  - Java 文件
  - Python 文件
  - 配置文件
  - 构建文件
  - Markdown 文件
- 调用 Python Code Knowledge Core。
- 返回代码图谱摘要。
- 保留 incident/task 相关接口，为后续 RCA 和 memory 做准备。

Java 后端不负责深度解析源码。深度代码分析会交给 Python 的 Code Knowledge Core。

### 3.3 Python LCMS 职责

`LCMS` 当前负责：

- 定义跨模块 JSON contract。
- 暴露 FastAPI 接口。
- 提供 Code Knowledge Core adapter 边界。
- 默认返回 mock 图谱结果。
- 已经包含 GitNexus client/mapper 相关代码，但真实 GitNexus backend 还需要后续配置和验证。

## 4. 默认端口

| 服务 | 默认地址 | 用途 |
| --- | --- | --- |
| Java Spring Boot | `http://localhost:8080` | 面向前端/Postman 的主后端 |
| Python FastAPI | `http://127.0.0.1:8001` | Java 内部调用的代码知识服务 |

Java 默认调用 Python：

```text
http://127.0.0.1:8001
```

后续可以通过配置覆盖：

```properties
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

## 5. 本地环境要求

需要安装：

- Java 17
- Maven
- Python 3.13 或更高版本
- Git
- Node.js 22 或更高版本，仅在本地运行/构建 GitNexus 时需要

测试本地项目时，目标项目必须已经在本地，并且是一个有效 Git 工作区。

例子：

```text
D:\movie-review-understanding
```

## 6. 第一次环境准备

### 6.1 安装 Python 依赖

进入 LCMS：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn pydantic pytest httpx
```

如果 `.venv` 不存在：

```powershell
cd D:\Hackathon\LCMS
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn pydantic pytest httpx
```

可选 editable install：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 6.2 验证 Python 测试

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pytest -q
```

当前预期：

```text
42 passed
```

### 6.3 验证 Java 编译

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

预期：

```text
BUILD SUCCESS
```

## 7. 本地启动方式

启动顺序必须是：

```text
先启动 Python
再启动 Java
```

因为当前 Java 的一键 onboarding 会自动调用 Python。如果 Python 没启动，Java 会返回 `502 Bad Gateway`。

### 7.1 启动 Python FastAPI

终端 1：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

健康检查：

```text
http://127.0.0.1:8001/health
```

预期返回：

```json
{
  "service": "legacy-pilot-interface-contract-middleware",
  "contract_version": "1.0.0"
}
```

### 7.2 启动 Java 后端

终端 2：

```powershell
cd D:\Hackathon\LegacyPilot
mvn spring-boot:run
```

Java 健康检查：

```text
GET http://localhost:8080/api/analysis/status
```

## 8. 主流程：一键接入本地项目

### 8.1 请求地址

```http
POST http://localhost:8080/api/onboarding/local-project
Content-Type: application/json
```

### 8.2 请求体

推荐使用 `/`，避免 Windows 反斜杠转义问题：

```json
{
  "projectName": "Movie Review Understanding",
  "localRepoPath": "D:/movie-review-understanding"
}
```

也可以使用 Windows 路径，但 JSON 里反斜杠要写成 `\\`：

```json
{
  "projectName": "Movie Review Understanding",
  "localRepoPath": "D:\\movie-review-understanding"
}
```

### 8.3 成功返回结构

```json
{
  "project": {
    "projectId": "PROJ-...",
    "name": "Movie Review Understanding",
    "repositoryUrl": "https://github.com/GuanyuJin1/movie-review-understanding.git",
    "defaultBranch": "main",
    "createdAt": "..."
  },
  "repository": {
    "repoId": "REPO-...",
    "projectId": "PROJ-...",
    "sourceType": "LOCAL_PATH",
    "repositoryUrl": "https://github.com/GuanyuJin1/movie-review-understanding.git",
    "localRepoPath": "D:\\movie-review-understanding",
    "branch": "main",
    "commitSha": "...",
    "graphId": "GRAPH-REPO-...",
    "taskId": "TASK-...",
    "createdAt": "..."
  },
  "files": {
    "repoId": "REPO-...",
    "localRepoPath": "D:\\movie-review-understanding",
    "totalFiles": 39,
    "javaFiles": [],
    "pythonFiles": [],
    "configFiles": [],
    "buildFiles": [],
    "markdownFiles": []
  },
  "graph": {
    "repoId": "REPO-...",
    "graphId": "GRAPH-DEMO",
    "nodeCount": 2,
    "edgeCount": 1,
    "generatedAt": "..."
  }
}
```

### 8.4 当前返回结果怎么理解

四个主要部分：

| 字段 | 含义 |
| --- | --- |
| `project` | 业务项目容器 |
| `repository` | 仓库连接信息 |
| `files` | Java 扫描出来的文件摘要 |
| `graph` | Python Code Knowledge Core 返回的图谱摘要 |

当前 `graph.graphId = GRAPH-DEMO`，说明 Python 仍在使用 mock adapter。

真实 GitNexus 接入后，`nodeCount`、`edgeCount` 应该接近真实图谱规模。之前单独测试 GitNexus 时，示例项目结果是：

```text
221 nodes | 395 edges
```

## 9. 单独重新分析仓库

如果项目已经 onboarding 过，可以单独重新跑代码图谱分析：

```http
POST http://localhost:8080/api/repos/{repoId}/analyze
```

不需要请求体。

返回：

```json
{
  "repoId": "REPO-...",
  "graphId": "GRAPH-DEMO",
  "nodeCount": 2,
  "edgeCount": 1,
  "generatedAt": "..."
}
```

这个接口用于：

- 重新分析已经接入的仓库。
- Python/GitNexus 失败后重试。
- 项目代码更新后重建图谱。
- 单独调试 Java -> Python 调用链。

## 10. Java API 列表

### 10.1 ProjectController

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/projects` | 只创建项目元数据 |
| `GET` | `/api/projects` | 查看当前进程内项目 |
| `POST` | `/api/onboarding/local-project` | 一键接入本地项目并触发图谱分析 |

### 10.2 RepositoryController

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/repos/index` | Git URL 占位索引接口，目前不 clone |
| `POST` | `/api/repos/connect` | 把本地仓库连接到已有 project |
| `GET` | `/api/repos/{repoId}/files` | 单独扫描仓库文件 |
| `POST` | `/api/repos/{repoId}/analyze` | 调 Python Code Knowledge Core |

### 10.3 IncidentController

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/incidents/analyze` | 创建 incident 分析任务占位 |
| `GET` | `/api/incidents/{incidentId}` | 查看 incident |
| `POST` | `/api/incidents/{incidentId}/confirm` | 用户确认 incident |

### 10.4 TaskController

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/analysis/status` | 后端状态检查 |
| `GET` | `/api/analysis/{taskId}` | 查询 task 状态 |

## 11. Python API 列表

FastAPI 入口：

```text
LCMS/legacy_pilot/middleware/app.py
```

主要接口：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/health` | Python 服务健康检查 |
| `POST` | `/v1/repos/index` | 对仓库建图，返回 GraphSnapshot |
| `POST` | `/v1/graph/query` | 查询图谱上下文 |
| `POST` | `/v1/alerts/submit` | 提交日志/告警 |
| `POST` | `/v1/evidence-bundles/build` | 构建证据包 |
| `POST` | `/v1/incidents/similar` | 查找相似 incident |
| `POST` | `/v1/rca/generate` | 生成 RCA |
| `POST` | `/v1/rca/review` | 审查 RCA |
| `POST` | `/v1/incidents/save` | 保存用户确认后的 incident |

当前 Java 实际调用的是：

```text
POST /v1/repos/index
```

Java 发给 Python 的 JSON 类似：

```json
{
  "repo_id": "REPO-...",
  "repo_uri": "D:/movie-review-understanding",
  "language_hint": "python",
  "parser_profile": "python-default",
  "contract_version": "1.0.0"
}
```

如果是 Java/Spring 项目，Java 会根据文件后缀自动判断并发送：

```json
{
  "language_hint": "java",
  "parser_profile": "spring-mybatis"
}
```

## 12. Java 内部架构

### 12.1 Controller 层

```text
controller/
+-- ProjectController
+-- RepositoryController
+-- IncidentController
+-- TaskController
```

Controller 只做 HTTP 请求接收和 service 调用，不写业务逻辑。

### 12.2 Service 层

```text
service/
+-- AnalysisService
+-- GitRepositoryService
+-- RepositoryFileScannerService
+-- CodeKnowledgeClient
+-- RepositoryCodeAnalysisService
+-- ProjectOnboardingService
```

职责划分：

| Service | 职责 |
| --- | --- |
| `AnalysisService` | 临时内存状态和基础 project/repo/task/incident 流程 |
| `GitRepositoryService` | 检查本地 Git 仓库，读取 remote/branch/commit |
| `RepositoryFileScannerService` | 扫描和分类仓库文件 |
| `CodeKnowledgeClient` | 调用 Python `/v1/repos/index` |
| `RepositoryCodeAnalysisService` | 编排 repoId -> local path -> Python 图谱分析 |
| `ProjectOnboardingService` | 一键 onboarding 总编排 |

### 12.3 DTO 层

重要 DTO：

| DTO | 作用 |
| --- | --- |
| `ConnectLocalProjectRequest` | 用户输入项目名和本地仓库路径 |
| `ConnectLocalProjectResponse` | 返回 project/repository/files/graph |
| `RepositoryFilesResponse` | 文件扫描摘要 |
| `CodeKnowledgeIndexRequest` | Java 发给 Python 的请求 |
| `CodeKnowledgeGraphSnapshotResponse` | Java 接 Python 的 GraphSnapshot |
| `RepositoryGraphAnalysisResponse` | Java 返回前端/Postman 的图谱摘要 |

### 12.4 Entity 层

当前 entity 基本对应未来数据库表：

| Entity | 含义 |
| --- | --- |
| `LegacyProject` | 项目容器 |
| `RepositoryIndex` | 仓库元信息和图谱/task 引用 |
| `AnalysisTask` | 后续长任务或分析任务 |
| `IncidentRecord` | 故障/RCA 记忆占位 |

当前 Java 使用内存 Map 保存数据。Java 重启后这些数据会消失：

- projects
- repositories
- tasks
- incidents

## 13. LCMS / Code Knowledge Core 架构

```text
legacy_pilot/
+-- contracts
|   +-- enums.py
|   +-- errors.py
|   +-- models.py
|   +-- validators.py
+-- middleware
|   +-- app.py
|   +-- router.py
+-- code_knowledge_core
    +-- adapter.py
    +-- gitnexus_client.py
    +-- gitnexus_mapper.py
    +-- local_graph_index.py
    +-- query_planner.py
    +-- semantic.py
    +-- extractors
```

组件职责：

| 组件 | 作用 |
| --- | --- |
| `contracts/models.py` | 定义跨模块 JSON contract |
| `middleware/app.py` | FastAPI 应用入口和路由 |
| `middleware/router.py` | contract 校验和路由编排 |
| `code_knowledge_core/adapter.py` | mock/GitNexus adapter 边界 |
| `code_knowledge_core/gitnexus_client.py` | GitNexus CLI 调用客户端 |
| `code_knowledge_core/gitnexus_mapper.py` | 把 GitNexus 输出映射成 LegacyPilot 图谱 |
| `code_knowledge_core/local_graph_index.py` | 本地图索引和查询支持 |

## 14. 当前调用链细节

### 14.1 一键 onboarding

```text
POST /api/onboarding/local-project
  -> ProjectController
  -> ProjectOnboardingService
  -> AnalysisService.connectLocalProject
      -> GitRepositoryService.inspectLocalRepository
      -> 创建 LegacyProject
      -> 创建 RepositoryIndex
      -> RepositoryFileScannerService.scanRepositoryFiles
  -> RepositoryCodeAnalysisService.analyzeRepository
      -> AnalysisService.getRepository
      -> CodeKnowledgeClient.indexRepository
      -> Python POST /v1/repos/index
  -> 返回 ConnectLocalProjectResponse
```

### 14.2 重新分析仓库

```text
POST /api/repos/{repoId}/analyze
  -> RepositoryController
  -> RepositoryCodeAnalysisService
  -> AnalysisService.getRepository
  -> CodeKnowledgeClient.indexRepository
  -> Python /v1/repos/index
  -> RepositoryGraphAnalysisResponse
```

## 15. GitNexus 说明

GitNexus 不在本仓库内提交，它是外部本地工具。

之前已经验证过的命令：

```powershell
node D:\Tools\GitNexus\gitnexus\dist\cli\index.js analyze D:\movie-review-understanding --index-only
```

示例成功输出：

```text
221 nodes | 395 edges | 11 clusters | 15 flows
```

当前 Java -> Python 链路返回的是 mock 图谱：

```text
GRAPH-DEMO
2 nodes
1 edge
```

后续真实链路应该是：

```text
Python Code Knowledge Core
  -> GitNexusCliCodeKnowledgeCoreAdapter
  -> GitNexus CLI
  -> GitNexus mapper
  -> GraphSnapshot
```

## 16. 配置建议

### 16.1 Java 配置

当前默认：

```properties
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

项目里还没有正式 `application.properties`。后续可以新增：

```text
LegacyPilot/src/main/resources/application.properties
```

建议内容：

```properties
server.port=8080
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

### 16.2 Python 配置

当前默认是 mock backend。

后续切真实 GitNexus 可以考虑环境变量：

```text
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
GITNEXUS_CLI_PATH=D:\Tools\GitNexus\gitnexus\dist\cli\index.js
```

具体变量名需要和 Python adapter 实现保持一致。

## 17. 上线方向设计

当前是本地 demo 形态，但建议按下面方式演进：

```text
Frontend
  -> Java Backend
  -> Python Code Knowledge Service
  -> GitNexus CLI / graph builder
  -> SQL / object storage / graph artifact store
```

生产化建议：

- Java 后端作为唯一公网 API。
- Python FastAPI 作为内网服务，不直接暴露给用户。
- SQL 保存 project/repository/task/incident。
- Redis 只做缓存、锁、任务进度，不做长期事实存储。
- Git URL clone 和图谱构建应该进入后台任务队列。
- 大仓库建图不能阻塞 HTTP 请求太久。
- 日志要能关联 `projectId`、`repoId`、`taskId`。

## 18. 数据持久化规划

当前 Java 内存 Map 后续应替换成 SQL：

| 当前内存结构 | 未来表 |
| --- | --- |
| `projects` | `legacy_project` |
| `repositories` | `repository_index` |
| `tasks` | `analysis_task` |
| `incidents` | `incident_record` |

SQL 应该保存：

- projectId
- repoId
- repositoryUrl
- localRepoPath 或 clonePath
- branch
- commitSha
- graphId
- taskId
- incidentId
- 用户确认后的 RCA/memory 记录

不建议把完整源码存进 SQL。源码应该留在用户本地路径、clone 工作区或对象存储里。

## 19. 当前限制

这些是当前阶段的限制，不是 bug：

- Java 后端数据在内存中，重启后消失。
- Python 默认返回 mock 图谱。
- 还没有真实前端可视化。
- Java onboarding 返回的是 graph summary，不是完整 nodes/edges。
- `repository.graphId` 当前是 Java 预生成，`graph.graphId` 来自 Python，后续需要统一。
- Git URL clone 还没有完整实现。
- incident RCA 仍然是占位流程。
- 没有用户认证和权限隔离。
- 没有数据库 schema 和 migration。

## 20. 常见问题排查

### 20.1 onboarding 返回 502

通常是 Python 没启动。

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

如果失败，启动 Python：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

### 20.2 repository not found

Java 当前是内存存储。如果 Java 重启，旧的 `repoId` 会丢失。

解决：

```text
重新调用 /api/onboarding/local-project，拿新的 repoId。
```

### 20.3 文件扫描扫到生成目录

当前 `RepositoryFileScannerService` 已忽略：

```text
.git
.gitnexus
.idea
.vscode
__pycache__
node_modules
target
build
dist
```

如果后续出现新的生成目录，需要加入忽略列表。

### 20.4 Maven 下载失败

如果看到 Maven Central 连接失败，通常是网络或代理问题。

重试：

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

### 20.5 git push 卡住

检查 GitHub 443：

```powershell
Test-NetConnection github.com -Port 443
```

如果不通，切换 VPN/网络后再推：

```powershell
git push origin Hackathon
```

## 21. 建议下一步

优先级建议：

1. 让 Python Code Knowledge Core 切到真实 GitNexus backend。
2. 验证 Java 一键 onboarding 返回真实 graph count。
3. 让 `repository.graphId` 使用 Python 返回的真实 `graphId`。
4. 增加 SQL 持久化。
5. 增加 graph detail API，用于返回完整 nodes/edges。
6. 在 `LCMS` 中实现前端页面。
7. 接入 Qwen/RAG，完成 incident RCA 和 evidence bundle。
8. 加入认证、权限、工作区隔离。

## 22. 常用命令汇总

启动 Python：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

启动 Java：

```powershell
cd D:\Hackathon\LegacyPilot
mvn spring-boot:run
```

跑 Python 测试：

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pytest -q
```

跑 Java 编译：

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

主 API：

```text
POST http://localhost:8080/api/onboarding/local-project
```

主请求体：

```json
{
  "projectName": "Movie Review Understanding",
  "localRepoPath": "D:/movie-review-understanding"
}
```
