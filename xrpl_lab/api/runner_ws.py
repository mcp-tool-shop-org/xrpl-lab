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


def _error_envelope(exc: BaseException) -> dict[str, str]:
    """Map an exception to a structured user-facing error envelope.

    Never leaks raw paths/internals — the server-side log captures the
    full str(exc); the client only sees code/message/hint. Codes align
    with xrpl_lab.errors.LabError taxonomy (RUNTIME_*, IO_*, etc.).
    """
    from ..errors import LabException

    if isinstance(exc, LabException):
        # Already structured — reuse the existing envelope.
        d = exc.error.safe_dict()
        return {
            "code": str(d.get("code", "RUNTIME_INTERNAL")),
            "message": str(d.get("message", "An error occurred")),
            "hint": str(d.get("hint", "")),
        }
    if isinstance(exc, TimeoutError):
        return {
            "code": "RUNTIME_TIMEOUT",
            "message": "The module run timed out.",
            "hint": "Try again, or run with --dry-run to bypass the network.",
        }
    if isinstance(exc, asyncio.CancelledError):
        return {
            "code": "RUNTIME_CANCELLED",
            "message": "The module run was cancelled.",
            "hint": "Restart the run when ready.",
        }
    # Unknown exception — generic envelope, full detail goes to server logs.
    return {
        "code": "RUNTIME_INTERNAL",
        "message": "An internal error occurred.",
        "hint": "Check server logs and report via xrpl-lab feedback.",
    }


@dataclass
class ModuleRunSession:
    """Holds state for one module run, bridging sync runner to WebSocket."""

    run_id: str
    module_id: str
    dry_run: bool
    status: str = "started"  # started | running | complete | error
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


def _evict_oldest_completed() -> None:
    """If _sessions exceeds _MAX_SESSIONS, evict the oldest completed session."""
    if len(_sessions) <= _MAX_SESSIONS:
        return

    # Find completed/error sessions sorted by creation time
    completed = [
        (sid, s) for sid, s in _sessions.items()
        if s.status in ("complete", "error")
    ]
    completed.sort(key=lambda pair: pair[1].created_at)

    # Evict oldest completed sessions until under limit
    while len(_sessions) > _MAX_SESSIONS and completed:
        sid, _ = completed.pop(0)
        _sessions.pop(sid, None)


# ── Session observability (facilitator endpoints) ───────────────────


def _public_status(internal_status: str) -> str:
    """Map internal session status → facilitator-facing status enum.

    Internal: ``started | running | complete | error``
    Public:   ``running | completed | failed``

    The internal ``started`` state is collapsed into ``running`` for
    consumers — facilitators don't need to distinguish "task created" from
    "task currently executing"; both are "in progress."
    """
    if internal_status in ("started", "running"):
        return "running"
    if internal_status == "complete":
        return "completed"
    if internal_status == "error":
        return "failed"
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


def _schedule_session_cleanup(run_id: str, delay: float = _CLEANUP_GRACE_SECONDS) -> None:
    """Schedule removal of a session after a grace period."""

    async def _cleanup() -> None:
        try:
            await asyncio.sleep(delay)
            session = _sessions.get(run_id)
            if session and session.status in ("complete", "error"):
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
        raise HTTPException(status_code=429, detail={
            "code": "RATE_LIMIT_RUNS",
            "message": f"Maximum {_MAX_CONCURRENT_RUNS} concurrent runs reached",
            "hint": "Wait for a running module to finish, then try again",
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

    # Start the module run as a background task
    asyncio.create_task(_run_module_task(session))

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
        await websocket.close(code=4003, reason="origin not allowed")
        return

    session = _sessions.get(run_id)
    if session is None:
        await websocket.close(code=4004, reason=f"Run '{run_id}' not found")
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
