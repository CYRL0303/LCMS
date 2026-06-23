from legacy_pilot.code_knowledge_core.graph_store import (
    DisabledGraphStore,
    payload_hash,
)


def test_payload_hash_is_stable_for_key_order_changes():
    left = {
        "repo_id": "repo-a",
        "graph_id": "GRAPH-repo-a",
        "nodes": [{"id": "Method:A", "type": "Method", "name": "A"}],
        "relationships": [],
    }
    right = {
        "relationships": [],
        "nodes": [{"name": "A", "type": "Method", "id": "Method:A"}],
        "graph_id": "GRAPH-repo-a",
        "repo_id": "repo-a",
    }

    assert payload_hash(left) == payload_hash(right)


def test_disabled_graph_store_ignores_save_and_loads_nothing():
    store = DisabledGraphStore()

    store.save_payload(
        repo_id="repo-a",
        graph_id="GRAPH-repo-a",
        payload={"repo_id": "repo-a", "graph_id": "GRAPH-repo-a"},
    )

    assert store.load_payload(repo_id="repo-a", graph_id="GRAPH-repo-a") is None
