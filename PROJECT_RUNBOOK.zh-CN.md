# LegacyPilot 运行说明

## 项目目录

```text
D:\Hackathon
|-- LegacyPilot              Java Spring Boot 后端
|-- LegacyPilot-Frontend     React + TypeScript 前端
|-- LCMS                     早期 Python/GitNexus 测试服务，当前主流程不依赖
```

## 后端启动

```powershell
cd D:\Hackathon\LegacyPilot
mvn.cmd spring-boot:run
```

默认地址：

```text
http://localhost:8080
```

## 前端启动

```powershell
cd D:\Hackathon\LegacyPilot-Frontend
npm.cmd install
npm.cmd run dev
```

默认地址：

```text
http://localhost:5173
```

## 基本测试流程

### 1. Onboarding 项目

先让后端知道当前要分析哪个项目：

```http
POST http://localhost:8080/api/onboarding/projects
```

Body：

```json
{
  "projectName": "LegacyPilot",
  "sourceType": "LOCAL_PATH",
  "localRepoPath": "D:\\Hackathon\\LegacyPilot"
}
```

说明：

```text
当前可用：LOCAL_PATH
已预留但未完成：GIT_URL
```

### 2. 测 Agent 主入口

```http
POST http://localhost:8080/api/agent/chat
```

RCA 示例：

```json
{
  "message": "order cancel 接口 500 报错",
  "maxCandidates": 3
}
```

接口探索示例：

```json
{
  "message": "这个项目有哪些接口"
}
```

代码图谱示例：

```json
{
  "message": "看一下代码图谱"
}
```

项目总结示例：

```json
{
  "message": "总结一下这个项目"
}
```

主要看返回里的：

```text
query              Agent 如何理解自然语言
toolResults        Agent 实际调用了哪些工具
agentContextText   给未来 Qwen 使用的上下文文本
```

当前还没接 Qwen，所以 `answer` 是占位文本。

## 后端模块说明

| 模块 | 功能 |
| --- | --- |
| `onboarding` | 接入项目来源，当前支持本地路径，预留 GitHub URL |
| `project` | 项目信息管理 |
| `repository` | 仓库信息、Git 元数据、文件扫描 |
| `codeanalysis` | 自研代码分析算法，生成节点、边、endpoint、evidence |
| `agenttool` | 给 Agent 使用的工具层 |
| `agent` | Agent 入口、规则调度、Qwen 接入边界 |
| `workspace` | 临时内存存储，后续可替换为数据库 |
| `incident` | 事故分析相关雏形 |
| `task` | 分析任务状态相关雏形 |
| `lcms` | 早期 Python/GitNexus 客户端遗留模块，当前主流程不依赖 |

## AgentTool 当前能力

| Tool | 状态 | 功能 |
| --- | --- | --- |
| `query.understand` | 可用 | 识别 intent、targetType、keywords、errorSignals、searchPlan |
| `endpoint.select` | 可用 | 根据自然语言选择候选 endpoint |
| `endpoint.list` | 可用 | 列出当前项目 endpoint |
| `endpoint.lookup` | 可用 | 按 path 查询 endpoint |
| `evidence.endpoint` | 可用 | 根据 endpoint 获取源码证据片段 |
| `code_graph.get_graph` | 可用 | 返回当前项目代码图谱 |
| `context.build` | 可用 | 生成 Agent 可读上下文文本 |
| `rca.investigate` | 可用 | 规则版 RCA 小闭环 |
| `trace.method_calls` | 未实现 | 需要后续补方法调用链算法 |
| `qwen.complete` | 未实现 | 需要后续接 Qwen |

## Agent 调度规则

`/api/agent/chat` 会先理解自然语言，再按 intent 选择工具：

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
-> 当前返回未实现
```

## 当前限制

```text
1. 没有数据库，Spring 重启后需要重新 onboarding
2. 还没接 Qwen，answer 是占位文本
3. GIT_URL 已预留但还不能 clone
4. codeanalysis 还没有完整方法调用链
5. 前端还没有完整绑定后端 API
```

## 常用命令

查看 Git 状态：

```powershell
cd D:\Hackathon
git status
```

提交当前改动：

```powershell
git add .
git commit -m "你的提交说明"
git push origin Hackathon
```
