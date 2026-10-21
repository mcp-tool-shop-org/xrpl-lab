"""2.7.1 (#20 item 13): a ``mode: dry-run`` module runs offline whatever it's handed.

``xrpl-lab run`` ignored the frontmatter, so a learner running
dex_vs_amm_risk_literacy without ``--dry-run`` went to testnet (Book Keeper,
2.6.2 live sweep). The runner now swaps in the dry-run transport.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.modules import ModuleDef, ModuleStep, load_all_modules
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

seen: list[str] = []


async def _note_transport(step, state, transport, wallet_seed, ctx, console):
    seen.append(transport.network_name)
    return ctx


@pytest.fixture()
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import xrpl_lab.state as state_mod

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    try:
        resolve("test_271_note")
    except Exception:
        register(ActionDef(name="test_271_note", handler=_note_transport, description="test"))
    seen.clear()
    return tmp_path


def _module(dry_run_only: bool) -> ModuleDef:
    return ModuleDef(
        id="m271", title="m271", time="1 min", level="beginner", requires=[], produces=[],
        checks=[], raw_body="", dry_run_only=dry_run_only,
        mode="dry-run" if dry_run_only else "testnet",
        steps=[ModuleStep(text="## Step 1: x", action="test_271_note", action_args={})],
    )


@pytest.mark.asyncio
async def test_an_offline_module_never_reaches_the_network(_home: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    buf = io.StringIO()
    ok = await run_module(_module(True), XRPLTestnetTransport(), dry_run=False,
                          console=Console(file=buf, width=200))
    assert ok is True
    assert seen == ["dry-run"]
    assert "offline lesson (mode: dry-run)" in buf.getvalue()
    assert load_state().network == "dry-run"


@pytest.mark.asyncio
async def test_a_network_module_keeps_its_transport(_home: Path) -> None:
    from xrpl_lab.runner import run_module

    buf = io.StringIO()
    await run_module(_module(False), XRPLTestnetTransport(), dry_run=False,
                     console=Console(file=buf, width=200))
    assert seen == ["testnet"]
    assert "offline lesson" not in buf.getvalue()


def test_the_shipped_offline_module_is_marked() -> None:
    assert load_all_modules()["dex_vs_amm_risk_literacy"].dry_run_only is True
