import hashlib
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from legacy_pilot.contracts.runtime_credentials import current_runtime_credentials


REPO_IMPORT_ROOT_ENV = "LEGACY_PILOT_REPO_IMPORT_ROOT"
REPO_IMPORT_TIMEOUT_ENV = "LEGACY_PILOT_REPO_IMPORT_TIMEOUT_SECONDS"
DEFAULT_REPO_IMPORT_TIMEOUT_SECONDS = 120.0
_SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_AUTHORITY_RE = re.compile(r"://[^/@]+:[^/@]+@")


class RepoImportError(Exception):
    def __init__(self, message: str, *, diagnostics: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class ResolvedRepo:
    local_path: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteRepo:
    source: str
    repo_url: str
    clone_url: str


def resolve_repo_uri(
    repo_uri: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> ResolvedRepo:
    remote = _remote_repo(repo_uri)
    if remote is not None:
        return _import_remote_repo(remote, runner=runner or subprocess.run)
    return ResolvedRepo(local_path=_local_repo_path(repo_uri))


def _remote_repo(repo_uri: str) -> RemoteRepo | None:
    parsed = urlparse(repo_uri)
    if parsed.scheme.lower() != "https":
        return None
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "gitlab.com"}:
        raise RepoImportError(
            "Only https://github.com/<owner>/<repo> or "
            "https://gitlab.com/<group>/<repo> remote repo_uri values are supported.",
            diagnostics={"repo_uri": repo_uri},
        )
    if parsed.params or parsed.query or parsed.fragment:
        raise RepoImportError(
            "Remote repo_uri must not include params, query, or fragment.",
            diagnostics={"repo_uri": repo_uri},
        )
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if host == "github.com":
        return _github_remote(parts, repo_uri)
    return _gitlab_remote(parts, repo_uri)


def _github_remote(parts: list[str], repo_uri: str) -> RemoteRepo:
    if len(parts) != 2:
        raise RepoImportError(
            "GitHub repo_uri must use https://github.com/<owner>/<repo>.",
            diagnostics={"repo_uri": repo_uri},
        )
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        raise RepoImportError(
            "GitHub repo_uri must include both owner and repo.",
            diagnostics={"repo_uri": repo_uri},
        )
    repo_url = f"https://github.com/{owner}/{repo}.git"
    token = current_runtime_credentials().github_token
    return RemoteRepo(
        source="github",
        repo_url=repo_url,
        clone_url=_authenticated_url(repo_url, username="x-access-token", token=token),
    )


def _gitlab_remote(parts: list[str], repo_uri: str) -> RemoteRepo:
    if len(parts) < 2:
        raise RepoImportError(
            "GitLab repo_uri must use https://gitlab.com/<group>/<repo>.",
            diagnostics={"repo_uri": repo_uri},
        )
    repo = parts[-1].removesuffix(".git")
    group_parts = parts[:-1]
    if not repo or any(not part for part in group_parts):
        raise RepoImportError(
            "GitLab repo_uri must include both group path and repo.",
            diagnostics={"repo_uri": repo_uri},
        )
    repo_path = "/".join([*group_parts, repo])
    repo_url = f"https://gitlab.com/{repo_path}.git"
    token = current_runtime_credentials().gitlab_token
    return RemoteRepo(
        source="gitlab",
        repo_url=repo_url,
        clone_url=_authenticated_url(repo_url, username="oauth2", token=token),
    )


def _import_remote_repo(
    remote: RemoteRepo,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> ResolvedRepo:
    destination = _remote_destination(remote.repo_url)
    if destination.exists():
        if not (destination / ".git").exists():
            raise RepoImportError(
                "Remote import destination exists but is not a git repository.",
                diagnostics={"repo_uri": remote.repo_url, "repo_path": str(destination)},
            )
        return ResolvedRepo(
            local_path=str(destination),
            metadata=_remote_metadata(remote, destination, imported=False),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--",
        remote.clone_url,
        str(destination),
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=_import_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RepoImportError(
            "Remote repo import timed out.",
            diagnostics={"repo_uri": remote.repo_url, "timeout_seconds": str(exc.timeout)},
        ) from exc
    except OSError as exc:
        raise RepoImportError(
            "Remote repo import failed before git clone completed.",
            diagnostics={"repo_uri": remote.repo_url, "error_type": exc.__class__.__name__},
        ) from exc
    if completed.returncode != 0:
        raise RepoImportError(
            "Remote repo import failed.",
            diagnostics={
                "repo_uri": remote.repo_url,
                "returncode": str(completed.returncode),
                "stderr": _redact_remote_secret(completed.stderr or "", remote)[:2000],
            },
        )
    return ResolvedRepo(
        local_path=str(destination),
        metadata=_remote_metadata(remote, destination, imported=True),
    )


def _remote_destination(repo_url: str) -> Path:
    parsed = urlparse(repo_url)
    repo_path = parsed.path.strip("/").removesuffix(".git")
    slug = _safe_slug(f"{parsed.hostname or 'remote'}-{repo_path}")
    digest = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:12]
    return _import_root() / f"{slug}-{digest}"


def _remote_metadata(
    remote: RemoteRepo, destination: Path, *, imported: bool
) -> dict[str, object]:
    return {
        "repo_import": {
            "source": remote.source,
            "repo_url": remote.repo_url,
            "local_path": str(destination),
            "imported": imported,
        }
    }


def _authenticated_url(repo_url: str, *, username: str, token: str | None) -> str:
    if not token:
        return repo_url
    parsed = urlparse(repo_url)
    authority = f"{username}:{token}@{parsed.netloc}"
    return parsed._replace(netloc=authority).geturl()


def _redact_remote_secret(value: str, remote: RemoteRepo) -> str:
    redacted = value.replace(remote.clone_url, remote.repo_url)
    return _AUTHORITY_RE.sub("://<redacted>@", redacted)


def _import_root() -> Path:
    configured = os.getenv(REPO_IMPORT_ROOT_ENV)
    root = Path(configured) if configured else Path(tempfile.gettempdir()) / "legacy-pilot-repos"
    return root.resolve()


def _import_timeout_seconds() -> float:
    configured = os.getenv(REPO_IMPORT_TIMEOUT_ENV)
    if not configured:
        return DEFAULT_REPO_IMPORT_TIMEOUT_SECONDS
    try:
        parsed = float(configured)
    except ValueError:
        return DEFAULT_REPO_IMPORT_TIMEOUT_SECONDS
    return max(parsed, 1.0)


def _local_repo_path(repo_uri: str) -> str:
    if _looks_like_windows_path(repo_uri):
        return repo_uri
    parsed = urlparse(repo_uri)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError("repo_uri is not a local path")
    if parsed.scheme == "file" and parsed.netloc not in {"", "localhost"}:
        raise ValueError("repo_uri is not a local path")
    return _repo_path(repo_uri)


def _repo_path(repo_uri: str) -> str:
    if repo_uri.startswith("file://"):
        from urllib.parse import unquote

        parsed = urlparse(repo_uri)
        path = unquote(parsed.path)
        if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
            return path[1:]
        return path
    return repo_uri


def _looks_like_windows_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha()


def _safe_slug(value: str) -> str:
    slug = _SAFE_SLUG_RE.sub("-", value).strip(".-")
    return slug[:80] or "repo"
