"""2.7.1: live verification accepts a tx signed by the lesson's own helper wallets.

Book Keeper's live check on da63f40: deposit_gate's honest pack failed
``proof verify --live`` because three successes were signed by its helper
wallets (a sender, a credential subject), and every success had to match the
pack's one learner address. Each completed module now records the accounts
that signed in it, and the pack carries them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.reporting import generate_proof_pack, verify_proof_pack_live
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

LEARNER, HELPER, STRANGER = "rLEARNER", "rHELPER", "rSTRANGER"
A, B, C = "A" * 64, "B" * 64, "C" * 64


def test_both_transports_report_their_bound_addresses() -> None:
    for t in (DryRunTransport(), XRPLTestnetTransport()):
        t.bind_wallet("s1", LEARNER)
        t.bind_wallet("s2", HELPER)
        t.bind_wallet("s3", HELPER)
        assert t.bound_addresses() == [HELPER, LEARNER]


@pytest.mark.asyncio
async def test_a_lesson_records_its_helper_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests._shipped_module import run_shipped_module
    from xrpl_lab.state import load_state

    await run_shipped_module("deposit_gate_101.md", tmp_path, monkeypatch)
    accounts = load_state().module_accounts["deposit_gate_101"]
    assert len(accounts) >= 3  # the learner, the sender, the outsider


def test_every_run_adds_its_accounts() -> None:
    """Argon, 2.7.1 round 5, F1: a retry, an interrupted run or a --force rerun
    each bind new helpers; all of them stay verifiable."""
    state = LabState()
    state.remember_accounts("m", [LEARNER, HELPER])
    state.remember_accounts("m", [LEARNER, "rHELPER2"])
    assert state.module_accounts["m"] == sorted([LEARNER, HELPER, "rHELPER2"])


def _pack(accounts, *records) -> dict:
    state = LabState(network="testnet", wallet_address=LEARNER)
    for txid, success, expected, validated in records:
        state.record_tx(txid=txid, module_id="m", network="testnet", success=success,
                        validated=validated)
        state.tx_index[-1].expected = expected
    state.complete_module("m")
    state.remember_accounts("m", accounts)
    return generate_proof_pack(state)


def _ledger(**txs) -> DryRunTransport:
    t = DryRunTransport()
    t.set_tx_fixtures({txid: TxInfo(txid=txid, result_code=code, validated=True,
                                    account=account) for txid, (code, account) in txs.items()})
    return t


@pytest.mark.asyncio
async def test_a_helper_signed_success_passes() -> None:
    pack = _pack([LEARNER, HELPER], (A, True, False, None), (B, True, False, None))
    live = await verify_proof_pack_live(pack, transport=_ledger(
        **{A: ("tesSUCCESS", LEARNER), B: ("tesSUCCESS", HELPER)}))
    assert live.overall_passed is True
    assert [r.status for r in live.tx_results] == ["PASS", "PASS"]


@pytest.mark.asyncio
async def test_a_tx_from_an_unrecorded_account_fails() -> None:
    pack = _pack([LEARNER, HELPER], (A, True, False, None), (C, False, True, True))
    live = await verify_proof_pack_live(pack, transport=_ledger(
        **{A: ("tesSUCCESS", STRANGER), C: ("tecNO_PERMISSION", STRANGER)}))
    assert [r.status for r in live.tx_results] == ["FAIL", "FAIL"]
    assert "recorded helper" in live.tx_results[0].reason
    assert "recorded helper wallets" in live.tx_results[1].reason


@pytest.mark.asyncio
async def test_an_older_pack_keeps_the_learner_only_check() -> None:
    pack = _pack([], (B, True, False, None))
    live = await verify_proof_pack_live(pack, transport=_ledger(**{B: ("tesSUCCESS", HELPER)}))
    assert live.tx_results[0].status == "FAIL"


@pytest.mark.asyncio
async def test_an_earlier_attempts_helper_tx_still_verifies() -> None:
    """A first attempt's helper signed B; the completing run's helper signed A.
    Both runs' accounts are recorded, so both txs verify."""
    state = LabState(network="testnet", wallet_address=LEARNER)
    state.record_tx(txid=B, module_id="m", network="testnet", success=True)
    state.remember_accounts("m", [LEARNER, "rFIRSTRUNHELPER"])  # the stopped run
    state.record_tx(txid=A, module_id="m", network="testnet", success=True)
    state.complete_module("m")
    state.remember_accounts("m", [LEARNER, HELPER])
    live = await verify_proof_pack_live(generate_proof_pack(state), transport=_ledger(
        **{A: ("tesSUCCESS", HELPER), B: ("tesSUCCESS", "rFIRSTRUNHELPER")}))
    assert live.overall_passed is True


@pytest.mark.asyncio
async def test_a_stopped_run_records_its_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from rich.console import Console

    import xrpl_lab.runner as runner_mod
    import xrpl_lab.state as state_mod
    from xrpl_lab.modules import ModuleDef, ModuleStep
    from xrpl_lab.registry import ActionDef, register, resolve
    from xrpl_lab.state import load_state

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")

    async def _bind_then_fail(step, state, transport, wallet_seed, ctx, console):
        transport.bind_wallet("sHELPERSEED", "rSTOPPEDHELPER")
        raise RuntimeError("step blew up")

    try:
        resolve("test_271_bind_fail")
    except Exception:
        register(ActionDef(name="test_271_bind_fail", handler=_bind_then_fail,
                           description="test"))
    mod = ModuleDef(id="m271s", title="s", time="1 min", level="beginner", requires=[],
                    produces=[], checks=[], raw_body="",
                    steps=[ModuleStep(text="## Step 1: x", action="test_271_bind_fail",
                                      action_args={})])
    ok = await runner_mod.run_module(mod, DryRunTransport(), dry_run=True,
                                     console=Console(file=io.StringIO()))
    assert ok is False
    assert "rSTOPPEDHELPER" in load_state().module_accounts["m271s"]


def test_reset_module_clears_its_accounts(tmp_path: Path, monkeypatch) -> None:
    import xrpl_lab.state as state_mod

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    state = LabState()
    state.complete_module("m")
    state.remember_accounts("m", [LEARNER, HELPER])
    state.remember_accounts("other", [LEARNER])
    state_mod.save_state(state)
    state_mod.reset_module("m")
    assert state_mod.load_state().module_accounts == {"other": [LEARNER]}


def test_the_state_merge_unions_accounts(tmp_path: Path, monkeypatch) -> None:
    import xrpl_lab.state as state_mod

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    on_disk = LabState()
    on_disk.remember_accounts("m", [HELPER])
    state_mod.save_state(on_disk)
    mine = LabState()
    mine.remember_accounts("m", [LEARNER])
    state_mod.save_state(mine)
    assert state_mod.load_state().module_accounts["m"] == sorted([HELPER, LEARNER])
