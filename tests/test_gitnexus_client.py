import json
import subprocess
from pathlib import Path

import pytest

from legacy_pilot.code_knowledge_core.errors import CodeKnowledgeCoreError
from legacy_pilot.code_knowledge_core.gitnexus_client import GitNexusCliClient
from legacy_pilot.contracts.models import GraphQuery, RepoIndexRequest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "java_spring_demo"


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
        "repo_uri": FIXTURE_ROOT.resolve().as_uri(),
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
    assert Path(command[2]) == FIXTURE_ROOT.resolve()
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
    assert Path(payload["repo_path"]) == FIXTURE_ROOT.resolve()
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


def test_query_graph_keeps_route_priority_when_query_terms_mix_symbol_and_route():
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
                    "outgoing": {"calls": []},
                }
            ),
        ]
    )
    client = GitNexusCliClient(gitnexus_bin="custom-gitnexus", runner=runner)

    client.query_graph(
        graph_query(
            query_terms=["DatasetService.getVersion", "/api/dataset/version"],
            node_filters=["Method"],
        )
    )

    route_lookup = runner.calls[0][0][0]
    assert "/api/dataset/version" in route_lookup[2]
    assert "DatasetService.getVersion" not in route_lookup[2]


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


def test_index_repo_rejects_non_local_repo_uri_before_analyze():
    runner = RecordingRunner()
    client = GitNexusCliClient(runner=runner)

    with pytest.raises(CodeKnowledgeCoreError) as excinfo:
        client.index_repo(repo_index_request(repo_uri="https://example.com/repo.git"))

    error = excinfo.value
    assert error.message == "repo_uri must resolve to a local filesystem path."
    assert error.recoverable is True
    assert error.diagnostics["repo_uri"] == "https://example.com/repo.git"
    assert runner.calls == []


def test_index_repo_rejects_missing_repo_path_before_analyze(tmp_path):
    missing_repo = tmp_path / "missing-repo"
    runner = RecordingRunner()
    client = GitNexusCliClient(runner=runner)

    with pytest.raises(CodeKnowledgeCoreError) as excinfo:
        client.index_repo(repo_index_request(repo_uri=missing_repo.as_uri()))

    error = excinfo.value
    assert error.message == "repo_uri path must exist before GitNexus analyze."
    assert error.recoverable is True
    assert Path(error.diagnostics["repo_path"]) == missing_repo
    assert runner.calls == []


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


def test_cypher_process_edges_synthesize_route_to_controller_endpoint_edge():
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process(
                "| n.id | r.type | r.confidence | r.reason | m.id |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Route:/api/dataset/version | ENTRY_POINT_OF | 0.85 | route-entry | proc_0_getversion |\n"
                "| Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1 | STEP_IN_PROCESS | 1 | trace-detection | proc_0_getversion |\n"
            ),
        ]
    )
    client = GitNexusCliClient(runner=runner)

    payload = client.index_repo(repo_index_request())

    nodes_by_id = {node["id"]: node for node in payload["nodes"]}
    edge_pairs = {
        (edge["source_id"], edge["type"], edge["target_id"])
        for edge in payload["relationships"]
    }
    assert nodes_by_id["Route:/api/dataset/version"]["type"] == "API Endpoint"
    assert (
        "Route:/api/dataset/version",
        "MAPS_TO_ENDPOINT",
        "Method:src/main/java/com/legacy/DatasetController.java:DatasetController.getVersion#1",
    ) in edge_pairs


def test_index_payload_respects_node_and_edge_limits():
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process(
                "| n.id | r.type | r.confidence | r.reason | m.id |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/A.java:A.one#1 | CALLS | 0.9 | call | Method:src/B.java:B.two#1 |\n"
                "| Method:src/B.java:B.two#1 | CALLS | 0.8 | call | Method:src/C.java:C.three#1 |\n"
                "| Method:src/C.java:C.three#1 | CALLS | 0.7 | call | Method:src/D.java:D.four#1 |\n"
            ),
        ]
    )
    client = GitNexusCliClient(max_graph_nodes=2, max_graph_edges=1, runner=runner)

    payload = client.index_repo(repo_index_request())

    assert len(payload["nodes"]) <= 2
    assert len(payload["relationships"]) <= 1


def test_stable_index_mode_reuses_existing_graph_without_analyze(monkeypatch):
    monkeypatch.setenv("LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE", "0")
    runner = RecordingRunner(
        cypher_process(
            "| n.id | r.type | r.confidence | r.reason | m.id |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Method:src/A.java:A.one#1 | CALLS | 0.9 | call | Method:src/B.java:B.two#1 |\n"
        )
    )
    client = GitNexusCliClient(gitnexus_bin="custom-gitnexus", runner=runner)

    payload = client.index_repo(repo_index_request())

    assert [call[0][0][1] for call in runner.calls] == ["cypher"]
    assert payload["relationships"]


def test_stable_index_mode_analyzes_and_retries_when_existing_graph_is_empty(
    monkeypatch,
):
    monkeypatch.setenv("LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE", "0")
    runner = RecordingRunner(
        results=[
            cypher_process("| n.id | r.type | r.confidence | r.reason | m.id |\n| --- | --- | --- | --- | --- |\n"),
            text_process("Repository indexed successfully\n"),
            cypher_process(
                "| n.id | r.type | r.confidence | r.reason | m.id |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Method:src/A.java:A.one#1 | CALLS | 0.9 | call | Method:src/B.java:B.two#1 |\n"
            ),
        ]
    )
    client = GitNexusCliClient(gitnexus_bin="custom-gitnexus", runner=runner)

    payload = client.index_repo(repo_index_request())

    assert [call[0][0][1] for call in runner.calls] == ["cypher", "analyze", "cypher"]
    assert payload["relationships"]


def test_index_uses_index_timeout_for_analyze_and_query_timeout_for_cypher(
    monkeypatch,
):
    monkeypatch.setenv("GITNEXUS_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("GITNEXUS_INDEX_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("GITNEXUS_QUERY_TIMEOUT_SECONDS", "30")
    runner = RecordingRunner(
        results=[
            text_process("Repository indexed successfully\n"),
            cypher_process("| n.id | r.type | r.confidence | r.reason | m.id |\n| --- | --- | --- | --- | --- |\n"),
        ]
    )
    client = GitNexusCliClient(runner=runner)

    client.index_repo(repo_index_request())

    assert [call[1]["timeout"] for call in runner.calls] == [120.0, 30.0]


def test_query_uses_query_timeout_for_cypher_lookup_and_context(monkeypatch):
    monkeypatch.setenv("GITNEXUS_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("GITNEXUS_INDEX_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("GITNEXUS_QUERY_TIMEOUT_SECONDS", "30")
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
                    },
                    "incoming": {"calls": []},
                    "outgoing": {"calls": []},
                }
            ),
        ]
    )
    client = GitNexusCliClient(runner=runner)

    client.query_graph(graph_query(query_terms=["DatasetService.getVersion"]))

    assert [call[1]["timeout"] for call in runner.calls] == [30.0, 30.0]


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


@pytest.mark.parametrize(
    ("query_terms", "node_filters", "edge_filters"),
    [
        (["dataset_version"], ["Table"], ["READS_TABLE"]),
        (["selectVersionById"], ["SQL"], ["EXECUTES_SQL"]),
        (["legacy.dataset.cache-enabled"], ["Config"], []),
        (["DatasetNotFoundException"], ["Exception"], []),
    ],
)
def test_query_graph_returns_not_found_for_enriched_lookups_until_local_index_handles_them(
    query_terms,
    node_filters,
    edge_filters,
):
    runner = RecordingRunner()
    client = GitNexusCliClient(runner=runner)

    payload = client.query_graph(
        graph_query(
            query_terms=query_terms,
            node_filters=node_filters,
            edge_filters=edge_filters,
        )
    )

    assert runner.calls == []
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
