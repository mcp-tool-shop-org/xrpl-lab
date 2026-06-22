"""Canonical API response schemas -- single source of truth.

These models define the API contract between backend and frontend.
Routes MUST return instances of these models.
Frontend TypeScript types MUST mirror these fields exactly.
Contract tests validate both sides against these definitions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# -- /api/status -----------------------------------------------------------


class LastRun(BaseModel):
    module: str
    timestamp: str
    success: bool


class TrackProgressItem(BaseModel):
    track: str
    completed: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    total: int
    done: int
    is_complete: bool


class StatusResponse(BaseModel):
    modules_completed: int
    modules_total: int
    wallet_configured: bool
    wallet_address: str | None
    last_run: LastRun | None
    workspace: str
    current_module: str | None = None
    current_track: str | None = None
    current_mode: str | None = None
    blockers: list[str] = Field(default_factory=list)
    is_blocked: bool = False
    track_progress: list[TrackProgressItem] = Field(default_factory=list)
    has_proof_pack: bool = False
    has_certificate: bool = False
    report_count: int = 0
    # The dashboard renders these directly. Before they were returned the
    # Network card showed a permanent "Unknown" and the footer "v-.-.-".
    # network is the ACTIVE network ("dry-run" | "testnet" | "devnet" |
    # "local" | "mainnet" | "unknown"), derived live from the serve mode +
    # configured RPC endpoint — not the static state literal.
    network: str = ""
    version: str = ""


class HealthResponse(BaseModel):
    """Liveness response — zero network calls, instant. Distinct from the
    network-bound readiness check at /api/doctor (which probes RPC + faucet
    with a 30s/15s budget). Lets a facilitator answer "is the server up?"
    without waiting on the upstream testnet."""

    status: str = "ok"
    version: str = ""
    dry_run: bool = False


# -- /api/modules ----------------------------------------------------------


class ModuleSummary(BaseModel):
    id: str
    title: str
    track: str = ""
    summary: str = ""
    level: str
    time_estimate: str
    mode: str = "testnet"
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    completed: bool
    is_next: bool = False


class ModuleDetail(BaseModel):
    id: str
    title: str
    level: str
    time_estimate: str
    prerequisites: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    completed: bool
    description: str
    steps: list[str] = Field(default_factory=list)


# -- /api/doctor -----------------------------------------------------------


class DoctorCheck(BaseModel):
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str


class DoctorResponse(BaseModel):
    overall: str  # "healthy" | "warning" | "error"
    checks: list[DoctorCheck]


# -- /api/artifacts --------------------------------------------------------


class ReportSummary(BaseModel):
    title: str
    generated: str
    content: str


class ReportDetail(BaseModel):
    module_id: str
    content: str


# -- /api/verify -----------------------------------------------------------


class VerifyTxResult(BaseModel):
    """Per-tx on-ledger verdict — mirrors reporting.TxLiveResult.to_dict().

    ``status`` is the live verdict ("PASS" | "FAIL" | "SKIPPED"); ``explorer_url``
    is recomputed server-side from the tx's own recorded network (testnet/devnet
    get a link, dry-run/local/simulated get "") so the browser table can link a
    real-network txid to its public explorer entry without trusting a value the
    pasted JSON supplied.
    """

    txid: str
    network: str
    status: str  # LIVE_PASS | LIVE_FAIL | LIVE_SKIPPED
    reason: str
    checks: list[str] = Field(default_factory=list)
    explorer_url: str = ""


class VerifyLiveResult(BaseModel):
    """Aggregate on-ledger verdict — mirrors reporting.LiveVerificationResult.to_dict()."""

    artifact_kind: str  # "proof_pack" | "certificate"
    overall_passed: bool
    no_onledger_txids: bool = False
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    note: str = ""
    tx_results: list[VerifyTxResult] = Field(default_factory=list)


class VerifyResponse(BaseModel):
    """Response for POST /api/verify — the browser-reachable equivalent of the
    CLI ``proof verify`` / ``cert-verify``.

    The offline hash layer (``hash_valid`` / ``hash_message``) ALWAYS runs and is
    tamper-evidence. The on-ledger ``live`` layer is present only when the request
    asked for it AND the hash passed (a locally-edited artifact is untrustworthy
    regardless of what its txids resolve to, so the live check is not attempted —
    mirrors the CLI). ``artifact_kind`` is "proof_pack" | "certificate", detected
    from the body's marker. ``overall_passed`` is the single headline verdict:
    hash must pass, and — when a live check ran — it must pass too.
    """

    artifact_kind: str  # "proof_pack" | "certificate"
    hash_valid: bool
    hash_message: str
    overall_passed: bool
    live_requested: bool = False
    live: VerifyLiveResult | None = None
    # Echoed identity fields (best-effort, never trusted) for the result header.
    version: str = ""
    address: str = ""
    network: str = ""


# -- /api/run --------------------------------------------------------------


class RunStartResponse(BaseModel):
    """Response for POST /api/run/{module_id}.

    ``status`` is always ``"started"`` on success; the run then progresses
    over the WebSocket. Mirrors the TS ``RunResult`` interface in
    ``site/src/lib/api.ts`` ({run_id, status}).
    """

    run_id: str
    status: str


class RunCancelResponse(BaseModel):
    """Response for DELETE /api/runs/{run_id} (facilitator cancellation).

    Union of the fields across both cancel outcomes so the shape is the
    SAME on every path:

      * active run cancelled — ``status="cancelled"``, ``message`` set.
      * already-terminal run — ``status="already_terminated"``, ``message`` set.

    ``message`` is optional in the type (``str | None``) to permit a future
    empty/None case, but both current branches populate it. Keeping it on
    every response lets the dashboard render one shape regardless of which
    branch fired.
    """

    run_id: str
    status: str  # "cancelled" | "already_terminated"
    message: str | None = None


# -- /api/runs (facilitator observability) ---------------------------------


class RunInfo(BaseModel):
    """Safe-to-expose snapshot of a single module run session.

    Returned by GET /api/runs (in a list) and GET /api/runs/{run_id}.
    Deliberately omits queue contents, error detail, txids, and report
    path — those require the WS connection (under its Origin allow-list)
    to read. Facilitators get enough to triage, not enough to leak
    step-level workshop state to a non-owner.
    """

    run_id: str
    module_id: str
    status: str  # "running" | "completed" | "failed" | "cancelled"
    created_at: str  # ISO 8601 UTC
    elapsed_seconds: float
    queue_size: int
    dry_run: bool


class RunListResponse(BaseModel):
    """Aggregate response for GET /api/runs.

    ``runs``           — list of all known sessions (active + recently completed)
    ``max_concurrent`` — the rate-limit cap (mirrors ``_MAX_CONCURRENT_RUNS``)
    ``active_count``   — sessions currently in ``running`` state
    """

    runs: list[RunInfo] = Field(default_factory=list)
    max_concurrent: int
    active_count: int
