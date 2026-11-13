"""After a test network reset: what the lab records, reports and advises.

The verify side (the RESET verdict) is in test_network_reset.py. This file
covers the learner's own lab: seeing the reset, knowing which completed
modules lost their on-ledger results, and the doctor and recovery guidance.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import xrpl_lab.reporting as rep
from xrpl_lab import doctor, resets
from xrpl_lab.cli import main
from xrpl_lab.modules import ModuleDef
from xrpl_lab.runner import run_module
from xrpl_lab.state import (
    CompletedModule,
    LabState,
    LedgerEpoch,
    LedgerMark,
    TxRecord,
    _merge_append_only,
    load_state,
    save_state,
)
from xrpl_lab.transport.base import NetworkInfo
from xrpl_lab.transport.dry_run import DryRunTransport
from xrpl_lab.workshop import diagnose_recovery

FIXTURE = Path(__file__).parent / "fixtures" / "proof_pack_sealed_by_2_7_9.json"
NOV_06 = datetime(2026, 11, 6, tzinfo=UTC).timestamp()
NOV_25_NOON = datetime(2026, 11, 25, 12, 0, tzinfo=UTC).timestamp()
NOV_28 = datetime(2026, 11, 28, tzinfo=UTC).timestamp()
DEC_01 = datetime(2026, 12, 1, tzinfo=UTC)
BEFORE = datetime(2026, 11, 20, tzinfo=UTC)


class _Ledger(DryRunTransport):
    def __init__(self, *, index: int | None = 4_200_000, connected: bool = True,
                 boom: bool = False, network: str = "testnet"):
        super().__init__()
        self._index, self._connected, self._boom, self._network = index, connected, boom, network

    @property
    def network_name(self) -> str:
        return self._network

    async def get_network_info(self) -> NetworkInfo:
        if self._boom:
            raise RuntimeError("rpc down")
        return NetworkInfo(network=self._network, rpc_url="none",
                           connected=self._connected, ledger_index=self._index)


def _tx(module: str, when: float, *, network: str = "testnet", txid: str | None = None,
        validated: bool | None = True, success: bool = True) -> TxRecord:
    return TxRecord(txid=txid or f"{module}-{when}", module_id=module, timestamp=when,
                    network=network, success=success, validated=validated)


def _state(*txs: TxRecord, completed: tuple[str, ...] = ("m1", "m2")) -> LabState:
    s = LabState()
    s.wallet_address = "rLEARNER"
    s.completed_modules = [CompletedModule(module_id=m, completed_at=NOV_06) for m in completed]
    s.tx_index = list(txs)
    return s


@pytest.fixture
def after_reset(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: DEC_01)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "home")
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    monkeypatch.delenv("XRPL_LAB_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── the lab sees a reset for itself ───────────────────────────────────


def test_a_much_lower_index_closes_the_epoch_and_starts_the_mark_again():
    s = LabState()
    s.note_ledger("testnet", 4_200_000)
    old_seen = s.ledger_marks["testnet"].seen_at
    s.note_ledger("testnet", 300)
    assert s.ledger_marks["testnet"].validated_ledger_index == 300
    (epoch,) = s.ledger_epochs["testnet"]
    assert (epoch.last_index, epoch.last_seen_at) == (4_200_000, old_seen)
    assert epoch.reset_seen_at >= old_seen
    s.note_ledger("testnet", 900)  # the new epoch's mark grows as usual
    assert s.ledger_marks["testnet"].validated_ledger_index == 900
    assert len(s.ledger_epochs["testnet"]) == 1


def test_server_lag_is_not_a_reset():
    s = LabState()
    s.note_ledger("testnet", 4_200_000)
    s.note_ledger("testnet", 4_199_990)
    assert s.ledger_epochs == {}
    assert s.ledger_marks["testnet"].validated_ledger_index == 4_200_000


def test_two_resets_are_two_epochs_and_survive_a_round_trip():
    s = LabState()
    for index in (4_200_000, 300, 2_000_000, 50):
        s.note_ledger("devnet", index)
    assert [e.last_index for e in s.ledger_epochs["devnet"]] == [4_200_000, 2_000_000]
    again = LabState.model_validate_json(s.model_dump_json())
    assert again.ledger_epochs == s.ledger_epochs


def test_a_state_file_from_before_epochs_still_loads():
    old = LabState().model_dump()
    old.pop("ledger_epochs")
    assert LabState.model_validate(old).ledger_epochs == {}


def _epoch(last_index: int, reset_seen_at: float) -> LedgerEpoch:
    return LedgerEpoch(last_index=last_index, last_seen_at=reset_seen_at - 100,
                       reset_seen_at=reset_seen_at)


def test_merging_states_unions_the_epochs_in_order():
    mine, disk = LabState(), LabState()
    mine.ledger_epochs["testnet"] = [_epoch(9, 500.0)]
    disk.ledger_epochs["testnet"] = [_epoch(9, 500.0), _epoch(5, 200.0)]
    disk.ledger_epochs["devnet"] = [_epoch(7, 300.0)]
    _merge_append_only(mine, disk)
    assert [e.reset_seen_at for e in mine.ledger_epochs["testnet"]] == [200.0, 500.0]
    assert [e.last_index for e in mine.ledger_epochs["devnet"]] == [7]


def test_merge_takes_the_other_copys_mark_when_this_one_has_none():
    mine, disk = LabState(), LabState()
    disk.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=10, seen_at=1.0)
    _merge_append_only(mine, disk)
    assert mine.ledger_marks["testnet"].validated_ledger_index == 10


def test_merge_keeps_the_post_reset_mark_over_a_stale_higher_one():
    """A stale copy with the old high mark must not undo the reset."""
    fresh, stale = LabState(), LabState()
    fresh.ledger_epochs["testnet"] = [_epoch(4_200_000, 500.0)]
    fresh.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=300, seen_at=500.0)
    stale.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=400.0)
    _merge_append_only(fresh, stale)
    assert fresh.ledger_marks["testnet"].validated_ledger_index == 300
    assert len(fresh.ledger_epochs["testnet"]) == 1

    # And the other way round: the stale copy merging the fresh one adopts it.
    stale2 = LabState()
    stale2.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=400.0)
    fresh2 = LabState()
    fresh2.ledger_epochs["testnet"] = [_epoch(4_200_000, 500.0)]
    fresh2.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=300, seen_at=500.0)
    _merge_append_only(stale2, fresh2)
    assert stale2.ledger_marks["testnet"].validated_ledger_index == 300


def test_merge_within_one_epoch_keeps_the_higher_index_without_a_false_reset():
    mine, disk = LabState(), LabState()
    mine.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=2.0)
    disk.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=10, seen_at=1.0)
    _merge_append_only(mine, disk)
    assert mine.ledger_marks["testnet"].validated_ledger_index == 4_200_000
    assert mine.ledger_epochs == {}


def _module(module_id: str = "m1") -> ModuleDef:
    return ModuleDef(id=module_id, title="T", time="1 min", level="beginner",
                     requires=[], produces=["nothing"], checks=[], steps=[], raw_body="")


def test_a_run_reads_the_ledger_before_its_first_step(home):
    s = _state(_tx("m1", NOV_06), completed=("m1",))
    s.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=NOV_06)
    save_state(s)
    # m1 is already complete, so the run stops straight after the reading.
    assert asyncio.run(run_module(_module("m1"), _Ledger(index=300))) is True
    saved = load_state()
    assert saved.ledger_marks["testnet"].validated_ledger_index == 300
    assert [e.last_index for e in saved.ledger_epochs["testnet"]] == [4_200_000]


def test_a_run_goes_on_when_the_reading_cannot_be_saved(home, monkeypatch):
    s = _state(_tx("m1", NOV_06), completed=("m1",))
    save_state(s)

    def boom(_state):
        raise OSError("disk full")

    monkeypatch.setattr("xrpl_lab.runner.save_state", boom)
    assert asyncio.run(run_module(_module("m1"), _Ledger(index=300))) is True


def test_a_dry_run_reads_no_public_ledger(home):
    save_state(_state(_tx("m1", NOV_06), completed=("m1",)))
    asyncio.run(run_module(_module("m2"), DryRunTransport(), dry_run=True))
    saved = load_state()
    assert saved.ledger_marks == {} and saved.ledger_epochs == {}


# ── the proof pack carries the resets the lab saw ─────────────────────


def test_a_pack_lists_the_resets_seen_inside_its_hash():
    s = _state()
    s.ledger_epochs["testnet"] = [
        LedgerEpoch(last_index=4_200_000, last_seen_at=NOV_06, reset_seen_at=NOV_25_NOON),
    ]
    s.ledger_epochs["devnet"] = []
    pack = rep.generate_proof_pack(s)
    assert pack["ledger_resets_seen"] == {"testnet": [{
        "last_index": 4_200_000,
        "last_seen_at": "2026-11-06T00:00:00+00:00",
        "reset_seen_at": "2026-11-25T12:00:00+00:00",
    }]}
    assert rep.verify_proof_pack(pack)[0] is True
    assert "ledger_resets_seen" not in rep.generate_proof_pack(_state())


def _pack_with_seen(seen) -> dict:
    pack = json.loads(FIXTURE.read_text(encoding="utf-8"))  # records from 2026-11-06
    pack["ledger_resets_seen"] = seen
    return pack


def _live(pack: dict):
    return asyncio.run(rep.verify_proof_pack_live(pack, transport=_Ledger()))


def test_verify_accepts_the_packs_own_record_of_a_reset(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE)  # no announced reset yet
    res = _live(_pack_with_seen({"testnet": [{"reset_seen_at": "2026-11-10T00:00:00+00:00"}]}))
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_RESET]
    assert "This pack records that Testnet was reset (seen on 2026-11-10)" in (
        res.tx_results[0].reason
    )
    assert res.overall_passed is False  # still never a pass


@pytest.mark.parametrize(
    "seen",
    [
        {"testnet": [{"reset_seen_at": "2026-11-01T00:00:00+00:00"}]},  # before the records
        {"devnet": [{"reset_seen_at": "2026-11-10T00:00:00+00:00"}]},   # another network
        {"testnet": "junk"}, {"testnet": ["junk"]}, {"testnet": [{"reset_seen_at": 5}]},
        "junk",
    ],
)
def test_a_reset_record_that_does_not_cover_the_tx_changes_nothing(monkeypatch, seen):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE)
    res = _live(_pack_with_seen(seen))
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]


def test_an_undated_tx_is_covered_by_a_reset_the_pack_records(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE)
    pack = {"address": "rA", "network": "testnet",
            "completed_modules": [{"module_id": "m", "txids": ["C" * 64]}],
            "ledger_resets_seen": {"testnet": [{"reset_seen_at": "2026-11-10T00:00:00+00:00"}]}}
    assert _live(pack).tx_results[0].status == rep.LIVE_RESET


# ── which completed modules a reset wiped ─────────────────────────────


def test_nothing_is_wiped_before_the_reset():
    s = _state(_tx("m1", NOV_06))
    assert resets.wiped_by_reset(s, now=BEFORE) == []


def test_the_announced_reset_wipes_modules_run_before_it():
    s = _state(_tx("m1", NOV_06), _tx("m2", NOV_06))
    (w,) = resets.wiped_by_reset(s, now=DEC_01)
    assert (w.network, w.modules, w.nothing_since) == ("testnet", ("m1", "m2"), True)
    assert w.label == "Testnet was reset on 2026-11-25"
    assert w.source == "https://xrpl.org/blog/2026/testnet-devnet-reset"
    assert w.since == datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def test_a_module_re_run_after_the_reset_is_no_longer_wiped():
    s = _state(_tx("m1", NOV_06), _tx("m1", NOV_28), _tx("m2", NOV_06))
    (w,) = resets.wiped_by_reset(s, now=DEC_01)
    assert (w.modules, w.nothing_since) == (("m2",), False)
    s.tx_index.append(_tx("m2", NOV_28))
    assert resets.wiped_by_reset(s, now=DEC_01) == []


def test_only_real_validated_records_of_completed_modules_count():
    s = _state(
        _tx("m1", NOV_06, network="dry-run"),          # never on a public ledger
        _tx("m2", NOV_06, txid="failed", success=False),
        _tx("m2", NOV_06, validated=False, success=False),
        _tx("not_done", NOV_06),                        # module not completed
    )
    assert resets.wiped_by_reset(s, now=DEC_01) == []


def test_a_reset_the_lab_saw_on_the_day_gives_the_exact_moment():
    """Re-running on the reset day itself clears the module at once."""
    s = _state(_tx("m1", NOV_06), _tx("m1", NOV_25_NOON + 60), _tx("m2", NOV_06))
    s.ledger_epochs["testnet"] = [
        LedgerEpoch(last_index=4_200_000, last_seen_at=NOV_06, reset_seen_at=NOV_25_NOON),
    ]
    (w,) = resets.wiped_by_reset(s, now=datetime(2026, 11, 25, 13, 0, tzinfo=UTC))
    assert w.since == datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    assert (w.modules, w.nothing_since) == (("m2",), False)
    assert w.label == "Testnet was reset on 2026-11-25"


def test_an_unannounced_reset_the_lab_saw_is_reported_by_its_date():
    s = _state(_tx("m1", NOV_06, network="devnet"), completed=("m1",))
    s.ledger_epochs["devnet"] = [
        LedgerEpoch(last_index=9_000_000, last_seen_at=NOV_06,
                    reset_seen_at=datetime(2026, 11, 10, tzinfo=UTC).timestamp()),
    ]
    (w,) = resets.wiped_by_reset(s, now=BEFORE)
    assert (w.network, w.source) == ("devnet", "")
    assert w.label == "Devnet was reset (seen on 2026-11-10)"


def test_a_reset_seen_after_the_announced_one_is_the_latest():
    later = datetime(2027, 3, 1, tzinfo=UTC)
    s = _state(_tx("m1", NOV_28), completed=("m1",))
    s.ledger_epochs["testnet"] = [
        LedgerEpoch(last_index=800_000, last_seen_at=NOV_28, reset_seen_at=later.timestamp()),
    ]
    (w,) = resets.wiped_by_reset(s, now=datetime(2027, 3, 2, tzinfo=UTC))
    assert w.since == later
    assert w.label == "Testnet was reset (seen on 2027-03-01)"


def test_an_old_seen_reset_does_not_hide_the_announced_one():
    s = _state(_tx("m1", NOV_06), completed=("m1",))
    s.ledger_epochs["testnet"] = [
        LedgerEpoch(last_index=9, last_seen_at=1.0,
                    reset_seen_at=datetime(2026, 10, 1, tzinfo=UTC).timestamp()),
    ]
    (w,) = resets.wiped_by_reset(s, now=DEC_01)
    assert w.label == "Testnet was reset on 2026-11-25"


# ── recovery ──────────────────────────────────────────────────────────


def test_recovery_says_fund_first_then_re_run(after_reset, home):
    hints = diagnose_recovery(_state(_tx("m1", NOV_06), _tx("m2", NOV_06)))
    reset_hints = [h for h in hints if "was reset" in h.situation]
    assert [h.command for h in reset_hints] == ["xrpl-lab fund", "xrpl-lab run m1 --force"]
    assert "your wallet was erased with it" in reset_hints[0].situation
    assert "2 completed modules lost on-ledger results" in reset_hints[1].situation
    assert "Affected: m1, m2." in reset_hints[1].explanation
    assert "RESET" in reset_hints[1].explanation


def test_recovery_skips_the_fund_hint_once_something_ran_after_the_reset(after_reset, home):
    s = _state(_tx("m1", NOV_06), _tx("m1", NOV_28), _tx("m2", NOV_06))
    reset_hints = [h for h in diagnose_recovery(s) if "was reset" in h.situation]
    assert [h.command for h in reset_hints] == ["xrpl-lab run m2 --force"]
    assert "1 completed module lost on-ledger results" in reset_hints[0].situation


def test_recovery_says_nothing_about_a_reset_before_it_happens(home):
    hints = diagnose_recovery(_state(_tx("m1", NOV_06)))
    assert not [h for h in hints if "was reset" in h.situation]


def test_the_recovery_command_prints_the_reset_hints(after_reset, home):
    save_state(_state(_tx("m1", NOV_06)))
    out = CliRunner().invoke(main, ["recovery"])
    text = " ".join(out.stdout.split())
    assert out.exit_code == 0
    assert "Testnet was reset on 2026-11-25" in text
    assert "xrpl-lab fund" in text and "xrpl-lab run m1 --force" in text


# ── doctor ────────────────────────────────────────────────────────────


def _doctor_ledger(monkeypatch, ledger: DryRunTransport) -> None:
    monkeypatch.setattr("xrpl_lab.transport.xrpl_testnet.XRPLTestnetTransport", lambda: ledger)


def _reset_check(monkeypatch, ledger: DryRunTransport | None = None) -> doctor.Check:
    _doctor_ledger(monkeypatch, ledger or _Ledger())
    return asyncio.run(doctor._check_network_reset())


def test_doctor_warns_about_work_the_announced_reset_wiped(after_reset, home, monkeypatch):
    save_state(_state(_tx("m1", NOV_06), _tx("m2", NOV_06)))
    c = _reset_check(monkeypatch)
    assert (c.name, c.passed, c.severity) == ("Network reset", False, "warn")
    assert "Testnet was reset on 2026-11-25. 2 completed modules lost" in c.detail
    assert "Your wallet was erased too." in c.detail
    assert "xrpl-lab recovery" in c.hint


def test_doctor_counts_one_module_and_drops_the_wallet_line_once_re_run(
    after_reset, home, monkeypatch,
):
    save_state(_state(_tx("m1", NOV_06), _tx("m1", NOV_28), _tx("m2", NOV_06)))
    c = _reset_check(monkeypatch)
    assert "1 completed module lost on-ledger results." in c.detail
    assert "wallet was erased" not in c.detail


def test_doctor_passes_with_no_state_or_no_mark(home, monkeypatch):
    c = _reset_check(monkeypatch)
    assert (c.passed, c.detail) == (True, "No reset since your last run")


def test_doctor_catches_a_reset_no_run_has_seen_yet(home, monkeypatch):
    s = _state(_tx("m1", NOV_06))
    s.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=NOV_06)
    save_state(s)
    c = _reset_check(monkeypatch, _Ledger(index=640))
    assert (c.passed, c.severity) == (False, "warn")
    assert "its ledger is now 640, below the 4200000 seen before" in c.detail
    assert "xrpl-lab fund" in c.hint


@pytest.mark.parametrize(
    ("ledger", "detail"),
    [
        (_Ledger(index=4_200_900), "No reset since your last run"),
        (_Ledger(index=None, connected=False), "No reset since your last run"),
        (_Ledger(boom=True), "Not checked (ledger unreachable: RuntimeError)"),
        (_Ledger(network="local"), "No reset since your last run"),
    ],
)
def test_doctor_passes_when_the_ledger_shows_no_reset(home, monkeypatch, ledger, detail):
    s = _state(_tx("m1", NOV_06))
    s.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=4_200_000, seen_at=NOV_06)
    save_state(s)
    c = _reset_check(monkeypatch, ledger)
    assert (c.passed, c.detail) == (True, detail)


def test_doctor_leaves_an_unreadable_state_to_the_state_check(home, monkeypatch):
    def boom():
        raise ValueError("bad state")

    monkeypatch.setattr("xrpl_lab.state.load_state", boom)
    c = _reset_check(monkeypatch)
    assert (c.passed, c.detail) == (True, "Not checked (state unreadable: ValueError)")


def test_the_doctor_report_includes_the_reset_check(home, monkeypatch):
    _doctor_ledger(monkeypatch, _Ledger())

    async def _ok(name):
        return doctor.Check(name, True)

    monkeypatch.setattr(doctor, "_check_rpc", lambda: _ok("RPC endpoint"))
    monkeypatch.setattr(doctor, "_check_faucet", lambda: _ok("Faucet"))
    report = asyncio.run(doctor.run_doctor())
    assert "Network reset" in [c.name for c in report.checks]


# ── help ──────────────────────────────────────────────────────────────


def test_verify_artifact_help_lists_the_exit_codes():
    out = CliRunner().invoke(main, ["verify-artifact", "--help"])
    text = " ".join(out.stdout.split())
    assert "Exit codes: 0 verified; 1" in text
    assert "4 the test network was reset" in text and "(not a pass)" in text
