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
    cm = next(m for m in load_state().completed_modules if m.module_id == "deposit_gate_101")
    assert len(cm.accounts) >= 3  # the learner, the sender, the outsider


def test_a_forced_rerun_keeps_both_runs_helpers() -> None:
    state = LabState()
    state.complete_module("m", accounts=[LEARNER, HELPER])
    state.complete_module("m", accounts=[LEARNER, "rHELPER2"])
    assert state.completed_modules[0].accounts == sorted([LEARNER, HELPER, "rHELPER2"])


def _pack(accounts, *records) -> dict:
    state = LabState(network="testnet", wallet_address=LEARNER)
    for txid, success, expected, validated in records:
        state.record_tx(txid=txid, module_id="m", network="testnet", success=success,
                        validated=validated)
        state.tx_index[-1].expected = expected
    state.complete_module("m", accounts=accounts)
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
