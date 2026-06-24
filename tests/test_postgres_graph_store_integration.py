import os
from datetime import UTC, datetime

import pytest

from legacy_pilot.code_knowledge_core.graph_store import PostgresGraphStore


pytestmark = pytest.mark.postgres_graph_store


def test_real_postgres_graph_store_round_trips_payload():
    if os.getenv("LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE") != "1":
        pytest.skip(
            "PostgreSQL graph store integration is opt-in; set "
            "LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE=1 and LEGACY_PILOT_GRAPH_STORE_DSN."
        )
    dsn = os.environ.get("LEGACY_PILOT_GRAPH_STORE_DSN")
    if not dsn:
        pytest.skip("LEGACY_PILOT_GRAPH_STORE_DSN is required.")

    table_name = os.getenv(
        "LEGACY_PILOT_GRAPH_STORE_TEST_TABLE",
        "legacy_pilot_graph_payloads_test",
    )
    store = PostgresGraphStore(
        dsn=dsn,
        table_name=table_name,
        now=lambda: datetime(2026, 6, 23, tzinfo=UTC),
    )
    payload = {
        "repo_id": "repo-postgres-test",
        "graph_id": "GRAPH-repo-postgres-test",
        "parser_version": "test-parser-v1",
        "semantic_enrichment_version": None,
        "nodes": [
            {
                "id": "Method:DatasetService.getVersion",
                "type": "Method",
                "name": "DatasetService.getVersion",
            }
        ],
        "relationships": [],
    }

    store.save_payload(
        repo_id="repo-postgres-test",
        graph_id="GRAPH-repo-postgres-test",
        payload=payload,
    )

    assert store.load_payload(
        repo_id="repo-postgres-test",
        graph_id="GRAPH-repo-postgres-test",
    ) == payload
