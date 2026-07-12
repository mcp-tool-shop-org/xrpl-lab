"""State and workspace management for XRPL Lab."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from . import __version__
from ._atomic import atomic_write_json
from .errors import LabException, state_locked

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


# ── Cross-process advisory lock (F-5312c8ba, CRITICAL) ───────────────────
#
# Guards save_state()'s read-merge-write critical section so two processes
# (a second `xrpl-lab` invocation in another terminal, or the FastAPI
# `serve` dashboard driving two concurrent run_module() calls in-process)
# can never both compute a merge against the same "before" snapshot and
# then both write, each blind to the other's write.
#
# The lock is held only for the duration of ONE save_state() call — read
# the current on-disk file, fold in a couple of short lists, atomic-write
# — a few milliseconds. It is never held across run_module()'s full
# interactive lifetime (which can span minutes of a learner reading module
# text and pressing Enter between steps): doing that would starve every
# OTHER concurrent save — including totally unrelated ones — for the
# whole module run. Locking only the actual read-merge-write is both
# sufficient (see _merge_append_only's docstring for why) and fast
# (uncontended in the overwhelmingly common single-process case, which is
# why tests never see meaningful lock latency).
#
# A dedicated sidecar ``state.json.lock`` file is locked — never
# ``state.json`` itself, since ``atomic_write_json``'s tmp+``os.replace``
# dance replaces state.json's underlying file on every save, and tying an
# OS lock to a file that's about to be swapped out from under it is not
# portable. The sidecar's identity never changes across saves.
_LOCK_TIMEOUT_S = 5.0
_LOCK_POLL_INTERVAL_S = 0.05


def _lock_path_for(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def _state_lock(path: Path):
    """Hold an advisory cross-process lock guarding ``path``'s save cycle.

    Bounded wait (``_LOCK_TIMEOUT_S``) with a short poll interval; raises
    ``LabException(state_locked())`` on exhaustion rather than hanging
    forever or silently proceeding unlocked — "never a silent clobber" is
    the whole point of this fix. Uncontended acquisition (the common
    single-process/tests case) succeeds on the very first non-blocking
    attempt with no sleep at all.

    Always released in a ``finally``, so an exception raised by the
    caller's critical section (e.g. a write failure) can never wedge a
    future save behind a lock nobody will ever release.
    """
    lock_path = _lock_path_for(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        # msvcrt.locking needs at least 1 real byte in the region it locks;
        # a brand-new lock file is 0 bytes. Harmless on POSIX too (flock
        # locks the whole file regardless of size), so do it unconditionally
        # rather than branch on platform.
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
            os.fsync(fd)
        # CRITICAL: seek to a FIXED position (0) before every lock attempt,
        # unconditionally. os.write() above left the fd's position at 1 for
        # whichever process happened to be the ONE THAT CREATED the file;
        # every other process's fd opens at position 0 and never writes
        # (size is already nonzero). Without this explicit seek, the
        # creator locks byte range [1, 2) while everyone else locks [0, 1)
        # — DIFFERENT ranges that never conflict, silently defeating the
        # whole point of this lock. Pinning the position to 0 here means
        # every acquirer always contends for the exact same byte.
        os.lseek(fd, 0, os.SEEK_SET)

        deadline = time.monotonic() + _LOCK_TIMEOUT_S
        acquired = _try_lock(fd)
        while not acquired and time.monotonic() < deadline:
            time.sleep(_LOCK_POLL_INTERVAL_S)
            acquired = _try_lock(fd)
        if not acquired:
            raise LabException(state_locked())
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def _load_state_for_merge(path: Path) -> LabState | None:
    """Best-effort quiet read of the on-disk state for save-time merging.

    Returns ``None`` when the file is absent, corrupt, or unreadable — the
    save then proceeds with just the in-memory state, identical to
    pre-fix behavior when there is nothing to merge against. This is an
    internal input to ``save_state()``'s merge step, not a user-facing
    load: unlike ``load_state()`` it never prints the version-mismatch
    warning and never writes a corrupt-backup — ``load_state()`` already
    owns surfacing those to the user on the READ path, and doing it again
    here (on every SAVE) would double-print / double-backup for no benefit.
    """
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return LabState.model_validate(_migrate(data))
    except (OSError, json.JSONDecodeError, ValidationError):
        return None


def _merge_append_only(target: LabState, on_disk: LabState) -> None:
    """Fold on-disk completed_modules/tx_index into ``target`` in place.

    F-5312c8ba: two processes (or two dashboard sessions each driving a
    separate run_module() call) can each hold an in-memory LabState loaded
    at a different time. Without this, whichever calls save_state() LAST
    silently overwrites the file with only ITS view — discarding the
    other's completed_modules/tx_index entries even though the underlying
    transaction genuinely landed on-ledger. Called with the state lock
    held, immediately before serializing, so ``on_disk`` is the freshest
    possible snapshot.

    Merge rule: union by identity key. An id/key already known to
    ``target`` is left as-is (this process's own view of work it already
    knows about is authoritative for that id) — only DISK-ONLY entries are
    folded in. This is deliberately additive-only: it has no way to tell
    "another process added this after my load" apart from "*I* am
    intentionally removing this and haven't persisted that yet", so it
    must never run for a save that performs a removal (see
    ``save_state``'s ``merge`` parameter — ``reset_module`` opts out).

    The merged lists are re-sorted chronologically afterward so ordinal
    assumptions elsewhere in the codebase (doctor._check_last_error's
    ``failed[-1]`` meaning "most recent failure") keep meaning what they
    say once a merge has interleaved arrival order.
    """
    known_module_ids = {m.module_id for m in target.completed_modules}
    for m in on_disk.completed_modules:
        if m.module_id not in known_module_ids:
            target.completed_modules.append(m)
            known_module_ids.add(m.module_id)
    target.completed_modules.sort(key=lambda m: m.completed_at)

    known_tx_keys = {(t.txid, t.module_id, t.timestamp) for t in target.tx_index}
    for t in on_disk.tx_index:
        key = (t.txid, t.module_id, t.timestamp)
        if key not in known_tx_keys:
            target.tx_index.append(t)
            known_tx_keys.add(key)
    target.tx_index.sort(key=lambda t: t.timestamp)

    # Preserve the earliest known creation time across both copies.
    target.created_at = min(target.created_at, on_disk.created_at)


class CompletedModule(BaseModel):
    """Record of a completed module.

    ``verified`` (RESWARM3): True iff every on-ledger verification the module
    ran passed. Defaults True for back-compat — an OLD state.json (or a module
    with no verify steps) loads as verified. A module whose verify step FAILED
    on-ledger records ``verified=False`` so the proof pack is honest: the run
    still "completed" (it did not crash), but the artifact does not claim a
    verification that never passed. See the runner's ``all_verified`` tracking
    and reporting.generate_proof_pack's top-level ``all_verified`` fold.
    """

    module_id: str
    completed_at: float
    txids: list[str] = Field(default_factory=list)
    report_path: str | None = None
    verified: bool = True


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
    variable (honored by :func:`get_home_dir`) or by patching
    :func:`get_home_dir` before use.
    """

    version: str = __version__
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
        verified: bool = True,
    ) -> None:
        if self.is_module_completed(module_id):
            return
        self.completed_modules.append(
            CompletedModule(
                module_id=module_id,
                completed_at=time.time(),
                txids=txids or [],
                report_path=report_path,
                verified=verified,
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


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a raw state dict to the current schema BEFORE ``model_validate``.

    PB-004 (RESWARM3): this establishes the migration seam. Today it is
    largely an identity function — the ``verified`` field added to
    ``CompletedModule`` is *additive*, so Pydantic's field default already
    fills it for an older state.json that lacks it, and no active rewrite is
    required. The seam exists so that ANY future field/shape change upgrades
    an older state.json IN PLACE here, instead of failing ``model_validate``
    and tripping ``load_state``'s corrupt-recovery path — which would back up
    the file and start the learner from a FRESH state, silently discarding
    their whole module history.

    Keyed on ``data.get("version")`` so version-specific migrations can be
    added as ``if`` branches without disturbing the identity path. Never
    mutates the caller's dict (works on the value it is handed; callers pass a
    dict they own). Unknown/absent versions fall through unchanged — the
    additive-default rule keeps them loadable.
    """
    if not isinstance(data, dict):
        # Defensive: a non-dict payload isn't migratable — hand it back so the
        # downstream model_validate raises the precise, honest error.
        return data
    # version = data.get("version")  # reserved for future keyed migrations.
    # No structural rewrite needed for the current (v2.2.0) additive change:
    # CompletedModule.verified defaults True, so a pre-verified-field entry
    # validates and fills verified=True automatically. Future non-additive
    # migrations branch here on version.
    return data


def load_state_from_path(path: Path) -> LabState:
    """Load state from an explicit path (read-only).

    Used by cohort-status / session-export to read a learner's
    state.json directly from a known location without going through
    XRPL_LAB_HOME / get_home_dir(). No corruption-backup side-effect:
    callers want a clean ``ValueError`` on malformed JSON so they
    can surface a per-learner warning row and continue.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the file is not valid JSON or fails schema.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    raw = path.read_text(encoding="utf-8")
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    try:
        return LabState.model_validate(_migrate(data))
    except ValidationError as e:
        raise ValueError(f"Schema mismatch in {path}: {e}") from e


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
            # PB-004: run the migration seam BEFORE model_validate so an older
            # state.json upgrades in place rather than tripping the
            # corrupt-recovery path below (which would reset the learner's
            # history). The current change is additive (verified defaults
            # True), so this is an identity step today — the seam is what
            # makes future non-additive changes safe.
            return LabState.model_validate(_migrate(data))
        except (json.JSONDecodeError, ValueError, ValidationError, OSError) as exc:
            # Unreadable / corrupted state — recover to a fresh LabState so a
            # single bad (or locked-down) state.json never crashes the CLI.
            #
            # CORE-A-003: read_text() can raise OSError/PermissionError on a
            # shared/locked-down machine. Catching it here (alongside the
            # parse/validation errors) keeps a raw traceback — which prints
            # the absolute state.json path + OS username — from escaping.
            #
            # The user-facing warning surfaces only the exception TYPE name,
            # never str(exc) (which carries the absolute path on OSError) and
            # never the backup path. This mirrors runner.py's recovery-save
            # discipline: type name to the user, full detail to logs only.
            ts = int(time.time())
            bak = p.with_suffix(f'.json.corrupted.{ts}')
            try:
                shutil.copy2(p, bak)
                print(
                    "Warning: state file could not be read "
                    f"({type(exc).__name__}); a backup was saved and a fresh "
                    "state was started. Run 'xrpl-lab doctor' to diagnose.",
                    file=sys.stderr,
                )
            except OSError as bak_err:
                print(
                    "Warning: state file could not be read "
                    f"({type(exc).__name__}) and the backup also failed "
                    f"({type(bak_err).__name__}); a fresh state was started.",
                    file=sys.stderr,
                )
            return LabState()
    return LabState()


def save_state(state: LabState, *, merge: bool = True) -> None:
    """Persist state to disk via a locked read-merge-write, then atomic
    write-then-rename.

    Writes to a unique temp file first, then ``os.replace``s it onto
    ``state.json``. Process death mid-write leaves the previous
    ``state.json`` intact (the orphan tmp is harmless litter — see
    ``_atomic``'s module docstring for the F-d6d7f5e8 unique-naming fix).

    Same TOCTOU class as the wallet seed file (F-BACKEND-NEW-001):
    the wallet uses O_TRUNC because a corrupt seed is recoverable from
    the user's mnemonic; state.json holds incrementally-appended module
    progress + tx history that has no external recovery source, so we
    use temp+rename to guarantee the previous good copy survives.

    The actual atomic-write mechanics live in ``_atomic.atomic_write_json``
    (shared with the wallet seed file's save_wallet). This module retains
    the dir-mode policy (DD-1, 0o700 for the home dir holding state.json
    alongside wallet.json) and the Pydantic-aware serializer
    (``state.model_dump_json(indent=2)``).

    The orphan tmp cleanup unlink propagates a re-raise of the
    original write exception per wave-1 discipline — no
    contextlib.suppress, no silent OSError swallow.

    F-5312c8ba (CRITICAL — lost-update race): before this fix, save_state()
    was a blind read-modify(in-memory)-write with NO protection across
    processes — two ``xrpl-lab`` invocations (or the FastAPI ``serve``
    dashboard driving two concurrent run_module() calls in-process) racing
    against the same state.json meant whichever saved LAST silently
    clobbered the other's completed_modules/tx_index, discarding real
    on-ledger history with no error raised. Fixed via:

    1. A sidecar advisory OS lock (Windows ``msvcrt.locking`` / POSIX
       ``fcntl.flock``, see ``_state_lock``) held for the duration of THIS
       function only — never across run_module()'s full interactive
       lifetime.
    2. Inside the lock, a fresh read of whatever is CURRENTLY on disk,
       merged into a copy of ``state`` (union by id/key; disk-only entries
       folded in; re-sorted chronologically) before serializing — see
       ``_merge_append_only``. The caller's own ``state`` object is never
       mutated by the merge (only a deep copy is), so a failed save leaves
       the caller's in-memory object exactly as they left it.

    A single-process save (tests, the common case) pays only the cost of
    one uncontended non-blocking lock attempt plus one small extra JSON
    read — no measurable slowdown.

    Args:
        state: the in-memory LabState to persist. Untouched by the merge
            step (a deep copy is what actually gets merged + written);
            ``updated_at``/``version`` ARE stamped directly onto it, same
            as pre-fix behavior.
        merge: when True (default), fold in any completed_modules/tx_index
            entries present on disk but absent from ``state`` before
            writing. Pass ``merge=False`` for a save that performs an
            INTENTIONAL REMOVAL — currently only ``reset_module``'s own
            save. Merging would silently resurrect the very entries the
            caller just removed: a fresh on-disk read at save time cannot
            tell "another process added this after my load" apart from "I
            am removing this and haven't persisted it yet". A
            ``merge=False`` save still takes the same lock (so it can't
            torn-write against a concurrent saver), it just skips the
            fold-in step and writes ``state`` as-is — the same
            last-writer-wins semantics this function had before the fix,
            scoped to the one call site that needs them.

    F-678304a1 (MEDIUM): stamps ``state.version = __version__`` so the
    "state from vX" warning in ``load_state()`` fires exactly once per
    install upgrade instead of on every single command for the lifetime of
    a state.json (nothing previously ever refreshed the persisted field).
    """
    state.updated_at = time.time()
    state.version = __version__
    p = state_path()
    # DD-1: state.json lives in ~/.xrpl-lab/ alongside wallet.json
    # (single-user private). 0o700 to match the wave-1 wallet upgrade.
    _ensure_dir_mode(p.parent, HOME_DIR_MODE)
    with _state_lock(p):
        to_write = state
        if merge:
            on_disk = _load_state_for_merge(p)
            if on_disk is not None:
                to_write = state.model_copy(deep=True)
                _merge_append_only(to_write, on_disk)
        atomic_write_json(
            p,
            to_write,
            file_mode=0o600,
            atomic=True,
            serialize=lambda s: s.model_dump_json(indent=2),
        )


def reset_state() -> None:
    """Delete state file and workspace.

    F-5312c8ba: the state.json unlink is guarded by the same advisory
    lock save_state() uses, so a full reset can't land mid-way through a
    concurrent save's read-merge-write. The lock sidecar file itself is
    removed AFTER the lock is released — never while held, since deleting
    a file out from under its own open lock handle is not portable on
    Windows.
    """
    p = state_path()
    with _state_lock(p):
        if p.exists():
            p.unlink()

    lock_p = _lock_path_for(p)
    if lock_p.exists():
        with contextlib.suppress(OSError):
            lock_p.unlink()

    ws = get_workspace_dir()
    if ws.exists():
        shutil.rmtree(ws)


def reset_module(module_id: str) -> dict:
    """Granularly reset a single module — preserves wallet + other modules.

    F-BACKEND-FT-003 (HIGH-equivalent per advisor): a stuck learner
    retries one module without losing the rest. The humane fix the
    wave-1 Stage C recovery messaging exposed but didn't address.

    Removes:
        - module_id from completed_modules
        - tx_index entries tagged with module_id (otherwise the retry
          accumulates duplicate tx history that would confuse audits)
        - reports/<module_id>.md (the module's report file)

    Preserves:
        - wallet (file + state.wallet_address + state.wallet_path)
        - all other completed_modules + their tx_index records
        - doctor.log + audit_packs/* (audit packs are session-keyed,
          not module-keyed — leaving them is the correct behavior)
        - workspace dir + structure (only the matching report is
          removed; sibling files stay)

    Returns a summary dict for the CLI:
        {"removed_from_completed": bool, "tx_records_cleared": int,
         "report_removed": bool}

    Raises:
        ValueError: if module_id is not currently in completed_modules.
    """
    state = load_state()
    if not state.is_module_completed(module_id):
        raise ValueError(
            f"Module '{module_id}' is not in completed_modules — "
            "nothing to reset for that ID."
        )

    # Filter out target module from completed list
    state.completed_modules = [
        m for m in state.completed_modules if m.module_id != module_id
    ]

    # Filter tx_index — keep records from other modules
    before_tx = len(state.tx_index)
    state.tx_index = [tx for tx in state.tx_index if tx.module_id != module_id]
    cleared_tx = before_tx - len(state.tx_index)

    state.updated_at = time.time()
    # F-5312c8ba: merge=False — this save performs an INTENTIONAL removal.
    # save_state()'s default merge would re-read the on-disk copy (which
    # still has module_id in it — that's exactly what we're removing) and
    # fold it back in, silently undoing the reset. See save_state's
    # docstring for the full reasoning.
    save_state(state, merge=False)

    # Clean the module's report from workspace (best-effort; absence is fine)
    ws = get_workspace_dir()
    report_path = ws / "reports" / f"{module_id}.md"
    report_removed = False
    if report_path.exists():
        try:
            report_path.unlink()
            report_removed = True
        except OSError:
            # Workspace cleanup failure is not fatal — the state side
            # of the reset already landed atomically. Surface to the
            # caller via the return value, not an exception.
            report_removed = False

    return {
        "removed_from_completed": True,
        "tx_records_cleared": cleared_tx,
        "report_removed": report_removed,
    }
