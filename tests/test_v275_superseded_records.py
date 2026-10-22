"""2.7.5 (#32): a failed run's records after a passing ``run --force``.

Book Keeper's 2.7.4 live checks: run 1 of clawback_101 failed before reaching
the network (four ``failed`` placeholders), ``run --force`` passed and the
module read ``verified: true``, but ``proof verify --live`` still failed on the
placeholders. A failure older than a module's passing latest run is now checked
as history: skipped when it never reached a ledger, and when it did, it must be
on the ledger as recorded. The pack keeps every record (a rerun destroys no
history, 2.7.1).

Placeholders were also collapsed into one claim for the whole pack, so one
module's could hide another's; they are now told apart by module.
"""

from __future__ import annotations

import pytest

from xrpl_lab import reporting as rep
from xrpl_lab.reporting import LIVE_FAIL, LIVE_PASS, LIVE_SKIPPED
from xrpl_lab.state import CompletedModule, LabState, TxRecord
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

LEARNER = "rLEARNERxxxxxxxxxxxxxxxxxxxxxxxxx"
OK = "A" * 64
TEC = "B" * 64


def _pack(records, completed):
    state = LabState(wallet_address=LEARNER, network="testnet")
    state.tx_index = records
    state.completed_modules = completed
    return rep.generate_proof_pack(state)


def _rec(txid, t, success=False, module="clawback_101", **kw):
    return TxRecord(txid=txid, module_id=module, timestamp=t, network="testnet",
                    success=success, **kw)


def _transport():
    t = DryRunTransport()
    t.set_tx_fixtures({
        OK: TxInfo(txid=OK, account=LEARNER, result_code="tesSUCCESS", validated=True),
        TEC: TxInfo(txid=TEC, account=LEARNER, result_code="tecNO_PERMISSION",
                    validated=True),
    })
    return t


async def _verify(pack):
    return await rep.verify_proof_pack_live(pack, transport=_transport())


@pytest.mark.asyncio
async def test_a_passing_rerun_supersedes_the_failed_runs_placeholders() -> None:
    """The #32 case: four placeholders from run 1, then a passing --force."""
    pack = _pack(
        [*(_rec("failed", 100.0 + i, validated=False) for i in range(4)),
         _rec(OK, 200.0, success=True, validated=True)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0,
                         txids=[OK], verified=True)],
    )
    result = await _verify(pack)
    assert [r.status for r in result.tx_results] == [LIVE_SKIPPED, LIVE_PASS]
    assert "latest run passed" in result.tx_results[0].reason
    assert result.failed_count == 0


@pytest.mark.asyncio
async def test_an_unverified_module_still_fails_its_placeholder() -> None:
    pack = _pack(
        [_rec("failed", 100.0, validated=False)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=False)],
    )
    [r] = (await _verify(pack)).tx_results
    assert r.status == LIVE_FAIL
    assert "before its transaction reached the network" in r.reason


@pytest.mark.asyncio
async def test_one_modules_placeholder_no_longer_hides_anothers() -> None:
    pack = _pack(
        [_rec("failed", 100.0, validated=False),
         _rec("failed", 110.0, module="checks_101", validated=False)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True),
         CompletedModule(module_id="checks_101", completed_at=300.0, verified=False)],
    )
    statuses = sorted(r.status for r in (await _verify(pack)).tx_results)
    assert statuses == sorted([LIVE_SKIPPED, LIVE_FAIL])


@pytest.mark.asyncio
async def test_a_failure_after_the_passing_run_is_not_superseded() -> None:
    pack = _pack(
        [_rec("failed", 400.0, validated=False)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True)],
    )
    [r] = (await _verify(pack)).tx_results
    assert r.status == LIVE_FAIL


@pytest.mark.asyncio
async def test_a_superseded_tec_must_be_on_the_ledger_as_recorded() -> None:
    pack = _pack(
        [_rec(TEC, 100.0, validated=True)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True)],
    )
    [r] = (await _verify(pack)).tx_results
    assert (r.status, r.reason) == (
        LIVE_PASS, "Earlier run's failure, validated on-ledger: tecNO_PERMISSION.")


@pytest.mark.asyncio
async def test_a_superseded_record_the_ledger_contradicts_fails() -> None:
    """A record claiming a failure whose hash is a success on the ledger."""
    pack = _pack(
        [_rec(OK, 100.0, validated=True)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True)],
    )
    [r] = (await _verify(pack)).tx_results
    assert r.status == LIVE_FAIL
    assert "an earlier run's failure" in r.reason


@pytest.mark.asyncio
async def test_a_superseded_record_not_on_the_ledger_is_skipped() -> None:
    """A pre-2.7.1 record that doesn't say whether it validated, and isn't found."""
    pack = _pack(
        [_rec("C" * 64, 100.0)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True)],
    )
    [r] = (await _verify(pack)).tx_results
    assert (r.status, r.reason) == (
        LIVE_SKIPPED, "Earlier run's failure not on the ledger (a tem or tef never is).")


def test_expected_rejections_are_not_superseded() -> None:
    claims = rep._iter_pack_tx_claims(_pack(
        [_rec(TEC, 100.0, validated=True, expected=True)],
        [CompletedModule(module_id="clawback_101", completed_at=300.0, verified=True)],
    ))
    assert claims[0]["superseded"] is False


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), ("", None), ("not a time", None), (5, None),
    ("2026-10-21T12:00:00+00:00", "2026-10-21T12:00:00+00:00"),
    ("2026-10-21T12:00:00", "2026-10-21T12:00:00+00:00"),  # naive reads as UTC
])
def test_pack_timestamps_parse(value, expected) -> None:
    when = rep._parse_iso(value)
    assert (when.isoformat() if when else None) == expected
