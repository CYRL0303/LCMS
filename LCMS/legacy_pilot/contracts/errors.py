from pydantic import BaseModel, Field


class ContractError(BaseModel):
    trace_id: str | None = None
    error_code: str
    message: str
    source_module: str
    recoverable: bool
    missing_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ContractViolation(Exception):
    def __init__(self, error: ContractError):
        super().__init__(error.message)
        self.error = error
