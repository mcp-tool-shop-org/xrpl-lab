"""WebSocket endpoint for running modules with live output streaming."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..modules import load_all_modules
from ..runner import run_module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# In-memory store of active and recently completed run sessions
_sessions: dict[str, ModuleRunSession] = {}

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
# the CSRF-via-WebSocket vector. Keep this list in sync with the
# `allow_origins=[...]` list in xrpl_lab/server.py — a future refactor
# (Stage B) should factor these into a single shared constant.
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
    status: str = "started"  # started | running | complete | error | cancelled
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

    Internal: ``started | running | complete | error | cancelled``
    Public:   ``running | completed | failed | cancelled``

    The internal ``started`` state is collapsed into ``running`` for
    consumers — facilitators don't need to distinguish "task created" from
    "task currently executing"; both are "in progress." ``cancelled`` is
    its own public state (distinct from ``failed``) so the dashboard can
    render facilitator-initiated terminations differently from runtime
    errors.
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


def _session_to_public_dict(session: ModuleRunSession) -> dict[str, Any]:
    """Project a ModuleRunSession to the safe-to-expose subset.

    Deliberately omits queue contents, error detail, txids, report_path,
    and any internal flags — those require the WS connection (under the
    Origin allow-list) to read. Facilitators get enough to triage, not
    enough to leak step-level workshop state to a non-owner.
    """
    started_iso = datetime.fromtimestamp(
        session.started_at_wall, tz=UTC
    ).isoformat()
    elapsed = max(0.0, time.monotonic() - session.created_at)
    return {
        "run_id": session.run_id,
        "module_id": session.module_id,
        "status": _public_status(session.status),
        "created_at": started_iso,
        "elapsed_seconds": round(elapsed, 3),
        "queue_size": session.queue.qsize(),
        "dry_run": session.dry_run,
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
    """Number of sessions currently in ``running`` or ``started`` state.

    Mirrors the rate-limit check in ``start_run`` so the GET /api/runs
    endpoint reports the same active-count semantics facilitators see in
    the 429 response copy.
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
    severity, icon_hint = _severity_for_code("RUNTIME_CANCELLED")
    _safe_put(
        session.queue,
        {
            "type": "error",
            "code": "RUNTIME_CANCELLED",
            "message": "Run cancelled by facilitator.",
            "hint": "Restart the run when ready, or check with the facilitator.",
            "severity": severity,
            "icon_hint": icon_hint,
        },
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
    """Schedule removal of a session after a grace period."""

    async def _cleanup() -> None:
        try:
            await asyncio.sleep(delay)
            session = _sessions.get(run_id)
            if session and session.status in ("complete", "error", "cancelled"):
                _sessions.pop(run_id, None)
        except Exception:
            logger.warning("Session cleanup failed for %s", run_id)

    asyncio.create_task(_cleanup())


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

    all_mods = load_all_modules()
    mod = all_mods.get(session.module_id)
    if mod is None:
        # Structured envelope — no internals leaked. Server log is fine to log
        # the bare module_id since it's user-supplied input, not a path/secret.
        envelope = {
            "type": "error",
            "code": "INPUT_MODULE_NOT_FOUND",
            "message": f"Module '{session.module_id}' not found.",
            "hint": "Run 'xrpl-lab list' to see available modules.",
        }
        _safe_put(session.queue, envelope, session.run_id)
        session.status = "error"
        session.error = envelope["message"]
        return

    if session.dry_run:
        from ..transport.dry_run import DryRunTransport
        transport = DryRunTransport()
    else:
        from ..transport.xrpl_testnet import XRPLTestnetTransport
        transport = XRPLTestnetTransport()

    session.status = "running"

    loop = asyncio.get_event_loop()
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
        except Exception:
            pass

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


@router.post("/run/{module_id}")
async def start_run(request: Request, module_id: str, dry_run: bool = False) -> dict[str, Any]:
    """Start a module run in the background. Returns run_id.

    The ``dry_run`` query parameter overrides the app-level default.  If not
    supplied, the value is read from ``request.app.state.dry_run`` (set by
    ``create_app(dry_run=...)`` via the ``serve`` CLI command).
    """
    # If the caller didn't pass ?dry_run=true, fall back to the app-level default
    # FastAPI sets default=False above; we detect "not explicitly passed" by
    # checking whether the raw query string contains the key.
    qs = str(request.url.query)
    if "dry_run" not in qs and "dry-run" not in qs:
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

    all_mods = load_all_modules()
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

    return {"run_id": run_id, "status": "started"}


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
    origin = websocket.headers.get("origin")
    if origin is None or origin not in _ALLOWED_ORIGINS:
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

    await websocket.accept()

    try:
        while True:
            try:
                msg = await asyncio.wait_for(session.queue.get(), timeout=30.0)
            except TimeoutError:
                # Send a keepalive ping and continue waiting
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            try:
                await websocket.send_json(msg)
            except Exception:
                break

            # Stop streaming once the run is done
            if msg.get("type") in ("complete", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
        # Schedule cleanup of this session after grace period
        _schedule_session_cleanup(run_id)
