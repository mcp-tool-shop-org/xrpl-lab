"""Token Escrow actions (XLS-85) — locking IOUs, not just XRP.

The TokenEscrow amendment went mainnet-live 2026-02-12. It extends the native
Escrow object beyond XRP so the locked ``Amount`` can be an ISSUED currency (an
IOU / trust-line token). The escrow lifecycle (create / finish / cancel) is
mechanically identical to XRP escrow — the difference is the asset and three
extra rules the network enforces at ``EscrowCreate``:

  1. **Issuer opt-in is mandatory, per-asset.** The token's ISSUER must set the
     account flag ``asfAllowTrustLineLocking`` (ledger flag
     ``lsfAllowTrustLineLocking``) via ``AccountSet`` BEFORE anyone can escrow
     that IOU. Missing it → ``tecNO_PERMISSION`` on ``EscrowCreate``.
  2. **The issuer cannot be the escrow SOURCE.** An issuer escrowing its own
     token as sender fails ``tecNO_PERMISSION``. The flow is: the issuer opts in
     and issues to a HOLDER; the holder escrows the token to a third party.
  3. **CancelAfter is mandatory.** Unlike XRP, there is no open-ended token
     escrow — every token escrow MUST carry a ``CancelAfter`` expiration.

``TransferRate``/``TransferFee`` is snapshotted at ``EscrowCreate`` and applied
at ``EscrowFinish``: the delivered amount is net of that captured fee, so the
recipient receives less than the locked face amount when a fee exists. This demo
keeps the token fee-free for clarity, so the recipient receives the full amount.

MPT escrow (Multi-Purpose Tokens) is the other half of XLS-85 — an MPT issuer
opts in with ``tfMPTCanEscrow`` (+ ``tfMPTCanTransfer``) instead of the trust-
line flag. This module focuses on the IOU path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..transport.base import SubmitResult, Transport


async def set_allow_trustline_locking(
    transport: Transport,
    issuer_seed: str,
    issuer_address: str = "",
) -> SubmitResult:
    """Enable ``asfAllowTrustLineLocking`` on the issuer (AccountSet).

    This is the per-asset opt-in that makes the issuer's IOU escrowable. It must
    be set on the ISSUER account before any holder can create a token escrow of
    that currency. ``issuer_address`` is forwarded for the dry-run transport's
    per-issuer flag state (the testnet path derives the account from the seed).
    """
    return await transport.submit_allow_trustline_locking(issuer_seed, issuer_address)


async def create_token_escrow(
    transport: Transport,
    source_seed: str,
    currency: str,
    issuer: str,
    value: str,
    destination: str,
    cancel_after: int,
    finish_after: int | None = None,
    source_address: str = "",
) -> SubmitResult:
    """Create a token (IOU) escrow (EscrowCreate with an issued Amount).

    Locks ``value`` of ``currency``/``issuer`` from the source account to
    ``destination`` until the escrow is finished or cancelled.

    Two rules are enforced LOCALLY before submission (rippled would otherwise
    return an opaque tec/tem, and the dry-run must reject them identically so a
    dry-run "pass" never masks a testnet failure):

    * **CancelAfter is mandatory.** ``cancel_after`` is required for a token
      escrow — a missing value is a structured local error, not a silent
      omission that reaches the ledger.

    * (The issuer-as-source and issuer-opt-in rules are enforced by the
      transport, which has the flag/identity state to check them.)
    """
    if cancel_after is None:
        return SubmitResult(
            success=False,
            result_code="local_error",
            error=(
                "CancelAfter is mandatory for a token escrow. Unlike XRP, "
                "XLS-85 requires every issued-currency escrow to carry a "
                "CancelAfter expiration — there is no open-ended token escrow. "
                "Pass a CancelAfter (ripple-time) later than any FinishAfter."
            ),
        )
    if (
        finish_after is not None
        and cancel_after is not None
        and cancel_after <= finish_after
    ):
        return SubmitResult(
            success=False,
            result_code="local_error",
            error=(
                f"CancelAfter ({cancel_after}) must be strictly after "
                f"FinishAfter ({finish_after})."
            ),
        )
    return await transport.submit_token_escrow_create(
        source_seed,
        currency,
        issuer,
        value,
        destination,
        cancel_after,
        finish_after,
        source_address,
    )


async def finish_escrow(
    transport: Transport,
    wallet_seed: str,
    owner: str,
    offer_sequence: int,
) -> SubmitResult:
    """Finish a token escrow, releasing the locked IOU to the destination.

    ``owner`` is the EscrowCreate's account (the holder who locked the token)
    and ``offer_sequence`` is its create sequence (``EscrowInfo.sequence``).
    EscrowFinish is the same transaction for token and XRP escrows, so this
    reuses the standard escrow-finish transport path.
    """
    return await transport.submit_escrow_finish(wallet_seed, owner, offer_sequence)


@dataclass
class TokenMovedResult:
    """Result of verifying an escrowed IOU reached the recipient's trust line."""

    found: bool
    balance: str
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.found and len(self.failures) == 0


async def verify_token_moved(
    transport: Transport,
    recipient: str,
    currency: str,
    issuer: str,
    before: str = "0",
    expected_increase: str | None = None,
) -> TokenMovedResult:
    """Verify the recipient's issued balance rose by the escrowed amount.

    Reads the recipient's trust line for ``currency``/``issuer`` and confirms it
    increased from ``before``. When ``expected_increase`` is given, the delta
    must equal it exactly (the fee-free demo delivers the full face amount);
    otherwise any increase passes.
    """
    checks: list[str] = []
    failures: list[str] = []

    lines = await transport.get_trust_lines(recipient)
    line = next(
        (tl for tl in lines if tl.currency == currency and tl.peer == issuer), None
    )
    if line is None:
        failures.append(
            f"No {currency} trust line from {issuer[:12]}... on the recipient — "
            "the escrowed token has no line to land on"
        )
        return TokenMovedResult(False, "0", checks, failures)

    try:
        before_val = Decimal(before)
        now_val = Decimal(line.balance)
    except (InvalidOperation, ValueError):
        failures.append(
            f"Could not compare balances (before={before!r}, now={line.balance!r})"
        )
        return TokenMovedResult(True, line.balance, checks, failures)

    delta = now_val - before_val
    if expected_increase is not None:
        try:
            want = Decimal(expected_increase)
        except (InvalidOperation, ValueError):
            want = None
        if want is not None and delta != want:
            failures.append(
                f"Recipient {currency} balance changed by {delta}, "
                f"expected +{want}"
            )
            return TokenMovedResult(True, line.balance, checks, failures)
        checks.append(
            f"Recipient received {delta} {currency} "
            f"(balance {before_val} -> {now_val})"
        )
    else:
        if delta <= 0:
            failures.append(
                f"Recipient {currency} balance did not increase "
                f"(before {before_val}, now {now_val})"
            )
            return TokenMovedResult(True, line.balance, checks, failures)
        checks.append(
            f"Recipient {currency} balance increased by {delta} "
            f"(now {now_val})"
        )

    return TokenMovedResult(True, line.balance, checks, failures)
