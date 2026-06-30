from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeCredentials:
    qwen_api_key: str | None = None
    github_token: str | None = None
    gitlab_token: str | None = None


_CURRENT_CREDENTIALS: ContextVar[RuntimeCredentials] = ContextVar(
    "legacy_pilot_runtime_credentials",
    default=RuntimeCredentials(),
)


def current_runtime_credentials() -> RuntimeCredentials:
    return _CURRENT_CREDENTIALS.get()


@contextmanager
def use_runtime_credentials(credentials: RuntimeCredentials) -> Iterator[None]:
    token = _CURRENT_CREDENTIALS.set(credentials)
    try:
        yield
    finally:
        _CURRENT_CREDENTIALS.reset(token)


def clean_secret(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
