from typing import Any


def merge_graph_payloads(
    base_payload: dict[str, Any],
    enrichment_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes_by_id = {
        str(node.get("id")): dict(node)
        for node in base_payload.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    relationships_by_id = {
        str(edge.get("id")): dict(edge)
        for edge in base_payload.get("relationships", [])
        if isinstance(edge, dict) and edge.get("id")
    }

    for payload in enrichment_payloads:
        for node in payload.get("nodes", []):
            if isinstance(node, dict) and node.get("id"):
                nodes_by_id.setdefault(str(node["id"]), dict(node))
        for edge in payload.get("relationships", []):
            if isinstance(edge, dict) and edge.get("id"):
                relationships_by_id.setdefault(str(edge["id"]), dict(edge))

    enriched = dict(base_payload)
    enriched["nodes"] = list(nodes_by_id.values())
    enriched["relationships"] = list(relationships_by_id.values())
    return enriched
