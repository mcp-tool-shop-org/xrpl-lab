"""Check actions — deferred pull-payments (CheckCreate / CheckCash / CheckCancel).

A Check is the OPPOSITE lock model from Escrow. ``CheckCreate`` writes a Check
ledger object naming a Destination and a ``SendMax`` — the maximum the writer
can ever be debited — but moves and locks NOTHING. The Destination decides
whether, and when, to actually pull the money via ``CheckCash``; either party
may void an unredeemed Check with ``CheckCancel``. All three transaction types
have been mainnet-live since 2018.

The gotcha this module exists to teach: **CheckCreate succeeding is never a
guaranteed payout.** Because nothing is reserved at create time, the writer's
balance can (and in production, eventually will) drop below ``SendMax`` before
the destination gets around to cashing it — CheckCash then fails honestly
(``tecUNFUNDED`` / ``tecPATH_PARTIAL``) rather than silently paying out funds
that are no longer there. Contrast this hard with Escrow, which debits and
holds the funds the instant ``EscrowCreate`` validates.

xrpl.org names ``CheckCash`` explicitly as one of the transaction types whose
own amount field is not authoritative — always credit from the validated tx's
``delivered_amount`` metadata (the same delivered_amount_101 discipline),
never the Check's ``SendMax`` or the CheckCash's own ``Amount``/``DeliverMin``.
"""

from __future__ import annotations

from ..transport.base import SubmitResult, Transport


async def create_check(
    transport: Transport,
    wallet_seed: str,
    destination: str,
    send_max: str,
    expiration: int | None = None,
    destination_tag: int | None = None,
    invoice_id: str = "",
    wallet_address: str = "",
) -> SubmitResult:
    """Write a Check authorizing *destination* to pull up to *send_max* (CheckCreate).

    Nothing moves and nothing is locked — this is the entire lesson. ``send_max``
    is a CEILING (the most the writer can ever be debited by this Check), not a
    reservation and not the amount that will necessarily be delivered.
    ``expiration`` (optional, ripple-epoch seconds) makes the Check un-cashable
    (but still cancellable, by anyone) after that time. Returns
    ``SubmitResult.check_id`` on success — the 64-hex Check ledger-object id
    ``cash_check`` / ``cancel_check`` need. ``wallet_address`` is a dry-run
    keying aid (every dry-run seed collapses to one synthetic address); the
    testnet transport derives the writer from the seed and ignores it.
    """
    return await transport.submit_check_create(
        wallet_seed,
        destination,
        send_max,
        expiration=expiration,
        destination_tag=destination_tag,
        invoice_id=invoice_id,
        wallet_address=wallet_address,
    )


async def cash_check(
    transport: Transport,
    wallet_seed: str,
    check_id: str,
    amount: str | None = None,
    deliver_min: str | None = None,
    wallet_address: str = "",
) -> SubmitResult:
    """Redeem a Check for an exact ``amount`` or a flexible ``deliver_min`` (CheckCash).

    Exactly one of ``amount`` (redeem for precisely this much) or
    ``deliver_min`` (redeem for at least this much, up to the Check's
    ``SendMax``) must be given — xrpl-py's model raises the identical "either
    amount or deliver_min... not both" at construction, mirrored by the
    dry-run transport so a dry-run pass never masks a testnet local_error.

    Only the Check's Destination may cash it (``tecNO_PERMISSION`` otherwise);
    a Check past its Expiration can only be cancelled, never cashed
    (``tecEXPIRED``); and the writer must still hold the funds AT CASH TIME —
    CheckCreate succeeding never guaranteed this (``tecUNFUNDED`` /
    ``tecPATH_PARTIAL`` for the token-check path). Always credit the
    destination from the resulting tx's ``delivered_amount`` metadata, never
    from ``amount``/``deliver_min``/the Check's ``SendMax``.
    """
    return await transport.submit_check_cash(
        wallet_seed,
        check_id,
        amount=amount,
        deliver_min=deliver_min,
        wallet_address=wallet_address,
    )


async def cancel_check(
    transport: Transport,
    wallet_seed: str,
    check_id: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Void an unredeemed Check, freeing the WRITER's owner reserve (CheckCancel).

    While the Check is still live, either the writer or the Destination may
    cancel it; once it has expired, ANY address may clean it up. Unlike
    ``EscrowCancel`` — which refunds the locked amount to the owner — a
    ``CheckCancel`` credits NOBODY: ``CheckCreate`` never moved or locked
    anything, so there is nothing to refund. Only the reserve slot the Check
    object held is freed.
    """
    return await transport.submit_check_cancel(
        wallet_seed, check_id, wallet_address=wallet_address
    )
