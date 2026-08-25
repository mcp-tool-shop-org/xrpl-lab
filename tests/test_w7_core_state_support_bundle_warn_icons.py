"""Wave-7/8 core-state — support-bundle WARN vs FAIL icons (F-dc21ac97 / F-71d35d61).

Warn-tier doctor checks (curriculum drift, etc.) must not render as public
``[FAIL]`` in support-bundle / feedback markdown. Thread severity into
``doctor_checks`` and use a WARN icon when ``severity == 'warn'``.
"""

from __future__ import annotations

from xrpl_lab.doctor import Check, public_check_icon
from xrpl_lab.feedback import generate_feedback
from xrpl_lab.state import CompletedModule, LabState
from xrpl_lab.workshop import (
    LearnerStatus,
    SupportBundle,
    TrackProgress,
    generate_support_bundle,
)


def test_public_check_icon_warn_vs_fail():
    assert public_check_icon(passed=True, severity="fail") == "PASS"
    assert public_check_icon(passed=True, severity="warn") == "PASS"
    assert public_check_icon(passed=False, severity="warn") == "WARN"
    assert public_check_icon(passed=False, severity="fail") == "FAIL"


def _minimal_learner() -> LearnerStatus:
    return LearnerStatus(
        version="2.4.0",
        wallet_address="rTest",
        network="testnet",
        current_module=None,
        current_track=None,
        current_mode=None,
        completed_modules=["child_mod"],
        completed_count=1,
        total_modules=10,
        blockers=[],
        is_blocked=False,
        track_progress=[
            TrackProgress(
                track="foundations",
                completed=["child_mod"],
                remaining=["a", "b"],
                total=3,
                done=1,
                is_complete=False,
            )
        ],
        last_activity=None,
        last_module=None,
        total_transactions=0,
        failed_transactions=0,
        has_proof_pack=False,
        has_certificate=False,
        report_count=0,
        all_verified=True,
        unverified_modules=[],
    )


def test_support_bundle_markdown_warn_not_fail():
    """Constructed warn-tier failure must render [WARN], never [FAIL]."""
    bundle = SupportBundle(
        version="2.4.0",
        generated="2026-08-25T00:00:00+00:00",
        python_version="3.12.0",
        platform_info="Windows",
        learner=_minimal_learner(),
        network="testnet",
        rpc_url="https://s.altnet.rippletest.net:51234",
        faucet_url="https://faucet.altnet.rippletest.net",
        recent_transactions=[],
        doctor_checks=[
            {
                "name": "Last module state",
                "passed": False,
                "detail": "drift: child_mod (missing prereqs: parent_mod)",
                "hint": "Run: xrpl-lab curriculum validate",
                "severity": "warn",
            },
            {
                "name": "RPC endpoint",
                "passed": False,
                "detail": "unreachable",
                "hint": "check network",
                "severity": "fail",
            },
            {
                "name": "Python version",
                "passed": True,
                "detail": "3.12",
                "hint": "",
                "severity": "fail",
            },
        ],
    )
    md = bundle.to_markdown()
    assert "[WARN] Last module state" in md
    assert "[FAIL] Last module state" not in md
    assert "[FAIL] RPC endpoint" in md
    assert "[PASS] Python version" in md


def test_generate_support_bundle_threads_severity(tmp_path, monkeypatch):
    """Live generate_support_bundle must seal severity into doctor_checks."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.workshop.get_workspace_dir", lambda: tmp_path / "ws")

    # Curriculum drift: complete a module whose prerequisite is missing.
    # Use a real pair from the shipped catalog if possible; otherwise inject
    # a synthetic doctor report via monkeypatch.
    async def _fake_doctor():
        from xrpl_lab.doctor import DoctorReport

        return DoctorReport(
            checks=[
                Check(
                    "Last module state",
                    False,
                    "drift: child (missing prereqs: parent)",
                    "Run: xrpl-lab curriculum validate",
                    severity="warn",
                ),
                Check("RPC endpoint", True, "ok"),
            ]
        )

    monkeypatch.setattr("xrpl_lab.doctor.run_doctor", _fake_doctor)

    bundle = generate_support_bundle(
        LabState(
            wallet_address="rTestAddr123",
            completed_modules=[
                CompletedModule(module_id="receipt_literacy", completed_at=1.0)
            ],
            tx_index=[],
        )
    )

    warn_rows = [c for c in bundle.doctor_checks if c.get("name") == "Last module state"]
    assert warn_rows, "expected Last module state check in doctor_checks"
    assert warn_rows[0].get("severity") == "warn"
    assert "severity" in bundle.doctor_checks[0]

    md = bundle.to_markdown()
    assert "[WARN] Last module state" in md
    assert "[FAIL] Last module state" not in md


def test_feedback_markdown_warn_not_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.load_state", lambda: LabState(
        wallet_address="rTestAddr123", completed_modules=[], tx_index=[]
    ))

    async def _fake_doctor():
        from xrpl_lab.doctor import DoctorReport

        return DoctorReport(
            checks=[
                Check(
                    "Last module state",
                    False,
                    "drift: x",
                    "hint",
                    severity="warn",
                ),
                Check("Hard break", False, "down", "fix it", severity="fail"),
            ]
        )

    monkeypatch.setattr("xrpl_lab.feedback.run_doctor", _fake_doctor)
    md = generate_feedback()
    assert "[WARN] Last module state" in md
    assert "[FAIL] Last module state" not in md
    assert "[FAIL] Hard break" in md
