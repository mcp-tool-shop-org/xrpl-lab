"""2.6.2 (#20 item 9): the dry run books every write against a real address.

Helper wallets (a buyer, a sender, an issuer, multisig signers) were never
bound, so the dry run mapped their seeds to one synthetic address that the
faucet never funded, and their writes landed there. Every shipped lesson now
leaves that address untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._shipped_module import MODULES_DIR, run_shipped_module
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS


def _touched(transport) -> list[str]:
    """The transport's stores that mention the synthetic address anywhere, as
    a key, a value, an owner field or an issuer."""
    return sorted(
        name for name, store in vars(transport).items()
        if _DRY_RUN_WALLET_ADDRESS in repr(store)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("module_file", sorted(p.name for p in MODULES_DIR.glob("*.md")))
async def test_no_write_lands_on_the_synthetic_address(
    module_file: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, transport = await run_shipped_module(module_file, tmp_path, monkeypatch)
    assert _touched(transport) == []


@pytest.mark.asyncio
async def test_verify_escrow_reports_xrp_and_drops() -> None:
    """A 10 XRP escrow printed as "10 drops": the dry run stored the XRP value
    where EscrowInfo (and testnet) carry drops."""
    from xrpl_lab.actions.escrow import create_escrow, verify_escrow
    from xrpl_lab.transport.dry_run import DryRunTransport

    transport = DryRunTransport()
    transport.bind_wallet("sLEARNER", "rLEARNER")
    await transport.fund_from_faucet("rLEARNER")
    await create_escrow(transport, "sLEARNER", "10", "rDEST", 800_000_000)
    v = await verify_escrow(transport, "rLEARNER", expected_destination="rDEST")
    assert v.passed
    assert v.checks[0].startswith("Escrow found: 10 XRP (10000000 drops) -> rDEST")
    assert transport._balances["rLEARNER"] == 100_000_000 - 10_000_000 - 12
