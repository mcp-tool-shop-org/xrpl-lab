"""FastAPI routes for XRPL Lab API."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .. import __version__
from ..doctor import run_doctor
from ..modules import load_all_modules
from ..reporting import (
    _explorer_url,
    generate_certificate,
    generate_proof_pack,
    verify_certificate,
    verify_certificate_live,
    verify_proof_pack,
    verify_proof_pack_live,
)
from ..state import get_workspace_dir, load_state
from ..transport.xrpl_testnet import classify_network, get_rpc_url
from .schemas import (
    DoctorCheck,
    DoctorResponse,
    HealthResponse,
    LastRun,
    ModuleDetail,
    ModuleSummary,
    ReportDetail,
    ReportSummary,
    RunCancelResponse,
    RunInfo,
    RunListResponse,
    StatusResponse,
    TrackProgressItem,
    VerifyLiveResult,
    VerifyResponse,
    VerifyTxResult,
)


def _active_network(request: Request) -> str:
    """The network label the dashboard/status should show.

    Dry-run mode is a serve-level flag (app.state.dry_run); otherwise the
    network is classified live from the configured RPC endpoint, so an
    XRPL_LAB_RPC_URL override to devnet/local is reported honestly instead
    of the static 'testnet' literal that used to ship in every response.
    """
    if getattr(request.app.state, "dry_run", False):
        return "dry-run"
    return classify_network(get_rpc_url())

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


@router.get("/health")
def get_health(request: Request) -> HealthResponse:
    """Liveness probe — instant, zero network calls.

    Separates "is the serve process up?" (this, fast + local) from "is the
    upstream testnet healthy?" (/api/doctor, slow + network-bound). A
    facilitator on a flaky venue network can confirm the server is alive
    without waiting up to ~30s on a doctor RPC timeout.
    """
    return HealthResponse(
        status="ok",
        version=__version__,
        dry_run=getattr(request.app.state, "dry_run", False),
    )


@router.get("/status")
def get_status(request: Request) -> StatusResponse:
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
        network=_active_network(request),
        version=__version__,
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


# -- /api/verify -----------------------------------------------------------
#
# Browser-reachable proof/certificate verification (FT-PROOF-001). The CLI
# already ships `xrpl-lab proof verify <file> [--live]`; this endpoint exposes
# the SAME trust loop to the dashboard so a facilitator (or anyone handed a
# pack) can paste/drop the JSON and check it without a terminal.
#
# It imports and CALLS the existing reporting functions — it does NOT
# reimplement verification:
#   * verify_proof_pack / verify_certificate  → offline SHA-256 (tamper-evidence)
#   * verify_proof_pack_live / verify_certificate_live → on-ledger re-fetch
#
# The body is UNTRUSTED. It can be any JSON the client pasted, so every access
# is defensive: a non-dict body, or one missing both artifact markers, is a
# clean structured 400 (same {code,message,hint} envelope used across this
# module) — never a 500 stack.


def _verify_explorer_url(tx: dict) -> str:
    """Recompute the explorer link for one live tx-result from its OWN network.

    Mirrors reporting._tx_detail: never trust a URL the pasted body supplied —
    derive it from the tx's recorded network (testnet/devnet → link, everything
    else → "") so a forged pack can't smuggle a misleading link into the table.
    """
    return _explorer_url(tx.get("txid", "") or "", tx.get("network", "") or "")


def _live_to_schema(live) -> VerifyLiveResult:
    """Map a reporting.LiveVerificationResult to the API VerifyLiveResult model,
    enriching each per-tx entry with a server-recomputed explorer URL."""
    d = live.to_dict()
    tx_results = [
        VerifyTxResult(
            txid=tx.get("txid", ""),
            network=tx.get("network", ""),
            status=tx.get("status", ""),
            reason=tx.get("reason", ""),
            checks=list(tx.get("checks", []) or []),
            explorer_url=_verify_explorer_url(tx),
        )
        for tx in d.get("tx_results", [])
    ]
    return VerifyLiveResult(
        artifact_kind=d.get("artifact_kind", ""),
        overall_passed=d.get("overall_passed", False),
        no_onledger_txids=d.get("no_onledger_txids", False),
        passed=d.get("passed", 0),
        failed=d.get("failed", 0),
        skipped=d.get("skipped", 0),
        note=d.get("note", ""),
        tx_results=tx_results,
    )


@router.post("/verify")
async def verify_artifact(request: Request) -> VerifyResponse:
    """Verify a pasted proof pack OR certificate — offline hash + optional --live.

    Request body: the artifact JSON object (a proof pack or a certificate). An
    optional ``live`` flag — accepted as a ``?live=true`` query param OR a
    top-level ``"live": true`` body key — adds the on-ledger trust layer (re-fetch
    every claimed txid from the public XRPL and confirm it exists, is validated,
    and succeeded). The offline SHA-256 check ALWAYS runs; ``live`` ADDS to it.

    Mirrors the CLI exactly: the hash layer is tamper-evidence and the live layer
    is ground truth, and the live check is only attempted when the hash passed
    (an edited artifact is untrustworthy regardless of its txids).
    """
    # The body is untrusted — a parse failure is a clean 400, never a 500.
    try:
        body = await request.json()
    except Exception as exc:  # malformed / empty / non-JSON
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_BODY",
            "message": "Request body is not valid JSON.",
            "hint": "POST the proof pack or certificate JSON object as the body.",
        }) from exc

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_BODY",
            "message": "Request body must be a JSON object (a proof pack or certificate).",
            "hint": "Paste the full xrpl_lab_proof_pack.json or xrpl_lab_certificate.json.",
        })

    # ``live`` from query (?live=true) takes precedence; fall back to a body key.
    # Both are coerced defensively — the body value can be anything.
    live_param = request.query_params.get("live")
    if live_param is not None:
        live = live_param.lower() in ("1", "true", "yes", "on")
    else:
        live = bool(body.get("live") is True)

    # Detect the artifact kind from its marker. A body carrying neither marker is
    # not something we know how to verify → structured 400 (not a silent pass).
    is_pack = body.get("xrpl_lab_proof_pack") is True
    is_cert = body.get("xrpl_lab_certificate") is True
    if not is_pack and not is_cert:
        raise HTTPException(status_code=400, detail={
            "code": "UNKNOWN_ARTIFACT",
            "message": (
                "Body is not a recognized XRPL Lab artifact — it is missing the "
                "xrpl_lab_proof_pack / xrpl_lab_certificate marker."
            ),
            "hint": "Paste a proof pack or certificate generated by xrpl-lab.",
        })

    artifact_kind = "proof_pack" if is_pack else "certificate"

    # Offline hash layer — ALWAYS runs (tamper-evidence). Reuses the EXACT same
    # functions the CLI calls; no reimplementation here.
    if is_pack:
        hash_valid, hash_message = verify_proof_pack(body)
    else:
        hash_valid, hash_message = verify_certificate(body)

    # On-ledger layer — only when asked AND the hash passed. Construct the
    # transport the SAME way the CLI does (no factory → reporting's default
    # public-RPC factory). Defensive: a live-check exception degrades to "hash
    # only" rather than a 500, since the hash verdict is still meaningful.
    live_schema: VerifyLiveResult | None = None
    live_ok = True
    if live and hash_valid:
        try:
            if is_pack:
                live_result = await verify_proof_pack_live(body)
            else:
                live_result = await verify_certificate_live(body)
            live_schema = _live_to_schema(live_result)
            live_ok = live_result.overall_passed
        except Exception:
            # On-ledger check failed to run (network, RPC). Keep the hash verdict;
            # surface the degradation honestly via a synthetic note, do not 500.
            live_schema = VerifyLiveResult(
                artifact_kind=artifact_kind,
                overall_passed=False,
                no_onledger_txids=False,
                note=(
                    "On-ledger verification could not be completed (the public "
                    "ledger was unreachable). The offline integrity check still "
                    "applies; retry --live when the network is reachable."
                ),
            )
            live_ok = False

    overall_passed = hash_valid and (live_ok if (live and hash_valid) else True)

    return VerifyResponse(
        artifact_kind=artifact_kind,
        hash_valid=hash_valid,
        hash_message=hash_message,
        overall_passed=overall_passed,
        live_requested=live,
        live=live_schema,
        version=str(body.get("version", "") or ""),
        address=str(body.get("address", "") or ""),
        network=str(body.get("network", "") or ""),
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
async def cancel_run(run_id: str) -> RunCancelResponse:
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
    auth; this surface is open under the localhost gate.
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
