import os
import re
import socket
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from json import dumps, loads
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    RCAReport,
    ReviewedRCAReport,
)
from legacy_pilot.contracts.runtime_credentials import current_runtime_credentials
from legacy_pilot.rca_reasoning_engine.errors import RCAGenerationError
from legacy_pilot.rca_reasoning_engine.evidence import (
    assert_bundle_has_evidence,
    assert_report_is_evidence_backed,
    evidence_by_id,
)


RCA_BACKEND_ENV = "LEGACY_PILOT_RCA_BACKEND"
RCA_BASE_URL_ENV = "LEGACY_PILOT_RCA_BASE_URL"
RCA_MODEL_ENV = "LEGACY_PILOT_RCA_MODEL"
RCA_CONFIDENCE_CAP_ENV = "LEGACY_PILOT_RCA_CONFIDENCE_CAP"
RCA_REPAIR_ATTEMPTS_ENV = "LEGACY_PILOT_RCA_REPAIR_ATTEMPTS"
RCA_TIMEOUT_SECONDS_ENV = "LEGACY_PILOT_RCA_TIMEOUT_SECONDS"
RCA_TRANSPORT_RETRIES_ENV = "LEGACY_PILOT_RCA_TRANSPORT_RETRIES"
RCA_RETRY_BACKOFF_SECONDS_ENV = "LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS"
DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_RCA_BACKEND = "qwen_api"
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_RCA_CONFIDENCE_CAP = 0.75
DEFAULT_QWEN_REPAIR_ATTEMPTS = 2
MAX_QWEN_REPAIR_ATTEMPTS = 3
DEFAULT_QWEN_TIMEOUT_SECONDS = 120.0
MIN_QWEN_TIMEOUT_SECONDS = 1.0
MAX_QWEN_TIMEOUT_SECONDS = 600.0
DEFAULT_QWEN_TRANSPORT_RETRIES = 1
MAX_QWEN_TRANSPORT_RETRIES = 3
DEFAULT_QWEN_RETRY_BACKOFF_SECONDS = 1.0
MAX_QWEN_RETRY_BACKOFF_SECONDS = 30.0
RETRYABLE_HTTP_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
LOW_RECALL_CONFIDENCE_CAP = 0.5
LOW_RECALL_MIN_EVIDENCE_REFS = 2
EVIDENCE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_$]*")
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
COMMON_EVIDENCE_TOKENS = {
    "and",
    "before",
    "calls",
    "code",
    "coverage",
    "evidence",
    "flow",
    "from",
    "guard",
    "into",
    "java",
    "line",
    "method",
    "near",
    "need",
    "needs",
    "null",
    "path",
    "regression",
    "source",
    "the",
    "uses",
    "with",
    "without",
}


class RCAReasoningEngineAdapter(ABC):
    @abstractmethod
    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        ...

    @abstractmethod
    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        ...


class _QwenRetryableTransportError(RCAGenerationError):
    pass


@dataclass(frozen=True)
class QwenApiRCAReasoningEngineAdapter(RCAReasoningEngineAdapter):
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_QWEN_BASE_URL
    model: str = DEFAULT_QWEN_MODEL
    confidence_cap: float = DEFAULT_RCA_CONFIDENCE_CAP
    http_post: Any | None = None
    max_repair_attempts: int = DEFAULT_QWEN_REPAIR_ATTEMPTS
    request_timeout_seconds: float = DEFAULT_QWEN_TIMEOUT_SECONDS
    max_transport_retries: int = DEFAULT_QWEN_TRANSPORT_RETRIES
    transport_retry_backoff_seconds: float = DEFAULT_QWEN_RETRY_BACKOFF_SECONDS
    transport_retry_sleep: Callable[[float], None] | None = field(
        default=None,
        repr=False,
    )
    metadata_recorder: Callable[[dict[str, Any]], None] | None = field(
        default=None,
        repr=False,
    )
    backend_name: str = "qwen_api"

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        evidence = assert_bundle_has_evidence(bundle)
        api_key = (
            self.api_key
            or current_runtime_credentials().qwen_api_key
            or os.getenv(DASHSCOPE_API_KEY_ENV)
        )
        if not api_key:
            raise RCAGenerationError(
                "DASHSCOPE_API_KEY is required for qwen_api RCA backend.",
                recoverable=True,
            )
        messages = [
            {"role": "system", "content": _qwen_system_prompt()},
            {"role": "user", "content": _qwen_rca_prompt(bundle, evidence)},
        ]
        repair_limit = _bounded_repair_attempts(self.max_repair_attempts)
        last_error: RCAGenerationError | None = None
        repair_attempts = 0
        for attempt in range(repair_limit + 1):
            attempts = attempt + 1
            response = self._post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                },
            )
            content = _chat_completion_content(response)
            try:
                payload = _loads_json_object(content)
                report = _report_from_qwen_payload(
                    bundle=bundle,
                    payload=payload,
                    evidence_lookup=evidence_by_id(bundle),
                    confidence_cap=self.confidence_cap,
                )
                self._record_metadata(
                    attempts=attempts,
                    repair_attempts=repair_attempts,
                    last_error=(
                        _error_summary(last_error.message)
                        if last_error is not None
                        else None
                    ),
                )
                return report
            except RCAGenerationError as exc:
                last_error = exc
            except (TypeError, ValueError, ValidationError) as exc:
                last_error = RCAGenerationError(
                    f"Qwen RCA backend returned invalid schema: {exc}"
                )
            if last_error is not None:
                if attempt >= repair_limit:
                    last_error_summary = _error_summary(last_error.message)
                    self._record_metadata(
                        attempts=attempts,
                        repair_attempts=repair_attempts,
                        last_error=last_error_summary,
                    )
                    raise RCAGenerationError(
                        "Qwen RCA backend failed after "
                        f"attempts={attempts}, "
                        f"repair_attempts={repair_attempts}; "
                        f"last_error={last_error_summary}",
                        recoverable=last_error.recoverable,
                    ) from last_error
                repair_attempts += 1
                messages = [
                    {"role": "system", "content": _qwen_system_prompt()},
                    {
                        "role": "user",
                        "content": _qwen_repair_prompt(
                            bundle=bundle,
                            evidence=evidence,
                            previous_content=content,
                            error_message=last_error.message,
                        ),
                    },
                ]
                continue
        if last_error is not None:
            raise last_error
        raise RCAGenerationError("Qwen RCA backend failed to generate a report.")

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        assert_report_is_evidence_backed(report)
        return ReviewedRCAReport(
            report_id=report.report_id,
            trace_id=report.trace_id,
            repo_id=report.repo_id,
            graph_id=report.graph_id,
            approved_findings=[
                report.selected_root_cause,
                *report.suggested_fix,
                report.migration_impact,
            ],
            rejected_findings=[],
            missing_evidence=list(report.open_questions),
            risk_notes=[],
            final_confidence=report.confidence,
        )

    def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        retry_limit = _bounded_transport_retries(self.max_transport_retries)
        last_error: RCAGenerationError | None = None
        for attempt in range(retry_limit + 1):
            try:
                if self.http_post is not None:
                    return self.http_post(url, headers, body)
                return _http_post_json(
                    url,
                    headers=headers,
                    body=body,
                    timeout_seconds=self.request_timeout_seconds,
                )
            except _QwenRetryableTransportError as exc:
                last_error = exc
            except (TimeoutError, socket.timeout, URLError, OSError) as exc:
                last_error = _transport_error_from_exception(
                    exc,
                    timeout_seconds=self.request_timeout_seconds,
                )
            if attempt < retry_limit:
                self._sleep_before_transport_retry(attempt)
                continue
            break
        if last_error is not None:
            raise RCAGenerationError(
                "Qwen RCA API request failed after "
                f"attempts={retry_limit + 1}; "
                f"last_error={_error_summary(last_error.message)}",
                recoverable=last_error.recoverable,
            ) from last_error
        raise RCAGenerationError("Qwen RCA API request failed.")

    def _sleep_before_transport_retry(self, attempt: int) -> None:
        base_delay = _bounded_backoff_seconds(self.transport_retry_backoff_seconds)
        if base_delay <= 0:
            return
        delay = min(base_delay * (2**attempt), MAX_QWEN_RETRY_BACKOFF_SECONDS)
        (self.transport_retry_sleep or sleep)(delay)

    def _record_metadata(
        self,
        *,
        attempts: int,
        repair_attempts: int,
        last_error: str | None,
    ) -> None:
        if self.metadata_recorder is None:
            return
        self.metadata_recorder(
            {
                "attempts": attempts,
                "repair_attempts": repair_attempts,
                "last_error": last_error,
            }
        )


class UnsupportedRCAReasoningEngineAdapter(RCAReasoningEngineAdapter):
    def __init__(self, backend: str):
        self._backend = backend

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        raise RCAGenerationError(
            f"Unsupported RCA Reasoning Engine backend: {self._backend}",
            recoverable=True,
        )

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        raise RCAGenerationError(
            f"Unsupported RCA Reasoning Engine backend: {self._backend}",
            recoverable=True,
        )


def create_rca_reasoning_engine_adapter(
    *,
    backend: str | None = None,
) -> RCAReasoningEngineAdapter:
    selected = (
        backend or os.getenv(RCA_BACKEND_ENV) or DEFAULT_RCA_BACKEND
    ).strip().lower()
    if selected == "qwen_api":
        return QwenApiRCAReasoningEngineAdapter(
            base_url=os.getenv(RCA_BASE_URL_ENV, DEFAULT_QWEN_BASE_URL),
            model=os.getenv(RCA_MODEL_ENV, DEFAULT_QWEN_MODEL),
            confidence_cap=_confidence_cap(),
            max_repair_attempts=_repair_attempts(),
            request_timeout_seconds=_timeout_seconds(),
            max_transport_retries=_transport_retries(),
            transport_retry_backoff_seconds=_retry_backoff_seconds(),
        )
    return UnsupportedRCAReasoningEngineAdapter(selected)


def _qwen_rca_prompt(bundle: EvidenceBundle, evidence: list[EvidenceRef]) -> str:
    quality = _evidence_quality(bundle, evidence)
    evidence_lines = [
        (
            f"- {ref.evidence_id}: source_type={ref.source_type}; "
            f"source_id={ref.source_id}; file={ref.file_path}; "
            f"lines={ref.start_line}-{ref.end_line}; excerpt={ref.excerpt}"
        )
        for ref in evidence
    ]
    return (
        f"trace_id: {bundle.trace_id}\n"
        f"repo_id: {bundle.repo_id}\n"
        f"alert_summary: {bundle.alert_summary}\n"
        f"error_type: {bundle.incident_query.error_type}\n"
        f"suspected_location: {bundle.incident_query.suspected_location}\n"
        f"graph_paths: {bundle.graph_paths}\n"
        f"missing_evidence: {bundle.missing_evidence}\n"
        f"evidence_quality: {quality.label}\n"
        f"evidence_quality_reasons: {quality.reasons}\n"
        "Evidence IDs:\n"
        + "\n".join(evidence_lines)
        + "\nReturn JSON with keys hypotheses, selected_root_cause, suggested_fix, "
        "migration_impact, migration_checklist, affected_path, open_questions, confidence. "
        "Each conclusion object must contain summary, evidence_ids, confidence. "
        + _quality_prompt_rules(quality)
    )


def _qwen_system_prompt() -> str:
    return (
        "You are LegacyPilot Structure3 RCA Reasoning Engine. "
        "Use only evidence IDs from the supplied EvidenceBundle. "
        "Return strict JSON and never invent evidence IDs."
    )


def _qwen_repair_prompt(
    *,
    bundle: EvidenceBundle,
    evidence: list[EvidenceRef],
    previous_content: str,
    error_message: str,
) -> str:
    return (
        _qwen_rca_prompt(bundle, evidence)
        + "\n\nThe previous response failed validation: "
        + error_message
        + "\nPrevious response:\n"
        + previous_content
        + "\nReturn only corrected JSON. "
        "hypotheses and suggested_fix must be arrays of objects. "
        "selected_root_cause and migration_impact must be objects. "
        "Every conclusion object must include summary, evidence_ids, and confidence. "
        "If evidence_ids were omitted or invented, choose the closest matching "
        "IDs from the supplied Evidence IDs list and do not invent new IDs."
    )


def _report_from_qwen_payload(
    *,
    bundle: EvidenceBundle,
    payload: dict[str, Any],
    evidence_lookup: dict[str, EvidenceRef],
    confidence_cap: float,
) -> RCAReport:
    evidence_candidates = list(evidence_lookup.values())
    hypotheses = [
        _item_from_qwen(raw, evidence_lookup, evidence_candidates, "hypotheses")
        for raw in payload.get("hypotheses", [])
    ]
    selected_root_cause = _item_from_qwen(
        payload.get("selected_root_cause"),
        evidence_lookup,
        evidence_candidates,
        "selected_root_cause",
    )
    suggested_fix = [
        _item_from_qwen(raw, evidence_lookup, evidence_candidates, "suggested_fix")
        for raw in payload.get("suggested_fix", [])
    ]
    migration_impact = _item_from_qwen(
        payload.get("migration_impact"),
        evidence_lookup,
        evidence_candidates,
        "migration_impact",
    )
    evidence_chain = _dedupe_evidence(
        [
            ref
            for item in [
                *hypotheses,
                selected_root_cause,
                *suggested_fix,
                migration_impact,
            ]
            for ref in item.evidence_refs
        ]
    )
    report = RCAReport(
        report_id=f"RCA-{bundle.trace_id.removeprefix('TRACE-')}",
        trace_id=bundle.trace_id,
        repo_id=bundle.repo_id,
        graph_id=bundle.incident_query.graph_id,
        contract_version=bundle.contract_version,
        hypotheses=hypotheses,
        selected_root_cause=selected_root_cause,
        evidence_chain=evidence_chain,
        affected_path=[str(value) for value in payload.get("affected_path", [])],
        suggested_fix=suggested_fix,
        migration_impact=migration_impact,
        migration_checklist=[
            str(value) for value in payload.get("migration_checklist", [])
        ],
        confidence=min(float(payload.get("confidence", confidence_cap)), confidence_cap),
        open_questions=[str(value) for value in payload.get("open_questions", [])],
    )
    assert_report_is_evidence_backed(report)
    _assert_report_respects_evidence_quality(bundle, evidence_candidates, report)
    return report


def _item_from_qwen(
    raw: Any,
    evidence_lookup: dict[str, EvidenceRef],
    evidence_candidates: list[EvidenceRef],
    field_name: str,
) -> EvidenceBackedItem:
    if not isinstance(raw, dict):
        raise RCAGenerationError(f"{field_name} must be an object.")
    evidence_ids = raw.get("evidence_ids")
    valid_ids: list[str] = []
    unknown: list[str] = []
    if isinstance(evidence_ids, list):
        for evidence_id in evidence_ids:
            key = str(evidence_id)
            if key in evidence_lookup:
                valid_ids.append(key)
            else:
                unknown.append(key)
    if not valid_ids:
        matched_refs = _match_evidence_refs_to_summary(raw, evidence_candidates)
        if matched_refs:
            valid_ids = [ref.evidence_id for ref in matched_refs]
        elif unknown:
            raise RCAGenerationError(
                f"{field_name} referenced unknown evidence_ids: "
                f"{', '.join(unknown)} and could not map summary to supplied evidence."
            )
        else:
            raise RCAGenerationError(
                f"{field_name} must include evidence_ids or match supplied evidence."
            )
    if unknown and valid_ids:
        matched_refs = _match_evidence_refs_to_summary(raw, evidence_candidates)
        if matched_refs:
            valid_ids = [ref.evidence_id for ref in matched_refs]
    refs = _dedupe_evidence([evidence_lookup[evidence_id] for evidence_id in valid_ids])
    if not refs:
        raise RCAGenerationError(
            f"{field_name} must include evidence_ids or match supplied evidence."
        )
    return EvidenceBackedItem(
        summary=str(raw.get("summary", "")).strip(),
        evidence_refs=refs,
        confidence=min(float(raw.get("confidence", 0.0)), 1.0),
    )


def _match_evidence_refs_to_summary(
    raw: dict[str, Any],
    evidence_candidates: list[EvidenceRef],
) -> list[EvidenceRef]:
    summary = str(raw.get("summary", "")).strip()
    query_tokens = _evidence_match_tokens(summary)
    if not query_tokens:
        return []
    scored = [
        (score, index, ref)
        for index, ref in enumerate(evidence_candidates)
        if (score := _evidence_match_score(query_tokens, ref)) > 0
    ]
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score = scored[0][0]
    return [ref for score, _, ref in scored if score == best_score][:3]


def _evidence_match_score(query_tokens: set[str], ref: EvidenceRef) -> int:
    evidence_tokens = _evidence_match_tokens(
        " ".join(
            str(value)
            for value in [
                ref.evidence_id,
                ref.source_type,
                ref.source_id,
                ref.file_path,
                ref.excerpt,
            ]
            if value is not None
        )
    )
    overlap = query_tokens & evidence_tokens
    if not overlap:
        return 0
    return len(overlap) + sum(2 for token in overlap if len(token) >= 6)


def _evidence_match_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in EVIDENCE_TOKEN_RE.findall(text):
        candidates = [raw_token, *CAMEL_BOUNDARY_RE.split(raw_token)]
        for candidate in candidates:
            token = candidate.lower().strip("_$")
            if len(token) <= 2 or token in COMMON_EVIDENCE_TOKENS:
                continue
            tokens.add(token)
    return tokens


@dataclass(frozen=True)
class EvidenceQuality:
    constrained: bool
    reasons: list[str]

    @property
    def label(self) -> str:
        return "constrained" if self.constrained else "sufficient"


def _evidence_quality(
    bundle: EvidenceBundle,
    evidence: list[EvidenceRef],
) -> EvidenceQuality:
    reasons: list[str] = []
    if bundle.missing_evidence:
        reasons.append("missing_evidence=" + ",".join(bundle.missing_evidence))
    if _has_graph_context(bundle) and len(evidence) < LOW_RECALL_MIN_EVIDENCE_REFS:
        reasons.append(f"low-recall evidence_refs={len(evidence)}")
    return EvidenceQuality(constrained=bool(reasons), reasons=reasons)


def _has_graph_context(bundle: EvidenceBundle) -> bool:
    return bool(bundle.matched_nodes or bundle.graph_paths)


def _quality_prompt_rules(quality: EvidenceQuality) -> str:
    if not quality.constrained:
        return ""
    return (
        "Evidence quality: constrained. For missing_evidence or low-recall evidence, "
        "you must not present a high-confidence root cause. "
        f"Set report confidence and selected_root_cause confidence <= {LOW_RECALL_CONFIDENCE_CAP}. "
        "Add open_questions naming missing evidence. "
        "Do not use missing evidence, absent files, or lack of evidence as proof of root cause."
    )


def _assert_report_respects_evidence_quality(
    bundle: EvidenceBundle,
    evidence: list[EvidenceRef],
    report: RCAReport,
) -> None:
    quality = _evidence_quality(bundle, evidence)
    if not quality.constrained:
        return
    if report.confidence > LOW_RECALL_CONFIDENCE_CAP:
        raise RCAGenerationError(
            "low-recall evidence requires report confidence <= "
            f"{LOW_RECALL_CONFIDENCE_CAP}."
        )
    if _confidence(report.selected_root_cause) > LOW_RECALL_CONFIDENCE_CAP:
        raise RCAGenerationError(
            "low-recall evidence requires selected_root_cause confidence <= "
            f"{LOW_RECALL_CONFIDENCE_CAP}."
        )
    if not report.open_questions:
        raise RCAGenerationError(
            "low-recall evidence requires open_questions naming missing evidence."
        )
    if _uses_missing_evidence_as_cause(report.selected_root_cause.summary):
        raise RCAGenerationError(
            "missing evidence cannot be used as proof of root cause."
        )


def _confidence(item: EvidenceBackedItem) -> float:
    return float(item.confidence if item.confidence is not None else 0.0)


def _uses_missing_evidence_as_cause(summary: str) -> bool:
    normalized = " ".join(summary.lower().split())
    markers = [
        "absence of evidence",
        "lack of evidence",
        "missing evidence",
        "no evidence",
        "not found in evidence",
    ]
    return any(marker in normalized for marker in markers)


def _chat_completion_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content).strip() if content is not None else ""


def _loads_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
    try:
        payload = loads(cleaned)
    except ValueError as exc:
        raise RCAGenerationError("Qwen RCA backend returned non-JSON content.") from exc
    if not isinstance(payload, dict):
        raise RCAGenerationError("Qwen RCA backend returned JSON that is not an object.")
    return payload


def _http_post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_seconds: float = DEFAULT_QWEN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    timeout = _bounded_timeout_seconds(timeout_seconds)
    request = Request(
        url,
        data=dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            try:
                return loads(response.read().decode("utf-8"))
            except ValueError as exc:
                raise RCAGenerationError(
                    "Qwen RCA API returned non-JSON response."
                ) from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"Qwen RCA API HTTP {exc.code}: {detail}"
        if exc.code in RETRYABLE_HTTP_STATUS_CODES:
            raise _QwenRetryableTransportError(message, recoverable=True) from exc
        raise RCAGenerationError(
            message,
            recoverable=exc.code not in {401, 403},
        ) from exc
    except URLError as exc:
        raise _transport_error_from_exception(
            exc,
            timeout_seconds=timeout,
        ) from exc
    except (TimeoutError, socket.timeout, OSError) as exc:
        raise _transport_error_from_exception(
            exc,
            timeout_seconds=timeout,
        ) from exc


def _transport_error_from_exception(
    exc: BaseException,
    *,
    timeout_seconds: float,
) -> _QwenRetryableTransportError:
    reason: object
    if isinstance(exc, URLError):
        reason = exc.reason
    else:
        reason = exc
    reason_text = " ".join(str(reason).split()) or exc.__class__.__name__
    if _is_timeout_exception(exc) or "timed out" in reason_text.lower():
        return _QwenRetryableTransportError(
            "Qwen RCA API request timed out after "
            f"{_format_seconds(timeout_seconds)}s: {reason_text}",
            recoverable=True,
        )
    return _QwenRetryableTransportError(
        f"Qwen RCA API request failed: {reason_text}",
        recoverable=True,
    )


def _is_timeout_exception(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, URLError):
        return isinstance(exc.reason, (TimeoutError, socket.timeout))
    return False


def _dedupe_evidence(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    result: list[EvidenceRef] = []
    seen: set[str] = set()
    for ref in refs:
        if ref.evidence_id in seen:
            continue
        seen.add(ref.evidence_id)
        result.append(ref)
    return result


def _confidence_cap() -> float:
    raw = os.getenv(RCA_CONFIDENCE_CAP_ENV)
    if raw is None:
        return DEFAULT_RCA_CONFIDENCE_CAP
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RCA_CONFIDENCE_CAP
    return min(max(value, 0.0), 1.0)


def _repair_attempts() -> int:
    return _bounded_repair_attempts(
        os.getenv(RCA_REPAIR_ATTEMPTS_ENV, str(DEFAULT_QWEN_REPAIR_ATTEMPTS))
    )


def _bounded_repair_attempts(value: int) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = DEFAULT_QWEN_REPAIR_ATTEMPTS
    return min(max(requested, 0), MAX_QWEN_REPAIR_ATTEMPTS)


def _timeout_seconds() -> float:
    return _bounded_timeout_seconds(
        os.getenv(RCA_TIMEOUT_SECONDS_ENV, str(DEFAULT_QWEN_TIMEOUT_SECONDS))
    )


def _bounded_timeout_seconds(value: float | str | None) -> float:
    return _bounded_float(
        value,
        default=DEFAULT_QWEN_TIMEOUT_SECONDS,
        minimum=MIN_QWEN_TIMEOUT_SECONDS,
        maximum=MAX_QWEN_TIMEOUT_SECONDS,
    )


def _transport_retries() -> int:
    return _bounded_transport_retries(
        os.getenv(RCA_TRANSPORT_RETRIES_ENV, str(DEFAULT_QWEN_TRANSPORT_RETRIES))
    )


def _bounded_transport_retries(value: int | str | None) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = DEFAULT_QWEN_TRANSPORT_RETRIES
    return min(max(requested, 0), MAX_QWEN_TRANSPORT_RETRIES)


def _retry_backoff_seconds() -> float:
    return _bounded_backoff_seconds(
        os.getenv(
            RCA_RETRY_BACKOFF_SECONDS_ENV,
            str(DEFAULT_QWEN_RETRY_BACKOFF_SECONDS),
        )
    )


def _bounded_backoff_seconds(value: float | str | None) -> float:
    return _bounded_float(
        value,
        default=DEFAULT_QWEN_RETRY_BACKOFF_SECONDS,
        minimum=0.0,
        maximum=MAX_QWEN_RETRY_BACKOFF_SECONDS,
    )


def _bounded_float(
    value: float | str | None,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        requested = float(value)
    except (TypeError, ValueError):
        requested = default
    return min(max(requested, minimum), maximum)


def _format_seconds(value: float) -> str:
    formatted = f"{value:.3f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _error_summary(message: str) -> str:
    return " ".join(str(message).split())[:240]
