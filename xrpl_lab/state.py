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

# DD-1: per-dir threat-model classification.
# Home dir holds wallet seed + state — single-user private. The workspace
# subdirs (proofs/, reports/, audit_packs/, logs/) are workshop-shareable
# (facilitator handoff at session end; threat model says no secrets in
# workspace). Mirrors the wave-1 wallet upgrade-tighten pattern: mkdir(mode=)
# on new install + post-mkdir os.chmod for existing 0o755 dirs from earlier
# versions. chmod failures propagate per wave-1 discipline.
HOME_DIR_MODE = 0o700
WORKSPACE_DIR_MODE = 0o755


def _ensure_dir_mode(path: Path, mode: int) -> None:
    """Create ``path`` at ``mode`` (POSIX) and tighten/loosen if it already exists.

    ``Path.mkdir(mode=...)`` only honors ``mode`` on creation, so directories
    left over from earlier xrpl-lab versions stay at their original (often
    0o755) mode. The post-mkdir chmod fixes those existing installs.

    chmod failures propagate intentionally — wave-1 discipline. The user
    must know when their dir is in a state we cannot secure. Windows uses
    ACLs rather than POSIX modes so the chmod step is skipped there.
    """
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    if sys.platform != "win32":
        current = path.stat().st_mode & 0o777
        if current != mode:
            os.chmod(path, mode)


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

    version: str = "1.5.0"
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
    """Create home dir if it doesn't exist (DD-1: 0o700 single-user private)."""
    home = get_home_dir()
    _ensure_dir_mode(home, HOME_DIR_MODE)
    return home


def ensure_workspace() -> Path:
    """Create workspace directories if they don't exist (DD-1: 0o755 workshop-shareable).

    The workspace + its subdirs (proofs/, reports/, logs/, audit_packs/)
    are facilitator-shareable at session end and contain no secrets per
    the threat model. They get 0o755 (owner-write, group/world-read).
    """
    ws = get_workspace_dir()
    _ensure_dir_mode(ws, WORKSPACE_DIR_MODE)
    for sub in ("proofs", "reports", "logs", "audit_packs"):
        _ensure_dir_mode(ws / sub, WORKSPACE_DIR_MODE)
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
            # Corrupted state — back up to a versioned name so we never clobber
            # a previous last-good .bak with the corrupt current. The atomic
            # write path in save_state means an existing state.json.bak from
            # any earlier run is the most recent intact snapshot we have, and
            # corrupt-recovery should preserve, not overwrite, that file.
            ts = int(time.time())
            bak = p.with_suffix(f'.json.corrupted.{ts}')
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
    """Persist state to disk via atomic write-then-rename.

    Writes to ``state.json.tmp`` first, then ``os.replace``s it onto
    ``state.json``. Process death mid-write leaves the previous
    ``state.json`` intact (the orphan ``.tmp`` is harmless and gets
    overwritten on the next save via O_EXCL retry-after-cleanup).

    Same TOCTOU class as the wallet seed file (F-BACKEND-NEW-001):
    the wallet uses O_TRUNC because a corrupt seed is recoverable from
    the user's mnemonic; state.json holds incrementally-appended module
    progress + tx history that has no external recovery source, so we
    use temp+rename to guarantee the previous good copy survives.

    The orphan ``.tmp`` cleanup unlink propagates a re-raise of the
    original write exception per wave-1 discipline — no
    contextlib.suppress, no silent OSError swallow.
    """
    state.updated_at = time.time()
    p = state_path()
    # DD-1: state.json lives in ~/.xrpl-lab/ alongside wallet.json
    # (single-user private). 0o700 to match the wave-1 wallet upgrade.
    _ensure_dir_mode(p.parent, HOME_DIR_MODE)
    tmp = p.with_suffix(p.suffix + '.tmp')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    # If a stale .tmp survived a previous crashed save, O_EXCL would
    # block us forever. Clear it so the current save can proceed; the
    # stale data is, by definition, partial/unknown and not safe to keep.
    # Explicit try/except (not contextlib.suppress) — wave-1 wallet TOCTOU
    # bug came from broad silent suppression; keep cleanup paths obvious
    # so a future reader doesn't repeat that mistake.
    if tmp.exists():
        try:  # noqa: SIM105 — explicit per wave-1 discipline
            tmp.unlink()
        except OSError:
            pass
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(state.model_dump_json(indent=2))
        os.replace(tmp, p)
    except Exception:
        # Cleanup orphan tmp on failure, then re-raise. Wave-1 antipattern
        # was silently swallowing OSError on the WRITE — that's distinct
        # from the cleanup-of-cleanup OSError here, which we ignore by
        # design (we're already in an exception path).
        if tmp.exists():
            try:  # noqa: SIM105 — explicit per wave-1 discipline
                tmp.unlink()
            except OSError:
                pass
        raise


def reset_state() -> None:
    """Delete state file and workspace."""
    p = state_path()
    if p.exists():
        p.unlink()

    ws = get_workspace_dir()
    if ws.exists():
        shutil.rmtree(ws)
