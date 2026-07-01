from pathlib import Path
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_build_backend_for_container_install():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
    assert "setuptools>=75" in pyproject["build-system"]["requires"]
    assert "wheel" in pyproject["build-system"]["requires"]
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "legacy_pilot*"
    ]


def test_gitignore_allows_prod_env_example_but_blocks_private_prod_env():
    lines = _nonempty_lines(ROOT / ".gitignore")

    assert ".env" in lines
    assert ".env.*" in lines
    assert ".env.prod" in lines
    assert "!.env.example" in lines
    assert "!.env.prod.example" in lines


def test_root_dockerignore_excludes_secrets_and_generated_artifacts():
    lines = _nonempty_lines(ROOT / ".dockerignore")

    assert ".git" in lines
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines
    assert "!.env.prod.example" in lines
    assert "frontend/node_modules" in lines
    assert "**/__pycache__" in lines
    assert "*.log" in lines
    assert ".e2e-artifacts" in lines
    assert "playwright-report" in lines


def test_prod_env_example_documents_real_backends_without_localhost_dsns():
    env_values = _parse_env(ROOT / ".env.prod.example")

    assert env_values["POSTGRES_USER"] == "legacy_pilot"
    assert env_values["POSTGRES_PASSWORD"] == "legacy_pilot_dev_password"
    assert env_values["POSTGRES_DB"] == "legacy_pilot"
    assert env_values["GITNEXUS_REPO_ROOT"] == "./.runtime/gitnexus"
    assert env_values["LEGACY_PILOT_CODE_CORE_BACKEND"] == "gitnexus_cli"
    assert env_values["LEGACY_PILOT_GRAPH_STORE_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND"] == "graph_context"
    assert env_values["LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
    assert env_values["DASHSCOPE_API_KEY"] == ""
    assert "127.0.0.1" not in (ROOT / ".env.prod.example").read_text(
        encoding="utf-8"
    )


def test_api_dockerfile_runs_real_gitnexus_wrapper_as_non_root():
    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")

    assert "FROM python:3.13-slim" in dockerfile
    assert "apt-get install" in dockerfile
    assert " git " in dockerfile or " git\\" in dockerfile
    assert " nodejs " in dockerfile or " nodejs\\" in dockerfile
    assert "exec node /opt/gitnexus/dist/cli/index.js" in dockerfile
    assert "LEGACY_PILOT_REPO_IMPORT_ROOT=/var/lib/legacy-pilot/repos" in dockerfile
    assert "USER legacy" in dockerfile
    assert "uvicorn" in dockerfile
    assert "legacy_pilot.middleware.app:app" in dockerfile


def test_frontend_dockerfile_builds_vite_and_serves_with_nginx():
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:22-alpine AS build" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "FROM nginx:1.27-alpine" in dockerfile
    assert "COPY nginx.conf /etc/nginx/conf.d/default.conf" in dockerfile
    assert "COPY --from=build /app/dist /usr/share/nginx/html" in dockerfile


def test_frontend_nginx_proxies_api_and_preserves_spa_fallback():
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "upstream legacy_pilot_api" in nginx
    assert "server api:8000;" in nginx
    assert "location /api/" in nginx
    assert "proxy_pass http://legacy_pilot_api/" in nginx
    assert "proxy_read_timeout 300s" in nginx
    assert "try_files $uri $uri/ /index.html" in nginx
    assert "location = /healthz" in nginx


def test_prod_compose_defines_real_web_api_postgres_stack():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"postgres", "api", "web"}.issubset(services)

    postgres = services["postgres"]
    assert postgres["image"] == "postgres:16-alpine"
    assert postgres["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U $${POSTGRES_USER:-legacy_pilot} -d $${POSTGRES_DB:-legacy_pilot}",
    ]
    assert "ports" not in postgres

    api = services["api"]
    assert api["build"]["dockerfile"] == "Dockerfile.api"
    assert api["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert api["environment"]["LEGACY_PILOT_CODE_CORE_BACKEND"] == "gitnexus_cli"
    assert api["environment"]["GITNEXUS_BIN"] == "/usr/local/bin/gitnexus"
    assert api["environment"]["GITNEXUS_REPO_ROOT"] == "/opt/gitnexus"
    assert api["environment"]["LEGACY_PILOT_GRAPH_STORE_BACKEND"] == "postgresql"
    assert api["environment"]["LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"] == "postgresql"
    assert api["environment"]["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
    assert api["environment"]["LEGACY_PILOT_REPO_IMPORT_ROOT"] == "/var/lib/legacy-pilot/repos"
    assert api["expose"] == ["8000"]
    assert "ports" not in api
    assert any(
        volume.get("target") == "/opt/gitnexus" and volume.get("read_only") is True
        for volume in api["volumes"]
        if isinstance(volume, dict)
    )

    web = services["web"]
    assert web["build"]["context"] == "./frontend"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert web["ports"] == ["8080:80"]


def test_prod_compose_smoke_script_checks_same_origin_api_health():
    script = (ROOT / "scripts" / "smoke-prod-compose.ps1").read_text(encoding="utf-8")

    assert "docker compose --env-file $EnvFile -f $ComposeFile up -d --build" in script
    assert "http://127.0.0.1:8080/api/health" in script
    assert "docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 web" in script
    assert "docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 api" in script


def test_readme_documents_dockerized_alibaba_cloud_deployment():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Dockerized deployment" in readme
    assert "docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build" in readme
    assert "GITNEXUS_REPO_ROOT" in readme
    assert "Alibaba Cloud ECS" in readme
    assert "ACR + ACK + RDS" in readme
    assert "DASHSCOPE_API_KEY" in readme


def _nonempty_lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values
