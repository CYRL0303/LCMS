import os

import pytest

from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    QwenApiSemanticEnricher,
    create_semantic_enricher,
)


METHOD_ID = (
    "Method:src/main/java/com/legacy/DatasetService.java:"
    "DatasetService.getVersion#1"
)
SEMANTIC_ID = f"SemanticSummary:{METHOD_ID}"
SEMANTIC_RELATIONSHIP_ID = f"SEM-REL-{METHOD_ID}"
FILE_PATH = "src/main/java/com/legacy/DatasetService.java"
QWEN_RUN_ENV = "LEGACY_PILOT_RUN_QWEN_SEMANTIC_INTEGRATION"


def test_semantic_enrichment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_SEMANTIC_BACKEND", raising=False)

    enricher = create_semantic_enricher()

    assert isinstance(enricher, DisabledSemanticEnricher)
    assert enricher.semantic_enrichment_version is None
    assert enricher.enrich([_method_node()]) == {"nodes": [], "relationships": []}


def test_create_semantic_enricher_rejects_runtime_mock_backend(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "mock")

    enricher = create_semantic_enricher()

    assert enricher.backend_name == "mock"
    with pytest.raises(ValueError, match="Unsupported semantic backend: mock"):
        enricher.enrich([_method_node()])


def test_qwen_api_semantic_enricher_skips_nodes_without_file_evidence():
    requests = []
    enricher = QwenApiSemanticEnricher(
        api_key="test-key",
        http_post=lambda url, headers, body: requests.append(body),
    )

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
    assert requests == []


def test_create_semantic_enricher_returns_qwen_api_backend(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_BACKEND", "qwen_api")
    monkeypatch.setenv(
        "LEGACY_PILOT_SEMANTIC_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_MODEL", "qwen-plus")
    monkeypatch.setenv("LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP", "0.33")

    enricher = create_semantic_enricher()

    assert isinstance(enricher, QwenApiSemanticEnricher)
    assert enricher.backend_name == "qwen_api"
    assert enricher.semantic_enrichment_version == "qwen_api:qwen-plus"
    assert enricher.confidence_cap == 0.33


def test_qwen_api_semantic_enricher_creates_pending_summary_payload():
    requests = []

    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        requests.append({"url": url, "headers": headers, "body": body})
        return {
            "choices": [
                {
                    "message": {
                        "content": "Reads dataset version through mapper SQL."
                    }
                }
            ]
        }

    enricher = QwenApiSemanticEnricher(
        api_key="test-key",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        confidence_cap=0.4,
        http_post=fake_post,
    )

    payload = enricher.enrich([_method_node()])

    assert requests == [
        {
            "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
            "headers": {
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            "body": {
                "model": "qwen-plus",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Summarize Java/Spring code semantics for an "
                            "evidence-backed code knowledge graph."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Node: DatasetService.getVersion\n"
                            "Type: Method\n"
                            f"File: {FILE_PATH}\n"
                            "Lines: 12-18\n"
                            "Code excerpt:\n"
                            "return datasetMapper.selectVersionById(datasetId);\n\n"
                            "Return one concise business-semantic sentence. "
                            "Do not claim facts absent from the excerpt."
                        ),
                    },
                ],
                "temperature": 0,
            },
        }
    ]
    assert payload["nodes"][0]["excerpt"] == "Reads dataset version through mapper SQL."
    assert payload["nodes"][0]["confidence"] == 0.4
    assert payload["nodes"][0]["source_type"] == "llm_semantic_summary"
    assert payload["nodes"][0]["extraction_method"] == "llm"
    assert payload["nodes"][0]["properties"]["verification_status"] == "pending"
    assert payload["nodes"][0]["properties"]["prompt_version"] == "qwen_semantic_v1"
    assert payload["relationships"][0]["type"] == "HAS_SEMANTIC_ACTION"
    assert payload["relationships"][0]["confidence"] == 0.4


def test_qwen_api_semantic_enricher_requires_api_key():
    enricher = QwenApiSemanticEnricher(api_key="", http_post=lambda url, headers, body: {})

    try:
        enricher.enrich([_method_node()])
    except ValueError as exc:
        assert str(exc) == "DASHSCOPE_API_KEY is required for qwen_api semantic backend."
    else:
        raise AssertionError("expected qwen_api to require an API key")


def test_qwen_api_semantic_enricher_repr_does_not_expose_api_key():
    enricher = QwenApiSemanticEnricher(api_key="secret-test-key")

    assert "secret-test-key" not in repr(enricher)


@pytest.mark.qwen_semantic_integration
def test_qwen_api_semantic_enricher_real_request():
    if os.getenv(QWEN_RUN_ENV) != "1" or not os.getenv("DASHSCOPE_API_KEY"):
        pytest.skip(
            "Qwen semantic integration is opt-in; set "
            "LEGACY_PILOT_RUN_QWEN_SEMANTIC_INTEGRATION=1 and "
            "DASHSCOPE_API_KEY to run it."
        )
    enricher = QwenApiSemanticEnricher(
        confidence_cap=0.2,
        base_url=os.getenv(
            "LEGACY_PILOT_SEMANTIC_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        ),
        model=os.getenv("LEGACY_PILOT_SEMANTIC_MODEL", "qwen-plus"),
    )

    payload = enricher.enrich([_method_node()])

    assert payload["nodes"]
    assert payload["relationships"]
    summary = payload["nodes"][0]["properties"]["summary"]
    assert isinstance(summary, str)
    assert summary.strip()
    assert payload["nodes"][0]["source_type"] == "llm_semantic_summary"
    assert payload["nodes"][0]["extraction_method"] == "llm"
    assert payload["nodes"][0]["confidence"] <= 0.2
    assert payload["nodes"][0]["properties"]["verification_status"] == "pending"


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
