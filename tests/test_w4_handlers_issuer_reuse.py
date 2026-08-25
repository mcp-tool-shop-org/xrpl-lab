"""Wave-4 handlers AMEND — F-c49d009d (CRITICAL).

``handle_create_issuer_wallet`` always called ``create_wallet()`` and
overwrote ``.xrpl-lab/issuer_wallet.json`` with no existence check.
Resume / re-run of modules that create an issuer (e.g. trust_lines_101)
minted a NEW issuer, orphaned the old LAB trust line on the learner's
persistent wallet, and locked another owner-reserve increment.

Contract: if the issuer file exists, load and reuse. Two sequential
dry-run runs of ``trust_lines_101`` must not add a second issuer/trust
line. Do not edit modules/.

Run in isolation:
    python -m pytest tests/test_w4_handlers_issuer_reuse.py -q --tb=short
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers  # noqa: F401 — register actions
from xrpl_lab.actions import wallet as wallet_mod
from xrpl_lab.handlers import handle_create_issuer_wallet
from xrpl_lab.modules import ModuleStep, parse_module
from xrpl_lab.runner import run_module
from xrpl_lab.state import LabState, save_state
from xrpl_lab.transport.dry_run import DryRunTransport

MODULE_PATH = Path(__file__).parent.parent / "modules" / "trust_lines_101.md"


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda _p="": ""  # type: ignore[assignment]
    return console, buf


@pytest.mark.asyncio
async def test_create_issuer_wallet_reuses_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If issuer_wallet.json already exists, do not mint a second issuer."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    console, _ = _console()
    step = ModuleStep(text="", action="create_issuer_wallet", action_args={})
    state = LabState(network="dry-run")
    transport = DryRunTransport()

    ctx1 = await handle_create_issuer_wallet(
        step, state, transport, "", {}, console,
    )
    first_address = ctx1["issuer_address"]
    issuer_path = Path(".xrpl-lab") / "issuer_wallet.json"
    assert issuer_path.is_file()
    first_seed = json.loads(issuer_path.read_text(encoding="utf-8"))["seed"]

    ctx2 = await handle_create_issuer_wallet(
        step, state, transport, "", {}, console,
    )
    second_address = ctx2["issuer_address"]
    second_seed = json.loads(issuer_path.read_text(encoding="utf-8"))["seed"]

    assert second_address == first_address, (
        "re-running create_issuer_wallet minted a new issuer address; "
        f"first={first_address} second={second_address}"
    )
    assert second_seed == first_seed, (
        "re-running create_issuer_wallet overwrote issuer_wallet.json "
        "with a different seed"
    )


@pytest.mark.asyncio
async def test_two_trust_lines_101_runs_do_not_add_second_issuer_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empirically: two sequential dry-run trust_lines_101 runs must keep a
    single LAB trust line against one issuer on the learner wallet.
    """
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    save_state(LabState(network="dry-run", wallet_address=w.address))

    module = parse_module(MODULE_PATH.read_text(encoding="utf-8"))
    # One shared dry-run ledger so the second run sees the first run's line.
    transport = DryRunTransport()

    for i in range(2):
        out = io.StringIO()
        console = Console(file=out, no_color=True, width=200)
        console.input = lambda _p="": ""  # type: ignore[assignment]
        ok = await run_module(module, transport, dry_run=True, console=console)
        assert ok is True, (
            f"trust_lines_101 dry-run #{i + 1} failed:\n{out.getvalue()}"
        )

    issuer_path = Path(".xrpl-lab") / "issuer_wallet.json"
    assert issuer_path.is_file()
    issuer_address = json.loads(issuer_path.read_text(encoding="utf-8"))["address"]

    lines = await transport.get_trust_lines(w.address)
    lab_lines = [tl for tl in lines if tl.currency == "LAB"]
    peers = {tl.peer for tl in lab_lines}

    assert len(lab_lines) == 1, (
        "two sequential trust_lines_101 runs left multiple LAB trust lines "
        f"on the learner wallet (peers={peers}): the issuer was re-minted.\n"
        f"lines={[(tl.currency, tl.peer, tl.balance) for tl in lab_lines]}"
    )
    assert peers == {issuer_address}, (
        f"LAB trust line peer(s) {peers} != reused issuer {issuer_address}"
    )
