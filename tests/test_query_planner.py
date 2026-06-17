from legacy_pilot.code_knowledge_core.query_planner import plan_graph_query
from legacy_pilot.contracts.models import GraphQuery


def graph_query(**overrides):
    values = {
        "repo_id": "repo-prod",
        "graph_id": "GRAPH-prod",
        "query_terms": ["DatasetService.getVersion"],
        "node_filters": [],
        "edge_filters": [],
        "max_depth": 4,
        "trace_id": "TRACE-QP",
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return GraphQuery(**values)


def test_query_planner_routes_sql_terms_to_sql_lookup():
    plan = plan_graph_query(
        graph_query(
            query_terms=["dataset_version"],
            node_filters=["Table"],
            edge_filters=["READS_TABLE"],
            trace_id="TRACE-SQL",
        )
    )

    assert plan.kind == "sql"
    assert plan.term == "dataset_version"


def test_query_planner_routes_route_terms_to_route_context():
    plan = plan_graph_query(graph_query(query_terms=["/api/dataset/version"]))

    assert plan.kind == "route_context"
    assert plan.term == "/api/dataset/version"


def test_query_planner_keeps_route_priority_across_mixed_terms():
    plan = plan_graph_query(
        graph_query(
            query_terms=["DatasetService.getVersion", "/api/dataset/version"],
            node_filters=["Method"],
        )
    )

    assert plan.kind == "route_context"
    assert plan.term == "/api/dataset/version"


def test_query_planner_routes_dotted_terms_to_symbol_context():
    plan = plan_graph_query(graph_query(query_terms=["DatasetService.getVersion"]))

    assert plan.kind == "symbol_context"
    assert plan.term == "DatasetService.getVersion"


def test_query_planner_routes_config_filters_to_config_lookup():
    plan = plan_graph_query(
        graph_query(query_terms=["legacy.dataset.cache-enabled"], node_filters=["Config"])
    )

    assert plan.kind == "config"
    assert plan.term == "legacy.dataset.cache-enabled"


def test_query_planner_routes_exception_filters_to_exception_lookup():
    plan = plan_graph_query(
        graph_query(query_terms=["DatasetNotFoundException"], node_filters=["Exception"])
    )

    assert plan.kind == "exception"
    assert plan.term == "DatasetNotFoundException"


def test_query_planner_routes_impact_edge_filters_to_impact_query():
    plan = plan_graph_query(
        graph_query(query_terms=["DatasetService"], edge_filters=["impact"])
    )

    assert plan.kind == "impact"
    assert plan.term == "DatasetService"


def test_query_planner_uses_keyword_for_plain_terms():
    plan = plan_graph_query(graph_query(query_terms=["dataset"]))

    assert plan.kind == "keyword"
    assert plan.term == "dataset"
