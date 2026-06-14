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

* ``atomic=True`` — write to a sibling ``<path>.tmp`` with ``O_EXCL``,
  then ``os.replace`` it onto ``path``. Used by ``state.json``: holds
  incrementally-appended module progress + tx history with no external
  recovery source, so we guarantee the previous good copy survives
  process death mid-write. Stale ``.tmp`` files from a previously-killed
  process are pre-cleaned (otherwise O_EXCL would block forever). The
  ``os.replace`` is wrapped in a bounded retry loop: on Windows a
  concurrent reader holding ``path`` open (the FastAPI dashboard reading
  state.json while the runner saves it) makes the rename raise transient
  ``PermissionError`` [WinError 5]; we retry with a short growing backoff
  so the rename lands once the reader's handle closes. POSIX is
  unaffected (rename-over-open succeeds first try). On final failure the
  orphan ``.tmp`` is unlinked and the original exception re-raises; we
  never silently swallow OSError on the WRITE path.

Both modes use ``os.open(..., file_mode)`` so the file is born with the
requested permissions — no chmod-after-create TOCTOU window.
"""

from __future__ import annotations

import json
import os
import time
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
        atomic: When True (default), write to ``<path>.tmp`` with
            ``O_EXCL`` then ``os.replace`` onto ``path`` so process death
            mid-write leaves the previous ``path`` intact. When False,
            write directly to ``path`` with ``O_TRUNC``.
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
        return

    tmp = path.with_suffix(path.suffix + ".tmp")
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
    fd = os.open(tmp, flags, file_mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
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
