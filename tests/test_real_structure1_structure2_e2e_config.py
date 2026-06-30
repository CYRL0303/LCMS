import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_E2E = ROOT / "docker-compose.e2e.yml"
PYPROJECT = ROOT / "pyproject.toml"
GITIGNORE = ROOT / ".gitignore"
README = ROOT / "README.md"
REAL_E2E_SCRIPT = ROOT / "scripts" / "run-real-e2e.ps1"
QWEN_ENV_SCRIPT = ROOT / "scripts" / "set-qwen-user-env.ps1"

REQUIRED_ENV_KEYS = {
    "LEGACY_PILOT_RUN_REAL_E2E",
    "LEGACY_PILOT_RUN_POSTGRES_GRAPH_STORE",
    "LEGACY_PILOT_RUN_GITNEXUS_INTEGRATION",
    "LEGACY_PILOT_CODE_CORE_BACKEND",
    "LEGACY_PILOT_GRAPH_STORE_BACKEND",
    "LEGACY_PILOT_GRAPH_STORE_DSN",
    "LEGACY_PILOT_GRAPH_STORE_TABLE",
    "LEGACY_PILOT_GRAPH_STORE_TEST_TABLE",
    "LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND",
    "LEGACY_PILOT_INCIDENT_MEMORY_BACKEND",
    "LEGACY_PILOT_INCIDENT_MEMORY_DSN",
    "LEGACY_PILOT_INCIDENT_MEMORY_TABLE",
    "LEGACY_PILOT_RCA_BACKEND",
    "LEGACY_PILOT_RCA_BASE_URL",
    "LEGACY_PILOT_RCA_MODEL",
    "LEGACY_PILOT_RCA_CONFIDENCE_CAP",
    "LEGACY_PILOT_RCA_REPAIR_ATTEMPTS",
    "DASHSCOPE_API_KEY",
    "GITNEXUS_BIN",
    "GITNEXUS_REPO_ROOT",
    "GITNEXUS_TIMEOUT_SECONDS",
    "GITNEXUS_INDEX_TIMEOUT_SECONDS",
    "GITNEXUS_QUERY_TIMEOUT_SECONDS",
}


def test_env_example_documents_real_structure1_structure2_e2e_variables():
    env_values = _parse_env_example(ENV_EXAMPLE)

    assert REQUIRED_ENV_KEYS.issubset(env_values)
    assert env_values["LEGACY_PILOT_RUN_REAL_E2E"] == "0"
    assert env_values["LEGACY_PILOT_CODE_CORE_BACKEND"] == "gitnexus_cli"
    assert env_values["LEGACY_PILOT_GRAPH_STORE_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND"] == "graph_context"
    assert env_values["LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
    assert "127.0.0.1:55432" in env_values["LEGACY_PILOT_GRAPH_STORE_DSN"]


def test_docker_compose_e2e_defines_postgres_graph_store_service():
    compose = yaml.safe_load(COMPOSE_E2E.read_text(encoding="utf-8"))
    postgres = compose["services"]["postgres"]

    assert postgres["image"] == "postgres:16-alpine"
    assert postgres["container_name"] == "legacy-pilot-pg-e2e"
    assert "55432:5432" in postgres["ports"]
    assert postgres["environment"] == {
        "POSTGRES_USER": "legacy_pilot",
        "POSTGRES_PASSWORD": "legacy_pilot",
        "POSTGRES_DB": "legacy_pilot",
    }
    assert "healthcheck" in postgres


def test_real_e2e_script_starts_postgres_and_runs_real_chain():
    script = REAL_E2E_SCRIPT.read_text(encoding="utf-8")

    assert "Docker Desktop.exe" in script
    assert "Start-Process" in script
    assert "docker info" in script
    assert "DockerWaitSeconds" in script
    assert "SkipDockerDaemonStart" in script
    assert ".env.local" in script
    assert "Import-LocalEnvFile" in script
    assert 'GetEnvironmentVariable("DASHSCOPE_API_KEY", "User")' in script
    assert "docker compose -f" in script
    assert "docker-compose.e2e.yml" in script
    assert "up -d postgres" in script
    assert "pg_isready" in script
    assert "DASHSCOPE_API_KEY" in script
    assert "LEGACY_PILOT_RUN_REAL_E2E" in script
    assert "LEGACY_PILOT_RCA_BACKEND" in script
    assert "LEGACY_PILOT_INCIDENT_MEMORY_BACKEND" in script
    assert "LEGACY_PILOT_INCIDENT_MEMORY_DSN" in script
    assert "LEGACY_PILOT_INCIDENT_MEMORY_TABLE" in script
    assert "LEGACY_PILOT_RCA_REPAIR_ATTEMPTS" in script
    assert "qwen_api" in script
    assert "tests/test_real_structure1_structure2_e2e.py" in script
    assert "sk-" not in script
    assert "*> $null" not in script


def test_qwen_env_script_persists_user_env_and_optional_local_env_file():
    script = QWEN_ENV_SCRIPT.read_text(encoding="utf-8")

    assert "Read-Host" in script
    assert "DASHSCOPE_API_KEY" in script
    assert 'SetEnvironmentVariable("DASHSCOPE_API_KEY", $plainKey, "User")' in script
    assert ".env.local" in script
    assert "WriteDotEnvLocal" in script
    assert "sk-" not in script


def test_readme_documents_qwen_key_replacement_without_committing_secret():
    readme = README.read_text(encoding="utf-8")

    assert "Replace the persisted Qwen key" in readme
    assert "set-qwen-user-env.ps1" in readme
    assert "[Environment]::SetEnvironmentVariable" in readme
    assert "sk-" not in readme


def test_pytest_declares_real_e2e_marker():
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]

    assert any(
        marker.startswith("real_structure1_structure2_e2e:")
        for marker in markers
    )


def test_gitignore_keeps_real_env_files_out_but_allows_example():
    lines = {
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    assert ".env" in lines
    assert ".env.*" in lines
    assert ".env.local" in lines
    assert "!.env.example" in lines


def _parse_env_example(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values
