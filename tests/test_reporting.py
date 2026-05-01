"""Tests for artifact generation."""

import hashlib
import json
import tarfile
import zipfile

import pytest

from xrpl_lab.reporting import (
    generate_certificate,
    generate_proof_pack,
    write_certificate,
    write_module_report,
    write_proof_pack,
    write_session_export,
)
from xrpl_lab.state import LabState


@pytest.fixture
def completed_state():
    state = LabState(
        network="testnet",
        wallet_address="rTEST123456789",
    )
    state.complete_module("receipt_literacy", txids=["TX001", "TX002"])
    state.record_tx("TX001", "receipt_literacy", "testnet", True)
    state.record_tx("TX002", "receipt_literacy", "testnet", True)
    return state


class TestProofPack:
    def test_structure(self, completed_state):
        pack = generate_proof_pack(completed_state)
        assert pack["xrpl_lab_proof_pack"] is True
        assert pack["network"] == "testnet"
        assert pack["address"] == "rTEST123456789"
        assert len(pack["completed_modules"]) == 1
        assert pack["total_transactions"] == 2
        assert pack["successful_transactions"] == 2
        assert pack["failed_transactions"] == 0
        assert "sha256" in pack
        assert "endpoint" in pack
        assert "transactions" in pack
        assert len(pack["transactions"]) == 2

    def test_no_secrets(self, completed_state):
        pack = generate_proof_pack(completed_state)
        text = json.dumps(pack)
        assert "seed" not in text.lower()
        assert "secret" not in text.lower()

    def test_receipt_table(self, completed_state):
        pack = generate_proof_pack(completed_state)
        assert "receipt_table" in pack
        table = pack["receipt_table"]
        assert len(table) == 2
        row = table[0]
        assert "txid" in row
        assert "txid_full" in row
        assert "module" in row
        assert "status" in row
        assert "network" in row
        assert "timestamp" in row
        assert row["status"] == "ok"
        assert row["module"] == "receipt_literacy"
        assert row["txid_full"] == "TX001"

    def test_receipt_table_failed_tx(self):
        state = LabState(network="testnet", wallet_address="rTEST")
        state.complete_module("test", txids=["TX1"])
        state.record_tx("TX1", "test", "testnet", True)
        state.record_tx("TX_FAIL", "test", "testnet", False)
        pack = generate_proof_pack(state)
        table = pack["receipt_table"]
        assert len(table) == 2
        assert table[0]["status"] == "ok"
        assert table[1]["status"] == "FAIL"

    def test_explorer_urls(self, completed_state):
        pack = generate_proof_pack(completed_state)
        mod = pack["completed_modules"][0]
        assert all("testnet.xrpl.org" in url for url in mod["explorer_urls"])

    def test_integrity_hash(self, completed_state):
        pack = generate_proof_pack(completed_state)
        sha = pack.pop("sha256")
        assert len(sha) == 64  # SHA-256 hex

    def test_write(self, completed_state, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: tmp_path)
        path = write_proof_pack(completed_state)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["xrpl_lab_proof_pack"] is True


class TestCertificate:
    def test_structure(self, completed_state):
        cert = generate_certificate(completed_state)
        assert cert["xrpl_lab_certificate"] is True
        assert "receipt_literacy" in cert["modules_completed"]
        assert cert["total_modules"] == 1

    def test_no_secrets(self, completed_state):
        cert = generate_certificate(completed_state)
        text = json.dumps(cert)
        assert "seed" not in text.lower()

    def test_write(self, completed_state, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: tmp_path)
        path = write_certificate(completed_state)
        assert path.exists()


class TestModuleReport:
    def test_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: tmp_path)
        path = write_module_report(
            module_id="receipt_literacy",
            title="Receipt Literacy",
            sections=[
                ("What happened", "Sent a payment."),
                ("Verification", "All fields checked."),
            ],
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Receipt Literacy" in content
        assert "Sent a payment." in content
        assert "XRPL Lab" in content

    def test_report_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: tmp_path)
        path = write_module_report("test_mod", "Test", [("A", "B")])
        assert path.name == "test_mod.md"
        assert path.parent.name == "reports"


# ── Default-path safety regression (F-TESTS-002) ─────────────────────


class TestDefaultPathSafety:
    """Lock in that write_proof_pack's default output stays inside the
    .xrpl-lab/ workspace sandbox. CLI is the trust boundary for caller-
    supplied paths; this is purely a regression catch for the default.
    """

    def test_default_proof_pack_path_is_inside_workspace(
        self, completed_state, tmp_path, monkeypatch
    ):
        """When write_proof_pack uses its default output_dir, the resulting
        path must resolve under the workspace root."""
        # Redirect get_workspace_dir() to a tmp .xrpl-lab/ root so we don't
        # touch the real workspace.
        ws = tmp_path / ".xrpl-lab"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)

        path = write_proof_pack(completed_state)  # no output_dir → default

        workspace_root = ws.resolve()
        assert path.resolve().is_relative_to(workspace_root), (
            f"default proof-pack path escaped workspace: "
            f"{path.resolve()} not under {workspace_root}"
        )


# ── F-BACKEND-FT-002: session-export ─────────────────────────────────


def _seed_learner_workspace(
    cohort_dir,
    learner_id: str,
    *,
    proofs: dict | None = None,
    reports: dict | None = None,
    audit_packs: dict | None = None,
    certificates: dict | None = None,
    wallet_seed: str | None = None,
    state_payload: str | None = None,
    doctor_log: str | None = None,
):
    """Build a fake learner subdir under cohort_dir/<learner-id>/.xrpl-lab/."""
    workspace = cohort_dir / learner_id / ".xrpl-lab"
    workspace.mkdir(parents=True)
    if proofs:
        (workspace / "proofs").mkdir()
        for fname, content in proofs.items():
            (workspace / "proofs" / fname).write_text(content, encoding="utf-8")
    if reports:
        (workspace / "reports").mkdir()
        for fname, content in reports.items():
            (workspace / "reports" / fname).write_text(content, encoding="utf-8")
    if audit_packs:
        (workspace / "audit_packs").mkdir()
        for fname, content in audit_packs.items():
            (workspace / "audit_packs" / fname).write_text(content, encoding="utf-8")
    if certificates:
        (workspace / "certificates").mkdir()
        for fname, content in certificates.items():
            (workspace / "certificates" / fname).write_text(
                content, encoding="utf-8",
            )
    if wallet_seed is not None:
        (workspace / "wallet.json").write_text(wallet_seed, encoding="utf-8")
    if state_payload is not None:
        (workspace / "state.json").write_text(state_payload, encoding="utf-8")
    if doctor_log is not None:
        (workspace / "doctor.log").write_text(doctor_log, encoding="utf-8")
    return workspace


class TestSessionExport:
    """Cohort artifact archive with privacy-preserving manifest."""

    def test_session_export_includes_all_artifact_types(self, tmp_path):
        """F-BACKEND-FT-002: proofs + reports + audit_packs + certs all
        land in the archive under <learner-id>/<subdir>/<file>."""
        cohort = tmp_path / "cohort"
        cohort.mkdir()
        _seed_learner_workspace(
            cohort, "alice",
            proofs={"proof.json": '{"ok":true}'},
            reports={"receipt.md": "# done"},
            audit_packs={"audit.json": '{"audit":1}'},
            certificates={"cert.json": '{"cert":true}'},
        )
        outfile = tmp_path / "session.tar.gz"
        summary = write_session_export(cohort, outfile, archive_format="tar.gz")
        assert outfile.exists()
        assert summary["learners"] == 1
        with tarfile.open(outfile, "r:gz") as tar:
            names = set(tar.getnames())
        assert "MANIFEST.json" in names
        assert "alice/proofs/proof.json" in names
        assert "alice/reports/receipt.md" in names
        assert "alice/audit_packs/audit.json" in names
        assert "alice/certificates/cert.json" in names

    def test_session_export_excludes_wallet_and_state(self, tmp_path):
        """F-BACKEND-FT-002: wallet.json + state.json + doctor.log are
        NEVER archived — workshop threat-model line. Public artifacts
        still flow through."""
        cohort = tmp_path / "cohort"
        cohort.mkdir()
        _seed_learner_workspace(
            cohort, "alice",
            proofs={"proof.json": '{"ok":true}'},
            wallet_seed='{"seed":"sSECRET"}',
            state_payload='{"version":"1.5.0","completed_modules":[]}',
            doctor_log="diagnostic noise",
        )
        outfile = tmp_path / "session.tar.gz"
        write_session_export(cohort, outfile, archive_format="tar.gz")
        with tarfile.open(outfile, "r:gz") as tar:
            names = set(tar.getnames())
            # Public artifact survives
            assert "alice/proofs/proof.json" in names
            # Private artifacts are absent — match by basename and full
            # path to be defensive against future archive-path drift.
            for forbidden in (
                "alice/wallet.json", "alice/state.json", "alice/doctor.log",
            ):
                assert forbidden not in names, (
                    f"{forbidden} leaked into session export"
                )
            # Also check no entry contains 'seed' content via scan
            for member in tar.getmembers():
                if member.isfile() and "wallet" in member.name.lower():
                    pytest.fail(
                        f"wallet-named file {member.name} should not be archived"
                    )

    def test_session_export_manifest_sha256_correct(self, tmp_path):
        """F-BACKEND-FT-002: MANIFEST.json sha256 fields match archived
        files' actual SHA-256 — facilitators verifying post-share can
        trust the manifest as ground truth."""
        cohort = tmp_path / "cohort"
        cohort.mkdir()
        proof_content = '{"proof":"data"}'
        report_content = "# Receipt\n\nA short report.\n"
        _seed_learner_workspace(
            cohort, "alice",
            proofs={"p.json": proof_content},
            reports={"r.md": report_content},
        )
        outfile = tmp_path / "session.tar.gz"
        write_session_export(cohort, outfile, archive_format="tar.gz")

        # Extract MANIFEST.json + the archived files; verify hashes match
        # the original sources.
        with tarfile.open(outfile, "r:gz") as tar:
            mf = tar.extractfile("MANIFEST.json")
            assert mf is not None
            manifest = json.loads(mf.read().decode("utf-8"))
        files_by_path = {f["path"]: f for f in manifest["files"]}

        # Each manifest sha256 must equal sha256 of the source file
        proof_src = cohort / "alice" / ".xrpl-lab" / "proofs" / "p.json"
        report_src = cohort / "alice" / ".xrpl-lab" / "reports" / "r.md"
        expected_proof_sha = hashlib.sha256(
            proof_src.read_bytes()
        ).hexdigest()
        expected_report_sha = hashlib.sha256(
            report_src.read_bytes()
        ).hexdigest()
        assert files_by_path["alice/proofs/p.json"]["sha256"] == \
            expected_proof_sha
        assert files_by_path["alice/reports/r.md"]["sha256"] == \
            expected_report_sha

    def test_session_export_zip_format(self, tmp_path):
        """Sanity: zip variant produces a readable archive too."""
        cohort = tmp_path / "cohort"
        cohort.mkdir()
        _seed_learner_workspace(
            cohort, "alice", proofs={"p.json": '{"ok":1}'},
        )
        outfile = tmp_path / "session.zip"
        write_session_export(cohort, outfile, archive_format="zip")
        with zipfile.ZipFile(outfile) as zf:
            names = set(zf.namelist())
        assert "MANIFEST.json" in names
        assert "alice/proofs/p.json" in names
