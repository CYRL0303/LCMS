from enum import StrEnum


class SourceType(StrEnum):
    CODE = "code"
    SQL = "sql"
    CONFIG = "config"
    LOG = "log"
    STACK_TRACE = "stack_trace"
    INCIDENT = "incident"
    DOCUMENT = "document"
    LLM_SEMANTIC_SUMMARY = "llm_semantic_summary"
    MANUAL_CONFIRMATION = "manual_confirmation"


class ExtractionMethod(StrEnum):
    TREE_SITTER = "tree_sitter"
    JAVA_PARSER = "java_parser"
    REGEX = "regex"
    VECTOR_RETRIEVAL = "vector_retrieval"
    LLM = "llm"
    MANUAL_CONFIRM = "manual_confirm"
    SYSTEM_GENERATED = "system_generated"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_CONTRACT_VERSION = "MISSING_CONTRACT_VERSION"
    UNSUPPORTED_CONTRACT_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    TRACE_REQUIRED = "TRACE_REQUIRED"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
    RESOURCE_IN_USE = "RESOURCE_IN_USE"
