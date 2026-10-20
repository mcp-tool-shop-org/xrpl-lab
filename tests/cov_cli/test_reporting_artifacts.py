"""reporting.py: artifact verification, on-ledger claims, session export gates."""

from __future__ import annotations

import asyncio
import json
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

import xrpl_lab.reporting as rep
from tests.cov_cli._helpers import seal
from xrpl_lab.audit import AuditConfig, run_audit, write_audit_pack
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

TX1 = "1" * 64
TX2 = "2" * 64


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform/account")


# ── sanitize_endpoint ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("", ""),
        ("none", "none"),
        ("dry-run", "dry-run"),
        ("https://s.altnet.rippletest.net:51234", "https://s.altnet.rippletest.net:51234"),
        ("https://user:pw@host.example:8080/path/TOKEN?api_key=K#frag", "https://host.example:8080"),
        ("wss://x.quiknode.pro/SECRETTOKEN/", "wss://x.quiknode.pro"),
        ("host.example:5005", "host.example:5005"),
    ],
)
def test_sanitize_endpoint_keeps_only_scheme_host_port(raw, clean):
    assert rep.sanitize_endpoint(raw) == clean


@pytest.mark.parametrize("raw", ["http://[unclosed", "http://host:notaport", "https://:8080"])
def test_sanitize_endpoint_fails_closed_on_unparseable_input(raw):
    assert rep.sanitize_endpoint(raw) == ""


# ── writers ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", "x..y"])
def test_write_module_report_rejects_path_like_ids(lab, tmp_path, bad):
    out = tmp_path / "reports"
    with pytest.raises(ValueError, match="Invalid module_id"):
        rep.write_module_report(bad, "T", [], output_dir=out)
    assert not out.exists() or list(out.iterdir()) == []


def test_write_module_report_renders_sections_and_leaves_no_tmp(lab, tmp_path):
    out = tmp_path / "reports"
    path = rep.write_module_report(
        "m1", "My Title", [("Heading A", "body a"), ("Heading B", "body b")],
        output_dir=out,
    )
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# My Title")
    assert "## Heading A\n\nbody a\n" in text and "## Heading B\n\nbody b\n" in text
    assert [p.name for p in out.iterdir()] == ["m1.md"]


def test_atomic_write_text_keeps_the_old_file_when_the_replace_fails(tmp_path, monkeypatch):
    box = tmp_path / "box"
    box.mkdir()
    dest = box / "pack.json"
    dest.write_text("GOOD", encoding="utf-8")

    def _boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(rep.os, "replace", _boom)
    with pytest.raises(OSError, match="disk gone"):
        rep._atomic_write_text(dest, "NEW")
    assert dest.read_text(encoding="utf-8") == "GOOD"
    assert [p.name for p in box.iterdir()] == ["pack.json"]


# ── load_artifact_json / verify_* ─────────────────────────────────────


def test_load_artifact_json_accepts_a_plain_object():
    assert rep.load_artifact_json('{"a": 1}') == {"a": 1}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ('{"a": 1, "a": 2}', "duplicate key"),
        ("[1, 2]", "single top-level object"),
        ('"str"', "single top-level object"),
        ("{oops", "Expecting"),
    ],
)
def test_load_artifact_json_rejects_ambiguous_or_invalid_input(text, match):
    with pytest.raises(ValueError, match=match):
        rep.load_artifact_json(text)


@pytest.mark.parametrize("fn", [rep.verify_proof_pack, rep.verify_certificate])
def test_verifiers_reject_non_objects(fn):
    assert fn([1]) == (False, "Not a valid JSON object")
    assert fn("x") == (False, "Not a valid JSON object")


def test_verifiers_name_the_other_artifact_when_the_marker_is_wrong():
    ok, msg = rep.verify_proof_pack({"xrpl_lab_certificate": True})
    assert not ok and "use cert-verify" in msg
    ok, msg = rep.verify_certificate({"xrpl_lab_proof_pack": True})
    assert not ok and "use proof verify" in msg


def test_verifiers_report_a_missing_hash_as_truncated():
    ok, msg = rep.verify_proof_pack({"xrpl_lab_proof_pack": True})
    assert not ok and "No SHA-256 hash found in proof pack" in msg
    ok, msg = rep.verify_certificate({"xrpl_lab_certificate": True})
    assert not ok and "No SHA-256 hash found in certificate" in msg


def test_verifiers_detect_any_edit_and_pass_a_sealed_artifact():
    pack = seal({"xrpl_lab_proof_pack": True, "address": "rA", "n": 1})
    cert = seal({"xrpl_lab_certificate": True, "address": "rA", "n": 1})
    assert rep.verify_proof_pack(pack) == (True, "Integrity verified")
    assert rep.verify_certificate(cert) == (True, "Integrity verified")
    pack["n"] = 2
    cert["n"] = 2
    ok, msg = rep.verify_proof_pack(pack)
    assert not ok and msg.startswith("Hash mismatch: expected")
    ok, msg = rep.verify_certificate(cert)
    assert not ok and "xrpl-lab certificate" in msg


# ── verify_offline_artifact ───────────────────────────────────────────


def test_offline_artifact_non_object_is_unknown_and_failing():
    out = rep.verify_offline_artifact([1, 2])
    assert out["artifact_kind"] == "unknown"
    assert out["hash_valid"] is False and out["overall_passed"] is False
    assert out["hash_message"] == "Not a valid JSON object"
    assert out["live"] is None and out["all_verified"] is True


def test_offline_artifact_proof_pack_surfaces_provenance():
    pack = seal({
        "xrpl_lab_proof_pack": True, "network": "dry-run", "version": "2.6.1",
        "all_verified": False,
    })
    out = rep.verify_offline_artifact(pack)
    assert out["artifact_kind"] == "proof_pack"
    assert out["hash_valid"] is True and out["overall_passed"] is True
    assert out["simulated"] is True
    assert out["network"] == "dry-run" and out["version"] == "2.6.1"
    assert out["all_verified"] is False
    assert out["live_requested"] is False


def test_offline_artifact_certificate_and_tamper():
    cert = seal({"xrpl_lab_certificate": True, "network": "testnet", "version": "2.6.1"})
    out = rep.verify_offline_artifact(cert)
    assert out["artifact_kind"] == "certificate"
    assert out["overall_passed"] is True and out["simulated"] is False
    assert out["all_verified"] is True
    cert["network"] = "mainnet"
    bad = rep.verify_offline_artifact(cert)
    assert bad["overall_passed"] is False
    assert bad["hash_message"].startswith("Hash mismatch")


def test_offline_artifact_audit_pack_and_unrecognized_bodies(tmp_path):
    report = asyncio.run(run_audit(DryRunTransport(), ["TXA"], AuditConfig()))
    pack_path = write_audit_pack(report, tmp_path / "audit.json")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    out = rep.verify_offline_artifact(pack)
    assert out["artifact_kind"] == "audit_pack"
    assert out["hash_valid"] is True

    unknown = rep.verify_offline_artifact({"hello": "world"})
    assert unknown["artifact_kind"] == "unknown"
    assert unknown["overall_passed"] is False
    assert "not a recognized XRPL Lab artifact" in unknown["hash_message"]


# ── _default_transport_factory ────────────────────────────────────────


def test_default_factory_points_each_network_at_its_own_public_rpc(monkeypatch):
    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    assert rep._default_transport_factory("testnet")._rpc_url == (
        "https://s.altnet.rippletest.net:51234"
    )
    assert rep._default_transport_factory("devnet")._rpc_url == (
        "https://s.devnet.rippletest.net:51234"
    )
    assert rep._default_transport_factory("something_else")._rpc_url == (
        "https://s.altnet.rippletest.net:51234"
    )


def test_default_factory_honours_an_override_only_for_the_same_network(monkeypatch):
    monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s.devnet.rippletest.net:51234")
    assert rep._default_transport_factory("devnet")._rpc_url == (
        "https://s.devnet.rippletest.net:51234"
    )
    # a devnet override must not misroute a testnet txid
    assert rep._default_transport_factory("testnet")._rpc_url == (
        "https://s.altnet.rippletest.net:51234"
    )


def test_default_factory_fails_loudly_if_the_transport_loses_its_url_attribute(
    monkeypatch,
):
    import xrpl_lab.transport.xrpl_testnet as tn

    class _Renamed:
        def __init__(self) -> None:
            self._url = "x"

    monkeypatch.setattr(tn, "XRPLTestnetTransport", _Renamed)
    with pytest.raises(AttributeError, match="no longer exposes _rpc_url"):
        rep._default_transport_factory("testnet")


def test_resolver_builds_one_transport_per_network():
    built: list[str] = []

    def factory(network):
        built.append(network)
        return DryRunTransport()

    resolve = rep._build_resolver(None, factory)
    a1, a2, b = resolve("testnet"), resolve("testnet"), resolve("devnet")
    assert a1 is a2 and a1 is not b
    assert built == ["testnet", "devnet"]
    fixed = DryRunTransport()
    assert rep._build_resolver(fixed, factory)("anything") is fixed


# ── _iter_pack_tx_claims ──────────────────────────────────────────────


def test_claims_from_transactions_skip_junk_and_duplicates():
    claims = rep._iter_pack_tx_claims({
        "address": "unknown", "network": "testnet",
        "transactions": [
            "not a dict",
            {"txid": ""},
            {"txid": TX1, "network": "devnet", "tx_type": "Payment"},
            {"txid": TX1, "network": "devnet"},  # duplicate
            {"txid": TX2},  # inherits the pack network
        ],
    })
    assert claims == [
        {"txid": TX1, "network": "devnet", "account": "", "tx_type": "Payment"},
        {"txid": TX2, "network": "testnet", "account": "", "tx_type": ""},
    ]


def test_claims_fall_back_to_completed_module_txids():
    claims = rep._iter_pack_tx_claims({
        "address": "rA", "network": "testnet",
        "completed_modules": [
            "junk",
            {"txids": [TX1, "", TX1, TX2]},
            {"module_id": "no_txids"},
        ],
    })
    assert [c["txid"] for c in claims] == [TX1, TX2]
    assert {c["network"] for c in claims} == {"testnet"}
    assert {c["account"] for c in claims} == {"rA"}
    assert rep._iter_pack_tx_claims({}) == []


# ── ledger-anchored verification verdicts ─────────────────────────────


def _ledger(**fixtures: TxInfo) -> DryRunTransport:
    t = DryRunTransport()
    t.set_tx_fixtures({f.txid: f for f in fixtures.values()})
    return t


def _ok(txid: str, account: str = "rA", tx_type: str = "Payment") -> TxInfo:
    return TxInfo(
        txid=txid, tx_type=tx_type, account=account, result_code="tesSUCCESS",
        validated=True,
    )


def test_live_proof_pack_with_no_transactions_has_nothing_to_anchor():
    res = asyncio.run(rep.verify_proof_pack_live({"address": "rA"}))
    assert res.no_onledger_txids is True and res.overall_passed is True
    assert "records no transactions" in res.note


def test_live_proof_pack_checks_type_account_and_engine_result():
    t = _ledger(
        a=_ok(TX1),
        b=_ok(TX2, tx_type="OfferCreate"),
        c=TxInfo(txid="3" * 64, result_code="tesSUCCESS", validated=False),
        d=TxInfo(txid="4" * 64, fetch_error="timeout"),
    )
    pack = {
        "address": "rA",
        "transactions": [
            {"txid": TX1, "network": "testnet", "tx_type": "Payment"},
            {"txid": TX2, "network": "testnet", "tx_type": "Payment"},
            {"txid": "3" * 64, "network": "testnet"},
            {"txid": "4" * 64, "network": "devnet"},
        ],
    }
    res = asyncio.run(rep.verify_proof_pack_live(pack, transport=t))
    by_tx = {r.txid: r for r in res.tx_results}
    assert by_tx[TX1].status == rep.LIVE_PASS
    assert "Type matches: Payment" in by_tx[TX1].checks
    assert by_tx[TX2].status == rep.LIVE_FAIL and "type does not match" in by_tx[TX2].reason
    assert "NOT validated" in by_tx["3" * 64].reason
    assert "Couldn't reach the ledger" in by_tx["4" * 64].reason
    assert res.overall_passed is False


def test_live_proof_pack_all_mixed_labels_fails_closed():
    pack = {"network": "mixed", "transactions": [{"txid": TX1, "network": "mixed"}]}
    res = asyncio.run(rep.verify_proof_pack_live(pack, transport=DryRunTransport()))
    assert res.failed_count == 1 and res.overall_passed is False
    assert res.no_onledger_txids is False
    assert "ambiguous network labels" in res.note


def test_live_proof_pack_unanchorable_network_label_is_named_not_called_dry_run():
    pack = {"transactions": [{"txid": TX1, "network": "mainnet"}]}
    res = asyncio.run(rep.verify_proof_pack_live(pack, transport=DryRunTransport()))
    assert res.no_onledger_txids is True and res.overall_passed is True
    assert "'mainnet'" in res.note and "Dry-run" not in res.note


def test_live_certificate_without_transactions_points_at_the_proof_pack():
    res = asyncio.run(rep.verify_certificate_live({"address": "rA"}))
    assert res.artifact_kind == "certificate"
    assert res.no_onledger_txids is True
    assert "proof verify <proof_pack.json> --live" in res.note


def test_live_certificate_with_embedded_transactions_is_verified_like_a_pack():
    cert = {
        "address": "rA",
        "transactions": [
            {"txid": TX1, "network": "testnet"},
            {"txid": "D1", "network": "dry-run"},
        ],
    }
    res = asyncio.run(rep.verify_certificate_live(cert, transport=_ledger(a=_ok(TX1))))
    assert res.passed_count == 1 and res.skipped_count == 1
    assert res.overall_passed is True


def test_live_certificate_all_dry_run_and_all_mixed_notes():
    dry = asyncio.run(rep.verify_certificate_live(
        {"transactions": [{"txid": "D1", "network": "dry-run"}]},
        transport=DryRunTransport(),
    ))
    assert dry.no_onledger_txids is True
    assert dry.note == "Dry-run certificate — no on-ledger txids to verify."

    mixed = asyncio.run(rep.verify_certificate_live(
        {"transactions": [{"txid": TX1, "network": "mixed"}]},
        transport=DryRunTransport(),
    ))
    assert mixed.failed_count == 1 and mixed.overall_passed is False
    assert "Cannot anchor this certificate" in mixed.note


# ── session export gates ──────────────────────────────────────────────


def _workspace(root: Path, name: str, files: dict[str, bytes]) -> Path:
    learner = root / name
    for rel, data in files.items():
        f = learner / ".xrpl-lab" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return learner


def test_export_rejects_unknown_formats_and_missing_directories(tmp_path):
    with pytest.raises(ValueError, match="Unsupported format"):
        rep.write_session_export(tmp_path, tmp_path / "o.rar", "rar")
    with pytest.raises(FileNotFoundError, match="Cohort dir not found"):
        rep.write_session_export(tmp_path / "missing", tmp_path / "o.zip", "zip")
    assert not (tmp_path / "o.rar").exists() and not (tmp_path / "o.zip").exists()


def test_export_skips_symlinked_learners_stray_files_and_bare_directories(tmp_path):
    cohort = tmp_path / "cohort"
    _workspace(cohort, "real", {"proofs/p.json": b"{}"})
    outside = _workspace(tmp_path / "elsewhere", "victim", {"proofs/secret.json": b"S"})
    (cohort / "stray.txt").write_text("x", encoding="utf-8")
    (cohort / "bare").mkdir()
    _symlink(cohort / "linked", outside, directory=True)

    res = rep.write_session_export(cohort, tmp_path / "o.zip", "zip")
    assert res["learners"] == 1
    assert res["manifest"]["learners"] == ["real"]
    with zipfile.ZipFile(tmp_path / "o.zip") as zf:
        assert sorted(zf.namelist()) == ["MANIFEST.json", "real/proofs/p.json"]


def test_collect_refuses_a_symlinked_learner_workspace_or_subdirectory(tmp_path):
    outside = _workspace(tmp_path / "elsewhere", "victim", {"proofs/secret.json": b"S"})

    # the learner directory itself is a symlink
    _symlink(tmp_path / "L1", outside, directory=True)
    assert rep._collect_learner_artifacts(tmp_path / "L1") == []

    # the learner's .xrpl-lab is a symlink to a directory elsewhere
    l2 = tmp_path / "L2"
    l2.mkdir()
    _symlink(l2 / ".xrpl-lab", outside / ".xrpl-lab", directory=True)
    assert rep._collect_learner_artifacts(l2) == []

    # one of the shareable subdirectories is a symlink
    l3 = tmp_path / "L3"
    (l3 / ".xrpl-lab").mkdir(parents=True)
    _symlink(l3 / ".xrpl-lab" / "proofs", outside / ".xrpl-lab" / "proofs", directory=True)
    assert rep._collect_learner_artifacts(l3) == []


def test_collect_skips_symlinked_files_and_secret_name_prefixes(tmp_path):
    learner = _workspace(tmp_path, "amy", {
        "proofs/ok.json": b"1",
        "proofs/WALLET.JSON.bak": b"seed",
        "reports/state.json.tmp": b"private",
        "audit_packs/doctor.log.1": b"log",
    })
    secret = tmp_path / "wallet_secret.txt"
    secret.write_text("SEED", encoding="utf-8")
    _symlink(learner / ".xrpl-lab" / "proofs" / "innocent.json", secret)
    items = rep._collect_learner_artifacts(learner)
    assert [rel for _p, rel in items] == ["amy/proofs/ok.json"]


def test_collect_realpath_containment_and_unresolvable_files(tmp_path, monkeypatch):
    learner = _workspace(tmp_path, "amy", {"proofs/a.json": b"1", "proofs/b.json": b"2"})
    a = learner / ".xrpl-lab" / "proofs" / "a.json"
    b = learner / ".xrpl-lab" / "proofs" / "b.json"
    real_resolve = Path.resolve

    def _resolve(self, strict=False):
        if self == a:
            raise OSError("vanished")
        if self == b:
            return tmp_path / "outside" / "b.json"
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", _resolve)
    assert rep._collect_learner_artifacts(learner) == []


def test_manifest_never_hashes_through_a_symlink(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    _symlink(link, real)
    m = rep.build_session_manifest(
        tmp_path / "cohort",
        {"amy": [(real, "amy/proofs/real.json"), (link, "amy/proofs/link.json")]},
    )
    assert [f["path"] for f in m["files"]] == ["amy/proofs/real.json"]
    assert m["files"][0]["size"] == 2
    assert m["cohort_dir"] == "cohort"


@pytest.mark.parametrize("fmt", ["tar.gz", "zip"])
def test_export_write_time_gate_drops_a_symlink_a_collector_let_through(
    tmp_path, monkeypatch, fmt,
):
    cohort = tmp_path / "cohort"
    learner = _workspace(cohort, "amy", {"proofs/ok.json": b"OK"})
    secret = tmp_path / "wallet_target.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    link = learner / ".xrpl-lab" / "proofs" / "innocent.json"
    _symlink(link, secret)
    ok = learner / ".xrpl-lab" / "proofs" / "ok.json"
    monkeypatch.setattr(
        rep, "_collect_learner_artifacts",
        lambda _d: [(ok, "amy/proofs/ok.json"), (link, "amy/proofs/innocent.json")],
    )
    out = tmp_path / f"o.{fmt}"
    res = rep.write_session_export(cohort, out, fmt)
    assert res["files"] == 2  # MANIFEST + the real file only
    if fmt == "zip":
        with zipfile.ZipFile(out) as zf:
            assert sorted(zf.namelist()) == ["MANIFEST.json", "amy/proofs/ok.json"]
            assert all(b"TOPSECRET" not in zf.read(n) for n in zf.namelist())
    else:
        with tarfile.open(out, "r:gz") as tar:
            assert sorted(tar.getnames()) == ["MANIFEST.json", "amy/proofs/ok.json"]


def test_export_failure_leaves_no_partial_archive_and_keeps_the_previous_one(
    tmp_path, monkeypatch,
):
    cohort = tmp_path / "cohort"
    _workspace(cohort, "amy", {"proofs/ok.json": b"OK"})
    out = tmp_path / "keep.tar.gz"
    out.write_bytes(b"PREVIOUS GOOD ARCHIVE")

    def _boom(*_a, **_k):
        raise OSError("rename failed")

    monkeypatch.setattr(rep.os, "replace", _boom)
    with pytest.raises(OSError, match="rename failed"):
        rep.write_session_export(cohort, out, "tar.gz")
    assert out.read_bytes() == b"PREVIOUS GOOD ARCHIVE"
    assert not out.with_name(out.name + ".tmp").exists()


def test_collect_ignores_a_workspace_that_is_not_a_directory(tmp_path):
    learner = tmp_path / "amy"
    learner.mkdir()
    (learner / ".xrpl-lab").write_text("not a directory", encoding="utf-8")
    assert rep._collect_learner_artifacts(learner) == []


def test_collect_walks_nested_folders_but_archives_only_files(tmp_path):
    learner = _workspace(tmp_path, "amy", {"reports/deep/er/r.md": b"# r"})
    (learner / ".xrpl-lab" / "reports" / "empty_dir").mkdir()
    items = rep._collect_learner_artifacts(learner)
    assert [rel for _p, rel in items] == ["amy/reports/deep/er/r.md"]
