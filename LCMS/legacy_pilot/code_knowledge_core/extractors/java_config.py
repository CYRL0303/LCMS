from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - dependency is declared for production use.
    yaml = None


def extract_java_config_graph(
    repo_root: Path,
    *,
    repo_id: str,
    graph_id: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []

    for path in [*repo_root.rglob("application.yml"), *repo_root.rglob("application.yaml")]:
        for key, value, line in _flatten_yaml_file(path):
            nodes.append(_config_node(repo_root, path, key, value, line))

    for path in repo_root.rglob("application.properties"):
        for key, value, line in _read_properties(path):
            nodes.append(_config_node(repo_root, path, key, value, line))

    return {
        "repo_id": repo_id,
        "graph_id": graph_id,
        "nodes": nodes,
        "relationships": [],
    }


def _flatten_yaml_file(path: Path) -> list[tuple[str, Any, int | None]]:
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text) if yaml is not None else _parse_simple_yaml(text)
    line_map = _yaml_leaf_lines(text)
    return [
        (key, value, line_map.get(key))
        for key, value in _flatten_mapping(parsed)
    ]


def _flatten_mapping(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if not isinstance(value, dict):
        return []
    flattened: list[tuple[str, Any]] = []
    for key, child in value.items():
        key_text = str(key)
        full_key = f"{prefix}.{key_text}" if prefix else key_text
        if isinstance(child, dict):
            flattened.extend(_flatten_mapping(child, full_key))
        else:
            flattened.append((full_key, child))
    return flattened


def _yaml_leaf_lines(text: str) -> dict[str, int]:
    stack: list[tuple[int, str]] = []
    line_map: dict[str, int] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = stripped.partition(":")
        key = key.strip().strip("'\"")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = [item_key for _, item_key in stack] + [key]
        if value.strip():
            line_map[".".join(path)] = number
        else:
            stack.append((indent, key))
    return line_map


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = stripped.partition(":")
        key = key.strip().strip("'\"")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            parent[key] = value.strip().strip("'\"")
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def _read_properties(path: Path) -> list[tuple[str, str, int]]:
    entries: list[tuple[str, str, int]] = []
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        delimiter = "=" if "=" in line else ":"
        if delimiter not in line:
            continue
        key, _, value = line.partition(delimiter)
        entries.append((key.strip(), value.strip(), number))
    return entries


def _config_node(
    repo_root: Path,
    path: Path,
    key: str,
    value: Any,
    line: int | None,
) -> dict[str, Any]:
    relpath = path.relative_to(repo_root).as_posix()
    excerpt = f"{key}: {value}"
    return {
        "id": f"Config:{relpath}:{key}",
        "type": "Config",
        "name": key,
        "filePath": relpath,
        "startLine": line,
        "endLine": line,
        "excerpt": excerpt,
        "source_type": "config",
        "extraction_method": "regex",
        "confidence": 0.82,
        "properties": {"value": value},
    }
