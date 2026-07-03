from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation
from legacy_pilot.contracts.models import AlertEvent


MAX_WEBHOOK_TEXT_CHARS = 120_000


def normalize_generic_webhook_payload(
    payload: Mapping[str, Any],
    *,
    repo_id: str,
    graph_id: str | None,
    contract_version: str,
    now: datetime,
) -> AlertEvent:
    raw_log = _first_text(payload, "raw_log", "log", "message", "text", "body", "error")
    stack_trace = _first_text(payload, "stack_trace", "stack", "trace", "stacktrace")
    error_description = _first_text(
        payload,
        "error_description",
        "description",
        "title",
        "summary",
        "alertname",
    )
    if not raw_log:
        raw_log = error_description or stack_trace
    if not raw_log:
        raise ContractViolation(
            ContractError(
                trace_id=None,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=(
                    "Webhook payload must contain raw_log, log, message, text, body, "
                    "error, title, description, stack, or stack_trace."
                ),
                source_module="alert_intake",
                recoverable=True,
                missing_fields=["raw_log"],
            )
        )

    raw_log = raw_log[:MAX_WEBHOOK_TEXT_CHARS]
    stack_trace = stack_trace[:MAX_WEBHOOK_TEXT_CHARS] if stack_trace else None
    error_description = (
        error_description[:MAX_WEBHOOK_TEXT_CHARS] if error_description else None
    )
    alert_id = _first_text(payload, "alert_id", "id", "event_id", "incident_id")
    if not alert_id:
        digest = sha256(
            f"{repo_id}:{graph_id or ''}:{raw_log}".encode("utf-8")
        ).hexdigest()[:12]
        alert_id = f"webhook-{digest}"
    source = _first_text(payload, "source", "provider", "integration") or "generic-webhook"

    return AlertEvent(
        alert_id=alert_id,
        repo_id=repo_id,
        graph_id=graph_id,
        raw_log=raw_log,
        stack_trace=stack_trace,
        error_description=error_description,
        occurred_at=_parse_datetime(
            _first_text(payload, "occurred_at", "timestamp", "time", "startsAt"),
            now,
        ),
        source=source,
        contract_version=contract_version,
    )


def _first_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _lookup(payload, key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
            continue
        if isinstance(value, (int, float, bool)):
            return str(value)
    return None


def _lookup(payload: Mapping[str, Any], key: str) -> Any:
    if key in payload:
        return payload[key]
    for value in payload.values():
        if isinstance(value, Mapping) and key in value:
            return value[key]
    return None


def _parse_datetime(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return _with_timezone(fallback)
    normalized = value.replace("Z", "+00:00")
    try:
        return _with_timezone(datetime.fromisoformat(normalized))
    except ValueError:
        return _with_timezone(fallback)


def _with_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
