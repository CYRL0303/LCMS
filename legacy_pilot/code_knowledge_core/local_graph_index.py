from collections import defaultdict
from typing import Any


class LocalGraphIndex:
    def __init__(
        self,
        *,
        graph_id: str,
        nodes_by_id: dict[str, dict[str, Any]],
        relationships: list[dict[str, Any]],
    ):
        self._graph_id = graph_id
        self._nodes_by_id = nodes_by_id
        self._relationships = relationships
        self._incoming_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._outgoing_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._edge_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for relationship in relationships:
            source_id = _text(relationship.get("source_id"))
            target_id = _text(relationship.get("target_id"))
            if not source_id or not target_id:
                continue
            self._incoming_by_target[target_id].append(relationship)
            self._outgoing_by_source[source_id].append(relationship)
            self._edge_by_pair[(source_id, target_id)].append(relationship)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LocalGraphIndex":
        nodes_by_id = {
            str(node["id"]): dict(node)
            for node in payload.get("nodes", [])
            if isinstance(node, dict) and node.get("id")
        }
        relationships = [
            dict(relationship)
            for relationship in payload.get("relationships", [])
            if (
                isinstance(relationship, dict)
                and relationship.get("source_id") in nodes_by_id
                and relationship.get("target_id") in nodes_by_id
            )
        ]
        return cls(
            graph_id=_text(payload.get("graph_id")) or "",
            nodes_by_id=nodes_by_id,
            relationships=relationships,
        )

    def query(
        self,
        *,
        term: str,
        node_filters: list[str],
        edge_filters: list[str],
        max_depth: int,
    ) -> dict[str, Any]:
        seeds = self._matching_seed_nodes(
            term=term,
            node_filters=node_filters,
            edge_filters=edge_filters,
        )
        if not seeds:
            return self._not_found()

        paths = [
            self._longest_incoming_path(seed["id"], max_depth=max_depth)
            for seed in seeds
        ]
        relationships = self._relationships_for_paths(paths)
        nodes = self._nodes_for_result(seeds=seeds, paths=paths)

        return {
            "graph_id": self._graph_id,
            "nodes": nodes,
            "relationships": relationships,
            "paths": paths,
            "not_found": False,
        }

    def _matching_seed_nodes(
        self,
        *,
        term: str,
        node_filters: list[str],
        edge_filters: list[str],
    ) -> list[dict[str, Any]]:
        normalized_term = term.strip().lower()
        normalized_types = {_normalized(value) for value in node_filters}
        normalized_edge_types = {_normalized(value) for value in edge_filters}
        matches = [
            node
            for node in self._nodes_by_id.values()
            if _node_type_matches(node, normalized_types)
            and _node_matches_term(node, normalized_term)
            and self._node_edge_matches(node["id"], normalized_edge_types)
        ]
        return sorted(matches, key=lambda node: (_match_rank(node, normalized_term), node["id"]))

    def _node_edge_matches(self, node_id: str, normalized_edge_types: set[str]) -> bool:
        if not normalized_edge_types:
            return True
        incident_edges = [
            *self._incoming_by_target.get(node_id, []),
            *self._outgoing_by_source.get(node_id, []),
        ]
        return any(
            _normalized(_text(edge.get("type"))) in normalized_edge_types
            for edge in incident_edges
        )

    def _longest_incoming_path(self, seed_id: str, *, max_depth: int) -> list[str]:
        max_nodes = max(1, max_depth)

        def walk(node_id: str, seen: set[str]) -> list[str]:
            if len(seen) >= max_nodes:
                return [node_id]
            candidates: list[list[str]] = []
            for edge in self._incoming_by_target.get(node_id, []):
                source_id = _text(edge.get("source_id"))
                if not source_id or source_id in seen:
                    continue
                candidates.append(walk(source_id, seen | {source_id}) + [node_id])
            if not candidates:
                return [node_id]
            return max(candidates, key=lambda path: (len(path), path))

        return walk(seed_id, {seed_id})

    def _relationships_for_paths(self, paths: list[list[str]]) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in paths:
            for source_id, target_id in zip(path, path[1:]):
                for relationship in self._edge_by_pair.get((source_id, target_id), []):
                    relationship_id = _relationship_identity(relationship)
                    if relationship_id in seen:
                        continue
                    seen.add(relationship_id)
                    relationships.append(relationship)
        return relationships

    def _nodes_for_result(
        self,
        *,
        seeds: list[dict[str, Any]],
        paths: list[list[str]],
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for seed in seeds:
            node_id = seed["id"]
            seen.add(node_id)
            nodes.append(seed)
        for node_id in [node_id for path in paths for node_id in path]:
            if node_id in seen:
                continue
            node = self._nodes_by_id.get(node_id)
            if node is None:
                continue
            seen.add(node_id)
            nodes.append(node)
        return nodes

    def _not_found(self) -> dict[str, Any]:
        return {
            "graph_id": self._graph_id,
            "nodes": [],
            "relationships": [],
            "paths": [],
            "not_found": True,
        }


def _node_type_matches(node: dict[str, Any], normalized_types: set[str]) -> bool:
    if not normalized_types:
        return True
    return _normalized(_text(node.get("type"))) in normalized_types


def _node_matches_term(node: dict[str, Any], normalized_term: str) -> bool:
    if not normalized_term:
        return True
    haystack = [
        _text(node.get("id")),
        _text(node.get("name")),
        _text(node.get("qualifiedName")),
        _text(node.get("qualified_name")),
    ]
    properties = node.get("properties")
    if isinstance(properties, dict):
        haystack.extend(_text(value) for value in properties.values())
    return any(normalized_term in value.lower() for value in haystack if value)


def _match_rank(node: dict[str, Any], normalized_term: str) -> int:
    node_name = _text(node.get("name")).lower()
    node_id = _text(node.get("id")).lower()
    if node_name == normalized_term or node_id.endswith(f":{normalized_term}"):
        return 0
    if normalized_term in node_name:
        return 1
    return 2


def _relationship_identity(relationship: dict[str, Any]) -> str:
    return (
        _text(relationship.get("id"))
        or "|".join(
            [
                _text(relationship.get("source_id")),
                _text(relationship.get("type")),
                _text(relationship.get("target_id")),
            ]
        )
    )


def _normalized(value: str) -> str:
    return value.strip().lower()


def _text(value: Any) -> str:
    return str(value) if value is not None else ""
