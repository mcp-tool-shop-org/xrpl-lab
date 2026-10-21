"""The dry-run sim must debit the account the faucet funded.

Regression for receipt_audit (negative balance, 2nd payment refused) and
game_economy_capstone (escrow refused: the 5% royalty and the escrow landed on a
phantom synthetic account instead of the funded wallet).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.modules import load_all_modules
from xrpl_lab.runner import run_module
from xrpl_lab.transport.dry_run import DryRunTransport

REAL = "rLEARNERxxxxxxxxxxxxxxxxxxxxxxxxxx"
OTHER = "rOTHERxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


@pytest.mark.asyncio
async def test_bound_seed_debits_the_funded_address() -> None:
    t = DryRunTransport()
    t.bind_wallet("sLEARNERSEED", REAL)
    await t.fund_from_faucet(REAL)
    for _ in range(2):  # two payments, as receipt_audit makes
        r = await t.submit_payment("sLEARNERSEED", OTHER, "1", "m")
        assert r.success, r.error
    assert t._balances[REAL] == 100_000_000 - 2 * 1_000_000 - 2 * 12
    assert all(v >= 0 for v in t._balances.values()), t._balances


@pytest.mark.asyncio
async def test_mint_is_booked_to_the_funded_account() -> None:
    t = DryRunTransport()
    t.bind_wallet("sLEARNERSEED", REAL)
    await t.fund_from_faucet(REAL)
    minted = await t.submit_nft_mint("sLEARNERSEED", "ipfs://x", 7, 5000, True)
    assert minted.success
    # the NFT's issuer is the funded account, so the royalty rule sees seller == issuer
    assert t._nfts[REAL][0].issuer == REAL
    assert REAL in t._owner_counts  # the mint's reserve is charged to the funded account


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_env")
@pytest.mark.parametrize("module_id", ["receipt_audit", "game_economy_capstone"])
async def test_module_dry_run_has_no_balance_failure(module_id: str) -> None:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, width=200)
    t = DryRunTransport()
    await run_module(load_all_modules()[module_id], t, dry_run=True, console=console)
    out = buf.getvalue()
    assert "insufficient XRP balance" not in out, out[-1500:]
    assert all(v >= 0 for v in t._balances.values()), t._balances
