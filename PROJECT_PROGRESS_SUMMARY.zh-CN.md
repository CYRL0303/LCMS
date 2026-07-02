# LegacyPilot 当前进度摘要

## 当前状态

项目现在已经有一个规则版 Agent 小闭环：

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

## 已完成能力

### 1. Onboarding

可通过本地路径登记并分析项目：

```text
POST /api/onboarding/projects
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
Spring Controller
Spring endpoint
endpoint method/path/controller/handler
endpoint evidenceRefs
基础 code graph nodes/edges
源码 filePath + lineNumber
```

当前还不完整：

```text
方法调用链
controller -> service
service -> repository
SQL / database 关系
```

### 3. AgentTool

当前已经实现并能被 Agent 使用的工具：

```text
QueryUnderstandingTool
EndpointSelectorTool
EndpointLookupTool
EvidenceTool
CodeGraphTool
RCA Investigation
agentContextText 生成逻辑
```

已登记但还没真正实现：

```text
trace.method_calls
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

优先补：

```text
METHOD_CALLS_METHOD
```

然后再补：

```text
FIELD_INJECTS_BEAN
SERVICE_USES_REPOSITORY
REPOSITORY_EXECUTES_SQL
```

目标是让 `TRACE_METHOD_CALLS` 真正可用。

### 3. 补正式工具

后续按需要补：

```text
NodeLookupTool
RepositoryContextTool
IncidentContextTool
RcaDraftingTool
```

### 4. 数据持久化

当前 project、repository、analysis result、agent context 都主要在内存里。后续需要接数据库，否则 Spring 重启后需要重新 onboarding。

### 5. GitHub URL 支持

实现：

```text
public GitHub URL 校验
clone 到本地工作目录
复用现有 codeanalysis
保存项目来源信息
```
