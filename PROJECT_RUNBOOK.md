# LegacyPilot Project Runbook

## 1. Project Overview

LegacyPilot is a legacy-code maintenance agent platform designed for old Java/Spring systems. The product goal is not only to read source files, but to build a traceable code knowledge layer that can later support incident analysis, root-cause analysis, migration planning, and agent-assisted maintenance.

The current repository contains two cooperating services:

- `LegacyPilot`: Java Spring Boot backend. It owns project onboarding, repository metadata, task records, incident records, and the API surface used by the frontend.
- `LCMS`: Python FastAPI service. It owns the interface contract middleware and Code Knowledge Core. It exposes graph/index APIs that the Java backend calls.

Current implemented flow:

```text
User/Postman
  -> Java Spring Boot /api/onboarding/local-project
  -> Java validates local Git repository
  -> Java scans project files
  -> Java calls Python /v1/repos/index
  -> Python returns GraphSnapshot
  -> Java returns project + repository + files + graph summary
```

The system is currently local-first for hackathon/demo use. It is structured so the in-memory stores can later be replaced by SQL persistence and the Python mock graph backend can later be switched to real GitNexus indexing.

## 2. Repository Layout

```text
D:\Hackathon
+-- LCMS
|   +-- legacy_pilot
|   |   +-- contracts
|   |   |   +-- Pydantic request/response contracts
|   |   +-- middleware
|   |   |   +-- FastAPI app and route orchestration
|   |   +-- code_knowledge_core
|   |       +-- Code graph adapters, GitNexus client/mapper, local graph index
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
```

## 3. Runtime Architecture

### 3.1 Service Boundary

```text
Frontend / Postman
       |
       v
LegacyPilot Java Backend
       |
       | HTTP JSON
       v
LCMS Python FastAPI Service
       |
       | Adapter boundary
       v
Code Knowledge Core
       |
       | Current: mock adapter
       | Future: GitNexus CLI adapter
       v
GraphSnapshot / GraphContext
```

The frontend should call Java only. Java is the application backend and hides Python/GitNexus details from the user-facing API.

### 3.2 Java Backend Responsibilities

`LegacyPilot` currently provides:

- Project creation and listing.
- Local Git repository onboarding.
- Repository metadata extraction:
  - local path
  - remote URL
  - branch
  - commit SHA
- File scanning:
  - Java files
  - Python files
  - config files
  - build files
  - markdown files
- Code graph analysis orchestration through Python.
- Incident/task placeholder APIs for later RCA and memory workflows.

Java does not parse source code deeply. It delegates graph analysis to LCMS/Python.

### 3.3 Python LCMS Responsibilities

`LCMS` currently provides:

- Contract models shared across internal structures.
- FastAPI routes for repository indexing, graph query, alert submission, evidence bundle generation, RCA review, and incident save.
- Code Knowledge Core adapter boundary.
- Mock graph indexing by default.
- GitNexus client/mapper code exists, but the running backend still needs explicit configuration before it becomes the real graph source.

### 3.4 Key Runtime Ports

| Service | Default URL | Purpose |
| --- | --- | --- |
| Java Spring Boot | `http://localhost:8080` | Public backend API |
| Python FastAPI | `http://127.0.0.1:8001` | Internal code knowledge API |

The Java backend expects Python at:

```text
http://127.0.0.1:8001
```

This can be overridden later with:

```properties
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

## 4. Prerequisites

Install these locally:

- Java 17
- Maven
- Python 3.13 or newer
- Git
- Node.js 22 or newer, only if running/building GitNexus locally

For local repository testing, the target project must already exist on disk and be a valid Git working tree.

Example tested path:

```text
D:\movie-review-understanding
```

## 5. First-Time Setup

### 5.1 Install Python Dependencies

From the LCMS directory:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn pydantic pytest httpx
```

If the virtual environment does not exist, create one first:

```powershell
cd D:\Hackathon\LCMS
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn pydantic pytest httpx
```

Optional editable install:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 5.2 Verify Python Tests

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pytest -q
```

Expected result for the current checked-in tests:

```text
42 passed
```

### 5.3 Verify Java Build

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

Expected result:

```text
BUILD SUCCESS
```

## 6. Local Run Procedure

Run Python first, then Java.

### 6.1 Start Python Code Knowledge Service

Open terminal 1:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

Check health:

```text
http://127.0.0.1:8001/health
```

Expected response:

```json
{
  "service": "legacy-pilot-interface-contract-middleware",
  "contract_version": "1.0.0"
}
```

### 6.2 Start Java Backend

Open terminal 2:

```powershell
cd D:\Hackathon\LegacyPilot
mvn spring-boot:run
```

Check readiness:

```text
GET http://localhost:8080/api/analysis/status
```

## 7. Main User Flow

### 7.1 One-Step Local Project Onboarding

Request:

```http
POST http://localhost:8080/api/onboarding/local-project
Content-Type: application/json
```

Body:

```json
{
  "projectName": "Movie Review Understanding",
  "localRepoPath": "D:/movie-review-understanding"
}
```

Successful response shape:

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

Current important note:

- `graph.graphId = GRAPH-DEMO` means Python is using the mock Code Knowledge adapter.
- Real GitNexus integration should later return graph data closer to the actual GitNexus output.
- `repository.graphId` is currently generated by Java before Python indexing. In a later persistence pass, it should be updated from `graph.graphId`.

### 7.2 Re-run Repository Graph Analysis

This endpoint is kept for retry/re-index use cases.

Request:

```http
POST http://localhost:8080/api/repos/{repoId}/analyze
```

No request body is required.

Response:

```json
{
  "repoId": "REPO-...",
  "graphId": "GRAPH-DEMO",
  "nodeCount": 2,
  "edgeCount": 1,
  "generatedAt": "..."
}
```

Use this endpoint when:

- the repo has already been onboarded,
- Python/GitNexus failed and needs retry,
- code changed and the graph should be rebuilt,
- debugging the Java-to-Python boundary.

## 8. Java API Surface

### 8.1 Project APIs

Implemented in `ProjectController`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/projects` | Create project metadata only |
| `GET` | `/api/projects` | List in-memory projects |
| `POST` | `/api/onboarding/local-project` | One-step local onboarding and graph analysis |

### 8.2 Repository APIs

Implemented in `RepositoryController`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/repos/index` | Placeholder Git URL indexing record |
| `POST` | `/api/repos/connect` | Connect local path repository to an existing project |
| `GET` | `/api/repos/{repoId}/files` | Scan files for an existing repository |
| `POST` | `/api/repos/{repoId}/analyze` | Call Python Code Knowledge Core and return graph summary |

### 8.3 Incident APIs

Implemented in `IncidentController`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/incidents/analyze` | Create placeholder incident analysis task |
| `GET` | `/api/incidents/{incidentId}` | Get incident record |
| `POST` | `/api/incidents/{incidentId}/confirm` | Mark incident as user-confirmed |

### 8.4 Task APIs

Implemented in `TaskController`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/analysis/status` | Backend readiness |
| `GET` | `/api/analysis/{taskId}` | Get task status |

## 9. Python API Surface

FastAPI app entrypoint:

```text
LCMS/legacy_pilot/middleware/app.py
```

Important routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Python service health check |
| `POST` | `/v1/repos/index` | Index repository and return `GraphSnapshot` |
| `POST` | `/v1/graph/query` | Query graph context |
| `POST` | `/v1/alerts/submit` | Submit alert/log |
| `POST` | `/v1/evidence-bundles/build` | Build evidence bundle |
| `POST` | `/v1/incidents/similar` | Retrieve similar incidents |
| `POST` | `/v1/rca/generate` | Generate RCA report |
| `POST` | `/v1/rca/review` | Review RCA report |
| `POST` | `/v1/incidents/save` | Save confirmed incident |

Java currently calls:

```text
POST /v1/repos/index
```

Expected Python request from Java:

```json
{
  "repo_id": "REPO-...",
  "repo_uri": "D:/movie-review-understanding",
  "language_hint": "python",
  "parser_profile": "python-default",
  "contract_version": "1.0.0"
}
```

For Java/Spring projects, Java auto-detection should send:

```json
{
  "language_hint": "java",
  "parser_profile": "spring-mybatis"
}
```

## 10. Java Internal Architecture

### 10.1 Controllers

```text
controller/
├── ProjectController
├── RepositoryController
├── IncidentController
└── TaskController
```

Controllers only receive HTTP requests and delegate to services.

### 10.2 Services

```text
service/
├── AnalysisService
├── GitRepositoryService
├── RepositoryFileScannerService
├── CodeKnowledgeClient
├── RepositoryCodeAnalysisService
└── ProjectOnboardingService
```

Service responsibilities:

| Service | Responsibility |
| --- | --- |
| `AnalysisService` | Temporary in-memory project/repo/task/incident state and basic workflow |
| `GitRepositoryService` | Validate local Git repo and read remote/branch/commit |
| `RepositoryFileScannerService` | Scan repository files and categorize them |
| `CodeKnowledgeClient` | HTTP client for Python `/v1/repos/index` |
| `RepositoryCodeAnalysisService` | Orchestrate repoId -> local path -> Python graph analysis |
| `ProjectOnboardingService` | One-step onboarding orchestration |

### 10.3 DTOs

DTOs define API request/response shapes.

Important DTOs:

| DTO | Purpose |
| --- | --- |
| `ConnectLocalProjectRequest` | User-provided project name and local repo path |
| `ConnectLocalProjectResponse` | Full onboarding response with project/repository/files/graph |
| `RepositoryFilesResponse` | File scan summary |
| `CodeKnowledgeIndexRequest` | JSON sent from Java to Python |
| `CodeKnowledgeGraphSnapshotResponse` | Raw-ish Python graph snapshot response |
| `RepositoryGraphAnalysisResponse` | Compact graph summary returned by Java |

### 10.4 Entity Records

Current entity records model future persistence objects:

| Entity | Purpose |
| --- | --- |
| `LegacyProject` | Top-level project container |
| `RepositoryIndex` | Repository metadata and graph/task references |
| `AnalysisTask` | Long-running or staged backend work |
| `IncidentRecord` | Incident/RCA memory placeholder |

Current state is in memory. Restarting the Java process clears:

- projects
- repositories
- tasks
- incidents

## 11. LCMS / Code Knowledge Core Architecture

```text
legacy_pilot/
├── contracts
│   ├── enums.py
│   ├── errors.py
│   ├── models.py
│   └── validators.py
├── middleware
│   ├── app.py
│   └── router.py
└── code_knowledge_core
    ├── adapter.py
    ├── gitnexus_client.py
    ├── gitnexus_mapper.py
    ├── local_graph_index.py
    ├── query_planner.py
    ├── semantic.py
    └── extractors
```

Important components:

| Component | Purpose |
| --- | --- |
| `contracts/models.py` | Pydantic contracts for all cross-module JSON |
| `middleware/app.py` | FastAPI application and route definitions |
| `middleware/router.py` | Contract validation and routing |
| `code_knowledge_core/adapter.py` | Adapter boundary, mock adapter, GitNexus adapter factory |
| `code_knowledge_core/gitnexus_client.py` | GitNexus CLI client |
| `code_knowledge_core/gitnexus_mapper.py` | Maps GitNexus results into LegacyPilot graph contracts |
| `code_knowledge_core/local_graph_index.py` | Local graph lookup/index support |

## 12. Current Data Flow Details

### 12.1 Onboarding Sequence

```text
POST /api/onboarding/local-project
  -> ProjectController
  -> ProjectOnboardingService
  -> AnalysisService.connectLocalProject
      -> GitRepositoryService.inspectLocalRepository
      -> create LegacyProject
      -> create RepositoryIndex
      -> RepositoryFileScannerService.scanRepositoryFiles
  -> RepositoryCodeAnalysisService.analyzeRepository
      -> AnalysisService.getRepository
      -> CodeKnowledgeClient.indexRepository
      -> Python POST /v1/repos/index
  -> return ConnectLocalProjectResponse
```

### 12.2 Re-analysis Sequence

```text
POST /api/repos/{repoId}/analyze
  -> RepositoryController
  -> RepositoryCodeAnalysisService
  -> AnalysisService.getRepository
  -> CodeKnowledgeClient.indexRepository
  -> Python /v1/repos/index
  -> RepositoryGraphAnalysisResponse
```

## 13. GitNexus Notes

GitNexus is not committed as part of this repository. It is treated as an external local tool.

Previously verified command shape:

```powershell
node D:\Tools\GitNexus\gitnexus\dist\cli\index.js analyze D:\movie-review-understanding --index-only
```

Example successful GitNexus output:

```text
221 nodes | 395 edges | 11 clusters | 15 flows
```

The current Java-to-Python integration returns mock graph data by default:

```text
GRAPH-DEMO
2 nodes
1 edge
```

Production direction:

```text
Python Code Knowledge Core
  -> GitNexusCliCodeKnowledgeCoreAdapter
  -> GitNexus CLI
  -> GitNexus mapper
  -> GraphSnapshot
```

## 14. Configuration

### 14.1 Java Backend

Current default:

```properties
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

There is no `application.properties` yet. For production-style configuration, create:

```text
LegacyPilot/src/main/resources/application.properties
```

Suggested content:

```properties
server.port=8080
legacypilot.code-knowledge.base-url=http://127.0.0.1:8001
```

### 14.2 Python Service

Current default backend is mock unless configured otherwise in Python code/environment.

Recommended future env variables:

```text
LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
GITNEXUS_CLI_PATH=D:\Tools\GitNexus\gitnexus\dist\cli\index.js
```

Exact variable names should match the Python adapter implementation when real GitNexus mode is finalized.

## 15. Production Deployment Direction

The current implementation is local MVP quality, but the module split is intended to support a production deployment.

### 15.1 Recommended Production Topology

```text
Frontend
  -> Java Backend
  -> Python Code Knowledge Service
  -> GitNexus CLI / graph builder
  -> Persistent storage
```

Recommended production components:

- Java Spring Boot service behind an API gateway or reverse proxy.
- Python FastAPI service as an internal service, not directly exposed to users.
- SQL database for project/repository/task/incident records.
- Object storage or local workspace policy for cloned repositories and graph artifacts.
- Background job queue for large repo indexing.
- Log aggregation for Java and Python services.

### 15.2 Persistence Plan

Current in-memory maps in Java should become SQL tables:

| Current Map | Future Table |
| --- | --- |
| `projects` | `legacy_project` |
| `repositories` | `repository_index` |
| `tasks` | `analysis_task` |
| `incidents` | `incident_record` |

Redis should not be the source of truth for project/repository IDs. Redis is better suited for:

- short-lived locks
- task progress cache
- rate limiting
- temporary session state

SQL should store durable IDs and business records.

### 15.3 Repository Storage Policy

Current local-path mode assumes the repository already exists on the user's machine.

Future Git URL mode should support:

- user-provided clone directory
- default workspace directory under user home
- conflict handling when a same-name repository already exists
- re-index behavior for updated commits

Do not store full source code in SQL. Store metadata and graph artifacts. Source remains in the local workspace or clone directory.

## 16. Current Limitations

These are known limits, not bugs:

- Java backend state is in memory and disappears after restart.
- Python Code Knowledge Core currently returns mock graph output unless GitNexus backend is enabled.
- Full graph visualization is not implemented in the frontend yet.
- Java returns graph summary, not full nodes/edges, from onboarding.
- `repository.graphId` is still Java-generated while `graph.graphId` comes from Python; this should be unified later.
- Git URL clone path is not fully implemented in Java yet.
- Incident RCA flow is still placeholder and not backed by a real LLM/RAG chain.
- No authentication/authorization layer exists yet.
- No database migration/schema exists yet.

## 17. Troubleshooting

### 17.1 Java Returns 502 When Calling Onboarding

Likely cause: Python service is not running.

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

If it fails, start Python:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

### 17.2 Java Returns 404 Repository Not Found

The Java backend is in-memory. If Java restarted after onboarding, the old `repoId` no longer exists.

Fix:

```text
Call /api/onboarding/local-project again and use the new repoId.
```

### 17.3 File Scan Includes Generated Folders

`RepositoryFileScannerService` intentionally ignores:

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

If another generated folder appears, add it to the ignore list.

### 17.4 Maven Cannot Download Dependencies

If Maven fails with `Permission denied: getsockopt` or cannot reach Maven Central, it is a network/proxy issue.

Retry after network/proxy is stable:

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

### 17.5 Git Push Hangs

Check GitHub connectivity:

```powershell
Test-NetConnection github.com -Port 443
```

If `TcpTestSucceeded` is false, switch VPN/network and retry:

```powershell
git push origin Hackathon
```

## 18. Recommended Next Steps

Priority order:

1. Enable real GitNexus backend in Python and verify Java receives real graph counts.
2. Update Java `repository.graphId` after Python returns a real `graphId`.
3. Add SQL persistence for projects, repositories, tasks, and incidents.
4. Add graph detail endpoint for nodes/edges when frontend visualization is ready.
5. Add frontend onboarding page in `LCMS`.
6. Add incident evidence/RCA flow using Qwen/RAG.
7. Add authentication and workspace isolation before real multi-user deployment.

## 19. Quick Command Summary

Start Python:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m uvicorn legacy_pilot.middleware.app:app --reload --port 8001
```

Start Java:

```powershell
cd D:\Hackathon\LegacyPilot
mvn spring-boot:run
```

Run Python tests:

```powershell
cd D:\Hackathon\LCMS
.\.venv\Scripts\python.exe -m pytest -q
```

Run Java build:

```powershell
cd D:\Hackathon\LegacyPilot
mvn test
```

Main API:

```text
POST http://localhost:8080/api/onboarding/local-project
```

Main request body:

```json
{
  "projectName": "Movie Review Understanding",
  "localRepoPath": "D:/movie-review-understanding"
}
```
