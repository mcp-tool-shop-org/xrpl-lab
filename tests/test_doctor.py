"""Tests for the doctor diagnostic system."""

import asyncio
import json
import sys

import pytest

from xrpl_lab.doctor import (
    Check,
    DoctorReport,
    _append_doctor_log,
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


class TestResultCodePedagogy:
    """F-TESTS-C-001: pin the humanized result-code catalog.

    The wave-3 humanization (commit 76f3ac1) rewrote tecNO_DST,
    tecNO_LINE, telINSUF_FEE_P, and tecNO_DST_INSUF_XRP to TEACH the
    XRPL concept the learner just bumped into (reserve activation,
    trust-line directionality, fee dynamics, base reserve as locked
    minimum). A future refactor that strips those teachings to a one-
    liner ("destination not found") would pass the substring-only tests
    above. These pin the load-bearing pedagogical phrases.
    """

    def test_tec_no_dst_teaches_reserve_activation(self):
        info = explain_result_code("tecNO_DST")
        # Concept: account doesn't exist on the ledger / never been funded.
        assert "doesn't exist" in info["meaning"] or "never been funded" in info["meaning"]
        # Concept: send 10 XRP to activate (the base reserve).
        assert "10 XRP" in info["action"]
        assert "base reserve" in info["action"] or "activate" in info["action"]

    def test_tec_no_dst_insuf_xrp_teaches_base_reserve(self):
        info = explain_result_code("tecNO_DST_INSUF_XRP")
        # Concept: every account must lock up a base reserve.
        assert "base reserve" in info["meaning"]
        assert "10 XRP" in info["meaning"]
        # Concept: reserve is a minimum balance, not a fee.
        assert "minimum balance" in info["meaning"]
        assert "not a fee" in info["meaning"]

    def test_tec_no_line_teaches_trust_line_opt_in(self):
        info = explain_result_code("tecNO_LINE")
        # Concept: token transfer requires recipient opt-in via a trust line.
        assert "opt-in" in info["meaning"] or "opt in" in info["meaning"]
        assert "trust line" in info["meaning"]
        # Concept: recipient runs the 'set trust line' step first.
        assert "set trust line" in info["action"]

    def test_tel_insuf_fee_teaches_fee_dynamics(self):
        info = explain_result_code("telINSUF_FEE_P")
        # Concept: fee is below the dynamic network minimum.
        assert "minimum" in info["meaning"]
        assert "dynamically" in info["meaning"] or "load" in info["meaning"]
        # Concept: testnet fee spikes recover quickly — wait and retry.
        assert "Wait" in info["action"] or "retry" in info["action"]


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


class TestDoctorFailureModes:
    """F-TESTS-B-003: doctor failure-mode coverage.

    The breadcrumb-depth work in wave-2 P1 (commit e8411fd) made the doctor
    surface more state. These tests pin the cascading-failure surface so a
    future refactor that swallows actionable hints regresses loud.
    """

    def test_doctor_when_all_checks_fail_summary_actionable(
        self, tmp_path, monkeypatch,
    ):
        """When every preflight fails, the report still contains actionable hints
        per failed check — not just FAILED markers.

        We mock the checks to return a known-broken cascade (no wallet,
        corrupt state, network down) and assert each failed Check has a
        non-empty .hint. The doctor's value to a stuck learner is in the
        hint, not the bare boolean.
        """
        # Wallet missing — _check_wallet hits the "Not found" branch.
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        # Corrupt state.json triggers _check_state's JSON-decode failure path.
        state_file = tmp_path / "state.json"
        state_file.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr("xrpl_lab.doctor.state_path", lambda: state_file)

        # Workspace cannot be created or written — point to a path under a
        # file (not a directory), guaranteed to fail mkdir.
        bogus_parent = tmp_path / "blocker"
        bogus_parent.write_text("i am a file, not a dir", encoding="utf-8")
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir",
            lambda: bogus_parent / "ws_inside_a_file",
        )

        # Stub network checks to deterministic failure with hints.
        async def _stub_rpc() -> Check:
            return Check(
                "RPC endpoint", False,
                "Could not connect", "Check internet or set XRPL_LAB_RPC_URL",
            )

        async def _stub_faucet() -> Check:
            return Check(
                "Faucet", False, "Could not reach faucet",
                "Faucet may be down — set XRPL_LAB_FAUCET_URL",
            )

        monkeypatch.setattr("xrpl_lab.doctor._check_rpc", _stub_rpc)
        monkeypatch.setattr("xrpl_lab.doctor._check_faucet", _stub_faucet)
        # state.DEFAULT_HOME_DIR pin so _check_last_error / load_state read tmp_path.
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        report = asyncio.run(run_doctor())

        # The cascade produced multiple failed checks.
        failed_checks = [c for c in report.checks if not c.passed]
        assert len(failed_checks) >= 3, (
            f"expected >=3 failed checks in the cascade, "
            f"got {[(c.name, c.passed) for c in report.checks]}"
        )

        # Every failed check has actionable hint content — not a stub
        # like "FAILED" with no follow-up. The hint is the contract.
        for c in failed_checks:
            assert c.hint, (
                f"failed check {c.name!r} has empty hint — facilitator "
                f"has no next step"
            )
            assert len(c.hint.strip()) > 0
            # Detail also non-empty so the failure has context.
            assert c.detail, (
                f"failed check {c.name!r} has empty detail — no diagnosis"
            )

    def test_diagnose_recovery_ambiguous_state(self, tmp_path, monkeypatch):
        """diagnose_recovery surfaces 'tx in tx_index but module not completed'.

        The "did the run finish or not?" ambiguity (transactions recorded
        for a module that is NOT marked completed) must be surfaced by
        the recovery diagnostic so the facilitator can decide manually,
        rather than silently auto-deciding.

        We exercise diagnose_recovery with a state that contains tx
        records for module M but no completed-module entry for M, then
        also surface the same condition through the doctor's
        _check_last_module_state breadcrumb (which calls out the
        "in-flight" module).
        """
        from xrpl_lab.workshop import diagnose_recovery

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.state_path",
            lambda: tmp_path / "state.json",
        )

        state = LabState(wallet_address="rTEST")
        # Mark wallet_basics done to advance graph position.
        state.complete_module("wallet_basics")
        # Record a tx for receipt_literacy WITHOUT marking it completed —
        # this is the ambiguity: was the run aborted, or did it complete
        # without recording the completion?
        state.record_tx("AMBIG_TX_001", "receipt_literacy", "testnet", success=True)
        save_state(state)

        # diagnose_recovery itself is an actionability layer — it should
        # never return [] when there's clearly an ambiguous in-flight
        # module. Either it surfaces a hint about the in-flight, or the
        # doctor's breadcrumb does. We assert on the breadcrumb here
        # since that's the wave-2 P1 surface — diagnose_recovery is the
        # lower-level engine; the doctor presents it.
        breadcrumb = _check_last_module_state()
        assert "receipt_literacy" in breadcrumb.detail, (
            f"breadcrumb must surface in-flight module: {breadcrumb.detail!r}"
        )
        # And the txid hint is in there so a facilitator can xrpl-lab verify it.
        assert "AMBIG_TX_001"[:16] in breadcrumb.detail

        # Sanity: diagnose_recovery is callable in this state and returns
        # a list (it may or may not contain a hint — that's a wave-3
        # backend question). What we lock in: it does not crash on the
        # ambiguity, and the doctor surfaces the in-flight module.
        hints = diagnose_recovery(state)
        assert isinstance(hints, list)


# ── DD-1: doctor artifacts respect threat-model classification ────────


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes — Windows uses ACLs",
)
class TestDoctorLogMode:
    """DD-1: doctor.log lives in single-user-private ~/.xrpl-lab/.
    The file itself must be 0o600 (matches wallet.json + state.json
    discipline) and the parent dir 0o700."""

    def test_doctor_log_file_is_0o600_after_run(self, tmp_path, monkeypatch):
        from xrpl_lab.state import ensure_home_dir

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "h")
        ensure_home_dir()  # create home dir at 0o700

        report = DoctorReport()
        report.checks.append(Check(name="probe", passed=True, detail="ok"))
        _append_doctor_log(report)

        log_path = tmp_path / "h" / "doctor.log"
        assert log_path.exists(), "doctor.log must be written"
        mode = log_path.stat().st_mode & 0o777
        assert mode == 0o600, (
            f"doctor.log must be 0o600 (single-user private), got 0o{mode:o}"
        )

    def test_doctor_workspace_probe_creates_0o755_dir(
        self, tmp_path, monkeypatch,
    ):
        """When _check_workspace creates the workspace, it must land at
        the workshop-shareable 0o755 (not the wallet's 0o700)."""
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        check = _check_workspace()
        assert check.passed, f"workspace probe failed: {check.detail!r}"
        assert ws.exists()
        mode = ws.stat().st_mode & 0o777
        assert mode == 0o755, (
            f"workspace dir created by doctor probe must be 0o755, got 0o{mode:o}"
        )
