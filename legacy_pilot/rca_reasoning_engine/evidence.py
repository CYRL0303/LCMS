from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    RCAReport,
)
from legacy_pilot.rca_reasoning_engine.errors import RCAEvidenceRequiredError


def collect_bundle_evidence(bundle: EvidenceBundle) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for ref in [
        *bundle.code_evidence,
        *bundle.sql_evidence,
        *bundle.config_evidence,
        *bundle.log_evidence,
    ]:
        _append_once(refs, seen, ref)
    for incident in bundle.similar_incidents:
        for ref in incident.evidence_refs:
            _append_once(refs, seen, ref)
    return refs


def evidence_by_id(bundle: EvidenceBundle) -> dict[str, EvidenceRef]:
    return {ref.evidence_id: ref for ref in collect_bundle_evidence(bundle)}


def assert_bundle_has_evidence(bundle: EvidenceBundle) -> list[EvidenceRef]:
    evidence = collect_bundle_evidence(bundle)
    if not evidence:
        raise RCAEvidenceRequiredError(
            "EvidenceBundle must contain evidence before RCA generation."
        )
    return evidence


def assert_report_is_evidence_backed(report: RCAReport) -> None:
    _require_item_evidence("selected_root_cause", report.selected_root_cause)
    for index, hypothesis in enumerate(report.hypotheses):
        _require_item_evidence(f"hypotheses[{index}]", hypothesis)
    for index, fix in enumerate(report.suggested_fix):
        _require_item_evidence(f"suggested_fix[{index}]", fix)
    _require_item_evidence("migration_impact", report.migration_impact)
    if not report.evidence_chain:
        raise RCAEvidenceRequiredError("evidence_chain must include evidence_refs.")


def _require_item_evidence(field_name: str, item: EvidenceBackedItem) -> None:
    if not getattr(item, "evidence_refs", None):
        raise RCAEvidenceRequiredError(f"{field_name} must include evidence_refs.")


def _append_once(refs: list[EvidenceRef], seen: set[str], ref: EvidenceRef) -> None:
    if ref.evidence_id in seen:
        return
    seen.add(ref.evidence_id)
    refs.append(ref)
