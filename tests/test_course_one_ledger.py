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


@pytest.mark.asyncio
async def test_every_lesson_verifies_after_all_the_ones_before_it(tmp_path, monkeypatch) -> None:
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    monkeypatch.chdir(tmp_path)  # the shared issuer file is workspace-relative
    mods = load_all_modules()
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
    assert unverified == []
