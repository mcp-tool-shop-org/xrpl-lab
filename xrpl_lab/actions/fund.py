"""Faucet funding action."""

from __future__ import annotations

from ..transport.base import FundResult, Transport


async def fund_wallet(transport: Transport, address: str) -> FundResult:
    """Fund a wallet address from the testnet faucet."""
    return await transport.fund_from_faucet(address)
