import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from legacy_pilot.contracts.models import IncidentRecord


INCIDENT_MEMORY_BACKEND_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"
INCIDENT_MEMORY_DSN_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_DSN"
INCIDENT_MEMORY_TABLE_ENV = "LEGACY_PILOT_INCIDENT_MEMORY_TABLE"
DEFAULT_INCIDENT_MEMORY_BACKEND = "postgresql"
DEFAULT_INCIDENT_MEMORY_TABLE = "legacy_pilot_incident_records"
ALLOWED_INCIDENT_MEMORY_BACKENDS = ("postgresql", "memory")
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


class InMemoryIncidentMemoryStoreAdapter(IncidentMemoryStoreAdapter):
    def __init__(self):
        self._records: dict[str, IncidentRecord] = {}

    def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        self._records[record.incident_id] = record
        return record

    def load_incident(self, incident_id: str) -> IncidentRecord | None:
        return self._records.get(incident_id)


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

    def _create_table_sql(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            incident_id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL,
            dedup_key TEXT NOT NULL,
            record_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
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
    if normalized == "memory":
        return InMemoryIncidentMemoryStoreAdapter()
    if normalized in {"postgres", "postgresql"}:
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
