import json
from abc import ABC, abstractmethod
from hashlib import sha256
from typing import Any


class GraphStoreError(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}


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


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
