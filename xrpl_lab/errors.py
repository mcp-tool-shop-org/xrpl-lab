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

    def safe_dict(self) -> dict[str, object]:
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
        hint="Create one first: xrpl-lab wallet create",
    )


def network_error(detail: str) -> LabError:
    return LabError(
        code="RUNTIME_NETWORK",
        message="Network request failed.",
        hint="Check your connection, or use --dry-run to work offline.",
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
        message=f"Transaction failed: {result_code}",
        hint="Check the result code in the XRPL documentation, or run 'xrpl-lab doctor'.",
        cause=detail if detail else None,
    )


def faucet_rate_limited() -> LabError:
    """Faucet 429 — distinct code so dashboards can route to a specific UI.

    Surfaces alongside the existing humanized prose in
    ``transport.xrpl_testnet.fund_from_faucet``; the prose still teaches
    WHY (abuse prevention) and the fallback (--dry-run). The structured
    code lets the Frontend distinguish "rate-limited, retry or use
    --dry-run" from a generic ``RUNTIME_NETWORK`` failure so the
    dashboard can render a clock icon and a wait/retry-cued banner
    rather than the generic alert-triangle.
    """
    return LabError(
        code="RUNTIME_FAUCET_RATE_LIMITED",
        message="Faucet rate-limited (HTTP 429).",
        hint=(
            "The testnet faucet caps funding requests to keep test XRP "
            "available for everyone. Wait at least 60 seconds before "
            "retrying, or use --dry-run to practice this module offline "
            "without needing a funded testnet wallet."
        ),
        retryable=True,
    )
