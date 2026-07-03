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
    assert "GITNEXUS_SOURCE_ROOT" not in env_values
    assert env_values["GITNEXUS_RUNTIME_IMAGE"] == "legacy-pilot-gitnexus-runtime:local"
    assert env_values["LEGACY_PILOT_CODE_CORE_BACKEND"] == "gitnexus_cli"
    assert env_values["GITNEXUS_CYPHER_RETRY_EDGE_LIMIT"] == "100"
    assert env_values["LEGACY_PILOT_GRAPH_STORE_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND"] == "graph_context"
    assert env_values["LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"] == "postgresql"
    assert env_values["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
    assert env_values["LEGACY_PILOT_RCA_TIMEOUT_SECONDS"] == "120"
    assert env_values["LEGACY_PILOT_RCA_TRANSPORT_RETRIES"] == "1"
    assert env_values["LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS"] == "1"
    assert env_values["DASHSCOPE_API_KEY"] == ""
    assert "127.0.0.1" not in (ROOT / ".env.prod.example").read_text(
        encoding="utf-8"
    )


def test_gitnexus_runtime_dockerfile_builds_pinned_linux_runtime():
    dockerfile = (ROOT / "Dockerfile.gitnexus-runtime").read_text(encoding="utf-8")

    assert "# syntax=docker/dockerfile:" in dockerfile
    assert "FROM node:22-bookworm-slim" in dockerfile
    assert "ARG GITNEXUS_PACKAGE_DIR=gitnexus" in dockerfile
    assert "COPY vendor/gitnexus-source /opt/gitnexus-source" in dockerfile
    assert "git clone" not in dockerfile
    assert "git checkout" not in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "dist/cli/index.js" in dockerfile
    assert "lbugjs.node" in dockerfile
    assert "not a Linux ELF binary" in dockerfile
    assert "/usr/local/bin/gitnexus" in dockerfile
    assert "exec node /opt/gitnexus/dist/cli/index.js" in dockerfile


def test_vendored_gitnexus_source_contains_build_inputs():
    source_root = ROOT / "vendor" / "gitnexus-source"
    package_root = source_root / "gitnexus"

    assert (package_root / "package.json").is_file()
    assert (package_root / "package-lock.json").is_file()
    assert (source_root / "gitnexus-shared" / "package.json").is_file()


def test_api_dockerfile_copies_gitnexus_runtime_image_without_building_it():
    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")

    assert "# syntax=docker/dockerfile:" in dockerfile
    assert "ARG GITNEXUS_RUNTIME_IMAGE" in dockerfile
    assert "FROM ${GITNEXUS_RUNTIME_IMAGE} AS gitnexus-runtime" in dockerfile
    assert "FROM python:3.13-slim-bookworm" in dockerfile
    assert "COPY --from=gitnexus-runtime /opt/gitnexus /opt/gitnexus" in dockerfile
    assert "COPY --from=gitnexus-runtime /usr/local/bin/gitnexus /usr/local/bin/gitnexus" in dockerfile
    assert "COPY --from=gitnexus-runtime /usr/local/bin/node /usr/local/bin/node" in dockerfile
    assert "COPY --from=gitnexus_source" not in dockerfile
    assert "gitnexus-build" not in dockerfile
    assert "npm ci" not in dockerfile
    assert "npm run build" not in dockerfile
    assert "lbugjs.node" in dockerfile
    assert "not a Linux ELF binary" in dockerfile
    assert "apt-get install" in dockerfile
    assert " git " in dockerfile or " git\\" in dockerfile
    assert "/opt/gitnexus/dist/cli/index.js" in dockerfile
    assert "LEGACY_PILOT_REPO_IMPORT_ROOT=/var/lib/legacy-pilot/repos" in dockerfile
    assert "chown -R legacy:legacy /app /var/lib/legacy-pilot /opt/gitnexus" in dockerfile
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
    assert "additional_contexts" not in api["build"]
    assert api["build"]["args"]["GITNEXUS_RUNTIME_IMAGE"] == (
        "${GITNEXUS_RUNTIME_IMAGE:?GITNEXUS_RUNTIME_IMAGE is required}"
    )
    assert api["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert api["environment"]["LEGACY_PILOT_CODE_CORE_BACKEND"] == "gitnexus_cli"
    assert api["environment"]["GITNEXUS_BIN"] == "/usr/local/bin/gitnexus"
    assert api["environment"]["GITNEXUS_REPO_ROOT"] == "/opt/gitnexus"
    assert api["environment"]["LEGACY_PILOT_GRAPH_STORE_BACKEND"] == "postgresql"
    assert api["environment"]["LEGACY_PILOT_INCIDENT_MEMORY_BACKEND"] == "postgresql"
    assert api["environment"]["LEGACY_PILOT_RCA_BACKEND"] == "qwen_api"
    assert api["environment"]["LEGACY_PILOT_RCA_TIMEOUT_SECONDS"] == (
        "${LEGACY_PILOT_RCA_TIMEOUT_SECONDS:-120}"
    )
    assert api["environment"]["LEGACY_PILOT_RCA_TRANSPORT_RETRIES"] == (
        "${LEGACY_PILOT_RCA_TRANSPORT_RETRIES:-1}"
    )
    assert api["environment"]["LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS"] == (
        "${LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS:-1}"
    )
    assert api["environment"]["LEGACY_PILOT_REPO_IMPORT_ROOT"] == "/var/lib/legacy-pilot/repos"
    assert api["expose"] == ["8000"]
    assert "ports" not in api
    assert not any(
        isinstance(volume, dict) and volume.get("target") == "/opt/gitnexus"
        for volume in api["volumes"]
    )

    web = services["web"]
    assert web["build"]["context"] == "./frontend"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert web["ports"] == ["8080:80"]


def test_prod_compose_smoke_script_checks_same_origin_api_health():
    script = (ROOT / "scripts" / "smoke-prod-compose.ps1").read_text(encoding="utf-8")

    assert "Read-EnvFile" in script
    assert "Get-EnvValue" in script
    assert "GetEnvironmentVariable($Key, \"Process\")" in script
    assert "Invoke-CheckedCommand" in script
    assert "$LASTEXITCODE" in script
    assert "GITNEXUS_RUNTIME_IMAGE" in script
    assert "Test-GitNexusRuntimeImage" in script
    assert "GITNEXUS_SOURCE_ROOT" not in script
    assert "Test-GitNexusBuildSource" not in script
    assert '$composeArgs = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile)' in script
    assert 'Invoke-CheckedCommand "docker" ($composeArgs + @("up", "-d", "--build"))' in script
    assert 'Invoke-CheckedCommand "docker" ($composeArgs + @("exec", "-T", "api", "test", "-f", "/opt/gitnexus/dist/cli/index.js"))' in script
    assert "node_modules/@ladybugdb/core" in script
    assert "lbugjs.node" in script
    assert "gitnexus analyze /tmp/gitnexus-smoke-repo --skip-git --index-only --name docker-smoke" in script
    assert "http://127.0.0.1:8080/api/health" in script
    assert "docker @composeArgs logs --tail 120 web" in script
    assert "docker @composeArgs logs --tail 120 api" in script


def test_gitnexus_runtime_build_script_builds_and_optionally_pushes_acr_image():
    script = (ROOT / "scripts" / "build-gitnexus-runtime.ps1").read_text(
        encoding="utf-8"
    )

    assert "Dockerfile.gitnexus-runtime" in script
    assert "GITNEXUS_PACKAGE_DIR" in script
    assert "GITNEXUS_RUNTIME_IMAGE" in script
    assert '"--build-arg", "GITNEXUS_PACKAGE_DIR=$GitNexusPackageDir"' in script
    assert "& docker @buildArgs" in script
    assert "docker push $RuntimeImage" in script
    assert "GITNEXUS_REPO" not in script
    assert "GITNEXUS_REF" not in script


def test_readme_documents_dockerized_alibaba_cloud_deployment():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Dockerized deployment" in readme
    assert "Dockerfile.gitnexus-runtime" in readme
    assert "GITNEXUS_RUNTIME_IMAGE" in readme
    assert "docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build" in readme
    assert "docker build -f Dockerfile.gitnexus-runtime" in readme
    assert "docker push" in readme
    assert "vendor/gitnexus-source" in readme
    assert "builds the Linux GitNexus runtime in a separate image" in readme
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
