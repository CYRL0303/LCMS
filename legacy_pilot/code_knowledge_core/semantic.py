import os
from dataclasses import dataclass
from typing import Any, Protocol


SEMANTIC_BACKEND_ENV = "LEGACY_PILOT_SEMANTIC_BACKEND"
SEMANTIC_CONFIDENCE_CAP_ENV = "LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP"
MOCK_SEMANTIC_ENRICHMENT_VERSION = "semantic_mock_v1"
MOCK_PROMPT_VERSION = "mock_semantic_v1"
DEFAULT_CONFIDENCE_CAP = 0.7
SEMANTIC_NODE_TYPE = "Function Semantic Summary"
SEMANTIC_EDGE_TYPE = "HAS_SEMANTIC_ACTION"
SEMANTIC_SOURCE_TYPE = "llm_semantic_summary"


class SemanticEnricher(Protocol):
    semantic_enrichment_version: str | None
    backend_name: str
    confidence_cap: float | None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class DisabledSemanticEnricher:
    semantic_enrichment_version: str | None = None
    backend_name: str = "disabled"
    confidence_cap: float | None = None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {"nodes": [], "relationships": []}


@dataclass(frozen=True)
class MockSemanticEnricher:
    confidence_cap: float = DEFAULT_CONFIDENCE_CAP
    semantic_enrichment_version: str | None = MOCK_SEMANTIC_ENRICHMENT_VERSION
    backend_name: str = "mock"

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        semantic_nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict) or not _is_semantic_candidate(node):
                continue
            file_path = _string_value(_get_nested(node, "filePath", "file_path"))
            if file_path is None:
                continue
            node_id = _string_value(_get_nested(node, "id", "node_id", "nodeId"))
            if node_id is None:
                continue
            name = _string_value(_get_nested(node, "name")) or node_id
            start_line = _int_value(_get_nested(node, "startLine", "start_line"))
            end_line = _int_value(_get_nested(node, "endLine", "end_line"))
            summary = f"Mock semantic summary for {name}."
            semantic_node_id = f"SemanticSummary:{node_id}"
            semantic_nodes.append(
                {
                    "id": semantic_node_id,
                    "type": SEMANTIC_NODE_TYPE,
                    "name": f"{name} semantic summary",
                    "filePath": file_path,
                    "startLine": start_line,
                    "endLine": end_line,
                    "excerpt": summary,
                    "source_type": SEMANTIC_SOURCE_TYPE,
                    "extraction_method": "llm",
                    "confidence": self.confidence_cap,
                    "properties": {
                        "source_node_id": node_id,
                        "summary": summary,
                        "evidence_span": name,
                        "prompt_version": MOCK_PROMPT_VERSION,
                        "verification_status": "pending",
                    },
                }
            )
            relationships.append(
                {
                    "id": f"SEM-REL-{node_id}",
                    "source_id": node_id,
                    "target_id": semantic_node_id,
                    "type": SEMANTIC_EDGE_TYPE,
                    "filePath": file_path,
                    "startLine": start_line,
                    "endLine": end_line,
                    "excerpt": summary,
                    "source_type": SEMANTIC_SOURCE_TYPE,
                    "extraction_method": "llm",
                    "confidence": self.confidence_cap,
                    "properties": {
                        "verification_status": "pending",
                        "prompt_version": MOCK_PROMPT_VERSION,
                    },
                }
            )
        return {"nodes": semantic_nodes, "relationships": relationships}


@dataclass(frozen=True)
class UnsupportedSemanticEnricher:
    backend_name: str
    semantic_enrichment_version: str | None = None
    confidence_cap: float | None = None

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        raise ValueError(f"Unsupported semantic backend: {self.backend_name}")


def create_semantic_enricher(
    *,
    backend: str | None = None,
    confidence_cap: float | None = None,
) -> SemanticEnricher:
    selected_backend = (
        backend or os.getenv(SEMANTIC_BACKEND_ENV) or "disabled"
    ).strip().lower()
    cap = _confidence_cap(confidence_cap)
    if selected_backend in {"", "disabled", "none", "off"}:
        return DisabledSemanticEnricher()
    if selected_backend == "mock":
        return MockSemanticEnricher(confidence_cap=cap)
    return UnsupportedSemanticEnricher(backend_name=selected_backend)


def _confidence_cap(value: float | None) -> float:
    if value is None:
        raw = os.getenv(SEMANTIC_CONFIDENCE_CAP_ENV)
        if raw is None:
            return DEFAULT_CONFIDENCE_CAP
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_CONFIDENCE_CAP
    return min(max(float(value), 0.0), 1.0)


def _is_semantic_candidate(node: dict[str, Any]) -> bool:
    node_type = _string_value(_get_nested(node, "type", "node_type", "nodeType"))
    return node_type in {"Method", "Mapper", "API Endpoint", "Service"}


def _get_nested(source: dict[str, Any], *keys: str) -> Any:
    properties = source.get("properties")
    property_source = properties if isinstance(properties, dict) else {}
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
        value = property_source.get(key)
        if value is not None:
            return value
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
