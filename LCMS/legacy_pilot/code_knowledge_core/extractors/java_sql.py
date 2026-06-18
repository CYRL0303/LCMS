import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


STATEMENT_TAGS = {"select", "insert", "update", "delete"}
TABLE_PATTERNS = {
    "select": [
        re.compile(r"\bFROM\s+([A-Za-z_][\w.]*)", re.IGNORECASE),
        re.compile(r"\bJOIN\s+([A-Za-z_][\w.]*)", re.IGNORECASE),
    ],
    "insert": [re.compile(r"\bINTO\s+([A-Za-z_][\w.]*)", re.IGNORECASE)],
    "update": [re.compile(r"\bUPDATE\s+([A-Za-z_][\w.]*)", re.IGNORECASE)],
    "delete": [re.compile(r"\bFROM\s+([A-Za-z_][\w.]*)", re.IGNORECASE)],
}


def extract_mybatis_sql_graph(
    repo_root: Path,
    *,
    repo_id: str,
    graph_id: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    for xml_path in repo_root.rglob("*.xml"):
        try:
            tree = ElementTree.parse(xml_path)
        except ElementTree.ParseError:
            continue
        root = tree.getroot()
        if _local_name(root.tag) != "mapper":
            continue

        namespace = root.attrib.get("namespace", "")
        for statement in root:
            statement_tag = _local_name(statement.tag)
            if statement_tag not in STATEMENT_TAGS:
                continue
            statement_id = statement.attrib.get("id")
            if not statement_id:
                continue

            sql_text = " ".join("".join(statement.itertext()).split())
            if not sql_text:
                continue

            relpath = _relpath(repo_root, xml_path)
            start_line, end_line = _statement_lines(xml_path, statement_tag, statement_id)
            statement_node_id = f"MapperXml:{relpath}:{statement_id}"
            _append_once(
                nodes,
                seen_nodes,
                _sql_node(
                    statement_node_id,
                    statement_id,
                    relpath,
                    start_line,
                    end_line,
                    sql_text,
                ),
            )

            mapper_method_id = _mapper_method_id(namespace, statement_id)
            _append_once(
                nodes,
                seen_nodes,
                _mapper_method_node(mapper_method_id, namespace, statement_id),
            )
            relationships.append(
                _edge(
                    mapper_method_id,
                    "EXECUTES_SQL",
                    statement_node_id,
                    relpath,
                    start_line,
                    end_line,
                    sql_text,
                )
            )

            for table_name in _table_names(sql_text, statement_tag):
                table_node_id = f"Table:{table_name}"
                _append_once(
                    nodes,
                    seen_nodes,
                    _table_node(
                        table_node_id,
                        table_name,
                        relpath,
                        start_line,
                        end_line,
                        sql_text,
                    ),
                )
                relationships.append(
                    _edge(
                        statement_node_id,
                        _table_edge_type(statement_tag),
                        table_node_id,
                        relpath,
                        start_line,
                        end_line,
                        sql_text,
                    )
                )

    return {
        "repo_id": repo_id,
        "graph_id": graph_id,
        "nodes": nodes,
        "relationships": relationships,
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


def _sql_node(
    node_id: str,
    statement_id: str,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
    sql_text: str,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "SQL",
        "name": statement_id,
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "excerpt": sql_text,
        "source_type": "sql",
        "extraction_method": "regex",
        "confidence": 0.86,
        "properties": {"sql": sql_text},
    }


def _table_node(
    node_id: str,
    table_name: str,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
    sql_text: str,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "Table",
        "name": table_name,
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "excerpt": sql_text,
        "source_type": "sql",
        "extraction_method": "regex",
        "confidence": 0.8,
    }


def _mapper_method_node(
    node_id: str,
    namespace: str,
    statement_id: str,
) -> dict[str, Any]:
    class_name = namespace.rsplit(".", 1)[-1] if namespace else "DatasetMapper"
    return {
        "id": node_id,
        "type": "Method",
        "name": statement_id,
        "filePath": _mapper_java_path(namespace),
        "source_type": "code",
        "extraction_method": "regex",
        "confidence": 0.68,
        "properties": {
            "qualifiedName": f"{class_name}.{statement_id}",
        },
    }


def _edge(
    source_id: str,
    edge_type: str,
    target_id: str,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
    excerpt: str,
) -> dict[str, Any]:
    identity = "|".join([source_id, edge_type, target_id])
    return {
        "id": f"SQL-REL-{sha256(identity.encode('utf-8')).hexdigest()[:12]}",
        "source_id": source_id,
        "target_id": target_id,
        "type": edge_type,
        "filePath": file_path,
        "startLine": start_line,
        "endLine": end_line,
        "excerpt": excerpt,
        "source_type": "sql",
        "extraction_method": "regex",
        "confidence": 0.82,
    }


def _table_names(sql_text: str, statement_tag: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for pattern in TABLE_PATTERNS.get(statement_tag, []):
        for match in pattern.finditer(sql_text):
            table_name = match.group(1).rstrip(",;")
            if table_name not in seen:
                seen.add(table_name)
                names.append(table_name)
    return names


def _table_edge_type(statement_tag: str) -> str:
    if statement_tag == "select":
        return "READS_TABLE"
    return "WRITES_TABLE"


def _mapper_method_id(namespace: str, statement_id: str) -> str:
    class_name = namespace.rsplit(".", 1)[-1] if namespace else "DatasetMapper"
    return f"Method:{_mapper_java_path(namespace)}:{class_name}.{statement_id}#1"


def _mapper_java_path(namespace: str) -> str:
    class_name = namespace.rsplit(".", 1)[-1] if namespace else "DatasetMapper"
    package_path = namespace.rsplit(".", 1)[0].replace(".", "/") if "." in namespace else ""
    return (
        f"src/main/java/{package_path}/{class_name}.java"
        if package_path
        else f"src/main/java/com/legacy/{class_name}.java"
    )


def _statement_lines(
    xml_path: Path,
    statement_tag: str,
    statement_id: str,
) -> tuple[int | None, int | None]:
    lines = xml_path.read_text(encoding="utf-8").splitlines()
    start_line = None
    end_line = None
    open_pattern = re.compile(
        rf"<\s*{re.escape(statement_tag)}\b[^>]*\bid\s*=\s*['\"]{re.escape(statement_id)}['\"]",
        re.IGNORECASE,
    )
    close_pattern = re.compile(rf"</\s*{re.escape(statement_tag)}\s*>", re.IGNORECASE)
    for number, line in enumerate(lines, start=1):
        if start_line is None and open_pattern.search(line):
            start_line = number
        if start_line is not None and close_pattern.search(line):
            end_line = number
            break
    return start_line, end_line or start_line


def _relpath(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
