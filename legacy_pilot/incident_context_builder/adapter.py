import os
from abc import ABC, abstractmethod
from collections.abc import Callable

from legacy_pilot.contracts.models import (
    AlertEvent,
    EvidenceBundle,
    GraphContext,
    GraphQuery,
    IncidentMatch,
    IncidentQuery,
)
from legacy_pilot.incident_context_builder.evidence_builder import (
    build_evidence_bundle_from_graph_context,
    build_graph_query,
)
from legacy_pilot.incident_context_builder.signals import parse_alert_event


INCIDENT_CONTEXT_BACKEND_ENV = "LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND"
DEFAULT_INCIDENT_CONTEXT_BACKEND = "graph_context"
ALLOWED_INCIDENT_CONTEXT_BACKENDS = ("graph_context",)
MIN_RECALL_EVIDENCE_REFS = 2
RECALL_MAX_DEPTH = 6


class IncidentContextBuilderAdapter(ABC):
    @abstractmethod
    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        ...

    @abstractmethod
    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        ...


class GraphBackedIncidentContextBuilderAdapter(IncidentContextBuilderAdapter):
    def __init__(
        self,
        *,
        query_graph: Callable[[GraphQuery], GraphContext],
        find_similar_incidents: Callable[[IncidentQuery], list[IncidentMatch]],
    ):
        self._query_graph = query_graph
        self._find_similar_incidents = find_similar_incidents

    def submit_alert(self, alert: AlertEvent) -> IncidentQuery:
        signals = parse_alert_event(alert)
        return IncidentQuery(
            trace_id=f"TRACE-{alert.alert_id}",
            repo_id=alert.repo_id,
            graph_id=alert.graph_id,
            error_type=signals.error_type,
            suspected_location=signals.suspected_location,
            endpoint=signals.endpoint,
            keywords=signals.keywords,
            query_terms=signals.query_terms,
            contract_version=alert.contract_version,
        )

    def build_evidence_bundle(self, query: IncidentQuery) -> EvidenceBundle:
        graph_query = build_graph_query(query)
        graph_context = self._query_graph(graph_query)
        if _needs_recall_retry(graph_context):
            graph_context = _merge_graph_contexts(
                graph_context,
                self._query_graph(_recall_graph_query(query, graph_query)),
            )
        return build_evidence_bundle_from_graph_context(
            query=query,
            graph_context=graph_context,
            similar_incidents=self._find_similar_incidents(query),
        )


def create_incident_context_builder_adapter(
    *,
    backend: str | None = None,
    query_graph: Callable[[GraphQuery], GraphContext] | None = None,
    find_similar_incidents: Callable[[IncidentQuery], list[IncidentMatch]] | None = None,
) -> IncidentContextBuilderAdapter:
    selected_backend = (
        backend
        or os.getenv(INCIDENT_CONTEXT_BACKEND_ENV)
        or DEFAULT_INCIDENT_CONTEXT_BACKEND
    )
    normalized = selected_backend.strip().lower()
    if normalized == "graph_context":
        if query_graph is None or find_similar_incidents is None:
            raise ValueError(
                "graph_context incident context backend requires "
                "query_graph and find_similar_incidents"
            )
        return GraphBackedIncidentContextBuilderAdapter(
            query_graph=query_graph,
            find_similar_incidents=find_similar_incidents,
        )
    allowed = ", ".join(ALLOWED_INCIDENT_CONTEXT_BACKENDS)
    raise ValueError(
        f"Unsupported incident context backend: {selected_backend}. "
        f"Allowed values: {allowed}."
    )


def _needs_recall_retry(graph_context: GraphContext) -> bool:
    return (
        not graph_context.graph_paths
        or not graph_context.evidence_refs
        or len(graph_context.evidence_refs) < MIN_RECALL_EVIDENCE_REFS
    )


def _recall_graph_query(query: IncidentQuery, base_query: GraphQuery) -> GraphQuery:
    recall_terms = _dedupe(
        [
            *base_query.query_terms,
            *query.query_terms,
            *query.keywords,
            query.suspected_location,
            query.endpoint,
            query.error_type,
        ]
    )
    return base_query.model_copy(
        update={
            "query_terms": recall_terms,
            "max_depth": max(base_query.max_depth, RECALL_MAX_DEPTH),
        }
    )


def _merge_graph_contexts(primary: GraphContext, recalled: GraphContext) -> GraphContext:
    return GraphContext(
        trace_id=primary.trace_id,
        matched_nodes=_dedupe_by(primary.matched_nodes, recalled.matched_nodes, "node_id"),
        matched_edges=_dedupe_by(primary.matched_edges, recalled.matched_edges, "edge_id"),
        graph_paths=_dedupe_paths([*primary.graph_paths, *recalled.graph_paths]),
        evidence_refs=_dedupe_by(
            primary.evidence_refs,
            recalled.evidence_refs,
            "evidence_id",
        ),
        confidence=max(primary.confidence, recalled.confidence),
    )


def _dedupe_by(first: list, second: list, attr: str) -> list:
    output = []
    seen: set[str] = set()
    for item in [*first, *second]:
        key = str(getattr(item, attr))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _dedupe_paths(paths: list[list[str]]) -> list[list[str]]:
    output: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        key = tuple(path)
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output


def _dedupe(values: list[str | None]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
