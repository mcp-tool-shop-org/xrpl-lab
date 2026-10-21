"""Verification commands: proof verify / cert-verify / audit-verify /
verify-artifact / support-bundle, the audit command and last-run.

Pins the exit-code taxonomy (a bad or tampered artifact is 1, a clean one is 0,
an audit with failed or missing txids is 3) and the ``--json`` shapes. On-ledger
(``--live``) checks run against a ``DryRunTransport`` with tx fixtures injected
through ``reporting._default_transport_factory``, so there is no network.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tests.cov_cli._helpers import all_module_ids, invoke, make_state, seal, write_json
from xrpl_lab.audit import verify_audit_pack
from xrpl_lab.doctor import Check, DoctorReport
from xrpl_lab.reporting import LIVE_PASS, verify_certificate, verify_proof_pack
from xrpl_lab.transport.base import NetworkInfo, TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

GOOD_TX = "A" * 64
FAIL_TX = "B" * 64
GHOST_TX = "C" * 64


def _ledger(monkeypatch, fixtures: dict[str, TxInfo]) -> None:
    """Resolve every per-network transport to one fixture-backed DryRunTransport."""
    t = DryRunTransport()
    t.set_tx_fixtures(fixtures)
    monkeypatch.setattr("xrpl_lab.reporting._default_transport_factory", lambda net: t)


def _ok_tx(txid: str, account: str = "rLEARNER") -> TxInfo:
    return TxInfo(
        txid=txid, tx_type="Payment", account=account, result_code="tesSUCCESS",
        validated=True, fee="12",
    )


def _pack(path: Path, *, network="testnet", txs=None, tamper=False, **extra) -> Path:
    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "2.6.1",
        "network": network,
        "address": "rLEARNER",
        "completed_modules": [{"module_id": "m1", "txids": []}],
        "total_transactions": len(txs or []),
        "transactions": txs or [],
        **extra,
    }
    seal(pack)
    if tamper:
        pack["address"] = "rEVIL"
    return write_json(path, pack)


def _cert(path: Path, *, network="testnet", tamper=False, **extra) -> Path:
    cert = {
        "xrpl_lab_certificate": True,
        "version": "2.6.1",
        "network": network,
        "address": "rLEARNER",
        "total_modules": 4,
        "total_transactions": 9,
        **extra,
    }
    seal(cert)
    if tamper:
        cert["total_modules"] = 99
    return write_json(path, cert)


def _tx(txid: str, network: str = "testnet") -> dict:
    return {"txid": txid, "network": network, "module_id": "m1", "success": True}


# ── invalid JSON, every native verify command ─────────────────────────


@pytest.mark.parametrize("cmd", [["proof", "verify"], ["cert-verify"], ["audit-verify"]])
def test_invalid_json_is_exit_1_with_plain_message(lab, cmd):
    f = lab.work / "broken.json"
    f.write_text("{not json", encoding="utf-8")
    r = invoke([*cmd, str(f)])
    assert r.exit_code == 1
    assert "Invalid JSON" in r.stdout
    assert "is deprecated" in r.stderr


@pytest.mark.parametrize("cmd", [["proof", "verify"], ["cert-verify"], ["audit-verify"]])
def test_invalid_json_with_json_flag_emits_a_failure_object(lab, cmd):
    f = lab.work / "broken.json"
    f.write_text("{not json", encoding="utf-8")
    r = invoke([*cmd, str(f), "--json"])
    assert r.exit_code == 1
    data = json.loads(r.stdout)
    assert data["valid"] is False
    assert data["message"].startswith("Invalid JSON")


# ── proof verify ──────────────────────────────────────────────────────


def test_proof_verify_json_shape_for_a_clean_pack(lab):
    f = _pack(lab.work / "p.json", txs=[_tx(GOOD_TX)])
    r = invoke(["proof", "verify", str(f), "--json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert d["valid"] is True
    assert d["message"] == "Integrity verified"
    assert d["address"] == "rLEARNER"
    assert d["network"] == "testnet"
    assert d["modules_completed"] == 1
    assert d["total_transactions"] == 1
    assert d["simulated"] is False
    assert d["all_verified"] is True
    assert d["sha256"] == json.loads(f.read_text(encoding="utf-8"))["sha256"]
    assert "live" not in d and "live_passed" not in d


def test_proof_verify_flags_a_dry_run_pack_as_simulated(lab):
    f = _pack(lab.work / "p.json", network="dry-run")
    text = invoke(["proof", "verify", str(f)])
    assert text.exit_code == 0
    assert "SIMULATED" in text.stdout
    js = json.loads(invoke(["proof", "verify", str(f), "--json"]).stdout)
    assert js["simulated"] is True


def test_proof_verify_flags_unverified_modules_without_failing(lab):
    f = _pack(lab.work / "p.json", all_verified=False)
    text = invoke(["proof", "verify", str(f)])
    assert text.exit_code == 0
    assert "UNVERIFIED" in text.stdout
    assert "PASS" in text.stdout
    js = json.loads(invoke(["proof", "verify", str(f), "--json"]).stdout)
    assert js["all_verified"] is False
    assert js["valid"] is True


def test_proof_verify_tampered_pack_fails_and_names_the_hash_mismatch(lab):
    f = _pack(lab.work / "p.json", tamper=True)
    r = invoke(["proof", "verify", str(f)])
    assert r.exit_code == 1
    assert "FAIL" in r.stdout
    assert "Hash mismatch" in r.stdout


def test_proof_verify_live_skips_the_ledger_when_the_hash_failed(lab):
    f = _pack(lab.work / "p.json", tamper=True, txs=[_tx(GOOD_TX)])
    text = invoke(["proof", "verify", str(f), "--live"])
    assert text.exit_code == 1
    assert "On-ledger verification skipped" in text.stdout
    js = json.loads(invoke(["proof", "verify", str(f), "--live", "--json"]).stdout)
    assert js["valid"] is False
    assert js["live_passed"] is False
    assert js["live"] == {"skipped": "hash check failed — live check not attempted"}


def test_proof_verify_live_pass_renders_verdict_and_json(lab, monkeypatch):
    _ledger(monkeypatch, {GOOD_TX: _ok_tx(GOOD_TX)})
    f = _pack(lab.work / "p.json", txs=[_tx(GOOD_TX)])
    text = invoke(["proof", "verify", str(f), "--live"])
    assert text.exit_code == 0, text.stdout
    assert "On-ledger verdict: PASS" in text.stdout
    assert "1 verified, 0 skipped" in text.stdout
    assert GOOD_TX[:20] in text.stdout
    js = json.loads(invoke(["proof", "verify", str(f), "--live", "--json"]).stdout)
    assert js["live_passed"] is True
    assert js["live"]["overall_passed"] is True
    assert js["live"]["tx_results"][0]["status"] == LIVE_PASS
    assert js["live"]["tx_results"][0]["txid"] == GOOD_TX


def test_proof_verify_live_failed_tx_exits_1_and_explains_why(lab, monkeypatch):
    _ledger(monkeypatch, {
        GOOD_TX: _ok_tx(GOOD_TX),
        FAIL_TX: TxInfo(txid=FAIL_TX, tx_type="Payment", account="rLEARNER",
                        result_code="tecPATH_DRY", validated=True),
        # GHOST_TX has no fixture and is not a dry-run id -> "not found"
    })
    f = _pack(lab.work / "p.json", txs=[_tx(GOOD_TX), _tx(FAIL_TX), _tx(GHOST_TX)])
    text = invoke(["proof", "verify", str(f), "--live"])
    assert text.exit_code == 1
    assert "On-ledger verdict: FAIL" in text.stdout
    assert "2 failed, 1 verified, 0 skipped" in text.stdout
    assert "tecPATH_DRY" in text.stdout
    assert "not found on the public ledger" in text.stdout
    js = json.loads(invoke(["proof", "verify", str(f), "--live", "--json"]).stdout)
    assert js["valid"] is True  # hash is fine; the ledger check is what fails
    assert js["live_passed"] is False
    assert js["live"]["failed"] == 2


def test_proof_verify_live_wrong_account_is_a_failure(lab, monkeypatch):
    _ledger(monkeypatch, {GOOD_TX: _ok_tx(GOOD_TX, account="rSOMEONEELSE")})
    f = _pack(lab.work / "p.json", txs=[_tx(GOOD_TX)])
    r = invoke(["proof", "verify", str(f), "--live"])
    assert r.exit_code == 1
    assert "does not match the pack's claimed address" in r.stdout


def test_proof_verify_live_mixed_pack_skips_dry_run_txs(lab, monkeypatch):
    _ledger(monkeypatch, {GOOD_TX: _ok_tx(GOOD_TX)})
    f = _pack(
        lab.work / "p.json", network="mixed",
        txs=[_tx(GOOD_TX), _tx("DRYTX1", "dry-run")],
    )
    r = invoke(["proof", "verify", str(f), "--live"])
    assert r.exit_code == 0, r.stdout
    assert "SKIP DRYTX1" in r.stdout
    assert "1 verified, 1 skipped" in r.stdout
    assert "Mixed pack" in r.stdout
    assert "SIMULATED" in r.stdout  # network == mixed


def test_proof_verify_live_dry_run_pack_is_honest_not_a_failure(lab):
    f = _pack(lab.work / "p.json", network="dry-run", txs=[_tx("DRYTX1", "dry-run")])
    r = invoke(["proof", "verify", str(f), "--live"])
    assert r.exit_code == 0
    assert "Dry-run pack" in r.stdout
    assert "On-ledger verdict" not in r.stdout


# ── cert-verify ───────────────────────────────────────────────────────


def test_cert_verify_json_shape_and_no_live_keys(lab):
    f = _cert(lab.work / "c.json")
    r = invoke(["cert-verify", str(f), "--json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert d["valid"] is True
    assert d["modules_completed"] == 4
    assert d["total_transactions"] == 9
    assert d["simulated"] is False
    assert "live" not in d


def test_cert_verify_dry_run_certificate_is_flagged_simulated(lab):
    f = _cert(lab.work / "c.json", network="dry-run")
    text = invoke(["cert-verify", str(f)])
    assert text.exit_code == 0
    assert "SIMULATED" in text.stdout
    assert "Modules:      4" in text.stdout
    assert json.loads(invoke(["cert-verify", str(f), "--json"]).stdout)["simulated"] is True


def test_cert_verify_tampered_fails(lab):
    f = _cert(lab.work / "c.json", tamper=True)
    r = invoke(["cert-verify", str(f)])
    assert r.exit_code == 1
    assert "Hash mismatch" in r.stdout


def test_cert_verify_live_reports_there_is_nothing_to_anchor(lab):
    f = _cert(lab.work / "c.json")
    text = invoke(["cert-verify", str(f), "--live"])
    assert text.exit_code == 0
    assert "Certificates record no individual txids" in text.stdout
    js = json.loads(invoke(["cert-verify", str(f), "--live", "--json"]).stdout)
    assert js["live_passed"] is True
    assert js["live"]["no_onledger_txids"] is True


def test_cert_verify_live_tampered_skips_the_ledger(lab):
    f = _cert(lab.work / "c.json", tamper=True)
    text = invoke(["cert-verify", str(f), "--live"])
    assert text.exit_code == 1
    assert "On-ledger verification skipped" in text.stdout
    js = json.loads(invoke(["cert-verify", str(f), "--live", "--json"]).stdout)
    assert js["live_passed"] is False
    assert "skipped" in js["live"]


def test_cert_verify_live_checks_embedded_transactions(lab, monkeypatch):
    _ledger(monkeypatch, {GOOD_TX: _ok_tx(GOOD_TX)})
    f = _cert(lab.work / "c.json", transactions=[_tx(GOOD_TX)])
    r = invoke(["cert-verify", str(f), "--live"])
    assert r.exit_code == 0, r.stdout
    assert "On-ledger verdict: PASS" in r.stdout

    _ledger(monkeypatch, {})  # ledger no longer knows the txid
    r2 = invoke(["cert-verify", str(f), "--live"])
    assert r2.exit_code == 1
    assert "On-ledger verdict: FAIL" in r2.stdout


# ── audit command + audit-verify ──────────────────────────────────────


class _TestnetLedger(DryRunTransport):
    """Fixture-backed transport that reports itself as the real testnet."""

    async def get_network_info(self) -> NetworkInfo:
        return NetworkInfo(
            network="testnet", rpc_url="https://s.altnet.rippletest.net:51234",
            connected=True, ledger_index=1,
        )


def _audit_ledger(monkeypatch, with_failure=True):
    t = _TestnetLedger()
    fx = {GOOD_TX: _ok_tx(GOOD_TX)}
    if with_failure:
        fx[FAIL_TX] = TxInfo(
            txid=FAIL_TX, tx_type="Payment", account="rA",
            result_code="tecUNFUNDED_PAYMENT", validated=True,
        )
    t.set_tx_fixtures(fx)
    monkeypatch.setattr("xrpl_lab.cli._get_transport", lambda dry_run=False: t)
    return t


def _txids_file(lab, *ids: str) -> Path:
    f = lab.work / "txids.txt"
    f.write_text("# comment\n\n" + "\n".join(ids) + "\n", encoding="utf-8")
    return f


def test_audit_with_no_txids_says_so_and_writes_nothing(lab):
    f = lab.work / "empty.txt"
    f.write_text("# only a comment\n\n", encoding="utf-8")
    r = invoke(["audit", "--txids", str(f)])
    assert r.exit_code == 0
    assert "No txids found in file." in r.stdout
    assert not lab.ws.exists()


def test_audit_rejects_a_malformed_txid_line(lab):
    f = _txids_file(lab, GOOD_TX, "=HYPERLINK(1)")
    r = invoke(["audit", "--txids", str(f)])
    assert r.exit_code == 1
    assert "Invalid txid on line" in r.output


def test_audit_all_pass_exits_0_and_seals_a_verifiable_pack(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX)
    r = invoke(["audit", "--txids", str(f)])
    assert r.exit_code == 0, r.output
    assert "Checked: 1 transactions" in r.output
    assert "Pass:    1" in r.output
    assert "Fail:    0" in r.output
    packs = list((lab.ws / "proofs").glob("audit_pack_*.json"))
    reports = list((lab.ws / "reports").glob("audit_*.md"))
    assert len(packs) == 1 and len(reports) == 1
    pack = json.loads(packs[0].read_text(encoding="utf-8"))
    assert pack["summary"] == {"total": 1, "passed": 1, "failed": 0, "not_found": 0}
    assert pack["dry_run"] is False
    assert pack["network"] == "testnet"
    assert verify_audit_pack(pack) == (True, "Integrity verified")
    assert f"| {GOOD_TX[:16]}... | PASS | Payment | tesSUCCESS |" in reports[0].read_text(
        encoding="utf-8"
    )


def test_audit_failures_exit_3_and_list_the_reasons(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX, FAIL_TX, GHOST_TX)
    r = invoke(["audit", "--txids", str(f)])
    assert r.exit_code == 3
    assert "Pass:    1" in r.output
    assert "Fail:    1" in r.output
    assert "Missing: 1" in r.output
    assert "Top failure reasons:" in r.output


def test_audit_dry_run_banner_and_sealed_flag(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX)
    r = invoke(["audit", "--txids", str(f), "--dry-run"])
    assert r.exit_code == 0
    assert "SIMULATED" in r.output
    pack = json.loads(next((lab.ws / "proofs").glob("audit_pack_*.json")).read_text("utf-8"))
    assert pack["dry_run"] is True
    assert pack["network"] == "dry-run"


def test_audit_custom_report_paths_csv_and_no_pack(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX)
    md = lab.work / "out" / "custom.md"
    csv_path = lab.work / "out" / "custom.csv"
    md.parent.mkdir()
    r = invoke([
        "audit", "--txids", str(f), "--md", str(md), "--csv", str(csv_path),
        "--no-pack",
    ])
    assert r.exit_code == 0, r.output
    assert md.exists() and GOOD_TX[:16] in md.read_text(encoding="utf-8")
    rows = [
        row for row in csv.reader(csv_path.read_text(encoding="utf-8").splitlines())
        if row
    ]
    assert rows[0][:2] == ["txid", "status"]
    assert rows[1][:2] == [GOOD_TX, "pass"]
    assert "CSV:" in r.output
    assert list((lab.ws / "proofs").glob("audit_pack_*.json")) == []
    assert "Audit pack:" not in r.output


def test_audit_expectations_file_changes_the_verdict(lab, monkeypatch):
    _audit_ledger(monkeypatch, with_failure=False)
    f = _txids_file(lab, GOOD_TX)
    exp = write_json(lab.work / "exp.json", {"defaults": {"types_allowed": ["OfferCreate"]}})
    r = invoke(["audit", "--txids", str(f), "--expect", str(exp), "--no-pack"])
    assert r.exit_code == 3
    assert "Fail:    1" in r.output


def test_audit_pack_roundtrips_through_audit_verify_and_catches_tampering(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX, FAIL_TX)
    invoke(["audit", "--txids", str(f)])
    pack_path = next((lab.ws / "proofs").glob("audit_pack_*.json"))

    ok = invoke(["audit-verify", str(pack_path)])
    assert ok.exit_code == 0
    assert "Audit pack integrity verified" in ok.stdout
    assert "Checked:      2" in ok.stdout
    assert "Pass/Fail:    1/1" in ok.stdout
    js = json.loads(invoke(["audit-verify", str(pack_path), "--json"]).stdout)
    assert js["valid"] is True and js["simulated"] is False and js["dry_run"] is False
    assert js["summary"]["total"] == 2
    assert js["integrity_sha256"]

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["summary"]["passed"] = 2  # forge a better result
    write_json(pack_path, pack)
    bad = invoke(["audit-verify", str(pack_path)])
    assert bad.exit_code == 1
    assert "Hash mismatch" in bad.stdout


def test_audit_verify_simulated_banner_for_a_dry_run_pack(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX)
    invoke(["audit", "--txids", str(f), "--dry-run"])
    pack_path = next((lab.ws / "proofs").glob("audit_pack_*.json"))
    r = invoke(["audit-verify", str(pack_path)])
    assert r.exit_code == 0
    assert "SIMULATED" in r.stdout
    assert json.loads(invoke(["audit-verify", str(pack_path), "--json"]).stdout)["simulated"]


# ── verify-artifact ───────────────────────────────────────────────────


def test_verify_artifact_invalid_json(lab):
    f = lab.work / "x.json"
    f.write_text("[1, 2", encoding="utf-8")
    text = invoke(["verify-artifact", str(f)])
    assert text.exit_code == 1 and "Invalid JSON" in text.stdout
    js = invoke(["verify-artifact", str(f), "--json"])
    assert js.exit_code == 1
    d = json.loads(js.stdout)
    assert d["valid"] is False
    assert d["artifact_kind"] == "unknown"
    assert d["message"].startswith("Invalid JSON")


@pytest.mark.parametrize("body", [{"hello": "world"}, [1, 2, 3], "just a string", 7])
def test_verify_artifact_rejects_unrecognized_shapes(lab, body):
    f = write_json(lab.work / "x.json", body)
    text = invoke(["verify-artifact", str(f)])
    assert text.exit_code == 1
    assert "Unrecognized artifact" in text.stdout
    d = json.loads(invoke(["verify-artifact", str(f), "--json"]).stdout)
    assert d["valid"] is False and d["artifact_kind"] == "unknown"
    assert "Recognized kinds" in d["message"]


def test_verify_artifact_unreadable_file_json_branch(lab, monkeypatch):
    f = write_json(lab.work / "x.json", {"a": 1})
    real = Path.read_text

    def _boom(self, *a, **k):
        if self.name == "x.json":
            raise PermissionError(str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _boom)
    r = invoke(["verify-artifact", str(f), "--json"])
    assert r.exit_code == 1
    d = json.loads(r.stdout)
    assert d == {
        "valid": False, "artifact_kind": "unknown",
        "message": "Could not read artifact (PermissionError).",
    }
    assert str(lab.work) not in r.stdout  # never leaks the absolute path


def test_verify_artifact_labels_each_kind_in_json(lab, monkeypatch):
    p = _pack(lab.work / "p.json")
    c = _cert(lab.work / "c.json")
    kinds = {
        p: "proof_pack",
        c: "certificate",
    }
    for path, kind in kinds.items():
        d = json.loads(invoke(["verify-artifact", str(path), "--json"]).stdout)
        assert d["artifact_kind"] == kind
        assert d["valid"] is True

    text = invoke(["verify-artifact", str(p)])
    assert "Artifact:    proof pack" in text.stdout
    assert "Proof pack integrity verified" in text.stdout


def test_verify_artifact_proof_marker_wins_over_support_bundle_schema(lab):
    f = _pack(lab.work / "both.json", schema="xrpl-lab-support-bundle-v1")
    d = json.loads(invoke(["verify-artifact", str(f), "--json"]).stdout)
    assert d["artifact_kind"] == "proof_pack"
    assert d["valid"] is True


def test_verify_artifact_tampered_proof_pack_is_exit_1(lab):
    f = _pack(lab.work / "p.json", tamper=True)
    r = invoke(["verify-artifact", str(f), "--json"])
    assert r.exit_code == 1
    d = json.loads(r.stdout)
    assert d["valid"] is False
    assert d["artifact_kind"] == "proof_pack"
    assert "Hash mismatch" in d["message"]


def test_verify_artifact_malformed_support_bundle_is_exit_1(lab):
    f = write_json(lab.work / "b.json", {"schema": "xrpl-lab-support-bundle-v1"})
    text = invoke(["verify-artifact", str(f)])
    assert text.exit_code == 1
    assert "Missing required fields" in text.stdout
    d = json.loads(invoke(["verify-artifact", str(f), "--json"]).stdout)
    assert d["artifact_kind"] == "support_bundle"
    assert d["valid"] is False


# ── support-bundle ────────────────────────────────────────────────────


@pytest.fixture()
def quiet_doctor(monkeypatch):
    async def _fake():
        return DoctorReport(checks=[
            Check("Wallet", True, "Found"),
            Check("RPC", False, "unreachable", "check network", severity="warn"),
        ])

    monkeypatch.setattr("xrpl_lab.doctor.run_doctor", _fake)


def test_support_bundle_json_is_a_valid_bundle_verify_artifact_accepts(
    lab, quiet_doctor,
):
    make_state(completed=all_module_ids()[:1], tx=[("TXQ", all_module_ids()[0], True)])
    r = invoke(["support-bundle", "--json"])
    assert r.exit_code == 0, r.output
    bundle = json.loads(r.stdout)
    assert bundle["schema"] == "xrpl-lab-support-bundle-v1"
    assert bundle["learner"]["completed_count"] == 1
    assert bundle["recent_transactions"][0]["txid"] == "TXQ"
    assert [c["name"] for c in bundle["doctor_checks"]] == ["Wallet", "RPC"]
    assert r.stderr == ""

    f = lab.work / "bundle.json"
    f.write_text(r.stdout, encoding="utf-8")
    v = invoke(["verify-artifact", str(f), "--json"])
    assert v.exit_code == 0
    assert json.loads(v.stdout)["artifact_kind"] == "support_bundle"


def test_support_bundle_markdown_mode(lab, quiet_doctor):
    r = invoke(["support-bundle"])
    assert r.exit_code == 0
    assert "Wallet" in r.stdout
    assert "WARN" in r.stdout  # warn-tier doctor checks never paste as FAIL


def test_feedback_alias_prints_the_bundle_and_a_deprecation_note(lab, quiet_doctor):
    r = invoke(["feedback"])
    assert r.exit_code == 0
    assert r.stderr == "`feedback` is deprecated, use `support-bundle`.\n"
    assert "Copy the block above into a GitHub issue" in r.stdout


def test_support_bundle_verify_bad_bundle_exit_1(lab):
    f = write_json(lab.work / "b.json", {"schema": "something-else"})
    r = invoke(["support-bundle", "--verify", str(f)])
    assert r.exit_code == 1
    assert "FAIL" in r.stdout
    js = invoke(["support-bundle", "--verify", str(f), "--json"])
    assert js.exit_code == 1
    assert json.loads(js.stdout)["valid"] is False


def test_support_bundle_verify_unreadable_file_is_path_free(lab, monkeypatch):
    f = write_json(lab.work / "b.json", {})
    real = Path.read_text

    def _boom(self, *a, **k):
        if self.name == "b.json":
            raise OSError("denied")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _boom)
    text = invoke(["support-bundle", "--verify", str(f)])
    assert text.exit_code == 1
    assert "Could not read support bundle (OSError)." in text.stdout
    js = invoke(["support-bundle", "--verify", str(f), "--json"])
    assert js.exit_code == 1
    assert json.loads(js.stdout) == {
        "valid": False, "message": "Could not read support bundle (OSError).",
    }


# ── last-run ──────────────────────────────────────────────────────────


def _last_run(lab, meta: object | str) -> None:
    lab.ws.mkdir(exist_ok=True)
    p = lab.ws / "last_run_meta.json"
    if isinstance(meta, str):
        p.write_text(meta, encoding="utf-8")
    else:
        write_json(p, meta)


def test_last_run_without_history(lab):
    r = invoke(["last-run"])
    assert r.exit_code == 0
    assert "No last run found." in r.stdout


def test_last_run_with_unreadable_metadata(lab):
    _last_run(lab, "{broken")
    r = invoke(["last-run"])
    assert r.exit_code == 0
    assert "Last run data is unreadable." in r.stdout


def test_last_run_prints_fields_and_the_audit_command(lab):
    _last_run(lab, {
        "module": "strategy_run", "run_id": "run-42",
        "timestamp": "2026-10-20T10:00:00Z", "txid_count": 7,
    })
    r = invoke(["last-run"])
    assert r.exit_code == 0
    for needle in ("strategy_run", "run-42", "2026-10-20T10:00:00Z", "TX count:  7"):
        assert needle in r.stdout
    assert "xrpl-lab audit --txids" in r.stdout
    assert "--expect" not in r.stdout
    assert "Preset:" not in r.stdout


def test_last_run_adds_expect_only_when_the_preset_file_exists(lab):
    _last_run(lab, {"module": "m", "preset": "tight", "txid_count": 1})
    r = invoke(["last-run"])
    assert "Preset:    tight" in r.stdout
    assert "--expect" not in r.stdout

    (lab.work / "presets").mkdir()
    write_json(lab.work / "presets" / "tight.json", {})
    r2 = invoke(["last-run"])
    assert "--expect presets/tight.json" in " ".join(r2.stdout.split())


def test_seal_helper_matches_the_generators_hash_recipe():
    """Guards the fixtures: sealed objects must verify with the real verifiers."""
    pack = seal({"xrpl_lab_proof_pack": True, "b": 1, "a": 2})
    body = json.dumps(
        {"a": 2, "b": 1, "xrpl_lab_proof_pack": True},
        sort_keys=True, separators=(",", ":"),
    )
    assert pack["sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert verify_proof_pack(pack) == (True, "Integrity verified")
    cert = seal({"xrpl_lab_certificate": True, "x": 1})
    assert verify_certificate(cert) == (True, "Integrity verified")


def test_audit_csv_has_no_doubled_carriage_returns(lab, monkeypatch):
    _audit_ledger(monkeypatch)
    f = _txids_file(lab, GOOD_TX)
    csv_path = lab.work / "r.csv"
    assert invoke(["audit", "--txids", str(f), "--csv", str(csv_path), "--no-pack"]).exit_code == 0
    assert b"\r\r" not in csv_path.read_bytes()
