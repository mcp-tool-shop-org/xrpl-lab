"""What a reset verdict rests on.

A txid missing after a network reset is not a failure, but who says there was
a reset matters:

* an announced reset that covers the tx's recorded time: independent -> RESET
* this lab's own state saw the reset:                     independent -> RESET
* only the pack says so (its marks, or its own record):   a claim -> UNCONFIRMED

None of them is ever a pass.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import xrpl_lab.reporting as rep
from xrpl_lab.api.routes import _live_to_schema
from xrpl_lab.cli import _own_state_or_none, main
from xrpl_lab.server import create_app
from xrpl_lab.state import LabState, LedgerEpoch, LedgerMark, save_state
from xrpl_lab.transport.base import NetworkInfo, TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

FIXTURE = Path(__file__).parent / "fixtures" / "proof_pack_sealed_by_2_7_9.json"
TX_A, TX_B = "A" * 64, "B" * 64
BEFORE_RESET = datetime(2026, 11, 20, tzinfo=UTC)   # the fixture's txs are from 11-06
AFTER_RESET = datetime(2026, 12, 1, tzinfo=UTC)
NOV_01 = datetime(2026, 11, 1, tzinfo=UTC).timestamp()
NOV_10 = datetime(2026, 11, 10, tzinfo=UTC).timestamp()
PACK_MARK = {"testnet": {"validated_ledger_index": 4_200_000,
                         "seen_at": "2026-11-10T00:00:00+00:00"}}
PACK_SEEN = {"testnet": [{"reset_seen_at": "2026-11-10T00:00:00+00:00"}]}


class _Ledger(DryRunTransport):
    def __init__(self, fixtures=None, *, index: int | None = 812, boom: bool = False):
        super().__init__()
        self.set_tx_fixtures({t.txid: t for t in (fixtures or [])})
        self._index, self._boom = index, boom

    @property
    def network_name(self) -> str:
        return "testnet"

    async def get_network_info(self) -> NetworkInfo:
        if self._boom:
            raise RuntimeError("rpc down")
        return NetworkInfo(network="testnet", rpc_url="none",
                           connected=self._index is not None, ledger_index=self._index)


def _ok(txid: str) -> TxInfo:
    return TxInfo(txid=txid, tx_type="Payment",
                  account="rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
                  result_code="tesSUCCESS", validated=True)


def _seal(pack: dict) -> dict:
    import hashlib

    body = {k: v for k, v in pack.items() if k != "sha256"}
    content = json.dumps(body, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return pack


def _pack(**extra) -> dict:
    pack = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pack.update(extra)
    return _seal(pack)


def _own(*, epoch_at: float | None = None, mark: tuple[int, float] | None = None) -> LabState:
    s = LabState()
    if epoch_at is not None:
        s.ledger_epochs["testnet"] = [
            LedgerEpoch(last_index=4_200_000, last_seen_at=epoch_at - 60, reset_seen_at=epoch_at),
        ]
    if mark is not None:
        s.ledger_marks["testnet"] = LedgerMark(validated_ledger_index=mark[0], seen_at=mark[1])
    return s


def _live(pack: dict, ledger: DryRunTransport | None = None, own_state=None):
    return asyncio.run(rep.verify_proof_pack_live(
        pack, transport=ledger or _Ledger(), own_state=own_state,
    ))


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """An empty lab home, and a clock before any announced reset."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "labhome")
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    monkeypatch.delenv("XRPL_LAB_HOME", raising=False)
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE_RESET)
    return tmp_path


@pytest.fixture
def after_reset(monkeypatch):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: AFTER_RESET)


# ── the three signals ─────────────────────────────────────────────────


def test_an_announced_reset_is_an_independent_signal(after_reset):
    res = _live(_pack())
    assert {r.status for r in res.tx_results} == {rep.LIVE_RESET}
    assert {r.reset_signal for r in res.tx_results} == {rep.SIGNAL_ANNOUNCED}
    assert res.reset_signal == "announced"
    assert (res.reset_count, res.unconfirmed_count) == (2, 0)


def test_a_reset_this_lab_saw_is_an_independent_signal():
    res = _live(_pack(), own_state=_own(epoch_at=NOV_10))
    assert {r.status for r in res.tx_results} == {rep.LIVE_RESET}
    assert res.reset_signal == "seen_by_this_lab"
    assert "This lab saw Testnet reset on 2026-11-10" in res.tx_results[0].reason
    assert "Can no longer be checked on-ledger" in res.tx_results[0].reason


def test_this_labs_own_mark_above_the_live_ledger_is_an_independent_signal():
    res = _live(_pack(), _Ledger(index=812), own_state=_own(mark=(4_200_000, NOV_10)))
    assert {r.status for r in res.tx_results} == {rep.LIVE_RESET}
    assert res.reset_signal == "seen_by_this_lab"
    assert "This lab last saw Testnet at ledger 4200000; it is now at 812" in (
        res.tx_results[0].reason
    )


@pytest.mark.parametrize(
    "own",
    [
        None,                                   # no lab state at all
        _own(),                                 # a lab that saw nothing
        _own(epoch_at=NOV_01),                  # a reset before the txs were recorded
        _own(mark=(4_200_000, NOV_01)),         # a mark from before the txs
        _own(mark=(900, NOV_10)),               # a mark the live ledger is not below
    ],
)
def test_a_lab_that_saw_no_reset_since_the_tx_gives_no_signal(own):
    res = _live(_pack(), _Ledger(index=812), own_state=own)
    assert {r.status for r in res.tx_results} == {rep.LIVE_FAIL}
    assert res.reset_signal == ""


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        ({"ledger_marks": PACK_MARK},
         "the pack records ledger 4200000 for Testnet, which is now at 812"),
        ({"ledger_resets_seen": PACK_SEEN},
         "the pack records that Testnet was reset (seen on 2026-11-10)"),
    ],
)
def test_a_reset_only_the_pack_claims_is_unconfirmed(extra, said):
    res = _live(_pack(**extra))
    assert {r.status for r in res.tx_results} == {rep.LIVE_UNCONFIRMED}
    assert {r.reset_signal for r in res.tx_results} == {rep.SIGNAL_PACK_CLAIM}
    reason = res.tx_results[0].reason
    assert reason.startswith(
        "UNCONFIRMED: the pack claims a reset that nothing else confirms."
    )
    assert said in reason and "anyone can write those fields" in reason
    assert res.reset_signal == "pack_claim"
    assert (res.reset_count, res.unconfirmed_count) == (0, 2)
    assert "only the pack itself says the network was reset" in res.note


def test_an_independent_signal_outranks_the_packs_claim(after_reset):
    """The same pack fields, but an announced reset covers the txs: RESET."""
    res = _live(_pack(ledger_marks=PACK_MARK, ledger_resets_seen=PACK_SEEN))
    assert {r.reset_signal for r in res.tx_results} == {rep.SIGNAL_ANNOUNCED}
    res = _live(_pack(ledger_resets_seen=PACK_SEEN), own_state=_own(epoch_at=NOV_10))
    assert {r.status for r in res.tx_results} == {rep.LIVE_RESET}


def test_the_weakest_signal_names_the_whole_result(after_reset):
    """One txid is covered by the announced reset, one only by the pack."""
    pack = _pack()
    pack["transactions"][1]["timestamp"] = "2026-11-28T09:00:00+00:00"
    pack["ledger_resets_seen"] = {"testnet": [{"reset_seen_at": "2026-12-05T00:00:00+00:00"}]}
    res = _live(_seal(pack))
    assert [r.status for r in res.tx_results] == [rep.LIVE_RESET, rep.LIVE_UNCONFIRMED]
    assert res.reset_signal == "pack_claim"
    assert (res.reset_count, res.unconfirmed_count) == (1, 1)
    assert "Ledger reset after issuance: 1 transaction(s)" in res.note
    assert "UNCONFIRMED: 1 transaction(s)" in res.note


# ── never a pass ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("clock", "extra", "own", "signal"),
    [
        (AFTER_RESET, {}, None, "announced"),
        (BEFORE_RESET, {}, _own(epoch_at=NOV_10), "seen_by_this_lab"),
        (BEFORE_RESET, {}, _own(mark=(4_200_000, NOV_10)), "seen_by_this_lab"),
        (BEFORE_RESET, {"ledger_marks": PACK_MARK}, None, "pack_claim"),
        (BEFORE_RESET, {"ledger_resets_seen": PACK_SEEN}, None, "pack_claim"),
    ],
)
def test_no_reset_path_is_ever_a_pass(monkeypatch, clock, extra, own, signal):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: clock)
    res = _live(_pack(**extra), own_state=own)
    assert res.reset_signal == signal
    assert res.overall_passed is False
    assert res.passed_count == 0 and res.failed_count == 0
    assert res.ledger_reset is True
    d = res.to_dict()
    assert d["overall_passed"] is False and d["reset_signal"] == signal
    assert d["reset"] + d["unconfirmed"] == 2
    assert {t["reset_signal"] for t in d["tx_results"]} == {signal}
    assert {t["validated"] for t in d["tx_results"]} == {False}


def test_a_passing_pack_has_no_reset_signal():
    res = _live(_pack(), _Ledger([_ok(TX_A), _ok(TX_B)], index=4_300_000))
    assert res.overall_passed is True
    d = res.to_dict()
    assert (d["reset_signal"], d["unconfirmed"], d["suspicious_ledger_marks"]) == ("", 0, [])
    assert {t["reset_signal"] for t in d["tx_results"]} == {""}


# ── a pack mark above the live ledger ─────────────────────────────────


def test_a_pack_mark_above_the_live_ledger_is_flagged_when_no_reset_is_known():
    """Its txids are all there, so the network was not reset: the mark is false."""
    res = _live(_pack(ledger_marks=PACK_MARK), _Ledger([_ok(TX_A), _ok(TX_B)], index=812))
    assert res.suspicious_ledger_marks == ["testnet"]
    assert "Suspicious ledger mark: the pack records a ledger index for Testnet" in res.note
    assert res.to_dict()["suspicious_ledger_marks"] == ["testnet"]
    # A flag, not a verdict: the transactions themselves were confirmed.
    assert {r.status for r in res.tx_results} == {rep.LIVE_PASS}


def test_the_flag_also_rides_with_an_unconfirmed_verdict():
    res = _live(_pack(ledger_marks=PACK_MARK), _Ledger(index=812))
    assert res.suspicious_ledger_marks == ["testnet"]
    assert res.note.startswith("UNCONFIRMED: 2 transaction(s)")
    assert "Suspicious ledger mark" in res.note


@pytest.mark.parametrize(
    ("clock", "own", "ledger"),
    [
        (AFTER_RESET, None, _Ledger(index=812)),                          # announced since
        (BEFORE_RESET, _own(epoch_at=NOV_10 + 60), _Ledger(index=812)),   # this lab saw it
        (BEFORE_RESET, None, _Ledger(index=4_200_500)),                   # not above
        (BEFORE_RESET, None, _Ledger(index=4_199_500)),                   # within server lag
        (BEFORE_RESET, None, _Ledger(index=None)),                        # index unreadable
        (BEFORE_RESET, None, _Ledger(boom=True)),
    ],
)
def test_a_mark_is_not_flagged_when_a_reset_is_known_or_it_is_not_above(
    monkeypatch, clock, own, ledger,
):
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: clock)
    res = _live(_pack(ledger_marks=PACK_MARK), ledger, own_state=own)
    assert res.suspicious_ledger_marks == []
    assert "Suspicious" not in res.note


def test_a_pack_without_marks_is_never_flagged():
    res = _live(_pack(), _Ledger([_ok(TX_A), _ok(TX_B)], index=812))
    assert res.suspicious_ledger_marks == [] and res.note == ""


# ── certificates take the same path ───────────────────────────────────


def test_a_certificate_with_txids_uses_the_same_signals():
    cert = {"address": "rA", "network": "testnet",
            "transactions": [{"txid": TX_A, "network": "testnet",
                              "timestamp": "2026-11-06T00:00:00+00:00"}],
            "ledger_resets_seen": PACK_SEEN}
    res = asyncio.run(rep.verify_certificate_live(cert, transport=_Ledger()))
    assert res.tx_results[0].status == rep.LIVE_UNCONFIRMED
    assert "only the certificate itself says the network was reset" in res.note
    res = asyncio.run(rep.verify_certificate_live(
        cert, transport=_Ledger(), own_state=_own(epoch_at=NOV_10),
    ))
    assert res.tx_results[0].status == rep.LIVE_RESET
    assert res.reset_signal == "seen_by_this_lab"


# ── the CLI ───────────────────────────────────────────────────────────


def _cli(args: list[str]):
    return CliRunner().invoke(main, args)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _file(tmp_path: Path, pack: dict) -> str:
    f = tmp_path / "pack.json"
    f.write_text(json.dumps(pack), encoding="utf-8")
    return str(f)


def _route_to(monkeypatch, ledger: DryRunTransport) -> None:
    monkeypatch.setattr("xrpl_lab.reporting._default_transport_factory", lambda net: ledger)


def test_cli_names_the_announced_signal(after_reset, monkeypatch, tmp_path):
    _route_to(monkeypatch, _Ledger())
    f = _file(tmp_path, _pack())
    out = _cli(["verify-artifact", f, "--live"])
    text = _flat(out.stdout)
    assert out.exit_code == 4
    assert "CAN'T BE CHECKED (ledger reset after issuance)" in text
    assert "Signal: announced." in text and "signal: announced" in text
    body = json.loads(_cli(["verify-artifact", f, "--live", "--json"]).stdout)
    assert body["reset_signal"] == "announced"
    assert body["live"]["reset_signal"] == "announced"


def test_cli_reports_a_pack_only_claim_as_unconfirmed_with_exit_4(monkeypatch, tmp_path):
    _route_to(monkeypatch, _Ledger())
    f = _file(tmp_path, _pack(ledger_resets_seen=PACK_SEEN))
    out = _cli(["verify-artifact", f, "--live"])
    text = _flat(out.stdout)
    assert out.exit_code == 4, out.stdout
    assert "On-ledger verdict: UNCONFIRMED: the pack claims a reset that nothing else" in text
    assert "? UNCONFIRMED" in text and "signal: pack_claim" in text
    assert "2 unconfirmed, 0 lost to a known reset, 0 verified" in text
    assert "On-ledger verdict: PASS" not in text
    js = _cli(["verify-artifact", f, "--live", "--json"])
    body = json.loads(js.stdout)
    assert js.exit_code == 4
    assert body["reset_signal"] == "pack_claim"
    assert body["live_passed"] is False and body["ledger_reset"] is True
    assert body["live"]["unconfirmed"] == 2 and body["live"]["reset"] == 0
    assert {t["status"] for t in body["live"]["tx_results"]} == {"UNCONFIRMED"}


def test_cli_uses_this_labs_own_state_as_a_signal(monkeypatch, tmp_path):
    save_state(_own(epoch_at=NOV_10))
    _route_to(monkeypatch, _Ledger())
    f = _file(tmp_path, _pack())
    body = json.loads(_cli(["verify-artifact", f, "--live", "--json"]).stdout)
    assert body["reset_signal"] == "seen_by_this_lab"
    assert {t["status"] for t in body["live"]["tx_results"]} == {"RESET"}


def test_cli_a_failure_beside_an_unconfirmed_claim_is_exit_1(monkeypatch, tmp_path):
    pack = _pack()
    pack["transactions"][1]["timestamp"] = "2026-11-12T00:00:00+00:00"  # after the claim
    pack["ledger_resets_seen"] = PACK_SEEN
    _route_to(monkeypatch, _Ledger())
    out = _cli(["verify-artifact", _file(tmp_path, _seal(pack)), "--live"])
    assert out.exit_code == 1
    assert "1 failed, 0 verified, 0 skipped, 0 lost to a ledger reset, 1 unconfirmed." in (
        _flat(out.stdout)
    )


def test_cli_a_verified_pack_reports_no_signal(monkeypatch, tmp_path):
    _route_to(monkeypatch, _Ledger([_ok(TX_A), _ok(TX_B)], index=4_300_000))
    out = _cli(["verify-artifact", _file(tmp_path, _pack()), "--live", "--json"])
    assert out.exit_code == 0
    assert json.loads(out.stdout)["reset_signal"] == ""


def test_cli_hash_failure_reports_no_signal(monkeypatch, tmp_path):
    pack = _pack()
    pack["address"] = "rEDITED"
    out = _cli(["verify-artifact", _file(tmp_path, pack), "--live", "--json"])
    assert out.exit_code == 1
    assert json.loads(out.stdout)["reset_signal"] == ""


def test_an_unreadable_lab_state_means_no_own_signal(monkeypatch):
    def boom():
        raise ValueError("bad state")

    monkeypatch.setattr("xrpl_lab.cli.load_state", boom)
    assert _own_state_or_none() is None


def test_verify_help_names_the_signals():
    text = _flat(_cli(["verify-artifact", "--help"]).stdout)
    assert "the output names the signal" in text and "(UNCONFIRMED)" in text


# ── the dashboard API ─────────────────────────────────────────────────


def test_the_api_schema_carries_the_signal_and_the_counts():
    schema = _live_to_schema(_live(_pack(ledger_marks=PACK_MARK)))
    assert (schema.unconfirmed, schema.reset, schema.reset_signal) == (2, 0, "pack_claim")
    assert schema.suspicious_ledger_marks == ["testnet"]
    assert schema.overall_passed is False and schema.ledger_reset is True
    assert [t.reset_signal for t in schema.tx_results] == ["pack_claim", "pack_claim"]
    assert [t.explorer_url for t in schema.tx_results] == ["", ""]


def test_the_verify_endpoint_reads_this_labs_own_state(monkeypatch):
    save_state(_own(epoch_at=NOV_10))
    _route_to(monkeypatch, _Ledger())
    resp = TestClient(create_app()).post("/api/verify?live=true", json=_pack())
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_passed"] is False
    assert data["live"]["reset_signal"] == "seen_by_this_lab"
    assert data["live"]["reset"] == 2


def test_the_verify_endpoint_goes_on_without_a_readable_lab_state(monkeypatch):
    def boom():
        raise ValueError("bad state")

    monkeypatch.setattr("xrpl_lab.api.routes.load_state", boom)
    _route_to(monkeypatch, _Ledger())
    resp = TestClient(create_app()).post(
        "/api/verify?live=true", json=_pack(ledger_resets_seen=PACK_SEEN),
    )
    assert resp.status_code == 200
    assert resp.json()["live"]["reset_signal"] == "pack_claim"
    assert resp.json()["live"]["unconfirmed"] == 2


def test_the_verify_endpoint_passes_this_labs_state_for_a_certificate_too(monkeypatch):
    save_state(_own(epoch_at=NOV_10))
    _route_to(monkeypatch, _Ledger())
    cert = rep.generate_certificate(LabState())
    assert rep.verify_certificate(cert)[0] is True
    resp = TestClient(create_app()).post("/api/verify?live=true", json=cert)
    assert resp.status_code == 200
    data = resp.json()
    assert data["artifact_kind"] == "certificate"
    # A certificate carries no txids, so there is nothing to anchor or reset.
    assert data["live"]["no_onledger_txids"] is True
    assert data["live"]["reset_signal"] == ""
