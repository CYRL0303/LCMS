# Task 3 Report: Persist Enriched Structure 1 Payloads

Status: DONE

## Summary

- Added `graph_store` injection to `GitNexusCliCodeKnowledgeCoreAdapter`.
- Created the default store with `create_graph_store(now=self._now)` when no store is injected.
- Persisted the enriched index payload after GitNexus payload merge, Structure 1 enrichment metadata, and semantic enrichment.
- Kept the existing local in-memory index behavior and did not add restore/load-on-query behavior.
- Wrapped `GraphStoreError` from save operations as recoverable `IndexingError` with diagnostics.

## Tests

- RED: `python -m pytest tests/test_code_knowledge_core_adapter.py::TestGitNexusCliAdapter::test_gitnexus_adapter_saves_enriched_payload_to_graph_store -q`
  - Failed as expected because `GitNexusCliCodeKnowledgeCoreAdapter.__init__()` did not accept `graph_store`.
- GREEN: `python -m pytest tests/test_code_knowledge_core_adapter.py::TestGitNexusCliAdapter::test_gitnexus_adapter_saves_enriched_payload_to_graph_store -q`
  - Passed: `1 passed`.
- Required adjacent verification: `python -m pytest tests/test_code_knowledge_core_adapter.py tests/test_router_pipeline.py tests/test_api.py -q`
  - Passed: `56 passed, 1 warning`.
  - Warning: existing `StarletteDeprecationWarning` from `fastapi.testclient`.

## Files Touched

- `legacy_pilot/code_knowledge_core/adapter.py`
- `tests/test_code_knowledge_core_adapter.py`
- `.superpowers/sdd/task-3-report.md`

## Self-Review

- Persistence is only on the adapter index path and uses the enriched payload already used for mapping/local indexing.
- Query behavior remains unchanged and does not load from the graph store.
- Structure 1 remains behind the existing adapter/router contract boundary.
- No unrelated files were modified.

## Concerns

- None.
