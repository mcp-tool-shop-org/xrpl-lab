"""2.7.7 (#39): doctor's "Last error" after a ``run --force`` recovery.

Book Keeper's 2.7.6 live check: run 1 of clawback_101 failed before reaching
the network (``failed`` placeholders), ``run --force`` passed, yet doctor (and
the support bundle that carries its checks) still reported "Last failure in
'clawback_101': tx failed" with the hint "Run: xrpl-lab verify --tx failed".
A failure older than its module's passing latest run is history, as live
verification has treated it since 2.7.5; and a step that never reached the
network has no hash to verify.
"""

from __future__ import annotations

import pytest

from xrpl_lab import doctor
from xrpl_lab.state import CompletedModule, LabState, TxRecord, save_state


def _rec(txid, t, module="clawback_101", **kw):
    return TxRecord(txid=txid, module_id=module, timestamp=t, network="testnet",
                    success=False, **kw)


def _done(t, verified=True, module="clawback_101"):
    return CompletedModule(module_id=module, completed_at=t, verified=verified)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    return tmp_path


def test_a_passing_rerun_supersedes_the_failures_before_it() -> None:
    state = LabState(tx_index=[_rec("failed", 100.0), _rec("A" * 64, 110.0)],
                     completed_modules=[_done(300.0)])
    assert state.current_failures() == []


def test_failures_stay_when_the_latest_run_failed_or_came_later() -> None:
    unverified = LabState(tx_index=[_rec("failed", 100.0)],
                          completed_modules=[_done(300.0, verified=False)])
    assert [r.txid for r in unverified.current_failures()] == ["failed"]
    later = LabState(tx_index=[_rec("B" * 64, 400.0)], completed_modules=[_done(300.0)])
    assert [r.txid for r in later.current_failures()] == ["B" * 64]
    other = LabState(tx_index=[_rec("C" * 64, 100.0, module="checks_101")],
                     completed_modules=[_done(300.0)])
    assert [r.txid for r in other.current_failures()] == ["C" * 64]


def test_expected_rejections_are_never_current_failures() -> None:
    state = LabState(tx_index=[_rec("D" * 64, 100.0, expected=True)])
    assert state.current_failures() == []


def test_doctor_is_clear_after_a_force_recovery(home) -> None:
    save_state(LabState(tx_index=[_rec("failed", 100.0)], completed_modules=[_done(300.0)]))
    assert doctor._check_last_error().detail == "No failed transactions"


def test_a_never_submitted_failure_gets_a_rerun_hint(home) -> None:
    save_state(LabState(tx_index=[_rec("failed", 100.0)]))
    check = doctor._check_last_error()
    assert "failed before its transaction reached the network" in check.detail
    assert check.hint == "Run: xrpl-lab run clawback_101 --force to retry the module"
    assert "verify --tx" not in check.hint


def test_a_failure_with_a_hash_keeps_the_verify_hint(home) -> None:
    save_state(LabState(tx_index=[_rec("E" * 64, 100.0)]))
    check = doctor._check_last_error()
    assert check.hint == f"Run: xrpl-lab verify --tx {'E' * 64} for details"

