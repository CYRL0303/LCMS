# Task 0-2 Structure 1 Change Summary

Date: 2026-06-16

This document summarizes what changed in Task 0, Task 1, and Task 2 of
`2026-06-16-complete-structure1-production-coverage.md`.

## Scope

Tasks covered:

```text
Task 0: Reconfirm real GitNexus CLI capabilities
Task 1: Add backward-compatible Structure 1 contract metadata
Task 2: Generalize Evidence source types in the mapper
```

These tasks are foundation work for Structure 1 production coverage. They do not
add SQL/config/exception extractors yet, and they do not implement semantic
enrichment.

## Task 0: Real GitNexus CLI Contract Check

Modified:

```text
docs/architecture/实现结构1对齐真实gitnexus-api改造.md
```

Added a `Task 0 实测 CLI 契约记录（2026-06-16）` section with observed real CLI
behavior.

Recorded:

```text
status behavior
cypher JSON wrapper fields
cypher markdown table headers
representative node ids
representative edge types and reasons
context symbol fields
incoming.calls fields
outgoing.calls fields
query result fields
known query/FTS limitations for Structure 1
```

Key finding:

```text
cypher returns JSON with markdown + row_count.
The graph facts are inside markdown tables, not native nodes/edges JSON.
context returns structured symbol/incoming/outgoing/process JSON.
query is discovery/ranking oriented and should not be treated as trusted
structural graph evidence by default.
```

No Python code was changed in Task 0.

## Task 1: GraphSnapshot Metadata Contract

Modified:

```text
legacy_pilot/code_knowledge_core/gitnexus_client.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
legacy_pilot/contracts/models.py
tests/test_gitnexus_client.py
tests/test_gitnexus_mapper.py
tests/test_contract_models.py
```

Added optional fields to `GraphSnapshot`:

```python
parser_version: str | None = None
semantic_enrichment_version: str | None = None
metadata: dict[str, Any] = Field(default_factory=dict)
```

Added test:

```text
test_graph_snapshot_accepts_structure1_versions
```

Purpose:

```text
Allow Structure 1 snapshots to carry parser/enrichment version metadata without
changing existing required GraphSnapshot fields.
```

Follow-up wiring after review:

```text
GitNexusCliClient.index_repo() now emits parser_version="gitnexus_cli+cypher_v1".
GitNexusCliClient.index_repo() also emits semantic_enrichment_version=None and
basic Structure 1 metadata.
map_index_payload() now propagates parser_version, semantic_enrichment_version,
and metadata into GraphSnapshot.
```

Compatibility:

```text
Backward-compatible.
Existing GraphSnapshot construction without these fields still works.
No RepoIndexRequest, GraphQuery, GraphContext, EvidenceBundle, RCAReport,
ReviewedRCAReport, or IncidentRecord required fields were changed.
```

## Task 2: Evidence Source Type Mapping

Modified:

```text
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_gitnexus_mapper.py
```

Added mapper behavior:

```text
map_gitnexus_node() now passes payload source_type into EvidenceRef.
map_gitnexus_edge() now passes payload source_type into EvidenceRef.
If payload/properties do not specify source_type, evidence remains SourceType.CODE.
```

Added helper:

```python
def _source_type(payload: dict[str, Any]) -> SourceType | str:
    properties = _properties(payload)
    return (
        _get_any(payload, "source_type", "sourceType")
        or _get_any(properties, "source_type", "sourceType")
        or SourceType.CODE
    )
```

Added tests:

```text
test_sql_node_maps_to_sql_evidence_source_type
test_config_node_maps_to_config_evidence_source_type
test_relationship_maps_payload_source_type_to_evidence_source_type
```

Purpose:

```text
Prepare the mapper for SQL/config/semantic enrichment payloads while preserving
the current GitNexus Java/Spring code evidence behavior.
```

## Middleware Impact

Middleware files changed:

```text
None.
```

The following middleware behavior was not changed:

```text
MiddlewareRouter.index_repo() still gates contract_version before adapter calls.
MiddlewareRouter.query_graph() still gates trace_id and contract_version before adapter calls.
MiddlewareRouter still depends only on CodeKnowledgeCoreAdapter.
Code Knowledge Core errors are still converted to ContractError envelopes.
```

Regression coverage was run against:

```text
tests/test_code_knowledge_core_adapter.py
tests/test_router_pipeline.py
tests/test_api.py
```

## Four-Structure Contract Impact

The four-structure interface contract was not redefined.

Task 1 implements fields that were already listed in the Structure 1
`GraphSnapshot` output in `docs/architecture/legacy-pilot-four-structures.md`:

```text
parser_version
semantic_enrichment_version
```

Contract impact:

```text
GraphSnapshot gained optional metadata fields.
No existing required contract field was removed.
No existing required contract field was renamed.
No existing request model was changed.
No Structure 2/3/4 model was changed.
EvidenceRef schema was not changed.
SourceType enum was not changed; sql/config/llm_semantic_summary already existed.
```

Task 2 only changes mapper behavior for how `EvidenceRef.source_type` is filled
from mapper-ready payloads. It does not change the `EvidenceRef` contract.

## TDD Evidence

Task 1 red test:

```text
python -m pytest tests/test_contract_models.py::test_graph_snapshot_accepts_structure1_versions -q

Initial result:
FAILED because GraphSnapshot had no parser_version attribute.
```

Task 1 green tests:

```text
python -m pytest tests/test_contract_models.py::test_graph_snapshot_accepts_structure1_versions -q
1 passed

python -m pytest tests/test_contract_models.py -q
8 passed
```

Task 2 red tests:

```text
python -m pytest tests/test_gitnexus_mapper.py::test_sql_node_maps_to_sql_evidence_source_type tests/test_gitnexus_mapper.py::test_config_node_maps_to_config_evidence_source_type tests/test_gitnexus_mapper.py::test_relationship_maps_payload_source_type_to_evidence_source_type -q

Initial result:
3 failed because EvidenceRef.source_type was still code.
```

Task 2 green tests:

```text
python -m pytest tests/test_gitnexus_mapper.py::test_sql_node_maps_to_sql_evidence_source_type tests/test_gitnexus_mapper.py::test_config_node_maps_to_config_evidence_source_type tests/test_gitnexus_mapper.py::test_relationship_maps_payload_source_type_to_evidence_source_type -q
3 passed

python -m pytest tests/test_gitnexus_mapper.py -q
13 passed
```

## Verification Commands

Task 0 baseline:

```text
python -m pytest tests/test_gitnexus_client.py tests/test_gitnexus_mapper.py tests/test_gitnexus_integration.py -q -rs
23 passed, 3 skipped
```

Task 1 middleware/API regression:

```text
python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q
47 passed, 1 warning
```

Task 2 related regression:

```text
python -m pytest tests/test_gitnexus_mapper.py tests/test_gitnexus_client.py tests/test_code_knowledge_core_adapter.py tests/test_contract_models.py -q
52 passed
```

Compile check:

```text
python -m compileall legacy_pilot
passed
```

Whitespace check:

```text
git diff --check
passed with no output
```

Full default test suite after Task 2:

```text
python -m pytest -q
82 passed, 3 skipped, 1 warning
```

The 3 skipped tests are opt-in GitNexus integration tests when the integration
environment variables are not set. The warning is the existing FastAPI/Starlette
TestClient deprecation warning.

## Current Uncommitted Task Files

Task-related files currently modified:

```text
docs/architecture/实现结构1对齐真实gitnexus-api改造.md
docs/architecture/2026-06-16-task0-2-structure1-summary.md
legacy_pilot/code_knowledge_core/gitnexus_client.py
tests/test_gitnexus_client.py
legacy_pilot/contracts/models.py
tests/test_contract_models.py
legacy_pilot/code_knowledge_core/gitnexus_mapper.py
tests/test_gitnexus_mapper.py
```

Not part of Task 0-2:

```text
.claude/settings.local.json
```
