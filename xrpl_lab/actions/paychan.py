"""Payment-channel actions (FT-CURRIC-001) — XRP micropayment channels.

A channel: the sender locks XRP once (PaymentChannelCreate), then signs many
cheap OFF-LEDGER claims for cumulative amounts; the receiver redeems the latest
ON-LEDGER when they choose (PaymentChannelClaim). "Sign many, settle once" — the
native rail for tipping, pay-per-action, and streaming rewards. XRP-only on
mainnet today.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..transport.base import ChannelInfo, SubmitResult, Transport


def _drops_to_xrp(drops: str) -> str:
    try:
        xrp = Decimal(str(drops)) / Decimal("1000000")
    except Exception:
        return "0"
    return str(int(xrp)) if xrp == int(xrp) else str(xrp)


async def open_channel(
    transport: Transport, wallet_seed: str, amount_xrp: str, destination: str,
    settle_delay: int, public_key: str = "", cancel_after: int | None = None,
) -> SubmitResult:
    """Open an XRP payment channel from the sender to a destination."""
    return await transport.submit_payment_channel_create(
        wallet_seed, amount_xrp, destination, settle_delay, public_key, cancel_after
    )


async def fund_channel(
    transport: Transport, wallet_seed: str, channel_id: str, amount_xrp: str
) -> SubmitResult:
    """Add more XRP to an existing channel."""
    return await transport.submit_payment_channel_fund(wallet_seed, channel_id, amount_xrp)


async def sign_claim(
    transport: Transport, wallet_seed: str, channel_id: str, amount_xrp: str
) -> str:
    """Sign an OFF-LEDGER cumulative claim; returns the signature hex (no network)."""
    return await transport.authorize_payment_channel_claim(wallet_seed, channel_id, amount_xrp)


async def check_claim(
    transport: Transport, channel_id: str, amount_xrp: str,
    public_key: str, signature: str,
) -> bool:
    """Verify an off-ledger claim signature against the channel's public key."""
    return await transport.verify_payment_channel_claim(
        channel_id, amount_xrp, public_key, signature
    )


async def redeem_claim(
    transport: Transport, wallet_seed: str, channel_id: str, balance_xrp: str,
    signature: str = "", public_key: str = "", close: bool = False,
) -> SubmitResult:
    """Redeem a signed claim on-ledger (the receiver settles the cumulative balance)."""
    return await transport.submit_payment_channel_claim(
        wallet_seed, channel_id, balance_xrp=balance_xrp,
        signature=signature, public_key=public_key, close=close,
    )


@dataclass
class ChannelVerifyResult:
    """Result of reading + checking a payment channel on-ledger."""

    channel: ChannelInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.channel is not None and len(self.failures) == 0


async def verify_channel(
    transport: Transport, source: str, channel_id: str = "",
    expect_amount_xrp: str | None = None, expect_balance_xrp: str | None = None,
) -> ChannelVerifyResult:
    """Read the channel and confirm its deposited / claimed amounts."""
    channels = await transport.get_account_channels(source)
    ch: ChannelInfo | None = None
    if channel_id:
        ch = next((c for c in channels if c.channel_id == channel_id), None)
    elif channels:
        ch = channels[-1]

    checks: list[str] = []
    failures: list[str] = []
    if ch is None:
        failures.append("No matching payment channel found on-ledger")
        return ChannelVerifyResult(None, checks, failures)

    checks.append(f"Channel found: {ch.channel_id[:16]}...")
    checks.append(f"Deposited: {_drops_to_xrp(ch.amount)} XRP")
    checks.append(f"Claimed so far: {_drops_to_xrp(ch.balance)} XRP")

    def _want(xrp: str) -> str:
        return str(int(Decimal(xrp) * Decimal("1000000")))

    if expect_amount_xrp is not None and ch.amount != _want(expect_amount_xrp):
        failures.append(
            f"Deposit mismatch: expected {expect_amount_xrp} XRP, "
            f"got {_drops_to_xrp(ch.amount)} XRP"
        )
    if expect_balance_xrp is not None and ch.balance != _want(expect_balance_xrp):
        failures.append(
            f"Claimed mismatch: expected {expect_balance_xrp} XRP, "
            f"got {_drops_to_xrp(ch.balance)} XRP"
        )
    return ChannelVerifyResult(ch, checks, failures)
