"""Shared harness for driving a SHIPPED curriculum module end-to-end offline.

Not a test module (no ``test_`` prefix, so pytest does not collect it) — it is
the helper four module suites import.

Why this exists as a whole-module run rather than more unit tests: every defect
it was built to catch was invisible at the unit level. Each one lived in the
seam between two layers that agreed on a value's NAME and disagreed on its
VALUE — the dry-run transport writing a holder's state under the seed-collapsed
``_DRY_RUN_WALLET_ADDRESS`` while the handler read it back under the learner's
real ``state.wallet_address``. Both sides pass their own tests. Only running the
shipped markdown the way a learner runs it puts the two together.

The assertion these suites make on the captured console is deliberately blunt:
NO "✗" anywhere. A red ✗ on a module whose every step succeeded is the exact
learner-facing symptom ("the lesson failed") that this class of bug produces,
and it is the only signal that does not depend on knowing in advance which
check will break next.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.modules import parse_module
from xrpl_lab.transport.dry_run import DryRunTransport

MODULES_DIR = Path(__file__).parent.parent / "modules"


async def run_shipped_module(
    module_filename: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, DryRunTransport]:
    """Run ``modules/<module_filename>`` end-to-end offline through the runner.

    Isolates state to *tmp_path* so the run never touches the developer's real
    workspace, and starts from a blank :class:`LabState` so an earlier module's
    residue cannot make a broken module look healthy.

    Returns the captured console text and the transport, so a caller can assert
    on what the learner SAW as well as on the resulting ledger state.
    """
    import xrpl_lab.runner as runner_mod
    import xrpl_lab.state as state_mod
    from xrpl_lab.state import LabState

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr(runner_mod, "load_state", lambda: LabState())

    text = (MODULES_DIR / module_filename).read_text(encoding="utf-8")

    buf = io.StringIO()
    console = Console(file=buf, no_color=True, width=120)
    monkeypatch.setattr(console, "input", lambda _p="": "")

    transport = DryRunTransport()
    ok = await runner_mod.run_module(
        parse_module(text), transport, dry_run=True, console=console
    )
    assert ok is True, f"{module_filename} did not complete its run"
    return buf.getvalue(), transport


def assert_no_failed_checks(out: str, module_filename: str) -> None:
    """Assert the learner saw no red ✗ anywhere in the module's output."""
    failed = [ln.strip() for ln in out.splitlines() if "✗" in ln]
    assert not failed, (
        f"{module_filename} reported {len(failed)} failed check(s) in --dry-run "
        f"even though every step succeeded: {failed}"
    )
