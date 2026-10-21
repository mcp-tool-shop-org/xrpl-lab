"""2.7.0: the defects Book Keeper's live sweep on 4deed70 found.

1. escrow_finish_101 failed tecNO_PERMISSION: the wall clock read past
   FinishAfter while the validated ledger's close time was still equal to it.
2. A wallet that doesn't sign as its address stopped the run, but exited 0.
3. ``run --force`` did nothing for a completed module on testnet.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, no_color=True, width=200), buf


# ── 1. The escrow waits for the ledger, not the wall clock ────────────


class _Ledger:
    def __init__(self, closes):
        self.network_name = "testnet"
        self._closes = list(closes)
        self.calls = 0

    async def get_validated_close_time(self):
        self.calls += 1
        return self._closes.pop(0) if len(self._closes) > 1 else self._closes[0]


@pytest.fixture()
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    out: list[float] = []

    async def _sleep(seconds):
        out.append(seconds)

    monkeypatch.setattr(handlers.asyncio, "sleep", _sleep)
    return out


@pytest.mark.asyncio
async def test_the_finish_waits_for_a_ledger_past_finish_after(slept) -> None:
    import time

    target = int(time.time()) - handlers._RIPPLE_EPOCH - 5  # the wall clock is past it
    ledger = _Ledger([target, target, target + 3])  # the ledger isn't, twice
    console, buf = _console()
    await handlers._wait_for_finish_after(ledger, target, console)
    assert slept == [2, 2]
    assert "Waiting for a validated ledger past FinishAfter" in buf.getvalue()
    assert ledger.calls == 3


@pytest.mark.asyncio
async def test_a_ledger_already_past_finish_after_needs_no_wait(slept) -> None:
    import time

    target = int(time.time()) - handlers._RIPPLE_EPOCH - 5
    await handlers._wait_for_finish_after(_Ledger([target + 1]), target, _console()[0])
    assert slept == []


@pytest.mark.asyncio
async def test_the_ledger_wait_is_capped(slept) -> None:
    import time

    target = int(time.time()) - handlers._RIPPLE_EPOCH - 5
    await handlers._wait_for_finish_after(_Ledger([target]), target, _console()[0], max_wait=6)
    assert sum(slept) == 6


@pytest.mark.asyncio
async def test_an_unknown_close_time_falls_back_to_the_wall_clock(slept) -> None:
    import time

    target = int(time.time()) - handlers._RIPPLE_EPOCH - 5
    await handlers._wait_for_finish_after(_Ledger([None]), target, _console()[0])
    assert slept == []
    await handlers._wait_for_finish_after(SimpleNamespace(network_name="testnet"), target,
                                          _console()[0])
    assert slept == []


# ── 2. An early stop exits with its code; 3. --force redoes ───────────


@pytest.fixture()
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import xrpl_lab.state as state_mod

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    return tmp_path


def _empty_module(mid: str = "m270"):
    from xrpl_lab.modules import ModuleDef

    return ModuleDef(id=mid, title=mid, time="1 min", level="beginner",
                     requires=[], produces=[], checks=[], raw_body="", steps=[])


@pytest.mark.asyncio
async def test_a_wallet_mismatch_exits_1(_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from xrpl.constants import CryptoAlgorithm
    from xrpl.core.keypairs import generate_seed

    import xrpl_lab.cli as cli
    import xrpl_lab.runner as runner_mod
    from xrpl_lab.state import LabState
    from xrpl_lab.transport.dry_run import DryRunTransport

    seed = generate_seed(entropy="00112233445566778899aabbccddeeff",
                         algorithm=CryptoAlgorithm.SECP256K1)
    path = _home / "wallet.json"
    path.write_text(json.dumps({"seed": seed, "address": "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"}),
                    encoding="utf-8")
    monkeypatch.setattr(runner_mod, "load_state", lambda: LabState(wallet_path=str(path)))
    console, _ = _console()
    ok = await runner_mod.run_module(_empty_module(), DryRunTransport(), console=console)
    assert ok is False and runner_mod.last_stop_exit_code == 1
    with pytest.raises(SystemExit) as exc:
        cli._exit_if_unverified("m270", ok, console)
    assert exc.value.code == 1


def test_a_stop_without_a_code_keeps_the_old_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import xrpl_lab.cli as cli
    import xrpl_lab.runner as runner_mod

    monkeypatch.setattr(runner_mod, "last_stop_exit_code", None)
    cli._exit_if_unverified("m270", False, _console()[0])  # no SystemExit


@pytest.mark.asyncio
async def test_force_redoes_a_completed_module_on_a_network(
    _home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrpl_lab.runner as runner_mod
    from xrpl_lab.state import CompletedModule, LabState
    from xrpl_lab.transport.dry_run import DryRunTransport

    def _completed() -> LabState:
        state = LabState()
        state.completed_modules.append(CompletedModule(module_id="m270", completed_at=1.0))
        return state

    monkeypatch.setattr(runner_mod, "load_state", _completed)
    for force, skipped in ((False, True), (True, False)):
        console, buf = _console()
        await runner_mod.run_module(_empty_module(), DryRunTransport(), dry_run=False,
                                    force=force, console=console)
        assert ("already completed" in buf.getvalue()) is skipped, force


# ── 4. The report counts recorded transactions that skipped context ───


@pytest.mark.asyncio
async def test_the_report_counts_a_recorded_offer_cancel(_home: Path) -> None:
    from xrpl_lab.modules import ModuleDef, ModuleStep
    from xrpl_lab.registry import ActionDef, register, resolve
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state
    from xrpl_lab.transport.dry_run import DryRunTransport

    async def _listed_and_recorded(step, state, transport, wallet_seed, ctx, console):
        ctx.setdefault("txids", []).append("A" * 64)
        state.record_tx(txid="A" * 64, module_id=ctx["module_id"], network=state.network,
                        success=True)
        # Like dex_market_making's OfferCancels: recorded, not in context.
        state.record_tx(txid="B" * 64, module_id=ctx["module_id"], network=state.network,
                        success=True)
        return ctx

    try:
        resolve("test_270_cancel")
    except Exception:
        register(ActionDef(name="test_270_cancel", handler=_listed_and_recorded,
                           description="test-only"))
    mod = ModuleDef(id="m270r", title="r", time="1 min", level="beginner", requires=[],
                    produces=[], checks=[], raw_body="",
                    steps=[ModuleStep(text="## Step 1: x", action="test_270_cancel",
                                      action_args={})])
    await run_module(mod, DryRunTransport(), dry_run=True, console=_console()[0])
    cm = next(m for m in load_state().completed_modules if m.module_id == "m270r")
    report = Path(cm.report_path).read_text(encoding="utf-8")
    assert "Transactions: 2 successful, 0 failed" in report
    assert report.count("## Transaction\n\nTXID: `") == 2
    # Argon, 2.7.0 round 3, F1: the completed module lists them too.
    assert cm.txids == ["A" * 64, "B" * 64]


@pytest.mark.asyncio
async def test_recorded_transactions_keep_their_order(_home: Path) -> None:
    """Argon, 2.7.0 round 3, F1: a mid-module recorded-only tx (an OfferCancel)
    stays ahead of a later step's listed tx, in the report and on the module."""
    from xrpl_lab.modules import ModuleDef, ModuleStep
    from xrpl_lab.registry import ActionDef, register, resolve
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state
    from xrpl_lab.transport.dry_run import DryRunTransport

    async def _cancel_recorded_only(step, state, transport, wallet_seed, ctx, console):
        state.record_tx(txid="C" * 64, module_id=ctx["module_id"], network=state.network,
                        success=True)
        return ctx

    async def _later_listed_and_recorded(step, state, transport, wallet_seed, ctx, console):
        ctx.setdefault("txids", []).append("D" * 64)
        state.record_tx(txid="D" * 64, module_id=ctx["module_id"], network=state.network,
                        success=True)
        return ctx

    for name, fn in (("test_270_c", _cancel_recorded_only),
                     ("test_270_d", _later_listed_and_recorded)):
        try:
            resolve(name)
        except Exception:
            register(ActionDef(name=name, handler=fn, description="test-only"))
    mod = ModuleDef(
        id="m270o", title="o", time="1 min", level="beginner", requires=[], produces=[],
        checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: c", action="test_270_c", action_args={}),
               ModuleStep(text="## Step 2: d", action="test_270_d", action_args={})],
    )
    console = _console()[0]
    console.input = lambda *a, **k: ""
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == "m270o")
    assert cm.txids == ["C" * 64, "D" * 64]
    report = Path(cm.report_path).read_text(encoding="utf-8")
    listed = report[report.index("## Summary"):]
    assert listed.index("C" * 64 + "`") < listed.index("D" * 64 + "`")
