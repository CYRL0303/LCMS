import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_E2E = ROOT / "docker-compose.e2e.yml"
PYPROJECT = ROOT / "pyproject.toml"
GITIGNORE = ROOT / ".gitignore"

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
