# LegacyPilot 当前进度与下一步

## 已完成

### 1. Code Analysis 第一版闭环

后端已经可以通过 onboarding 触发本地项目分析：

```text
POST /api/onboarding/local-project
```

当前流程：

```text
读取本地项目路径
-> 创建 project / repository
-> 扫描源文件
-> 运行 Java codeanalysis
-> 生成 CodeAnalysisResult
-> 保存当前 repo 上下文给 Agent 使用
```

### 2. Graph Tool 第一轮测试

已完成当前项目代码图谱读取入口：

```text
GET /api/agent/tools/code-graph/current
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

## 下一步目标

### 1. 做 Agent 可读摘要

当前 graph 和 endpoint 返回的是结构化 JSON，但内容可能太多。

下一步需要新增一个整理层，把 JSON 转成更适合 Agent 阅读的文本摘要，例如：

```text
项目类型
主要 package
主要 controller
endpoint 列表摘要
endpoint -> controller method 映射
关键 evidence 引用
当前缺失信息或分析限制
```

目标不是替代 JSON，而是让 Agent 先读摘要，再按需调用具体工具查详情。

### 2. 做 Evidence Tool

Evidence Tool 的核心目标：

```text
根据 endpointId / evidenceId / nodeId 返回可读证据。
```

第一版重点：

```text
文件路径
行号
证据类型
相关 endpoint / class / method
附近代码片段
```

RCA 后续必须依赖 evidence，而不是只看 graph 节点和边。

### 3. 优化 Code Analysis 算法

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

### 4. 后续再接 Agent / Qwen

短期先做规则版小 Agent，验证工具调用链。

理想流程：

```text
用户自然语言问题
-> Agent 读取项目摘要
-> Agent 调用 endpoint / graph / evidence 工具
-> 组装 EvidenceBundle
-> Qwen 生成 RCA 初稿
-> 后端校验证据引用
```

### 5. 后续支持 GitHub URL

当前主要支持本地路径。

后续需要支持：

```text
LOCAL_PATH
GIT_URL
```

GitHub URL 模式需要补：

```text
public URL 校验
clone 到本地工作区
复用现有 codeanalysis
保存项目来源信息
```
