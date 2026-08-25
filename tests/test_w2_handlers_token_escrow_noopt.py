"""Wave 2 (health-amend-a) regression test — handlers domain.

Pins F-57c984e9 (HIGH): the shipped modules/token_escrow_101.md Step 10
("see the failure — a token escrow WITHOUT opt-in") can never demonstrate the
tecNO_PERMISSION lesson it advertises in its own frontmatter `checks:` list,
because its required setup handler (create_noopt_issuer, which sets
context['noopt_issuer_address']) is never invoked by any step in the module.

Before this fix, handle_create_token_escrow_expect_fail
(xrpl_lab/handlers.py) printed a yellow console warning when
'noopt_issuer_address' was absent from context, then silently fell back to
the MAIN (already opted-in) issuer and submitted anyway. Because
asfAllowTrustLineLocking is account-wide, that submit could never hit the
opt-in check — it instead failed tecNO_LINE (no trust line for the "NOP"
currency against that issuer), which was console-printed as an unmet
expectation but never raised or otherwise surfaced as a structured failure.
A real run of the shipped module therefore "completed successfully"
(run_module returned True) while silently teaching the WRONG result code.

Per the wave-2 ADVISOR CONTRACT for this finding, a silent tecNO_LINE is
forbidden — the handler must now raise a structured, explicit failure naming
the missing prerequisite instead of degrading quietly. This test drives the
REAL shipped modules/token_escrow_101.md end-to-end through run_module()
(offline DryRunTransport, dry_run=True, zero network calls, zero writes
outside tmp_path) to prove the actual shipped module now fails LOUD instead
of teaching the wrong lesson quietly. modules/token_escrow_101.md itself is
NOT modified by this wave (out of the handlers domain's scope) — until the
coordinator adds a create_noopt_issuer step before Step 10, this test
documents that the module halts with a named, actionable error rather than
silently mis-teaching.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers  # noqa: F401 -- import registers actions as a side effect
from xrpl_lab.actions import wallet as wallet_mod
from xrpl_lab.modules import parse_module
from xrpl_lab.runner import run_module
from xrpl_lab.state import LabState, save_state
from xrpl_lab.transport.dry_run import DryRunTransport

MODULE_PATH = Path(__file__).parent.parent / "modules" / "token_escrow_101.md"


def _load_token_escrow_module():
    return parse_module(MODULE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_shipped_module_fails_loud_instead_of_silent_tecno_line(
    tmp_path, monkeypatch,
):
    """F-57c984e9: an end-to-end dry-run of the SHIPPED token_escrow_101
    module must not report success while silently recording tecNO_LINE in
    place of the advertised tecNO_PERMISSION lesson."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    save_state(LabState(network="dry-run", wallet_address=w.address))

    module = _load_token_escrow_module()
    transport = DryRunTransport()
    out = io.StringIO()
    console = Console(file=out, no_color=True, width=200)
    # Patch console.input so the between-step pause doesn't read real stdin
    # (established pattern — see test_reswarm3_backend.py).
    console.input = lambda _p="": ""  # type: ignore[assignment]

    ok = await run_module(module, transport, dry_run=True, console=console)
    text = out.getvalue()

    # A "successful" run of this shipped module is a defect: Step 10 cannot
    # possibly exercise its advertised tecNO_PERMISSION lesson (the module
    # never runs create_noopt_issuer), so a True return here means the wrong
    # lesson (tecNO_LINE) was taught silently.
    assert ok is False, (
        "run_module reported success (ok=True) for the shipped "
        "token_escrow_101 module even though Step 10's prerequisite "
        "(create_noopt_issuer) never ran — this means the tecNO_PERMISSION "
        "lesson was silently replaced by a different, unreported failure. "
        f"Console output was:\n{text}"
    )
    # The failure must be STRUCTURED and must NAME the missing prerequisite —
    # a learner (or CI) reading the output must be able to tell exactly what
    # to do, not just that "something" tec-failed.
    assert "create_noopt_issuer" in text, (
        f"failure output does not name the missing prerequisite step; "
        f"console output was:\n{text}"
    )
    # The wrong result code must never reach the console at all post-fix —
    # the step must fail BEFORE attempting the submit, not after.
    assert "tecNO_LINE" not in text, (
        f"the wrong-lesson result code leaked into the console even though "
        f"the step should fail before ever submitting the transaction; "
        f"console output was:\n{text}"
    )


@pytest.mark.asyncio
async def test_noopt_issuer_prerequisite_still_yields_real_tecno_permission(
    tmp_path, monkeypatch,
):
    """Positive control: this is what modules/token_escrow_101.md SHOULD do
    (mirroring modules/clawback_101.md's create_noclaw_issuer wiring) — call
    create_noopt_issuer before create_token_escrow_expect_fail. Once the
    prerequisite is genuinely established, the real tecNO_PERMISSION lesson
    must fire; the handler-side fix must not have broken the working path.
    """
    from xrpl_lab.modules import ModuleDef, ModuleStep

    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    save_state(LabState(network="dry-run", wallet_address=w.address))

    # Minimal module: the real prerequisite chain (wallet/issuer/opt-in/
    # trust/issue) plus a create_noopt_issuer step BEFORE the expect-fail
    # step — the exact fix the coordinator will land in modules/.
    module = ModuleDef(
        id="w2_noopt_probe",
        title="noopt probe",
        time="1 min",
        level="beginner",
        requires=[],
        produces=["txid"],
        checks=[],
        steps=[
            ModuleStep(text="", action="ensure_wallet", action_args={}),
            ModuleStep(text="", action="ensure_funded", action_args={}),
            ModuleStep(text="", action="create_issuer_wallet", action_args={}),
            ModuleStep(text="", action="fund_issuer", action_args={}),
            ModuleStep(
                text="", action="set_allow_trustline_locking", action_args={},
            ),
            ModuleStep(
                text="", action="set_trust_line",
                action_args={"currency": "GLD", "limit": "1000"},
            ),
            ModuleStep(
                text="", action="issue_token",
                action_args={"currency": "GLD", "amount": "100"},
            ),
            ModuleStep(
                text="", action="create_noopt_issuer",
                action_args={"currency": "NOP", "amount": "50"},
            ),
            ModuleStep(
                text="", action="create_token_escrow_expect_fail",
                action_args={"currency": "NOP", "amount": "50"},
            ),
        ],
        order=1,
        track="payments",
        summary="probe",
        mode="dry-run",
    )

    transport = DryRunTransport()
    out = io.StringIO()
    console = Console(file=out, no_color=True, width=200)
    console.input = lambda _p="": ""  # type: ignore[assignment]
    ok = await run_module(module, transport, dry_run=True, console=console)
    text = out.getvalue()

    assert ok is True, f"probe module did not complete; console was:\n{text}"
    assert "tecNO_PERMISSION" in text, (
        f"the noopt-issuer prerequisite did not produce the real "
        f"tecNO_PERMISSION lesson; console was:\n{text}"
    )
    assert "Expected failure" in text
