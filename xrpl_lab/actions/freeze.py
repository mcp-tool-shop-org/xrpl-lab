"""Token-freeze actions — the issuer's Individual & Global Freeze levers (FT-CURRIC-003).

Freeze is the sanction tier BELOW clawback: stop token movement without
destroying balances. Individual Freeze (TrustSet tfSetFreeze) locks one
holder's trust line; Global Freeze (AccountSet asfGlobalFreeze) halts every
token the issuer issues. Both are mainnet-live core features. Deep Freeze
(XLS-77d) is deliberately NOT taught here — it is not enabled on mainnet.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import FreezeStatus, SubmitResult, Transport


async def set_individual_freeze(
    transport: Transport,
    issuer_seed: str,
    holder: str,
    currency: str,
    freeze: bool,
    issuer_address: str = "",
) -> SubmitResult:
    """Freeze (or unfreeze) one holder's trust line for a currency."""
    return await transport.submit_set_freeze(
        issuer_seed, holder, currency, freeze, issuer_address
    )


async def set_global_freeze(
    transport: Transport,
    issuer_seed: str,
    enable: bool,
    issuer_address: str = "",
) -> SubmitResult:
    """Enable (or clear) Global Freeze on the issuer account."""
    return await transport.submit_global_freeze(issuer_seed, enable, issuer_address)


@dataclass
class FreezeVerifyResult:
    """Result of verifying freeze state on-ledger."""

    status: FreezeStatus
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_freeze(
    transport: Transport,
    issuer_address: str,
    holder: str,
    currency: str,
    expect_individual: bool | None = None,
    expect_global: bool | None = None,
) -> FreezeVerifyResult:
    """Read freeze state and confirm it matches the expected Individual/Global flags."""
    status = await transport.get_freeze_status(issuer_address, holder, currency)
    checks: list[str] = []
    failures: list[str] = []

    if expect_individual is not None:
        want = "ON" if expect_individual else "OFF"
        got = "ON" if status.individual_frozen else "OFF"
        if status.individual_frozen == expect_individual:
            checks.append(f"Individual freeze is {want} for the holder's {currency} line")
        else:
            failures.append(
                f"Individual freeze mismatch: expected {want}, got {got}"
            )

    if expect_global is not None:
        want = "ON" if expect_global else "OFF"
        got = "ON" if status.global_frozen else "OFF"
        if status.global_frozen == expect_global:
            checks.append(f"Global freeze is {want} on the issuer account")
        else:
            failures.append(f"Global freeze mismatch: expected {want}, got {got}")

    return FreezeVerifyResult(status, checks, failures)
