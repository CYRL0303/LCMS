import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


DEFAULT_GRAPH_STORE_TABLE = "legacy_pilot_graph_payloads"
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class GraphStoreError(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class GraphStoreRecord:
    repo_id: str
    graph_id: str
    parser_version: str | None
    semantic_enrichment_version: str | None
    created_at: datetime
    updated_at: datetime
    node_count: int
    edge_count: int


class GraphStore(ABC):
    @abstractmethod
    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        ...

    @abstractmethod
    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def list_payloads(self) -> list[GraphStoreRecord]:
        ...

    @abstractmethod
    def delete_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> bool:
        ...


class DisabledGraphStore(GraphStore):
    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        return None

    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        return None

    def list_payloads(self) -> list[GraphStoreRecord]:
        return []

    def delete_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> bool:
        return False


class PostgresGraphStore(GraphStore):
    def __init__(
        self,
        *,
        dsn: str,
        table_name: str = DEFAULT_GRAPH_STORE_TABLE,
        connect: Callable[[str], Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.dsn = dsn
        self.table_name = _safe_sql_identifier(table_name)
        self._connect = connect or _psycopg_connect
        self._now = now or (lambda: datetime.now(UTC))

    def save_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
        payload: dict[str, Any],
    ) -> None:
        parser_version = _text_or_none(payload.get("parser_version"))
        semantic_version = _text_or_none(payload.get("semantic_enrichment_version"))
        now = self._now()
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._upsert_sql(),
                        (
                            repo_id,
                            graph_id,
                            _json_payload(payload),
                            payload_hash(payload),
                            parser_version,
                            semantic_version,
                            now,
                            now,
                        ),
                    )
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while saving graph payload.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc

    def load_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> dict[str, Any] | None:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(
                        self._select_sql(),
                        (repo_id, graph_id),
                    )
                    row = cursor.fetchone()
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while loading graph payload.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload)

    def list_payloads(self) -> list[GraphStoreRecord]:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(self._list_sql())
                    rows = cursor.fetchall()
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while listing graph payloads.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        return [_record_from_row(row) for row in rows]

    def delete_payload(
        self,
        *,
        repo_id: str,
        graph_id: str,
    ) -> bool:
        try:
            with self._connect(self.dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self._create_table_sql())
                    cursor.execute(self._delete_sql(), (repo_id, graph_id))
                    deleted = cursor.rowcount > 0
        except Exception as exc:
            raise GraphStoreError(
                "PostgreSQL graph store failed while deleting graph payload.",
                diagnostics={"error_type": exc.__class__.__name__},
            ) from exc
        return deleted

    def _create_table_sql(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            repo_id TEXT NOT NULL,
            graph_id TEXT NOT NULL,
            payload_json JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            parser_version TEXT NULL,
            semantic_enrichment_version TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (repo_id, graph_id)
        )
        """

    def _upsert_sql(self) -> str:
        return f"""
        INSERT INTO {self.table_name} (
            repo_id,
            graph_id,
            payload_json,
            payload_hash,
            parser_version,
            semantic_enrichment_version,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (repo_id, graph_id) DO UPDATE SET
            payload_json = EXCLUDED.payload_json,
            payload_hash = EXCLUDED.payload_hash,
            parser_version = EXCLUDED.parser_version,
            semantic_enrichment_version = EXCLUDED.semantic_enrichment_version,
            updated_at = EXCLUDED.updated_at
        """

    def _select_sql(self) -> str:
        return f"""
        SELECT payload_json
        FROM {self.table_name}
        WHERE repo_id = %s AND graph_id = %s
        """

    def _list_sql(self) -> str:
        return f"""
        SELECT repo_id, graph_id, parser_version, semantic_enrichment_version,
               created_at, updated_at, payload_json
        FROM {self.table_name}
        ORDER BY updated_at DESC
        """

    def _delete_sql(self) -> str:
        return f"""
        DELETE FROM {self.table_name}
        WHERE repo_id = %s AND graph_id = %s
        """


def create_graph_store(
    *,
    backend: str | None = None,
    dsn: str | None = None,
    table_name: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> GraphStore:
    selected_backend = (
        backend
        or os.getenv("LEGACY_PILOT_GRAPH_STORE_BACKEND")
        or ("postgresql" if os.getenv("LEGACY_PILOT_GRAPH_STORE_DSN") else "disabled")
    )
    normalized = selected_backend.strip().lower()
    if normalized in {"disabled", "none", "off"}:
        return DisabledGraphStore()
    if normalized in {"postgres", "postgresql"}:
        selected_dsn = dsn or os.getenv("LEGACY_PILOT_GRAPH_STORE_DSN")
        if not selected_dsn:
            raise GraphStoreError(
                "PostgreSQL graph store requires LEGACY_PILOT_GRAPH_STORE_DSN."
            )
        return PostgresGraphStore(
            dsn=selected_dsn,
            table_name=(
                table_name
                or os.getenv("LEGACY_PILOT_GRAPH_STORE_TABLE")
                or DEFAULT_GRAPH_STORE_TABLE
            ),
            now=now,
        )
    raise GraphStoreError(
        f"Unsupported graph store backend: {selected_backend}",
        diagnostics={"backend": selected_backend},
    )


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _record_from_row(row: Any) -> GraphStoreRecord:
    payload = row[6]
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = dict(payload)
    return GraphStoreRecord(
        repo_id=str(row[0]),
        graph_id=str(row[1]),
        parser_version=_text_or_none(row[2]),
        semantic_enrichment_version=_text_or_none(row[3]),
        created_at=row[4],
        updated_at=row[5],
        node_count=_payload_count(payload, "nodes", "vertices"),
        edge_count=_payload_count(payload, "relationships", "edges"),
    )


def _payload_count(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


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
        raise GraphStoreError(
            "PostgreSQL graph store table name must be a safe SQL identifier "
            "matching [A-Za-z_][A-Za-z0-9_]{0,62}.",
            diagnostics={"table_name": identifier},
        )
    return identifier


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
