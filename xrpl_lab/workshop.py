"""Workshop support — facilitator-facing status and track summaries.

Single source of truth for:
- Learner status (4A)
- Support bundles (4B)
- Track completion summaries (4C)

Voice: clear, steady, respectful, lightly encouraging.
Never: hypey, chatty, condescending, gamified.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import UTC, datetime

from . import __version__
from .curriculum import TRACKS, build_graph
from .modules import load_all_modules
from .state import LabState, get_workspace_dir, load_state

# ── 4A: Facilitator Status Truth ─────────────────────────────────────


@dataclass
class TrackProgress:
    """Progress summary for a single track."""

    track: str
    completed: list[str]
    remaining: list[str]
    total: int
    done: int
    is_complete: bool


@dataclass
class LearnerStatus:
    """Everything a facilitator needs in under 10 seconds."""

    version: str
    wallet_address: str | None
    network: str

    # Curriculum position
    current_module: str | None
    current_track: str | None
    current_mode: str | None
    completed_modules: list[str]
    completed_count: int
    total_modules: int

    # Blockers — explicit, not inferred
    blockers: list[str]
    is_blocked: bool

    # Track progress
    track_progress: list[TrackProgress]

    # Activity
    last_activity: str | None  # ISO timestamp
    last_module: str | None
    total_transactions: int
    failed_transactions: int

    # Artifacts
    has_proof_pack: bool
    has_certificate: bool
    report_count: int

    def to_dict(self) -> dict:
        """Serialize to plain dict for JSON output."""
        return {
            "version": self.version,
            "wallet_address": self.wallet_address,
            "network": self.network,
            "current_module": self.current_module,
            "current_track": self.current_track,
            "current_mode": self.current_mode,
            "completed_modules": self.completed_modules,
            "completed_count": self.completed_count,
            "total_modules": self.total_modules,
            "blockers": self.blockers,
            "is_blocked": self.is_blocked,
            "track_progress": [
                {
                    "track": tp.track,
                    "completed": tp.completed,
                    "remaining": tp.remaining,
                    "total": tp.total,
                    "done": tp.done,
                    "is_complete": tp.is_complete,
                }
                for tp in self.track_progress
            ],
            "last_activity": self.last_activity,
            "last_module": self.last_module,
            "total_transactions": self.total_transactions,
            "failed_transactions": self.failed_transactions,
            "has_proof_pack": self.has_proof_pack,
            "has_certificate": self.has_certificate,
            "report_count": self.report_count,
        }


def get_learner_status(state: LabState | None = None) -> LearnerStatus:
    """Build a complete learner status snapshot from state + curriculum."""
    if state is None:
        state = load_state()

    modules = load_all_modules()
    graph = build_graph(modules)
    completed_ids = {m.module_id for m in state.completed_modules}

    next_id = graph.next_module(completed_ids)
    next_mod = modules.get(next_id) if next_id else None

    # ── Blockers (explicit, deterministic) ────────────────────────
    blockers: list[str] = []
    if not state.wallet_address:
        blockers.append("No wallet yet — create one with: xrpl-lab wallet create")
    if next_mod:
        missing_prereqs = [r for r in next_mod.requires if r not in completed_ids]
        if missing_prereqs:
            blockers.append(
                f"'{next_id}' builds on {', '.join(missing_prereqs)} — finish "
                f"{'that' if len(missing_prereqs) == 1 else 'those'} first"
            )
        if next_mod.mode == "dry-run":
            blockers.append(
                f"'{next_id}' runs offline — add --dry-run: "
                f"xrpl-lab run {next_id} --dry-run"
            )

    # Blocked = unresolvable blockers (not mode hints).
    # Mode hints ("requires --dry-run") are guidance, not blockers.
    is_blocked = bool(blockers) and any(
        "wallet" in b.lower() or "prerequisite" in b.lower() for b in blockers
    )

    # ── Track progress ────────────────────────────────────────────
    track_progress: list[TrackProgress] = []
    for track in TRACKS:
        track_mods = [m for m in modules.values() if m.track == track]
        completed_in_track = [m.id for m in track_mods if m.id in completed_ids]
        remaining = [m.id for m in track_mods if m.id not in completed_ids]
        track_progress.append(TrackProgress(
            track=track,
            completed=completed_in_track,
            remaining=remaining,
            total=len(track_mods),
            done=len(completed_in_track),
            is_complete=len(remaining) == 0 and len(track_mods) > 0,
        ))

    # ── Activity ──────────────────────────────────────────────────
    last_activity: str | None = None
    last_module: str | None = None
    if state.completed_modules:
        latest = max(state.completed_modules, key=lambda m: m.completed_at)
        last_activity = datetime.fromtimestamp(latest.completed_at, tz=UTC).isoformat()
        last_module = latest.module_id

    failed = [tx for tx in state.tx_index if not tx.success]

    # ── Artifacts ─────────────────────────────────────────────────
    ws = get_workspace_dir()
    has_proof_pack = (ws / "proofs" / "xrpl_lab_proof_pack.json").exists()
    has_certificate = (ws / "proofs" / "xrpl_lab_certificate.json").exists()
    reports_dir = ws / "reports"
    report_count = len(list(reports_dir.glob("*.md"))) if reports_dir.is_dir() else 0

    return LearnerStatus(
        version=__version__,
        wallet_address=state.wallet_address,
        network=state.network,
        current_module=next_id,
        current_track=next_mod.track if next_mod else None,
        current_mode=next_mod.mode if next_mod else None,
        completed_modules=[m.module_id for m in state.completed_modules],
        completed_count=len(state.completed_modules),
        total_modules=len(modules),
        blockers=blockers,
        is_blocked=is_blocked,
        track_progress=track_progress,
        last_activity=last_activity,
        last_module=last_module,
        total_transactions=len(state.tx_index),
        failed_transactions=len(failed),
        has_proof_pack=has_proof_pack,
        has_certificate=has_certificate,
        report_count=report_count,
    )


# ── 4B: Support Bundle ───────────────────────────────────────────────


@dataclass
class SupportBundle:
    """Machine-parseable, human-readable support handoff artifact."""

    version: str
    generated: str
    python_version: str
    platform_info: str

    # Learner snapshot
    learner: LearnerStatus

    # Environment
    network: str
    rpc_url: str
    faucet_url: str

    # Recent transactions (last 10, no secrets)
    recent_transactions: list[dict]

    # Doctor summary
    doctor_checks: list[dict]

    def to_dict(self) -> dict:
        """Serialize for JSON output."""
        return {
            "schema": "xrpl-lab-support-bundle-v1",
            "version": self.version,
            "generated": self.generated,
            "python_version": self.python_version,
            "platform": self.platform_info,
            "learner": self.learner.to_dict(),
            "network": self.network,
            "rpc_url": self.rpc_url,
            "faucet_url": self.faucet_url,
            "recent_transactions": self.recent_transactions,
            "doctor_checks": self.doctor_checks,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Human-readable markdown rendering."""
        ls = self.learner
        lines: list[str] = []
        lines.append("## XRPL Lab Support Bundle")
        lines.append("")
        lines.append("```")
        lines.append(f"xrpl-lab v{self.version}")
        lines.append(f"Python {self.python_version} on {self.platform_info}")
        lines.append(f"Generated: {self.generated}")
        lines.append("```")
        lines.append("")

        # Position
        lines.append("### Curriculum Position")
        lines.append("")
        lines.append(f"- Current module: {ls.current_module or '(all complete)'}")
        lines.append(f"- Current track: {ls.current_track or 'n/a'}")
        lines.append(f"- Mode: {ls.current_mode or 'n/a'}")
        lines.append(f"- Progress: {ls.completed_count}/{ls.total_modules} modules")
        lines.append("")

        # Blockers
        if ls.blockers:
            lines.append("### Blockers")
            lines.append("")
            for b in ls.blockers:
                lines.append(f"- {b}")
            lines.append("")

        # Track progress
        lines.append("### Track Progress")
        lines.append("")
        for tp in ls.track_progress:
            status = "complete" if tp.is_complete else f"{tp.done}/{tp.total}"
            lines.append(f"- {tp.track}: {status}")
        lines.append("")

        # Environment
        lines.append("### Environment")
        lines.append("")
        lines.append(f"- Network: {self.network}")
        lines.append(f"- RPC: `{self.rpc_url}`")
        lines.append(f"- Faucet: `{self.faucet_url}`")
        if ls.wallet_address:
            lines.append(f"- Wallet: `{ls.wallet_address}`")
        lines.append("")

        # Transactions
        lines.append("### Transactions")
        lines.append("")
        lines.append(
            f"- Total: {ls.total_transactions} "
            f"({ls.total_transactions - ls.failed_transactions} ok, "
            f"{ls.failed_transactions} failed)"
        )
        if self.recent_transactions:
            lines.append("- Recent:")
            for tx in self.recent_transactions[-5:]:
                icon = "ok" if tx.get("success") else "FAIL"
                lines.append(f"  - [{icon}] {tx.get('txid', '?')[:24]}... ({tx.get('module_id')})")
        lines.append("")

        # Artifacts
        lines.append("### Artifacts")
        lines.append("")
        lines.append(f"- Proof pack: {'yes' if ls.has_proof_pack else 'no'}")
        lines.append(f"- Certificate: {'yes' if ls.has_certificate else 'no'}")
        lines.append(f"- Reports: {ls.report_count}")
        lines.append("")

        # Doctor
        lines.append("### Doctor")
        lines.append("")
        for check in self.doctor_checks:
            icon = "PASS" if check.get("passed") else "FAIL"
            line = f"- [{icon}] {check.get('name', '?')}"
            if check.get("detail"):
                line += f": {check['detail']}"
            lines.append(line)
            if check.get("hint") and not check.get("passed"):
                lines.append(f"  - Hint: {check['hint']}")
        lines.append("")

        lines.append("---")
        lines.append("*Attach proof pack if relevant. "
                     "Run `xrpl-lab proof-pack` to generate.*")

        return "\n".join(lines)


def generate_support_bundle(state: LabState | None = None) -> SupportBundle:
    """Generate a support bundle for facilitator handoff."""
    import asyncio

    from .doctor import run_doctor
    from .transport.xrpl_testnet import get_faucet_url, get_rpc_url

    if state is None:
        state = load_state()

    learner = get_learner_status(state)
    report = asyncio.run(run_doctor())

    # Recent tx (last 10, no secrets)
    recent = state.tx_index[-10:]
    recent_transactions = [
        {
            "txid": tx.txid,
            "module_id": tx.module_id,
            "success": tx.success,
            "network": tx.network,
            "timestamp": datetime.fromtimestamp(tx.timestamp, tz=UTC).isoformat(),
        }
        for tx in recent
    ]

    doctor_checks = [
        {"name": c.name, "passed": c.passed, "detail": c.detail, "hint": c.hint}
        for c in report.checks
    ]

    return SupportBundle(
        version=__version__,
        generated=datetime.now(tz=UTC).isoformat(),
        python_version=platform.python_version(),
        platform_info=platform.system(),
        learner=learner,
        network=state.network,
        rpc_url=get_rpc_url(),
        faucet_url=get_faucet_url(),
        recent_transactions=recent_transactions,
        doctor_checks=doctor_checks,
    )


def verify_support_bundle(raw: str) -> tuple[bool, str]:
    """Verify a support bundle is well-formed. Returns (valid, message)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    if not isinstance(data, dict):
        return False, "Expected a JSON object"

    required = {"schema", "version", "generated", "learner", "network"}
    missing = required - set(data.keys())
    if missing:
        return False, f"Missing required fields: {', '.join(sorted(missing))}"

    schema = data.get("schema", "")
    if schema != "xrpl-lab-support-bundle-v1":
        return False, f"Unknown schema: {schema}"

    learner = data.get("learner", {})
    if not isinstance(learner, dict):
        return False, "Learner field must be an object"

    learner_required = {"version", "completed_count", "total_modules"}
    learner_missing = learner_required - set(learner.keys())
    if learner_missing:
        return False, f"Learner missing fields: {', '.join(sorted(learner_missing))}"

    return True, "Support bundle is well-formed."


# ── 4C: Track Completion Summaries ───────────────────────────────────


@dataclass
class TrackSummary:
    """What a learner actually practiced in a track."""

    track: str
    is_complete: bool
    completed_modules: list[str]
    remaining_modules: list[str]
    skills_practiced: list[str]
    mode_breakdown: str  # "testnet" | "dry-run" | "mixed" | "none"
    transaction_count: int
    artifacts: list[str]


def get_track_summaries(state: LabState | None = None) -> list[TrackSummary]:
    """Generate completion summaries for all tracks."""
    if state is None:
        state = load_state()

    modules = load_all_modules()
    completed_ids = {m.module_id for m in state.completed_modules}
    ws = get_workspace_dir()
    reports_dir = ws / "reports"

    summaries: list[TrackSummary] = []
    for track in TRACKS:
        track_mods = [m for m in modules.values() if m.track == track]
        if not track_mods:
            continue

        completed_in_track = [m for m in track_mods if m.id in completed_ids]
        remaining = [m.id for m in track_mods if m.id not in completed_ids]

        # Skills = checks from completed modules
        skills: list[str] = []
        for m in completed_in_track:
            skills.extend(m.checks or [])

        # Mode breakdown
        modes = {m.mode for m in completed_in_track}
        if len(modes) == 0:
            mode_breakdown = "none"
        elif len(modes) == 1:
            mode_breakdown = modes.pop()
        else:
            mode_breakdown = "mixed"

        # Transaction count for this track
        track_mod_ids = {m.id for m in track_mods}
        tx_count = sum(1 for tx in state.tx_index if tx.module_id in track_mod_ids)

        # Related artifacts
        artifacts: list[str] = []
        if reports_dir.is_dir():
            for m in completed_in_track:
                for rpt in reports_dir.glob(f"*{m.id}*"):
                    artifacts.append(rpt.name)

        summaries.append(TrackSummary(
            track=track,
            is_complete=len(remaining) == 0,
            completed_modules=[m.id for m in completed_in_track],
            remaining_modules=remaining,
            skills_practiced=skills,
            mode_breakdown=mode_breakdown,
            transaction_count=tx_count,
            artifacts=artifacts,
        ))

    return summaries


# ── 4D: Workshop Recovery Guidance ───────────────────────────────────


@dataclass
class RecoveryHint:
    """Actionable recovery guidance for a known stuck state."""

    situation: str
    command: str
    explanation: str


def diagnose_recovery(state: LabState | None = None) -> list[RecoveryHint]:
    """Diagnose known stuck states and return recovery hints.

    Each hint is a concrete command the facilitator or learner can run.
    """
    if state is None:
        state = load_state()

    modules = load_all_modules()
    graph = build_graph(modules)
    completed_ids = {m.module_id for m in state.completed_modules}
    next_id = graph.next_module(completed_ids)

    hints: list[RecoveryHint] = []

    # No wallet
    if not state.wallet_address:
        hints.append(RecoveryHint(
            situation="No wallet yet",
            command="xrpl-lab wallet create",
            explanation=(
                "Every account on XRPL needs a wallet — the seed file that "
                "signs your transactions and proves you control the address. "
                "Lab creates one locally (~/.xrpl-lab/wallet.json, owner-only "
                "permissions) and never shares it."
            ),
        ))

    # Next module requires dry-run
    if next_id and next_id in modules:
        next_mod = modules[next_id]
        if next_mod.mode == "dry-run":
            hints.append(RecoveryHint(
                situation=f"'{next_id}' runs in offline sandbox",
                command=f"xrpl-lab run {next_id} --dry-run",
                explanation="This module uses simulated transactions. "
                            "Add --dry-run to run it offline.",
            ))

        # Missing prerequisites
        missing = [r for r in next_mod.requires if r not in completed_ids]
        if missing:
            for req in missing:
                dry = " --dry-run" if modules.get(req, next_mod).mode == "dry-run" else ""
                hints.append(RecoveryHint(
                    situation=f"'{next_id}' needs '{req}' first",
                    command=f"xrpl-lab run {req}{dry}",
                    explanation=f"Finish '{req}' before moving on to '{next_id}'.",
                ))

    # Camp wallet mismatch
    if state.wallet_address:
        from pathlib import Path

        camp_wallet = Path.cwd() / ".xrpl-camp" / "wallet.json"
        if camp_wallet.exists():
            try:
                camp_data = json.loads(camp_wallet.read_text(encoding="utf-8"))
                camp_addr = camp_data.get("address", "")
                if camp_addr and camp_addr != state.wallet_address:
                    hints.append(RecoveryHint(
                        situation="Camp and Lab wallets differ",
                        command="xrpl-lab reset",
                        explanation="Your XRPL Camp and Lab wallets use different addresses. "
                                    "Reset to re-import if you want continuity.",
                    ))
            except (json.JSONDecodeError, OSError):
                pass

    # Failed transactions in recent history
    recent_failed = [tx for tx in state.tx_index[-10:] if not tx.success]
    if len(recent_failed) >= 3:
        hints.append(RecoveryHint(
            situation="Several recent transaction failures",
            command="xrpl-lab doctor",
            explanation="Multiple failures usually mean a connectivity or wallet issue. "
                        "Doctor will check and suggest fixes.",
        ))

    # All modules complete but no proof pack
    if completed_ids and len(completed_ids) == len(modules):
        ws = get_workspace_dir()
        if not (ws / "proofs" / "xrpl_lab_proof_pack.json").exists():
            hints.append(RecoveryHint(
                situation="All modules done — proof pack not yet exported",
                command="xrpl-lab proof-pack",
                explanation="You've finished everything. Export your proof pack "
                            "to seal the completion record.",
            ))

    return hints


# Canonical workshop flows — for docs and CLI reference
WORKSHOP_FLOWS = {
    "offline-sandbox": {
        "name": "All-Offline Sandbox",
        "description": "Run every module in dry-run mode. No network required.",
        "steps": [
            "xrpl-lab wallet create",
            "xrpl-lab start --dry-run",
        ],
        "notes": "Ideal for venues with unreliable internet. "
                 "Simulated transactions, real local state.",
    },
    "mixed": {
        "name": "Mixed Offline + Testnet",
        "description": "Foundation modules on testnet, advanced topics in sandbox.",
        "steps": [
            "xrpl-lab wallet create",
            "xrpl-lab fund",
            "xrpl-lab start",
            "# AMM modules will prompt for --dry-run",
        ],
        "notes": "Most common workshop setup. "
                 "Real transactions for basics, simulation for complex topics.",
    },
    "camp-to-lab": {
        "name": "Camp → Lab Progression",
        "description": "Continue from xrpl-camp into deeper xrpl-lab modules.",
        "steps": [
            "# After completing xrpl-camp:",
            "xrpl-lab start",
            "# Lab auto-detects camp wallet and certificate",
        ],
        "notes": "Lab imports the camp wallet automatically. "
                 "If wallets differ, run 'xrpl-lab reset' to re-import.",
    },
}
