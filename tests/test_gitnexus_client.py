import json
import subprocess

import pytest

from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


class RecordingRunner:
    def __init__(self, result=None, side_effect=None):
        self.result = result or subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        self.side_effect = side_effect
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.side_effect:
            raise self.side_effect
        return self.result


def repo_index_request(**overrides):
    values = {
        "repo_id": "repo-demo",
        "repo_uri": "file:///workspace/legacy-demo",
        "language_hint": "java",
        "parser_profile": "spring-boot",
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return RepoIndexRequest(**values)


def graph_query(**overrides):
    values = {
        "repo_id": "repo-demo",
        "graph_id": "GRAPH-GN",
        "query_terms": ["DatasetService.getVersion", "/api/dataset/version"],
        "node_filters": ["Method"],
        "edge_filters": ["CALLS"],
        "max_depth": 3,
        "trace_id": "TRACE-Q-001",
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return GraphQuery(**values)


def completed_process(payload, *, stderr="debug details"):
    return subprocess.CompletedProcess(
        args=["gitnexus"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr=stderr,
    )


def test_index_command_includes_repo_path_repo_id_and_operation(monkeypatch):
    monkeypatch.setenv("GITNEXUS_BIN", "env-gitnexus")
    monkeypatch.setenv("GITNEXUS_REPO_ROOT", "/gitnexus/runtime")
    monkeypatch.setenv("GITNEXUS_TIMEOUT_SECONDS", "9")
    runner = RecordingRunner(
        completed_process(
            {
                "graphId": "GRAPH-GN",
                "nodes": [],
                "relationships": [],
            }
        )
    )
    client = GitNexusCliClient(runner=runner)

    client.index_repo(repo_index_request())

    args, kwargs = runner.calls[0]
    command = args[0]
    assert command[:2] == ["env-gitnexus", "index"]
    assert "--repo-id" in command
    assert "repo-demo" in command
    assert "--repo-path" in command
    assert "/workspace/legacy-demo" in command
    assert kwargs["cwd"] == "/gitnexus/runtime"
    assert kwargs["timeout"] == 9.0


def test_query_command_includes_requested_operation_and_query_inputs():
    runner = RecordingRunner(completed_process({"nodes": [], "relationships": []}))
    client = GitNexusCliClient(
        gitnexus_bin="custom-gitnexus",
        timeout_seconds=5,
        max_graph_nodes=11,
        max_graph_edges=22,
        runner=runner,
    )

    client.query_graph(graph_query())

    command = runner.calls[0][0][0]
    assert command[:2] == ["custom-gitnexus", "query"]
    assert "--repo-id" in command
    assert "repo-demo" in command
    assert "--graph-id" in command
    assert "GRAPH-GN" in command
    assert "--query-term" in command
    assert "DatasetService.getVersion" in command
    assert "--max-depth" in command
    assert "3" in command
    assert "--max-nodes" in command
    assert "11" in command
    assert "--max-edges" in command
    assert "22" in command


@pytest.mark.parametrize(
    ("side_effect", "expected_message"),
    [
        (
            subprocess.TimeoutExpired(cmd=["gitnexus", "index"], timeout=1),
            "GitNexus CLI timed out while indexing repo.",
        ),
        (
            FileNotFoundError("missing binary"),
            "GitNexus CLI executable was not found.",
        ),
    ],
)
def test_index_subprocess_failures_become_recoverable_code_knowledge_core_errors(
    side_effect,
    expected_message,
):
    runner = RecordingRunner(side_effect=side_effect)
    client = GitNexusCliClient(gitnexus_bin="missing-gitnexus", runner=runner)

    with pytest.raises(CodeKnowledgeCoreError) as excinfo:
        client.index_repo(repo_index_request())

    assert excinfo.value.message == expected_message
    assert excinfo.value.recoverable is True
    assert excinfo.value.source_module == "code_knowledge_core"


def test_non_zero_exit_becomes_recoverable_error_without_leaking_stderr_text():
    runner = RecordingRunner(
        subprocess.CompletedProcess(
            args=["gitnexus"],
            returncode=17,
            stdout="",
            stderr="Traceback: internal secret",
        )
    )
    client = GitNexusCliClient(runner=runner)

    with pytest.raises(CodeKnowledgeCoreError) as excinfo:
        client.query_graph(graph_query())

    error = excinfo.value
    assert error.message == "GitNexus CLI failed while querying graph."
    assert error.recoverable is True
    assert "Traceback" not in error.message
    assert error.diagnostics["stderr"] == "Traceback: internal secret"
    assert error.diagnostics["returncode"] == "17"


def test_invalid_json_stdout_becomes_recoverable_error():
    runner = RecordingRunner(
        subprocess.CompletedProcess(
            args=["gitnexus"],
            returncode=0,
            stdout="{not json",
            stderr="parser diagnostic",
        )
    )
    client = GitNexusCliClient(runner=runner)

    with pytest.raises(CodeKnowledgeCoreError) as excinfo:
        client.index_repo(repo_index_request())

    assert excinfo.value.message == "GitNexus CLI returned invalid JSON while indexing repo."
    assert excinfo.value.recoverable is True
    assert excinfo.value.diagnostics["stderr"] == "parser diagnostic"


def test_valid_index_json_is_normalized_into_mapper_ready_payload():
    raw_payload = {
        "graphId": "GRAPH-GN",
        "metadata": {"repoId": "repo-from-gitnexus"},
        "graph": {
            "vertices": [{"id": "N1", "labels": ["Method"]}],
            "edges": [{"id": "R1", "source": "N1", "target": "N1"}],
        },
    }
    runner = RecordingRunner(completed_process(raw_payload, stderr="index diagnostic"))
    client = GitNexusCliClient(runner=runner)

    payload = client.index_repo(repo_index_request(repo_id="repo-request"))

    assert payload == {
        "repo_id": "repo-from-gitnexus",
        "graph_id": "GRAPH-GN",
        "trace_id": "TRACE-INDEX-repo-request",
        "nodes": [{"id": "N1", "labels": ["Method"]}],
        "relationships": [{"id": "R1", "source": "N1", "target": "N1"}],
    }
    assert client.last_diagnostics["stderr"] == "index diagnostic"


def test_valid_query_json_is_normalized_into_mapper_ready_payload():
    raw_payload = {
        "graphId": "GRAPH-GN",
        "subgraph": {
            "nodes": [{"id": "N1", "type": "Method"}],
            "relationships": [{"id": "R1", "source_id": "N1", "target_id": "N1"}],
        },
        "paths": [{"nodes": ["N1"]}],
    }
    runner = RecordingRunner(completed_process(raw_payload))
    client = GitNexusCliClient(runner=runner)

    payload = client.query_graph(graph_query())

    assert payload == {
        "graph_id": "GRAPH-GN",
        "nodes": [{"id": "N1", "type": "Method"}],
        "relationships": [{"id": "R1", "source_id": "N1", "target_id": "N1"}],
        "paths": [{"nodes": ["N1"]}],
        "not_found": False,
    }


def test_constructor_configuration_overrides_environment(monkeypatch):
    monkeypatch.setenv("GITNEXUS_BIN", "env-gitnexus")
    monkeypatch.setenv("GITNEXUS_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("LEGACY_PILOT_MAX_GRAPH_NODES", "99")
    monkeypatch.setenv("LEGACY_PILOT_MAX_GRAPH_EDGES", "99")
    runner = RecordingRunner(completed_process({"nodes": [], "relationships": []}))
    client = GitNexusCliClient(
        gitnexus_bin="param-gitnexus",
        timeout_seconds=3,
        max_graph_nodes=7,
        max_graph_edges=8,
        runner=runner,
    )

    client.query_graph(graph_query())

    command = runner.calls[0][0][0]
    assert command[0] == "param-gitnexus"
    assert runner.calls[0][1]["timeout"] == 3.0
    assert "7" in command
    assert "8" in command
