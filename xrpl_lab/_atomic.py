"""Atomic JSON write helper — TOCTOU-safe permission setting + optional rename.

Centralizes the create-with-mode + write + (optional) atomic-rename pattern
shared by ``xrpl_lab.actions.wallet.save_wallet`` and
``xrpl_lab.state.save_state``. Both call sites had near-identical
``os.open(..., O_WRONLY|O_CREAT|..., 0o600)`` + ``os.fdopen`` + JSON
serialization sequences; consolidating here keeps the wave-1 TOCTOU
discipline (no chmod-after-create race, no silent OSError swallow) in one
auditable place.

Two modes:

* ``atomic=False`` — write directly to ``path`` with ``O_TRUNC``. Used by
  the wallet seed file: a corrupt seed is recoverable from the user's
  mnemonic, so we accept the (vanishingly small) torn-write window in
  exchange for fewer moving parts.

* ``atomic=True`` — write to a sibling ``<path>.<pid>.<uuid8>.tmp`` with
  ``O_EXCL``, then ``os.replace`` it onto ``path``. Used by
  ``state.json``: holds incrementally-appended module progress + tx
  history with no external recovery source, so we guarantee the previous
  good copy survives process death mid-write.

  F-d6d7f5e8 (HIGH): the tmp name is unique PER CALL (process id + a short
  uuid4 suffix), not a fixed ``<path>.tmp`` literal. Two independent
  writers racing to save the same ``path`` now open two DIFFERENT tmp
  files, so ``O_EXCL`` can never raise ``FileExistsError`` between them —
  the only remaining race is the final ``os.replace()``, which is atomic
  at the filesystem level (benign last-writer-wins, no exception). This
  closes the crash for every ``save_state()`` call site at once (several
  had no try/except around it — a raw ``FileExistsError`` would otherwise
  propagate as an uncaught traceback) instead of requiring every caller to
  remember to wrap the call. The ``os.open`` of the tmp file itself now
  also lives INSIDE the try/except (previously it sat just outside), so
  ANY create-time failure (the freak uuid collision, a permission change,
  disk full) funnels through the same cleanup-and-reraise path as a
  write/replace failure, rather than propagating raw with no chance to
  clean up. Trade-off: because the name is unique per call, a stale tmp
  left by a process that crashed between ``os.open`` and ``os.replace``
  can no longer be recognized and pre-cleaned by name (a uuid4-suffixed
  name essentially never matches a later caller's freshly-generated name).
  Those orphans are inert — never collide, never block a future O_EXCL —
  pure disk-space litter, not a correctness or availability issue.

  The ``os.replace`` is wrapped in a bounded retry loop: on Windows a
  concurrent reader holding ``path`` open (the FastAPI dashboard reading
  state.json while the runner saves it) makes the rename raise transient
  ``PermissionError`` [WinError 5]; we retry with a short growing backoff
  so the rename lands once the reader's handle closes. POSIX is
  unaffected (rename-over-open succeeds first try). On final failure the
  orphan ``.tmp`` is unlinked and the original exception re-raises; we
  never silently swallow OSError on the WRITE path.

Both modes use ``os.open(..., file_mode)`` so the file is born with the
requested permissions — no chmod-after-create TOCTOU window. Both modes
also ``os.fsync()`` the file descriptor before closing (F-0c21577b,
MEDIUM): write-then-rename alone protects against process death (the old
file survives because the rename never happens) but NOT against a harder
crash (OS panic, power loss) — data can sit in the OS page cache after
``f.write()`` without being durably on disk. On the atomic path, the
containing directory is additionally fsynced (POSIX only) after a
successful ``os.replace()`` so the rename itself — not just the file's
bytes — is durable across a hard crash, not only a software-level
exception.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Windows-only transience window for ``os.replace`` over an open destination.
# On POSIX, rename-over-open succeeds first try (the destination's inode is
# simply unlinked while readers keep their handle), so the loop exits after
# attempt 0 and these constants never bite. On Windows a concurrent reader
# holding ``path`` open (e.g. the FastAPI dashboard ``read_text``-ing
# state.json while the runner saves it) makes ``os.replace`` raise
# ``PermissionError`` [WinError 5] — but only for the instant that handle is
# open. A short bounded retry with growing backoff lands in a clear window:
# the dashboard's per-iteration read handle closes between reads, so an
# attempt a few ms later succeeds. We cap attempts so a genuinely-stuck
# destination (a permanently-locked file) still fails loudly instead of
# hanging — the final exception re-raises with the orphan tmp cleaned up.
_REPLACE_MAX_ATTEMPTS = 5
_REPLACE_BACKOFF_BASE_S = 0.02  # 20ms, then 40, 60, 80 — ~200ms total worst case


def _fsync_dir(dir_path: Path) -> None:
    """Best-effort fsync of a directory fd (POSIX only; F-0c21577b).

    Makes a preceding ``os.replace()``'s directory-entry update durable
    across a hard crash or power loss, not just a process death. Called
    only after the rename already succeeded, so a failure here never
    means the write failed — the file is correctly in place either way —
    it only means the "even a kernel panic right now can't un-rename it"
    guarantee is weaker than intended. Not a correctness gate: failures
    are swallowed by design, mirroring this module's existing
    cleanup-of-cleanup discipline (the orphan-tmp unlink below).
    """
    try:
        dir_fd = os.open(str(dir_path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    file_mode: int = 0o600,
    atomic: bool = True,
    serialize: Callable[[Any], str] | None = None,
) -> None:
    """Write a JSON document to ``path`` with TOCTOU-safe permissions.

    Args:
        path: Final destination path.
        data: Object to serialize. By default rendered with
            ``json.dumps(data, indent=2)``. Pass ``serialize`` to override
            (e.g. Pydantic's ``model_dump_json(indent=2)``).
        file_mode: POSIX file mode passed to ``os.open`` at create time.
            Defaults to ``0o600`` (owner-only). On Windows the mode arg
            is largely a no-op for ACLs; the caller is responsible for
            warning the user about that limitation.
        atomic: When True (default), write to a unique
            ``<path>.<pid>.<uuid8>.tmp`` with ``O_EXCL`` then
            ``os.replace`` onto ``path`` so process death mid-write
            leaves the previous ``path`` intact. When False, write
            directly to ``path`` with ``O_TRUNC``.
        serialize: Optional callable that takes ``data`` and returns the
            JSON text to write. Defaults to ``json.dumps(data, indent=2)``.

    Raises:
        Any exception from the serializer, ``os.open``, the file write,
        or ``os.replace`` propagates to the caller. In ``atomic=True``
        mode a write failure unlinks the orphan ``.tmp`` before the
        original exception re-raises (cleanup-of-cleanup OSError is
        ignored by design — we are already in an exception path).
    """
    text = json.dumps(data, indent=2) if serialize is None else serialize(data)

    if not atomic:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(path, flags, file_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(fd)  # F-0c21577b: durable past the OS page cache
        return

    # F-d6d7f5e8: unique PER CALL — pid + a short uuid4 suffix — so two
    # independent writers can never collide on the same O_EXCL tmp path.
    # (See the module docstring for the full "why" and the accepted
    # trade-off: a stale tmp from a differently-named previous crash is no
    # longer auto-recognized/cleaned, but it's inert litter, not a hazard.)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    # Defensive belt-and-suspenders: if THIS exact (freak-collision-odds)
    # tmp name already exists, clear it so O_EXCL doesn't block us forever
    # — the leftover is, by definition, partial/unknown and not safe to
    # keep. Explicit try/except (not contextlib.suppress) — wave-1 wallet
    # TOCTOU bug came from broad silent suppression; keep cleanup paths
    # obvious so a future reader doesn't repeat that mistake.
    if tmp.exists():
        try:  # noqa: SIM105 — explicit per wave-1 discipline
            tmp.unlink()
        except OSError:
            pass
    try:
        # F-d6d7f5e8: os.open(tmp, ...) now lives INSIDE the try/except
        # (previously it sat just outside), so any create-time failure —
        # not just a write/replace failure — funnels through the same
        # cleanup-and-reraise path below.
        fd = os.open(tmp, flags, file_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(fd)  # F-0c21577b: durable past the OS page cache
        # Windows-aware atomic rename. os.replace over a destination a
        # concurrent reader holds open raises PermissionError [WinError 5]
        # on Windows; the lock is transient (clears the instant the reader's
        # handle closes), so retry a few times with growing backoff before
        # giving up. POSIX rename-over-open succeeds on attempt 0, so the
        # loop falls through immediately there. See module-level constants.
        for attempt in range(_REPLACE_MAX_ATTEMPTS):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == _REPLACE_MAX_ATTEMPTS - 1:
                    # Exhausted retries — re-raise so the outer except can
                    # clean up the orphan tmp and propagate to the caller.
                    raise
                # Growing backoff: 20ms, 40ms, 60ms, 80ms. Gives a
                # concurrent reader time to close its handle between reads.
                time.sleep(_REPLACE_BACKOFF_BASE_S * (attempt + 1))
        # F-0c21577b: fsync the directory entry too (POSIX only — Windows
        # has no equivalent directory-fd fsync via this API, and NTFS's
        # own metadata journaling covers this case in practice) so the
        # rename survives a hard crash, not just an application exception.
        if sys.platform != "win32":
            _fsync_dir(path.parent)
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
