"""The whole course in one home, on one dry-run ledger, in curriculum order.

2.7.4 (#28): every CLI dry run starts a fresh in-memory ledger, so the offline
sweep could never see one lesson break a later one. The 2.7.3 full live sweep
found three (custodial_crediting_101's RequireDest, clawback_101's shared
issuer, checks_101 running short of XRP), and deposit_gate_101's DepositAuth
before them (2.7.2). This runs the course the way a workshop does. On v2.7.3
it verified 30 of 32 (checks_101 and deposit_gate_101 failed).
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

import xrpl_lab.runner as runner_mod
import xrpl_lab.state as state_mod
from xrpl_lab.curriculum import build_graph
from xrpl_lab.modules import load_all_modules
from xrpl_lab.transport.dry_run import DryRunTransport


async def _unverified(mods: dict, tmp_path, monkeypatch) -> list[str]:
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    monkeypatch.chdir(tmp_path)  # the shared issuer file is workspace-relative
    order = build_graph(mods).canonical_order()
    assert len(order) == len(mods)
    transport = DryRunTransport()
    unverified = []
    for mid in order:
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, width=200)
        monkeypatch.setattr(console, "input", lambda *a, **k: "")
        assert await runner_mod.run_module(mods[mid], transport, dry_run=True, console=console)
        done = [m for m in state_mod.load_state().completed_modules if m.module_id == mid]
        if not (done and done[-1].verified):
            unverified.append(mid)
    return unverified


@pytest.mark.asyncio
async def test_every_lesson_verifies_after_all_the_ones_before_it(tmp_path, monkeypatch) -> None:
    assert await _unverified(load_all_modules(), tmp_path, monkeypatch) == []


@pytest.mark.asyncio
async def test_without_custodials_cleanup_the_later_lessons_fail(tmp_path, monkeypatch) -> None:
    """The dry run reproduces the live sweep's knock-on failures (Argon, 2.7.4 round 1, F1).

    Live on 2.7.3, custodial_crediting_101 left RequireDest on and these lessons
    failed tecDST_TAG_NEEDED; dex_vs_amm_risk_literacy is offline-only.
    """
    mods = load_all_modules()
    cc = mods["custodial_crediting_101"]
    cc.steps = [s for s in cc.steps if s.action != "disable_require_dest"]
    assert sorted(await _unverified(mods, tmp_path, monkeypatch)) == [
        "amm_liquidity_101", "deposit_gate_101", "dex_inventory_guardrails",
        "dex_market_making_101", "dex_vs_amm_risk_literacy", "game_economy_capstone",
    ]
