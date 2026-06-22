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


async def finish_escrow(
    transport: Transport,
    wallet_seed: str,
    owner: str,
    offer_sequence: int,
) -> SubmitResult:
    """Finish a time-based escrow past FinishAfter (EscrowFinish).

    ``owner`` is the EscrowCreate's account and ``offer_sequence`` is its
    create sequence (``EscrowInfo.sequence``). No condition/fulfillment — this
    is the time-based release path the lifecycle modules teach.
    """
    return await transport.submit_escrow_finish(wallet_seed, owner, offer_sequence)


async def cancel_escrow(
    transport: Transport,
    wallet_seed: str,
    owner: str,
    offer_sequence: int,
) -> SubmitResult:
    """Cancel an escrow past CancelAfter, reclaiming funds (EscrowCancel)."""
    return await transport.submit_escrow_cancel(wallet_seed, owner, offer_sequence)


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


@dataclass
class EscrowGoneResult:
    """Result of verifying an escrow object is no longer on-ledger."""

    gone: bool
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.gone and len(self.failures) == 0


async def verify_escrow_finished(
    transport: Transport,
    address: str,
    offer_sequence: int | None = None,
) -> EscrowGoneResult:
    """Verify an escrow has been finished/cancelled (removed from the ledger).

    After EscrowFinish/EscrowCancel the Escrow object is deleted and the
    owner's reserve is freed. We confirm the object is gone: if
    ``offer_sequence`` is given, that specific create-sequence must no longer
    be present; otherwise the account must own no escrows at all.
    """
    escrows = await transport.get_escrows(address)
    checks: list[str] = []
    failures: list[str] = []

    if offer_sequence is not None:
        still_present = any(e.sequence == offer_sequence for e in escrows)
        if still_present:
            failures.append(
                f"Escrow with create-sequence {offer_sequence} is still on-ledger"
            )
            return EscrowGoneResult(False, checks, failures)
        # Guard against a FALSE "gone": EscrowInfo.sequence resolves to 0 when
        # the testnet transport could not join the Escrow object back to its
        # EscrowCreate (PreviousTxnID miss, or the create tx fell outside the
        # account_tx window). If any still-present escrow has an unresolved
        # create-sequence, we cannot prove THIS escrow was removed — so we must
        # NOT claim the funds were released. Report indeterminate instead.
        if any(e.sequence == 0 for e in escrows):
            failures.append(
                f"Could not confirm escrow {offer_sequence} was removed: "
                f"{sum(1 for e in escrows if e.sequence == 0)} escrow(s) "
                "on-ledger have an unresolved create-sequence — retry, or "
                "check the address on a block explorer"
            )
            return EscrowGoneResult(False, checks, failures)
        checks.append(
            f"Escrow (create-sequence {offer_sequence}) is gone — funds released, "
            "reserve freed"
        )
        return EscrowGoneResult(True, checks, failures)

    if escrows:
        failures.append(f"{len(escrows)} escrow(s) still on-ledger for this account")
        return EscrowGoneResult(False, checks, failures)
    checks.append("No escrows remain on-ledger — reserve freed")
    return EscrowGoneResult(True, checks, failures)
