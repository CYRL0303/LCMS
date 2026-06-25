import re

from pydantic import BaseModel, Field

from legacy_pilot.contracts.models import AlertEvent


JAVA_FRAME_RE = re.compile(
    r"(?P<class>[A-Za-z_$][\w$]*)\.(?P<method>[A-Za-z_$][\w$]*)"
    r"\((?P<file>[^():]+\.java):(?P<line>\d+)\)"
)
ENDPOINT_RE = re.compile(r"(?P<endpoint>/api/[A-Za-z0-9_./{}-]+)")
SQL_TABLE_RE = re.compile(
    r"\b(?:from|join|update|into)\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
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
    endpoint = _first_match(ENDPOINT_RE, text, "endpoint")
    table = _first_match(SQL_TABLE_RE, text, "table")
    suspected_location = None
    file_path = None
    line_number = None
    if frame:
        suspected_location = f"{frame.group('class')}.{frame.group('method')}"
        file_path = frame.group("file")
        line_number = int(frame.group("line"))
    keywords = _dedupe([value for value in [table] if value])
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
    if "Slow query" in text or "slow query" in text:
        return "SlowQuery"
    return "UnknownError"


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
