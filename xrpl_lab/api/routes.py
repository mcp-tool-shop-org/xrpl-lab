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
    StatusResponse,
)

router = APIRouter(prefix="/api")


# -- /api/modules ----------------------------------------------------------


@router.get("/modules")
def list_modules() -> list[ModuleSummary]:
    """List all modules with metadata and completion status."""
    all_mods = load_all_modules()
    state = load_state()
    completed_ids = {cm.module_id for cm in state.completed_modules}

    result: list[ModuleSummary] = []
    for mod in all_mods.values():
        result.append(
            ModuleSummary(
                id=mod.id,
                title=mod.title,
                level=mod.level,
                time_estimate=mod.time,
                requires=mod.requires,
                produces=mod.produces,
                checks=mod.checks,
                completed=mod.id in completed_ids,
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
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

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
    """Return overall lab status: completion counts, wallet info, workspace."""
    state = load_state()
    all_mods = load_all_modules()

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
