"""Escrow actions — create a time-based XRP escrow and verify it on-ledger."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import EscrowInfo, SubmitResult, Transport


async def create_escrow(
    transport: Transport,
    wallet_seed: str,
    amount: str,
    destination: str,
    finish_after: int,
    cancel_after: int | None = None,
) -> SubmitResult:
    """Create a time-based XRP escrow (EscrowCreate)."""
    return await transport.submit_escrow_create(
        wallet_seed, amount, destination, finish_after, cancel_after
    )


@dataclass
class EscrowVerifyResult:
    """Result of verifying an escrow on-ledger."""

    found: bool
    escrow: EscrowInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_escrow(
    transport: Transport,
    address: str,
    expected_destination: str | None = None,
) -> EscrowVerifyResult:
    """Verify the account owns an escrow (optionally to a given destination)."""
    escrows = await transport.get_escrows(address)
    checks: list[str] = []
    failures: list[str] = []
    if not escrows:
        failures.append("No escrows found for this account")
        return EscrowVerifyResult(False, None, checks, failures)

    match = escrows[-1]
    if expected_destination:
        match = next((e for e in escrows if e.destination == expected_destination), match)

    checks.append(f"Escrow found: {match.amount} drops -> {match.destination[:16]}...")
    if match.finish_after:
        checks.append(f"FinishAfter (ripple time): {match.finish_after}")
    if match.cancel_after:
        checks.append(f"CancelAfter (ripple time): {match.cancel_after}")

    if expected_destination and match.destination != expected_destination:
        failures.append(f"Destination mismatch: expected {expected_destination}")
    return EscrowVerifyResult(True, match, checks, failures)
