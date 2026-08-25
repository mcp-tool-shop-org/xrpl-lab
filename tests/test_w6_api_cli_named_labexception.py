"""Wave-6 api-cli Stage C — SEED-C-named-fix.

PERM_*, STATE_LOCKED, and STATE_MISSING_NOOPT_ISSUER must reach the learner
as code + message + hint (88c0a4e pattern) via CLI ``except LabException``
and WS ``_error_envelope`` — never a raw traceback or a generic blob.

Also pins runner recovery-save: when save_state raises LabException
(STATE_LOCKED), the console must show code/message/hint (not just the
exception type name).

Run in isolation:
    python -m pytest tests/test_w6_api_cli_named_labexception.py -q
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from xrpl_lab.api.runner_ws import _error_envelope
from xrpl_lab.errors import LabError, LabException, state_locked

ACL_ERROR = LabError(
    code="PERM_WALLET_ACL_FAILED",
    message="Could not restrict permissions on wallet.json (Windows ACL lockdown).",
    hint="icacls is required to secure the wallet on Windows.",
)

NOOPT_ERROR = LabError(
    code="STATE_MISSING_NOOPT_ISSUER",
    message=(
        "Cannot demonstrate the missing-opt-in tecNO_PERMISSION lesson: "
        "no non-opted-in issuer in context."
    ),
    hint="Run the 'create_noopt_issuer' step before this action.",
)


@pytest.mark.parametrize(
    "error",
    [ACL_ERROR, state_locked(), NOOPT_ERROR],
    ids=["PERM_WALLET_ACL_FAILED", "STATE_LOCKED", "STATE_MISSING_NOOPT_ISSUER"],
)
def test_error_envelope_preserves_code_message_hint(error: LabError) -> None:
    """_error_envelope must forward LabException code/message/hint intact."""
    envelope = _error_envelope(LabException(error))
    assert envelope["code"] == error.code
    assert envelope["message"] == error.message
    assert envelope["hint"] == error.hint
    assert envelope["severity"] in {"warning", "error", "info", "critical"}
    assert envelope["icon_hint"]


def test_runner_recovery_save_renders_state_locked(monkeypatch, tmp_path) -> None:
    """Recovery save_state(STATE_LOCKED) must print code+message+hint, not type-only."""
    import asyncio

    from xrpl_lab.modules import ModuleDef, ModuleStep
    from xrpl_lab.runner import run_module
    from xrpl_lab.transport.dry_run import DryRunTransport

    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    async def _boom(*_a, **_kw):
        raise LabException(
            LabError(code="RUNTIME_TEST", message="step boom", hint="fix me")
        )

    monkeypatch.setattr("xrpl_lab.runner._execute_action", _boom)

    def _locked(_state):
        raise LabException(state_locked())

    monkeypatch.setattr("xrpl_lab.runner.save_state", _locked)

    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=False, no_color=True)
    mod = ModuleDef(
        id="named_err_probe",
        title="Named Err Probe",
        time="1 min",
        level="beginner",
        requires=[],
        produces=[],
        checks=[],
        steps=[ModuleStep(text="boom", action="ensure_wallet", action_args={})],
        raw_body="probe",
        order=1,
    )

    ok = asyncio.run(run_module(mod, DryRunTransport(), dry_run=True, console=console))
    assert ok is False
    out = buf.getvalue()
    assert "Traceback (most recent call last)" not in out
    assert "STATE_LOCKED" in out, f"recovery save must name STATE_LOCKED:\n{out}"
    assert "Hint:" in out or "another xrpl-lab process" in out, (
        f"recovery save must surface message/hint:\n{out}"
    )


def test_cli_except_labexception_sites_use_code_message_hint() -> None:
    """Static pin: every except LabException in cli.py renders code+message+hint."""
    from pathlib import Path

    src = Path("xrpl_lab/cli.py").read_text(encoding="utf-8")
    # Split on the except LabException blocks and require the 88c0a4e trio
    # in each handler body before the next top-level def/except.
    chunks = src.split("except LabException")
    assert len(chunks) >= 5, (
        f"expected >=4 except LabException sites in cli.py, found {len(chunks) - 1}"
    )
    for i, chunk in enumerate(chunks[1:], start=1):
        body = chunk[:800]
        assert "e.error.code" in body, (
            f"except LabException site #{i} missing e.error.code render:\n{body[:200]}"
        )
        assert "e.error.message" in body, (
            f"except LabException site #{i} missing e.error.message render:\n{body[:200]}"
        )
        assert "e.error.hint" in body, (
            f"except LabException site #{i} missing e.error.hint render:\n{body[:200]}"
        )
