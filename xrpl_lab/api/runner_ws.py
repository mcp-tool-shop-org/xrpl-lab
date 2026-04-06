"""WebSocket endpoint for running modules with live output streaming."""

from __future__ import annotations

import asyncio
import contextlib
import io
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..modules import load_all_modules
from ..runner import run_module

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


@dataclass
class ModuleRunSession:
    """Holds state for one module run, bridging sync runner to WebSocket."""

    run_id: str
    module_id: str
    dry_run: bool
    status: str = "started"  # started | running | complete | error
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    txids: list[str] = field(default_factory=list)
    report_path: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.monotonic)


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


def _schedule_session_cleanup(run_id: str, delay: float = _CLEANUP_GRACE_SECONDS) -> None:
    """Schedule removal of a session after a grace period."""

    async def _cleanup() -> None:
        try:
            await asyncio.sleep(delay)
            session = _sessions.get(run_id)
            if session and session.status in ("complete", "error"):
                _sessions.pop(run_id, None)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Session cleanup failed for %s", run_id)

    asyncio.create_task(_cleanup())


def _make_capture_console(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """Return a Rich Console whose output is forwarded to the queue as output messages."""
    from rich.console import Console

    class _QueueFile(io.StringIO):
        def write(self, s: str) -> int:
            text = s.rstrip("\n")
            if text:
                # Schedule the put_nowait on the event loop thread-safely
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "output", "text": text}),
                    loop,
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
        msg = f"Module '{session.module_id}' not found"
        await session.queue.put({"type": "error", "message": msg})
        session.status = "error"
        session.error = msg
        return

    if session.dry_run:
        from ..transport.dry_run import DryRunTransport
        transport = DryRunTransport()
    else:
        from ..transport.xrpl_testnet import XRPLTestnetTransport
        transport = XRPLTestnetTransport()

    session.status = "running"

    loop = asyncio.get_event_loop()
    capture_console = _make_capture_console(session.queue, loop)
    # Skip interactive pauses in WebSocket mode
    capture_console.input = lambda _prompt="": ""  # type: ignore[method-assign]

    total_steps = len(mod.steps)

    # ── Callbacks fed to run_module ──────────────────────────────────

    async def _on_step(action: str, index: int, total: int) -> None:
        await session.queue.put({
            "type": "step",
            "action": action,
            "index": index,
            "total": total_steps,
        })

    async def _on_step_complete(action: str, success: bool) -> None:
        await session.queue.put({
            "type": "step_complete",
            "action": action,
            "success": success,
        })

    async def _on_tx(txid: str, result_code: str) -> None:
        if txid not in session.txids:
            session.txids.append(txid)
            await session.queue.put({
                "type": "tx",
                "txid": txid,
                "result_code": result_code,
            })

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
        await session.queue.put({
            "type": "complete",
            "success": success,
            "txids": session.txids,
            "report_path": session.report_path,
        })
    except TimeoutError:
        session.status = "error"
        session.error = f"Module run timed out after {_RUN_TIMEOUT_SECONDS}s"
        await session.queue.put({
            "type": "error",
            "message": session.error,
        })
    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        await session.queue.put({
            "type": "error",
            "message": str(exc),
        })


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
        raise HTTPException(status_code=429, detail="Too many concurrent runs. Try again later.")

    all_mods = load_all_modules()
    if module_id not in all_mods:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

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
