# LegacyPilot 当前进度摘要

> 新人先读 `PROJECT_OVERVIEW.zh-CN.md`，再读本文。本文只记录当前做到哪里、哪些已完成、下一步做什么。

## 当前状态

项目现在已经有一个规则版 Agent 小闭环，并且已经接入第一版 MySQL 持久化：

```text
用户自然语言
-> /api/agent/chat
-> QueryUnderstandingTool 判断 intent / targetType / searchPlan
-> AgentToolDispatcherService 根据 intent 选择工具
-> 调用对应 agenttool
-> 生成 agentContextText
-> AgentModelClient
-> 返回 answer + query + toolResults + agentContextText
```

当前还没有接 Qwen，`answer` 由 `NoOpAgentModelClient` 返回占位文本。真正有价值的结果主要看：

```text
query
toolResults
agentContextText
```

数据库当前状态：

```text
MySQL / Redis 已部署在阿里云 ECS Docker
本地开发通过 SSH 隧道连接云 MySQL
Flyway 已负责建表和迁移
project / repository / task / code analysis snapshot 已经可以写入 MySQL
onboarding 已有第一版幂等逻辑，避免重复创建同名项目和同一仓库记录
```

## 已完成能力

### 1. Onboarding

可通过本地路径登记并分析项目：

```text
POST /api/onboarding/projects
POST /api/onboarding/local-project  （兼容旧 Postman / 前端路径）
```

当前可用：

```text
LOCAL_PATH
```

已预留但未完成：

```text
GIT_URL clone
```

### 2. Code Analysis

已经有自己的 Java/Spring 分析逻辑，能生成 `CodeAnalysisResult`。

当前能识别：

```text
Java 文件
Java class / method
Spring Controller
Spring endpoint
endpoint method/path/controller/handler
endpoint evidenceRefs
基础 code graph nodes/edges
源码 filePath + lineNumber
Controller / Service / Repository / Mapper / Component / Configuration
字段注入和构造器注入的基础依赖
DECLARES / MAPS_TO_ENDPOINT / USES_SERVICE / USES_REPOSITORY / USES_COMPONENT / CALLS
```

当前还不完整：

```text
方法调用链准确率还不够
controller -> service -> repository 还没有完整 trace API
SQL / database 关系
入口 endpoint 的影响面收敛
```

当前算法定位：

```text
可演示的 V1 结构分析算法。
能生成基础代码结构图和初级调用关系。
JavaSourceAnalyzer 已经完成第一步 AST 化：从正则扫描切换到 JavaParser 解析 Java 源文件。
当前只是 AST 地基完成，不代表 GitNexus 强度的完整图谱算法已经完成。
```

当前算法限制：

```text
1. AST 解析已开始，但还只是第一层源码结构提取
2. 方法重载分不清，只按 methodName 匹配
3. 只能较稳定识别 receiver.method() 这种调用
4. 对链式调用支持弱，例如 userService.find().map()
5. 对 this.xxx、内部类、lambda、静态方法支持弱
6. Spring Bean 注入只支持字段/构造器的基础形式
7. 还没有 SQL / Mapper XML / JPA query 关系
8. 还没有 endpoint -> service -> repository 的完整 trace API
9. 还没有按入口 endpoint 做影响面收敛
```

GitNexus 借鉴方向：

```text
不直接把 GitNexus CLI 接进主流程。
借鉴它的结构图思想：Node / Edge / EvidenceRef / GraphSnapshot / Query / Context / Trace / Impact。
LegacyPilot 自己实现 Java/Spring 分析算法。
已经选择 JavaParser 做第一版 AST 地基，后续继续补调用链、trace、SQL、影响面分析。
```

### 3. AgentTool

当前已经实现并能被 Agent 使用的工具：

```text
QueryUnderstandingTool
EndpointSelectorTool
EndpointLookupTool
EvidenceTool
EndpointTraceTool
CodeGraphTool
RCA Investigation
agentContextText 生成逻辑
```

已登记但还没真正实现：

```text
qwen.complete
```

还没做成正式工具：

```text
NodeLookupTool
RepositoryContextTool
IncidentContextTool
RcaDraftingTool
```

### 4. Agent 调度

Agent 主入口：

```text
POST /api/agent/chat
```

当前规则调度：

```text
RCA
-> RcaInvestigationService
-> EndpointSelectorTool
-> EndpointLookupTool
-> EndpointTraceTool
-> EvidenceTool

EXPLORE_ENDPOINT
-> EndpointLookupTool

EXPLORE_GRAPH
-> CodeGraphTool

SUMMARIZE_PROJECT
-> CodeGraphTool
-> EndpointLookupTool

LOOKUP_CODE
-> 暂时返回 not implemented

UNKNOWN
-> 返回需要更明确的问题
```

## 需要注意

如果用 `LegacyPilot` 自己作为测试项目，然后问：

```text
order cancel 接口 500 报错
```

候选 endpoint 可能全部是 `score=0`。这是因为当前被分析项目里没有 `order cancel` 业务接口，不是 Agent 调度错误。

## 下一步

### 0. 给接手 AI / 组员的执行说明

如果你是另一个 AI 或组员来接手这个分支，先按这里做，不要重新设计方向。

当前分支的主线目标：

```text
继续增强 LegacyPilot 自己的 Java/Spring Code Analysis 算法。
每做出一个稳定算法能力，就必须接入 AgentTool 或现有 RCA/trace 流程。
不要把 GitNexus CLI 直接接进主流程。
不要优先做前端大改。
不要优先接 Qwen，除非图谱事实层已经足够稳定。
```

当前已完成到：

```text
AST 地基第一版
基础 endpoint / class / method / CALLS 图谱
endpoint trace API
trace.endpoint AgentTool
RCA 流程接入 trace
SQL 注解最小闭环：@Query / @Select / @Insert / @Update / @Delete -> SQL Statement
trace.endpoint 可沿 CALLS + EXECUTES_SQL 走到 SQL Statement
```

下一步唯一推荐任务：

```text
Step 4.2：在最小范围内补 table 抽取。
只从当前已识别的 SQL Statement 文本里提取简单表名。
只支持最常见 SQL：
- FROM table_name
- JOIN table_name
- UPDATE table_name
- INSERT INTO table_name
- DELETE FROM table_name

生成：
- Table 节点
- SQL Statement -> Table 的 TOUCHES_TABLE 边

不要做复杂 SQL parser。
不要做 Mapper XML。
不要做 jdbcTemplate 字符串 SQL。
不要做 JPA 方法名推导。
```

Step 4.2 完成后必须验证：

```text
mvn.cmd test
重启 Spring Boot
重新调用 POST /api/onboarding/local-project
再调用 trace.endpoint 或 /api/code-analysis/repos/{repoId}/endpoint-trace
确认 matchedNodes 里能看到 SQL Statement 和 Table
确认 matchedEdges 里能看到 EXECUTES_SQL 和 TOUCHES_TABLE
```

文档更新规则：

```text
每完成一个小功能，必须更新本文对应 Step 的“当前状态”。
如果新增算法能力，也要写清楚是否已接入 AgentTool。
如果没有接入 AgentTool，要明确说明原因和下一步接入点。
如果改了数据库结构，必须新增 Flyway migration，并在本文记录。
```

### 1. 接入 Qwen

把当前占位的：

```text
NoOpAgentModelClient
```

替换或扩展为：

```text
QwenAgentModelClient
```

让 Qwen 读取 `agentContextText` 并生成自然语言回答。

### 2. 增强 Code Analysis

按本文后面的“Code Analysis 算法升级计划”逐项推进。

当前优先级：

```text
1. 验证并收敛 AST 第一版输出
2. 补 endpoint trace API
3. 增强 Java 调用解析：this / static / chained call / lambda / 内部类
4. 补 SQL / Mapper XML / JPA query 关系
5. 做 endpoint 入口影响面分析
6. 最后再接 Qwen，让模型读取更稳定的图谱上下文
```

### 3. 补正式工具

后续按需要补：

```text
NodeLookupTool
RepositoryContextTool
IncidentContextTool
RcaDraftingTool
```

### 4. 数据持久化

第一版 MySQL 持久化已经完成：

```text
legacy_project
repository_index
analysis_task
code_analysis_snapshot
incident_record
```

当前已接数据库：

```text
project 创建 / 查询
repository 连接 / 查询
task 保存 / 查询
code analysis snapshot 保存 / 查询最新结果
```

当前仍需完善：

```text
incident_record 还没完全切到 JDBC
AgentContextStore 仍是进程内当前 repoId
用户模块未实现，当前 owner_id 使用 local-dev 占位
code_analysis_snapshot 暂时存完整 JSON，后续算法稳定后再考虑拆 nodes / edges / endpoints 表
```

### 5. GitHub URL 支持

实现：

```text
public GitHub URL 校验
clone 到本地工作目录
复用现有 codeanalysis
保存项目来源信息
```

### 6. Code Analysis 算法升级计划

目标不是一次性复刻 GitNexus，而是借鉴它的图谱思想，把 LegacyPilot 自己的 Java/Spring 分析能力逐步做实。

当前原则：

```text
先保证事实图谱可靠，再做 Agent 推理。
先做 endpoint trace 和 impact，因为它们最能体现竞赛项目价值。
每一步都要能通过 onboarding + MySQL snapshot 验收。
每新增一个稳定算法能力，都要接成 AgentTool，否则只能算调试接口，不能进入产品闭环。
```

建议顺序如下：

#### Step 0：AST 地基第一版

目标：

```text
把 JavaSourceAnalyzer 从正则扫描切换为 JavaParser AST 解析
继续保持 JavaProjectModel 作为内部契约
不破坏 CodeAnalysisResult 的外部 JSON 结构
提取 package / import / class / annotation / field / constructor / method / method call
```

当前状态：

```text
已完成第一版。
pom.xml 已加入 javaparser-core。
JavaSourceAnalyzer 已替换为 AST-based parser。
mvn clean test 已通过。
```

验收：

```text
Postman 调用 /api/onboarding/local-project 能成功生成 graph
code_analysis_snapshot 能写入最新 snapshot
nodeCount / edgeCount / endpointCount 不出现明显异常下降
原有 endpoint / class / method / edge 结构仍能被前端和 AgentTool 使用
```

#### Step 1：稳定调用图边的语义

目标：

```text
让 CALLS / USES_* 的语义更清楚
减少重复边和明显错误边
统一 node type / edge type 命名
区分“类依赖关系”和“方法调用关系”
```

重点处理：

```text
Controller -> Service
Service -> Repository / Mapper
同类内部调用
this.method()
ClassName.staticMethod()
```

当前状态：

```text
已完成第一处收敛：JavaMethodInfo 记录 parameterCount / parameterTypes。
已完成第一处收敛：JavaMethodCallInfo 记录 argumentCount。
CALLS 目标方法现在优先按 methodName + argumentCount 匹配，找不到再退回 methodName。
外部 method nodeId 暂时仍保持 repoId:METHOD:file#methodName，避免破坏 endpoint 节点连接。
```

验收：

```text
对 LegacyPilot 自身跑 onboarding 后，能看到稳定的 Controller / Service / Repository 链路
同一个 endpoint 能找到对应 Handler Method
Handler Method 至少能追到直接调用的 Service Method
每条 CALLS 边尽量带 evidence：filePath + lineNumber
```

#### Step 2：补 endpoint trace API

目标：

```text
输入 endpointId 或 method/path
返回 endpoint -> handler -> service -> repository 的路径
```

建议接口：

```text
GET /api/code-analysis/repos/{repoId}/endpoint-trace?endpointId={endpointId}
GET /api/code-analysis/repos/{repoId}/endpoint-trace?httpMethod=GET&path=/api/example
```

当前状态：

```text
已完成第一版 EndpointTraceService。
已完成第一版 HTTP 接口：/api/code-analysis/repos/{repoId}/endpoint-trace。
已完成 AgentTool 接口：POST /api/agent/tools/trace/endpoint。
已在 AgentToolCatalog 登记 trace.endpoint，状态为 implemented。
已接入 RCA 流程：每个 endpoint candidate 现在会附带 trace 结果。
支持通过 endpointId 查询，也支持通过 httpMethod + path 查询。
当前 trace 会从 endpoint 反查 handler method，再沿 CALLS 边向下追踪。
endpointId 使用 query 参数传递，因为 endpointId 内部可能包含 /，不适合直接放 path variable。
```

验收：

```text
返回 graphPaths / matchedNodes / matchedEdges / evidenceRefs
每条边都有 filePath + lineNumber 证据
AgentTool 后续可以直接调用这个 trace 结果，不需要自己重新拼图
```

#### Step 3：增强 Java 调用解析深度

目标：

```text
方法重载从只按 methodName 匹配，升级到 methodName + 参数数量/类型的基础签名匹配
增强链式调用识别，例如 userService.find().map()
增强 lambda / method reference / 内部类的识别
增强构造器注入、字段注入、setter 注入的 Bean 关系
```

当前状态：

```text
已完成链式调用 receiver 第一版收敛：userService.find().map() 这类表达式会优先取根 receiver。
已补 MethodReferenceExpr：例如 users.forEach(userService::save) 可以提取 userService.save。
已补 @Autowired setter 注入第一版：setXxx(Type xxx) 会补充依赖关系。
lambda 内部的普通 method call 已由 JavaParser findAll(MethodCallExpr) 覆盖。
内部类 / 匿名内部类还没有完整展开，后续单独处理。
```

验收：

```text
CALLS 边数量增加，但明显误报不增加
方法级 evidence 能定位到调用行
复杂调用不会导致整份文件解析失败
```

#### Step 4：补 SQL / Mapper / JPA 关系

目标：

```text
识别 MyBatis Mapper interface / XML
识别 @Query
识别 JDBC SQL 字符串
识别 repository/mapper 到 SQL/table 的关系
生成 REPOSITORY_EXECUTES_SQL / MAPPER_EXECUTES_SQL / TOUCHES_TABLE
```

当前状态：

```text
已完成最小闭环 Step 4.1：JavaSqlAnnotationParser。
当前只识别方法注解 SQL：@Query / @Select / @Insert / @Update / @Delete。
当前会生成 SQL Statement 节点。
当前会生成 Method -> SQL Statement 的 EXECUTES_SQL 边。
trace.endpoint 已支持继续沿 CALLS + EXECUTES_SQL 追踪，因此路径可以走到 SQL Statement。
暂不处理 Mapper XML。
暂不处理 jdbcTemplate 字符串 SQL。
暂不抽取 table 节点，TOUCHES_TABLE 后续再做。
```

验收：

```text
service -> repository -> SQL/table 的路径可被 Agent 使用
RCA 时能把数据库相关错误关联到 repository/mapper/sql evidence
```

#### Step 5：影响面分析

目标：

```text
从 endpoint、method、class、repository、SQL/table 任一节点出发
计算上下游影响范围
支持 downstream / upstream / both
支持 maxDepth
```

验收：

```text
返回 impactNodes / impactEdges / graphPaths
能回答“改这个 service 会影响哪些 endpoint”
能回答“这个接口会碰到哪些 repository / SQL”
```

#### Step 6：图谱持久化拆表

目标：

```text
当前 code_analysis_snapshot 先存完整 JSON
算法稳定后拆出 graph_node / graph_edge / graph_endpoint / graph_evidence 表
支持按 repoId / projectId / nodeId 快速查询
```

验收：

```text
不用每次反序列化完整 JSON 才能查图
trace / impact / endpoint lookup 都能直接查数据库
保留 snapshot JSON 作为回放和调试依据
```

#### Step 7：接 Qwen 做基于图谱的回答

目标：

```text
把 NoOpAgentModelClient 替换或扩展为 QwenAgentModelClient
让 Qwen 读取 endpoint trace / evidence / impact 结果
生成自然语言 RCA、影响分析、修改建议
```

验收：

```text
模型回答必须引用具体 endpoint / class / method / evidence
不能只输出泛泛建议
Agent 返回 answer + toolResults + agentContextText，便于调试
```
