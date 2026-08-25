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
of teaching the wrong lesson quietly. The coordinator has since landed the curriculum
half: modules/token_escrow_101.md
now calls create_noopt_issuer in its own step before the expect-fail step, so
the shipped module delivers the real tecNO_PERMISSION lesson. Both halves are
covered below — the working lesson, and the guard that still fires when the
prerequisite is absent.
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
async def test_shipped_module_teaches_real_tecno_permission(tmp_path, monkeypatch):
    """F-57c984e9, coordinator half: the SHIPPED modules/token_escrow_101.md now
    wires create_noopt_issuer before the expect-fail step, so an end-to-end
    dry-run must actually deliver the tecNO_PERMISSION lesson its own frontmatter
    `checks:` advertises — not a structured abort, and not a silent tecNO_LINE.
    """
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    save_state(LabState(network="dry-run", wallet_address=w.address))

    module = _load_token_escrow_module()
    transport = DryRunTransport()
    out = io.StringIO()
    console = Console(file=out, no_color=True, width=200)
    console.input = lambda _p="": ""  # type: ignore[assignment]

    ok = await run_module(module, transport, dry_run=True, console=console)
    text = out.getvalue()

    assert ok is True, (
        "the shipped token_escrow_101 module did not run to completion; the "
        f"create_noopt_issuer wiring should make the lesson reachable.\n{text}"
    )
    assert "tecNO_PERMISSION" in text, (
        "the shipped module completed but never produced the tecNO_PERMISSION "
        f"lesson it advertises in its checks: frontmatter.\n{text}"
    )
    assert "tecNO_LINE" not in text, (
        f"the wrong-lesson result code reached the learner's console.\n{text}"
    )


@pytest.mark.asyncio
async def test_missing_prerequisite_still_fails_loud(tmp_path, monkeypatch):
    """The guard must survive the module being fixed.

    Drives the SHIPPED module with its create_noopt_issuer step surgically
    removed. That is the exact condition the handler guards, so it must still
    halt with a named, actionable error rather than falling back to the MAIN
    (already opted-in) issuer and teaching tecNO_LINE quietly.
    """
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    save_state(LabState(network="dry-run", wallet_address=w.address))

    module = _load_token_escrow_module()
    kept = [s for s in module.steps if s.action != "create_noopt_issuer"]
    assert len(kept) == len(module.steps) - 1, (
        "expected exactly one create_noopt_issuer step in the shipped module; "
        "if this fires, the module wiring changed and this test needs revisiting"
    )
    module.steps = kept

    transport = DryRunTransport()
    out = io.StringIO()
    console = Console(file=out, no_color=True, width=200)
    console.input = lambda _p="": ""  # type: ignore[assignment]

    ok = await run_module(module, transport, dry_run=True, console=console)
    text = out.getvalue()

    assert ok is False, (
        "with create_noopt_issuer removed, run_module reported success — the "
        f"silent-fallback defect has regressed.\n{text}"
    )
    assert "create_noopt_issuer" in text, (
        f"the failure does not name the missing prerequisite.\n{text}"
    )
    assert "tecNO_LINE" not in text, (
        "the step must fail BEFORE submitting, so the wrong result code should "
        f"never reach the console.\n{text}"
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
