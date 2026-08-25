"""WebSocket endpoint for running modules with live output streaming."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..modules import load_all_modules
from ..reporting import sanitize_endpoint
from ..runner import run_module
from .schemas import RunStartResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# In-memory store of active and recently completed run sessions
_sessions: dict[str, ModuleRunSession] = {}

# Strong references to fire-and-forget background tasks (currently the
# session-cleanup tasks scheduled by _schedule_session_cleanup). asyncio
# holds only a WEAK reference to a task created via create_task(); if the
# only other reference is a local that falls out of scope, the task can be
# garbage-collected mid-flight and the cleanup never runs (documented
# asyncio footgun — see the create_task() note in the stdlib docs). We
# retain each task here and discard it via add_done_callback so the set
# doesn't grow unbounded.
_background_tasks: set[asyncio.Task] = set()

# Run IDs with a grace-period cleanup task currently scheduled. A run with a
# connected WS client double-schedules cleanup: ``cancel_session`` schedules
# it (facilitator DELETE), and the WS read-loop's ``finally`` schedules it
# again on close — two tasks + two 60s timers racing the same idempotent pop.
# This set lets ``_schedule_session_cleanup`` early-return when a cleanup is
# already pending for a run_id, so exactly ONE timer runs per run_id. The
# marker is discarded when the cleanup task finishes, so a session that is
# (rarely) re-created under the same run_id can be cleaned up again.
_pending_cleanups: set[str] = set()

# Max sessions cap — evict oldest completed when exceeded
_MAX_SESSIONS = 100

# Concurrency policy: up to _MAX_CONCURRENT_RUNS module runs may execute
# simultaneously. Each run has its own Console, context, and event sink.
# No global mutable state is shared between runs.
_MAX_CONCURRENT_RUNS = 3

# Grace period (seconds) before cleaning up a disconnected session
_CLEANUP_GRACE_SECONDS = 60

# Timeout (seconds) for a single module run
_RUN_TIMEOUT_SECONDS = 300

# Bounded queue size — caps memory if the WS consumer stalls or is slow.
# On overflow we drop the OLDEST item (drop-oldest policy): the dashboard
# values freshness over completeness.
_QUEUE_MAXSIZE = 1024

# Allowed Origin values for the WS handshake. WebSocket upgrades are NOT
# covered by browser CORS, so we must reject by Origin manually to close
# the CSRF-via-WebSocket vector. This tuple is the single source of truth
# for both the WS Origin allow-list (here) and the HTTP CORS middleware
# allow-list — ``xrpl_lab/server.py`` imports this constant and feeds it
# into ``CORSMiddleware(allow_origins=...)``. Edit the set in one place.
# Tuple (immutable) signals constant; consumers wrap in ``list(...)``
# when an API requires a list (FastAPI's CORSMiddleware does).
_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:4321",
    "http://localhost:3000",
    "http://127.0.0.1:4321",
    "http://127.0.0.1:3000",
)


def _safe_put(queue: asyncio.Queue, item: dict, run_id: str = "") -> None:
    """Put `item` on `queue`, dropping the oldest entry on overflow.

    The queue is bounded (see _QUEUE_MAXSIZE). When full, we drain one
    oldest item and retry — the WS dashboard consumer values freshness
    over completeness. Logs a WARNING when the policy fires.
    """
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        logger.warning(
            "queue overflow: dropped oldest, run_id=%s qsize=%d",
            run_id,
            queue.qsize(),
        )
        # Retry; if still full (unlikely — we just drained), drop the new item.
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning(
                "queue overflow: dropped new item, run_id=%s qsize=%d",
                run_id,
                queue.qsize(),
            )


def _severity_for_code(code: str) -> tuple[str, str]:
    """Map a LabError code → (severity, icon_hint).

    Severity drives the dashboard's visual treatment (color, urgency)
    so the Frontend's ws.onclose / message handler doesn't have to
    code-introspect the prefix taxonomy itself. Mapping aligns with
    xrpl_lab.errors._EXIT_CODES — INPUT_/CONFIG_/STATE_ are user-error
    (warning, recoverable); IO_/DEP_/RUNTIME_/PERM_ are runtime fault
    (error, server-side); PARTIAL_ is success-with-degradation (info).

    The taxonomy match is by prefix, not full code — so a future
    RUNTIME_FOOBAR added without updating this map renders as
    'error/alert-triangle' rather than leaking an unmapped value.
    """
    # Specific code overrides (more specific than the prefix mapping)
    if code == "RUNTIME_TIMEOUT":
        return ("warning", "clock")
    if code == "RUNTIME_CANCELLED":
        return ("info", "x-circle")
    if code == "RUNTIME_FAUCET_RATE_LIMITED":
        # Rate-limit is recoverable (retry after wait or use --dry-run);
        # render as warning/clock — same family as RUNTIME_TIMEOUT — so
        # the dashboard distinguishes it from generic RUNTIME_* runtime
        # faults (error/alert-triangle).
        return ("warning", "clock")

    # Prefix-based mapping
    if code.startswith("INPUT_") or code.startswith("CONFIG_") or code.startswith("STATE_"):
        return ("warning", "alert-circle")
    if code.startswith("PARTIAL_"):
        return ("info", "info")
    if (
        code.startswith("RUNTIME_")
        or code.startswith("IO_")
        or code.startswith("DEP_")
        or code.startswith("PERM_")
    ):
        return ("error", "alert-triangle")

    # Default fallback — unknown code prefix
    return ("error", "alert-triangle")


def _error_envelope(exc: BaseException) -> dict[str, str]:
    """Map an exception to a structured user-facing error envelope.

    Never leaks raw paths/internals — the server-side log captures the
    full str(exc); the client only sees code/message/hint plus the
    optional severity/icon_hint metadata. Codes align with
    xrpl_lab.errors.LabError taxonomy (RUNTIME_*, IO_*, etc.).

    Envelope shape (all string-valued):
        {code, message, hint, severity, icon_hint}

    severity is one of 'info' | 'warning' | 'error' | 'critical' and
    icon_hint is a generic glyph name (e.g. 'clock', 'alert-triangle')
    chosen to give the Frontend a hint without locking the dashboard
    into a specific icon library. Both are derived from ``code`` via
    ``_severity_for_code`` — they are additive metadata; existing
    consumers reading only {code, message, hint} continue to work.
    """
    from ..errors import LabException

    if isinstance(exc, LabException):
        # Already structured — reuse the existing envelope.
        d = exc.error.safe_dict()
        code = str(d.get("code", "RUNTIME_INTERNAL"))
        severity, icon_hint = _severity_for_code(code)
        return {
            "code": code,
            "message": str(d.get("message", "An error occurred")),
            "hint": str(d.get("hint", "")),
            "severity": severity,
            "icon_hint": icon_hint,
        }
    if isinstance(exc, TimeoutError):
        code = "RUNTIME_TIMEOUT"
        severity, icon_hint = _severity_for_code(code)
        return {
            "code": code,
            "message": (
                "The module run timed out — the XRPL testnet did not "
                "respond within the run window. This usually means the "
                "testnet is congested or your network is slow, not a "
                "bug in your module logic."
            ),
            "hint": (
                "Retry the run — testnet load varies and a second attempt "
                "often succeeds. If it keeps timing out, restart in "
                "offline mode: from the CLI run "
                "`xrpl-lab run <module> --dry-run`, or from the dashboard "
                "select 'Dry Run' on the module page before clicking Start."
            ),
            "severity": severity,
            "icon_hint": icon_hint,
        }
    if isinstance(exc, asyncio.CancelledError):
        code = "RUNTIME_CANCELLED"
        severity, icon_hint = _severity_for_code(code)
        return {
            "code": code,
            "message": "The module run was cancelled.",
            "hint": "Restart the run when ready.",
            "severity": severity,
            "icon_hint": icon_hint,
        }
    # Unknown exception — generic envelope, full detail goes to server logs.
    # Workshop learners don't have server-log access, so route them to the
    # facilitator who does (server logs + doctor.log live on the host
    # running `xrpl-lab serve`, not the learner's browser).
    code = "RUNTIME_INTERNAL"
    severity, icon_hint = _severity_for_code(code)
    return {
        "code": code,
        "message": (
            "An internal server error occurred. This is a server-side "
            "fault — not something you did wrong in the module."
        ),
        "hint": (
            "Note your run_id (visible in the dashboard URL or the "
            "POST /api/run response) and notify the workshop "
            "facilitator. They can check server logs and "
            "~/.xrpl-lab/doctor.log to diagnose, then point you at a "
            "fix or workaround (often: re-run the module, or use "
            "--dry-run to bypass network-dependent steps)."
        ),
        "severity": severity,
        "icon_hint": icon_hint,
    }


@dataclass
class ModuleRunSession:
    """Holds state for one module run, bridging sync runner to WebSocket."""

    run_id: str
    module_id: str
    dry_run: bool
    # Lifecycle: running | complete | error | cancelled.
    #
    # TXBCD-007: the session starts in ``running`` — NOT a separate
    # ``started`` state. The concurrency cap counts non-terminal sessions
    # (see ``get_active_count`` / the rate-limit check in ``start_run``);
    # a session pinned in a non-terminal state that no path ever clears
    # would strand its slot forever, because ``_evict_oldest_completed``
    # only evicts terminal sessions and the run-timeout lives inside the
    # task. Previously the session was created ``started`` and only flipped
    # to ``running`` inside ``_run_module_task`` — so any path that
    # returned/raised before that flip (a future early-return, a failure to
    # schedule the task) left a permanent ``started`` orphan holding a
    # slot. Collapsing creation straight to ``running`` closes that window:
    # the only non-terminal state is ``running``, and every code path out
    # of ``_run_module_task`` ends in a terminal status (complete/error)
    # or re-raises CancelledError (after ``cancel_session`` set
    # ``cancelled``). The public status map already collapsed
    # ``started -> running`` (see ``_public_status``), so no facilitator-
    # facing surface changes. The POST /api/run RESPONSE still reports
    # ``status="started"`` as a fixed literal (the HTTP "accepted, task
    # scheduled" signal), independent of this internal field.
    status: str = "running"  # running | complete | error | cancelled
    queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    )
    txids: list[str] = field(default_factory=list)
    report_path: str = ""
    error: str = ""
    # Monotonic clock — used for ordering and elapsed-seconds derivation.
    # Do NOT change to time.time(): the eviction sort and the GET /api/runs
    # elapsed_seconds calculation both rely on monotonicity.
    created_at: float = field(default_factory=time.monotonic)
    # Wall-clock seconds since epoch — used to render an ISO 8601 timestamp
    # for the GET /api/runs facilitator endpoints. Captured at construction
    # so /api/runs returns the same value across calls regardless of clock
    # adjustments after the fact.
    started_at_wall: float = field(default_factory=time.time)
    # Reference to the asyncio task running this module, set by start_run
    # right after _run_module_task is scheduled. DELETE /api/runs/{run_id}
    # uses this to cancel the in-flight run; the WS handler reads it only
    # to know the task exists, never invokes it. Optional so tests that
    # fabricate sessions without a real task continue to work.
    task: asyncio.Task | None = None
    # F-67805cb0: True while a WS connection is actively streaming this
    # session's queue. run_websocket()'s read loop does
    # ``session.queue.get()``, which REMOVES the item from the single
    # per-session queue — if a second connection attached to the same
    # run_id (a learner opening the run page in a second tab, or reloading
    # without the first tab's socket closing first), the two sockets would
    # race for items off the same queue and each silently observe a
    # disjoint, partial subset of the run's frames with no error or
    # indication the stream is incomplete. This flag lets run_websocket()
    # reject a second concurrent attach (close code 4008) instead of
    # letting that race happen. Set True right after the claim-check
    # passes (synchronously, no ``await`` in between — see run_websocket)
    # and reset False in its ``finally`` block, so a clean reconnect after
    # the first socket closes is always allowed.
    ws_attached: bool = False


def _evict_oldest_completed() -> None:
    """If _sessions exceeds _MAX_SESSIONS, evict the oldest terminal session.

    Terminal = ``complete | error | cancelled``. Cancelled runs are
    eligible for eviction the same as completed/errored ones; a
    facilitator-initiated DELETE that lands while at session-cap should
    not block new runs from starting.
    """
    if len(_sessions) <= _MAX_SESSIONS:
        return

    # Find terminal sessions sorted by creation time
    completed = [
        (sid, s) for sid, s in _sessions.items()
        if s.status in ("complete", "error", "cancelled")
    ]
    completed.sort(key=lambda pair: pair[1].created_at)

    # Evict oldest terminal sessions until under limit
    while len(_sessions) > _MAX_SESSIONS and completed:
        sid, _ = completed.pop(0)
        _sessions.pop(sid, None)


# ── Session observability (facilitator endpoints) ───────────────────


def _public_status(internal_status: str) -> str:
    """Map internal session status → facilitator-facing status enum.

    Internal: ``running | complete | error | cancelled``
    Public:   ``running | completed | failed | cancelled``

    ``started`` is retained in the match below as a defensive legacy case
    only — since TXBCD-007 the system never creates a ``started`` session
    (creation goes straight to ``running``; see ``ModuleRunSession.status``).
    Mapping it to ``running`` keeps this total in the unlikely event a
    future path reintroduces it, rather than leaking the raw value.
    ``cancelled`` is its own public state (distinct from ``failed``) so the
    dashboard can render facilitator-initiated terminations differently from
    runtime errors.
    """
    if internal_status in ("started", "running"):
        return "running"
    if internal_status == "complete":
        return "completed"
    if internal_status == "error":
        return "failed"
    if internal_status == "cancelled":
        return "cancelled"
    # Defensive default — a future internal status added without updating
    # this map renders as "running" rather than leaking the new internal
    # value to the public surface.
    return "running"


# SEED-C-run-state: canonical learner-facing banners for the four run
# signals the dashboard must be able to distinguish. api-cli owns the
# strings; dashboard owns the pixels (data-state / live region / CSS).
RUN_SIGNAL_BANNERS: dict[str, str] = {
    "live": "LIVE — XRPL Testnet",
    "dry-run": "DRY-RUN — offline sandbox (simulated)",
    "stalled": (
        "Connection stalled — the server isn't responding. Reload to reconnect."
    ),
    "reconnecting": "Reconnecting to run stream…",
}


def _run_mode(session: ModuleRunSession) -> str:
    """Return ``dry-run`` or ``live`` for a session."""
    return "dry-run" if session.dry_run else "live"


def _connection_signal(session: ModuleRunSession) -> str:
    """Server-visible connection signal: ``live`` while a WS is attached."""
    return "live" if session.ws_attached else "detached"


def _build_run_state_frame(session: ModuleRunSession) -> dict[str, Any]:
    """WS frame that makes mode + connection + all four banners obvious."""
    mode = _run_mode(session)
    return {
        "type": "run_state",
        "mode": mode,
        "mode_banner": RUN_SIGNAL_BANNERS[mode],
        "connection": _connection_signal(session),
        "status": _public_status(session.status),
        "dry_run": session.dry_run,
        "signals": dict(RUN_SIGNAL_BANNERS),
    }


def _build_ping_frame(session: ModuleRunSession) -> dict[str, Any]:
    """Keepalive ping carrying mode so a quiet dry-run stays distinguishable."""
    mode = _run_mode(session)
    return {
        "type": "ping",
        "mode": mode,
        "connection": "live",
        "mode_banner": RUN_SIGNAL_BANNERS[mode],
    }


def _session_to_public_dict(session: ModuleRunSession) -> dict[str, Any]:
    """Project a ModuleRunSession to the safe-to-expose subset.

    Deliberately omits queue contents, error detail, txids, report_path,
    and any internal flags — those require the WS connection (under the
    Origin allow-list) to read. Facilitators get enough to triage, not
    enough to leak step-level workshop state to a non-owner.

    SEED-C-run-state: also exposes ``mode`` / ``mode_banner`` / ``connection``
    / ``signals`` so a refresh can tell dry-run vs live (and has copy for
    stalled/reconnecting) without inventing strings client-side.
    """
    started_iso = datetime.fromtimestamp(
        session.started_at_wall, tz=UTC
    ).isoformat()
    elapsed = max(0.0, time.monotonic() - session.created_at)
    mode = _run_mode(session)
    return {
        "run_id": session.run_id,
        "module_id": session.module_id,
        "status": _public_status(session.status),
        "created_at": started_iso,
        "elapsed_seconds": round(elapsed, 3),
        "queue_size": session.queue.qsize(),
        "dry_run": session.dry_run,
        "mode": mode,
        "mode_banner": RUN_SIGNAL_BANNERS[mode],
        "connection": _connection_signal(session),
        "signals": dict(RUN_SIGNAL_BANNERS),
    }


def get_session_snapshot() -> list[dict[str, Any]]:
    """Return a snapshot of all active/recent sessions, safe-to-expose only.

    Used by the GET /api/runs facilitator endpoint. Returns a list copy so
    callers cannot mutate ``_sessions`` indirectly. Order is insertion
    order (Python 3.7+ dict guarantee) — newest sessions appear last.
    """
    return [_session_to_public_dict(s) for s in _sessions.values()]


def get_session_detail(run_id: str) -> dict[str, Any] | None:
    """Return one session's safe-to-expose snapshot, or None if not found.

    Used by the GET /api/runs/{run_id} facilitator endpoint. The route
    converts a None return into a structured 404 envelope.
    """
    session = _sessions.get(run_id)
    if session is None:
        return None
    return _session_to_public_dict(session)


def get_active_count() -> int:
    """Number of sessions currently counting against the concurrency cap.

    Counts non-terminal sessions — i.e. ``running`` (the only state the
    system creates since TXBCD-007) plus the defensive legacy ``started``.
    Mirrors the rate-limit check in ``start_run`` so the GET /api/runs
    endpoint reports the same active-count semantics facilitators see in
    the 429 response copy. Keeping ``started`` here means that even if a
    future path ever produced one, it would still be correctly counted (and
    so still evictable via the timeout/terminal paths) rather than silently
    uncapped.
    """
    return sum(1 for s in _sessions.values() if s.status in ("running", "started"))


# ── Facilitator-initiated cancellation (DELETE /api/runs/{run_id}) ──


async def cancel_session(run_id: str) -> dict[str, Any] | None:
    """Cancel an in-flight run by run_id; idempotent on terminated runs.

    Returns:
        ``None`` if the run_id is unknown (caller renders 404).
        A dict ``{run_id, status, message}`` describing the outcome:
            - ``status == "cancelled"`` — was running, task cancelled,
              concurrency slot freed, RUNTIME_CANCELLED envelope emitted
              to the WS queue (so any connected client sees the final
              frame before close).
            - ``status == "already_terminated"`` — was already
              ``complete`` / ``error`` / ``cancelled``; no-op.

    Implementation notes:
        Calls ``Task.cancel()`` and awaits the task with a short bound
        so the asyncio.CancelledError fully propagates through the run
        loop's ``except`` clauses before returning. The run loop's
        existing ``except Exception`` branch already maps CancelledError
        to a structured envelope via ``_error_envelope`` — we don't
        duplicate that emission here, we just guarantee it has a chance
        to run before the slot is reported as free.

        The session is left in ``_sessions`` with status="cancelled" so
        subsequent GET /api/runs calls show the terminal state; the
        existing _schedule_session_cleanup grace-period eviction
        (triggered by the WS handler's finally block, or by cleanup-on-
        terminate below) handles long-term removal.
    """
    session = _sessions.get(run_id)
    if session is None:
        return None

    # Idempotent on already-terminated runs. ``cancelled`` is included so
    # a double-DELETE returns a stable shape rather than racing the
    # in-progress cancel.
    if session.status in ("complete", "error", "cancelled"):
        return {
            "run_id": run_id,
            "status": "already_terminated",
            "message": (
                f"Run was already {_public_status(session.status)}; "
                "nothing to cancel."
            ),
        }

    # Mark cancelled BEFORE asking the task to stop — so a concurrent
    # GET /api/runs that lands during cancellation sees the terminal
    # state, not a stale "running" snapshot.
    session.status = "cancelled"
    session.error = "cancelled by facilitator"

    # Emit a final RUNTIME_CANCELLED envelope to any connected WS so
    # the dashboard shows the terminal frame instead of a silent close.
    # The WS read loop breaks on type=="error", then the finally block
    # closes the socket with code 1000 (normal closure) — we don't need
    # a separate close here. _safe_put is non-blocking; even a stalled
    # consumer drops-oldest rather than blocking the cancel path.
    #
    # Pattern #3 discipline: route through ``_error_envelope`` rather
    # than constructing the dict inline — keeps the canonical producer
    # the single source of truth for severity/icon_hint/shape. The
    # facilitator-cancellation message and hint are tailored here
    # (different from a generic asyncio.CancelledError) by passing a
    # purpose-built LabError through the canonical path.
    from ..errors import LabError, LabException

    envelope = _error_envelope(
        LabException(
            LabError(
                code="RUNTIME_CANCELLED",
                message="Run cancelled by facilitator.",
                hint="Restart the run when ready, or check with the facilitator.",
            )
        )
    )
    _safe_put(
        session.queue,
        {"type": "error", **envelope},
        run_id,
    )

    task = session.task
    if task is not None and not task.done():
        task.cancel()
        # Bounded wait — the run loop's except handlers complete quickly
        # (they just write a final envelope to the queue and return).
        # Suppress CancelledError that propagates here from the awaited
        # task itself; either branch (timeout, or our own cancellation)
        # leaves the slot logically free — the session is already marked
        # cancelled and the task will not resume.
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(_await_quietly(task)), timeout=5.0)

    # Schedule grace-period cleanup the same way completed runs are
    # cleaned up (after the WS handler's finally block runs). For
    # facilitator-initiated cancellation there may not be a connected
    # WS, so trigger the cleanup ourselves to avoid leaking a session.
    _schedule_session_cleanup(run_id)

    return {
        "run_id": run_id,
        "status": "cancelled",
        "message": "Run cancelled by facilitator",
    }


async def _await_quietly(task: asyncio.Task) -> None:
    """Await ``task`` and swallow ``CancelledError`` from it.

    The cancel path needs to know the task has finished unwinding
    without re-raising the cancellation that was just requested.
    """
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 — task's own exception path already logged.
        pass


def _schedule_session_cleanup(run_id: str, delay: float = _CLEANUP_GRACE_SECONDS) -> None:
    """Schedule removal of a session after a grace period.

    Idempotent per run_id: if a cleanup is already pending for ``run_id``
    (tracked in ``_pending_cleanups``), this is a no-op. A run with a
    connected WS client otherwise double-schedules — ``cancel_session`` and
    the WS read-loop's ``finally`` both call here — leaving two 60s timers
    racing the same pop (API-A-003). The dedup guard collapses them to one.
    The marker is discarded when the cleanup task completes so a re-created
    session under the same run_id can be cleaned up again later.
    """
    if run_id in _pending_cleanups:
        return
    _pending_cleanups.add(run_id)

    async def _cleanup() -> None:
        try:
            await asyncio.sleep(delay)
            session = _sessions.get(run_id)
            if session and session.status in ("complete", "error", "cancelled"):
                _sessions.pop(run_id, None)
        except Exception:
            logger.warning("Session cleanup failed for %s", run_id)

    # Retain a strong reference so the GC can't collect the task before it
    # finishes (asyncio keeps only a weak ref). Discard on completion to
    # keep _background_tasks bounded. See _background_tasks rationale.
    task = asyncio.create_task(_cleanup())
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        # Clear BOTH the strong-ref retention set and the per-run-id dedup
        # marker. Done in the done-callback (not the coroutine ``finally``)
        # because a task cancelled before its body first executes never runs
        # the body's ``finally`` — the callback always fires, so the marker
        # can never leak and block a future re-schedule for this run_id.
        _background_tasks.discard(t)
        _pending_cleanups.discard(run_id)

    task.add_done_callback(_on_done)


# ── Output-channel redaction (F-717654d7 — HIGH) ─────────────────────
#
# The {"type": "output"} WS frame forwards captured Rich console text
# VERBATIM — unlike the {"type": "error"} channel, which is always routed
# through ``_error_envelope`` and therefore never carries raw exception
# text. A non-LabException step failure prints ``str(exc)`` (runner.py's
# per-step exception handler), which can embed absolute filesystem paths —
# and, via them, the OS username — straight into that captured console
# text (see runner.py's own comment on the Windows os.replace race that
# embeds the state.json path + username on a save-recovery failure). That
# text flows unfiltered through this channel to the browser, so a
# facilitator or peer who merely observes a run_id (visible via
# GET /api/runs) could read leaked internals from a DIFFERENT user's run
# on a ``--host 0.0.0.0`` multi-tenant deployment.
#
# runner.py is being tightened independently to print only the exception
# TYPE name for the non-LabException branch (defense-in-depth, not this
# fix) — this redaction is the SECOND, independent layer: strip
# absolute-path-shaped substrings out of every captured line before it is
# ever queued as an 'output' frame, so a future console.print() regression
# anywhere upstream (in runner.py or any handler it calls) cannot reopen
# the leak. Wallet secrets are a separate concern already handled
# elsewhere (every seed is wrapped in runtime._SecretValue, whose
# __repr__/__str__ deliberately return '***').
#
# Two passes:
#   1. QUOTED paths first — Python exception messages routinely quote the
#      path (``FileNotFoundError: [Errno 2] ... 'C:\\Users\\mike\\x.json'``,
#      or a traceback's ``File "C:\\...\\runner.py", line 321``). Matching
#      the quoted form FIRST lets us safely swallow a path containing
#      spaces by consuming everything up to the matching closing quote.
#   2. BARE paths second — mops up any path-shaped token NOT wrapped in
#      quotes, stopping at the first whitespace/quote/angle-bracket.
#
# ``_PATH_START`` matches a Windows drive letter (``C:\`` / ``E:/``), a
# UNC prefix (``\\host\share``), or a POSIX home/system directory
# (``/home/``, ``/Users/``, ``/root/``, ``/etc/``, ``/var/``, ``/tmp/``,
# ``/usr/``, ``/opt/``, ``/mnt/``). The leading ``(?<![A-Za-z0-9])``
# negative lookbehind is load-bearing: without it, a scheme like
# ``http://`` or ``https://`` false-positives — the trailing letter of
# "http" followed by ``:`` and ``/`` satisfies the bare drive-letter shape
# — and would mangle a legitimate testnet explorer/faucet URL printed to
# the console. The lookbehind requires the candidate path to start at a
# token boundary (not glued onto a preceding letter/digit), which a URL
# scheme or a URL path segment never is.
#
# This is defense-in-depth, not a formal guarantee for every possible path
# shape — the primary control is runner.py printing only the exception
# type name. A bare POSIX path using an unrecognized top-level directory,
# or one embedded with no token-boundary separator, can still partially
# survive.
_PATH_START = (
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|Users|root|etc|var|tmp|usr|opt|mnt)/)"
)
_QUOTED_PATH_RE = re.compile(r"""(['"])""" + _PATH_START + r"""[^'"]*\1""")
_BARE_PATH_RE = re.compile(_PATH_START + r"""[^\s"'<>|]+""")

_PATH_REDACTED = "<path-redacted>"

# F-d4a0435c / F-cbd44005: the path-redaction above is BLIND BY DESIGN to a
# URL-shaped credential — its lookbehind exists so a legitimate
# ``http://``/``https://`` link is never mistaken for a path (see
# test_does_not_mangle_urls in tests/test_reswarm4_api.py). A
# credential-bearing endpoint URL (user-configured XRPL_LAB_FAUCET_URL /
# XRPL_LAB_RPC_URL) can reach this channel via any console.print() site.
#
# One redactor only: locate URL spans that carry any of the three shapes
# ``sanitize_endpoint`` strips (userinfo, QuickNode-style path token, query
# API key) and hand each span to that function. Credential-free explorer /
# faucet CONTENT links stay byte-identical — their path is the point of
# printing them (unlike runtime.py's FundResult.message site, which never
# carries a legitimate path and therefore reduces every URL span).
_URL_SPAN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"()<>]+")
_URL_USERINFO_MARKER_RE = re.compile(r"://[^/\s'@]+@")
_URL_QUERY_CRED_RE = re.compile(
    r"[?&](?:api_?key|token|secret|auth|password|access_token)=",
    re.IGNORECASE,
)
# Single opaque path segment after the authority (QuikNode-style), not a
# multi-segment explorer path like /transactions/<hash>.
_URL_PATH_TOKEN_RE = re.compile(
    r"://[^/\s?#]+/[A-Za-z0-9_-]{16,}/?(?:[?#]|$)",
)


def _url_has_endpoint_credentials(url: str) -> bool:
    """True when ``url`` carries a sanitize_endpoint credential shape."""
    return bool(
        _URL_USERINFO_MARKER_RE.search(url)
        or _URL_QUERY_CRED_RE.search(url)
        or _URL_PATH_TOKEN_RE.search(url)
    )


def _redact_url_credentials(text: str) -> str:
    """Hand credential-shaped URL spans to sanitize_endpoint(); leave others.

    See the F-d4a0435c / F-cbd44005 note above ``_URL_SPAN_RE``.
    """
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0)
        if _url_has_endpoint_credentials(url):
            return sanitize_endpoint(url)
        return url

    return _URL_SPAN_RE.sub(_replace, text)


def _redact_output_text(text: str) -> str:
    """Strip absolute-filesystem-path-shaped substrings AND
    credential-bearing endpoint URLs from ``text``.

    Defense-in-depth for the WS 'output' channel — see the module comment
    above ``_PATH_START`` (paths) and ``_URL_SPAN_RE`` (URL credentials,
    F-d4a0435c / F-cbd44005). Applied in ``_QueueFile.write()`` before any
    captured console line is queued as an ``{"type": "output"}`` frame.
    """
    text = _redact_url_credentials(text)
    text = _QUOTED_PATH_RE.sub(_PATH_REDACTED, text)
    text = _BARE_PATH_RE.sub(_PATH_REDACTED, text)
    return text


def _make_capture_console(
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    run_id: str = "",
):
    """Return a Rich Console whose output is forwarded to the queue as output messages."""
    from rich.console import Console

    class _QueueFile(io.StringIO):
        def write(self, s: str) -> int:
            text = s.rstrip("\n")
            if text:
                # F-717654d7: redact absolute-path-shaped substrings BEFORE
                # queuing — see _redact_output_text / _PATH_START above.
                text = _redact_output_text(text)
                # Schedule a non-blocking put on the event loop thread-safely.
                # Uses _safe_put so a stalled WS consumer triggers drop-oldest
                # rather than unbounded memory growth.
                loop.call_soon_threadsafe(
                    _safe_put,
                    queue,
                    {"type": "output", "text": text},
                    run_id,
                )
            return len(s)

    return Console(file=_QueueFile(), highlight=False, markup=False, no_color=True)


async def _run_module_task(session: ModuleRunSession) -> None:
    """Background task: run the module and feed events to session.queue.

    Each run gets its own ``Console`` and callback closures — no global
    mutable state is shared, so concurrent runs are naturally isolated.
    """

    # F-bddfe64b: load_all_modules() re-reads and re-parses every module
    # file from disk on every call (no caching). This function itself runs
    # as a plain asyncio.Task (start_run does
    # ``asyncio.create_task(_run_module_task(...))``), so in PRODUCTION a
    # synchronous call here blocks the shared event loop for the duration
    # of the disk I/O + parsing, same as the start_run call site below.
    #
    # This call site is deliberately left SYNCHRONOUS rather than offloaded
    # via ``asyncio.to_thread`` — verified empirically that offloading it
    # breaks a wide swath of the existing test suite (test_runner_ws.py
    # alone: 20+ tests hang for 30s-per-keepalive-ping and one fails
    # outright). Root cause: this task is fire-and-forget
    # (``asyncio.create_task``, never awaited by the request/response
    # path), and many existing tests construct ``client = TestClient(app)``
    # WITHOUT the ``with`` context-manager form — each such request spins
    # up its OWN short-lived anyio portal that tears down as soon as THAT
    # request's own coroutine (``start_run``) completes. Before this task
    # had any real suspension point, it ran to completion synchronously
    # within the same portal lifetime; a genuine cross-thread hop here
    # (``asyncio.to_thread``) needs the loop to keep running afterward,
    # and can be orphaned mid-flight when the portal shuts down —
    # silently starving the WS queue of its 'complete'/'error' frame.
    # ``start_run`` does NOT have this problem: it IS the coroutine the
    # request's own portal awaits, so the portal necessarily keeps running
    # until it (and its to_thread call) finishes.
    #
    # Given the severity here is LOW and the existing test suite's
    # TestClient-without-``with`` convention is widespread (not something
    # this agent should rewrite wholesale to chase a LOW finding), this
    # call site stays synchronous. A real fix (caching the parsed module
    # set, invalidated on mtime/dir change) belongs in modules.py, which
    # is outside this agent's owned domain — see the corresponding
    # ``skipped`` entry in this wave's output envelope.
    all_mods = load_all_modules()
    mod = all_mods.get(session.module_id)
    if mod is None:
        # Structured envelope via the canonical producer — same path every
        # other error code takes (Pattern #3 discipline: never construct
        # error envelopes inline; route through ``_error_envelope`` so
        # severity/icon_hint stay attached and the contract is enforced
        # by one source of truth). Server log is fine to log the bare
        # module_id since it's user-supplied input, not a path/secret.
        from ..errors import LabException, module_not_found

        envelope = _error_envelope(LabException(module_not_found(session.module_id)))
        _safe_put(
            session.queue,
            {"type": "error", **envelope},
            session.run_id,
        )
        session.status = "error"
        session.error = envelope["message"]
        return

    if session.dry_run:
        from ..transport.dry_run import DryRunTransport
        transport = DryRunTransport()
    else:
        from ..transport.xrpl_testnet import XRPLTestnetTransport
        transport = XRPLTestnetTransport()

    # Session was already created in ``running`` (see ModuleRunSession.status
    # / TXBCD-007). This assignment is now idempotent — kept as a defensive
    # no-op so the running state is unambiguous at the point execution
    # actually begins, and so a future reorder that introduced a transient
    # pre-run status would self-correct here.
    session.status = "running"

    # get_running_loop() (not the deprecated get_event_loop()) — guaranteed
    # valid here because _run_module_task only ever runs as a scheduled
    # asyncio.Task (start_run does ``asyncio.create_task(_run_module_task(...))``),
    # so a running loop always exists on this thread. get_event_loop() is
    # deprecated for this use and emits a DeprecationWarning under 3.12+.
    loop = asyncio.get_running_loop()
    capture_console = _make_capture_console(session.queue, loop, session.run_id)
    # Skip interactive pauses in WebSocket mode
    capture_console.input = lambda _prompt="": ""  # type: ignore[method-assign]

    total_steps = len(mod.steps)

    # ── Callbacks fed to run_module ──────────────────────────────────

    async def _on_step(action: str, index: int, total: int) -> None:
        _safe_put(
            session.queue,
            {
                "type": "step",
                "action": action,
                "index": index,
                "total": total_steps,
            },
            session.run_id,
        )

    async def _on_step_complete(action: str, success: bool) -> None:
        _safe_put(
            session.queue,
            {
                "type": "step_complete",
                "action": action,
                "success": success,
            },
            session.run_id,
        )

    async def _on_tx(txid: str, result_code: str) -> None:
        if txid not in session.txids:
            session.txids.append(txid)
            _safe_put(
                session.queue,
                {
                    "type": "tx",
                    "txid": txid,
                    "result_code": result_code,
                },
                session.run_id,
            )

    try:
        success = await asyncio.wait_for(
            run_module(
                mod,
                transport,
                dry_run=session.dry_run,
                console=capture_console,
                on_step=_on_step,
                on_step_complete=_on_step_complete,
                on_tx=_on_tx,
            ),
            timeout=_RUN_TIMEOUT_SECONDS,
        )

        # Collect report path from state
        try:
            from ..state import load_state as _load_state
            state = _load_state()
            for cm in state.completed_modules:
                if cm.module_id == session.module_id:
                    session.report_path = cm.report_path or ""
                    if not session.txids:
                        session.txids = list(cm.txids)
                    break
        except Exception as exc:
            # The run already succeeded; this block only backfills
            # report_path/txids for the 'complete' frame. Don't fail the run,
            # but leave a breadcrumb so a "success but blank receipt" report is
            # diagnosable (type name only — no path leak into the WS-captured
            # console, matching the recovery-save discipline elsewhere).
            logger.warning(
                "post-run report-path collection failed for %s: %s",
                session.module_id,
                type(exc).__name__,
            )

        session.status = "complete"
        _safe_put(
            session.queue,
            {
                "type": "complete",
                "success": success,
                "txids": session.txids,
                "report_path": session.report_path,
            },
            session.run_id,
        )
    except TimeoutError as exc:
        # Server-side observability: full str(exc) at ERROR with run_id.
        logger.error(
            "module run timeout: run_id=%s module_id=%s detail=%s",
            session.run_id,
            session.module_id,
            str(exc),
        )
        session.status = "error"
        session.error = f"Module run timed out after {_RUN_TIMEOUT_SECONDS}s"
        envelope = _error_envelope(exc)
        _safe_put(
            session.queue,
            {"type": "error", **envelope},
            session.run_id,
        )
    except asyncio.CancelledError:
        # Facilitator-initiated cancellation via DELETE /api/runs/{run_id}.
        # ``cancel_session`` has already set session.status="cancelled"
        # and emitted the RUNTIME_CANCELLED envelope to the queue, so
        # we must NOT overwrite either here. Re-raise so asyncio's
        # task-cancellation bookkeeping completes correctly (the
        # ``cancel_session`` awaiter expects the task to finish in the
        # cancelled state).
        logger.info(
            "module run cancelled: run_id=%s module_id=%s",
            session.run_id,
            session.module_id,
        )
        raise
    except Exception as exc:
        # Server-side observability: full str(exc) at ERROR with run_id.
        # The client only sees the structured envelope — no paths/internals.
        logger.error(
            "module run failed: run_id=%s module_id=%s detail=%s",
            session.run_id,
            session.module_id,
            str(exc),
        )
        session.status = "error"
        session.error = str(exc)
        envelope = _error_envelope(exc)
        _safe_put(
            session.queue,
            {"type": "error", **envelope},
            session.run_id,
        )


# ── POST /api/run/{module_id} ────────────────────────────────────────

# F-ab18b053: boolean tokens accepted for the ``dry-run`` (hyphen) alias.
# Mirrors the token set FastAPI/pydantic itself accepts for a ``bool``
# query parameter (case-insensitive), so the alias behaves the way a
# caller would already expect the canonical ``dry_run`` key to behave.
_TRUE_QUERY_TOKENS = frozenset({"1", "true", "yes", "on"})
_FALSE_QUERY_TOKENS = frozenset({"0", "false", "no", "off"})


def _parse_bool_query_value(raw: str) -> bool | None:
    """Parse a query-string boolean token, or ``None`` if unrecognized.

    Callers must fail closed (e.g. HTTP 400) on ``None`` rather than guess
    — see F-ab18b053's use at the ``dry-run`` alias site below.
    """
    normalized = raw.strip().lower()
    if normalized in _TRUE_QUERY_TOKENS:
        return True
    if normalized in _FALSE_QUERY_TOKENS:
        return False
    return None


@router.post("/run/{module_id}")
async def start_run(
    request: Request, module_id: str, dry_run: bool = False
) -> RunStartResponse:
    """Start a module run in the background. Returns run_id.

    The ``dry_run`` query parameter overrides the app-level default.  If not
    supplied, the value is read from ``request.app.state.dry_run`` (set by
    ``create_app(dry_run=...)`` via the ``serve`` CLI command).
    """
    # If the caller didn't pass ?dry_run=true, fall back to the app-level default.
    # FastAPI sets default=False above; we detect "not explicitly passed" by
    # checking whether the parsed query params contain the KEY.
    #
    # F-9936b28c: this USED to substring-search the raw query string
    # (``"dry_run" not in str(request.url.query)``), so ANY unrelated query
    # key or value merely CONTAINING the substring "dry_run"/"dry-run" (e.g.
    # ``?note=dry_run_test``) made this believe the caller explicitly passed
    # it — even though the real ``dry_run`` key was absent and FastAPI had
    # already bound the function parameter to its literal default (False).
    # Net effect: the fallback to the server-wide ``--dry-run`` safety
    # default was silently skipped and the run executed live against
    # testnet. Checking membership against the PARSED query params (keys,
    # not raw-string substrings) removes the false-positive class entirely.
    #
    # F-ab18b053: THIS function's parameter is literally named ``dry_run``
    # with no ``Query(alias=...)`` — ONLY that exact key ever binds to it.
    # The fix above still treated mere PRESENCE of the unbound "dry-run"
    # (hyphen) key as an "explicitly passed" signal on its own and used it
    # to skip the app.state fallback — but that key's VALUE never reaches
    # anywhere, so its presence could ONLY ever produce a FALSE "explicit"
    # signal, reopening the exact hole F-9936b28c fixed via key-spelling
    # instead of substring-matching (e.g. ``?dry-run=true`` — a natural
    # mistake, since the CLI's own flag is spelled ``--dry-run`` — silently
    # executed LIVE even against a True app-level safety default).
    #
    # Fixed: the hyphen key's presence no longer suppresses the fallback by
    # itself. When the canonical key is absent, the hyphen key (if present)
    # is read explicitly and folded in as a first-class alias of
    # ``dry_run`` — honouring the caller's evident intent instead of
    # silently discarding it — or the request fails closed with 400 if its
    # value isn't a recognized boolean token. An explicit canonical
    # ``dry_run`` key always takes precedence over the alias.
    if "dry_run" not in request.query_params:
        dry_run_hyphen_raw = request.query_params.get("dry-run")
        if dry_run_hyphen_raw is not None:
            parsed = _parse_bool_query_value(dry_run_hyphen_raw)
            if parsed is None:
                raise HTTPException(status_code=400, detail={
                    "code": "INVALID_QUERY_PARAM",
                    "message": (
                        f"Invalid value {dry_run_hyphen_raw!r} for "
                        "'dry-run'. Use 'true' or 'false' (or the "
                        "canonical 'dry_run' query parameter)."
                    ),
                    "hint": "Example: ?dry-run=true or ?dry_run=true",
                })
            dry_run = parsed
        else:
            dry_run = getattr(request.app.state, "dry_run", False)

    # Rate limit: cap concurrent runs
    active = sum(1 for s in _sessions.values() if s.status in ("running", "started"))
    if active >= _MAX_CONCURRENT_RUNS:
        # The cap exists because each run holds its own asyncio task,
        # event-queue, and Console — without a ceiling, a workshop room
        # full of learners triggering modules simultaneously would
        # exhaust server memory. Distinguish transient (1 active run
        # finishing soon) from sustained (full saturation = workshop
        # may need more capacity or a faster module rotation).
        raise HTTPException(status_code=429, detail={
            "code": "RATE_LIMIT_RUNS",
            "message": (
                f"All {_MAX_CONCURRENT_RUNS} concurrent run slots are in use "
                f"({active} active). The cap protects the server from "
                f"memory exhaustion when many learners run modules at once."
            ),
            "hint": (
                f"If only 1-2 runs are active, wait ~30s and retry — they "
                f"usually finish quickly. If the workshop is at full "
                f"saturation ({_MAX_CONCURRENT_RUNS}/{_MAX_CONCURRENT_RUNS} "
                f"sustained), facilitator can stagger learner starts or "
                f"raise _MAX_CONCURRENT_RUNS in xrpl_lab/api/runner_ws.py."
            ),
        })

    # F-bddfe64b: start_run is an ``async def`` HTTP route handler — unlike
    # a plain sync ``def`` route (which FastAPI already dispatches to a
    # threadpool via Starlette's run_in_threadpool), a synchronous call
    # here runs directly on the event loop and would block every other
    # concurrent request and every in-flight run's WS message pump for the
    # duration of the disk I/O + parsing. Offload to a worker thread.
    all_mods = await asyncio.to_thread(load_all_modules)
    if module_id not in all_mods:
        raise HTTPException(status_code=404, detail={
            "code": "MODULE_NOT_FOUND",
            "message": f"Module '{module_id}' not found",
            "hint": "Use GET /api/modules to see available module IDs",
        })

    # Evict oldest completed sessions if at capacity
    _evict_oldest_completed()

    run_id = str(uuid.uuid4())
    session = ModuleRunSession(run_id=run_id, module_id=module_id, dry_run=dry_run)
    _sessions[run_id] = session

    # Start the module run as a background task. Stash the task on the
    # session so DELETE /api/runs/{run_id} can cancel it. The task
    # reference is also what _cancel_session awaits during cancellation
    # so the asyncio.CancelledError fully propagates before the response
    # returns — preventing a race where the freed concurrency slot is
    # reported before the task actually exits.
    session.task = asyncio.create_task(_run_module_task(session))

    return RunStartResponse(run_id=run_id, status="started")


# ── WS /api/run/{module_id}/ws?run_id=... ────────────────────────────


@router.websocket("/run/{module_id}/ws")
async def run_websocket(websocket: WebSocket, module_id: str, run_id: str) -> None:
    """Stream module run events to a WebSocket client."""
    # ── Origin validation (CSRF-via-WebSocket defense) ────────────────
    # Browser CORS does NOT cover WebSocket upgrades, so we must reject
    # by Origin manually. Browsers always send Origin on WS upgrades; a
    # missing Origin means a non-browser client (CLI, integration test,
    # server-to-server). Per spec, mismatched Origin is rejected with
    # RFC 6455 application policy code 4003.
    # Origin presence required; reject None or non-allow-listed values with RFC 6455 code 4003.
    # The effective allow-list is per-app: ``create_app`` may extend the
    # ``_ALLOWED_ORIGINS`` base with the in-process ``serve`` origin (when the
    # dashboard is mounted on the API server itself, the browser's Origin is
    # the API host:port, not localhost:4321). Falls back to the base constant
    # for the bare-uvicorn / test path where app.state was not populated.
    allowed_origins = getattr(websocket.app.state, "allowed_origins", _ALLOWED_ORIGINS)
    origin = websocket.headers.get("origin")
    if origin is None or origin not in allowed_origins:
        logger.warning(
            "ws origin rejected: origin=%r run_id=%s",
            origin,
            run_id,
        )
        # RFC 6455 caps reason at 123 bytes — surface the canonical
        # dashboard origins so non-browser clients (curl, wscat, custom
        # integrations) know where to connect from. The browser dashboard
        # substitutes its own user-visible message via ws.onclose; this
        # text is for facilitator-debug.
        await websocket.close(
            code=4003,
            reason=(
                "origin not in allow-list — connect dashboard from "
                "http://localhost:4321 or http://localhost:3000"
            ),
        )
        return

    session = _sessions.get(run_id)
    if session is None:
        # RFC 6455 caps reason at 123 bytes. With a 36-char UUID this
        # leaves ~85 bytes for teaching — distinguish "never existed"
        # from "cleaned up after disconnect grace period" so a
        # facilitator's curl-based debug knows whether the run_id was
        # wrong or the session expired, and point at the action.
        await websocket.close(
            code=4004,
            reason=(
                f"run '{run_id}' not found — never existed, or cleaned up "
                f"{_CLEANUP_GRACE_SECONDS}s after disconnect; POST /api/run"
            ),
        )
        return

    if session.module_id != module_id:
        await websocket.close(code=4004, reason="module_id mismatch")
        return

    # F-67805cb0: reject a second concurrent WS attach to the same run_id.
    # Each ModuleRunSession has exactly ONE asyncio.Queue; the read loop
    # below does ``session.queue.get()``, which REMOVES the item. Two
    # sockets attached to the same run_id would race for items off that
    # single queue — a learner opening the run page in a second tab, or
    # reloading without the first tab's socket closing first — and each
    # would silently observe a disjoint, partial subset of the run's
    # output/step/tx frames with no error or indication the stream is
    # incomplete.
    #
    # The check-then-set below is atomic with respect to the event loop:
    # there is no ``await`` between reading ``session.ws_attached`` and
    # setting it, so no other coroutine can interleave and both observe
    # ``False`` (asyncio is single-threaded/cooperative — a task only
    # yields at an ``await``).
    if session.ws_attached:
        logger.warning(
            "ws rejected: run_id=%s already has an active streaming connection",
            run_id,
        )
        await websocket.close(
            code=4008,
            reason="already streaming elsewhere — this run has another active connection",
        )
        return
    session.ws_attached = True

    await websocket.accept()

    # SEED-C-run-state: first frame names dry-run vs live and ships the
    # four canonical banners (incl. stalled/reconnecting copy) so the
    # dashboard does not invent mode strings after a refresh/reconnect.
    try:
        await websocket.send_json(_build_run_state_frame(session))
    except Exception:
        logger.info(
            "ws run_state send failed; closing stream: run_id=%s",
            run_id,
        )
        session.ws_attached = False
        with contextlib.suppress(Exception):
            await websocket.close()
        _schedule_session_cleanup(run_id)
        return

    try:
        while True:
            try:
                msg = await asyncio.wait_for(session.queue.get(), timeout=30.0)
            except TimeoutError:
                # Send a keepalive ping and continue waiting
                try:
                    await websocket.send_json(_build_ping_frame(session))
                except Exception:
                    # TXBCD-006: leave a server-side breadcrumb so a
                    # facilitator investigating a stuck dashboard can tell
                    # "keepalive send failed" apart from "client navigated
                    # away cleanly". The run itself is unaffected — it
                    # completes via its own task and the session is cleaned
                    # up by the finally block below. Log run_id + a short
                    # static reason ONLY: the failed payload is the fixed
                    # ``{"type": "ping"}`` (no learner data), and we
                    # deliberately do NOT log the exception text, which
                    # could carry transport internals. No seed/path here.
                    logger.info(
                        "ws keepalive ping send failed; closing stream "
                        "(run still completes via its task): run_id=%s",
                        run_id,
                    )
                    break
                continue

            try:
                await websocket.send_json(msg)
            except Exception:
                # TXBCD-006: distinct breadcrumb for a mid-stream message
                # send failure (vs the ping-send breadcrumb above). Log the
                # run_id and the message TYPE only — never the message body,
                # which for an ``output`` frame carries captured console text
                # that may include paths/seeds. The exception text is not
                # logged for the same no-leak reason.
                logger.info(
                    "ws message send failed; closing stream (run still "
                    "completes via its task): run_id=%s msg_type=%s",
                    run_id,
                    msg.get("type", "?"),
                )
                break

            # Stop streaming once the run is done
            if msg.get("type") in ("complete", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        # F-67805cb0: release the claim so a legitimate reconnect (network
        # blip, tab refresh after this socket actually closed) is allowed —
        # only a SECOND, SIMULTANEOUSLY-open connection is rejected above.
        session.ws_attached = False
        with contextlib.suppress(Exception):
            await websocket.close()
        # Schedule cleanup of this session after grace period
        _schedule_session_cleanup(run_id)
