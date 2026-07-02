# LegacyPilot 项目运行说明

## 1. 当前项目状态

LegacyPilot 是一个面向 Java/Spring 老项目维护场景的代码分析与 Agent 平台。当前重点已经从早期 mock/demo 流程，切换到 Java 后端自研 `codeanalysis` 模块。

现在主链路是：

```text
Postman / Frontend
  -> LegacyPilot Java Spring Boot
  -> ProjectOnboardingService
  -> RepositoryCodeAnalysisService
  -> JavaCodeAnalysisService
  -> JavaSourceStructureParser / SpringEndpointParser
  -> 返回 project + repository + files + graph summary
```

也就是说，当前 `POST /api/onboarding/projects` 不再依赖 Python LCMS 或 GitNexus CLI。Python 服务和 GitNexus 代码暂时保留，但不是当前测试主链路。

## 2. 仓库目录

```text
D:\Hackathon
|-- LegacyPilot
|   |-- Java Spring Boot 后端
|   |-- 当前主流程、项目接入、文件扫描、Java/Spring 代码分析
|
|-- LegacyPilot-Frontend
|   |-- React + TypeScript 前端空壳
|
|-- LCMS
|   |-- Python FastAPI 服务
|   |-- 之前用于调用 GitNexus CLI / Code Knowledge Core
|   |-- 当前主流程暂时不依赖它
|
|-- PROJECT_RUNBOOK.zh-CN.md
|-- PROJECT_RUNBOOK.md
|-- PROJECT_CONTEXT_PROMPT.zh-CN.md
```

## 3. 当前后端模块结构

Java 后端目录：

```text
LegacyPilot/src/main/java/com/legacypilot
|-- onboarding
|   |-- controller
|   |-- dto
|   |-- service
|
|-- project
|   |-- controller
|   |-- dto
|   |-- entity
|   |-- service
|
|-- repository
|   |-- controller
|   |-- dto
|   |-- entity
|   |-- service
|
|-- codeanalysis
|   |-- context
|   |-- detector
|   |-- entity
|   |-- parser
|   |-- service
|
|-- incident
|-- task
|-- lcms
|-- workspace
|-- common
```

重点模块：

| 模块 | 作用 |
| --- | --- |
| `onboarding` | 一键接入项目来源，当前支持 LOCAL_PATH，预留 GIT_URL |
| `repository` | Git 元数据读取、文件扫描、仓库相关 API |
| `codeanalysis` | 当前自研代码分析算法 |
| `lcms` | 之前用于调用 Python/GitNexus 的客户端和 DTO，当前主链路暂时不走 |
| `workspace` | 临时内存存储，后续可替换为数据库 |

## 4. 当前 Code Analysis 能力

当前已经实现的能力：

```text
1. 扫描本地项目源码文件
2. 检测项目类型
3. 解析 Java 类和方法
4. 解析 Spring Controller 接口
5. 提取接口 path 和 HTTP method
6. 支持多 path、多 method 组合
7. 构建基础 node / edge / evidence
8. 返回 graph summary
```

主要实现文件：

```text
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/service/JavaCodeAnalysisService.java
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/parser/JavaSourceStructureParser.java
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/parser/SpringEndpointParser.java
```

### 4.1 SpringEndpointParser 已优化内容

`SpringEndpointParser` 当前支持：

```java
@GetMapping("/users")
@GetMapping(value = "/users")
@GetMapping(path = "/users")
@GetMapping({"/users", "/members"})
@RequestMapping(value = {"/api", "/internal"})
@RequestMapping(method = {RequestMethod.GET, RequestMethod.POST})
```

当前会生成：

```text
Controller Class node
Handler Method node
API Endpoint node

Controller Class -> Handler Method
Handler Method -> API Endpoint
```

同时会生成 evidence：

```text
spring_mapping_annotation
spring_handler_method
spring_controller_class
```

### 4.2 当前限制

现在自研算法还没有完全达到 GitNexus CLI 的图谱丰富度。

已知差距主要在 edge：

```text
当前 Java 自研 codeanalysis：
  可以识别基础结构和 Spring endpoint

GitNexus CLI：
  还能识别更多 method call、import、extends、implements、package、flow 等关系
```

所以如果你看到：

```text
nodeCount 接近
edgeCount 比 GitNexus 少很多
```

这是当前阶段的正常现象。下一步应该重点优化 `JavaSourceStructureParser`，增加：

```text
PACKAGE_CONTAINS_CLASS
CLASS_DECLARES_METHOD
CLASS_IMPORTS_TYPE
CLASS_EXTENDS_CLASS
CLASS_IMPLEMENTS_INTERFACE
METHOD_CALLS_METHOD
```

## 5. GitNexus CLI 当前状态

之前 GitNexus CLI 是通过 Python LCMS 间接调用的。现在为了测试自研 Java `codeanalysis`，GitNexus 调用已经暂时注释。

切换位置在：

```text
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/service/RepositoryCodeAnalysisService.java
```

当前正在执行的是：

```java
CodeAnalysisResult analysisResult =
        javaCodeAnalysisService.analyze(repository.repoId(), repository.localRepoPath());
```

旧的 GitNexus / LCMS 调用没有删除，而是保留在块注释里：

```java
/*
CodeKnowledgeGraphSnapshotResponse graphSnapshot =
        codeKnowledgeClient.indexRepository(repository.repoId(), repository.localRepoPath());

return new RepositoryGraphAnalysisResponse(
        repository.repoId(),
        graphSnapshot.graphId(),
        graphSnapshot.nodeCount(),
        graphSnapshot.edgeCount(),
        graphSnapshot.generatedAt()
);
*/
```

如果之后要切回 GitNexus，需要恢复：

```java
private final CodeKnowledgeClient codeKnowledgeClient;
```

构造器参数也要恢复：

```java
CodeKnowledgeClient codeKnowledgeClient
```

然后把当前 `JavaCodeAnalysisService` 调用注释掉。

## 6. 本地启动方式

当前测试自研 Java codeanalysis 时，只需要启动 Java 后端。

```powershell
cd D:\Hackathon\LegacyPilot
mvn.cmd spring-boot:run
```

默认端口：

```text
http://localhost:8080
```

健康检查：

```http
GET http://localhost:8080/api/analysis/status
```

当前不需要启动：

```text
D:\Hackathon\LCMS
```

除非你要测试 Python / GitNexus 旧链路。

## 7. Postman 调用方式

### 7.1 一键接入项目

请求地址：

```http
POST http://localhost:8080/api/onboarding/projects
Content-Type: application/json
```

LOCAL_PATH 推荐测试 Java 后端自身：

```json
{
  "projectName": "LegacyPilot",
  "sourceType": "LOCAL_PATH",
  "localRepoPath": "D:\\Hackathon\\LegacyPilot"
}
```

也可以测试整个 workspace：

```json
{
  "projectName": "Hackathon Workspace",
  "sourceType": "LOCAL_PATH",
  "localRepoPath": "D:\\Hackathon"
}
```

注意：`D:\Hackathon` 是 workspace 根目录，不是单独项目。当前代码已经尽量容错扫描，但最终应该新增 workspace/module discovery，而不是一直把 workspace 当成一个普通 repo。

GIT_URL 路径已经预留，但当前还没有实现 clone。测试时会返回 `501 Not Implemented`：

```json
{
  "projectName": "Remote Demo",
  "sourceType": "GIT_URL",
  "repositoryUrl": "https://github.com/owner/repository.git",
  "branch": "main",
  "cloneToLocal": true
}
```

### 7.2 成功返回结构

成功后会返回：

```json
{
  "project": {
    "projectId": "PROJ-...",
    "name": "LegacyPilot",
    "repositoryUrl": "...",
    "defaultBranch": "...",
    "createdAt": "..."
  },
  "repository": {
    "repoId": "REPO-...",
    "projectId": "PROJ-...",
    "sourceType": "LOCAL_PATH",
    "repositoryUrl": "...",
    "localRepoPath": "D:\\Hackathon\\LegacyPilot",
    "branch": "...",
    "commitSha": "...",
    "graphId": "GRAPH-REPO-...",
    "taskId": "TASK-...",
    "createdAt": "..."
  },
  "files": {
    "repoId": "REPO-...",
    "localRepoPath": "D:\\Hackathon\\LegacyPilot",
    "totalFiles": 57,
    "javaFiles": [],
    "pythonFiles": [],
    "configFiles": [],
    "buildFiles": [],
    "markdownFiles": []
  },
  "graph": {
    "repoId": "REPO-...",
    "graphId": "GRAPH-REPO-...",
    "nodeCount": 215,
    "edgeCount": 24,
    "generatedAt": "..."
  }
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `project` | LegacyPilot 内部项目容器 |
| `repository` | 本地 Git 仓库元数据 |
| `files` | 文件扫描摘要 |
| `graph` | 自研 Java codeanalysis 返回的图谱摘要 |

### 7.3 单独重新分析仓库

如果项目已经 onboarding 过，可以用：

```http
POST http://localhost:8080/api/repos/{repoId}/analyze
```

不需要请求体。

注意：Java 后端当前用内存存储，重启后旧 `repoId` 会失效，需要重新 onboarding。

## 8. 常见问题

### 8.1 返回 400：Failed to scan repository source files

这通常出现在扫描 workspace 根目录时，例如：

```json
{
  "localRepoPath": "D:\\Hackathon"
}
```

当前已经在这些位置做了容错扫描：

```text
JavaCodeAnalysisService
ProjectTypeDetector
RepositoryFileScannerService
```

如果仍然失败，看 Java 控制台中文日志。后续正式方案应该引入：

```text
ScanIssue
ScanIssueSeverity
WorkspaceScanService
ModuleDiscoveryService
```

不能只靠简单跳过文件。

### 8.2 返回的 edgeCount 比 GitNexus 少很多

这是当前自研算法能力范围导致的。现在主要有：

```text
Controller -> Handler Method
Handler Method -> API Endpoint
基础 Java class/method 节点
```

还没有完整实现：

```text
method call graph
import graph
extends/implements graph
package graph
service/repository dependency graph
```

所以 edge 数少是正常的，后续要继续增强 `JavaSourceStructureParser`。

### 8.3 为什么现在不需要启动 Python

因为当前主链路已经切到：

```text
RepositoryCodeAnalysisService -> JavaCodeAnalysisService
```

不是：

```text
RepositoryCodeAnalysisService -> CodeKnowledgeClient -> LCMS -> GitNexus
```

### 8.4 什么时候还需要 Python

Python 可以先保留，后续可能用于：

```text
Qwen 调用封装
RAG / 向量检索
prompt 编排
长文本切分
实验性分析工具
```

但如果 Agent 和 codeanalysis 都决定用 Java 实现，Python 暂时不是主流程必需服务。

## 9. 当前 API 列表

### 9.1 Onboarding

| Method | Path | 作用 |
| --- | --- | --- |
| `POST` | `/api/onboarding/projects` | 接入项目来源并触发 Java 自研代码分析；LOCAL_PATH 已可用，GIT_URL 预留 |

### 9.2 Repository

| Method | Path | 作用 |
| --- | --- | --- |
| `POST` | `/api/repos/connect` | 将本地仓库连接到已有 project |
| `GET` | `/api/repos/{repoId}/files` | 查看文件扫描结果 |
| `POST` | `/api/repos/{repoId}/analyze` | 重新运行代码分析 |

### 9.3 Project

| Method | Path | 作用 |
| --- | --- | --- |
| `POST` | `/api/projects` | 创建项目元数据 |
| `GET` | `/api/projects` | 查看当前内存中的项目 |

### 9.4 Incident / Task

| Method | Path | 作用 |
| --- | --- | --- |
| `POST` | `/api/incidents/analyze` | 创建 incident 分析任务占位 |
| `GET` | `/api/incidents/{incidentId}` | 查看 incident |
| `POST` | `/api/incidents/{incidentId}/confirm` | 确认 incident |
| `GET` | `/api/analysis/status` | 后端状态检查 |
| `GET` | `/api/analysis/{taskId}` | 查看任务状态 |

## 10. 后续开发建议

优先级建议：

1. 增强 `JavaSourceStructureParser`，补齐 package/class/method/import/extends/implements 关系。
2. 增加 `ScanIssue`，把跳过文件、不可读文件、重要文件失败都结构化返回给前端。
3. 增加 workspace/module discovery，支持扫描 `D:\Hackathon` 这种大目录。
4. 增加 graph detail API，返回完整 nodes/edges，而不是只有 summary。
5. 前端接入 onboarding API 和 graph summary。
6. 接入 Qwen，放到 Java Agent 或独立模型服务里。
7. 增加数据库，把当前内存 Map 替换成持久化表。

## 11. 常用命令

启动 Java：

```powershell
cd D:\Hackathon\LegacyPilot
mvn.cmd spring-boot:run
```

编译 Java：

```powershell
cd D:\Hackathon\LegacyPilot
mvn.cmd test
```

启动前端：

```powershell
cd D:\Hackathon\LegacyPilot-Frontend
npm.cmd run dev
```

Git 提交：

```powershell
cd D:\Hackathon
git status
git add .
git commit -m "Update Java code analysis documentation"
git push origin Hackathon
```
