import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from json import dumps, loads
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    RCAReport,
    ReviewedRCAReport,
)
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
DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_RCA_BACKEND = "qwen_api"
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_RCA_CONFIDENCE_CAP = 0.75


class RCAReasoningEngineAdapter(ABC):
    @abstractmethod
    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        ...

    @abstractmethod
    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        ...


@dataclass(frozen=True)
class QwenApiRCAReasoningEngineAdapter(RCAReasoningEngineAdapter):
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_QWEN_BASE_URL
    model: str = DEFAULT_QWEN_MODEL
    confidence_cap: float = DEFAULT_RCA_CONFIDENCE_CAP
    http_post: Any | None = None
    backend_name: str = "qwen_api"

    def generate_rca(self, bundle: EvidenceBundle) -> RCAReport:
        evidence = assert_bundle_has_evidence(bundle)
        api_key = self.api_key or os.getenv(DASHSCOPE_API_KEY_ENV)
        if not api_key:
            raise RCAGenerationError(
                "DASHSCOPE_API_KEY is required for qwen_api RCA backend.",
                recoverable=True,
            )
        response = self._post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are LegacyPilot Structure3 RCA Reasoning Engine. "
                            "Use only evidence IDs from the supplied EvidenceBundle. "
                            "Return strict JSON and never invent evidence IDs."
                        ),
                    },
                    {"role": "user", "content": _qwen_rca_prompt(bundle, evidence)},
                ],
                "temperature": 0,
            },
        )
        payload = _loads_json_object(_chat_completion_content(response))
        return _report_from_qwen_payload(
            bundle=bundle,
            payload=payload,
            evidence_lookup=evidence_by_id(bundle),
            confidence_cap=self.confidence_cap,
        )

    def review_rca(self, report: RCAReport) -> ReviewedRCAReport:
        assert_report_is_evidence_backed(report)
        return ReviewedRCAReport(
            report_id=report.report_id,
            trace_id=report.trace_id,
            repo_id=report.repo_id,
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
        if self.http_post is not None:
            return self.http_post(url, headers, body)
        return _http_post_json(url, headers=headers, body=body)


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
        )
    return UnsupportedRCAReasoningEngineAdapter(selected)


def _qwen_rca_prompt(bundle: EvidenceBundle, evidence: list[EvidenceRef]) -> str:
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
        "Evidence IDs:\n"
        + "\n".join(evidence_lines)
        + "\nReturn JSON with keys hypotheses, selected_root_cause, suggested_fix, "
        "migration_impact, migration_checklist, affected_path, open_questions, confidence. "
        "Each conclusion object must contain summary, evidence_ids, confidence."
    )


def _report_from_qwen_payload(
    *,
    bundle: EvidenceBundle,
    payload: dict[str, Any],
    evidence_lookup: dict[str, EvidenceRef],
    confidence_cap: float,
) -> RCAReport:
    hypotheses = [
        _item_from_qwen(raw, evidence_lookup, "hypotheses")
        for raw in payload.get("hypotheses", [])
    ]
    selected_root_cause = _item_from_qwen(
        payload.get("selected_root_cause"),
        evidence_lookup,
        "selected_root_cause",
    )
    suggested_fix = [
        _item_from_qwen(raw, evidence_lookup, "suggested_fix")
        for raw in payload.get("suggested_fix", [])
    ]
    migration_impact = _item_from_qwen(
        payload.get("migration_impact"),
        evidence_lookup,
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
    return report


def _item_from_qwen(
    raw: Any,
    evidence_lookup: dict[str, EvidenceRef],
    field_name: str,
) -> EvidenceBackedItem:
    if not isinstance(raw, dict):
        raise RCAGenerationError(f"{field_name} must be an object.")
    evidence_ids = raw.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise RCAGenerationError(f"{field_name} must include evidence_ids.")
    unknown = [str(eid) for eid in evidence_ids if str(eid) not in evidence_lookup]
    if unknown:
        raise RCAGenerationError(
            f"{field_name} referenced unknown evidence_ids: {', '.join(unknown)}"
        )
    return EvidenceBackedItem(
        summary=str(raw.get("summary", "")).strip(),
        evidence_refs=[evidence_lookup[str(eid)] for eid in evidence_ids],
        confidence=min(float(raw.get("confidence", 0.0)), 1.0),
    )


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
) -> dict[str, Any]:
    request = Request(
        url,
        data=dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RCAGenerationError(f"Qwen RCA API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RCAGenerationError(f"Qwen RCA API request failed: {exc.reason}") from exc


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
