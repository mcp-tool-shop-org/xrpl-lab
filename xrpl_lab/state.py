"""State and workspace management for XRPL Lab."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from . import __version__

# Defaults
DEFAULT_HOME_DIR = Path.home() / ".xrpl-lab"
DEFAULT_WORKSPACE_DIR = Path(".xrpl-lab")
DEFAULT_NETWORK = "testnet"


class CompletedModule(BaseModel):
    """Record of a completed module."""

    module_id: str
    completed_at: float
    txids: list[str] = Field(default_factory=list)
    report_path: str | None = None


class TxRecord(BaseModel):
    """A single transaction record."""

    txid: str
    module_id: str
    timestamp: float
    network: str
    success: bool
    explorer_url: str = ""


class LabState(BaseModel):
    """Persistent state stored in ~/.xrpl-lab/state.json by default.

    The home directory is overridable via the ``XRPL_LAB_HOME`` environment
    variable (not yet wired) or by patching :func:`get_home_dir` before use.
    """

    version: str = "1.2.0"
    network: str = DEFAULT_NETWORK
    wallet_path: str | None = None
    wallet_address: str | None = None
    completed_modules: list[CompletedModule] = Field(default_factory=list)
    tx_index: list[TxRecord] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def is_module_completed(self, module_id: str) -> bool:
        return any(m.module_id == module_id for m in self.completed_modules)

    def complete_module(
        self,
        module_id: str,
        txids: list[str] | None = None,
        report_path: str | None = None,
    ) -> None:
        if self.is_module_completed(module_id):
            return
        self.completed_modules.append(
            CompletedModule(
                module_id=module_id,
                completed_at=time.time(),
                txids=txids or [],
                report_path=report_path,
            )
        )
        self.updated_at = time.time()

    def record_tx(
        self,
        txid: str,
        module_id: str,
        network: str,
        success: bool,
        explorer_url: str = "",
    ) -> None:
        self.tx_index.append(
            TxRecord(
                txid=txid,
                module_id=module_id,
                timestamp=time.time(),
                network=network,
                success=success,
                explorer_url=explorer_url,
            )
        )
        self.updated_at = time.time()


def get_home_dir() -> Path:
    """Return the XRPL Lab home directory (~/.xrpl-lab/).

    Override with the ``XRPL_LAB_HOME`` environment variable.
    """
    env_home = os.environ.get('XRPL_LAB_HOME')
    if env_home:
        return Path(env_home)
    return DEFAULT_HOME_DIR


def get_workspace_dir() -> Path:
    """Return the per-project workspace directory (./.xrpl-lab/)."""
    return DEFAULT_WORKSPACE_DIR


def ensure_home_dir() -> Path:
    """Create home dir if it doesn't exist."""
    home = get_home_dir()
    home.mkdir(parents=True, exist_ok=True)
    return home


def ensure_workspace() -> Path:
    """Create workspace directories if they don't exist."""
    ws = get_workspace_dir()
    for sub in ("proofs", "reports", "logs"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    return ws


def state_path() -> Path:
    """Path to state.json."""
    return get_home_dir() / "state.json"


def load_state() -> LabState:
    """Load state from disk, or return fresh state."""
    p = state_path()
    if p.exists():
        try:
            data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
            # The state version tracks when the state was last saved.
            # Comparing against __version__ detects upgrades so the user
            # is warned that persisted fields may have changed shape.
            state_version = data.get("version", "unknown")
            if state_version != __version__:
                print(
                    f"Warning: state from v{state_version}, current is v{__version__}. "
                    "Some fields may differ.",
                    file=sys.stderr,
                )
            return LabState.model_validate(data)
        except (json.JSONDecodeError, ValueError, ValidationError):
            # Corrupted state — backup then start fresh
            bak = p.with_suffix('.json.bak')
            try:
                shutil.copy2(p, bak)
                print(
                    f"Warning: state file was corrupted, backup saved to {bak}",
                    file=sys.stderr,
                )
            except OSError as bak_err:
                print(
                    f"Warning: state file was corrupted and backup failed: {bak_err}",
                    file=sys.stderr,
                )
            return LabState()
    return LabState()


def save_state(state: LabState) -> None:
    """Persist state to disk."""
    state.updated_at = time.time()
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    except OSError as e:
        print(f"Warning: could not save state: {e}", file=sys.stderr)


def reset_state() -> None:
    """Delete state file and workspace."""
    p = state_path()
    if p.exists():
        p.unlink()

    ws = get_workspace_dir()
    if ws.exists():
        shutil.rmtree(ws)
