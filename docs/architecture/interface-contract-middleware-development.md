# Interface Contract Middleware 开发规范

## 1. 中间件定位

Interface Contract Middleware 是 LegacyPilot 各结构之间的契约层。

它不应该成为业务大脑，也不应该承载代码解析、根因推理或历史记忆逻辑。它的价值是让各结构通过稳定、可审计、可版本化的接口通信。

```text
Code Knowledge Core
Incident Context Builder
RCA Reasoning Engine
Incident Memory & Report Store

以上结构都只依赖 Middleware Contract，不直接依赖彼此内部实现。
```

## 2. 中间件核心职责

### 2.1 Contract Registry

维护所有接口和数据对象的版本定义。

必须管理：

```text
contract_version
schema_version
producer
consumer
required_fields
optional_fields
deprecated_fields
```

### 2.2 Schema Validation

所有跨结构输入输出都必须经过 schema 校验。

校验目标：

- 必填字段存在。
- ID 格式稳定。
- evidence_refs 可解析。
- confidence 在合法范围内。
- LLM 语义增强结果包含 extraction_method、prompt_version、confidence。
- RCA 结论不能缺少 evidence_refs。

### 2.3 Evidence Normalization

统一证据格式，让报告、图谱、日志、SQL、配置和历史 incident 都能引用同一种 EvidenceRef。

### 2.4 Routing

中间件负责把标准请求路由到对应结构。

示例：

```text
IndexRepo -> Code Knowledge Core
QueryGraph -> Code Knowledge Core
SubmitAlert -> Incident Context Builder
BuildEvidenceBundle -> Incident Context Builder
GenerateRCA -> RCA Reasoning Engine
ReviewRCA -> RCA Reasoning Engine
FindSimilarIncidents -> Incident Memory & Report Store
SaveIncident -> Incident Memory & Report Store
```

### 2.5 Audit Trace

每次分析都必须有 trace_id。

trace_id 用于串联：

```text
AlertEvent
IncidentQuery
GraphQuery
EvidenceBundle
RCAReport
ReviewedRCAReport
IncidentRecord
```

### 2.6 Error Envelope

所有结构返回错误时，必须使用统一错误格式。

```text
ContractError
- trace_id
- error_code
- message
- source_module
- recoverable
- missing_fields[]
- evidence_refs[]
```

## 3. 最小接口清单

## 3.1 IndexRepo

用途：导入 legacy repo 并生成图谱。

```text
Request: RepoIndexRequest
Response: GraphSnapshot
Owner: Code Knowledge Core
```

最小请求字段：

```text
repo_id
repo_uri
language_hint
parser_profile
contract_version
```

最小响应字段：

```text
graph_id
repo_id
nodes[]
edges[]
evidence_refs[]
generated_at
```

## 3.2 QueryGraph

用途：按日志线索或代码线索查询图谱上下文。

```text
Request: GraphQuery
Response: GraphContext
Owner: Code Knowledge Core
```

最小请求字段：

```text
repo_id
graph_id
query_terms[]
node_filters[]
edge_filters[]
max_depth
trace_id
```

最小响应字段：

```text
matched_nodes[]
matched_edges[]
graph_paths[]
evidence_refs[]
confidence
```

## 3.3 SubmitAlert

用途：接收日志、报警、stack trace 或错误描述。

```text
Request: AlertEvent
Response: IncidentQuery
Owner: Incident Context Builder
```

最小请求字段：

```text
alert_id
repo_id
raw_log
stack_trace
error_description
occurred_at
source
contract_version
```

最小响应字段：

```text
trace_id
repo_id
error_type
suspected_location
endpoint
keywords[]
query_terms[]
```

## 3.4 BuildEvidenceBundle

用途：基于 IncidentQuery 组装 RCA 所需证据包。

```text
Request: IncidentQuery
Response: EvidenceBundle
Owner: Incident Context Builder
```

最小响应字段：

```text
trace_id
alert_summary
matched_nodes[]
graph_paths[]
code_evidence[]
sql_evidence[]
config_evidence[]
similar_incidents[]
missing_evidence[]
```

## 3.5 GenerateRCA

用途：根据 EvidenceBundle 生成根因分析草稿。

```text
Request: EvidenceBundle
Response: RCAReport
Owner: RCA Reasoning Engine
```

最小响应字段：

```text
report_id
trace_id
hypotheses[]
selected_root_cause
evidence_chain[]
affected_path
suggested_fix[]
migration_impact
migration_checklist[]
confidence
```

## 3.6 ReviewRCA

用途：审查 RCAReport 是否有足够证据支撑。

```text
Request: RCAReport
Response: ReviewedRCAReport
Owner: RCA Reasoning Engine
```

最小响应字段：

```text
report_id
trace_id
approved_findings[]
rejected_findings[]
missing_evidence[]
risk_notes[]
final_confidence
```

## 3.7 FindSimilarIncidents

用途：查询历史相似故障。

```text
Request: IncidentQuery
Response: IncidentMatch[]
Owner: Incident Memory & Report Store
```

最小响应字段：

```text
incident_id
similarity
previous_root_cause
previous_fix
related_files[]
evidence_refs[]
confirmed_by_user
```

## 3.8 SaveIncident

用途：用户确认后保存结构化故障记忆。

```text
Request: SaveIncidentRequest
Response: IncidentRecord
Owner: Incident Memory & Report Store
```

最小请求字段：

```text
reviewed_report
user_confirmation
fix_outcome
retention_policy
contract_version
```

最小响应字段：

```text
incident_id
repo_id
error_type
symptom
root_cause
fix
related_files[]
evidence_refs[]
confirmed_by_user
dedup_key
created_at
```

## 4. 统一数据对象

## 4.1 EvidenceRef

任何结论、图边、历史故障和报告都必须能引用 EvidenceRef。

```text
EvidenceRef
- evidence_id
- trace_id
- source_type
- source_id
- file_path
- start_line
- end_line
- excerpt
- excerpt_hash
- extraction_method
- confidence
- created_at
```

source_type 可选值：

```text
code
sql
config
log
stack_trace
incident
document
llm_semantic_summary
manual_confirmation
```

extraction_method 可选值：

```text
tree_sitter
java_parser
regex
vector_retrieval
llm
manual_confirm
system_generated
```

## 4.2 Node

```text
Node
- node_id
- graph_id
- repo_id
- type
- name
- qualified_name
- source_location
- metadata
- evidence_refs[]
```

## 4.3 Edge

```text
Edge
- edge_id
- graph_id
- source_node_id
- target_node_id
- type
- confidence
- extraction_method
- evidence_refs[]
- metadata
```

## 4.4 EvidenceBundle

```text
EvidenceBundle
- trace_id
- repo_id
- alert_summary
- incident_query
- matched_nodes[]
- graph_paths[]
- code_evidence[]
- sql_evidence[]
- config_evidence[]
- log_evidence[]
- similar_incidents[]
- missing_evidence[]
```

## 4.5 RCAReport

```text
RCAReport
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
- open_questions[]
```

## 4.6 IncidentRecord

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
- related_nodes[]
- evidence_refs[]
- confirmed_by_user
- fix_outcome
- dedup_key
- retention_policy
- created_at
- updated_at
```

## 5. 中间件校验规则

### 5.1 Evidence Gate

以下对象必须至少包含一个 evidence_ref：

```text
Edge
RootCauseHypothesis
selected_root_cause
suggested_fix
migration_impact
IncidentRecord
```

如果缺少 evidence_ref，中间件应返回：

```text
error_code: EVIDENCE_REQUIRED
recoverable: true
```

### 5.2 LLM Semantic Gate

LLM 产生的语义边或语义摘要必须包含：

```text
evidence_span
source_location
prompt_version
confidence
extraction_method = llm
verification_status
```

默认状态：

```text
verification_status = pending
```

### 5.3 Confidence Gate

confidence 范围：

```text
0.0 <= confidence <= 1.0
```

建议解释：

```text
0.90 - 1.00: parser or manually confirmed fact
0.70 - 0.89: strong evidence but still inferred
0.50 - 0.69: weak hypothesis
0.00 - 0.49: should not be used as final conclusion
```

### 5.4 Trace Gate

所有运行时对象必须包含 trace_id：

```text
AlertEvent
IncidentQuery
GraphQuery
GraphContext
EvidenceBundle
RCAReport
ReviewedRCAReport
SaveIncidentRequest
```

### 5.5 Contract Version Gate

所有跨结构请求必须带 contract_version。

中间件处理策略：

```text
same version: accept
compatible minor version: accept with warning
unsupported major version: reject
missing version: reject
```

## 6. 推荐目录规划

后续写代码时，可以按以下边界组织。

```text
legacy_pilot/
  contracts/
    schemas/
    validators/
    errors/
  middleware/
    router/
    audit/
    evidence/
    versioning/
  code_knowledge_core/
  incident_context_builder/
  rca_reasoning_engine/
  incident_memory_store/
```

注意：这是后续实现建议，不是当前要求写代码。

## 7. MVP 开发顺序

### Step 1: 固定 contract

先冻结最小数据对象：

```text
EvidenceRef
Node
Edge
GraphSnapshot
AlertEvent
IncidentQuery
EvidenceBundle
RCAReport
ReviewedRCAReport
IncidentRecord
```

### Step 2: 实现 schema validation

先让每个对象能被校验，不急着接真实 parser 或 LLM。

### Step 3: 实现 mock router

用 mock response 跑通以下链路：

```text
SubmitAlert
-> BuildEvidenceBundle
-> GenerateRCA
-> ReviewRCA
-> SaveIncident
```

### Step 4: 接入 Code Knowledge Core

先支持 Java / Spring Boot。

最小可用能力：

```text
Controller -> Service -> Mapper -> SQL -> Table
Exception -> Method
Config -> Method
```

### Step 5: 接入 RCA Reasoning Engine

RCA Reasoning Engine 只能读取 EvidenceBundle，不能直接绕过中间件读 repo。

### Step 6: 接入 Incident Memory

先做结构化保存，再做相似度召回。

### Step 7: 接前端或 demo CLI

前端只调用中间件接口，不直接调用内部结构。

## 8. 开发纪律

- 任何跨结构数据都必须走 contract。
- 任何 RCA 结论都必须有 evidence_ref。
- 任何 LLM 语义增强都必须标注 confidence 和 prompt_version。
- 中间件不写业务推理逻辑。
- 内部结构可以替换，但 contract 尽量稳定。
- 先 mock 跑通闭环，再替换真实实现。

## 9. 首版验收标准

首版中间件完成后，应该能证明：

```text
1. 一个 mock repo 可以生成 GraphSnapshot。
2. 一段 mock NPE 日志可以生成 IncidentQuery。
3. IncidentQuery 可以生成 EvidenceBundle。
4. EvidenceBundle 可以生成 RCAReport。
5. RCAReport 缺少 evidence_ref 时会被 ReviewRCA 或 Middleware 拦截。
6. 用户确认后可以保存 IncidentRecord。
7. 所有对象都能通过 trace_id 串起来。
```

