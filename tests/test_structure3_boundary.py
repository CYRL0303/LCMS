import ast
import builtins
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from legacy_pilot.contracts.models import (
    EvidenceBackedItem,
    EvidenceBundle,
    EvidenceRef,
    IncidentQuery,
    RCAReport,
)
from legacy_pilot.rca_reasoning_engine.errors import (
    RCAGenerationError,
    RCAEvidenceRequiredError,
)
from legacy_pilot.rca_reasoning_engine.evidence import (
    assert_report_is_evidence_backed,
    collect_bundle_evidence,
    evidence_by_id,
)
from legacy_pilot.rca_reasoning_engine.adapter import (
    QwenApiRCAReasoningEngineAdapter,
    create_rca_reasoning_engine_adapter,
)


def test_collect_bundle_evidence_deduplicates_bundle_sources():
    code = evidence_ref("EV-CODE-1", "code")
    sql = evidence_ref("EV-SQL-1", "sql")
    log = evidence_ref("EV-LOG-1", "log")
    bundle = evidence_bundle(
        code_evidence=[code],
        sql_evidence=[sql],
        log_evidence=[log, code],
    )

    collected = collect_bundle_evidence(bundle)

    assert [ref.evidence_id for ref in collected] == [
        "EV-CODE-1",
        "EV-SQL-1",
        "EV-LOG-1",
    ]
    assert evidence_by_id(bundle)["EV-CODE-1"] == code


def test_report_gate_rejects_unsupported_strong_conclusion():
    evidence = evidence_ref("EV-CODE-1", "code")
    report = valid_report(evidence)
    unsupported = EvidenceBackedItem.model_construct(
        summary="unsupported conclusion",
        evidence_refs=[],
        confidence=0.9,
    )
    invalid = RCAReport.model_construct(
        **{**report.model_dump(), "selected_root_cause": unsupported}
    )

    with pytest.raises(RCAEvidenceRequiredError) as excinfo:
        assert_report_is_evidence_backed(invalid)

    assert excinfo.value.error_code == "EVIDENCE_REQUIRED"
    assert "selected_root_cause" in excinfo.value.message


def test_rca_factory_defaults_to_qwen_api_not_mock(monkeypatch):
    monkeypatch.delenv("LEGACY_PILOT_RCA_BACKEND", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    adapter = create_rca_reasoning_engine_adapter()

    assert isinstance(adapter, QwenApiRCAReasoningEngineAdapter)


def test_structure3_package_imports_only_contracts_and_own_package():
    root = Path(__file__).resolve().parents[1] / "legacy_pilot" / "rca_reasoning_engine"
    allowed_legacy_prefixes = (
        "legacy_pilot.contracts",
        "legacy_pilot.rca_reasoning_engine",
    )
    forbidden_imports = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                if module.startswith("legacy_pilot") and not module.startswith(
                    allowed_legacy_prefixes
                ):
                    forbidden_imports.append(f"{path.name}:{module}")

    assert forbidden_imports == []


def test_structure3_generation_does_not_touch_files_processes_or_lower_structures(
    monkeypatch,
):
    def forbidden_call(*args, **kwargs):
        raise AssertionError(
            "Structure3 must not touch files, subprocesses, or lower structures"
        )

    monkeypatch.setattr(builtins, "open", forbidden_call)
    monkeypatch.setattr(Path, "read_text", forbidden_call)
    monkeypatch.setattr(Path, "read_bytes", forbidden_call)
    monkeypatch.setattr(subprocess, "run", forbidden_call)

    def fake_post(url, headers, body):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"selected_root_cause":{"summary":"datasetId guard missing",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7},'
                            '"suggested_fix":[{"summary":"add validation",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"endpoint and mapper need regression",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.6},'
                            '"migration_checklist":["add regression"],'
                            '"affected_path":[],"open_questions":[],"confidence":0.7}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(api_key="test-key", http_post=fake_post)
    bundle = evidence_bundle(code_evidence=[evidence_ref("EV-CODE-1", "code")])

    report = adapter.generate_rca(bundle)
    reviewed = adapter.review_rca(report)

    assert report.selected_root_cause.evidence_refs
    assert reviewed.approved_findings


def test_structure3_package_has_no_lower_structure_runtime_tokens():
    root = Path(__file__).resolve().parents[1] / "legacy_pilot" / "rca_reasoning_engine"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = [
        "PostgresGraphStore",
        "GitNexus",
        "psycopg",
        "query_graph",
        "repo_uri",
        "subprocess",
        "Path(",
    ]
    for token in forbidden:
        assert token not in text


def test_qwen_adapter_maps_real_api_shape_to_evidence_backed_report():
    requests = []

    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        requests.append({"url": url, "headers": headers, "body": body})
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"datasetId is missing before mapper read",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.72}],'
                            '"selected_root_cause":{"summary":"datasetId guard is missing in the service path",'
                            '"evidence_ids":["EV-CODE-1","EV-LOG-1"],"confidence":0.74},'
                            '"suggested_fix":[{"summary":"validate datasetId before service and mapper calls",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.7}],'
                            '"migration_impact":{"summary":"dataset version endpoint and mapper SQL need regression coverage",'
                            '"evidence_ids":["EV-CODE-1"],"confidence":0.66},'
                            '"migration_checklist":["Add null datasetId endpoint regression test"],'
                            '"affected_path":["DatasetController.getVersion","DatasetService.getVersion"],'
                            '"open_questions":[],"confidence":0.74}'
                        )
                    }
                }
            ]
        }

    code = evidence_ref("EV-CODE-1", "code")
    log = evidence_ref("EV-LOG-1", "log")
    adapter = QwenApiRCAReasoningEngineAdapter(
        api_key="test-key",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        confidence_cap=0.5,
        http_post=fake_post,
    )

    report = adapter.generate_rca(
        evidence_bundle(code_evidence=[code], log_evidence=[log])
    )

    assert (
        requests[0]["url"]
        == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert requests[0]["headers"]["Authorization"] == "Bearer test-key"
    prompt = requests[0]["body"]["messages"][1]["content"]
    assert "EV-CODE-1" in prompt
    assert "EV-LOG-1" in prompt
    assert (
        report.selected_root_cause.summary
        == "datasetId guard is missing in the service path"
    )
    assert [ref.evidence_id for ref in report.selected_root_cause.evidence_refs] == [
        "EV-CODE-1",
        "EV-LOG-1",
    ]
    assert report.confidence == 0.5


def test_qwen_adapter_rejects_unknown_evidence_ids():
    def fake_post(url: str, headers: dict[str, str], body: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"hypotheses":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"selected_root_cause":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"suggested_fix":[{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9}],'
                            '"migration_impact":{"summary":"unsupported",'
                            '"evidence_ids":["EV-UNKNOWN"],"confidence":0.9},'
                            '"migration_checklist":[],"affected_path":[],'
                            '"open_questions":[],"confidence":0.9}'
                        )
                    }
                }
            ]
        }

    adapter = QwenApiRCAReasoningEngineAdapter(
        api_key="test-key",
        http_post=fake_post,
    )
    bundle = evidence_bundle(code_evidence=[evidence_ref("EV-CODE-1", "code")])

    with pytest.raises(RCAGenerationError) as excinfo:
        adapter.generate_rca(bundle)

    assert "unknown evidence_ids" in excinfo.value.message
    assert "EV-UNKNOWN" in excinfo.value.message


def evidence_ref(evidence_id: str, source_type: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        trace_id="TRACE-STRUCTURE3-001",
        source_type=source_type,
        source_id=evidence_id,
        file_path=(
            "src/main/java/com/legacy/DatasetService.java"
            if source_type == "code"
            else None
        ),
        start_line=40 if source_type == "code" else None,
        end_line=45 if source_type == "code" else None,
        excerpt=f"{source_type} evidence",
        excerpt_hash=f"hash-{evidence_id}",
        extraction_method="java_parser" if source_type == "code" else "regex",
        confidence=0.9,
        created_at=datetime(2026, 6, 29, tzinfo=UTC),
    )


def incident_query() -> IncidentQuery:
    return IncidentQuery(
        trace_id="TRACE-STRUCTURE3-001",
        repo_id="repo-demo",
        graph_id="GRAPH-repo-demo",
        error_type="NullPointerException",
        suspected_location="DatasetService.getVersion",
        query_terms=["NullPointerException", "DatasetService.getVersion"],
        contract_version="1.0.0",
    )


def evidence_bundle(**updates) -> EvidenceBundle:
    values = {
        "trace_id": "TRACE-STRUCTURE3-001",
        "repo_id": "repo-demo",
        "contract_version": "1.0.0",
        "alert_summary": "NullPointerException near DatasetService.getVersion",
        "incident_query": incident_query(),
    }
    values.update(updates)
    return EvidenceBundle(**values)


def backed(summary: str, evidence: EvidenceRef) -> EvidenceBackedItem:
    return EvidenceBackedItem(
        summary=summary,
        evidence_refs=[evidence],
        confidence=0.8,
    )


def valid_report(evidence: EvidenceRef) -> RCAReport:
    root = backed("DatasetService uses datasetId without a guard.", evidence)
    fix = backed("Add request validation and service guard for datasetId.", evidence)
    impact = backed("Dataset version endpoint and mapper SQL are affected.", evidence)
    return RCAReport(
        report_id="RCA-STRUCTURE3-001",
        trace_id="TRACE-STRUCTURE3-001",
        repo_id="repo-demo",
        contract_version="1.0.0",
        hypotheses=[root],
        selected_root_cause=root,
        evidence_chain=[evidence],
        affected_path=["DatasetController.getVersion", "DatasetService.getVersion"],
        suggested_fix=[fix],
        migration_impact=impact,
        migration_checklist=["Add null datasetId regression coverage."],
        confidence=0.8,
    )
