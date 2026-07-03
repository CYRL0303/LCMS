import re

from pydantic import BaseModel, Field

from legacy_pilot.contracts.models import AlertEvent


JAVA_FRAME_RE = re.compile(
    r"(?P<class>[A-Za-z_$][\w$]*)\.(?P<method>[A-Za-z_$][\w$]*)"
    r"\((?P<file>[^():]+\.java):(?P<line>\d+)\)"
)
JAVA_SYMBOL_RE = re.compile(
    r"\b(?P<class>[A-Z][A-Za-z0-9_$]*)\.(?P<method>[A-Za-z_$][\w$]*)\b"
)
JAVA_CLASS_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9_$]*(?:Controller|Service|Repository|Mapper|DAO|Dao|"
    r"Client|Handler|Manager|Processor|Exception|Error|Info|Entity|Model|DTO|Dto)\b"
)
CAMEL_TOKEN_RE = re.compile(r"\b[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b")
PASCAL_PART_RE = re.compile(r"[A-Z][a-z0-9]*")
ENDPOINT_RE = re.compile(r"(?P<endpoint>/api/[A-Za-z0-9_./{}-]+)")
JAVA_ERROR_TYPE_RE = re.compile(
    r"\b(?:[a-z_][\w$]*\.)+(?P<error>[A-Z][A-Za-z0-9_$]*(?:Exception|Error))\b"
)
SLOW_QUERY_RE = re.compile(r"\bslow\s+query\b", re.IGNORECASE)
SQL_TABLE_RE = re.compile(
    r"\b(?:from|join|update|into)\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
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


class IncidentSignals(BaseModel):
    error_type: str
    suspected_location: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    endpoint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)


def parse_alert_event(alert: AlertEvent) -> IncidentSignals:
    text = "\n".join(
        part
        for part in [
            alert.raw_log,
            alert.stack_trace or "",
            alert.error_description or "",
        ]
        if part
    )
    error_type = _detect_error_type(text)
    frame = JAVA_FRAME_RE.search(text)
    endpoint = _endpoint_match(text)
    table = _first_match(SQL_TABLE_RE, text, "table")
    suspected_location = None
    file_path = None
    line_number = None
    if frame:
        suspected_location = f"{frame.group('class')}.{frame.group('method')}"
        file_path = frame.group("file")
        line_number = int(frame.group("line"))
    else:
        symbol = JAVA_SYMBOL_RE.search(text)
        if symbol:
            suspected_location = f"{symbol.group('class')}.{symbol.group('method')}"
    keyword_candidates = [table, *_java_code_terms(text)]
    keywords = _dedupe([value for value in keyword_candidates if value])
    query_terms = _dedupe(
        [
            error_type,
            suspected_location,
            endpoint,
            *keywords,
        ]
    )
    return IncidentSignals(
        error_type=error_type,
        suspected_location=suspected_location,
        file_path=file_path,
        line_number=line_number,
        endpoint=endpoint,
        keywords=keywords,
        query_terms=query_terms,
    )


def _detect_error_type(text: str) -> str:
    if "NullPointerException" in text:
        return "NullPointerException"
    java_error = JAVA_ERROR_TYPE_RE.search(text)
    if java_error:
        return java_error.group("error")
    if SLOW_QUERY_RE.search(text):
        return "SlowQuery"
    return "UnknownError"


def _endpoint_match(text: str) -> str | None:
    endpoint = _first_match(ENDPOINT_RE, text, "endpoint")
    if endpoint is None:
        return None
    endpoint = endpoint.rstrip(".,;:!?)\"]}'")
    return _normalize_endpoint(endpoint)


def _normalize_endpoint(endpoint: str) -> str:
    parts = endpoint.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "api":
        last = parts[-1]
        previous = parts[-2]
        if _looks_like_path_value(last, previous):
            parts = parts[:-1]
    return "/" + "/".join(parts)


def _looks_like_path_value(value: str, previous: str) -> bool:
    if value.startswith("{") and value.endswith("}"):
        return False
    if value[:1].isupper() or value[:1].isdigit():
        return True
    return bool(CAMEL_TOKEN_RE.fullmatch(previous))


def _java_code_terms(text: str) -> list[str]:
    class_terms = [match.group(0) for match in JAVA_CLASS_RE.finditer(text)]
    symbol_terms = [
        f"{match.group('class')}.{match.group('method')}"
        for match in JAVA_SYMBOL_RE.finditer(text)
    ]
    method_terms = [match.group("method") for match in JAVA_SYMBOL_RE.finditer(text)]
    domain_terms = _java_domain_terms(class_terms)
    camel_terms = [match.group(0) for match in CAMEL_TOKEN_RE.finditer(text)]
    return _dedupe([*class_terms, *symbol_terms, *method_terms, *domain_terms, *camel_terms])


def _java_domain_terms(class_terms: list[str]) -> list[str]:
    domains: list[str] = []
    for term in class_terms:
        for suffix in JAVA_ROLE_SUFFIXES:
            if term.endswith(suffix) and len(term) > len(suffix):
                domain = term[: -len(suffix)]
                domains.append(domain)
                domains.extend(_pascal_domain_terms(domain))
                break
    return domains


def _pascal_domain_terms(value: str) -> list[str]:
    parts = PASCAL_PART_RE.findall(value)
    if len(parts) <= 1:
        return []
    return [parts[0]]


def _first_match(pattern: re.Pattern[str], text: str, group_name: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(group_name)


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
