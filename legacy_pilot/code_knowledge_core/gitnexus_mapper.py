from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from legacy_pilot.contracts.enums import ExtractionMethod, SourceType
from legacy_pilot.contracts.models import (
    Edge,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    Node,
    SourceLocation,
)


def map_gitnexus_node(
    payload: dict[str, Any],
    *,
    graph_id: str,
    repo_id: str,
    trace_id: str,
    now: Callable[[], datetime] | None = None,
) -> Node:
    clock = _clock(now)
    properties = _properties(payload)
    node_id = _string_value(_get_any(payload, "id", "node_id", "nodeId")) or ""
    name = (
        _string_value(_get_any(payload, "name"))
        or _string_value(_get_any(properties, "name", "simpleName", "displayName"))
        or node_id
    )
    file_path, start_line, end_line, excerpt = _source_details(payload)
    qualified_name = (
        _string_value(_get_any(properties, "qualifiedName", "qualified_name"))
        or _string_value(_get_any(payload, "qualifiedName", "qualified_name"))
        or (f"{file_path}::{name}" if file_path else None)
    )

    evidence_refs = []
    if file_path:
        evidence_refs.append(
            _evidence_ref(
                trace_id=trace_id,
                source_id=node_id,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                excerpt=excerpt,
                extraction_method=_extraction_method(payload),
                confidence=_confidence(payload, default=0.95),
                now=clock,
            )
        )

    return Node(
        node_id=node_id,
        graph_id=graph_id,
        repo_id=repo_id,
        type=_node_type(payload),
        name=name,
        qualified_name=qualified_name,
        source_location=_source_location(file_path, start_line, end_line),
        metadata={
            "gitnexus": {
                "id": node_id,
                "labels": _list_value(_get_any(payload, "labels", "label")),
                "source_node_type": _get_any(payload, "type", "node_type", "nodeType"),
                "properties": dict(properties),
            }
        },
        evidence_refs=evidence_refs,
    )


def map_gitnexus_edge(
    payload: dict[str, Any],
    *,
    graph_id: str,
    trace_id: str,
    nodes_by_id: dict[str, Node],
    now: Callable[[], datetime] | None = None,
) -> Edge | None:
    clock = _clock(now)
    properties = _properties(payload)
    edge_id = _string_value(_get_any(payload, "id", "edge_id", "relationship_id")) or ""
    source_node_id = _string_value(
        _get_any(payload, "source_id", "sourceNodeId", "source", "from")
    )
    target_node_id = _string_value(
        _get_any(payload, "target_id", "targetNodeId", "target", "to")
    )
    if not source_node_id or not target_node_id:
        return None

    relationship_type = _string_value(
        _get_any(payload, "type", "relationship_type", "relationshipType")
    ) or "RELATED_TO"
    edge_confidence = _confidence(payload, default=0.5)
    file_path, start_line, end_line, excerpt = _edge_source_details(
        payload,
        source_node=nodes_by_id.get(source_node_id),
        target_node=nodes_by_id.get(target_node_id),
    )
    evidence_confidence = 0.2 if file_path is None else edge_confidence
    evidence_refs = [
        _evidence_ref(
            trace_id=trace_id,
            source_id=edge_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            excerpt=excerpt,
            extraction_method=_extraction_method(payload),
            confidence=evidence_confidence,
            now=clock,
        )
    ]

    return Edge(
        edge_id=edge_id,
        graph_id=graph_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        type=relationship_type,
        confidence=edge_confidence,
        extraction_method=_extraction_method(payload),
        evidence_refs=evidence_refs,
        metadata={
            "gitnexus": {
                "reason": _get_any(payload, "reason") or _get_any(properties, "reason"),
                "evidence_signals": _list_value(
                    _get_any(payload, "evidence_signals", "evidenceSignals")
                    or _get_any(properties, "evidence_signals", "evidenceSignals")
                ),
                "source_relationship_type": relationship_type,
            }
        },
    )


def map_index_payload(
    payload: dict[str, Any],
    *,
    now: Callable[[], datetime] | None = None,
) -> GraphSnapshot:
    clock = _clock(now)
    repo_id = _string_value(_get_any(payload, "repo_id", "repoId")) or ""
    graph_id = _string_value(_get_any(payload, "graph_id", "graphId")) or f"GRAPH-{repo_id}"
    trace_id = (
        _string_value(_get_any(payload, "trace_id", "traceId"))
        or f"TRACE-INDEX-{repo_id}"
    )
    nodes = [
        map_gitnexus_node(
            node_payload,
            graph_id=graph_id,
            repo_id=repo_id,
            trace_id=trace_id,
            now=clock,
        )
        for node_payload in _payload_list(payload, "nodes", "vertices")
    ]
    nodes_by_id = {node.node_id: node for node in nodes}
    edges = [
        edge
        for edge_payload in _payload_list(payload, "relationships", "edges")
        if (
            edge := map_gitnexus_edge(
                edge_payload,
                graph_id=graph_id,
                trace_id=trace_id,
                nodes_by_id=nodes_by_id,
                now=clock,
            )
        )
        is not None
    ]

    return GraphSnapshot(
        graph_id=graph_id,
        repo_id=repo_id,
        nodes=nodes,
        edges=edges,
        evidence_refs=_collect_evidence(nodes, edges),
        generated_at=clock(),
    )


def map_query_payload(
    payload: dict[str, Any],
    *,
    query: GraphQuery,
    now: Callable[[], datetime] | None = None,
) -> GraphContext:
    if payload.get("not_found") is True:
        return GraphContext(
            trace_id=query.trace_id,
            matched_nodes=[],
            matched_edges=[],
            graph_paths=[],
            evidence_refs=[],
            confidence=0.0,
        )

    clock = _clock(now)
    graph_id = _string_value(_get_any(payload, "graph_id", "graphId")) or query.graph_id
    nodes = [
        map_gitnexus_node(
            node_payload,
            graph_id=graph_id,
            repo_id=query.repo_id,
            trace_id=query.trace_id,
            now=clock,
        )
        for node_payload in _payload_list(payload, "nodes", "vertices")
    ]
    nodes_by_id = {node.node_id: node for node in nodes}
    edges = [
        edge
        for edge_payload in _payload_list(payload, "relationships", "edges")
        if (
            edge := map_gitnexus_edge(
                edge_payload,
                graph_id=graph_id,
                trace_id=query.trace_id,
                nodes_by_id=nodes_by_id,
                now=clock,
            )
        )
        is not None
    ]

    return GraphContext(
        trace_id=query.trace_id,
        matched_nodes=nodes,
        matched_edges=edges,
        graph_paths=_graph_paths(
            _any_list(payload, "paths", "graph_paths"),
            nodes_by_id=nodes_by_id,
        ),
        evidence_refs=_collect_evidence(nodes, edges),
        confidence=_graph_context_confidence(edges),
    )


def _clock(now: Callable[[], datetime] | None) -> Callable[[], datetime]:
    return now or (lambda: datetime.now(UTC))


def _properties(payload: dict[str, Any]) -> dict[str, Any]:
    properties = payload.get("properties")
    return properties if isinstance(properties, dict) else {}


def _get_any(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _payload_list(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    value = _get_any(payload, *keys)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _any_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    value = _get_any(payload, *keys)
    return value if isinstance(value, list) else []


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _node_type(payload: dict[str, Any]) -> str:
    properties = _properties(payload)
    labels = _list_value(_get_any(payload, "labels", "label"))
    return (
        _string_value(_get_any(payload, "type", "node_type", "nodeType"))
        or _string_value(_get_any(properties, "type", "kind"))
        or (_string_value(labels[0]) if labels else None)
        or "Unknown"
    )


def _source_details(
    payload: dict[str, Any],
) -> tuple[str | None, int | None, int | None, str | None]:
    properties = _properties(payload)
    location = _location(payload)
    file_path = _string_value(
        _get_any(payload, "file_path", "filePath")
        or _get_any(properties, "file_path", "filePath", "path")
        or _get_any(location, "file_path", "filePath", "path")
    )
    start_line = _int_value(
        _get_any(payload, "start_line", "startLine")
        or _get_any(properties, "start_line", "startLine", "line")
        or _get_any(location, "start_line", "startLine", "line")
    )
    end_line = _int_value(
        _get_any(payload, "end_line", "endLine")
        or _get_any(properties, "end_line", "endLine")
        or _get_any(location, "end_line", "endLine")
    )
    excerpt = _string_value(
        _get_any(payload, "excerpt", "snippet")
        or _get_any(properties, "excerpt", "snippet")
        or _get_any(location, "excerpt", "snippet")
    )
    return file_path, start_line, end_line, excerpt


def _location(payload: dict[str, Any]) -> dict[str, Any]:
    location = _get_any(payload, "source_location", "sourceLocation", "location")
    return location if isinstance(location, dict) else {}


def _source_location(
    file_path: str | None,
    start_line: int | None,
    end_line: int | None,
) -> SourceLocation | None:
    if file_path is None:
        return None
    return SourceLocation(file_path=file_path, start_line=start_line, end_line=end_line)


def _edge_source_details(
    payload: dict[str, Any],
    *,
    source_node: Node | None,
    target_node: Node | None,
) -> tuple[str | None, int | None, int | None, str | None]:
    file_path, start_line, end_line, excerpt = _source_details(payload)
    if file_path:
        return file_path, start_line, end_line, excerpt
    for node in (source_node, target_node):
        if node and node.source_location:
            return (
                node.source_location.file_path,
                node.source_location.start_line,
                node.source_location.end_line,
                None,
            )
    return None, None, None, excerpt


def _extraction_method(payload: dict[str, Any]) -> ExtractionMethod | str:
    properties = _properties(payload)
    return (
        _get_any(payload, "extraction_method", "extractionMethod")
        or _get_any(properties, "extraction_method", "extractionMethod")
        or ExtractionMethod.JAVA_PARSER
    )


def _confidence(payload: dict[str, Any], *, default: float) -> float:
    properties = _properties(payload)
    value = _get_any(payload, "confidence")
    if value is None:
        value = _get_any(properties, "confidence")
    try:
        confidence = float(value) if value is not None else default
    except (TypeError, ValueError):
        confidence = default
    return min(max(confidence, 0.0), 1.0)


def _evidence_ref(
    *,
    trace_id: str,
    source_id: str | None,
    file_path: str | None,
    start_line: int | None,
    end_line: int | None,
    excerpt: str | None,
    extraction_method: ExtractionMethod | str,
    confidence: float,
    now: Callable[[], datetime],
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=_evidence_id(
            trace_id=trace_id,
            source_id=source_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        ),
        trace_id=trace_id,
        source_type=SourceType.CODE,
        source_id=source_id,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        excerpt=excerpt,
        excerpt_hash=_excerpt_hash(excerpt),
        extraction_method=extraction_method,
        confidence=confidence,
        created_at=now(),
    )


def _evidence_id(
    *,
    trace_id: str,
    source_id: str | None,
    file_path: str | None,
    start_line: int | None,
    end_line: int | None,
) -> str:
    identity = "|".join(
        [
            trace_id,
            source_id or "",
            file_path or "",
            str(start_line or ""),
            str(end_line or ""),
        ]
    )
    return f"EV-GN-{sha256(identity.encode('utf-8')).hexdigest()[:12]}"


def _excerpt_hash(excerpt: str | None) -> str | None:
    if excerpt is None:
        return None
    return sha256(excerpt.encode("utf-8")).hexdigest()[:12]


def _collect_evidence(nodes: list[Node], edges: list[Edge]) -> list[EvidenceRef]:
    evidence_refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for item in [*nodes, *edges]:
        for evidence_ref in item.evidence_refs:
            if evidence_ref.evidence_id in seen:
                continue
            seen.add(evidence_ref.evidence_id)
            evidence_refs.append(evidence_ref)
    return evidence_refs


def _graph_paths(paths: list[Any], *, nodes_by_id: dict[str, Node]) -> list[list[str]]:
    normalized_paths: list[list[str]] = []
    for path in paths:
        path_items = path.get("nodes") if isinstance(path, dict) else path
        if not isinstance(path_items, list):
            continue
        normalized_paths.append(
            [
                _path_item_label(item, nodes_by_id=nodes_by_id)
                for item in path_items
            ]
        )
    return normalized_paths


def _path_item_label(item: Any, *, nodes_by_id: dict[str, Node]) -> str:
    item_id = _string_value(item)
    if item_id and item_id in nodes_by_id:
        node = nodes_by_id[item_id]
        return node.qualified_name or node.name or node.node_id
    return item_id or ""


def _graph_context_confidence(edges: list[Edge]) -> float:
    if not edges:
        return 0.0
    average_edge_confidence = sum(edge.confidence for edge in edges) / len(edges)
    max_edge_evidence_confidence = max(
        evidence_ref.confidence
        for edge in edges
        for evidence_ref in edge.evidence_refs
    )
    return round(min(average_edge_confidence, max_edge_evidence_confidence), 6)
