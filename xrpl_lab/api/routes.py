"""FastAPI routes for XRPL Lab API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..doctor import run_doctor
from ..modules import load_all_modules
from ..reporting import generate_certificate, generate_proof_pack
from ..state import get_workspace_dir, load_state

router = APIRouter(prefix="/api")


# ── /api/modules ──────────────────────────────────────────────────────


@router.get("/modules")
def list_modules() -> list[dict[str, Any]]:
    """List all modules with metadata and completion status."""
    all_mods = load_all_modules()
    state = load_state()
    completed_ids = {cm.module_id for cm in state.completed_modules}

    result: list[dict[str, Any]] = []
    for mod in all_mods.values():
        result.append(
            {
                "id": mod.id,
                "title": mod.title,
                "level": mod.level,
                "time": mod.time,
                "requires": mod.requires,
                "produces": mod.produces,
                "checks": mod.checks,
                "completed": mod.id in completed_ids,
            }
        )
    return result


# ── /api/modules/{module_id} ──────────────────────────────────────────


@router.get("/modules/{module_id}")
def get_module(module_id: str) -> dict[str, Any]:
    """Return detailed info for a single module including steps."""
    all_mods = load_all_modules()
    mod = all_mods.get(module_id)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

    state = load_state()
    completed_ids = {cm.module_id for cm in state.completed_modules}

    steps = [
        {
            "text": step.text,
            "action": step.action,
            "action_args": step.action_args,
        }
        for step in mod.steps
    ]

    return {
        "id": mod.id,
        "title": mod.title,
        "level": mod.level,
        "time": mod.time,
        "requires": mod.requires,
        "produces": mod.produces,
        "checks": mod.checks,
        "completed": mod.id in completed_ids,
        "steps": steps,
    }


# ── /api/status ───────────────────────────────────────────────────────


@router.get("/status")
def get_status() -> dict[str, Any]:
    """Return overall lab status: completion counts, wallet info, version."""
    from .. import __version__

    state = load_state()
    all_mods = load_all_modules()

    last_run: str | None = None
    if state.completed_modules:
        latest = max(state.completed_modules, key=lambda m: m.completed_at)
        from datetime import UTC, datetime

        last_run = datetime.fromtimestamp(latest.completed_at, tz=UTC).isoformat()

    return {
        "version": __version__,
        "network": state.network,
        "wallet_address": state.wallet_address,
        "completed_modules": len(state.completed_modules),
        "total_modules": len(all_mods),
        "last_run": last_run,
    }


# ── /api/artifacts/proof-pack ─────────────────────────────────────────


@router.get("/artifacts/proof-pack")
def get_proof_pack() -> dict[str, Any]:
    """Return the proof pack JSON generated from current state."""
    state = load_state()
    return generate_proof_pack(state)


# ── /api/artifacts/certificate ────────────────────────────────────────


@router.get("/artifacts/certificate")
def get_certificate() -> dict[str, Any]:
    """Return the certificate JSON generated from current state."""
    state = load_state()
    return generate_certificate(state)


# ── /api/artifacts/reports ────────────────────────────────────────────


@router.get("/artifacts/reports")
def list_reports() -> list[str]:
    """Return a list of available module report file names."""
    ws = get_workspace_dir()
    reports_dir = ws / "reports"
    if not reports_dir.is_dir():
        return []
    return sorted(p.name for p in reports_dir.glob("*.md"))


@router.get("/artifacts/reports/{module_id}")
def get_report(module_id: str) -> dict[str, Any]:
    """Return the content of a specific module report."""
    # Guard against path traversal
    if "/" in module_id or "\\" in module_id or ".." in module_id:
        raise HTTPException(status_code=400, detail="Invalid module_id")

    ws = get_workspace_dir()
    report_path = ws / "reports" / f"{module_id}.md"
    if not report_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Report for '{module_id}' not found"
        )

    return {
        "module_id": module_id,
        "content": report_path.read_text(encoding="utf-8"),
    }


# ── /api/doctor ───────────────────────────────────────────────────────


@router.get("/doctor")
async def get_doctor() -> dict[str, Any]:
    """Run diagnostic checks and return results."""
    report = await run_doctor()
    return {
        "all_passed": report.all_passed,
        "summary": report.summary,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "detail": c.detail,
                "hint": c.hint,
            }
            for c in report.checks
        ],
    }
