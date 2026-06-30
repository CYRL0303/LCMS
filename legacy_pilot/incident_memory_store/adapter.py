import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from legacy_pilot.contracts.models import IncidentMatch, IncidentQuery, IncidentRecord


INCIDENT_MEMORY_BACKEND_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"
INCIDENT_MEMORY_DSN_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_DSN"
INCIDENT_MEMORY_TABLE_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_TABLE"
DEFAULT_INCIDENT_MEMORY_BACKEND = "postgresql"
DEFAULT_INCIDENT_MEMORY_TABLE = "legacy_pilot_incident_records"
ALLOWED_INCIDENT_MEMORY_BACKENDS = ("postgresql",)
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class IncidentMemoryStoreError(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}


class IncidentMemoryStoreAdapter(ABC):
    @abstractmethod
    def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        ...

    @abstractmethod
    def load_incident(self, incident_id: str) -> IncidentRecord | None:
        ...

    @abstractmethod
    def find_similar_incidents(
        self,
        query: IncidentQuery,
        *,
        limit: int = 5,
    ) -> list[IncidentMatch]:
        ...


class PostgresIncidentMemoryStoreAdapter(IncidentMemoryStoreAdapter):
    def __init__(
        self,
        *,
        dsn: str,
        table_name: str = DEFAULT_INCIDENT_MEMORY_TABLE,
        connect: Callable[[str], Any] | None = None,
    ):
        self.dsn = dsn
        self.table_name = _safe_sql_identifier(table_name)
        self._connect = connect or _psycopg_connect

    def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._upsert_sql(),
                        (
                            record.incident_id,
                            record.repo_id,
                            record.dedup_key,
                            _json_payload(record.model_dump(mode="json")),
                            record.created_at,
                            record.updated_at,
                        ),
                    )
        except Exception as exc:
            raise IncidentMemoryStoreError(
                "PostgreSQL incident memory store failed while saving incident.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        return record

    def load_incident(self, incident_id: str) -> IncidentRecord | None:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(self._select_sql(), (incident_id,))
                    row = cursor.fetchone()
        except Exception as exc:
            raise IncidentMemoryStoreError(
                "PostgreSQL incident memory store failed while loading incident.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return IncidentRecord.model_validate(dict(payload))

    def find_similar_incidents(
        self,
        query: IncidentQuery,
        *,
        limit: int = 5,
    ) -> list[IncidentMatch]:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._search_sql(),
                        (query.repo_id, _bounded_limit(limit)),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            raise IncidentMemoryStoreError(
                "PostgreSQL incident memory store failed while searching incidents.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        records = [
            _record_from_payload(row[0])
            for row in rows
            if row and row[0] is not None
        ]
        return _rank_similar_records(query=query, records=records, limit=limit)

    def _create_table_sql(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            incident_id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL,
            dedup_key TEXT NOT NULL,
            record_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS {self.table_name}_repo_id_idx
            ON {self.table_name} (repo_id);
        CREATE INDEX IF NOT EXISTS {self.table_name}_dedup_key_idx
            ON {self.table_name} (dedup_key)
        """

    def _upsert_sql(self) -> str:
        return f"""
        INSERT INTO {self.table_name} (
            incident_id,
            repo_id,
            dedup_key,
            record_json,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (incident_id) DO UPDATE SET
            repo_id = EXCLUDED.repo_id,
            dedup_key = EXCLUDED.dedup_key,
            record_json = EXCLUDED.record_json,
            updated_at = EXCLUDED.updated_at
        """

    def _select_sql(self) -> str:
        return f"""
        SELECT record_json
        FROM {self.table_name}
        WHERE incident_id = %s
        """

    def _search_sql(self) -> str:
        return f"""
        SELECT record_json
        FROM {self.table_name}
        WHERE repo_id = %s
        ORDER BY updated_at DESC
        LIMIT %s
        """


def create_incident_memory_store_adapter(
    *,
    backend: str | None = None,
    dsn: str | None = None,
    table_name: str | None = None,
    connect: Callable[[str], Any] | None = None,
) -> IncidentMemoryStoreAdapter:
    selected_backend = (
        backend
        or os.getenv(INCIDENT_MEMORY_BACKEND_ENV)
        or DEFAULT_INCIDENT_MEMORY_BACKEND
    )
    normalized = selected_backend.strip().lower()
    if normalized == "postgresql":
        selected_dsn = dsn or os.getenv(INCIDENT_MEMORY_DSN_ENV)
        if not selected_dsn:
            raise IncidentMemoryStoreError(
                "PostgreSQL incident memory store requires "
                "LEGACY_PILOT_INCIDENT_MEMORY_DSN."
            )
        return PostgresIncidentMemoryStoreAdapter(
            dsn=selected_dsn,
            table_name=(
                table_name
                or os.getenv(INCIDENT_MEMORY_TABLE_ENV)
                or DEFAULT_INCIDENT_MEMORY_TABLE
            ),
            connect=connect,
        )
    allowed = ", ".join(ALLOWED_INCIDENT_MEMORY_BACKENDS)
    raise IncidentMemoryStoreError(
        f"Unsupported incident memory backend: {selected_backend}. "
        f"Allowed values: {allowed}.",
        diagnostics={"backend": selected_backend},
    )


def _json_payload(payload: dict[str, Any]) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return json.dumps(payload, ensure_ascii=False, default=str)
    return Jsonb(payload)


def _record_from_payload(payload: Any) -> IncidentRecord:
    if isinstance(payload, str):
        payload = json.loads(payload)
    return IncidentRecord.model_validate(dict(payload))


def _rank_similar_records(
    *,
    query: IncidentQuery,
    records: list[IncidentRecord],
    limit: int,
) -> list[IncidentMatch]:
    scored: list[tuple[float, IncidentRecord]] = []
    for record in records:
        similarity = _similarity(query, record)
        if similarity <= 0:
            continue
        scored.append((similarity, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        _incident_match(record=record, similarity=similarity)
        for similarity, record in scored[: _bounded_limit(limit)]
    ]


def _similarity(query: IncidentQuery, record: IncidentRecord) -> float:
    if record.repo_id != query.repo_id or not record.confirmed_by_user:
        return 0.0
    searchable = _searchable_record_text(record)
    score = 0.0
    if query.error_type and query.error_type.lower() == record.error_type.lower():
        score += 0.45
    if query.suspected_location and query.suspected_location.lower() in searchable:
        score += 0.3
    terms = _unique_terms(
        [
            query.error_type,
            query.suspected_location,
            *query.keywords,
            *query.query_terms,
        ]
    )
    if terms:
        matched = sum(1 for term in terms if term.lower() in searchable)
        score += 0.25 * (matched / len(terms))
    return min(score, 0.99)


def _incident_match(
    *,
    record: IncidentRecord,
    similarity: float,
) -> IncidentMatch:
    return IncidentMatch(
        incident_id=record.incident_id,
        similarity=round(similarity, 4),
        previous_root_cause=record.root_cause,
        previous_fix=record.fix,
        related_files=record.related_files,
        evidence_refs=record.evidence_refs,
        confirmed_by_user=record.confirmed_by_user,
    )


def _searchable_record_text(record: IncidentRecord) -> str:
    values = [
        record.repo_id,
        record.module,
        record.error_type,
        record.symptom,
        record.root_cause,
        record.fix,
        record.dedup_key,
        *record.related_files,
        *record.related_nodes,
    ]
    return " ".join(value for value in values if value).lower()


def _unique_terms(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _bounded_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 5
    return min(max(parsed, 1), 50)


def _psycopg_connect(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def _safe_sql_identifier(identifier: str) -> str:
    if not _SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise IncidentMemoryStoreError(
            "PostgreSQL incident memory store table name must be a safe SQL "
            "identifier matching [A-Za-z_][A-Za-z0-9_]{0,62}.",
            diagnostics={"table_name": identifier},
        )
    return identifier
