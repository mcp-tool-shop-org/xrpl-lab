"""Tests for the doctor diagnostic system."""

import asyncio
import json

from xrpl_lab.doctor import (
    Check,
    DoctorReport,
    _check_env_overrides,
    _check_last_error,
    _check_last_module_state,
    _check_state,
    _check_wallet,
    _check_workspace,
    explain_result_code,
    run_doctor,
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


class TestLastModuleState:
    """F-BACKEND-B-003: facilitator breadcrumb trail.

    The new ``_check_last_module_state`` reports a breadcrumb of curriculum
    progress so facilitators debugging a stuck learner see context (last
    completed module, in-flight module, drift) instead of just "state ok".
    """

    def test_doctor_surfaces_last_module_state_when_state_present(
        self, tmp_path, monkeypatch,
    ):
        # Point both home and state_path at a tmp dir, then seed a state
        # file with a known last-attempted-but-incomplete module.
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.state_path",
            lambda: tmp_path / "state.json",
        )
        state = LabState()
        state.complete_module("receipt_literacy")
        # Record an attempt for a different module that hasn't completed.
        state.record_tx(
            "INFLIGHT_TXID_001", "amm_swap_basics", "testnet", success=False,
        )
        save_state(state)

        check = _check_last_module_state()

        # Surfaces the completed module
        assert "receipt_literacy" in check.detail
        # Surfaces the in-flight (attempted-but-incomplete) module
        assert "amm_swap_basics" in check.detail
        # Surfaces the txid hint for the in-flight module
        assert "INFLIGHT_TXID_001"[:16] in check.detail

    def test_doctor_handles_missing_state_gracefully(
        self, tmp_path, monkeypatch,
    ):
        # No state.json present at the location — doctor still runs and
        # the new check returns a "no state yet" status (not a failure).
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.state_path",
            lambda: tmp_path / "state.json",
        )
        check = _check_last_module_state()
        assert check.passed
        assert (
            "no state" in check.detail.lower()
            or "fresh" in check.detail.lower()
        )

    def test_doctor_log_appended_when_home_exists(
        self, tmp_path, monkeypatch,
    ):
        # Run doctor twice and assert ~/.xrpl-lab/doctor.log has 2 lines,
        # each parses as JSON.
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: home)
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", home)
        # Avoid network checks turning into real HTTP calls in this unit
        # test. Replace _check_rpc/_check_faucet with stubs returning a
        # passing Check; the log-write code path doesn't care about
        # contents, only that run_doctor invokes _append_doctor_log.
        async def _stub_rpc() -> Check:
            return Check("RPC endpoint", True, "stub")

        async def _stub_faucet() -> Check:
            return Check("Faucet", True, "stub")

        monkeypatch.setattr("xrpl_lab.doctor._check_rpc", _stub_rpc)
        monkeypatch.setattr("xrpl_lab.doctor._check_faucet", _stub_faucet)

        asyncio.run(run_doctor())
        asyncio.run(run_doctor())

        log_path = home / "doctor.log"
        assert log_path.exists(), "doctor.log should be written when home exists"
        lines = [
            line for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2, f"expected 2 log lines, got {len(lines)}"
        for line in lines:
            record = json.loads(line)  # must parse as JSON
            assert "ts" in record
            assert "checks" in record
            assert "summary" in record
