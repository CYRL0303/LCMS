from legacy_pilot.code_knowledge_core.local_graph_index import LocalGraphIndex


def test_local_graph_index_finds_table_and_upstream_path():
    index = LocalGraphIndex.from_payload(
        {
            "graph_id": "GRAPH-prod",
            "nodes": [
                {
                    "id": "Method:DatasetService.getVersion",
                    "type": "Method",
                    "name": "getVersion",
                },
                {
                    "id": "SQL:selectVersionById",
                    "type": "SQL",
                    "name": "selectVersionById",
                },
                {
                    "id": "Table:dataset_version",
                    "type": "Table",
                    "name": "dataset_version",
                },
            ],
            "relationships": [
                {
                    "id": "R1",
                    "source_id": "Method:DatasetService.getVersion",
                    "target_id": "SQL:selectVersionById",
                    "type": "EXECUTES_SQL",
                },
                {
                    "id": "R2",
                    "source_id": "SQL:selectVersionById",
                    "target_id": "Table:dataset_version",
                    "type": "READS_TABLE",
                },
            ],
        }
    )

    result = index.query(
        term="dataset_version",
        node_filters=["Table"],
        edge_filters=["READS_TABLE"],
        max_depth=4,
    )

    assert result["not_found"] is False
    assert result["nodes"][0]["id"] == "Table:dataset_version"
    assert result["paths"][0] == [
        "Method:DatasetService.getVersion",
        "SQL:selectVersionById",
        "Table:dataset_version",
    ]
    assert {edge["type"] for edge in result["relationships"]} == {
        "EXECUTES_SQL",
        "READS_TABLE",
    }


def test_local_graph_index_keeps_full_structure_chain_when_edge_filter_identifies_seed():
    payload = {
        "graph_id": "GRAPH-prod",
        "nodes": [
            {"id": "Controller:getVersion", "type": "Method", "name": "getVersion"},
            {"id": "Service:getVersion", "type": "Method", "name": "getVersion"},
            {"id": "Mapper:selectVersionById", "type": "Method", "name": "selectVersionById"},
            {"id": "SQL:selectVersionById", "type": "SQL", "name": "selectVersionById"},
            {"id": "Table:dataset_version", "type": "Table", "name": "dataset_version"},
        ],
        "relationships": [
            {
                "id": "R1",
                "source_id": "Controller:getVersion",
                "target_id": "Service:getVersion",
                "type": "CALLS",
            },
            {
                "id": "R2",
                "source_id": "Service:getVersion",
                "target_id": "Mapper:selectVersionById",
                "type": "CALLS",
            },
            {
                "id": "R3",
                "source_id": "Mapper:selectVersionById",
                "target_id": "SQL:selectVersionById",
                "type": "EXECUTES_SQL",
            },
            {
                "id": "R4",
                "source_id": "SQL:selectVersionById",
                "target_id": "Table:dataset_version",
                "type": "READS_TABLE",
            },
        ],
    }

    result = LocalGraphIndex.from_payload(payload).query(
        term="dataset_version",
        node_filters=["Table"],
        edge_filters=["READS_TABLE"],
        max_depth=5,
    )

    assert result["paths"] == [
        [
            "Controller:getVersion",
            "Service:getVersion",
            "Mapper:selectVersionById",
            "SQL:selectVersionById",
            "Table:dataset_version",
        ]
    ]
    assert {edge["type"] for edge in result["relationships"]} == {
        "CALLS",
        "EXECUTES_SQL",
        "READS_TABLE",
    }


def test_local_graph_index_requires_edge_filter_to_match_seed_context():
    index = LocalGraphIndex.from_payload(
        {
            "graph_id": "GRAPH-prod",
            "nodes": [
                {"id": "SQL:selectVersionById", "type": "SQL", "name": "selectVersionById"},
                {"id": "Table:dataset_version", "type": "Table", "name": "dataset_version"},
            ],
            "relationships": [
                {
                    "id": "R1",
                    "source_id": "SQL:selectVersionById",
                    "target_id": "Table:dataset_version",
                    "type": "READS_TABLE",
                },
            ],
        }
    )

    result = index.query(
        term="dataset_version",
        node_filters=["Table"],
        edge_filters=["WRITES_TABLE"],
        max_depth=4,
    )

    assert result == {
        "graph_id": "GRAPH-prod",
        "nodes": [],
        "relationships": [],
        "paths": [],
        "not_found": True,
    }


def test_local_graph_index_returns_single_config_node_without_edges():
    index = LocalGraphIndex.from_payload(
        {
            "graph_id": "GRAPH-prod",
            "nodes": [
                {
                    "id": "Config:src/main/resources/application.yml:legacy.dataset.cache-enabled",
                    "type": "Config",
                    "name": "legacy.dataset.cache-enabled",
                }
            ],
            "relationships": [],
        }
    )

    result = index.query(
        term="legacy.dataset.cache-enabled",
        node_filters=["Config"],
        edge_filters=[],
        max_depth=3,
    )

    assert result["not_found"] is False
    assert result["nodes"][0]["type"] == "Config"
    assert result["paths"] == [
        ["Config:src/main/resources/application.yml:legacy.dataset.cache-enabled"]
    ]


def test_local_graph_index_returns_not_found_when_no_seed_matches():
    index = LocalGraphIndex.from_payload({"graph_id": "GRAPH-prod", "nodes": []})

    result = index.query(
        term="missing",
        node_filters=["Exception"],
        edge_filters=[],
        max_depth=3,
    )

    assert result == {
        "graph_id": "GRAPH-prod",
        "nodes": [],
        "relationships": [],
        "paths": [],
        "not_found": True,
    }
