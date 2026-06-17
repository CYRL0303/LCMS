from dataclasses import dataclass
from typing import Literal

from legacy_pilot.contracts.models import GraphQuery


QueryPlanKind = Literal[
    "route_context",
    "symbol_context",
    "sql",
    "config",
    "exception",
    "impact",
    "keyword",
]


@dataclass(frozen=True)
class GraphQueryPlan:
    kind: QueryPlanKind
    term: str


def plan_graph_query(query: GraphQuery) -> GraphQueryPlan:
    term = _first_query_term(query)
    node_filters = {_normalized_filter(value) for value in query.node_filters}
    edge_filters = {_normalized_filter(value) for value in query.edge_filters}

    if term.startswith("/"):
        return GraphQueryPlan(kind="route_context", term=term)
    if {"table", "sql"} & node_filters:
        return GraphQueryPlan(kind="sql", term=term)
    if "config" in node_filters:
        return GraphQueryPlan(kind="config", term=term)
    if "exception" in node_filters:
        return GraphQueryPlan(kind="exception", term=term)
    if "impact" in edge_filters:
        return GraphQueryPlan(kind="impact", term=term)
    if "." in term:
        return GraphQueryPlan(kind="symbol_context", term=term)
    return GraphQueryPlan(kind="keyword", term=term)


def _first_query_term(query: GraphQuery) -> str:
    for term in query.query_terms:
        stripped = term.strip()
        if stripped:
            return stripped
    return ""


def _normalized_filter(value: str) -> str:
    return value.strip().lower()
