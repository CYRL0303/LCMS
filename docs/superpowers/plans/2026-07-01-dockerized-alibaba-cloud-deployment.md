# Dockerized Alibaba Cloud Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real Docker deployment path for LegacyPilot's frontend, interface middleware, GitNexus-backed Structure 1, Qwen-backed Structure 3, and PostgreSQL-backed graph/incident stores, then document how to run it locally and on Alibaba Cloud.

**Architecture:** Use a three-service production Compose stack first: `web` serves the built Vite app through Nginx, `api` runs FastAPI/Uvicorn plus a real mounted GitNexus runtime, and `postgres` stores graph payloads plus incident memory. Keep `/api` same-origin at the web layer so the browser does not need CORS in the default deployment. Alibaba Cloud MVP maps this stack to ECS + Docker Compose; later product deployment maps the same images to ACR + ACK + RDS PostgreSQL + SLB/Ingress.

**Tech Stack:** Docker, Docker Compose, Python 3.13, FastAPI, Uvicorn, psycopg, Node.js for GitNexus CLI execution, React 19, Vite, Nginx, PostgreSQL 16, Alibaba Cloud ECS/ACR/ACK/RDS/SLB.

---

## Current Facts

- `docker-compose.e2e.yml` only runs PostgreSQL for local E2E.
- `frontend/vite.config.ts` provides a dev-only `/api` proxy; production needs an Nginx `/api` reverse proxy.
- `legacy_pilot.middleware.app:app` is the API entry point.
- Structure 1 uses `LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli`.
- GitNexus is currently external to this repo and invoked through `GITNEXUS_BIN` plus `GITNEXUS_REPO_ROOT`.
- Structure 3 uses real Qwen through `LEGACY_PILOT_RCA_BACKEND=qwen_api`.
- Structure 4 production factory only allows PostgreSQL incident memory.
- Graph payloads and incident memory can share one PostgreSQL database with separate tables.

## File Structure

- Create `tests/test_docker_deployment_config.py`: locked regression tests for Dockerfiles, production compose, env docs, and deployment README content.
- Modify `pyproject.toml`: add setuptools build metadata so the API image can install the package cleanly.
- Modify `.gitignore`: keep private `.env.prod` ignored while allowing `.env.prod.example`.
- Create `.dockerignore`: keep secrets, VCS metadata, caches, logs, and generated reports out of the API image build context.
- Create `.env.prod.example`: runnable Compose env sample with no real secrets committed.
- Create `Dockerfile.api`: Python API image with Git, Node.js, non-root user, Uvicorn entry point, and a wrapper that executes a mounted real GitNexus CLI.
- Create `frontend/.dockerignore`: keep frontend build context small.
- Create `frontend/Dockerfile`: Vite build stage plus Nginx runtime stage.
- Create `frontend/nginx.conf`: static SPA serving, `/api` reverse proxy, health endpoint, and long API timeouts.
- Create `docker-compose.prod.yml`: production-like local/ECS stack for `postgres`, `api`, and `web`.
- Create `scripts/smoke-prod-compose.ps1`: build and smoke-test the production Compose stack.
- Modify `README.md`: add Docker/ECS/ACK/RDS deployment instructions and operational notes.

## GitNexus Packaging Decision

P0 uses a real mounted GitNexus runtime instead of vendoring GitNexus into this repository:

- Local Windows example: set `GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus`.
- ECS example: clone/build GitNexus on the host at `/opt/legacy-pilot/gitnexus`, then set `GITNEXUS_REPO_ROOT=/opt/legacy-pilot/gitnexus`.
- API container mounts that path read-only at `/opt/gitnexus`.
- API container wrapper runs `node /opt/gitnexus/dist/cli/index.js`.

This keeps the chain real and avoids adding a fake GitNexus service. A self-contained API image or separate GitNexus service can be added after GitNexus has a stable package/release strategy.

---

### Task 1: Add Docker Deployment Config Tests

**Files:**
- Create: `tests/test_docker_deployment_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_docker_deployment_config.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py -q
```

Expected: FAIL because `Dockerfile.api`, `.dockerignore`, `.env.prod.example`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.prod.yml`, and `scripts/smoke-prod-compose.ps1` do not exist yet.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add tests/test_docker_deployment_config.py
git commit -m "test: cover docker deployment config"
```

---

### Task 2: Add Packaging Metadata, Ignore Rules, and Production Env Example

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `.dockerignore`
- Create: `.env.prod.example`

- [ ] **Step 1: Add package build metadata to `pyproject.toml`**

Append this exact content to `pyproject.toml`:

```toml

[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["legacy_pilot*"]
```

- [ ] **Step 2: Allow the production env example in `.gitignore`**

Add this line next to `!.env.example`:

```gitignore
!.env.prod.example
```

Keep private env files ignored:

```gitignore
.env
.env.*
.env.local
.env.prod
!.env.example
!.env.prod.example
```

- [ ] **Step 3: Create root `.dockerignore`**

Create `.dockerignore`:

```dockerignore
.git
.agents
.claude
.codex
.pytest_cache
.playwright
.playwright-cli
.playwright-cli-cache
.tmp
.worktrees
.e2e-artifacts
playwright-report
test-results

.env
.env.*
!.env.example
!.env.prod.example

**/__pycache__
**/*.pyc
**/*.pyo
**/*.pyd
*.log

frontend/node_modules
frontend/dist
frontend/.vite
node_modules
dist
coverage
```

- [ ] **Step 4: Create `.env.prod.example`**

Create `.env.prod.example`:

```dotenv
# Copy to .env.prod for ECS or local production-like Compose runs.
# Keep .env.prod private. Do not commit real secrets.

POSTGRES_USER=legacy_pilot
POSTGRES_PASSWORD=legacy_pilot_dev_password
POSTGRES_DB=legacy_pilot

# Path on the Docker host. Compose mounts this path read-only into /opt/gitnexus.
# Local Windows example can use Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus.
# ECS example can use /opt/legacy-pilot/gitnexus.
GITNEXUS_REPO_ROOT=./.runtime/gitnexus

LEGACY_PILOT_CODE_CORE_BACKEND=gitnexus_cli
LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE=1
LEGACY_PILOT_MAX_GRAPH_NODES=5000
LEGACY_PILOT_MAX_GRAPH_EDGES=10000
GITNEXUS_TIMEOUT_SECONDS=60
GITNEXUS_INDEX_TIMEOUT_SECONDS=120
GITNEXUS_QUERY_TIMEOUT_SECONDS=30

LEGACY_PILOT_GRAPH_STORE_BACKEND=postgresql
LEGACY_PILOT_GRAPH_STORE_TABLE=legacy_pilot_graph_payloads

LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND=graph_context

LEGACY_PILOT_INCIDENT_MEMORY_BACKEND=postgresql
LEGACY_PILOT_INCIDENT_MEMORY_TABLE=legacy_pilot_incident_records

LEGACY_PILOT_RCA_BACKEND=qwen_api
LEGACY_PILOT_RCA_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
LEGACY_PILOT_RCA_MODEL=qwen-plus
LEGACY_PILOT_RCA_CONFIDENCE_CAP=0.75
LEGACY_PILOT_RCA_REPAIR_ATTEMPTS=2
DASHSCOPE_API_KEY=

LEGACY_PILOT_REPO_IMPORT_ROOT=/var/lib/legacy-pilot/repos
LEGACY_PILOT_REPO_IMPORT_TIMEOUT_SECONDS=120
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_pyproject_declares_build_backend_for_container_install tests/test_docker_deployment_config.py::test_gitignore_allows_prod_env_example_but_blocks_private_prod_env tests/test_docker_deployment_config.py::test_root_dockerignore_excludes_secrets_and_generated_artifacts tests/test_docker_deployment_config.py::test_prod_env_example_documents_real_backends_without_localhost_dsns -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml .gitignore .dockerignore .env.prod.example tests/test_docker_deployment_config.py
git commit -m "chore: add production docker env config"
```

---

### Task 3: Add API Dockerfile with Real GitNexus Runtime Mount

**Files:**
- Create: `Dockerfile.api`

- [ ] **Step 1: Create `Dockerfile.api`**

Create `Dockerfile.api`:

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LEGACY_PILOT_REPO_IMPORT_ROOT=/var/lib/legacy-pilot/repos

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY legacy_pilot ./legacy_pilot

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'exec node /opt/gitnexus/dist/cli/index.js "$@"' \
    > /usr/local/bin/gitnexus \
    && chmod +x /usr/local/bin/gitnexus

RUN useradd --create-home --shell /usr/sbin/nologin legacy \
    && mkdir -p /var/lib/legacy-pilot/repos \
    && chown -R legacy:legacy /app /var/lib/legacy-pilot

USER legacy

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()"

CMD ["python", "-m", "uvicorn", "legacy_pilot.middleware.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Run API Dockerfile test**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_api_dockerfile_runs_real_gitnexus_wrapper_as_non_root -q
```

Expected: PASS.

- [ ] **Step 3: Build the API image**

Run:

```powershell
docker build -f Dockerfile.api -t legacy-pilot-api:local .
```

Expected: image builds successfully.

- [ ] **Step 4: Commit**

Run:

```powershell
git add Dockerfile.api tests/test_docker_deployment_config.py
git commit -m "feat: add api docker image"
```

---

### Task 4: Add Frontend Dockerfile and Nginx Reverse Proxy

**Files:**
- Create: `frontend/.dockerignore`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Create `frontend/.dockerignore`**

Create `frontend/.dockerignore`:

```dockerignore
node_modules
dist
.vite
coverage
playwright-report
test-results
*.log
.env
.env.*
```

- [ ] **Step 2: Create `frontend/Dockerfile`**

Create `frontend/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
ARG VITE_LEGACY_PILOT_API_BASE=/api
ENV VITE_LEGACY_PILOT_API_BASE=${VITE_LEGACY_PILOT_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=12 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
```

- [ ] **Step 3: Create `frontend/nginx.conf`**

Create `frontend/nginx.conf`:

```nginx
upstream legacy_pilot_api {
    server api:8000;
}

server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location = /healthz {
        add_header Content-Type text/plain;
        return 200 "ok\n";
    }

    location /api/ {
        proxy_pass http://legacy_pilot_api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Run frontend Docker tests**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_frontend_dockerfile_builds_vite_and_serves_with_nginx tests/test_docker_deployment_config.py::test_frontend_nginx_proxies_api_and_preserves_spa_fallback -q
```

Expected: PASS.

- [ ] **Step 5: Build the frontend image**

Run:

```powershell
docker build -t legacy-pilot-web:local ./frontend
```

Expected: image builds successfully.

- [ ] **Step 6: Commit**

Run:

```powershell
git add frontend/.dockerignore frontend/Dockerfile frontend/nginx.conf tests/test_docker_deployment_config.py
git commit -m "feat: add frontend docker image"
```

---

### Task 5: Add Production Compose Stack

**Files:**
- Create: `docker-compose.prod.yml`

- [ ] **Step 1: Create `docker-compose.prod.yml`**

Create `docker-compose.prod.yml`:

```yaml
name: legacy-pilot-prod

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-legacy_pilot}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: ${POSTGRES_DB:-legacy_pilot}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - legacy-pilot-internal
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "pg_isready -U $${POSTGRES_USER:-legacy_pilot} -d $${POSTGRES_DB:-legacy_pilot}",
        ]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      LEGACY_PILOT_CODE_CORE_BACKEND: gitnexus_cli
      LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE: ${LEGACY_PILOT_GITNEXUS_FORCE_ANALYZE:-1}
      LEGACY_PILOT_MAX_GRAPH_NODES: ${LEGACY_PILOT_MAX_GRAPH_NODES:-5000}
      LEGACY_PILOT_MAX_GRAPH_EDGES: ${LEGACY_PILOT_MAX_GRAPH_EDGES:-10000}
      GITNEXUS_BIN: /usr/local/bin/gitnexus
      GITNEXUS_REPO_ROOT: /opt/gitnexus
      GITNEXUS_TIMEOUT_SECONDS: ${GITNEXUS_TIMEOUT_SECONDS:-60}
      GITNEXUS_INDEX_TIMEOUT_SECONDS: ${GITNEXUS_INDEX_TIMEOUT_SECONDS:-120}
      GITNEXUS_QUERY_TIMEOUT_SECONDS: ${GITNEXUS_QUERY_TIMEOUT_SECONDS:-30}
      LEGACY_PILOT_GRAPH_STORE_BACKEND: postgresql
      LEGACY_PILOT_GRAPH_STORE_DSN: "postgresql://${POSTGRES_USER:-legacy_pilot}:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/${POSTGRES_DB:-legacy_pilot}?connect_timeout=5"
      LEGACY_PILOT_GRAPH_STORE_TABLE: ${LEGACY_PILOT_GRAPH_STORE_TABLE:-legacy_pilot_graph_payloads}
      LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND: graph_context
      LEGACY_PILOT_INCIDENT_MEMORY_BACKEND: postgresql
      LEGACY_PILOT_INCIDENT_MEMORY_DSN: "postgresql://${POSTGRES_USER:-legacy_pilot}:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/${POSTGRES_DB:-legacy_pilot}?connect_timeout=5"
      LEGACY_PILOT_INCIDENT_MEMORY_TABLE: ${LEGACY_PILOT_INCIDENT_MEMORY_TABLE:-legacy_pilot_incident_records}
      LEGACY_PILOT_RCA_BACKEND: qwen_api
      LEGACY_PILOT_RCA_BASE_URL: ${LEGACY_PILOT_RCA_BASE_URL:-https://dashscope-intl.aliyuncs.com/compatible-mode/v1}
      LEGACY_PILOT_RCA_MODEL: ${LEGACY_PILOT_RCA_MODEL:-qwen-plus}
      LEGACY_PILOT_RCA_CONFIDENCE_CAP: ${LEGACY_PILOT_RCA_CONFIDENCE_CAP:-0.75}
      LEGACY_PILOT_RCA_REPAIR_ATTEMPTS: ${LEGACY_PILOT_RCA_REPAIR_ATTEMPTS:-2}
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:?DASHSCOPE_API_KEY is required}
      LEGACY_PILOT_REPO_IMPORT_ROOT: /var/lib/legacy-pilot/repos
      LEGACY_PILOT_REPO_IMPORT_TIMEOUT_SECONDS: ${LEGACY_PILOT_REPO_IMPORT_TIMEOUT_SECONDS:-120}
    volumes:
      - repo-cache:/var/lib/legacy-pilot/repos
      - type: bind
        source: ${GITNEXUS_REPO_ROOT:?GITNEXUS_REPO_ROOT is required}
        target: /opt/gitnexus
        read_only: true
    expose:
      - "8000"
    networks:
      - legacy-pilot-internal
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()",
        ]
      interval: 10s
      timeout: 5s
      start_period: 20s
      retries: 12

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "8080:80"
    networks:
      - legacy-pilot-internal
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      start_period: 10s
      retries: 12

volumes:
  postgres-data:
  repo-cache:

networks:
  legacy-pilot-internal:
    driver: bridge
```

- [ ] **Step 2: Run Compose config validation**

Create a private `.env.prod` from `.env.prod.example`, then set `DASHSCOPE_API_KEY` and `GITNEXUS_REPO_ROOT` to real local values.

Run:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml config
```

Expected: rendered config prints `postgres`, `api`, and `web` services with no interpolation errors.

- [ ] **Step 3: Run Compose test**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_prod_compose_defines_real_web_api_postgres_stack -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docker-compose.prod.yml tests/test_docker_deployment_config.py
git commit -m "feat: add production compose stack"
```

---

### Task 6: Add Production Compose Smoke Script

**Files:**
- Create: `scripts/smoke-prod-compose.ps1`

- [ ] **Step 1: Create `scripts/smoke-prod-compose.ps1`**

Create `scripts/smoke-prod-compose.ps1`:

```powershell
param(
    [string]$ComposeFile = "docker-compose.prod.yml",
    [string]$EnvFile = ".env.prod",
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

docker compose --env-file $EnvFile -f $ComposeFile up -d --build

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$healthUrl = "http://127.0.0.1:8080/api/health"

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 5
        if ($response.StatusCode -eq 200 -and $response.Content -match "legacy-pilot-interface-contract-middleware") {
            Write-Host "Production Compose smoke passed: $healthUrl"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

docker compose --env-file $EnvFile -f $ComposeFile ps
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 web
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 api
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 postgres

throw "Production Compose smoke failed: $healthUrl"
```

- [ ] **Step 2: Run script test**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_prod_compose_smoke_script_checks_same_origin_api_health -q
```

Expected: PASS.

- [ ] **Step 3: Run smoke test**

Run:

```powershell
.\scripts\smoke-prod-compose.ps1 -TimeoutSeconds 240
```

Expected: `Production Compose smoke passed: http://127.0.0.1:8080/api/health`.

- [ ] **Step 4: Commit**

Run:

```powershell
git add scripts/smoke-prod-compose.ps1 tests/test_docker_deployment_config.py
git commit -m "test: add production compose smoke"
```

---

### Task 7: Document Dockerized Alibaba Cloud Deployment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README section**

Add this section after the current local E2E instructions in `README.md`:

````markdown
## Dockerized deployment

The production-like Docker path runs the real chain:

```text
web container
-> /api reverse proxy
-> api container
-> gitnexus_cli mounted at /opt/gitnexus
-> PostgreSQL graph payload store
-> graph_context evidence builder
-> qwen_api RCA generation
-> PostgreSQL incident memory store
```

Create a private env file:

```powershell
Copy-Item .env.prod.example .env.prod
```

Set these private values in `.env.prod`:

```dotenv
DASHSCOPE_API_KEY=
GITNEXUS_REPO_ROOT=Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus
```

`GITNEXUS_REPO_ROOT` must point to a real GitNexus runtime with `dist/cli/index.js`.
The API container mounts that directory read-only at `/opt/gitnexus` and executes
it through `/usr/local/bin/gitnexus`. This is a real GitNexus CLI path, not a mock.

Run the stack:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Open:

```text
http://127.0.0.1:8080
```

Smoke test:

```powershell
.\scripts\smoke-prod-compose.ps1 -TimeoutSeconds 240
```

Stop:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

Keep data:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down
```

Delete local database and repo cache:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml down -v
```

### Alibaba Cloud ECS

Fast hackathon deployment:

1. Create an Alibaba Cloud ECS instance with Docker and Docker Compose.
2. Clone this repository on the ECS instance.
3. Clone/build GitNexus on the ECS instance at `/opt/legacy-pilot/gitnexus`.
4. Copy `.env.prod.example` to `.env.prod`.
5. Set `DASHSCOPE_API_KEY` and `GITNEXUS_REPO_ROOT=/opt/legacy-pilot/gitnexus`.
6. Run `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`.
7. Put Nginx/Caddy/SLB in front of port `8080` and expose HTTPS only.

For hackathon demo, the bundled PostgreSQL container can use an ECS cloud disk
volume. For durable product data, use RDS PostgreSQL and point both
`LEGACY_PILOT_GRAPH_STORE_DSN` and `LEGACY_PILOT_INCIDENT_MEMORY_DSN` at the RDS
internal endpoint through a Compose override or ACK Secret.

### Alibaba Cloud product path

Production path:

- Build `legacy-pilot-api` and `legacy-pilot-web` images in CI.
- Push images to Alibaba Cloud ACR.
- Run `api` and `web` as ACK Deployments.
- Use RDS PostgreSQL for graph payloads and incident memory.
- Use SLB/Ingress for HTTPS.
- Store `DASHSCOPE_API_KEY`, GitHub/GitLab tokens, and PostgreSQL passwords in
  Alibaba Cloud Secret Manager or Kubernetes Secrets.
- Store repo clone cache on NAS/PVC, or keep it ephemeral with a cleanup policy.
- Send container logs to Alibaba Cloud SLS.

Network rule:

- Public: only HTTPS to `web`.
- Internal: `web -> api:8000`, `api -> PostgreSQL`.
- Outbound: DashScope, GitHub, GitLab, and remote Git clone endpoints.
````

- [ ] **Step 2: Run README test**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py::test_readme_documents_dockerized_alibaba_cloud_deployment -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```powershell
git add README.md tests/test_docker_deployment_config.py
git commit -m "docs: document dockerized deployment"
```

---

### Task 8: Verify Full Deployment Work

**Files:**
- No new files.

- [ ] **Step 1: Run config tests**

Run:

```powershell
python -m pytest tests/test_docker_deployment_config.py -q
```

Expected: PASS.

- [ ] **Step 2: Run existing non-external suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with the existing external integration tests skipped unless their opt-in env vars are set.

- [ ] **Step 3: Build frontend outside Docker**

Run:

```powershell
cd frontend
npm run build
cd ..
```

Expected: Vite build passes.

- [ ] **Step 4: Validate Compose rendering**

Run:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml config
```

Expected: rendered YAML includes `legacy-pilot-prod-postgres`, `legacy-pilot-prod-api`, and `legacy-pilot-prod-web` resources with no missing variable errors.

- [ ] **Step 5: Smoke-test real containers**

Run:

```powershell
.\scripts\smoke-prod-compose.ps1 -TimeoutSeconds 240
```

Expected: `Production Compose smoke passed: http://127.0.0.1:8080/api/health`.

- [ ] **Step 6: Manually verify browser**

Open:

```text
http://127.0.0.1:8080
```

Expected:

- Page renders `Incident Workbench`.
- Health button reports real backends.
- Existing graph dropdown loads from PostgreSQL through `/api/v1/graphs`.
- Running with an existing graph can build evidence and generate RCA with a real Qwen key.
- Saving incident writes to PostgreSQL incident memory.

- [ ] **Step 7: Commit final adjustments**

Run:

```powershell
git status --short
git add -A
git commit -m "feat: dockerize legacy pilot deployment"
```

---

## RDS Follow-Up

After ECS Compose works with container PostgreSQL, add one of these paths:

1. Compose override file `docker-compose.rds.yml` that removes the `postgres` service and injects RDS DSNs.
2. ACK manifests or Helm chart that sets DSNs from Kubernetes Secrets.

RDS DSN shape:

```dotenv
LEGACY_PILOT_GRAPH_STORE_DSN=postgresql://legacy_pilot:legacy_pilot_rds_password@legacy-pilot-postgres.rds.aliyuncs.internal:5432/legacy_pilot?connect_timeout=5
LEGACY_PILOT_INCIDENT_MEMORY_DSN=postgresql://legacy_pilot:legacy_pilot_rds_password@legacy-pilot-postgres.rds.aliyuncs.internal:5432/legacy_pilot?connect_timeout=5
```

Keep RDS on private VPC networking. Do not expose PostgreSQL publicly.

## Risks and Controls

- GitNexus runtime path missing: Compose fails loudly because `GITNEXUS_REPO_ROOT` is required.
- Qwen key missing: Compose fails loudly because `DASHSCOPE_API_KEY` is required.
- API returning `index.html`: Nginx has an explicit `/api/` block before SPA fallback.
- API calls timing out: Nginx proxy timeout is `300s`; backend GitNexus/Qwen timeouts remain env-configurable.
- Secrets in images: `.dockerignore` excludes `.env*`; secrets are env/secret only.
- Untrusted repo analysis: API image runs non-root and only mounts repo cache plus read-only GitNexus runtime.
- PostgreSQL data loss on local cleanup: `down` preserves volumes; `down -v` deletes local database and repo cache.

## Self-Review

- Spec coverage: plan covers frontend, API, GitNexus runtime, PostgreSQL graph store, incident memory store, Qwen env, ECS, ACK/ACR/RDS, smoke testing, and README.
- No mock path added: `gitnexus_cli`, `graph_context`, `qwen_api`, and `postgresql` remain the production backends.
- No in-memory Structure 4 path added: incident memory env remains `postgresql`.
- Type and path consistency: `GITNEXUS_BIN=/usr/local/bin/gitnexus`, `GITNEXUS_REPO_ROOT=/opt/gitnexus`, repo cache `/var/lib/legacy-pilot/repos`, and web proxy `/api -> api:8000` are used consistently.
- Test coverage: config tests validate file content; smoke script validates same-origin `/api/health`; manual browser check validates frontend behavior.
