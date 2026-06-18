from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    MockSemanticEnricher,
    create_semantic_enricher,
)


METHOD_ID = (
    "Method:src/main/java/com/legacy/DatasetService.java:"
    "DatasetService.getVersion#1"
)
SEMANTIC_ID = f"SemanticSummary:{METHOD_ID}"
SEMANTIC_RELATIONSHIP_ID = f"SEM-REL-{METHOD_ID}"
FILE_PATH = "src/main/java/com/legacy/DatasetService.java"
SUMMARY = "Mock semantic summary for DatasetService.getVersion."


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
            "id": SEMANTIC_ID,
            "type": "Function Semantic Summary",
            "name": "DatasetService.getVersion semantic summary",
            "filePath": FILE_PATH,
            "startLine": 12,
            "endLine": 18,
            "excerpt": SUMMARY,
            "source_type": "llm_semantic_summary",
            "extraction_method": "llm",
            "confidence": 0.42,
            "properties": {
                "source_node_id": METHOD_ID,
                "summary": SUMMARY,
                "evidence_span": "DatasetService.getVersion",
                "prompt_version": "mock_semantic_v1",
                "verification_status": "pending",
            },
        }
    ]
    assert payload["relationships"] == [
        {
            "id": SEMANTIC_RELATIONSHIP_ID,
            "source_id": METHOD_ID,
            "target_id": SEMANTIC_ID,
            "type": "HAS_SEMANTIC_ACTION",
            "filePath": FILE_PATH,
            "startLine": 12,
            "endLine": 18,
            "excerpt": SUMMARY,
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
        "id": METHOD_ID,
        "type": "Method",
        "name": "DatasetService.getVersion",
        "filePath": FILE_PATH,
        "startLine": 12,
        "endLine": 18,
        "excerpt": "return datasetMapper.selectVersionById(datasetId);",
        "confidence": 0.91,
    }
