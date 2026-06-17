import json
import subprocess

import pytest

from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


class RecordingRunner:
    def __init__(self, result=None, side_effect=None, results=None):
        self.result = result or subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        self.results = list(results or [])
        self.side_effect = side_effect
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.side_effect:
            raise self.side_effect
        if self.results:
            return self.results.pop(0)
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


def text_process(stdout="", *, stderr="debug details", returncode=0):
    return subprocess.CompletedProcess(
        args=["gitnexus"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def cypher_process(markdown, *, stderr="debug details"):
    return completed_process({"markdown": markdown}, stderr=stderr)


def test_index_command_uses_real_gitnexus_analyze_shape(monkeypatch):
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
    assert command[:2] == ["env-gitnexus", "analyze"]
    assert "/workspace/legacy-demo" in command
    assert "--skip-git" in command
    assert "--index-only" in command
    assert "--name" in command
    assert "repo-demo" in command
    assert kwargs["cwd"] == "/gitnexus/runtime"
    assert kwargs["timeout"] == 9.0


def test_index_repo_runs_analyze_then_cypher_and_normalizes_graph():
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process(
                "| n.id | r.type | r.confidence | r.reason | m.id |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1 | CALLS | 0.85 | import-resolved | Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1 |\n"
            ),
        ]
    )
    client = GitNexusCliClient(gitnexus_bin="custom-gitnexus", runner=runner)

    payload = client.index_repo(repo_index_request())

    assert len(runner.calls) == 2
    assert runner.calls[0][0][0][:2] == ["custom-gitnexus", "analyze"]
    assert runner.calls[1][0][0][:2] == ["custom-gitnexus", "cypher"]
    assert payload["repo_id"] == "repo-demo"
    assert payload["graph_id"] == "GRAPH-repo-demo"
    assert payload["repo_path"] == "/workspace/legacy-demo"
    assert payload["parser_version"] == "gitnexus_cli+cypher_v1"
    assert payload["nodes"][0]["id"].startswith("Method:")
    assert payload["relationships"][0]["type"] == "CALLS"
    assert payload["relationships"][0]["source_id"].endswith("DatasetController.getVersion#1")
    assert payload["relationships"][0]["target_id"].endswith("DatasetService.getVersion#1")
    assert payload["relationships"][0]["confidence"] == 0.85


def test_query_graph_uses_cypher_uid_lookup_then_context_for_method_query():
    runner = RecordingRunner(
        results=[
            cypher_process(
                "| n.id | n.name | n.filePath | n.startLine | n.endLine |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1 | getVersion | src/main/java/com/legacy/DatasetService.java | 12 | 17 |\n"
            ),
            completed_process(
                {
                    "status": "found",
                    "symbol": {
                        "uid": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
                        "name": "getVersion",
                        "kind": "Method",
                        "filePath": "src/main/java/com/legacy/DatasetService.java",
                        "startLine": 12,
                        "endLine": 17,
                    },
                    "incoming": {
                        "calls": [
                            {
                                "uid": "Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1",
                                "name": "getVersion",
                                "kind": "Method",
                                "filePath": "src/main/java/com/legacy/DatasetController.java",
                                "startLine": 14,
                            }
                        ]
                    },
                    "outgoing": {
                        "calls": [
                            {
                                "uid": "Method:src/main/java/com/legacy/DatasetMapper.java:DatasetMapper.selectVersionById#1",
                                "name": "selectVersionById",
                                "kind": "Method",
                                "filePath": "src/main/java/com/legacy/DatasetMapper.java",
                                "startLine": 3,
                            }
                        ]
                    },
                    "processes": [
                        {
                            "id": "proc_0_getversion",
                            "name": "GetVersion \u2192 SelectVersionById",
                        }
                    ],
                }
            ),
        ]
    )
    client = GitNexusCliClient(
        gitnexus_bin="custom-gitnexus",
        timeout_seconds=5,
        max_graph_nodes=11,
        max_graph_edges=22,
        runner=runner,
    )

    payload = client.query_graph(graph_query(query_terms=["DatasetService.getVersion"]))

    lookup_command = runner.calls[0][0][0]
    context_command = runner.calls[1][0][0]
    assert lookup_command[:2] == ["custom-gitnexus", "cypher"]
    assert "DatasetService.getVersion" in lookup_command[2]
    assert context_command[:2] == ["custom-gitnexus", "context"]
    assert "--uid" in context_command
    assert "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1" in context_command
    assert payload["graph_id"] == "GRAPH-GN"
    assert payload["nodes"][0]["id"].endswith("DatasetService.getVersion#1")
    assert payload["relationships"][0]["type"] == "CALLS"
    assert payload["paths"] == [
        [
            "Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1",
            "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
            "Method:src/main/java/com/legacy/DatasetMapper.java:DatasetMapper.selectVersionById#1",
        ]
    ]


def test_query_graph_route_term_falls_back_to_controller_method_context():
    runner = RecordingRunner(
        results=[
            cypher_process(
                "| n.id | n.name | n.filePath |\n"
                "| --- | --- | --- |\n"
                "| File:src/main/java/com/legacy/DatasetController.java | DatasetController.java | src/main/java/com/legacy/DatasetController.java |\n"
            ),
            cypher_process(
                "| n.id | n.name | n.filePath | n.startLine | n.endLine |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1 | getVersion | src/main/java/com/legacy/DatasetController.java | 14 | 16 |\n"
            ),
            completed_process(
                {
                    "status": "found",
                    "symbol": {
                        "uid": "Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1",
                        "name": "getVersion",
                        "kind": "Method",
                        "filePath": "src/main/java/com/legacy/DatasetController.java",
                        "startLine": 14,
                    },
                    "incoming": {"calls": []},
                    "outgoing": {
                        "calls": [
                            {
                                "uid": "Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1",
                                "name": "getVersion",
                                "kind": "Method",
                                "filePath": "src/main/java/com/legacy/DatasetService.java",
                                "startLine": 12,
                            }
                        ]
                    },
                }
            ),
        ]
    )
    client = GitNexusCliClient(gitnexus_bin="custom-gitnexus", runner=runner)

    payload = client.query_graph(graph_query(query_terms=["/api/dataset/version"]))

    route_lookup = runner.calls[0][0][0]
    method_lookup = runner.calls[1][0][0]
    context_command = runner.calls[2][0][0]
    assert route_lookup[:2] == ["custom-gitnexus", "cypher"]
    assert "/api/dataset/version" in route_lookup[2]
    assert "DatasetController.getVersion" in method_lookup[2]
    assert context_command[:2] == ["custom-gitnexus", "context"]
    assert payload["nodes"][0]["id"].endswith("DatasetController.getVersion#1")
    assert payload["relationships"][0]["target_id"].endswith("DatasetService.getVersion#1")


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


def test_valid_cypher_markdown_is_normalized_into_mapper_ready_index_payload():
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process(
                "| n.id | r.type | r.confidence | r.reason | m.id |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/main/java/com/legacy/DatasetService.java:DatasetService.getVersion#1 | CALLS | 0.85 | import-resolved | Method:src/main/java/com/legacy/DatasetMapper.java:DatasetMapper.selectVersionById#1 |\n",
                stderr="index diagnostic",
            ),
        ]
    )
    client = GitNexusCliClient(runner=runner)

    payload = client.index_repo(repo_index_request(repo_id="repo-request"))

    assert payload["repo_id"] == "repo-request"
    assert payload["graph_id"] == "GRAPH-repo-request"
    assert payload["trace_id"] == "TRACE-INDEX-repo-request"
    assert payload["parser_version"] == "gitnexus_cli+cypher_v1"
    assert payload["nodes"][0]["id"].endswith("DatasetService.getVersion#1")
    assert payload["relationships"][0]["type"] == "CALLS"
    assert client.last_diagnostics["stderr"] == "index diagnostic"


def test_query_graph_returns_not_found_when_symbol_lookup_is_empty():
    runner = RecordingRunner(cypher_process("| n.id |\n| --- |\n"))
    client = GitNexusCliClient(runner=runner)

    payload = client.query_graph(graph_query())

    assert payload == {
        "graph_id": "GRAPH-GN",
        "nodes": [],
        "relationships": [],
        "paths": [],
        "not_found": True,
    }


def test_constructor_configuration_overrides_environment(monkeypatch):
    monkeypatch.setenv("GITNEXUS_BIN", "env-gitnexus")
    monkeypatch.setenv("GITNEXUS_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("LEGACY_PILOT_MAX_GRAPH_NODES", "99")
    monkeypatch.setenv("LEGACY_PILOT_MAX_GRAPH_EDGES", "99")
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process("| n.id | r.type | r.confidence | r.reason | m.id |\n| --- | --- | --- | --- | --- |\n"),
        ]
    )
    client = GitNexusCliClient(
        gitnexus_bin="param-gitnexus",
        timeout_seconds=3,
        max_graph_nodes=7,
        max_graph_edges=8,
        runner=runner,
    )

    client.index_repo(repo_index_request())

    analyze_command = runner.calls[0][0][0]
    cypher_command = runner.calls[1][0][0]
    assert analyze_command[0] == "param-gitnexus"
    assert cypher_command[0] == "param-gitnexus"
    assert runner.calls[0][1]["timeout"] == 3.0
    assert runner.calls[0][1]["encoding"] == "utf-8"
    assert runner.calls[0][1]["errors"] == "replace"
    assert "LIMIT 8" in cypher_command[2]
