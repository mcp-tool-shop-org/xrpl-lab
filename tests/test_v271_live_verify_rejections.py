"""2.7.1: live verification checks an expected rejection as a rejection.

Since 2.6.2 a rejection lesson records its expected tec, tem or tef in the
proof pack, and ``verify_proof_pack_live`` asserted tesSUCCESS on every claim,
so an honest pack failed live verification: the tec as "not tesSUCCESS", the
tem as "not found". Found while checking Argon's 2.7.1 round-2 F1 (the verify
route's links never saw ``validated``).
"""

from __future__ import annotations

import pytest

from xrpl_lab.reporting import generate_proof_pack, verify_proof_pack_live
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

OK, TEC, TEM, FAKE = "A" * 64, "B" * 64, "C" * 64, "D" * 64


def _pack(*records) -> dict:
    state = LabState(network="testnet", wallet_address="rLEARNER")
    for txid, success, expected, validated in records:
        state.record_tx(txid=txid, module_id="m", network="testnet", success=success,
                        validated=validated)
        state.tx_index[-1].expected = expected
    return generate_proof_pack(state)


def _ledger(**txs) -> DryRunTransport:
    t = DryRunTransport()
    t.set_tx_fixtures({txid: TxInfo(txid=txid, result_code=code, validated=True,
                                    account="rLEARNER") for txid, code in txs.items()})
    return t


@pytest.mark.asyncio
async def test_an_honest_rejection_lesson_pack_passes() -> None:
    pack = _pack((OK, True, False, None), (TEC, False, True, True), (TEM, False, True, False))
    live = await verify_proof_pack_live(
        pack, transport=_ledger(**{OK: "tesSUCCESS", TEC: "tecNO_PERMISSION"}))
    assert live.overall_passed is True
    assert [r.status for r in live.tx_results] == ["PASS", "PASS", "SKIPPED"]
    assert "Expected rejection, validated on-ledger: tecNO_PERMISSION" in live.tx_results[1].reason


@pytest.mark.asyncio
async def test_a_claimed_rejection_the_ledger_contradicts_fails() -> None:
    # Claimed a validated tec; the ledger has no such tx, or shows a success.
    for ledger in ({}, {TEC: "tesSUCCESS"}):
        pack = _pack((TEC, False, True, True))
        live = await verify_proof_pack_live(pack, transport=_ledger(**ledger))
        assert live.overall_passed is False
        assert live.tx_results[0].status == "FAIL"


@pytest.mark.asyncio
async def test_a_pack_of_only_unanchored_claims_does_not_pass() -> None:
    """A pack whose every claim is a never-validated rejection anchors nothing."""
    live = await verify_proof_pack_live(_pack((FAKE, False, True, False)),
                                        transport=_ledger())
    assert live.overall_passed is False


@pytest.mark.asyncio
async def test_an_unexpected_failure_still_fails_live() -> None:
    live = await verify_proof_pack_live(_pack((TEC, False, False, True)),
                                        transport=_ledger(**{TEC: "tecNO_PERMISSION"}))
    assert live.tx_results[0].status == "FAIL"


@pytest.mark.asyncio
async def test_a_pre_271_pack_without_the_flag_is_handled() -> None:
    pack = _pack((TEC, False, True, None), (TEM, False, True, None))
    live = await verify_proof_pack_live(pack, transport=_ledger(**{TEC: "tecDUPLICATE"}))
    assert [r.status for r in live.tx_results] == ["PASS", "SKIPPED"]


@pytest.mark.asyncio
async def test_the_verify_route_links_only_what_is_on_a_ledger() -> None:
    """Argon, 2.7.1 round 2, F1: the route reads live.to_dict(), which didn't
    carry validated, so the round-1 fix never reached it."""
    from xrpl_lab.api.routes import _live_to_schema

    pack = _pack((OK, True, False, None), (TEC, False, True, True), (TEM, False, True, False))
    live = await verify_proof_pack_live(
        pack, transport=_ledger(**{OK: "tesSUCCESS", TEC: "tecNO_PERMISSION"}))
    urls = [t.explorer_url for t in _live_to_schema(live).tx_results]
    assert urls[0].endswith(OK) and urls[1].endswith(TEC)
    assert urls[2] == ""
