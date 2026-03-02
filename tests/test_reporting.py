"""Tests for artifact generation."""

import json

import pytest

from xrpl_lab.reporting import (
    generate_certificate,
    generate_proof_pack,
    write_certificate,
    write_module_report,
    write_proof_pack,
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
