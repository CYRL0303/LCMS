import json
import os
import subprocess
from collections.abc import Callable
from typing import Any

from legacy_pilot.code_knowledge_core.errors import IndexingError, QueryError
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


DEFAULT_GITNEXUS_BIN = "gitnexus"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_GRAPH_NODES = 5000
DEFAULT_MAX_GRAPH_EDGES = 10000


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
        max_graph_nodes: int | None = None,
        max_graph_edges: int | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ):
        self.gitnexus_bin = gitnexus_bin or os.getenv("GITNEXUS_BIN") or DEFAULT_GITNEXUS_BIN
        self.repo_root = repo_root or os.getenv("GITNEXUS_REPO_ROOT")
        self.timeout_seconds = _float_config(
            timeout_seconds,
            "GITNEXUS_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
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
        command = [
            self.gitnexus_bin,
            "index",
            "--repo-id",
            request.repo_id,
            "--repo-path",
            _repo_path(request.repo_uri),
            "--language",
            request.language_hint,
            "--parser-profile",
            request.parser_profile,
            "--max-nodes",
            str(self.max_graph_nodes),
            "--max-edges",
            str(self.max_graph_edges),
        ]
        raw_payload = self._run_json(command, operation="index")
        return self._normalize_index_payload(raw_payload, request=request)

    def query_graph(self, query: GraphQuery) -> dict[str, Any]:
        command = [
            self.gitnexus_bin,
            "query",
            "--repo-id",
            query.repo_id,
            "--graph-id",
            query.graph_id,
            "--max-depth",
            str(query.max_depth),
            "--max-nodes",
            str(self.max_graph_nodes),
            "--max-edges",
            str(self.max_graph_edges),
        ]
        for term in query.query_terms:
            command.extend(["--query-term", term])
        for node_filter in query.node_filters:
            command.extend(["--node-filter", node_filter])
        for edge_filter in query.edge_filters:
            command.extend(["--edge-filter", edge_filter])

        raw_payload = self._run_json(command, operation="query")
        return self._normalize_query_payload(raw_payload)

    def _run_json(self, command: list[str], *, operation: str) -> dict[str, Any]:
        try:
            result = self._runner(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
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


def _repo_path(repo_uri: str) -> str:
    if repo_uri.startswith("file://"):
        return repo_uri.removeprefix("file://")
    return repo_uri


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
