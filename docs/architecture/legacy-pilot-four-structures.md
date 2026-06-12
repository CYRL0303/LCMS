# LegacyPilot 四个核心结构拆分

## 1. 设计目标

LegacyPilot 不应被设计成普通的代码图谱问答工具，而应围绕一个明确闭环：

```text
legacy repo + 报警/日志
-> 代码图谱定位
-> 历史故障召回
-> RCA 分析
-> Reviewer 审查
-> 根因报告 + 修复建议 + 迁移 checklist
-> 用户确认后保存 incident memory
```

为了降低 MVP 复杂度，系统先拆成 4 个尽量原子的结构。每个结构只负责一个核心问题，并通过中间件定义的标准接口通信。

## 2. 总体结构

```text
                  +-----------------------------+
                  | Interface Contract Middleware |
                  +--------------+--------------+
                                 |
        +------------------------+------------------------+
        |                        |                        |
+-------v--------+      +--------v---------+      +-------v--------+
| Code Knowledge |      | Incident Context |      | RCA Reasoning  |
| Core           |      | Builder          |      | Engine         |
+-------+--------+      +--------+---------+      +-------+--------+
        |                        |                        |
        +------------------------+------------------------+
                                 |
                         +-------v--------+
                         | Incident Memory |
                         | & Report Store |
                         +----------------+
```

## 3. Structure 1: Code Knowledge Core

### 3.1 职责

Code Knowledge Core 负责把 legacy repo 转换成可查询、可追溯的代码知识。

它应生成两层图谱：

- Structural Graph：由 parser / tree-sitter / JavaParser 抽取的高置信结构事实。
- Semantic Graph：由 LLM 辅助抽取的业务语义、隐式依赖、数据流和副作用。

### 3.2 负责的事情

- 导入 legacy repo。
- 解析文件、模块、包、类、方法、接口路径、SQL、配置、异常。
- 抽取调用关系、继承/实现关系、Controller 到 Service 到 Mapper 到 SQL 的路径。
- 为每个节点、边、代码片段保留 evidence。
- 提供图查询接口，支持按日志线索、类名、方法名、endpoint、异常类型查找相关路径。

### 3.3 不负责的事情

- 不直接判断事故根因。
- 不生成最终 RCA 报告。
- 不保存 incident memory。
- 不自动修改生产代码。

### 3.4 核心输入

```text
RepoIndexRequest
- repo_id
- repo_path or repo_archive
- language_hint
- parser_profile
- contract_version
```

### 3.5 核心输出

```text
GraphSnapshot
- graph_id
- repo_id
- generated_at
- nodes[]
- edges[]
- evidence_refs[]
- parser_version
- semantic_enrichment_version
```

### 3.6 最小节点类型

```text
File
Module / Package
Class
Method
API Endpoint
Service
Mapper
SQL
Table
Config
Exception
Business Concept
Function Semantic Summary
Data Flow / State Change
```

### 3.7 最小边类型

```text
DECLARES
CALLS
MAPS_TO_ENDPOINT
USES_MAPPER
EXECUTES_SQL
READS_TABLE
WRITES_TABLE
THROWS_EXCEPTION
MENTIONED_IN_LOG
IMPLEMENTS
EXTENDS
HAS_SEMANTIC_ACTION
FLOWS_TO
AFFECTS_MIGRATION
```

### 3.8 原子边界判断

如果一个需求是在问“这个 repo 里有什么结构、调用、SQL、配置、异常、证据”，它属于 Code Knowledge Core。

如果一个需求是在问“这次事故为什么发生”，它不属于 Code Knowledge Core。

## 4. Structure 2: Incident Context Builder

### 4.1 职责

Incident Context Builder 负责把报警、日志、stack trace 或错误描述转换成标准化的调查上下文。

它是从“用户输入”到“可推理证据包”的桥梁。

### 4.2 负责的事情

- 接收日志、报警、stack trace、错误描述。
- 解析错误类型、出错类、方法、文件行号、endpoint、SQL 关键词、配置关键词。
- 生成 IncidentQuery。
- 调用 Code Knowledge Core 查询相关图节点和调用路径。
- 调用 Incident Memory & Report Store 检索历史相似故障。
- 组装 EvidenceBundle。

### 4.3 不负责的事情

- 不生成最终根因。
- 不决定修复方案。
- 不把 incident 写入长期记忆。
- 不直接访问 parser 内部结构。

### 4.4 核心输入

```text
AlertEvent
- alert_id
- repo_id
- raw_log
- stack_trace
- error_description
- occurred_at
- source
- contract_version
```

### 4.5 核心输出

```text
EvidenceBundle
- trace_id
- alert_summary
- incident_query
- matched_nodes[]
- graph_paths[]
- code_evidence[]
- sql_evidence[]
- config_evidence[]
- similar_incidents[]
- missing_evidence[]
```

### 4.6 原子边界判断

如果一个需求是在问“如何把一段日志变成可分析的上下文”，它属于 Incident Context Builder。

如果一个需求是在问“根据这些证据推断根因”，它不属于 Incident Context Builder。

## 5. Structure 3: RCA Reasoning Engine

### 5.1 职责

RCA Reasoning Engine 负责基于 EvidenceBundle 生成有证据链的根因分析。

它内部可以包含多 Agent，但外部只暴露标准 RCA 接口。

### 5.2 内部 Agent 建议

```text
Log RCA Agent
- 解析错误类型、症状、直接故障点。

Code Graph Agent
- 阅读 EvidenceBundle 中的图路径、代码证据、SQL、配置。

Memory Agent
- 比较历史 incident，提取相似根因和修复方案。

Reviewer Agent
- 检查每条结论是否有 evidence。
- 标注置信度、缺失证据和风险。
```

### 5.3 负责的事情

- 生成一个或多个 RootCauseHypothesis。
- 给出每个假设对应的 evidence_refs。
- 选择最可能根因。
- 输出修复建议。
- 输出迁移影响范围和 checklist。
- 输出置信度和缺失信息。
- 阻止没有证据支撑的强结论进入最终报告。

### 5.4 不负责的事情

- 不直接解析 repo。
- 不直接读取源代码文件。
- 不直接写入 incident memory。
- 不自动修改生产代码。

### 5.5 核心输入

```text
EvidenceBundle
- trace_id
- alert_summary
- matched_nodes[]
- graph_paths[]
- code_evidence[]
- sql_evidence[]
- config_evidence[]
- similar_incidents[]
- missing_evidence[]
```

### 5.6 核心输出

```text
ReviewedRCAReport
- report_id
- trace_id
- root_cause
- hypotheses[]
- evidence_chain[]
- affected_path
- suggested_fix[]
- migration_impact
- migration_checklist[]
- confidence
- missing_evidence[]
- reviewer_notes[]
```

### 5.7 原子边界判断

如果一个需求是在问“基于证据应该得出什么工程结论”，它属于 RCA Reasoning Engine。

如果一个需求是在问“证据从哪里来”，它不属于 RCA Reasoning Engine。

## 6. Structure 4: Incident Memory & Report Store

### 6.1 职责

Incident Memory & Report Store 负责保存和复用结构化故障记忆。

它不是聊天记忆，而是可审计、可检索、可去重的 incident memory。

### 6.2 负责的事情

- 保存用户确认后的 RCA 结果。
- 保存历史 incident 的症状、根因、修复、影响范围、证据引用。
- 支持相似 incident 检索。
- 支持 dedup_key 去重。
- 支持 fix outcome、timestamp、retention policy。
- 保存最终报告记录。

### 6.3 不负责的事情

- 不做代码解析。
- 不做实时根因判断。
- 不直接决定 RCA 报告内容。
- 不保存无用户确认的强结论为事实。

### 6.4 核心输入

```text
SaveIncidentRequest
- reviewed_report
- user_confirmation
- fix_outcome
- retention_policy
- contract_version
```

### 6.5 核心输出

```text
IncidentRecord
- incident_id
- repo_id
- module
- error_type
- symptom
- root_cause
- fix
- related_files[]
- evidence_refs[]
- confirmed_by_user
- fix_outcome
- dedup_key
- created_at
- updated_at
```

### 6.6 原子边界判断

如果一个需求是在问“历史故障如何保存、召回、去重、复用”，它属于 Incident Memory & Report Store。

如果一个需求是在问“这次事故到底是什么原因”，它不属于 Incident Memory & Report Store。

## 7. 结构间主流程

### 7.1 Repo 建图流程

```text
1. 用户上传或连接 legacy repo
2. Middleware 接收 IndexRepo 请求
3. Code Knowledge Core 解析 repo
4. Code Knowledge Core 输出 GraphSnapshot
5. Middleware 校验 graph schema 和 evidence_refs
6. GraphSnapshot 可供后续事故分析使用
```

### 7.2 故障分析流程

```text
1. 用户输入日志 / 报警 / stack trace
2. Incident Context Builder 生成 IncidentQuery
3. Incident Context Builder 查询图谱和历史 incident
4. Incident Context Builder 输出 EvidenceBundle
5. RCA Reasoning Engine 生成 RCAReport
6. Reviewer Agent 生成 ReviewedRCAReport
7. 用户确认结果
8. Incident Memory & Report Store 保存 IncidentRecord
```

## 8. MVP 开发顺序

```text
P0. 定义统一 contract schema
P0. 用 mock GraphSnapshot 跑通 EvidenceBundle
P0. 用 mock EvidenceBundle 跑通 RCAReport
P0. 用 mock IncidentRecord 跑通相似故障召回
P1. 接入真实 Java parser
P1. 接入 Qwen RCA 生成
P1. 接入向量相似检索
P1. 接入前端 demo
P2. 补充多语言 adapter 和更多 demo case
```

## 9. 设计原则

- 结构之间不共享内部对象，只共享 middleware contract。
- RCA 结论必须引用 evidence_refs。
- LLM 生成的语义边默认是待验证信息，必须有 confidence 和 evidence_span。
- MVP 只承诺 Java / Spring Boot 闭环，多语言作为 adapter 能力预留。
- 迁移能力只输出风险、影响范围和 checklist，不自动迁移生产代码。

