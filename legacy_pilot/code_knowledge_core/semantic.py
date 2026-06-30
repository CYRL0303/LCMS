import os
from dataclasses import dataclass, field
from json import dumps, loads
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SEMANTIC_BACKEND_ENV = "LEGACY_PILOT_SEMANTIC_BACKEND"
SEMANTIC_CONFIDENCE_CAP_ENV = "LEGACY_PILOT_SEMANTIC_CONFIDENCE_CAP"
SEMANTIC_BASE_URL_ENV = "LEGACY_PILOT_SEMANTIC_BASE_URL"
SEMANTIC_MODEL_ENV = "LEGACY_PILOT_SEMANTIC_MODEL"
DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"
QWEN_PROMPT_VERSION = "qwen_semantic_v1"
DEFAULT_CONFIDENCE_CAP = 0.7
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
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
class QwenApiSemanticEnricher:
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_QWEN_BASE_URL
    model: str = DEFAULT_QWEN_MODEL
    confidence_cap: float = DEFAULT_CONFIDENCE_CAP
    http_post: Any | None = None
    backend_name: str = "qwen_api"

    @property
    def semantic_enrichment_version(self) -> str:
        return f"qwen_api:{self.model}"

    def enrich(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        api_key = self.api_key or os.getenv(DASHSCOPE_API_KEY_ENV)
        if not api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is required for qwen_api semantic backend."
            )

        semantic_nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict) or not _is_semantic_candidate(node):
                continue
            base_payload = _semantic_payload_base(node)
            if base_payload is None:
                continue
            summary = self._summarize(api_key, base_payload)
            semantic_node, relationship = _semantic_payload_items(
                base_payload,
                summary=summary,
                confidence=self.confidence_cap,
                prompt_version=QWEN_PROMPT_VERSION,
            )
            semantic_nodes.append(semantic_node)
            relationships.append(relationship)
        return {"nodes": semantic_nodes, "relationships": relationships}

    def _summarize(self, api_key: str, base_payload: dict[str, Any]) -> str:
        body = {
            "model": self.model,
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
                    "content": _qwen_prompt(base_payload),
                },
            ],
            "temperature": 0,
        }
        response = self._post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body=body,
        )
        summary = _chat_completion_content(response)
        return summary or f"Semantic summary for {base_payload['name']} is pending."

    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if self.http_post is not None:
            return self.http_post(url, headers, body)
        return _http_post_json(url, headers=headers, body=body)


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
    if selected_backend == "qwen_api":
        return QwenApiSemanticEnricher(
            base_url=os.getenv(SEMANTIC_BASE_URL_ENV, DEFAULT_QWEN_BASE_URL),
            model=os.getenv(SEMANTIC_MODEL_ENV, DEFAULT_QWEN_MODEL),
            confidence_cap=cap,
        )
    return UnsupportedSemanticEnricher(backend_name=selected_backend)


def _semantic_payload_base(node: dict[str, Any]) -> dict[str, Any] | None:
    file_path = _string_value(_get_nested(node, "filePath", "file_path"))
    if file_path is None:
        return None
    node_id = _string_value(_get_nested(node, "id", "node_id", "nodeId"))
    if node_id is None:
        return None
    name = _string_value(_get_nested(node, "name")) or node_id
    return {
        "node_id": node_id,
        "node_type": _string_value(_get_nested(node, "type", "node_type", "nodeType")),
        "name": name,
        "file_path": file_path,
        "start_line": _int_value(_get_nested(node, "startLine", "start_line")),
        "end_line": _int_value(_get_nested(node, "endLine", "end_line")),
        "excerpt": _string_value(_get_nested(node, "excerpt")) or "",
    }


def _semantic_payload_items(
    base_payload: dict[str, Any],
    *,
    summary: str,
    confidence: float,
    prompt_version: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    semantic_node_id = f"SemanticSummary:{base_payload['node_id']}"
    semantic_node = {
        "id": semantic_node_id,
        "type": SEMANTIC_NODE_TYPE,
        "name": f"{base_payload['name']} semantic summary",
        "filePath": base_payload["file_path"],
        "startLine": base_payload["start_line"],
        "endLine": base_payload["end_line"],
        "excerpt": summary,
        "source_type": SEMANTIC_SOURCE_TYPE,
        "extraction_method": "llm",
        "confidence": confidence,
        "properties": {
            "source_node_id": base_payload["node_id"],
            "summary": summary,
            "evidence_span": base_payload["name"],
            "prompt_version": prompt_version,
            "verification_status": "pending",
        },
    }
    relationship = {
        "id": f"SEM-REL-{base_payload['node_id']}",
        "source_id": base_payload["node_id"],
        "target_id": semantic_node_id,
        "type": SEMANTIC_EDGE_TYPE,
        "filePath": base_payload["file_path"],
        "startLine": base_payload["start_line"],
        "endLine": base_payload["end_line"],
        "excerpt": summary,
        "source_type": SEMANTIC_SOURCE_TYPE,
        "extraction_method": "llm",
        "confidence": confidence,
        "properties": {
            "verification_status": "pending",
            "prompt_version": prompt_version,
        },
    }
    return semantic_node, relationship


def _qwen_prompt(base_payload: dict[str, Any]) -> str:
    return (
        f"Node: {base_payload['name']}\n"
        f"Type: {base_payload['node_type']}\n"
        f"File: {base_payload['file_path']}\n"
        f"Lines: {base_payload['start_line']}-{base_payload['end_line']}\n"
        "Code excerpt:\n"
        f"{base_payload['excerpt']}\n\n"
        "Return one concise business-semantic sentence. "
        "Do not claim facts absent from the excerpt."
    )


def _chat_completion_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content).strip() if content is not None else ""


def _http_post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
) -> dict[str, Any]:
    request = Request(
        url,
        data=dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen semantic API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Qwen semantic API request failed: {exc.reason}") from exc


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
