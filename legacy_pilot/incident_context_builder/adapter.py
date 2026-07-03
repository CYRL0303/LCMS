import os
import re
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
RECALL_MAX_TERMS = 6
JAVA_ROLE_SUFFIXES = (
    "Controller",
    "Service",
    "Repository",
    "Mapper",
    "DAO",
    "Dao",
    "Client",
    "Handler",
    "Manager",
    "Processor",
)
NOISY_RECALL_TERMS = {
    "Abstract",
    "Autowired",
    "Client",
    "Default",
    "Delegating",
    "Dispatcher",
    "Framework",
    "Injection",
    "Invocable",
    "Method",
    "Native",
    "Prepared",
    "PreparedStatement",
    "Proxy",
    "Request",
    "Servlet",
    "Spring",
    "SQLSyntax",
}
PASCAL_PART_RE = re.compile(r"[A-Z][a-z0-9]*")


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
    recall_terms = _high_recall_terms(query)
    if not recall_terms:
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


def _high_recall_terms(query: IncidentQuery) -> list[str]:
    terms = [*query.query_terms, *query.keywords, query.suspected_location]
    roots = _dedupe(_root_terms(terms))
    keywords = _dedupe(
        term for term in query.keywords if term and _is_recall_keyword(term)
    )
    classes = _dedupe(_class_terms(terms))
    return _dedupe([*roots, *keywords, *classes])[:RECALL_MAX_TERMS]


def _root_terms(terms) -> list[str]:
    output: list[str] = []
    for term in terms:
        class_name = _class_name(term)
        if not class_name:
            continue
        role_root = _role_root(class_name)
        if role_root:
            output.extend(_pascal_roots(role_root))
            continue
        output.extend(_pascal_roots(class_name))
    return _ranked_terms([term for term in output if _is_recall_pascal_term(term)])


def _ranked_terms(terms: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, term in enumerate(terms):
        counts[term] = counts.get(term, 0) + 1
        first_seen.setdefault(term, index)
    return sorted(counts, key=lambda term: (-counts[term], first_seen[term]))


def _class_terms(terms) -> list[str]:
    output: list[str] = []
    for term in terms:
        class_name = _class_name(term)
        if class_name and _role_root(class_name) and _is_recall_pascal_term(class_name):
            output.append(class_name)
    return output


def _class_name(term: str | None) -> str | None:
    if (
        not term
        or "/" in term
        or term.endswith(".java")
        or term.endswith(("Exception", "Error"))
    ):
        return None
    candidate = term.split(".", 1)[0]
    if not candidate or not candidate[:1].isupper():
        return None
    return candidate


def _role_root(class_name: str) -> str | None:
    for suffix in JAVA_ROLE_SUFFIXES:
        if class_name.endswith(suffix) and len(class_name) > len(suffix):
            return class_name[: -len(suffix)]
    return None


def _pascal_roots(value: str) -> list[str]:
    parts = PASCAL_PART_RE.findall(value)
    if len(parts) <= 1:
        return [value]
    return [parts[0], value]


def _is_recall_pascal_term(term: str) -> bool:
    first_part = PASCAL_PART_RE.findall(term)[:1]
    return (
        len(term) >= 3
        and term not in NOISY_RECALL_TERMS
        and (not first_part or first_part[0] not in NOISY_RECALL_TERMS)
        and not term.endswith(("Exception", "Error"))
    )


def _is_recall_keyword(term: str) -> bool:
    return bool(term) and "/" not in term and "." not in term


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
