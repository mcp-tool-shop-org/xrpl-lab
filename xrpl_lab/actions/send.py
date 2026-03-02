"""Payment submission action."""

from __future__ import annotations

from ..transport.base import SubmitResult, Transport


async def send_payment(
    transport: Transport,
    wallet_seed: str,
    destination: str,
    amount: str,
    memo: str = "",
) -> SubmitResult:
    """Submit a payment transaction."""
    return await transport.submit_payment(
        wallet_seed=wallet_seed,
        destination=destination,
        amount=amount,
        memo=memo,
    )
