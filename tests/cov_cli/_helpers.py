"""Helpers shared by the CLI coverage tests (not a test module)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from click.testing import CliRunner

from xrpl_lab.cli import main
from xrpl_lab.modules import load_all_modules
from xrpl_lab.state import LabState, load_state, save_state


def invoke(args: list[str], input: str | None = None):
    """Run the CLI (click >= 8.2: ``.stdout`` / ``.stderr`` are separate)."""
    return CliRunner().invoke(main, args, input=input)


def all_module_ids() -> list[str]:
    return list(load_all_modules().keys())


def make_state(
    completed: list[str] | None = None,
    unverified: tuple[str, ...] = (),
    wallet: str | None = "rLEARNER123",
    tx: list[tuple[str, str, bool]] | None = None,
) -> LabState:
    """Build + save a state. ``tx`` is [(txid, module_id, success)]."""
    state = LabState()
    state.network = "testnet"
    state.wallet_address = wallet
    for mid in completed or []:
        state.complete_module(
            mid, txids=[f"TX_{mid}"], verified=mid not in unverified,
        )
    for txid, mid, ok in tx or []:
        state.record_tx(txid, mid, "testnet", ok)
    save_state(state)
    return load_state()


def seal(obj: dict, key: str = "sha256") -> dict:
    """Seal ``obj`` with the same hash recipe the generators use."""
    body = {k: v for k, v in obj.items() if k != key}
    content = json.dumps(body, sort_keys=True, separators=(",", ":"))
    obj[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return obj


def write_json(path: Path, obj: object) -> Path:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def fake_run_module(calls: list, *, ok: bool = True, verified: bool = True):
    """An async stand-in for runner.run_module that records state like the real one."""

    async def _fake(module, transport, dry_run=False, force=False, **kwargs):
        calls.append({
            "module": module.id, "transport": transport,
            "dry_run": dry_run, "force": force,
        })
        if ok:
            state = load_state()
            state.complete_module(module.id, txids=["T1"], verified=verified)
            save_state(state)
        return ok

    return _fake
