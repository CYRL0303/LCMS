# LegacyPilot 项目上下文与下一步实施 Prompt

## 1. 项目核心定位

LegacyPilot 是一个面向老旧 Java/Spring 项目的维护 Agent。项目目标不是普通代码问答，而是让系统能读取 legacy repo，抽取代码结构、调用关系、SQL、配置、异常等证据，再基于这些结构化信息辅助故障分析、影响范围判断、迁移 checklist 和后续 RCA。

当前重点是 Track 4 Autopilot Agent，核心卖点是：

```text
为维护 Java/Spring 屎山项目提供代码理解、证据链和修改建议能力。
```

## 2. 当前已经实现的能力

Java 后端 `LegacyPilot` 已经实现：

- Spring Boot 后端基础框架。
- Controller 分层：
  - `ProjectController`
  - `RepositoryController`
  - `IncidentController`
  - `TaskController`
- 一键本地项目接入接口：
  - `POST /api/onboarding/local-project`
- 本地 Git 仓库识别：
  - local path
  - repository URL
  - branch
  - commit SHA
- 文件扫描：
  - Java files
  - Python files
  - config files
  - build files
  - markdown files
- Java 调 Python LCMS：
  - `CodeKnowledgeClient`
  - `POST /v1/repos/index`
- 返回结构：

```text
project + repository + files + graph
```

Python `LCMS` 已经实现：

- FastAPI contract middleware。
- `/v1/repos/index`、`/v1/graph/query` 等接口。
- Pydantic contract。
- mock `GraphSnapshot` 返回。
- GitNexus 适配相关框架代码。

当前问题：

```text
Java -> Python 链路已经通了，但 Python 返回的是 mock 图谱，不是真实代码解析结果。
```

## 3. 关键架构共识

核心 Java/Spring 代码解析算法应该优先放在 Java 侧实现。

原因：

- 目标项目主要是 Java/Spring 老系统。
- Java 生态更适合做 Java AST / annotation / Maven / MyBatis / method relation 解析。
- JavaParser、Spoon、Eclipse JDT 等工具比 Python regex 更适合复杂 Java 语法。
- 这更符合项目“维护 Java legacy system”的技术亮点。

推荐分工：

```text
Java Backend
  - 项目管理
  - 仓库管理
  - 任务管理
  - incident 管理
  - Java/Spring/MyBatis 核心代码解析算法
  - 输出标准 nodes / edges / evidence_refs

Python LCMS
  - contract middleware
  - RAG / LLM / Qwen / Agent 上下文组织
  - 图谱查询增强
  - 接收 Java 生成的结构化代码图谱

Frontend / TypeScript
  - 用户输入项目
  - 展示 onboarding 状态
  - 后续展示图谱、RCA、建议和 Agent 对话
```

## 4. 推荐目标架构

```text
Frontend
  -> Java Spring Backend
      -> Project / Repository / Task / Incident APIs
      -> Java Code Analysis Core
          -> Java/Spring parser
          -> MyBatis/XML parser
          -> SQL/config/exception extractor
          -> GraphSnapshot builder
      -> Python LCMS
          -> contract validation
          -> RAG / LLM / Agent reasoning
```

不要让前端直接调用 Python。

不要把核心 Java/Spring 解析算法放到 Python mock adapter 里。

Python 可以继续保留为 AI/RAG/contract 层，但真正“读懂 Java 项目”的核心能力应该逐步迁移到 Java。

## 5. 下一步最重要的实现方向

下一步不要优先做前端，也不要优先做完整 Agent。应该先做：

```text
Java Code Analysis Core MVP
```

建议新增模块位置：

```text
LegacyPilot/src/main/java/com/legacypilot/codeanalysis
```

建议子包：

```text
codeanalysis/
  parser/
    JavaSourceParser.java
    SpringAnnotationParser.java
    MyBatisXmlParser.java
  model/
    CodeNode.java
    CodeEdge.java
    EvidenceRef.java
    CodeGraph.java
  service/
    JavaCodeAnalysisService.java
    CodeGraphBuilder.java
```

## 6. 第一版核心算法范围

第一版不要做太大。先支持 Java/Spring 最小闭环：

### 需要识别的节点

```text
File
Package
Class
Method
API Endpoint
Service
Mapper
SQL Statement
Table
Config
Exception
```

### 需要识别的边

```text
DECLARES
MAPS_TO_ENDPOINT
CALLS
USES_SERVICE
USES_MAPPER
EXECUTES_SQL
READS_CONFIG
THROWS_EXCEPTION
DEFINED_IN
```

### 第一版最小可交付

先做到：

```text
扫描 .java 文件
识别 package / class / method
识别 @RestController / @Controller
识别 @RequestMapping / @GetMapping / @PostMapping
生成 endpoint node
生成 class -> method -> endpoint 的边
返回 nodeCount / edgeCount
```

然后再加：

```text
Service
Mapper
MyBatis XML
SQL table
Exception
Config
```

## 7. Java 与 Python 的连接方式建议

短期可以保留当前链路：

```text
Java onboarding
  -> Java 自己扫描/解析代码
  -> Java 生成 graph summary
  -> Java 继续调用 Python 做 contract/RAG/后续 AI 处理
```

中期更合理的方式：

```text
Java Code Analysis Core
  -> 输出 GraphSnapshot-compatible JSON
  -> Python LCMS 接收这个结构化图谱
  -> Python 负责 query / RAG / LLM / Agent
```

也就是说：

```text
Java 负责产生事实
Python 负责组织事实并推理
```

## 8. 当前代码里需要注意的点

当前 `POST /api/onboarding/local-project` 返回：

```text
project
repository
files
graph
```

但是 `graph` 现在来自 Python mock：

```text
GRAPH-DEMO
2 nodes
1 edge
```

后续 Java Code Analysis Core 实现后，`graph` 应该来自 Java 自己解析出的真实结果，或者由 Java 解析后传给 Python 归一化。

当前 Java 内存数据会在重启后丢失。之后需要 SQL：

```text
legacy_project
repository_index
analysis_task
incident_record
```

## 9. 推荐下一次开发任务

下一次开发请优先实现：

```text
JavaCodeAnalysisService
```

目标：

```text
输入 repoId 或 localRepoPath
扫描 Java 文件
提取 class / method / endpoint
生成 CodeGraph
返回真实 nodeCount / edgeCount
```

推荐先不要引入复杂 AST 依赖，第一版可以先用规则解析和注解扫描跑通结构。等闭环跑通后，再引入 JavaParser 或 Spoon 提升准确率。

第一版完成标准：

```text
给一个 Spring Boot 项目路径
接口能返回真实 endpoint 数量、class 数量、method 数量
不再返回 GRAPH-DEMO
```

## 10. 一句话指导原则

```text
LegacyPilot 的核心竞争力不是调用 GitNexus，而是自己为 Java/Spring legacy 项目构建可追踪的代码事实图谱，再让 Agent 基于这些事实给维护建议。
```
