from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    MockSemanticEnricher,
    create_semantic_enricher,
)


def test_semantic_enrichment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)

    enricher = create_semantic_enricher()

    assert isinstance(enricher, DisabledSemanticEnricher)
    assert enricher.semantic_enrichment_version is None
    assert enricher.enrich([_method_node()]) == {"nodes": [], "relationships": []}


def test_mock_semantic_enricher_creates_pending_summary_node(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "mock")
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP", "0.42")

    enricher = create_semantic_enricher()
    payload = enricher.enrich([_method_node()])

    assert payload["nodes"] == [
        {
            "id": "SemanticSummary:Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "type": "Function Semantic Summary",
            "name": "DatasetService.getVersion semantic summary",
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 12,
            "endLine": 18,
            "excerpt": "Mock semantic summary for DatasetService.getVersion.",
            "source_type": "llm_semantic_summary",
            "extraction_method": "llm",
            "confidence": 0.42,
            "properties": {
                "source_node_id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
                "summary": "Mock semantic summary for DatasetService.getVersion.",
                "evidence_span": "DatasetService.getVersion",
                "prompt_version": "mock_semantic_v1",
                "verification_status": "pending",
            },
        }
    ]
    assert payload["relationships"] == [
        {
            "id": "SEM-REL-Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "source_id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "target_id": "SemanticSummary:Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "type": "HAS_SEMANTIC_ACTION",
            "filePath": "src/main/java/com/legacy/DatasetService.java",
            "startLine": 12,
            "endLine": 18,
            "excerpt": "Mock semantic summary for DatasetService.getVersion.",
            "source_type": "llm_semantic_summary",
            "extraction_method": "llm",
            "confidence": 0.42,
            "properties": {
                "verification_status": "pending",
                "prompt_version": "mock_semantic_v1",
            },
        }
    ]


def test_mock_semantic_enricher_skips_nodes_without_file_evidence():
    enricher = MockSemanticEnricher(confidence_cap=0.7)

    payload = enricher.enrich(
        [
            {
                "id": "Method:NoLocation",
                "type": "Method",
                "name": "NoLocation",
            }
        ]
    )

    assert payload == {"nodes": [], "relationships": []}


def _method_node():
    return {
        "id": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
        "type": "Method",
        "name": "DatasetService.getVersion",
        "filePath": "src/main/java/com/legacy/DatasetService.java",
        "startLine": 12,
        "endLine": 18,
        "excerpt": "return datasetMapper.selectVersionById(datasetId);",
        "confidence": 0.91,
    }
