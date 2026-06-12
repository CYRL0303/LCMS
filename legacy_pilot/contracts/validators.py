from legacy_pilot.contracts.enums import ErrorCode
from legacy_pilot.contracts.errors import ContractError, ContractViolation

SUPPORTED_CONTRACT_VERSION = "1.0.0"
SUPPORTED_MAJOR_VERSION = 1


def ensure_supported_contract_version(
    contract_version: str | None,
    *,
    trace_id: str | None = None,
    source_module: str = "interface_contract_middleware",
) -> None:
    if not contract_version:
        raise ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.MISSING_CONTRACT_VERSION,
                message="contract_version is required for cross-structure requests.",
                source_module=source_module,
                recoverable=True,
                missing_fields=["contract_version"],
            )
        )

    major_part = contract_version.removeprefix("v").split(".", maxsplit=1)[0]
    try:
        major = int(major_part)
    except ValueError as exc:
        raise ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.UNSUPPORTED_CONTRACT_VERSION,
                message=f"Unsupported contract_version: {contract_version}",
                source_module=source_module,
                recoverable=False,
            )
        ) from exc

    if major != SUPPORTED_MAJOR_VERSION:
        raise ContractViolation(
            ContractError(
                trace_id=trace_id,
                error_code=ErrorCode.UNSUPPORTED_CONTRACT_VERSION,
                message=f"Unsupported contract_version: {contract_version}",
                source_module=source_module,
                recoverable=False,
            )
        )
