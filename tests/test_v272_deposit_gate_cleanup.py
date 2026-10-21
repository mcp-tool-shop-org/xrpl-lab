"""2.7.2 (#20 items 15 and 16): deposit_gate_101 cleans up after itself.

Book Keeper's 2.7.1 helper-account live check, in one home:
- deposit_gate_101 left ``lsfDepositAuth`` on the learner's wallet, so
  amm_liquidity_101's issuer couldn't issue LAB to the learner (a validated
  ``tecNO_PERMISSION``) and the AMM had nothing to pool;
- after ``reset --module`` the lesson couldn't run again on the same wallet:
  its first run's credential preauthorization was still on the ledger, and
  the rerun's DepositPreauth validated ``tecDUPLICATE``.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from tests.cov_testnet import _fakes
from xrpl_lab.modules import ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

LEARNER = "rLEARNER"


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, no_color=True, width=200), buf


@pytest.mark.asyncio
async def test_the_lesson_leaves_deposit_auth_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests._shipped_module import run_shipped_module
    from xrpl_lab.state import load_state

    out, transport = await run_shipped_module("deposit_gate_101.md", tmp_path, monkeypatch)
    # The lesson set it on the learner; no account is left with it.
    assert transport._deposit_auth == set()
    assert "payments to your wallet are accepted again" in out
    cm = next(m for m in load_state().completed_modules if m.module_id == "deposit_gate_101")
    assert cm.verified is True


@pytest.mark.asyncio
async def test_the_lesson_runs_twice_on_one_wallet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the cleanup, a second run (after a reset) finds nothing left over."""
    import xrpl_lab.runner as runner_mod
    import xrpl_lab.state as state_mod
    from tests._shipped_module import MODULES_DIR
    from xrpl_lab.modules import parse_module

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    mod = parse_module((MODULES_DIR / "deposit_gate_101.md").read_text(encoding="utf-8"))
    transport = DryRunTransport()  # one ledger across both runs
    for _ in range(2):
        console, _buf = _console()
        console.input = lambda *a, **k: ""
        assert await runner_mod.run_module(mod, transport, dry_run=True, console=console)
        cm = next(m for m in state_mod.load_state().completed_modules
                  if m.module_id == "deposit_gate_101")
        assert cm.verified is True
        state_mod.reset_module("deposit_gate_101")


@pytest.mark.asyncio
async def test_a_leftover_credential_preauthorization_is_tolerated(monkeypatch) -> None:
    """A wallet a pre-2.7.2 run left the preauthorization on still passes."""
    monkeypatch.setattr(handlers, "save_state", lambda state: None)

    async def _dup(*args, **kwargs):
        return SubmitResult(success=False, txid="D" * 64, result_code="tecDUPLICATE")

    monkeypatch.setattr(handlers, "authorize_deposit_credential", _dup)
    state = LabState(wallet_address=LEARNER, network="testnet")
    ctx = {"module_id": "deposit_gate_101"}
    console, buf = _console()
    step = ModuleStep(text="x", action="authorize_kyc_credential", action_args={})
    ctx = await handlers.handle_authorize_kyc_credential(
        step, state, DryRunTransport(), "sSEED", ctx, console)
    assert "Already installed" in buf.getvalue()
    assert state.tx_index[-1].expected is True
    assert ctx.get("expected_failure_txids") == ["D" * 64]
    assert not [v for v in ctx.get("verifications", []) if not v["passed"]]


@pytest.mark.asyncio
async def test_ensure_funded_warns_when_deposit_auth_was_left_on(monkeypatch) -> None:
    async def _funded(*args, **kwargs):
        return True

    monkeypatch.setattr(handlers, "ensure_funded", _funded)
    t = DryRunTransport()
    t._deposit_auth.add(LEARNER)
    step = ModuleStep(text="x", action="ensure_funded", action_args={})
    for module_id, warned in (("amm_liquidity_101", True), ("deposit_gate_101", False)):
        console, buf = _console()
        await handlers.handle_ensure_funded(
            step, LabState(wallet_address=LEARNER), t, "", {"module_id": module_id}, console)
        assert ("Deposit authorization is on" in buf.getvalue()) is warned


@pytest.mark.asyncio
@pytest.mark.parametrize(("flags", "expected"), [(0x01000000, True), (0x00010000, False)])
async def test_the_testnet_transport_reads_the_flag(monkeypatch, flags, expected) -> None:
    _fakes.install(monkeypatch, results={
        "AccountInfo": {"account_data": {"Account": LEARNER, "Flags": flags}},
    })
    assert await XRPLTestnetTransport().get_deposit_auth(LEARNER) is expected


@pytest.mark.asyncio
async def test_an_unreadable_account_is_unknown(monkeypatch) -> None:
    _fakes.install(monkeypatch, results={"AccountInfo": {"error": "actNotFound"}})
    assert await XRPLTestnetTransport().get_deposit_auth(LEARNER) is None


@pytest.mark.asyncio
async def test_a_failed_clear_fails_the_step_when_the_read_back_is_unknown(monkeypatch) -> None:
    """Argon, 2.7.2 round 1, F1."""
    monkeypatch.setattr(handlers, "save_state", lambda state: None)

    async def _fail(*args, **kwargs):
        return SubmitResult(success=False, result_code="local_error", error="timed out")

    async def _unknown(address):
        return None

    monkeypatch.setattr(handlers, "enable_deposit_auth", _fail)
    t = DryRunTransport()
    monkeypatch.setattr(t, "get_deposit_auth", _unknown)
    console, _ = _console()
    step = ModuleStep(text="x", action="disable_deposit_auth", action_args={})
    ctx = await handlers.handle_disable_deposit_auth(
        step, LabState(wallet_address=LEARNER), t, "sSEED", {"module_id": "m"}, console)
    assert any(not v["passed"] for v in ctx.get("verifications", []))


def test_the_checks_list_names_the_cleanup() -> None:
    """Argon, 2.7.2 round 1, F2."""
    from xrpl_lab.modules import load_all_modules

    checks = load_all_modules()["deposit_gate_101"].checks
    assert any("cleanup" in c for c in checks)
