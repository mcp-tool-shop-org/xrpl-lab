"""FastAPI routes for XRPL Lab API."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..doctor import run_doctor
from ..modules import load_all_modules
from ..reporting import generate_certificate, generate_proof_pack
from ..state import get_workspace_dir, load_state
from .schemas import (
    DoctorCheck,
    DoctorResponse,
    LastRun,
    ModuleDetail,
    ModuleSummary,
    ReportDetail,
    ReportSummary,
    RunInfo,
    RunListResponse,
    StatusResponse,
    TrackProgressItem,
)

router = APIRouter(prefix="/api")


# -- /api/modules ----------------------------------------------------------


@router.get("/modules")
def list_modules() -> list[ModuleSummary]:
    """List all modules with metadata, completion status, and progression."""
    from ..curriculum import build_graph

    all_mods = load_all_modules()
    state = load_state()
    completed_ids = {cm.module_id for cm in state.completed_modules}

    graph = build_graph(all_mods)
    ordered = graph.canonical_order()
    next_id = graph.next_module(completed_ids)

    result: list[ModuleSummary] = []
    for mid in ordered:
        mod = all_mods[mid]
        result.append(
            ModuleSummary(
                id=mod.id,
                title=mod.title,
                track=mod.track,
                summary=mod.summary,
                level=mod.level,
                time_estimate=mod.time,
                mode=mod.mode,
                requires=mod.requires,
                produces=mod.produces,
                checks=mod.checks,
                completed=mod.id in completed_ids,
                is_next=mod.id == next_id,
            )
        )
    return result


# -- /api/modules/{module_id} ----------------------------------------------


@router.get("/modules/{module_id}")
def get_module(module_id: str) -> ModuleDetail:
    """Return detailed info for a single module including steps."""
    all_mods = load_all_modules()
    mod = all_mods.get(module_id)
    if mod is None:
        raise HTTPException(status_code=404, detail={
            "code": "MODULE_NOT_FOUND",
            "message": f"Module '{module_id}' not found",
            "hint": "Use GET /api/modules to see available module IDs",
        })

    state = load_state()
    completed_ids = {cm.module_id for cm in state.completed_modules}

    # Extract step text as string[]
    steps = [step.text for step in mod.steps]

    # Derive description from raw_body or first step text
    description = ""
    if mod.raw_body:
        # Use first paragraph of raw_body
        paragraphs = mod.raw_body.strip().split("\n\n")
        if paragraphs:
            description = paragraphs[0].strip()
    if not description and mod.steps:
        description = mod.steps[0].text

    return ModuleDetail(
        id=mod.id,
        title=mod.title,
        level=mod.level,
        time_estimate=mod.time,
        prerequisites=mod.requires,
        artifacts=mod.produces,
        checks=mod.checks,
        completed=mod.id in completed_ids,
        description=description,
        steps=steps,
    )


# -- /api/status -----------------------------------------------------------


@router.get("/status")
def get_status() -> StatusResponse:
    """Return overall lab status: completion, curriculum position, blockers."""
    from ..workshop import get_learner_status

    state = load_state()
    all_mods = load_all_modules()
    ls = get_learner_status(state)

    last_run: LastRun | None = None
    if state.completed_modules:
        latest = max(state.completed_modules, key=lambda m: m.completed_at)
        last_run = LastRun(
            module=latest.module_id,
            timestamp=datetime.fromtimestamp(latest.completed_at, tz=UTC).isoformat(),
            success=True,
        )

    ws = get_workspace_dir()

    return StatusResponse(
        modules_completed=len(state.completed_modules),
        modules_total=len(all_mods),
        wallet_configured=state.wallet_address is not None and len(state.wallet_address) > 0,
        wallet_address=state.wallet_address,
        last_run=last_run,
        workspace=str(ws),
        current_module=ls.current_module,
        current_track=ls.current_track,
        current_mode=ls.current_mode,
        blockers=ls.blockers,
        is_blocked=ls.is_blocked,
        track_progress=[
            TrackProgressItem(
                track=tp.track,
                completed=tp.completed,
                remaining=tp.remaining,
                total=tp.total,
                done=tp.done,
                is_complete=tp.is_complete,
            )
            for tp in ls.track_progress
        ],
        has_proof_pack=ls.has_proof_pack,
        has_certificate=ls.has_certificate,
        report_count=ls.report_count,
    )


# -- /api/artifacts/proof-pack ---------------------------------------------


@router.get("/artifacts/proof-pack")
def get_proof_pack() -> dict[str, Any]:
    """Return the proof pack JSON generated from current state."""
    state = load_state()
    return generate_proof_pack(state)


# -- /api/artifacts/certificate --------------------------------------------


@router.get("/artifacts/certificate")
def get_certificate() -> dict[str, Any]:
    """Return the certificate JSON generated from current state."""
    state = load_state()
    return generate_certificate(state)


# -- /api/artifacts/reports ------------------------------------------------


@router.get("/artifacts/reports")
def list_reports() -> list[ReportSummary]:
    """Return a list of available module reports with title, generated timestamp, and content."""
    ws = get_workspace_dir()
    reports_dir = ws / "reports"
    if not reports_dir.is_dir():
        return []

    result: list[ReportSummary] = []
    for p in sorted(reports_dir.glob("*.md")):
        # Title from filename (strip .md, replace underscores with spaces, title-case)
        title = p.stem.replace("_", " ").replace("-", " ").title()
        # Generated timestamp from file mtime
        mtime = os.path.getmtime(p)
        generated = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        # Read content
        content = p.read_text(encoding="utf-8")
        result.append(ReportSummary(
            title=title,
            generated=generated,
            content=content,
        ))
    return result


@router.get("/artifacts/reports/{module_id}")
def get_report(module_id: str) -> ReportDetail:
    """Return the content of a specific module report."""
    # Guard against path traversal
    if "/" in module_id or "\\" in module_id or ".." in module_id or "\x00" in module_id:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_MODULE_ID",
            "message": "Invalid module_id",
            "hint": "Module IDs must not contain path separators or special characters",
        })

    ws = get_workspace_dir()
    reports_dir = ws / "reports"
    report_path = reports_dir / f"{module_id}.md"

    # Defense-in-depth: ensure resolved path stays within reports dir
    if not report_path.resolve().is_relative_to(reports_dir.resolve()):
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_MODULE_ID",
            "message": "Invalid module_id",
            "hint": "Module IDs must not contain path separators or special characters",
        })

    if not report_path.exists():
        raise HTTPException(status_code=404, detail={
            "code": "REPORT_NOT_FOUND",
            "message": f"Report for '{module_id}' not found",
            "hint": "Run a module first to generate its report",
        })

    return ReportDetail(
        module_id=module_id,
        content=report_path.read_text(encoding="utf-8"),
    )


# -- /api/doctor -----------------------------------------------------------


@router.get("/doctor")
async def get_doctor() -> DoctorResponse:
    """Run diagnostic checks and return results."""
    report = await run_doctor()

    # Map checks to canonical shape
    checks: list[DoctorCheck] = []
    has_failure = False
    for c in report.checks:
        if c.passed:
            status = "pass"
        else:
            status = "fail"
            has_failure = True

        message = c.detail
        if c.hint:
            message = f"{message}. {c.hint}" if message else c.hint

        checks.append(DoctorCheck(
            name=c.name,
            status=status,
            message=message,
        ))

    # Determine overall status
    if has_failure:
        overall = "error"
    elif report.all_passed:
        overall = "healthy"
    else:
        overall = "warning"

    return DoctorResponse(
        overall=overall,
        checks=checks,
    )


# -- /api/runs (facilitator observability) ---------------------------------
#
# These endpoints expose a safe-to-expose projection of the in-memory
# `_sessions` dict in `runner_ws.py`. Facilitators inspecting via the
# dashboard or curl can ask "which learners are running, who's stuck,
# what's the cleanup status" without opening a WebSocket per session.
#
# Auth model: same as the rest of the HTTP API — `server.py` gates CORS
# to localhost. Deliberately NOT mirroring the WS Origin allow-list:
# these are read-only observability endpoints with no step-level state,
# and HTTP CORS is sufficient. See M1 of F-BRIDGE-B-RUNNER-SESSION-OBS.


@router.get("/runs")
def list_runs() -> RunListResponse:
    """Return all known module-run sessions plus concurrency metadata.

    Includes both active (``running``) and recently-completed sessions
    (``completed`` / ``failed``); completed sessions are pruned by the
    cleanup task scheduled in the WS handler's ``finally`` block.
    """
    from . import runner_ws

    return RunListResponse(
        runs=[RunInfo(**d) for d in runner_ws.get_session_snapshot()],
        max_concurrent=runner_ws._MAX_CONCURRENT_RUNS,
        active_count=runner_ws.get_active_count(),
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> RunInfo:
    """Return the safe-to-expose snapshot for a single run.

    404 with a structured envelope if ``run_id`` is unknown — sessions
    expire after ``_CLEANUP_GRACE_SECONDS`` post-completion, so a 404
    can mean "never existed" or "completed and was cleaned up." The hint
    points facilitators at GET /api/runs for the live list.
    """
    from . import runner_ws

    detail = runner_ws.get_session_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run '{run_id}' not found",
            "hint": "Use GET /api/runs to list active and recent runs",
        })
    return RunInfo(**detail)


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str) -> dict[str, str]:
    """Cancel an in-flight module run; idempotent on terminated runs.

    Facilitator workflow: a learner's run gets stuck (slow testnet, bad
    input, distracted learner) and the facilitator needs to free the
    concurrency slot without restarting the server. This endpoint is the
    surgical cancel for that case.

    Semantics:
        * ``running`` run — cancels the underlying asyncio task, marks
          ``status="cancelled"``, emits a final ``RUNTIME_CANCELLED``
          envelope to any connected WS client, and returns 200 with
          ``status="cancelled"``. The WS handler closes the socket with
          code 1000 (normal closure — this is a facilitator-initiated
          terminal state, not an error).
        * ``complete | error | cancelled`` run — idempotent. Returns
          200 with ``status="already_terminated"``. A double-DELETE
          from a flaky network or a confused facilitator is safe.
        * Unknown ``run_id`` — 404 with the structured ``RUN_NOT_FOUND``
          envelope (same shape as GET /api/runs/{run_id}).

    Auth model: same as GET /api/runs — ``server.py`` gates CORS to
    localhost. A future hardening (F-BRIDGE-FT-004) adds opt-in token
    auth; this v1.6.0 surface is open under the localhost gate.
    """
    from . import runner_ws

    result = await runner_ws.cancel_session(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run '{run_id}' not found",
            "hint": "Use GET /api/runs to list active and recent runs",
        })
    return result
