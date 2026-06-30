import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from legacy_pilot.code_knowledge_core.errors import (
    CodeKnowledgeCoreError,
    IndexingError,
    QueryError,
)
from legacy_pilot.code_knowledge_core.enrichment import merge_graph_payloads
from legacy_pilot.code_knowledge_core.extractors.java_config import (
    extract_java_config_graph,
)
from legacy_pilot.code_knowledge_core.extractors.java_exception import (
    extract_java_exception_graph,
)
from legacy_pilot.code_knowledge_core.extractors.java_sql import (
    extract_mybatis_sql_graph,
)
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient, _repo_path
from legacy_pilot.code_knowledge_core.gitnexus_mapper import (
    map_index_payload,
    map_query_payload,
)
from legacy_pilot.code_knowledge_core.graph_store import (
    GraphStore,
    GraphStoreError,
    create_graph_store,
)
from legacy_pilot.code_knowledge_core.local_graph_index import LocalGraphIndex
from legacy_pilot.code_knowledge_core.query_planner import (
    GraphQueryPlan,
    plan_graph_query,
)
from legacy_pilot.code_knowledge_core.semantic import (
    DisabledSemanticEnricher,
    SemanticEnricher,
    create_semantic_enricher,
)
from legacy_pilot.contracts.models import (
    GraphContext,
    GraphQuery,
    GraphSnapshot,
    RepoIndexRequest,
)


STRUCTURE1_ENRICHED_PARSER_VERSION = "gitnexus_cli+structure1_sql_config_exception_v1"
DEFAULT_STRUCTURE1_ENRICHMENT_SOURCES = [
    "mybatis_sql",
    "java_config",
    "java_exception",
]
LOCAL_QUERYABLE_PLAN_KINDS = frozenset(
    {
        "route_context",
        "symbol_context",
        "sql",
        "config",
        "exception",
        "keyword",
    }
)


class CodeKnowledgeCoreAdapter(ABC):
    """Interface boundary for Structure 1: Code Knowledge Core.

    Owns only index_repo() and query_graph(). Contract gates
    (contract_version, trace_id) remain at MiddlewareRouter.
    """

    @abstractmethod
    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        """Index a legacy repo and return a structural graph snapshot."""
        ...

    @abstractmethod
    def query_graph(self, query: GraphQuery) -> GraphContext:
        """Query the code knowledge graph and return a traceable context."""
        ...


class GitNexusCliCodeKnowledgeCoreAdapter(CodeKnowledgeCoreAdapter):
    """Real Code Knowledge Core adapter backed by GitNexus CLI output."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        now: Callable[[], datetime] | None = None,
        index_enrichers: list[
            Callable[[RepoIndexRequest], dict[str, Any]]
        ] | None = None,
        query_enrichers: list[Callable[[GraphQuery], dict[str, Any]]] | None = None,
        semantic_enricher: SemanticEnricher | None = None,
        graph_store: GraphStore | None = None,
    ):
        self._client = client or GitNexusCliClient()
        self._now = now or (lambda: datetime.now(UTC))
        self._graph_store = graph_store or create_graph_store(now=self._now)
        uses_default_index_enrichers = index_enrichers is None
        self._index_enrichers = (
            index_enrichers
            if not uses_default_index_enrichers
            else _default_structure1_enrichers()
        )
        self._index_enrichment_sources = (
            list(DEFAULT_STRUCTURE1_ENRICHMENT_SOURCES)
            if uses_default_index_enrichers
            else [_enricher_name(enricher) for enricher in self._index_enrichers]
        )
        self._index_parser_version = (
            STRUCTURE1_ENRICHED_PARSER_VERSION if uses_default_index_enrichers else None
        )
        self._query_enrichers = query_enrichers or []
        self._semantic_enricher = semantic_enricher or create_semantic_enricher()
        self._local_indexes: dict[tuple[str, str], LocalGraphIndex] = {}

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        payload = self._client.index_repo(request)
        if self._index_enrichers:
            enricher_request = _request_with_resolved_repo_path(request, payload)
            payload = merge_graph_payloads(
                payload,
                _run_index_enrichers(self._index_enrichers, enricher_request),
            )
            payload = _with_enrichment_metadata(
                payload,
                enrichment_sources=self._index_enrichment_sources,
                parser_version=self._index_parser_version,
            )
        payload = _with_semantic_enrichment(payload, self._semantic_enricher)
        graph_id = _payload_graph_id(payload, request.repo_id)
        self._save_persisted_payload(
            repo_id=request.repo_id,
            graph_id=graph_id,
            payload=payload,
        )
        self._local_indexes[(request.repo_id, graph_id)] = LocalGraphIndex.from_payload(
            payload
        )
        return map_index_payload(payload, now=self._now)

    def _save_persisted_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            self._graph_store.save_payload(
                repo_id=repo_id,
                graph_id=graph_id,
                payload=payload,
            )
        except GraphStoreError as exc:
            raise IndexingError(
                exc.message,
                recoverable=True,
                diagnostics=exc.diagnostics,
            ) from exc

    def query_graph(self, query: GraphQuery) -> GraphContext:
        plan = plan_graph_query(query)
        local_payload = self._query_local_index(query, plan=plan)
        if local_payload is not None and local_payload.get("not_found") is not True:
            return map_query_payload(
                self._with_query_enrichers(local_payload, query),
                query=query,
                now=self._now,
            )

        if local_payload is None and self._should_restore_persisted_payload(
            query,
            plan,
        ):
            restored_payload = self._load_persisted_payload(query)
            if restored_payload is not None:
                self._local_indexes[(query.repo_id, query.graph_id)] = (
                    LocalGraphIndex.from_payload(restored_payload)
                )
                local_payload = self._query_local_index(query, plan=plan)
                if (
                    local_payload is not None
                    and local_payload.get("not_found") is not True
                ):
                    return map_query_payload(
                        self._with_query_enrichers(local_payload, query),
                        query=query,
                        now=self._now,
                    )

        payload = self._client.query_graph(query)
        payload = self._with_query_enrichers(payload, query)
        return map_query_payload(payload, query=query, now=self._now)

    def _load_persisted_payload(self, query: GraphQuery) -> dict[str, Any] | None:
        try:
            return self._graph_store.load_payload(
                repo_id=query.repo_id,
                graph_id=query.graph_id,
            )
        except GraphStoreError as exc:
            raise QueryError(
                exc.message,
                recoverable=True,
                diagnostics=exc.diagnostics,
            ) from exc

    def _should_restore_persisted_payload(
        self,
        query: GraphQuery,
        plan: GraphQueryPlan,
    ) -> bool:
        if not _is_local_queryable_plan(plan):
            return False
        return (query.repo_id, query.graph_id) not in self._local_indexes

    def _query_local_index(
        self,
        query: GraphQuery,
        *,
        plan: GraphQueryPlan | None = None,
    ) -> dict[str, Any] | None:
        plan = plan or plan_graph_query(query)
        if not _is_local_queryable_plan(plan):
            return None
        index = self._local_indexes.get((query.repo_id, query.graph_id))
        if index is None:
            return None
        return index.query(
            term=plan.term,
            node_filters=query.node_filters,
            edge_filters=query.edge_filters,
            max_depth=query.max_depth,
        )

    def _with_query_enrichers(
        self,
        payload: dict[str, Any],
        query: GraphQuery,
    ) -> dict[str, Any]:
        if not self._query_enrichers:
            return payload
        return merge_graph_payloads(
            payload,
            _run_query_enrichers(self._query_enrichers, query),
        )


class UnsupportedCodeKnowledgeCoreBackendAdapter(CodeKnowledgeCoreAdapter):
    """Failing adapter used so router contract gates still run first."""

    def __init__(self, backend: str):
        self._backend = backend

    def index_repo(self, request: RepoIndexRequest) -> GraphSnapshot:
        raise IndexingError(self._message(), recoverable=True)

    def query_graph(self, query: GraphQuery) -> GraphContext:
        raise QueryError(self._message(), recoverable=True)

    def _message(self) -> str:
        return f"Unsupported Code Knowledge Core backend: {self._backend}"


def create_code_knowledge_core_adapter(
    *,
    backend: str | None = None,
    now: Callable[[], datetime] | None = None,
    gitnexus_client: GitNexusCliClient | None = None,
) -> CodeKnowledgeCoreAdapter:
    selected_backend = backend or os.getenv("LEGACY_PILOT_CODE_CORE_BACKEND") or "gitnexus_cli"
    normalized_backend = selected_backend.strip().lower()
    if normalized_backend == "gitnexus_cli":
        return GitNexusCliCodeKnowledgeCoreAdapter(client=gitnexus_client, now=now)
    return UnsupportedCodeKnowledgeCoreBackendAdapter(selected_backend)


def _default_structure1_enrichers() -> list[Callable[[RepoIndexRequest], dict[str, Any]]]:
    return [
        _extract_mybatis_sql_for_request,
        _extract_java_config_for_request,
        _extract_java_exception_for_request,
    ]


def _is_local_queryable_plan(plan: GraphQueryPlan) -> bool:
    return plan.kind in LOCAL_QUERYABLE_PLAN_KINDS


def _with_enrichment_metadata(
    payload: dict[str, Any],
    *,
    enrichment_sources: list[str],
    parser_version: str | None,
) -> dict[str, Any]:
    enriched = dict(payload)
    metadata = payload.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata.setdefault("code_knowledge_core_backend", "gitnexus_cli")
    metadata.setdefault("graph_source", "gitnexus_cypher_markdown")
    metadata["enrichment_sources"] = list(enrichment_sources)
    enriched["metadata"] = metadata
    if parser_version is not None:
        enriched["parser_version"] = parser_version
    enriched.setdefault("semantic_enrichment_version", None)
    return enriched


def _with_semantic_enrichment(
    payload: dict[str, Any],
    semantic_enricher: SemanticEnricher,
) -> dict[str, Any]:
    if isinstance(semantic_enricher, DisabledSemanticEnricher):
        enriched = dict(payload)
        enriched.setdefault("semantic_enrichment_version", None)
        return enriched
    try:
        semantic_payload = semantic_enricher.enrich(
            [node for node in payload.get("nodes", []) if isinstance(node, dict)]
        )
    except CodeKnowledgeCoreError:
        raise
    except Exception as exc:
        raise IndexingError(
            "Structure 1 semantic enrichment failed while indexing repo.",
            recoverable=True,
            diagnostics={
                "semantic_backend": getattr(
                    semantic_enricher,
                    "backend_name",
                    semantic_enricher.__class__.__name__,
                ),
                "error_type": exc.__class__.__name__,
            },
        ) from exc

    enriched = merge_graph_payloads(payload, [semantic_payload])
    version = getattr(semantic_enricher, "semantic_enrichment_version", None)
    enriched["semantic_enrichment_version"] = version
    metadata = enriched.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata["semantic_enrichment"] = {
        "backend": getattr(
            semantic_enricher,
            "backend_name",
            semantic_enricher.__class__.__name__,
        ),
        "version": version,
        "verification_status": "pending",
        "confidence_cap": getattr(semantic_enricher, "confidence_cap", None),
    }
    enriched["metadata"] = metadata
    return enriched


def _payload_graph_id(payload: dict[str, Any], repo_id: str) -> str:
    graph_id = payload.get("graph_id") or payload.get("graphId")
    return str(graph_id) if graph_id else f"GRAPH-{repo_id}"


def _request_with_resolved_repo_path(
    request: RepoIndexRequest,
    payload: dict[str, Any],
) -> RepoIndexRequest:
    repo_path = payload.get("repo_path")
    if not repo_path:
        return request
    return request.model_copy(update={"repo_uri": Path(str(repo_path)).resolve().as_uri()})


def _run_index_enrichers(
    enrichers: list[Callable[[RepoIndexRequest], dict[str, Any]]],
    request: RepoIndexRequest,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for enricher in enrichers:
        try:
            payloads.append(enricher(request))
        except CodeKnowledgeCoreError:
            raise
        except Exception as exc:
            raise IndexingError(
                "Structure 1 enrichment failed while indexing repo.",
                recoverable=True,
                diagnostics={
                    "enricher": _enricher_name(enricher),
                    "error_type": exc.__class__.__name__,
                },
            ) from exc
    return payloads


def _run_query_enrichers(
    enrichers: list[Callable[[GraphQuery], dict[str, Any]]],
    query: GraphQuery,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for enricher in enrichers:
        try:
            payloads.append(enricher(query))
        except CodeKnowledgeCoreError:
            raise
        except Exception as exc:
            raise QueryError(
                "Structure 1 enrichment failed while querying graph.",
                recoverable=True,
                diagnostics={
                    "enricher": _enricher_name(enricher),
                    "error_type": exc.__class__.__name__,
                },
            ) from exc
    return payloads


def _enricher_name(enricher: Callable[..., dict[str, Any]]) -> str:
    return getattr(enricher, "__name__", enricher.__class__.__name__)


def _request_repo_root(request: RepoIndexRequest) -> Path:
    return Path(_repo_path(request.repo_uri))


def _extract_mybatis_sql_for_request(request: RepoIndexRequest) -> dict[str, Any]:
    return extract_mybatis_sql_graph(
        _request_repo_root(request),
        repo_id=request.repo_id,
        graph_id=f"GRAPH-{request.repo_id}",
    )


def _extract_java_config_for_request(request: RepoIndexRequest) -> dict[str, Any]:
    return extract_java_config_graph(
        _request_repo_root(request),
        repo_id=request.repo_id,
        graph_id=f"GRAPH-{request.repo_id}",
    )


def _extract_java_exception_for_request(request: RepoIndexRequest) -> dict[str, Any]:
    return extract_java_exception_graph(
        _request_repo_root(request),
        repo_id=request.repo_id,
        graph_id=f"GRAPH-{request.repo_id}",
    )
