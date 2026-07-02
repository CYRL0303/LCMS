# LegacyPilot 当前进度与下一步

## 已完成

### 1. Code Analysis 第一版闭环

后端已经可以通过 onboarding 触发本地项目分析：

```text
POST /api/onboarding/projects
```

当前流程：

```text
读取项目来源
-> LOCAL_PATH：读取本地项目路径
-> GIT_URL：预留 Git clone 流程
-> 创建 project / repository
-> 扫描源文件
-> 运行 Java codeanalysis
-> 生成 CodeAnalysisResult
-> 保存当前 repo 上下文给 Agent 使用
```

### 2. Graph Tool 第一轮测试

已完成当前项目代码图谱读取入口：

```text
GET /api/agent/tools/code-graph/graph
```

用途：

```text
让 Agent 或调试工具读取当前 onboarding 项目的完整代码分析结果。
```

当前问题：

```text
返回 JSON 较大，不适合直接全部喂给 Agent。
后续需要做一层摘要整理，把 graph JSON 转成 Agent 更容易理解的文本上下文。
```

### 3. Endpoint Tool 第一轮测试

已完成 endpoint 工具的两个入口：

```text
GET /api/agent/tools/endpoints
POST /api/agent/tools/endpoints/endpoint
```

功能区别：

```text
GET /endpoints
返回当前项目所有 endpoint 上下文。

POST /endpoints/endpoint
根据 path 精确查询某一个 endpoint 的 controller、method、file、line、evidence。
```

说明：

```text
现在 Postman 测试时还需要手动传 path。
后续真正接入 Agent 后，path 应该由 Agent 根据自然语言和 endpoint 列表自动选择。
```

### 4. Evidence Tool 第一版雏形

已完成根据 endpointId 读取证据和源码片段：

```text
POST /api/agent/tools/evidence/endpoint
```

当前流程：

```text
输入 endpointId
-> 读取当前 repo 的 CodeAnalysisResult
-> 找到对应 CodeEndpoint
-> 读取 endpoint.evidenceRefs
-> 根据 filePath + startLine 截取源码片段
-> 返回 evidence items 和 codeSnippet
```

当前能力边界：

```text
EvidenceTool 现在只负责“给定 endpointId 后取证据”。
它还不会自动判断哪个 endpoint 有问题。
它返回的仍然是结构化 JSON，不是自然语言解释。
```

## 下一步目标

### 1. 做 Agent 可读摘要

当前 graph、endpoint、evidence 返回的是结构化 JSON，但内容可能太多，也不够像自然语言上下文。

下一步需要新增一个整理层，把 JSON 转成更适合 Agent 阅读的文本摘要，例如：

```text
项目类型
主要 package
主要 controller
endpoint 列表摘要
endpoint -> controller method 映射
关键 evidence 引用
关键源码片段
当前缺失信息或分析限制
```

目标不是替代 JSON，而是让 Agent 先读摘要，再按需调用具体工具查详情。

### 2. 做 Agent Endpoint 选择逻辑

现在工具还不能自动定位“用户说的是哪个接口”。

需要新增 Agent 编排逻辑：

```text
用户自然语言问题
-> 读取所有 endpoint
-> 根据 path / controller / method / 关键词匹配候选 endpoint
-> 自动调用 EvidenceTool 取证据
```

第一版可以先做规则匹配，不必马上接 Qwen。

### 3. 继续增强 Evidence Tool

当前 EvidenceTool 只支持 endpointId。

后续补：

```text
根据 evidenceId 查询单条证据
根据 nodeId 查询 class / method 证据
合并同一文件相邻证据片段
增加 reason 字段，把证据用途解释清楚
```

RCA 后续必须依赖 evidence，而不是只看 graph 节点和边。

### 4. 优化 Code Analysis 算法

当前算法已经能识别部分 Java / Spring 信息，但图谱关系还不够丰富。

后续优先补：

```text
PACKAGE_CONTAINS_CLASS
CLASS_DECLARES_METHOD
CLASS_IMPORTS_TYPE
CLASS_EXTENDS_CLASS
CLASS_IMPLEMENTS_INTERFACE
```

再往后补：

```text
METHOD_CALLS_METHOD
FIELD_INJECTS_BEAN
SERVICE_USES_REPOSITORY
REPOSITORY_EXECUTES_SQL
```

### 5. 后续再接 Agent / Qwen

短期先做规则版小 Agent，验证工具调用链。

理想流程：

```text
用户自然语言问题
-> Agent 读取项目摘要 / endpoint 候选
-> Agent 调用 endpoint / graph / evidence 工具
-> Agent Context Builder 把 JSON 整理成文本上下文
-> 组装 EvidenceBundle
-> Qwen 生成 RCA 初稿
-> 后端校验证据引用
```

### 6. 后续实现 GitHub URL Clone

当前 onboarding 已经预留两种来源：

```text
LOCAL_PATH：已可用，直接分析用户提供的本地路径
GIT_URL：已预留入口，后续实现 clone 后再分析本地路径
```

GitHub URL 模式还需要补：

```text
public URL 校验
clone 到本地工作区
复用现有 codeanalysis
保存项目来源信息
```
