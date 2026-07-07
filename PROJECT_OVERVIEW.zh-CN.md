# LegacyPilot 项目总览

## 1. 项目一句话说明

LegacyPilot 是一个面向 Java/Spring 旧项目维护的 Agent 系统。

它的目标不是普通代码问答，而是：

```text
先分析一个 legacy repo
-> 抽取 endpoint、代码图谱、源码证据、调用关系等结构化事实
-> 把这些事实暴露成 Agent 可调用的工具
-> 让 Agent 根据用户自然语言选择工具
-> 未来接入 Qwen 生成 RCA、影响分析、维护建议和迁移计划
```

## 2. 为什么要这样设计

旧项目维护时，用户真正需要的不是“模型随便猜”，而是有证据的分析。

所以 LegacyPilot 分成三层：

```text
codeanalysis
负责分析代码，生成事实。

agenttool
负责把事实包装成 Agent 可调用的工具。

agent
负责理解用户问题、选择工具、组织上下文，并在未来调用 Qwen。
```

这三层的关系是：

```text
codeanalysis 产出事实
agenttool 查询和整理事实
agent 决定什么时候调用哪个工具
```

## 3. 当前整体架构

```text
Frontend
  -> Java Spring Boot Backend
      -> onboarding
          接入本地项目或未来 GitHub URL

      -> codeanalysis
          扫描 Java/Spring 项目
          生成 CodeAnalysisResult
          包含 endpoints / nodes / edges / evidenceRefs

      -> agenttool
          QueryUnderstandingTool
          EndpointSelectorTool
          EndpointLookupTool
          EvidenceTool
          CodeGraphTool
          ContextBuilderTool

      -> agent
          /api/agent/chat
          AgentToolDispatcherService
          AgentModelClient
          未来替换为 QwenAgentModelClient
```

## 4. 当前主流程

### 第一步：Onboarding

用户先告诉系统要分析哪个项目：

```text
POST /api/onboarding/projects
```

当前支持本地路径：

```json
{
  "projectName": "LegacyPilot",
  "sourceType": "LOCAL_PATH",
  "localRepoPath": "D:\\Hackathon\\LegacyPilot"
}
```

后端会：

```text
创建 project / repository
扫描文件
运行 codeanalysis
保存 CodeAnalysisResult 到内存
设置当前 repoId 给 Agent 使用
```

### 第二步：用户问 Agent

用户通过：

```text
POST /api/agent/chat
```

发送自然语言，例如：

```json
{
  "message": "这个项目有哪些接口"
}
```

### 第三步：Agent 选择工具

Agent 当前是规则版，不是 LLM 版。

流程是：

```text
用户自然语言
-> QueryUnderstandingTool 判断 intent / targetType / searchPlan
-> AgentToolDispatcherService 根据 intent 选择工具
-> 调用对应 agenttool
-> 生成 agentContextText
-> AgentModelClient
-> 返回结果
```

当前 intent 调度规则：

```text
RCA
-> rca.investigate

EXPLORE_ENDPOINT
-> endpoint.list

EXPLORE_GRAPH
-> code_graph.get_graph

SUMMARIZE_PROJECT
-> code_graph.get_graph
-> endpoint.list

LOOKUP_CODE
-> 当前未实现
```

## 5. 当前已经能做什么

当前系统已经能：

```text
接入本地 Java/Spring 项目
扫描项目文件
识别 Spring Controller 和 endpoint
生成基础 code graph
生成 endpoint evidenceRefs
根据自然语言判断用户意图
根据 intent 自动选择部分工具
返回 toolResults
生成 agentContextText
```

当前已经能用的工具：

```text
query.understand
endpoint.select
endpoint.list
endpoint.lookup
evidence.endpoint
code_graph.get_graph
context.build
rca.investigate
```

## 6. 当前还不能做什么

当前还没有：

```text
Qwen 调用
数据库持久化
GitHub URL clone
完整方法调用链
controller -> service -> repository 追踪
SQL / database 关系分析
前端完整 API 绑定
```

所以现在的 Agent 更准确地说是：

```text
规则版 Tool Agent / Rule-based Agent Orchestrator
```

不是最终的 LLM Agent。

## 7. 未来目标

未来理想流程是：

```text
用户输入问题
-> Agent 读取当前项目上下文
-> Qwen 判断需要调用哪些工具
-> 后端执行工具
-> Qwen 阅读 toolResults 和 agentContextText
-> 生成自然语言 RCA / 影响分析 / 修复建议
-> 后端校验证据引用
-> 返回给前端
```

优先级建议：

```text
P0 接入 QwenAgentModelClient
P0 实现 METHOD_CALLS_METHOD
P1 实现 trace.method_calls
P1 支持 GitHub URL clone
P1 接数据库
P2 前端绑定 Agent API
P2 图谱可视化
```

## 8. 新人阅读顺序

建议按这个顺序阅读：

```text
1. PROJECT_OVERVIEW.zh-CN.md
   先理解项目目标和整体架构

2. PROJECT_RUNBOOK.zh-CN.md
   学会怎么启动和测试

3. PROJECT_PROGRESS_SUMMARY.zh-CN.md
   查看当前进度和下一步任务

4. LegacyPilot/src/main/java/com/legacypilot
   阅读后端代码
```

重点代码入口：

```text
agent/controller/AgentChatController.java
agent/service/LegacyPilotAgent.java
agent/service/AgentToolDispatcherService.java
agenttool/query/service/QueryUnderstandingService.java
codeanalysis/service/JavaCodeAnalysisService.java
```
