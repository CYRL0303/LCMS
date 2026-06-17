import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


EXCEPTION_CLASS_RE = re.compile(r"class\s+(\w+Exception)\s+extends\s+(\w+Exception)")
THROW_RE = re.compile(r"throw\s+new\s+(\w+Exception)\s*\(")
HANDLER_RE = re.compile(r"@ExceptionHandler\s*\(\s*(\w+Exception)\.class\s*\)")
CLASS_RE = re.compile(r"\bclass\s+(\w+)\b|\binterface\s+(\w+)\b")
METHOD_RE = re.compile(
    r"\b(?:public|protected|private)\s+(?:static\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\([^)]*\)\s*\{"
)


@dataclass(frozen=True)
class JavaMethod:
    class_name: str
    name: str
    file_path: str
    start_line: int
    end_line: int

    @property
    def node_id(self) -> str:
        return f"Method:{self.file_path}:{self.class_name}.{self.name}#1"


def extract_java_exception_graph(
    repo_root: Path,
    *,
    repo_id: str,
    graph_id: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    exception_nodes: dict[str, str] = {}

    java_files = list(repo_root.rglob("*.java"))
    for java_path in java_files:
        relpath = _relpath(repo_root, java_path)
        text = java_path.read_text(encoding="utf-8")
        for match in EXCEPTION_CLASS_RE.finditer(text):
            exception_name = match.group(1)
            line = _line_number(text, match.start())
            node_id = f"Exception:{relpath}:{exception_name}"
            exception_nodes[exception_name] = node_id
            _append_once(
                nodes,
                seen_nodes,
                _exception_node(node_id, exception_name, relpath, line),
            )

    for java_path in java_files:
        relpath = _relpath(repo_root, java_path)
        text = java_path.read_text(encoding="utf-8")
        class_name = _class_name(text) or java_path.stem
        methods = _methods(text, relpath, class_name)

        for match in THROW_RE.finditer(text):
            exception_name = match.group(1)
            target_id = exception_nodes.get(exception_name)
            if target_id is None:
                continue
            line = _line_number(text, match.start())
            method = _method_at_line(methods, line)
            if method is None:
                continue
            _append_once(nodes, seen_nodes, _method_node(method))
            relationships.append(
                _edge(
                    method.node_id,
                    "THROWS_EXCEPTION",
                    target_id,
                    relpath,
                    line,
                    line,
                    _line_excerpt(text, line),
                )
            )

        for handler_match in HANDLER_RE.finditer(text):
            exception_name = handler_match.group(1)
            target_id = exception_nodes.get(exception_name)
            if target_id is None:
                continue
            annotation_line = _line_number(text, handler_match.start())
            method = _first_method_after(methods, annotation_line)
            if method is None:
                continue
            _append_once(nodes, seen_nodes, _method_node(method))
            relationships.append(
                _edge(
                    method.node_id,
                    "HANDLES_EXCEPTION",
                    target_id,
                    relpath,
                    annotation_line,
                    method.end_line,
                    _line_excerpt(text, annotation_line),
                )
            )

    return {
        "repo_id": repo_id,
        "graph_id": graph_id,
        "nodes": nodes,
        "relationships": relationships,
    }


def _exception_node(
    node_id: str,
    name: str,
    file_path: str,
    line: int,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "Exception",
        "name": name,
        "filePath": file_path,
        "startLine": line,
        "endLine": line,
        "source_type": "code",
        "extraction_method": "regex",
        "confidence": 0.84,
    }


def _method_node(method: JavaMethod) -> dict[str, Any]:
    return {
        "id": method.node_id,
        "type": "Method",
        "name": method.name,
        "filePath": method.file_path,
        "startLine": method.start_line,
        "endLine": method.end_line,
        "source_type": "code",
        "extraction_method": "regex",
        "confidence": 0.78,
        "properties": {
            "qualifiedName": f"{method.class_name}.{method.name}",
        },
    }


def _edge(
    source_id: str,
    edge_type: str,
    target_id: str,
    file_path: str,
    start_line: int,
    end_line: int,
    excerpt: str,
) -> dict[str, Any]:
    identity = "|".join([source_id, edge_type, target_id])
    return {
        "id": f"JAVA-EXC-REL-{sha256(identity.encode('utf-8')).hexdigest()[:12]}",
        "source_id": source_id,
        "target_id": target_id,
        "type": edge_type,
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "excerpt": excerpt,
        "source_type": "code",
        "extraction_method": "regex",
        "confidence": 0.8,
    }


def _append_once(
    nodes: list[dict[str, Any]],
    seen_nodes: set[str],
    node: dict[str, Any],
) -> None:
    node_id = str(node["id"])
    if node_id in seen_nodes:
        return
    seen_nodes.add(node_id)
    nodes.append(node)


def _methods(text: str, relpath: str, class_name: str) -> list[JavaMethod]:
    methods: list[JavaMethod] = []
    lines = text.splitlines()
    for match in METHOD_RE.finditer(text):
        start_line = _line_number(text, match.start())
        end_line = _block_end_line(lines, start_line)
        methods.append(
            JavaMethod(
                class_name=class_name,
                name=match.group(1),
                file_path=relpath,
                start_line=start_line,
                end_line=end_line,
            )
        )
    return methods


def _block_end_line(lines: list[str], start_line: int) -> int:
    depth = 0
    seen_open = False
    for number in range(start_line, len(lines) + 1):
        line = lines[number - 1]
        depth += line.count("{")
        if "{" in line:
            seen_open = True
        depth -= line.count("}")
        if seen_open and depth <= 0:
            return number
    return start_line


def _method_at_line(methods: list[JavaMethod], line: int) -> JavaMethod | None:
    for method in methods:
        if method.start_line <= line <= method.end_line:
            return method
    return None


def _first_method_after(methods: list[JavaMethod], line: int) -> JavaMethod | None:
    for method in methods:
        if method.start_line > line:
            return method
    return None


def _class_name(text: str) -> str | None:
    match = CLASS_RE.search(text)
    if match is None:
        return None
    return match.group(1) or match.group(2)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_excerpt(text: str, line: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def _relpath(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()
