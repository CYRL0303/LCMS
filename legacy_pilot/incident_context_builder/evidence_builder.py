from legacy_pilot.contracts.models import (
    EvidenceBundle,
    EvidenceRef,
    GraphContext,
    GraphQuery,
    IncidentMatch,
    IncidentQuery,
)


def graph_id_for_query(query: IncidentQuery) -> str:
    return query.graph_id or f"GRAPH-{query.repo_id}"


def build_graph_query(query: IncidentQuery) -> GraphQuery:
    return GraphQuery(
        repo_id=query.repo_id,
        graph_id=graph_id_for_query(query),
        query_terms=query.query_terms or [query.error_type],
        node_filters=[],
        edge_filters=[],
        max_depth=4,
        trace_id=query.trace_id,
        contract_version=query.contract_version,
    )


def build_evidence_bundle_from_graph_context(
    *,
    query: IncidentQuery,
    graph_context: GraphContext,
    similar_incidents: list[IncidentMatch],
) -> EvidenceBundle:
    code_evidence = _by_source_type(graph_context.evidence_refs, "code")
    sql_evidence = _by_source_type(graph_context.evidence_refs, "sql")
    config_evidence = _by_source_type(graph_context.evidence_refs, "config")
    log_evidence = _by_source_type(graph_context.evidence_refs, "log")
    missing_evidence = []
    if not graph_context.matched_nodes:
        missing_evidence.append("matched_nodes")
    if not graph_context.graph_paths:
        missing_evidence.append("graph_paths")
    if not graph_context.evidence_refs:
        missing_evidence.append("evidence_refs")
    return EvidenceBundle(
        trace_id=query.trace_id,
        repo_id=query.repo_id,
        contract_version=query.contract_version,
        alert_summary=_alert_summary(query),
        incident_query=query,
        matched_nodes=graph_context.matched_nodes,
        graph_paths=graph_context.graph_paths,
        code_evidence=code_evidence,
        sql_evidence=sql_evidence,
        config_evidence=config_evidence,
        log_evidence=log_evidence,
        similar_incidents=similar_incidents,
        missing_evidence=missing_evidence,
    )


def _alert_summary(query: IncidentQuery) -> str:
    if query.suspected_location:
        return f"{query.error_type} near {query.suspected_location}"
    return query.error_type


def _by_source_type(
    evidence_refs: list[EvidenceRef],
    source_type: str,
) -> list[EvidenceRef]:
    return [ref for ref in evidence_refs if ref.source_type == source_type]
