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
        graph_context = self._query_graph(build_graph_query(query))
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
