"""WebSocket endpoint for running modules with live output streaming."""

from __future__ import annotations

import asyncio
import contextlib
import io
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..modules import load_all_modules
from ..runner import run_module

router = APIRouter(prefix="/api")

# In-memory store of active and recently completed run sessions
_sessions: dict[str, ModuleRunSession] = {}


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
    """Background task: run the module and feed events to session.queue."""

    all_mods = load_all_modules()
    mod = all_mods.get(session.module_id)
    if mod is None:
        msg = f"Module '{session.module_id}' not found"
        await session.queue.put({"type": "error", "message": msg})
        session.status = "error"
        session.error = f"Module '{session.module_id}' not found"
        return

    if session.dry_run:
        from ..transport.dry_run import DryRunTransport
        transport = DryRunTransport()
    else:
        from ..transport.xrpl_testnet import XRPLTestnetTransport
        transport = XRPLTestnetTransport()

    session.status = "running"

    # Emit step events by wrapping the runner's console output
    # We intercept at the run_module level by patching the console in runner module
    import xrpl_lab.runner as runner_mod

    loop = asyncio.get_event_loop()
    capture_console = _make_capture_console(session.queue, loop)

    # Count steps for progress messages
    total_steps = len(mod.steps)

    # Emit step start events alongside the regular execution
    # We wrap _execute_action to emit step events
    original_execute = runner_mod._execute_action

    step_counter = [0]

    async def _tracked_execute(step, state, transport_inner, wallet_seed, context):
        idx = step_counter[0]
        step_counter[0] += 1
        action = step.action or "read"
        await session.queue.put({
            "type": "step",
            "action": action,
            "index": idx,
            "total": total_steps,
        })
        result_ctx = await original_execute(step, state, transport_inner, wallet_seed, context)

        # Emit tx events for any new txids
        new_txids = result_ctx.get("txids", [])
        for txid in new_txids:
            if txid not in session.txids:
                session.txids.append(txid)
                last_submit = result_ctx.get("last_submit")
                result_code = ""
                if last_submit and hasattr(last_submit, "result_code"):
                    result_code = last_submit.result_code or ""
                await session.queue.put({
                    "type": "tx",
                    "txid": txid,
                    "result_code": result_code,
                })

        success = True
        last_submit = result_ctx.get("last_submit")
        if last_submit and hasattr(last_submit, "success"):
            success = bool(last_submit.success)

        await session.queue.put({
            "type": "step_complete",
            "action": action,
            "success": success,
        })
        return result_ctx

    original_console = runner_mod.console
    runner_mod.console = capture_console
    runner_mod._execute_action = _tracked_execute

    try:
        # run_module calls console.input for step pauses — we skip interactive mode
        # by patching console.input to return "" automatically
        capture_console.input = lambda _prompt="": ""  # type: ignore[method-assign]

        success = await run_module(mod, transport, dry_run=session.dry_run)

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
    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        await session.queue.put({
            "type": "error",
            "message": str(exc),
        })
    finally:
        runner_mod.console = original_console
        runner_mod._execute_action = original_execute


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

    all_mods = load_all_modules()
    if module_id not in all_mods:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

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
