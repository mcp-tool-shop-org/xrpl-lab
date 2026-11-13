"""A test network reset after a proof pack was issued.

Testnet and Devnet are wiped on 2026-11-25. A pack issued before that keeps an
intact hash, but its txids are on no ledger afterwards. Live verification must
say so ("can no longer be checked") without calling the pack verified and
without calling it forged.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

import xrpl_lab.reporting as rep
from xrpl_lab import resets, runner
from xrpl_lab.api.routes import _live_to_schema
from xrpl_lab.cli import EXIT_LEDGER_RESET, _verify_exit_code, main
from xrpl_lab.state import LabState, LedgerMark, _merge_append_only
from xrpl_lab.transport.base import NetworkInfo, TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

FIXTURE = Path(__file__).parent / "fixtures" / "proof_pack_sealed_by_2_7_9.json"
TX_A = "A" * 64
TX_B = "B" * 64
TX_C = "C" * 64
RESET_DAY = date(2026, 11, 25)
AFTER_RESET = datetime(2026, 12, 1, tzinfo=UTC)
BEFORE_RESET = datetime(2026, 11, 20, tzinfo=UTC)


def _old_pack() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _seal(pack: dict) -> dict:
    import hashlib

    body = {k: v for k, v in pack.items() if k != "sha256"}
    content = json.dumps(body, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return pack


class _Ledger(DryRunTransport):
    """A fixture-backed ledger with a settable validated ledger index."""

    def __init__(self, fixtures=None, *, index: int | None = 99_999_999,
                 connected: bool = True, boom: bool = False, network: str = "testnet"):
        super().__init__()
        self.set_tx_fixtures({t.txid: t for t in (fixtures or [])})
        self._index = index
        self._connected = connected
        self._boom = boom
        self._network = network
        self.info_calls = 0

    @property
    def network_name(self) -> str:
        return self._network

    async def get_network_info(self) -> NetworkInfo:
        self.info_calls += 1
        if self._boom:
            raise RuntimeError("rpc down")
        return NetworkInfo(
            network=self._network, rpc_url="none",
            connected=self._connected, ledger_index=self._index,
        )


def _ok(txid: str, account: str = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe") -> TxInfo:
    return TxInfo(txid=txid, tx_type="Payment", account=account,
                  result_code="tesSUCCESS", validated=True)


@pytest.fixture
def after_reset(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: AFTER_RESET)


@pytest.fixture
def before_reset(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE_RESET)


def _live(pack: dict, ledger: DryRunTransport) -> rep.LiveVerificationResult:
    return asyncio.run(rep.verify_proof_pack_live(pack, transport=ledger))


# ── the known-reset list ──────────────────────────────────────────────


def test_the_2026_11_25_reset_is_listed_for_both_test_networks():
    listed = {(r.network, r.day) for r in resets.KNOWN_RESETS}
    assert listed == {("testnet", RESET_DAY), ("devnet", RESET_DAY)}
    assert all(r.source.startswith("https://xrpl.org/") for r in resets.KNOWN_RESETS)


def test_a_reset_day_spans_every_timezone():
    r = resets.KnownReset("testnet", RESET_DAY, "src")
    # The 25th begins at UTC+14 and ends at UTC-12.
    assert r.starts == datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
    assert r.ends == datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    assert r.label() == "Testnet was reset on 2026-11-25"


def test_no_reset_counts_before_its_day_begins():
    just_before = datetime(2026, 11, 24, 9, 59, tzinfo=UTC)
    old = datetime(2026, 11, 1, tzinfo=UTC)
    assert resets.known_reset_after("testnet", old, now=just_before) is None
    assert resets.known_reset_after("testnet", None, now=just_before) is None


def test_a_reset_covers_what_was_recorded_before_it_ended():
    old = datetime(2026, 11, 1, tzinfo=UTC)
    on_the_day = datetime(2026, 11, 25, 18, 0, tzinfo=UTC)
    for recorded in (old, on_the_day, None):
        found = resets.known_reset_after("testnet", recorded, now=AFTER_RESET)
        assert found is not None and found.day == RESET_DAY


def test_a_reset_does_not_cover_later_records_or_other_networks():
    later = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    assert resets.known_reset_after("testnet", later, now=AFTER_RESET) is None
    assert resets.known_reset_after("mainnet", None, now=AFTER_RESET) is None
    assert resets.known_reset_after("local", None, now=AFTER_RESET) is None


def test_the_suite_pins_the_reset_clock_before_any_listed_reset():
    pinned = resets._now()
    assert all(pinned < r.starts for r in resets.KNOWN_RESETS)


def test_the_unpinned_clock_reads_the_real_time(monkeypatch):
    monkeypatch.undo()  # drop the suite's pin for this test
    now = resets._now()
    assert now.tzinfo is UTC
    assert abs(datetime.now(tz=UTC) - now) < timedelta(seconds=5)


@pytest.mark.parametrize(
    ("recorded", "current", "backwards"),
    [(5_000_000, 120, True), (5_000_000, 5_000_001, False), (5_000_000, 5_000_000, False),
     # A server a few ledgers behind is lag, not a reset.
     (5_000_000, 4_999_990, False), (5_000_000, 4_999_000, False),
     (5_000_000, 4_998_999, True),
     (None, 120, False), (5_000_000, None, False), (0, 120, False)],
)
def test_ledger_went_backwards(recorded, current, backwards):
    assert resets.ledger_went_backwards(recorded, current) is backwards


# ── the ledger mark in state ──────────────────────────────────────────


def test_state_keeps_the_highest_ledger_index_per_network():
    s = LabState()
    for network, index in [("testnet", 100), ("testnet", 50), ("testnet", 300),
                           ("devnet", 7), ("", 9), ("testnet", None), ("testnet", 0),
                           ("testnet", -4)]:
        s.note_ledger(network, index)
    assert {n: m.validated_ledger_index for n, m in s.ledger_marks.items()} == {
        "testnet": 300, "devnet": 7,
    }
    again = LabState.model_validate_json(s.model_dump_json())
    assert again.ledger_marks == s.ledger_marks


def test_a_state_file_from_before_marks_still_loads():
    old = LabState().model_dump()
    old.pop("ledger_marks")
    assert LabState.model_validate(old).ledger_marks == {}


def test_merging_states_keeps_the_larger_mark():
    mine, disk = LabState(), LabState()
    mine.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=10, seen_at=1.0)
    disk.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=90, seen_at=2.0)
    disk.ledger_marks["devnet"] = LedgerMark(validated_ledger_index=5, seen_at=3.0)
    _merge_append_only(mine, disk)
    assert mine.ledger_marks["testnet"].validated_ledger_index == 90
    assert mine.ledger_marks["devnet"].validated_ledger_index == 5


def test_a_run_on_a_public_test_network_records_the_ledger_index():
    s = LabState()
    asyncio.run(runner._note_ledger_mark(s, _Ledger(index=4_200_000)))
    assert s.ledger_marks["testnet"].validated_ledger_index == 4_200_000


@pytest.mark.parametrize(
    "ledger",
    [
        DryRunTransport(),                      # a dry run has no public ledger
        _Ledger(network="local"),               # nor does a local node
        _Ledger(connected=False, index=None),   # could not reach the network
        _Ledger(boom=True),                     # the read failed
    ],
)
def test_no_mark_without_a_public_ledger_reading(ledger):
    s = LabState()
    asyncio.run(runner._note_ledger_mark(s, ledger))
    assert s.ledger_marks == {}


# ── the proof pack ────────────────────────────────────────────────────


def test_a_pack_sealed_by_2_7_9_still_verifies():
    """A pack made before this change has no ledger_marks; its hash must hold."""
    pack = _old_pack()
    assert pack["version"] == "2.7.9" and "ledger_marks" not in pack
    assert rep.verify_proof_pack(pack) == (True, "Integrity verified")


def test_a_pack_without_marks_has_the_same_fields_as_before():
    s = LabState()
    s.wallet_address = "rA"
    pack = rep.generate_proof_pack(s)
    assert "ledger_marks" not in pack
    assert set(pack) == set(_old_pack())


def test_a_pack_carries_the_marks_inside_its_hash():
    s = LabState()
    s.wallet_address = "rA"
    s.ledger_marks["testnet"] = LedgerMark(
        validated_ledger_index=4_200_000, seen_at=1_794_000_000.0,
    )
    pack = rep.generate_proof_pack(s)
    assert pack["ledger_marks"] == {
        "testnet": {"validated_ledger_index": 4_200_000,
                    "seen_at": "2026-11-06T21:20:00+00:00"},
    }
    assert rep.verify_proof_pack(pack)[0] is True
    pack["ledger_marks"]["testnet"]["validated_ledger_index"] = 1
    assert rep.verify_proof_pack(pack)[0] is False


# ── live verification: the announced reset ────────────────────────────


def test_before_the_reset_a_missing_txid_is_a_failure(before_reset):
    res = _live(_old_pack(), _Ledger())
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]
    assert res.reset_count == 0 and res.ledger_reset is False
    assert "not found on the public ledger" in res.tx_results[0].reason


def test_after_the_reset_an_old_pack_cannot_be_checked_and_is_not_verified(after_reset):
    res = _live(_old_pack(), _Ledger())
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_RESET]
    # Not a pass, not a failure, and never "verified".
    assert res.overall_passed is False
    assert (res.passed_count, res.failed_count, res.reset_count) == (0, 0, 2)
    assert res.ledger_reset is True
    reason = res.tx_results[0].reason
    assert "Can no longer be checked on-ledger" in reason
    assert "Testnet was reset on 2026-11-25" in reason
    assert "not that the transaction happened" in reason
    assert "Ledger reset after issuance: 2 transaction(s)" in res.note
    assert "offline hash is intact" in res.note
    d = res.to_dict()
    assert d["reset"] == 2 and d["ledger_reset"] is True and d["overall_passed"] is False
    assert "not_found" not in d["tx_results"][0]
    assert d["tx_results"][0]["validated"] is False


def test_a_forged_pack_dated_before_the_reset_is_not_verified_either(after_reset):
    """Made-up txids with old dates read as RESET too, so RESET is never a pass."""
    forged = _old_pack()
    forged["transactions"][0]["txid"] = "F" * 64
    _seal(forged)
    assert rep.verify_proof_pack(forged)[0] is True
    res = _live(forged, _Ledger())
    assert res.overall_passed is False
    assert res.passed_count == 0


def test_a_txid_recorded_after_the_reset_still_fails_when_missing(after_reset):
    pack = _old_pack()
    pack["transactions"][1]["timestamp"] = "2026-11-28T09:00:00+00:00"
    res = _live(pack, _Ledger())
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_FAIL]
    assert res.overall_passed is False


def test_a_txid_still_on_the_ledger_passes_after_the_reset(after_reset):
    res = _live(_old_pack(), _Ledger([_ok(TX_A), _ok(TX_B)]))
    assert [r.status for r in res.tx_results] == [rep.LIVE_PASS, rep.LIVE_PASS]
    assert res.overall_passed is True and res.reset_count == 0 and res.note == ""


def test_devnet_is_covered_and_an_undated_legacy_pack_too(after_reset):
    legacy = {"address": "rA", "network": "devnet",
              "completed_modules": [{"module_id": "m", "txids": [TX_C]}]}
    res = _live(legacy, _Ledger(network="devnet"))
    assert res.tx_results[0].status == rep.LIVE_RESET
    assert "Devnet was reset on 2026-11-25" in res.tx_results[0].reason


def test_an_expected_rejection_lost_to_the_reset_is_reset_not_failed(after_reset):
    pack = _old_pack()
    pack["transactions"][0].update(success=False, expected=True, validated=True)
    res = _live(pack, _Ledger())
    assert res.tx_results[0].status == rep.LIVE_RESET


def test_a_wrong_account_is_still_a_failure_after_the_reset(after_reset):
    res = _live(_old_pack(), _Ledger([_ok(TX_A, account="rSOMEONE_ELSE"), _ok(TX_B)]))
    assert res.tx_results[0].status == rep.LIVE_FAIL
    assert res.failed_count == 1 and res.reset_count == 0


def test_a_certificate_with_txids_gets_the_same_verdict(after_reset):
    cert = {"address": "rA", "network": "testnet",
            "transactions": [{"txid": TX_A, "network": "testnet",
                              "timestamp": "2026-11-06T00:00:00+00:00"}]}
    res = asyncio.run(rep.verify_certificate_live(cert, transport=_Ledger()))
    assert res.tx_results[0].status == rep.LIVE_RESET
    assert "this certificate can't be verified on-ledger" in res.note


# ── live verification: the ledger went backwards ──────────────────────


def _marked_pack(seen_at: str = "2026-11-10T00:00:00+00:00", index=4_200_000) -> dict:
    pack = _old_pack()
    pack["ledger_marks"] = {"testnet": {"validated_ledger_index": index, "seen_at": seen_at}}
    return pack


def test_a_ledger_below_the_recorded_index_means_an_unannounced_reset(before_reset):
    ledger = _Ledger(index=812)
    res = _live(_marked_pack(), ledger)
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_RESET]
    assert "validated ledger is now 812, below the 4200000 this pack recorded" in (
        res.tx_results[0].reason
    )
    assert res.overall_passed is False
    assert ledger.info_calls == 1  # read once per network, not once per txid


@pytest.mark.parametrize("index", [4_200_050, 4_200_000, 4_199_990])
def test_a_ledger_at_above_or_just_behind_the_recorded_index_is_no_reset(before_reset, index):
    res = _live(_marked_pack(), _Ledger(index=index))
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]


def test_a_txid_recorded_after_the_mark_is_not_excused_by_it(before_reset):
    # The mark was seen on 11-01; the records are from 11-06.
    res = _live(_marked_pack(seen_at="2026-11-01T00:00:00+00:00"), _Ledger(index=812))
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]


@pytest.mark.parametrize(
    "ledger", [_Ledger(boom=True), _Ledger(connected=False, index=None)],
)
def test_an_unreadable_ledger_index_gives_no_reset_signal(before_reset, ledger):
    res = _live(_marked_pack(), ledger)
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]


@pytest.mark.parametrize(
    "marks",
    ["junk", {"testnet": "junk"}, {"testnet": {"validated_ledger_index": "9"}},
     {"testnet": {"validated_ledger_index": True}}, {"devnet": {"validated_ledger_index": 9}}],
)
def test_malformed_or_other_network_marks_are_ignored(before_reset, marks):
    pack = _old_pack()
    pack["ledger_marks"] = marks
    res = _live(pack, _Ledger(index=1))
    assert [r.status for r in res.tx_results] == [rep.LIVE_FAIL, rep.LIVE_FAIL]


def test_a_mark_without_a_time_covers_every_record(before_reset):
    pack = _old_pack()
    pack["ledger_marks"] = {"testnet": {"validated_ledger_index": 4_200_000}}
    res = _live(pack, _Ledger(index=812))
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_RESET]


# ── the CLI ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("valid", "live", "result", "live_ok", "code"),
    [
        (False, True, None, False, 1),
        (True, False, None, True, 0),
        (True, True, None, True, 0),
        (True, True, None, False, 1),
    ],
)
def test_exit_codes_without_a_reset(valid, live, result, live_ok, code):
    assert _verify_exit_code(valid, live, result, live_ok) == code


def _cli(args: list[str]):
    return CliRunner().invoke(main, args)


def _flat(text: str) -> str:
    """Console output with its line wrapping removed."""
    return " ".join(text.split())


def _route_to(monkeypatch, ledger: DryRunTransport) -> None:
    monkeypatch.setattr("xrpl_lab.reporting._default_transport_factory", lambda net: ledger)


def test_cli_reports_a_reset_pack_as_unverifiable_with_exit_4(after_reset, monkeypatch):
    _route_to(monkeypatch, _Ledger())
    out = _cli(["verify-artifact", str(FIXTURE), "--live"])
    assert out.exit_code == EXIT_LEDGER_RESET == 4, out.stdout
    text = _flat(out.stdout)
    assert "Proof pack integrity verified" in text  # the offline hash
    assert "RESET" in text
    assert "CAN'T BE CHECKED (ledger reset after issuance)" in text
    assert "2 lost to the reset, 0 verified" in text
    assert "On-ledger verdict: PASS" not in text
    assert "On-ledger verdict: FAIL" not in text

    js = _cli(["verify-artifact", str(FIXTURE), "--live", "--json"])
    assert js.exit_code == 4
    body = json.loads(js.stdout)
    assert body["valid"] is True
    assert body["live_passed"] is False
    assert body["ledger_reset"] is True
    assert body["live"]["reset"] == 2 and body["live"]["passed"] == 0
    assert {t["status"] for t in body["live"]["tx_results"]} == {"RESET"}


def test_cli_a_failure_beside_a_reset_is_still_exit_1(after_reset, monkeypatch, tmp_path):
    pack = _old_pack()
    pack["transactions"][1]["timestamp"] = "2026-11-28T09:00:00+00:00"
    f = tmp_path / "p.json"
    f.write_text(json.dumps(_seal(pack)), encoding="utf-8")
    _route_to(monkeypatch, _Ledger())
    out = _cli(["verify-artifact", str(f), "--live"])
    assert out.exit_code == 1
    text = _flat(out.stdout)
    assert "On-ledger verdict: FAIL" in text
    assert "1 failed, 0 verified, 0 skipped, 1 lost to a ledger reset." in text
    assert json.loads(_cli(["verify-artifact", str(f), "--live", "--json"]).stdout)[
        "ledger_reset"
    ] is True


def test_cli_a_passing_pack_reports_no_reset(after_reset, monkeypatch):
    _route_to(monkeypatch, _Ledger([_ok(TX_A), _ok(TX_B)]))
    out = _cli(["verify-artifact", str(FIXTURE), "--live", "--json"])
    assert out.exit_code == 0
    body = json.loads(out.stdout)
    assert body["live_passed"] is True and body["ledger_reset"] is False


def test_cli_offline_verify_of_an_old_pack_is_unchanged(after_reset):
    out = _cli(["verify-artifact", str(FIXTURE)])
    assert out.exit_code == 0
    assert "Proof pack integrity verified" in out.stdout


# ── the dashboard API ─────────────────────────────────────────────────


def test_the_api_carries_the_reset_count_and_gives_no_explorer_link(after_reset):
    schema = _live_to_schema(_live(_old_pack(), _Ledger()))
    assert schema.reset == 2 and schema.ledger_reset is True
    assert schema.overall_passed is False
    assert [t.status for t in schema.tx_results] == ["RESET", "RESET"]
    assert [t.explorer_url for t in schema.tx_results] == ["", ""]
