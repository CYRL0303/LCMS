import json
import os
import subprocess
from collections.abc import Callable
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

from legacy_pilot.code_knowledge_core.errors import IndexingError, QueryError
from legacy_pilot.code_knowledge_core.query_planner import plan_graph_query
from legacy_pilot.code_knowledge_core.repo_importer import (
    RepoImportError,
    ResolvedRepo,
    _repo_path,
    resolve_repo_uri,
)
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


DEFAULT_GITNEXUS_BIN = "gitnexus"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_GRAPH_NODES = 5000
DEFAULT_MAX_GRAPH_EDGES = 10000
GITNEXUS_CYPHER_PARSER_VERSION = "gitnexus_cli+cypher_v1"


class GitNexusCliClient:
    """Subprocess client for GitNexus CLI output normalization.

    This class deliberately returns mapper-ready dictionaries instead of LCMS
    Pydantic response models; contract validation stays above the adapter layer.
    """

    def __init__(
        self,
        *,
        gitnexus_bin: str | None = None,
        repo_root: str | None = None,
        timeout_seconds: float | int | None = None,
        index_timeout_seconds: float | int | None = None,
        query_timeout_seconds: float | int | None = None,
        force_analyze: bool | None = None,
        max_graph_nodes: int | None = None,
        max_graph_edges: int | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ):
        self.gitnexus_bin = gitnexus_bin or os.getenv("GITNEXUS_BIN") or DEFAULT_GITNEXUS_BIN
        self.repo_root = repo_root or os.getenv("GITNEXUS_REPO_ROOT")
        timeout_default = _float_config(
            timeout_seconds,
            "GITNEXUS_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        )
        self.timeout_seconds = timeout_default
        self.index_timeout_seconds = _float_config(
            index_timeout_seconds,
            "GITNEXUS_INDEX_TIMEOUT_SECONDS",
            timeout_default,
        )
        self.query_timeout_seconds = _float_config(
            query_timeout_seconds,
            "GITNEXUS_QUERY_TIMEOUT_SECONDS",
            timeout_default,
        )
        self.force_analyze = _bool_config(
            force_analyze,
            "LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE",
            True,
        )
        self.max_graph_nodes = _int_config(
            max_graph_nodes,
            "LEGACY_PILOT_MAX_GRAPH_NODES",
            DEFAULT_MAX_GRAPH_NODES,
        )
        self.max_graph_edges = _int_config(
            max_graph_edges,
            "LEGACY_PILOT_MAX_GRAPH_EDGES",
            DEFAULT_MAX_GRAPH_EDGES,
        )
        self._runner = runner or subprocess.run
        self.last_diagnostics: dict[str, str] = {}

    def index_repo(self, request: RepoIndexRequest) -> dict[str, Any]:
        resolved_repo = self._validated_repo_path(request.repo_uri)
        repo_path = resolved_repo.local_path
        if self.force_analyze:
            self._run_analyze(repo_path, request.repo_id)
            payload = self._run_index_cypher(request)
        else:
            payload = self._run_index_cypher(request)
            if not _has_graph_rows(payload):
                self._run_analyze(repo_path, request.repo_id)
                payload = self._run_index_cypher(request)
        payload["repo_path"] = repo_path
        if resolved_repo.metadata:
            payload.setdefault("metadata", {}).update(resolved_repo.metadata)
        return payload

    def _validated_repo_path(self, repo_uri: str) -> ResolvedRepo:
        try:
            resolved_repo = resolve_repo_uri(repo_uri, runner=self._runner)
        except ValueError:
            raise self._error(
                "index",
                "repo_uri must resolve to a local filesystem path or GitHub URL.",
                diagnostics={"repo_uri": repo_uri},
            ) from None
        except RepoImportError as exc:
            raise self._error(
                "index",
                exc.message,
                diagnostics=exc.diagnostics,
            ) from exc
        repo_path = resolved_repo.local_path
        if not os.path.exists(repo_path):
            raise self._error(
                "index",
                "repo_uri path must exist before GitNexus analyze.",
                diagnostics={"repo_uri": repo_uri, "repo_path": repo_path},
            )
        return resolved_repo

    def _run_analyze(self, repo_path: str, repo_id: str) -> None:
        analyze_command = [
            self.gitnexus_bin,
            "analyze",
            repo_path,
            "--skip-git",
            "--index-only",
            "--name",
            repo_id,
        ]
        self._run_text(analyze_command, operation="index", timeout_category="index")

    def _run_index_cypher(self, request: RepoIndexRequest) -> dict[str, Any]:
        raw_payload = self._run_json(
            [
                self.gitnexus_bin,
                "cypher",
                (
                    "MATCH (n)-[r]->(m) "
                    "RETURN n.id, r.type, r.confidence, r.reason, m.id "
                    f"LIMIT {self.max_graph_edges}"
                ),
                "-r",
                request.repo_id,
            ],
            operation="index",
            timeout_category="query",
        )
        return self._normalize_cypher_graph_payload(raw_payload, request=request)

    def query_graph(self, query: GraphQuery) -> dict[str, Any]:
        plan = plan_graph_query(query)
        if plan.kind in {"sql", "config", "exception"}:
            return _not_found_query_payload(query.graph_id)
        if plan.kind == "route_context":
            uid = self._resolve_route_controller_uid(query)
        else:
            uid = self._resolve_symbol_uid(query, plan.term)
        if uid is None:
            return _not_found_query_payload(query.graph_id)

        raw_context = self._run_json(
            [
                self.gitnexus_bin,
                "context",
                "--uid",
                uid,
                "-r",
                query.repo_id,
                "--content",
            ],
            operation="query",
            timeout_category="query",
        )
        return self._normalize_context_query_payload(raw_context, query=query)

    def _run_text(
        self,
        command: list[str],
        *,
        operation: str,
        timeout_category: str,
    ) -> str:
        return self._run_completed(
            command,
            operation=operation,
            timeout_seconds=self._timeout_seconds(timeout_category),
        ).stdout or ""

    def _run_json(
        self,
        command: list[str],
        *,
        operation: str,
        timeout_category: str,
    ) -> dict[str, Any]:
        result = self._run_completed(
            command,
            operation=operation,
            timeout_seconds=self._timeout_seconds(timeout_category),
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise self._error(
                operation,
                f"GitNexus CLI returned invalid JSON while {_operation_phrase(operation)}.",
                diagnostics=self.last_diagnostics,
            ) from exc
        if not isinstance(payload, dict):
            raise self._error(
                operation,
                f"GitNexus CLI returned invalid JSON while {_operation_phrase(operation)}.",
                diagnostics=self.last_diagnostics,
            )
        return payload

    def _run_completed(
        self,
        command: list[str],
        *,
        operation: str,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._runner(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            diagnostics = _diagnostics(
                stderr=getattr(exc, "stderr", None),
                stdout=getattr(exc, "stdout", None),
                returncode=None,
            )
            raise self._error(
                operation,
                f"GitNexus CLI timed out while {_operation_phrase(operation)}.",
                diagnostics=diagnostics,
            ) from exc
        except FileNotFoundError as exc:
            raise self._error(
                operation,
                "GitNexus CLI executable was not found.",
                diagnostics={"executable": self.gitnexus_bin},
            ) from exc

        self.last_diagnostics = _diagnostics(
            stderr=result.stderr,
            stdout=result.stdout,
            returncode=result.returncode,
        )
        if result.returncode != 0:
            raise self._error(
                operation,
                f"GitNexus CLI failed while {_operation_phrase(operation)}.",
                diagnostics=self.last_diagnostics,
            )
        return result

    def _timeout_seconds(self, timeout_category: str) -> float:
        if timeout_category == "index":
            return self.index_timeout_seconds
        return self.query_timeout_seconds

    def _normalize_index_payload(
        self,
        raw_payload: dict[str, Any],
        *,
        request: RepoIndexRequest,
    ) -> dict[str, Any]:
        payload = _unwrap_payload(raw_payload)
        graph = _graph_payload(payload)
        repo_id = (
            _string_value(_get_any(payload, "repo_id", "repoId", "repositoryId"))
            or _string_value(_get_any(_metadata(payload), "repo_id", "repoId", "repositoryId"))
            or request.repo_id
        )
        graph_id = (
            _string_value(_get_any(payload, "graph_id", "graphId"))
            or _string_value(_get_any(graph, "graph_id", "graphId", "id"))
            or f"GRAPH-{repo_id}"
        )
        trace_id = (
            _string_value(_get_any(payload, "trace_id", "traceId"))
            or f"TRACE-INDEX-{request.repo_id}"
        )

        return {
            "repo_id": repo_id,
            "graph_id": graph_id,
            "trace_id": trace_id,
            "nodes": _limited_dicts(
                _get_any(payload, "nodes", "vertices")
                or _get_any(graph, "nodes", "vertices"),
                self.max_graph_nodes,
            ),
            "relationships": _limited_dicts(
                _get_any(payload, "relationships", "edges")
                or _get_any(graph, "relationships", "edges"),
                self.max_graph_edges,
            ),
        }

    def _normalize_query_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        payload = _unwrap_payload(raw_payload)
        graph = _graph_payload(payload)
        not_found = _not_found(payload)

        return {
            "graph_id": (
                _string_value(_get_any(payload, "graph_id", "graphId"))
                or _string_value(_get_any(graph, "graph_id", "graphId", "id"))
            ),
            "nodes": _limited_dicts(
                _get_any(payload, "nodes", "vertices")
                or _get_any(graph, "nodes", "vertices"),
                self.max_graph_nodes,
            ),
            "relationships": _limited_dicts(
                _get_any(payload, "relationships", "edges")
                or _get_any(graph, "relationships", "edges"),
                self.max_graph_edges,
            ),
            "paths": _list_value(_get_any(payload, "paths", "graph_paths", "graphPaths")),
            "not_found": not_found,
        }

    def _normalize_cypher_graph_payload(
        self,
        raw_payload: dict[str, Any],
        *,
        request: RepoIndexRequest,
    ) -> dict[str, Any]:
        markdown = _string_value(raw_payload.get("markdown")) or ""
        rows = _markdown_table_rows(markdown)
        nodes_by_id: dict[str, dict[str, Any]] = {}
        relationships: list[dict[str, Any]] = []
        routes_by_process: dict[str, list[str]] = {}
        methods_by_process: dict[str, list[str]] = {}

        for row in rows:
            source_id = _string_value(row.get("n.id"))
            target_id = _string_value(row.get("m.id"))
            relationship_type = _string_value(row.get("r.type")) or "RELATED_TO"
            if not source_id or not target_id:
                continue
            nodes_by_id.setdefault(source_id, _node_payload_from_gitnexus_id(source_id))
            nodes_by_id.setdefault(target_id, _node_payload_from_gitnexus_id(target_id))
            if relationship_type == "ENTRY_POINT_OF" and _is_route_id(source_id):
                routes_by_process.setdefault(target_id, []).append(source_id)
            if relationship_type == "STEP_IN_PROCESS" and _is_method_id(source_id):
                methods_by_process.setdefault(target_id, []).append(source_id)
            relationships.append(
                {
                    "id": _relationship_id(source_id, relationship_type, target_id),
                    "type": relationship_type,
                    "source_id": source_id,
                    "target_id": target_id,
                    "confidence": _float_value(row.get("r.confidence"), default=0.5),
                    "reason": _string_value(row.get("r.reason")),
                    "evidence_signals": [_string_value(row.get("r.reason")) or "cypher"],
                }
            )

        relationships.extend(
            _route_endpoint_relationships(
                routes_by_process=routes_by_process,
                methods_by_process=methods_by_process,
            )
        )

        return {
            "repo_id": request.repo_id,
            "graph_id": f"GRAPH-{request.repo_id}",
            "trace_id": f"TRACE-INDEX-{request.repo_id}",
            "parser_version": GITNEXUS_CYPHER_PARSER_VERSION,
            "semantic_enrichment_version": None,
            "metadata": {
                "code_knowledge_core_backend": "gitnexus_cli",
                "graph_source": "gitnexus_cypher_markdown",
            },
            "nodes": list(nodes_by_id.values())[: self.max_graph_nodes],
            "relationships": relationships[: self.max_graph_edges],
        }

    def _resolve_symbol_uid(self, query: GraphQuery, term: str | None = None) -> str | None:
        term = term or _first_symbol_query_term(query.query_terms)
        if term is None:
            return None
        raw_payload = self._run_json(
            [
                self.gitnexus_bin,
                "cypher",
                (
                    "MATCH (n) "
                    f"WHERE n.id CONTAINS {_cypher_string(term)} "
                    "RETURN n.id, n.name, n.filePath, n.startLine, n.endLine "
                    "LIMIT 10"
                ),
                "-r",
                query.repo_id,
            ],
            operation="query",
            timeout_category="query",
        )
        rows = _markdown_table_rows(_string_value(raw_payload.get("markdown")) or "")
        for row in rows:
            uid = _string_value(row.get("n.id"))
            if uid and term in uid:
                return uid
        return _string_value(rows[0].get("n.id")) if rows else None

    def _resolve_route_controller_uid(self, query: GraphQuery) -> str | None:
        route = _first_route_query_term(query.query_terms)
        if route is None:
            return None
        raw_payload = self._run_json(
            [
                self.gitnexus_bin,
                "cypher",
                (
                    "MATCH (n) "
                    f"WHERE n.content CONTAINS {_cypher_string(route)} "
                    "RETURN n.id, n.name, n.filePath "
                    "LIMIT 5"
                ),
                "-r",
                query.repo_id,
            ],
            operation="query",
            timeout_category="query",
        )
        rows = _markdown_table_rows(_string_value(raw_payload.get("markdown")) or "")
        for row in rows:
            file_path = _string_value(row.get("n.filePath")) or _string_value(row.get("n.id")) or ""
            class_name = _class_name_from_java_file(file_path)
            method_name = _method_name_from_route(route)
            if class_name and method_name:
                uid = self._resolve_symbol_uid(query, f"{class_name}.{method_name}")
                if uid:
                    return uid
        return None

    def _normalize_context_query_payload(
        self,
        raw_context: dict[str, Any],
        *,
        query: GraphQuery,
    ) -> dict[str, Any]:
        if raw_context.get("status") not in {None, "found"}:
            return _not_found_query_payload(query.graph_id)
        symbol = raw_context.get("symbol")
        if not isinstance(symbol, dict):
            return _not_found_query_payload(query.graph_id)

        center = _node_payload_from_context_item(symbol)
        center_id = center["id"]
        nodes_by_id = {center_id: center}
        relationships: list[dict[str, Any]] = []
        incoming_ids: list[str] = []
        outgoing_ids: list[str] = []

        for caller in _context_calls(raw_context, "incoming"):
            caller_node = _node_payload_from_context_item(caller)
            caller_id = caller_node["id"]
            nodes_by_id.setdefault(caller_id, caller_node)
            incoming_ids.append(caller_id)
            relationships.append(_relationship_payload(caller_id, "CALLS", center_id, "context-incoming"))

        for callee in _context_calls(raw_context, "outgoing"):
            callee_node = _node_payload_from_context_item(callee)
            callee_id = callee_node["id"]
            nodes_by_id.setdefault(callee_id, callee_node)
            outgoing_ids.append(callee_id)
            relationships.append(_relationship_payload(center_id, "CALLS", callee_id, "context-outgoing"))

        paths: list[list[str]] = []
        if incoming_ids and outgoing_ids:
            paths.append([incoming_ids[0], center_id, outgoing_ids[0]])
        elif incoming_ids:
            paths.append([incoming_ids[0], center_id])
        elif outgoing_ids:
            paths.append([center_id, outgoing_ids[0]])
        elif center_id:
            paths.append([center_id])

        return {
            "graph_id": query.graph_id,
            "nodes": list(nodes_by_id.values())[: self.max_graph_nodes],
            "relationships": relationships[: self.max_graph_edges],
            "paths": paths,
            "not_found": False,
        }

    def _error(
        self,
        operation: str,
        message: str,
        *,
        diagnostics: dict[str, str] | None = None,
    ) -> IndexingError | QueryError:
        if operation == "index":
            return IndexingError(message, recoverable=True, diagnostics=diagnostics)
        return QueryError(message, recoverable=True, diagnostics=diagnostics)


def _float_config(value: float | int | None, env_key: str, default: float) -> float:
    if value is not None:
        return float(value)
    env_value = os.getenv(env_key)
    if env_value is None:
        return default
    try:
        return float(env_value)
    except ValueError:
        return default


def _int_config(value: int | None, env_key: str, default: int) -> int:
    if value is not None:
        return int(value)
    env_value = os.getenv(env_key)
    if env_value is None:
        return default
    try:
        return int(env_value)
    except ValueError:
        return default


def _bool_config(value: bool | None, env_key: str, default: bool) -> bool:
    if value is not None:
        return bool(value)
    env_value = os.getenv(env_key)
    if env_value is None:
        return default
    normalized = env_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _has_graph_rows(payload: dict[str, Any]) -> bool:
    return bool(payload.get("nodes") or payload.get("relationships"))


def _operation_phrase(operation: str) -> str:
    return "indexing repo" if operation == "index" else "querying graph"


def _diagnostics(
    *,
    stderr: Any,
    stdout: Any,
    returncode: int | None,
) -> dict[str, str]:
    diagnostics: dict[str, str] = {}
    if stderr:
        diagnostics["stderr"] = _decode_text(stderr)
    if stdout:
        diagnostics["stdout"] = _decode_text(stdout)
    if returncode is not None:
        diagnostics["returncode"] = str(returncode)
    return diagnostics


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _unwrap_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "result", "payload"):
        value = raw_payload.get(key)
        if isinstance(value, dict):
            return value
    return raw_payload


def _graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("graph", "subgraph"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _get_any(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _limited_dicts(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value[:limit] if isinstance(item, dict)]


def _not_found(payload: dict[str, Any]) -> bool:
    value = _get_any(payload, "not_found", "notFound")
    if isinstance(value, bool):
        return value
    status = _string_value(_get_any(payload, "status"))
    if status is None:
        return False
    return status.lower() in {"not_found", "not-found", "not found"}


def _markdown_table_rows(markdown: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = _markdown_table_cells(lines[0])
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = _markdown_table_cells(line)
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _node_payload_from_gitnexus_id(node_id: str) -> dict[str, Any]:
    node_type, _, body = node_id.partition(":")
    normalized_type = "API Endpoint" if node_type == "Route" else node_type
    name = body or node_id
    file_path = None
    qualified_name = None
    if node_type in {"Class", "Interface", "Method"} and ":" in body:
        file_path, symbol = body.rsplit(":", 1)
        qualified_name = symbol.removesuffix("#1")
        name = qualified_name.split(".")[-1]
    elif node_type == "File":
        file_path = body
        name = os.path.basename(body)
    elif node_type == "Folder":
        file_path = body
        name = os.path.basename(body)

    properties: dict[str, Any] = {}
    if file_path:
        properties["filePath"] = file_path
    if qualified_name:
        properties["qualifiedName"] = qualified_name

    return {
        "id": node_id,
        "type": normalized_type or "Unknown",
        "name": name,
        "properties": properties,
    }


def _route_endpoint_relationships(
    *,
    routes_by_process: dict[str, list[str]],
    methods_by_process: dict[str, list[str]],
) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    for process_id, route_ids in routes_by_process.items():
        method_ids = methods_by_process.get(process_id, [])
        for route_id in route_ids:
            for method_id in method_ids:
                relationships.append(
                    {
                        "id": _relationship_id(route_id, "MAPS_TO_ENDPOINT", method_id),
                        "type": "MAPS_TO_ENDPOINT",
                        "source_id": route_id,
                        "target_id": method_id,
                        "confidence": 0.85,
                        "reason": "gitnexus-process-entrypoint",
                        "evidence_signals": [
                            "ENTRY_POINT_OF",
                            "STEP_IN_PROCESS",
                            process_id,
                        ],
                    }
                )
    return relationships


def _is_route_id(node_id: str) -> bool:
    return node_id.startswith("Route:")


def _is_method_id(node_id: str) -> bool:
    return node_id.startswith("Method:")


def _node_payload_from_context_item(item: dict[str, Any]) -> dict[str, Any]:
    uid = _string_value(_get_any(item, "uid", "id")) or ""
    payload = _node_payload_from_gitnexus_id(uid)
    name = _string_value(item.get("name"))
    kind = _string_value(item.get("kind"))
    file_path = _string_value(item.get("filePath"))
    start_line = _int_value(item.get("startLine"))
    end_line = _int_value(item.get("endLine"))

    if name:
        payload["name"] = name
    if kind:
        payload["type"] = kind
    if file_path:
        payload["properties"]["filePath"] = file_path
    if start_line is not None:
        payload["properties"]["startLine"] = start_line
    if end_line is not None:
        payload["properties"]["endLine"] = end_line
    if content := _string_value(item.get("content")):
        payload["properties"]["excerpt"] = content
    return payload


def _relationship_payload(
    source_id: str,
    relationship_type: str,
    target_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": _relationship_id(source_id, relationship_type, target_id),
        "type": relationship_type,
        "source_id": source_id,
        "target_id": target_id,
        "confidence": 0.85,
        "reason": reason,
        "evidence_signals": [reason],
    }


def _relationship_id(source_id: str, relationship_type: str, target_id: str) -> str:
    identity = "|".join([source_id, relationship_type, target_id])
    return f"GN-REL-{sha256(identity.encode('utf-8')).hexdigest()[:12]}"


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_symbol_query_term(query_terms: list[str]) -> str | None:
    for term in query_terms:
        if term and not term.startswith("/"):
            return term
    return None


def _first_route_query_term(query_terms: list[str]) -> str | None:
    for term in query_terms:
        if term and term.startswith("/"):
            return term
    return None


def _class_name_from_java_file(file_path: str) -> str | None:
    file_name = os.path.basename(file_path)
    if not file_name.endswith(".java"):
        return None
    class_name = file_name.removesuffix(".java")
    return class_name if class_name.endswith("Controller") else None


def _method_name_from_route(route: str) -> str | None:
    leaf = route.rstrip("/").rsplit("/", 1)[-1]
    if not leaf:
        return None
    parts = [part for part in leaf.replace("-", "_").split("_") if part]
    if not parts:
        return None
    return "get" + "".join(part[:1].upper() + part[1:] for part in parts)


def _context_calls(raw_context: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    value = raw_context.get(direction)
    if not isinstance(value, dict):
        return []
    calls = value.get("calls")
    if not isinstance(calls, list):
        return []
    return [item for item in calls if isinstance(item, dict)]


def _not_found_query_payload(graph_id: str | None) -> dict[str, Any]:
    return {
        "graph_id": graph_id,
        "nodes": [],
        "relationships": [],
        "paths": [],
        "not_found": True,
    }


def _cypher_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
