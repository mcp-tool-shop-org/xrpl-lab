"""Tests for the doctor diagnostic system."""

import json

from xrpl_lab.doctor import (
    Check,
    DoctorReport,
    _check_env_overrides,
    _check_last_error,
    _check_state,
    _check_wallet,
    _check_workspace,
    explain_result_code,
)
from xrpl_lab.state import LabState, save_state


class TestExplainResultCode:
    def test_known_code(self):
        info = explain_result_code("tesSUCCESS")
        assert info["category"] == "success"
        assert "action" in info

    def test_tec_code(self):
        info = explain_result_code("tecUNFUNDED_PAYMENT")
        assert info["category"] == "claimed"
        assert "fund" in info["action"].lower()

    def test_unknown_tec(self):
        info = explain_result_code("tecSOMETHING_NEW")
        assert info["category"] == "claimed"

    def test_unknown_prefix(self):
        info = explain_result_code("xyzGARBAGE")
        assert info["category"] == "unknown"

    def test_local_error(self):
        info = explain_result_code("local_error")
        assert info["category"] == "local"


class TestDoctorReport:
    def test_all_passed(self):
        report = DoctorReport(
            checks=[Check("A", True), Check("B", True)]
        )
        assert report.all_passed
        assert "2/2" in report.summary

    def test_some_failed(self):
        report = DoctorReport(
            checks=[Check("A", True), Check("B", False)]
        )
        assert not report.all_passed
        assert "1/2" in report.summary


class TestLocalChecks:
    def test_wallet_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        check = _check_wallet()
        assert not check.passed
        assert "Not found" in check.detail

    def test_wallet_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        wallet_file = tmp_path / "wallet.json"
        wallet_file.write_text(json.dumps({"address": "rTEST123"}), encoding="utf-8")
        check = _check_wallet()
        assert check.passed
        assert "rTEST123" in check.detail

    def test_wallet_corrupted(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        (tmp_path / "wallet.json").write_text("{bad json", encoding="utf-8")
        check = _check_wallet()
        assert not check.passed

    def test_state_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.doctor.state_path", lambda: tmp_path / "state.json")
        check = _check_state()
        assert check.passed
        assert "fresh" in check.detail.lower()

    def test_state_valid(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.state_path", lambda: tmp_path / "state.json")
        state = LabState()
        state.complete_module("receipt_literacy")
        save_state(state)
        check = _check_state()
        assert check.passed
        assert "1 module" in check.detail

    def test_state_corrupted(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text("{bad", encoding="utf-8")
        monkeypatch.setattr("xrpl_lab.doctor.state_path", lambda: state_file)
        check = _check_state()
        assert not check.passed

    def test_workspace_creatable(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: ws)
        check = _check_workspace()
        assert check.passed

    def test_env_overrides_none(self, monkeypatch):
        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        monkeypatch.delenv("XRPL_LAB_FAUCET_URL", raising=False)
        check = _check_env_overrides()
        assert check.passed
        assert "None" in check.detail

    def test_env_overrides_set(self, monkeypatch):
        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://custom.rpc")
        check = _check_env_overrides()
        assert check.passed
        assert "custom.rpc" in check.detail

    def test_last_error_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        check = _check_last_error()
        assert check.passed
        assert "No failed" in check.detail

    def test_last_error_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        state = LabState()
        state.record_tx("FAIL01", "failure_literacy", "testnet", False)
        save_state(state)
        check = _check_last_error()
        assert check.passed  # Informational, not a failure
        assert "failure_literacy" in check.detail
