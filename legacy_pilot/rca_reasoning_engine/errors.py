from legacy_pilot.contracts.enums import ErrorCode


SOURCE_MODULE = "rca_reasoning_engine"


class RCAReasoningEngineError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = ErrorCode.VALIDATION_ERROR,
        recoverable: bool = True,
        missing_fields: list[str] | None = None,
        diagnostics: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.recoverable = recoverable
        self.source_module = SOURCE_MODULE
        self.missing_fields = missing_fields or []
        self.diagnostics = diagnostics or {}


class RCAGenerationError(RCAReasoningEngineError):
    pass


class RCAReviewError(RCAReasoningEngineError):
    pass


class RCAEvidenceRequiredError(RCAReasoningEngineError):
    def __init__(self, message: str):
        super().__init__(
            message,
            error_code=ErrorCode.EVIDENCE_REQUIRED,
            recoverable=True,
        )
