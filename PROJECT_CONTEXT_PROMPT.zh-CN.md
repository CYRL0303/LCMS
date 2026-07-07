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
  - `POST /api/onboarding/projects`
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
- 第一版 MySQL 持久化：
  - `legacy_project`
  - `repository_index`
  - `analysis_task`
  - `code_analysis_snapshot`
  - `incident_record`
- Java Code Analysis Core：
  - JavaParser AST 地基第一版
  - class / method / endpoint 提取
  - Spring endpoint 识别
  - Controller / Service / Repository / Mapper / Component / Configuration 分类
  - 字段注入 / 构造器注入 / setter 注入基础识别
  - `CALLS` / `DECLARES` / `MAPS_TO_ENDPOINT` / `USES_*` 边
  - `endpoint trace` 第一版
  - SQL 注解最小闭环：`@Query` / `@Select` / `@Insert` / `@Update` / `@Delete`
- AgentTool：
  - `endpoint.select`
  - `endpoint.list`
  - `endpoint.lookup`
  - `evidence.endpoint`
  - `trace.endpoint`
  - `code_graph.get_graph`
  - `rca.investigate`
- 当前返回结构：

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
主流程已经不再依赖 Python mock 图谱。
Java 侧已经能生成真实 CodeAnalysisResult。
当前还没有接 Qwen，AgentModelClient 仍是 NoOp 占位。
当前 code_analysis_snapshot 仍存完整 JSON，nodes / edges / endpoints 尚未拆表。
当前 SQL 关系只做到 Method -> SQL Statement，还没有 SQL Statement -> Table。
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

下一步不要优先做前端，也不要优先接 Qwen。应该继续小步增强：

```text
Code Analysis Step 4.2：SQL Statement -> Table 最小闭环
```

只做最小范围：

```text
从当前已经识别到的 SQL Statement 文本中抽取简单表名。
支持：
- FROM table_name
- JOIN table_name
- UPDATE table_name
- INSERT INTO table_name
- DELETE FROM table_name

生成：
- Table 节点
- SQL Statement -> Table 的 TOUCHES_TABLE 边
```

明确不要做：

```text
不要做复杂 SQL parser
不要做 Mapper XML
不要做 jdbcTemplate 字符串 SQL
不要做 JPA 方法名推导
不要大改图谱结构
不要改数据库 schema，除非确实需要 Flyway migration
```

## 6. 当前核心算法范围

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

已经做到：

```text
扫描 .java 文件
识别 package / class / method
识别 @RestController / @Controller
识别 @RequestMapping / @GetMapping / @PostMapping
生成 endpoint node
生成 class -> method -> endpoint 的边
返回 nodeCount / edgeCount
生成 method call 关系
生成 endpoint trace
生成 SQL Statement 节点
生成 Method -> SQL Statement 的 EXECUTES_SQL 边
```

后续再加：

```text
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

`graph` 当前来自 Java Code Analysis Core，不再是 Python mock：

```text
CodeAnalysisResult summary
nodeCount
edgeCount
endpointCount
```

当前数据库已经接入第一版 MySQL / Flyway：

```text
legacy_project
repository_index
analysis_task
incident_record
code_analysis_snapshot
```

## 9. 推荐下一次开发任务

下一次开发请优先实现：

```text
Step 4.2：SQL table extraction minimal loop
```

目标：

```text
在 JavaSqlAnnotationParser 已产生 SQL Statement 的基础上：
从简单 SQL 文本抽取 table 名
生成 Table 节点
生成 SQL Statement -> Table 的 TOUCHES_TABLE 边
让 endpoint trace 可以走到 Table 节点
```

建议修改位置：

```text
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/parser/JavaSqlAnnotationParser.java
LegacyPilot/src/main/java/com/legacypilot/codeanalysis/service/EndpointTraceService.java
PROJECT_PROGRESS_SUMMARY.zh-CN.md
```

完成标准：

```text
mvn.cmd test 通过
重新 onboarding 后 graph 里出现 SQL Statement 和 Table 节点
trace.endpoint 的 matchedEdges 里出现 EXECUTES_SQL 和 TOUCHES_TABLE
PROJECT_PROGRESS_SUMMARY.zh-CN.md 记录当前状态
```

## 10. 一句话指导原则

```text
LegacyPilot 的核心竞争力不是调用 GitNexus，而是自己为 Java/Spring legacy 项目构建可追踪的代码事实图谱，再让 Agent 基于这些事实给维护建议。
```
