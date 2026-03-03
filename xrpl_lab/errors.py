"""Structured errors for XRPL Lab — Shipcheck Tier 2 error contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LabError:
    """Structured error shape — every user-facing error uses this."""

    code: str
    message: str
    hint: str
    cause: str | None = None
    retryable: bool = False

    def safe_dict(self) -> dict:
        """Return a dict safe for display (no stack traces)."""
        d: dict = {"code": self.code, "message": self.message, "hint": self.hint}
        if self.cause:
            d["cause"] = self.cause
        if self.retryable:
            d["retryable"] = True
        return d


class LabException(Exception):
    """Base exception with structured error data."""

    def __init__(self, error: LabError) -> None:
        self.error = error
        super().__init__(error.message)

    @property
    def exit_code(self) -> int:
        """Map error code prefix to CLI exit code."""
        prefix = self.error.code.split("_")[0] + "_"
        return _EXIT_CODES.get(prefix, 2)


# Exit code mapping: prefix → exit code
# 0 = ok, 1 = user error, 2 = runtime error, 3 = partial success
_EXIT_CODES: dict[str, int] = {
    "INPUT_": 1,
    "CONFIG_": 1,
    "STATE_": 1,
    "IO_": 2,
    "DEP_": 2,
    "RUNTIME_": 2,
    "PERM_": 2,
    "PARTIAL_": 3,
}


# ── Common error constructors ──────────────────────────────────────


def module_not_found(module_id: str) -> LabError:
    return LabError(
        code="INPUT_MODULE_NOT_FOUND",
        message=f"Module '{module_id}' not found.",
        hint="Run 'xrpl-lab list' to see available modules.",
    )


def no_wallet() -> LabError:
    return LabError(
        code="STATE_NO_WALLET",
        message="No wallet found.",
        hint="Run 'xrpl-lab wallet create' first.",
    )


def network_error(detail: str) -> LabError:
    return LabError(
        code="RUNTIME_NETWORK",
        message="Network request failed.",
        hint="Check your connection or use --dry-run for offline mode.",
        cause=detail,
        retryable=True,
    )


def corrupt_state(detail: str) -> LabError:
    return LabError(
        code="STATE_CORRUPT",
        message="State file is corrupted.",
        hint="Run 'xrpl-lab reset' to start fresh, or 'xrpl-lab doctor' to diagnose.",
        cause=detail,
    )


def tx_failed(result_code: str, detail: str = "") -> LabError:
    return LabError(
        code="RUNTIME_TX_FAILED",
        message=f"Transaction failed with result: {result_code}",
        hint="Check the result code reference in 'xrpl-lab doctor'.",
        cause=detail if detail else None,
    )
