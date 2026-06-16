SOURCE_MODULE = "code_knowledge_core"


class CodeKnowledgeCoreError(Exception):
    """Base exception for Code Knowledge Core internal errors.

    Carries enough data for MiddlewareRouter to convert into a
    ContractError envelope without leaking internal stack traces.
    """

    def __init__(
        self,
        message: str,
        *,
        recoverable: bool = True,
        diagnostics: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable
        self.source_module = SOURCE_MODULE
        self.diagnostics = diagnostics or {}


class IndexingError(CodeKnowledgeCoreError):
    """Repo indexing failed (e.g. unreadable source, parse timeout)."""


class QueryError(CodeKnowledgeCoreError):
    """Graph query failed (e.g. backend unavailable, invalid graph id)."""
