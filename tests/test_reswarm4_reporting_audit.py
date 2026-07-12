"""Re-swarm 4 regression tests — reporting-audit domain.

Each test pins a fix from the wave-2 reporting-audit amend:

* RA-001 / F-a8db1a2d — audit pack seals the CLASSIFIED network, not a
  hardcoded 'testnet' literal.
* RA-002 / F-60b2df48 — RPC URLs are credential-stripped BEFORE they enter
  any hashed artifact (value-level no-secrets, not just field names).
* RA-003 / F-a39c228a — session export never reads through symlinks and
  excludes secret-file name PREFIXES.
* F-0183341d — legacy packs with ambiguous ('mixed') network labels fail
  closed in live verification instead of skipping to a green verdict.
* F-55604e7e — artifact writers are atomic (tmp + os.replace).
* F-0fb57446 — verify_audit_pack closes the audit-pack trust loop.
* F-6b3c9205 — txid parse validation + CSV formula-injection defusing.
* F-f7520b7f — duplicate-key JSON is rejected by the artifact loader.
* F-65f845fa — the live-verify transport factory provably pins per-network
  URLs (via the public network_name surface).
* F-314bdd5a — a fully dry-run proof pack seals endpoint='none'.

Run in isolation:
    python -m pytest tests/test_reswarm4_reporting_audit.py -q
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import click
import pytest

from xrpl_lab.audit import (
    AuditConfig,
    AuditReport,
    AuditVerdict,
    parse_txids_file,
    run_audit,
    verify_audit_pack,
    write_audit_pack,
    write_audit_report_csv,
    write_audit_report_md,
)
from xrpl_lab.reporting import (
    _atomic_write_text,
    _default_transport_factory,
    generate_proof_pack,
    load_artifact_json,
    sanitize_endpoint,
    verify_proof_pack,
    verify_proof_pack_live,
    write_proof_pack,
    write_session_export,
)
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import NetworkInfo, TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# A credentialed RPC URL of the kind RA-002 defends against: basic-auth
# userinfo + a query API key. Neither 'hunter2' nor 'key=abc' may ever
# appear in any artifact.
CRED_URL = "https://user:hunter2@example.com:51234/?key=abc"

# 64-hex txids for realistic claims.
TXID_A = "A" * 64
TXID_B = "B" * 64


class _StubTransport:
    """Duck-typed minimal transport — only what run_audit touches.

    run_audit calls ``fetch_tx`` per txid and ``get_network_info`` once; a
    stub keeps these tests fully offline while exercising the exact
    net_info -> AuditReport.network plumbing the fix added.
    """

    def __init__(self, network: str, rpc_url: str) -> None:
        self._network = network
        self._rpc_url_value = rpc_url

    async def fetch_tx(self, txid: str) -> TxInfo:
        return TxInfo(
            txid=txid,
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=True,
        )

    async def get_network_info(self) -> NetworkInfo:
        return NetworkInfo(
            network=self._network,
            rpc_url=self._rpc_url_value,
            connected=True,
        )


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create a symlink or skip the test where the platform forbids it
    (Windows without Developer Mode / SeCreateSymbolicLinkPrivilege)."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - env
        pytest.skip(f"symlinks unavailable on this platform: {exc}")


# ── RA-001 / F-a8db1a2d: honest network label in audit artifacts ─────


class TestAuditPackNetworkHonesty:
    @pytest.mark.asyncio
    async def test_devnet_env_url_seals_devnet_not_testnet(
        self, tmp_path, monkeypatch
    ):
        """XRPL_LAB_RPC_URL at a devnet URL must seal network='devnet'.

        The transport chain is exercised without network I/O: the env URL is
        classified exactly as XRPLTestnetTransport does (classify_network),
        and run_audit seals whatever get_network_info reports.
        """
        devnet_url = "https://s.devnet.rippletest.net:51234"
        monkeypatch.setenv("XRPL_LAB_RPC_URL", devnet_url)

        from xrpl_lab.transport.xrpl_testnet import (
            XRPLTestnetTransport,
            classify_network,
            get_rpc_url,
        )

        # The transport the CLI would build classifies the env URL as devnet
        # (constructor + classification only — no socket I/O).
        assert XRPLTestnetTransport().network_name == "devnet"

        url = get_rpc_url()
        stub = _StubTransport(classify_network(url), url)
        report = await run_audit(stub, [TXID_A])
        assert report.network == "devnet"

        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        assert data["network"] == "devnet"
        assert data["network"] != "testnet"
        # The label is sealed INSIDE the hash.
        valid, _ = verify_audit_pack(data)
        assert valid

    @pytest.mark.asyncio
    async def test_md_report_shows_classified_network(self, tmp_path):
        stub = _StubTransport("devnet", "https://s.devnet.rippletest.net:51234")
        report = await run_audit(stub, [TXID_A])
        md_path = tmp_path / "report.md"
        write_audit_report_md(report, md_path)
        text = md_path.read_text(encoding="utf-8")
        assert "- **Network**: devnet" in text
        assert "- **Network**: testnet" not in text

    @pytest.mark.asyncio
    async def test_dry_run_flag_still_overrides_to_dry_run(self, tmp_path):
        """dry_run=True seals network='dry-run' regardless of net_info."""
        stub = _StubTransport("devnet", "https://s.devnet.rippletest.net:51234")
        report = await run_audit(stub, [TXID_A], dry_run=True)
        assert report.network == "dry-run"
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        assert data["network"] == "dry-run"
        assert data["dry_run"] is True

    @pytest.mark.asyncio
    async def test_local_endpoint_seals_local(self, tmp_path):
        """A local rippled audit is labeled 'local', never 'testnet'."""
        stub = _StubTransport("local", "http://localhost:5005")
        report = await run_audit(stub, [TXID_A])
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        assert data["network"] == "local"


# ── RA-002 / F-60b2df48: credential-stripping at every sealing site ──


class TestEndpointSanitization:
    def test_sanitize_endpoint_strips_userinfo_query_and_path(self):
        assert sanitize_endpoint(CRED_URL) == "https://example.com:51234"
        # QuickNode-style path token.
        assert (
            sanitize_endpoint("https://x.quiknode.pro/SECRETTOKEN123/")
            == "https://x.quiknode.pro"
        )

    def test_sanitize_endpoint_passes_through_safe_values(self):
        # Default public endpoints survive byte-for-byte.
        assert (
            sanitize_endpoint("https://s.altnet.rippletest.net:51234")
            == "https://s.altnet.rippletest.net:51234"
        )
        # Transport provenance labels are not URLs and pass through.
        assert sanitize_endpoint("none") == "none"
        assert sanitize_endpoint("dry-run") == "dry-run"
        assert sanitize_endpoint("") == ""

    def test_sanitize_endpoint_fails_closed_on_garbage(self):
        # Unparseable port — never echo a string we could not strip.
        assert sanitize_endpoint("https://user:pw@host:notaport/x") == ""

    def test_proof_pack_never_seals_credentials(self, monkeypatch):
        monkeypatch.setenv("XRPL_LAB_RPC_URL", CRED_URL)
        state = LabState(network="testnet", wallet_address="rTEST")
        state.complete_module("receipt_literacy", txids=[TXID_A])
        state.record_tx(TXID_A, "receipt_literacy", "testnet", True)

        pack = generate_proof_pack(state)
        text = json.dumps(pack)
        # Value-level no-secrets: the existing no-secrets test pins field
        # NAMES; this greps the VALUES for the sanitized-away credential.
        assert "hunter2" not in text
        assert "key=abc" not in text
        assert "user:" not in text
        assert pack["endpoint"] == "https://example.com:51234"
        # Sanitization happened BEFORE hashing — the pack still verifies.
        valid, msg = verify_proof_pack(pack)
        assert valid, msg

    @pytest.mark.asyncio
    async def test_audit_artifacts_never_seal_credentials(self, tmp_path):
        """Pack + md + csv from a credentialed net_info carry no secret."""
        stub = _StubTransport("testnet", CRED_URL)
        report = await run_audit(stub, [TXID_B])
        assert "hunter2" not in report.endpoint

        pack_path = tmp_path / "pack.json"
        md_path = tmp_path / "report.md"
        csv_path = tmp_path / "report.csv"
        write_audit_pack(report, pack_path)
        write_audit_report_md(report, md_path)
        write_audit_report_csv(report, csv_path)

        for artifact in (pack_path, md_path, csv_path):
            content = artifact.read_text(encoding="utf-8")
            assert "hunter2" not in content, artifact.name
            assert "key=abc" not in content, artifact.name

        data = json.loads(pack_path.read_text(encoding="utf-8"))
        assert data["endpoint"] == "https://example.com:51234"
        valid, _ = verify_audit_pack(data)
        assert valid

    @pytest.mark.asyncio
    async def test_explicit_endpoint_argument_is_sanitized(self):
        stub = _StubTransport("testnet", "https://s.altnet.rippletest.net:51234")
        report = await run_audit(stub, [TXID_A], endpoint=CRED_URL)
        assert report.endpoint == "https://example.com:51234"

    def test_writers_sanitize_directly_constructed_reports(self, tmp_path):
        """Belt-and-braces: even a report constructed with a raw credentialed
        endpoint (bypassing run_audit) must not leak through the writers."""
        report = AuditReport(
            verdicts=[],
            config=AuditConfig(),
            endpoint=CRED_URL,
            tool_version="0.0.0-test",
            timestamp="2026-07-12T00:00:00Z",
        )
        pack_path = tmp_path / "pack.json"
        md_path = tmp_path / "report.md"
        write_audit_pack(report, pack_path)
        write_audit_report_md(report, md_path)
        for artifact in (pack_path, md_path):
            content = artifact.read_text(encoding="utf-8")
            assert "hunter2" not in content
            assert "key=abc" not in content


# ── RA-003 / F-a39c228a: session export symlink + prefix defenses ────


class TestSessionExportSymlinkDefense:
    SEED_CONTENT = '{"seed": "sEdSYMLINK_SENTINEL_9f2c71"}'

    def _build_cohort_with_symlink(self, tmp_path: Path) -> tuple[Path, str]:
        """Cohort with a planted proofs/innocent.json -> wallet.json link."""
        secret_dir = tmp_path / "facilitator_home"
        secret_dir.mkdir()
        wallet = secret_dir / "wallet.json"
        wallet.write_text(self.SEED_CONTENT, encoding="utf-8")
        secret_sha = hashlib.sha256(self.SEED_CONTENT.encode()).hexdigest()

        cohort = tmp_path / "cohort"
        ws = cohort / "alice" / ".xrpl-lab"
        (ws / "proofs").mkdir(parents=True)
        (ws / "proofs" / "real.json").write_text('{"ok": 1}', encoding="utf-8")
        _symlink_or_skip(ws / "proofs" / "innocent.json", wallet)
        return cohort, secret_sha

    def test_zip_export_never_reads_through_symlink(self, tmp_path):
        cohort, secret_sha = self._build_cohort_with_symlink(tmp_path)
        outfile = tmp_path / "session.zip"
        write_session_export(cohort, outfile, archive_format="zip")

        with zipfile.ZipFile(outfile) as zf:
            names = set(zf.namelist())
            assert "alice/proofs/innocent.json" not in names
            assert "alice/proofs/real.json" in names
            for name in names:
                content = zf.read(name).decode("utf-8", errors="replace")
                assert self.SEED_CONTENT not in content, name
                assert "sEdSYMLINK_SENTINEL" not in content, name
            manifest = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
        assert all(f["path"] != "alice/proofs/innocent.json" for f in manifest["files"])
        assert all(f["sha256"] != secret_sha for f in manifest["files"])

    def test_targz_export_never_reads_through_symlink(self, tmp_path):
        cohort, secret_sha = self._build_cohort_with_symlink(tmp_path)
        outfile = tmp_path / "session.tar.gz"
        write_session_export(cohort, outfile, archive_format="tar.gz")

        with tarfile.open(outfile, "r:gz") as tar:
            names = set(tar.getnames())
            assert "alice/proofs/innocent.json" not in names
            assert "alice/proofs/real.json" in names
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                fobj = tar.extractfile(member)
                assert fobj is not None
                content = fobj.read().decode("utf-8", errors="replace")
                assert self.SEED_CONTENT not in content, member.name
                assert "sEdSYMLINK_SENTINEL" not in content, member.name
            mf = tar.extractfile("MANIFEST.json")
            assert mf is not None
            manifest = json.loads(mf.read().decode("utf-8"))
        # The secret's hash must not leak into the manifest either
        # (metadata leak + manifest/archive divergence).
        assert all(f["path"] != "alice/proofs/innocent.json" for f in manifest["files"])
        assert all(f["sha256"] != secret_sha for f in manifest["files"])

    def test_symlinked_directory_contents_never_archived(self, tmp_path):
        """A planted proofs/sub -> <secrets dir> directory symlink must not
        leak anything, whatever the platform's rglob traversal behavior."""
        secret_dir = tmp_path / "victim_secrets"
        secret_dir.mkdir()
        (secret_dir / "wallet.json").write_text(
            self.SEED_CONTENT, encoding="utf-8"
        )
        (secret_dir / "notes.txt").write_text(
            "sEdSYMLINK_SENTINEL_dirlink", encoding="utf-8"
        )

        cohort = tmp_path / "cohort"
        ws = cohort / "alice" / ".xrpl-lab"
        (ws / "proofs").mkdir(parents=True)
        (ws / "proofs" / "real.json").write_text('{"ok": 1}', encoding="utf-8")
        _symlink_or_skip(ws / "proofs" / "sub", secret_dir)

        outfile = tmp_path / "session.zip"
        write_session_export(cohort, outfile, archive_format="zip")
        with zipfile.ZipFile(outfile) as zf:
            for name in zf.namelist():
                assert "sub" not in name.split("/"), name
                content = zf.read(name).decode("utf-8", errors="replace")
                assert "sEdSYMLINK_SENTINEL" not in content, name

    def test_exclusion_matches_prefixes_and_case(self, tmp_path):
        """wallet.json.bak / state.json.tmp / doctor.log.1 / WALLET.JSON are
        excluded from archive AND manifest; ordinary proofs still flow."""
        cohort = tmp_path / "cohort"
        ws = cohort / "alice" / ".xrpl-lab"
        (ws / "proofs").mkdir(parents=True)
        (ws / "proofs" / "proof.json").write_text('{"ok": 1}', encoding="utf-8")
        for secret_name in (
            "wallet.json.bak",
            "state.json.tmp",
            "state.json.corrupted.20260712",
            "doctor.log.1",
            "WALLET.JSON",
        ):
            (ws / "proofs" / secret_name).write_text(
                '{"seed": "sEdPREFIX_SENTINEL"}', encoding="utf-8"
            )

        outfile = tmp_path / "session.zip"
        summary = write_session_export(cohort, outfile, archive_format="zip")
        with zipfile.ZipFile(outfile) as zf:
            names = set(zf.namelist())
            assert "alice/proofs/proof.json" in names
            for name in names:
                base = name.rsplit("/", 1)[-1].lower()
                assert not base.startswith(("wallet.json", "state.json", "doctor.log")), name
                content = zf.read(name).decode("utf-8", errors="replace")
                assert "sEdPREFIX_SENTINEL" not in content, name
        manifest = summary["manifest"]
        assert all("wallet" not in f["path"].lower() for f in manifest["files"])


# ── F-0183341d: ambiguous ('mixed') legacy packs fail closed ─────────


class TestMixedNetworkFailClosed:
    def _legacy_pack(self, network: str, txids: list[str]) -> dict:
        """A legacy-format pack: completed_modules txids, NO transactions."""
        return {
            "xrpl_lab_proof_pack": True,
            "version": "1.0.0",
            "network": network,
            "address": "rLEGACY",
            "completed_modules": [{"module_id": "m1", "txids": txids}],
        }

    @pytest.mark.asyncio
    async def test_legacy_mixed_pack_is_not_live_passed(self):
        """A legacy pack with network='mixed' + a fake txid must NOT ride the
        dry-run skip to overall_passed=True."""
        pack = self._legacy_pack("mixed", [TXID_A])
        live = await verify_proof_pack_live(pack, transport=DryRunTransport())
        assert live.overall_passed is False
        assert live.failed_count == 1
        assert live.no_onledger_txids is False
        assert "Dry-run pack" not in live.note
        assert live.tx_results[0].status == "FAIL"
        assert "mixed" in live.tx_results[0].reason

    @pytest.mark.asyncio
    async def test_empty_transactions_list_with_mixed_top_network(self):
        """``transactions: []`` falls through to the legacy path — with an
        ambiguous top network it must fail closed, not pass."""
        pack = self._legacy_pack("mixed", [TXID_B])
        pack["transactions"] = []
        live = await verify_proof_pack_live(pack, transport=DryRunTransport())
        assert live.overall_passed is False

    @pytest.mark.asyncio
    async def test_honest_dry_run_legacy_pack_unchanged(self):
        """The honest dry-run skip is preserved for genuinely dry-run labels."""
        pack = self._legacy_pack("dry-run", ["SIMTX1"])
        live = await verify_proof_pack_live(pack, transport=DryRunTransport())
        assert live.overall_passed is True
        assert live.no_onledger_txids is True
        assert "Dry-run pack" in live.note

    @pytest.mark.asyncio
    async def test_non_dryrun_skip_note_never_claims_dry_run(self):
        """A legacy pack labeled 'mainnet' is skipped (we cannot check
        mainnet) but the note must name the label, not claim dry-run."""
        pack = self._legacy_pack("mainnet", [TXID_A])
        live = await verify_proof_pack_live(pack, transport=DryRunTransport())
        assert "Dry-run pack" not in live.note
        assert "mainnet" in live.note

    @pytest.mark.asyncio
    async def test_per_tx_mixed_label_in_modern_pack_fails_closed(self):
        """Even a hand-crafted modern pack with a per-tx 'mixed' label fails."""
        pack = {
            "xrpl_lab_proof_pack": True,
            "network": "mixed",
            "address": "rX",
            "transactions": [{"txid": TXID_A, "network": "mixed"}],
        }
        live = await verify_proof_pack_live(pack, transport=DryRunTransport())
        assert live.overall_passed is False
        assert live.failed_count == 1


# ── F-55604e7e: atomic artifact writes ───────────────────────────────


class TestAtomicWrites:
    def test_failed_replace_preserves_previous_artifact(self, tmp_path, monkeypatch):
        """A crash between tmp-write and replace must leave the previous
        GOOD artifact untouched and no stray .tmp behind."""
        from xrpl_lab import reporting as reporting_mod

        target = tmp_path / "artifact.json"
        target.write_text("PREVIOUS-GOOD", encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated crash during replace")

        monkeypatch.setattr(reporting_mod.os, "replace", boom)
        with pytest.raises(OSError, match="simulated crash"):
            _atomic_write_text(target, "NEW-CONTENT")

        assert target.read_text(encoding="utf-8") == "PREVIOUS-GOOD"
        assert not list(tmp_path.glob("*.tmp"))

    def test_proof_pack_write_leaves_no_tmp_residue(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "xrpl_lab.reporting.get_workspace_dir", lambda: tmp_path
        )
        state = LabState(network="testnet", wallet_address="rTEST")
        state.record_tx(TXID_A, "m", "testnet", True)
        path = write_proof_pack(state)
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["xrpl_lab_proof_pack"]
        assert not list(path.parent.glob("*.tmp"))

    @pytest.mark.asyncio
    async def test_audit_writers_leave_no_tmp_residue(self, tmp_path):
        stub = _StubTransport("testnet", "https://s.altnet.rippletest.net:51234")
        report = await run_audit(stub, [TXID_A])
        write_audit_pack(report, tmp_path / "pack.json")
        write_audit_report_md(report, tmp_path / "report.md")
        write_audit_report_csv(report, tmp_path / "report.csv")
        assert not list(tmp_path.glob("*.tmp"))

    def test_session_export_leaves_no_tmp_residue(self, tmp_path):
        cohort = tmp_path / "cohort"
        ws = cohort / "alice" / ".xrpl-lab"
        (ws / "proofs").mkdir(parents=True)
        (ws / "proofs" / "p.json").write_text('{"ok": 1}', encoding="utf-8")
        outfile = tmp_path / "session.zip"
        write_session_export(cohort, outfile, archive_format="zip")
        assert outfile.exists()
        assert not list(tmp_path.glob("*.tmp"))


# ── F-0fb57446: verify_audit_pack closes the trust loop ──────────────


class TestVerifyAuditPack:
    @pytest.mark.asyncio
    async def test_tampered_network_label_is_detected(self, tmp_path):
        """Flipping the sealed network (dry-run -> testnet) must fail."""
        report = await run_audit(DryRunTransport(), [TXID_A], dry_run=True)
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))

        valid, _ = verify_audit_pack(data)
        assert valid

        data["network"] = "testnet"
        data["dry_run"] = False
        valid, message = verify_audit_pack(data)
        assert not valid
        assert "mismatch" in message.lower()

    def test_rejects_non_dict_and_wrong_marker(self):
        valid, message = verify_audit_pack("not a dict")  # type: ignore[arg-type]
        assert not valid

        valid, message = verify_audit_pack({"xrpl_lab_proof_pack": True})
        assert not valid
        assert "marker" in message.lower()

    @pytest.mark.asyncio
    async def test_missing_hash_is_actionable(self, tmp_path):
        report = await run_audit(DryRunTransport(), [TXID_A])
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        del data["integrity_sha256"]
        valid, message = verify_audit_pack(data)
        assert not valid
        assert "truncated" in message.lower()


# ── F-6b3c9205: txid validation + CSV formula-injection defense ──────


class TestCsvInjectionDefense:
    def test_parse_rejects_formula_payloads(self, tmp_path):
        for payload in (
            '=HYPERLINK("http://evil","ok")',
            "=cmd|' /C calc'!A0",
            "@SUM(1+9)*cmd",
            "+2+5+cmd|' /C calc'!A0",
        ):
            f = tmp_path / "txids.txt"
            f.write_text(payload + "\n", encoding="utf-8")
            with pytest.raises(click.ClickException) as excinfo:
                parse_txids_file(f)
            assert "line 1" in str(excinfo.value)

    def test_parse_accepts_real_and_fixture_shapes(self, tmp_path):
        f = tmp_path / "txids.txt"
        f.write_text(
            f"# comment\n{TXID_A}\nTX_FAIL_1\nDRYRUN-abc123\n", encoding="utf-8"
        )
        assert parse_txids_file(f) == [TXID_A, "TX_FAIL_1", "DRYRUN-abc123"]

    def test_csv_cells_are_defused(self, tmp_path):
        """A hostile txid reaching the CSV writer (e.g. via a directly
        constructed report) is neutralized with a leading single quote."""
        report = AuditReport(
            verdicts=[
                AuditVerdict(
                    txid="=EVIL()",
                    status="not_found",
                    checks=[],
                    failures=["not found"],
                    failure_reasons=["NOT_FOUND"],
                ),
                AuditVerdict(
                    txid="-1+CMD",
                    status="not_found",
                    checks=[],
                    failures=["not found"],
                    failure_reasons=["NOT_FOUND"],
                ),
                AuditVerdict(
                    txid=TXID_A,
                    status="pass",
                    checks=["ok"],
                    failures=[],
                    failure_reasons=[],
                ),
            ],
            config=AuditConfig(),
            endpoint="https://s.altnet.rippletest.net:51234",
            tool_version="0.0.0-test",
            timestamp="2026-07-12T00:00:00Z",
        )
        path = tmp_path / "report.csv"
        write_audit_report_csv(report, path)
        content = path.read_text(encoding="utf-8")
        # Filter blank rows — newline translation on Windows can introduce
        # empty lines between CSV records.
        rows = [r for r in csv.reader(io.StringIO(content)) if r]
        assert rows[0][0] == "txid"  # header intact
        by_status_cells = {row[0] for row in rows[1:]}
        assert "'=EVIL()" in by_status_cells
        assert "'-1+CMD" in by_status_cells
        assert TXID_A in by_status_cells  # clean txid untouched


# ── F-f7520b7f: duplicate-key JSON rejected by artifact loader ───────


class TestDuplicateKeyRejection:
    def test_duplicate_top_level_key_rejected(self):
        forged = (
            '{"xrpl_lab_proof_pack": true, '
            '"address": "rFORGED", "address": "rREAL"}'
        )
        with pytest.raises(ValueError, match="duplicate key"):
            load_artifact_json(forged)

    def test_duplicate_nested_key_rejected(self):
        with pytest.raises(ValueError, match="duplicate key"):
            load_artifact_json('{"a": {"x": 1, "x": 2}}')

    def test_clean_artifact_parses_identically(self):
        pack = {"xrpl_lab_proof_pack": True, "nested": {"a": 1}, "n": 2}
        text = json.dumps(pack)
        assert load_artifact_json(text) == json.loads(text)

    def test_non_object_top_level_rejected(self):
        with pytest.raises(ValueError):
            load_artifact_json("[1, 2, 3]")


# ── F-65f845fa: transport factory provably pins per-network URLs ─────


class TestDefaultTransportFactory:
    def test_factory_pins_each_network(self, monkeypatch):
        """Via the PUBLIC surface: if the private-attr pinning ever went
        dead, network_name would classify the process default (testnet)
        and the devnet assertion here would fail."""
        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        assert _default_transport_factory("devnet").network_name == "devnet"
        assert _default_transport_factory("testnet").network_name == "testnet"

    def test_factory_ignores_cross_network_override(self, monkeypatch):
        """An env override aimed at devnet must not misroute testnet txids."""
        monkeypatch.setenv(
            "XRPL_LAB_RPC_URL", "https://s.devnet.rippletest.net:51234"
        )
        assert _default_transport_factory("testnet").network_name == "testnet"
        assert _default_transport_factory("devnet").network_name == "devnet"


# ── F-314bdd5a: dry-run packs seal endpoint='none' ───────────────────


class TestDryRunEndpointHonesty:
    def test_fully_dry_run_pack_seals_endpoint_none(self, monkeypatch):
        # Even with a credentialed URL configured, a dry-run pack implies no
        # network contact — and leaks nothing.
        monkeypatch.setenv("XRPL_LAB_RPC_URL", CRED_URL)
        state = LabState(network="dry-run", wallet_address="rTEST")
        state.record_tx("DRYTX1", "m", "dry-run", True)
        pack = generate_proof_pack(state)
        assert pack["network"] == "dry-run"
        assert pack["endpoint"] == "none"
        assert "hunter2" not in json.dumps(pack)

    def test_testnet_pack_keeps_sanitized_generation_endpoint(self, monkeypatch):
        monkeypatch.setenv(
            "XRPL_LAB_RPC_URL", "https://s.altnet.rippletest.net:51234"
        )
        state = LabState(network="testnet", wallet_address="rTEST")
        state.record_tx(TXID_A, "m", "testnet", True)
        pack = generate_proof_pack(state)
        assert pack["endpoint"] == "https://s.altnet.rippletest.net:51234"
