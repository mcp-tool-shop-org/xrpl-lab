"""xrpl-lab doctor — checklist diagnostic, not stack traces."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ._atomic import atomic_write_json
from .state import get_home_dir, get_workspace_dir, load_state, state_path

logger = logging.getLogger(__name__)

# Maximum lines retained in the clinic-friendly doctor.log (last-N tail).
_DOCTOR_LOG_MAX_LINES = 100
_DOCTOR_LOG_FILENAME = "doctor.log"


def _redact_path(p: Path | str) -> str:
    """Home-/cwd-relativize a path for doctor output.

    Doctor ``Check.detail`` strings flow into ``doctor.log`` and the
    explicitly issue-shareable feedback bundle (``feedback.py``). A raw
    absolute path leaks the OS username and home layout, so we render paths
    as ``~/…`` or ``./…`` and never expose the absolute home prefix. Mirrors
    the COREBCD-002 discipline already applied to the network checks, which
    surface only ``type(exc).__name__`` rather than ``str(exc)``.
    """
    path = Path(p)
    try:
        resolved = path.resolve()
    except OSError:
        return path.name
    try:
        return "~/" + str(resolved.relative_to(Path.home())).replace("\\", "/")
    except (ValueError, OSError):
        pass
    try:
        return "./" + str(resolved.relative_to(Path.cwd())).replace("\\", "/")
    except (ValueError, OSError):
        return resolved.name


@dataclass
class Check:
    """Single diagnostic check result.

    ``severity`` distinguishes a HARD failure (the environment is broken and
    the learner is stuck — red ✗) from an informational WARN (something worth
    surfacing in amber, but not "broken": curriculum drift, a safe-but-present
    env override, an informational last-error breadcrumb). It defaults to
    ``"fail"`` so every existing check keeps failing loudly; only the
    explicitly informational checks opt into ``"warn"``. The API layer
    (``api/routes.py::get_doctor``) maps ``severity`` onto the
    ``"pass"|"warn"|"fail"`` status the frontend renders — before this field
    the "warn" tier was dead code and informational checks rendered as red
    failures under an "environment is broken" banner.
    """

    name: str
    passed: bool
    detail: str = ""
    hint: str = ""
    severity: str = "fail"  # "fail" (hard, red ✗) | "warn" (informational, amber !)


@dataclass
class DoctorReport:
    """Full diagnostic report."""

    checks: list[Check] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c.passed)
        total = len(self.checks)
        return f"{passed}/{total} checks passed"


def _check_wallet() -> Check:
    """Check if a wallet file exists."""
    home = get_home_dir()
    wallet_path = home / "wallet.json"
    if wallet_path.exists():
        try:
            data = json.loads(wallet_path.read_text(encoding="utf-8"))
            addr = data.get("address", "?")
            return Check("Wallet", True, f"Found: {addr}")
        except (json.JSONDecodeError, OSError):
            return Check(
                "Wallet", False, "File exists but unreadable",
                "Try: xrpl-lab wallet create",
            )
    return Check("Wallet", False, "Not found", "Run: xrpl-lab wallet create")


def _check_state() -> Check:
    """Check if state file is valid."""
    p = state_path()
    if not p.exists():
        return Check("State file", True, "No state yet (fresh install)")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        version = data.get("version", "?")
        modules = len(data.get("completed_modules", []))
        return Check("State file", True, f"v{version}, {modules} module(s) completed")
    except json.JSONDecodeError:
        return Check("State file", False, "Corrupted JSON", "Run: xrpl-lab reset")
    except OSError as exc:
        logger.warning("state file unreadable", exc_info=True)
        return Check(
            "State file", False, f"Unreadable ({type(exc).__name__})", "Check file permissions"
        )


def _check_workspace() -> Check:
    """Check if workspace is writable."""
    ws = get_workspace_dir()
    if not ws.exists():
        # Try to create it. DD-1: workspace is workshop-shareable (0o755),
        # not single-user private — facilitator handoff path. Use the
        # state.py helper so the threat-model classification is centralized.
        try:
            from .state import WORKSPACE_DIR_MODE, _ensure_dir_mode
            _ensure_dir_mode(ws, WORKSPACE_DIR_MODE)
            (ws / ".doctor-probe").write_text("ok", encoding="utf-8")
            (ws / ".doctor-probe").unlink()
            return Check("Workspace", True, f"Created: {_redact_path(ws)}")
        except OSError as exc:
            logger.warning("workspace create failed", exc_info=True)
            return Check(
                "Workspace",
                False,
                f"Cannot create ({type(exc).__name__})",
                "Check directory permissions",
            )

    # Exists — check writable
    try:
        probe = ws / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("Workspace", True, f"Writable: {_redact_path(ws)}")
    except OSError as exc:
        logger.warning("workspace not writable", exc_info=True)
        return Check(
            "Workspace",
            False,
            f"Not writable ({type(exc).__name__})",
            "Check directory permissions",
        )


async def _check_rpc() -> Check:
    """Check if XRPL RPC endpoint is reachable."""
    from .reporting import sanitize_endpoint
    from .transport.xrpl_testnet import XRPLTestnetTransport

    # RA-002 sibling: doctor details flow into the shareable feedback bundle and
    # the /api/doctor surface, so strip any credential embedded in a
    # user-configured RPC URL before it enters a check detail.
    transport = XRPLTestnetTransport()
    try:
        # Match RPC_TIMEOUT from xrpl_testnet transport
        info = await asyncio.wait_for(
            transport.get_network_info(), timeout=30,
        )
        if info.connected:
            return Check(
                "RPC endpoint",
                True,
                f"Connected to {sanitize_endpoint(info.rpc_url)} (ledger {info.ledger_index})",
            )
        return Check(
            "RPC endpoint",
            False,
            f"Not connected: {sanitize_endpoint(info.rpc_url)}",
            "Check your internet connection or set XRPL_LAB_RPC_URL",
        )
    except TimeoutError:
        rpc_url = os.environ.get("XRPL_LAB_RPC_URL", "https://s.altnet.rippletest.net:51234")
        return Check(
            "RPC endpoint",
            False,
            f"Timeout connecting to {sanitize_endpoint(rpc_url)}",
            "The testnet RPC may be down. Try again later or set XRPL_LAB_RPC_URL",
        )
    except Exception as exc:
        # COREBCD-002: str(exc) on a connection/proxy error commonly embeds the
        # endpoint URL (and any configured proxy), which lands in the
        # facilitator-shared support bundle / feedback markdown. Mirror the
        # humanized TimeoutError branch: a path-free detail (exception TYPE
        # only) + the actionable hint, with the full detail logged at WARNING
        # to the package logger for the operator.
        logger.warning("doctor _check_rpc failed: %s", exc)
        return Check(
            "RPC endpoint",
            False,
            f"Could not reach the RPC endpoint ({type(exc).__name__})",
            "Check your internet connection or set XRPL_LAB_RPC_URL",
        )


async def _check_faucet() -> Check:
    """Check if testnet faucet is reachable."""
    import httpx

    from .reporting import sanitize_endpoint

    faucet_url = os.environ.get(
        "XRPL_LAB_FAUCET_URL", "https://faucet.altnet.rippletest.net/accounts"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            # HEAD or GET to check reachability (don't actually fund)
            resp = await http.get(faucet_url.replace("/accounts", ""))
            # Any response means it's reachable — sanitize (RA-002 sibling): the
            # detail reaches the shareable bundle, so strip any credential.
            return Check(
                "Faucet", True,
                f"Reachable: {sanitize_endpoint(faucet_url)} (HTTP {resp.status_code})",
            )
    except httpx.TimeoutException:
        return Check(
            "Faucet",
            False,
            f"Timeout: {sanitize_endpoint(faucet_url)}",
            "The faucet may be down. Try again later or set XRPL_LAB_FAUCET_URL",
        )
    except Exception as exc:
        # COREBCD-002: same endpoint/proxy-leak risk as _check_rpc — str(exc)
        # on an httpx connect error embeds the faucet URL. Path-free detail +
        # actionable hint to the facilitator; full detail to the WARNING log.
        logger.warning("doctor _check_faucet failed: %s", exc)
        return Check(
            "Faucet",
            False,
            f"Could not reach the faucet ({type(exc).__name__})",
            "The faucet may be down. Try again later or set XRPL_LAB_FAUCET_URL",
        )


def _check_env_overrides() -> Check:
    """Report env var overrides and FAIL on a non-testnet endpoint.

    XRPL Lab is testnet-only. An ``XRPL_LAB_RPC_URL`` / ``XRPL_LAB_FAUCET_URL``
    override pointed at mainnet or an unrecognized host is a real-funds risk,
    so the doctor surfaces it as a FAILING check (not a passing
    informational note) — matching the transport's write-path refusal.
    """
    from .reporting import sanitize_endpoint
    from .transport.xrpl_testnet import (
        SAFE_NETWORKS,
        classify_network,
        get_faucet_url,
        get_rpc_url,
    )

    # RA-002 sibling: this detail reaches the shareable feedback bundle, so
    # report the sanitized endpoint (scheme://host[:port]) — enough to diagnose
    # the override without echoing an embedded basic-auth/token credential.
    rpc = os.environ.get("XRPL_LAB_RPC_URL")
    faucet = os.environ.get("XRPL_LAB_FAUCET_URL")
    overrides = []
    if rpc:
        overrides.append(f"RPC: {sanitize_endpoint(rpc)}")
    if faucet:
        overrides.append(f"Faucet: {sanitize_endpoint(faucet)}")

    if not overrides:
        return Check("Env overrides", True, "None (using defaults)")

    rpc_net = classify_network(get_rpc_url())
    faucet_net = classify_network(get_faucet_url())
    detail = "; ".join(overrides) + f"  [RPC: {rpc_net}, faucet: {faucet_net}]"

    if rpc_net not in SAFE_NETWORKS or faucet_net not in SAFE_NETWORKS:
        return Check(
            "Env overrides",
            False,
            detail,
            "Refusing non-testnet endpoint — XRPL Lab is testnet-only and will "
            "not sign or submit against it. Unset the override to use the "
            "default testnet, or use --dry-run for offline practice.",
            severity="fail",  # a non-testnet override is a real-funds risk — hard fail
        )
    # Safe-but-present: the learner overrode an endpoint but stayed on a safe
    # (testnet/devnet/local) network. Not broken — but worth surfacing in amber
    # so it's clear a non-default endpoint is active. Passes (all_passed stays
    # true) yet renders as a WARN, not a silent green pass.
    return Check(
        "Env overrides",
        True,
        detail,
        "A non-default (but safe) endpoint override is active. Unset "
        "XRPL_LAB_RPC_URL / XRPL_LAB_FAUCET_URL to return to the defaults.",
        severity="warn",
    )


def _check_windows_dir_permissions() -> Check:
    """Windows ACL awareness (F-eeddbf7f, MEDIUM).

    ``state._ensure_dir_mode()`` (which backs ``ensure_home_dir()``'s 0o700
    for ``~/.xrpl-lab/``, the directory holding both ``state.json`` and
    ``wallet.json``) explicitly skips the ``os.chmod`` step on Windows —
    POSIX modes don't map onto ACLs, so the wave-1 discipline of tightening
    the home dir to single-user-private is a no-op there. Both
    ``_ensure_dir_mode``'s and ``_atomic``'s docstrings say "the caller is
    responsible for warning the user about that limitation" — until this
    tool actually tightens the Windows ACL (pywin32 / ``icacls``), doctor
    at least says so explicitly, instead of the previous silence that gave
    a learner on a shared/multi-user Windows machine zero signal that their
    wallet-seed-holding directory's permissions were never verified or
    tightened by this tool.

    Informational only (``passed=True``, ``severity="warn"``): the
    environment isn't necessarily broken, and POSIX installs get a plain
    pass with no noise.
    """
    if sys.platform != "win32":
        return Check(
            "Directory permissions", True, "POSIX 0o700 enforced on ~/.xrpl-lab",
        )
    home = get_home_dir()
    return Check(
        "Directory permissions",
        True,
        f"Windows ACLs not tightened by xrpl-lab for {_redact_path(home)}",
        "xrpl-lab tightens directory permissions to owner-only on Linux/"
        "macOS (chmod 0o700); on Windows it does not yet tighten the ACL. "
        "If this machine is shared, consider restricting access yourself, "
        "e.g.: icacls \"%USERPROFILE%\\.xrpl-lab\" /inheritance:r "
        "/grant:r \"%USERNAME%\":F",
        severity="warn",
    )


def _check_last_error() -> Check:
    """Check state for last failed transaction and give a hint."""
    state = load_state()
    failed = [tx for tx in state.tx_index if not tx.success]
    if not failed:
        return Check("Last error", True, "No failed transactions")

    last = failed[-1]
    # Informational, not a failure — but a prior failed tx is worth surfacing
    # in amber (warn) so a facilitator sees "there was a failure here, run
    # verify" rather than a green all-clear. ``passed`` stays True so it never
    # trips the hard-fail / all_passed path.
    return Check(
        "Last error",
        True,  # Informational, not a failure
        f"Last failure in '{last.module_id}': "
        f"tx {last.txid[:24]}{'...' if len(last.txid) > 24 else ''}",
        f"Run: xrpl-lab verify --tx {last.txid} for details",
        severity="warn",
    )


def _check_last_module_state() -> Check:
    """Surface a breadcrumb trail of curriculum progress for facilitators.

    Reads ``state.json`` and reports:

    * the most recently completed module (id + completion timestamp),
    * the most recently attempted module that has NOT completed
      (id + last txid + last error in that module, if any),
    * curriculum-position drift — any completed module whose declared
      prerequisites are not also marked completed.

    Returns an informational :class:`Check` (``passed`` reflects whether
    drift was detected; surface details always populated).

    Stays informational when state is missing — fresh installs are not
    failures. The state-file integrity check (`_check_state`) covers the
    corrupt/unreadable case; here we just skip silently if the load
    returns a fresh state with no modules and no tx history.
    """
    if not state_path().exists():
        return Check(
            "Last module state",
            True,
            "No state yet (fresh install)",
        )

    try:
        state = load_state()
    except Exception as exc:  # noqa: BLE001 — state-file corruption is reported by _check_state
        logger.warning("could not read state for last-module check", exc_info=True)
        return Check(
            "Last module state",
            False,
            f"Could not read state ({type(exc).__name__})",
            "Run: xrpl-lab reset",
        )

    parts: list[str] = []

    # Last completed module (most recent by completed_at timestamp)
    if state.completed_modules:
        last_done = max(state.completed_modules, key=lambda m: m.completed_at)
        try:
            ts = datetime.fromtimestamp(
                last_done.completed_at, tz=UTC,
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            ts = f"epoch={last_done.completed_at}"
        parts.append(f"last completed: {last_done.module_id} ({ts})")
    else:
        parts.append("last completed: none")

    # Last attempted-but-incomplete module: walk tx_index in reverse,
    # find the most recent module_id that is NOT in completed_modules.
    completed_ids = {m.module_id for m in state.completed_modules}
    last_incomplete_attempt = None
    for tx in reversed(state.tx_index):
        if tx.module_id and tx.module_id not in completed_ids:
            last_incomplete_attempt = tx
            break

    if last_incomplete_attempt is not None:
        # Find the most recent FAILED tx for that module to surface as the
        # "last error" hint specific to this in-flight module.
        module_id = last_incomplete_attempt.module_id
        module_failures = [
            tx for tx in state.tx_index
            if tx.module_id == module_id and not tx.success
        ]
        last_err = module_failures[-1] if module_failures else None
        txid_short = (
            last_incomplete_attempt.txid[:16]
            + ("..." if len(last_incomplete_attempt.txid) > 16 else "")
        )
        if last_err is not None:
            err_short = (
                last_err.txid[:16]
                + ("..." if len(last_err.txid) > 16 else "")
            )
            parts.append(
                f"in-flight: {module_id} (last txid {txid_short}, "
                f"last failed tx {err_short})"
            )
        else:
            parts.append(
                f"in-flight: {module_id} (last txid {txid_short}, no failures)"
            )
    else:
        parts.append("in-flight: none")

    # Curriculum-position drift: any completed module whose declared
    # prerequisites are NOT all in the completed set. Lazy-load curriculum
    # so this check stays cheap when state is empty.
    drift_modules: list[str] = []
    if state.completed_modules:
        try:
            from .curriculum import build_graph
            from .modules import load_all_modules

            mods = load_all_modules()
            graph = build_graph(mods)
            for m in state.completed_modules:
                if m.module_id not in graph.modules:
                    # Completed module no longer in catalog — also drift.
                    drift_modules.append(f"{m.module_id} (not in catalog)")
                    continue
                missing = [
                    req for req in graph.prerequisites(m.module_id)
                    if req not in completed_ids
                ]
                if missing:
                    drift_modules.append(
                        f"{m.module_id} (missing prereqs: {','.join(missing)})"
                    )
        except Exception as exc:  # noqa: BLE001 — curriculum load is best-effort here
            logger.warning("curriculum drift check skipped", exc_info=True)
            parts.append(f"curriculum check skipped ({type(exc).__name__})")
            drift_modules = []

    if drift_modules:
        parts.append(f"drift: {'; '.join(drift_modules)}")
        # Curriculum drift is INFORMATIONAL, not a broken environment: a
        # completed module whose prereqs aren't marked complete usually means
        # an out-of-order run or a catalog change, not a stuck learner. Surface
        # it in amber (warn), not as a red ✗ under an "environment broken"
        # banner.
        return Check(
            "Last module state",
            False,
            " | ".join(parts),
            "Run: xrpl-lab curriculum validate",
            severity="warn",
        )

    parts.append("drift: none")
    return Check("Last module state", True, " | ".join(parts))


def _append_doctor_log(report: DoctorReport) -> None:
    """Append a structured JSON-line record to ~/.xrpl-lab/doctor.log.

    Best-effort observability for facilitators reviewing a stuck learner
    post-hoc. Skips silently if the home dir doesn't exist (first run
    before any wallet creation) or if the write fails (perms / disk
    full) — the doctor command itself must never break for a logging
    side-effect.

    Bounded to the last :data:`_DOCTOR_LOG_MAX_LINES` lines via a simple
    read-tail / truncate pattern (no log-rotation library; stdlib only).

    F-be051e03 (LOW): the rewrite is routed through
    ``_atomic.atomic_write_json`` (text mode, via a passthrough
    ``serialize``) instead of a plain ``write_text()`` — this was the one
    persisted file under ~/.xrpl-lab/ that didn't share the
    write-tmp-then-rename crash-safety discipline used for state.json and
    wallet.json, so a crash or power loss mid-write could truncate/corrupt
    the log's tail. Still best-effort: failures are swallowed by the same
    outer ``except OSError`` this function already had — a diagnostic
    breadcrumb trail must never break the doctor command itself. This also
    folds in the ``file_mode=0o600`` tightening at CREATE time (via
    ``os.open``), so the separate post-write ``os.chmod`` this function
    used to do — a TOCTOU window between write and chmod — is no longer
    needed.
    """
    home = get_home_dir()
    if not home.exists():
        # First run before any wallet — don't auto-create the home dir
        # just for observability. The wallet creation flow owns that.
        return

    log_path = home / _DOCTOR_LOG_FILENAME

    record = {
        "ts": datetime.fromtimestamp(time.time(), tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        # Include the actionable hint when present — a facilitator reviewing
        # doctor.log post-hoc needs the "what to do next" string, not just the
        # pass/fail boolean + detail. The hint is the contract (mirrors the
        # CLI surface, which only prints hints on failures, but the log keeps
        # any hint so an informational check's follow-up survives too).
        "checks": {
            c.name: (
                {"passed": c.passed, "detail": c.detail, "hint": c.hint}
                if c.hint
                else {"passed": c.passed, "detail": c.detail}
            )
            for c in report.checks
        },
        "summary": report.summary,
    }

    # Read existing tail, append new record, truncate to last N lines.
    # ONE try/except OSError per the watchpoint: best-effort observability,
    # not security state. Comment makes intent explicit (no contextlib.suppress).
    try:
        existing: list[str] = []
        if log_path.exists():
            existing = log_path.read_text(encoding="utf-8").splitlines()
        existing.append(json.dumps(record, separators=(",", ":")))
        # Keep only the last N entries.
        if len(existing) > _DOCTOR_LOG_MAX_LINES:
            existing = existing[-_DOCTOR_LOG_MAX_LINES:]
        text = "\n".join(existing) + "\n"
        atomic_write_json(log_path, text, file_mode=0o600, serialize=lambda s: s)
    except OSError:
        # Best-effort log; perms or disk-full must not break doctor.
        pass


async def run_doctor() -> DoctorReport:
    """Run all diagnostic checks and return a report."""
    report = DoctorReport()

    # Local checks (fast)
    report.checks.append(_check_wallet())
    report.checks.append(_check_state())
    report.checks.append(_check_workspace())
    report.checks.append(_check_env_overrides())
    report.checks.append(_check_windows_dir_permissions())

    # Network checks (run in parallel)
    rpc_check, faucet_check = await asyncio.gather(_check_rpc(), _check_faucet())
    report.checks.append(rpc_check)
    report.checks.append(faucet_check)

    # Informational
    report.checks.append(_check_last_error())
    report.checks.append(_check_last_module_state())

    # Best-effort clinic log for facilitators (silently skipped on failure).
    _append_doctor_log(report)

    return report


# ── Result code reference (used by transport polish too) ────────────

RESULT_CODE_INFO: dict[str, dict[str, str]] = {
    # Success
    "tesSUCCESS": {
        "category": "success",
        "meaning": "Transaction applied and finalized",
        "action": "None needed",
    },
    # Claimed (fee charged on mainnet)
    "tecUNFUNDED_PAYMENT": {
        "category": "claimed",
        "meaning": "Sender doesn't have enough XRP",
        "action": "Fund your wallet: xrpl-lab fund",
    },
    "tecNO_DST": {
        "category": "claimed",
        "meaning": (
            "Destination account not found on ledger — either the address "
            "doesn't exist yet or has never been funded."
        ),
        "action": (
            "Verify the address. If it's new, send at least 1 XRP first "
            "(XRPL's base reserve) to activate it on the ledger."
        ),
    },
    "tecNO_DST_INSUF_XRP": {
        "category": "claimed",
        "meaning": (
            "Destination exists but doesn't hold enough XRP. XRPL requires "
            "every account to lock up a base reserve (1 XRP) — this is a "
            "minimum balance, not a fee. Additional reserves apply per owned "
            "object (trust line, offer)."
        ),
        "action": (
            "Send enough XRP so the account has 1 XRP available "
            "(excluding any locked in trust lines or offers)."
        ),
    },
    "tecPATH_DRY": {
        "category": "claimed",
        "meaning": "No liquidity path for this issued currency payment",
        "action": "Check trust lines and order book liquidity",
    },
    "tecNO_LINE": {
        "category": "claimed",
        "meaning": (
            "Token transfer requires recipient opt-in. In XRPL you must "
            "explicitly create a trust line before someone can send you an "
            "issued token — this is a security model where you decide what "
            "currencies you accept."
        ),
        "action": (
            "Ask the recipient to run the 'set trust line' step first, "
            "then retry the transfer."
        ),
    },
    "tecDST_TAG_NEEDED": {
        "category": "claimed",
        "meaning": (
            "The destination requires a DestinationTag (asfRequireDest is "
            "set) and this Payment carried none. Custodial/pooled accounts "
            "use the tag to route each deposit to a specific player or "
            "customer — an untagged deposit would land unattributable."
        ),
        "action": (
            "Resend WITH the DestinationTag the recipient assigned you, or "
            "use their X-address (it bundles address + tag into one string "
            "so the tag can't be forgotten)."
        ),
    },
    # Failed (not applied)
    "tefBAD_AUTH": {
        "category": "failed",
        "meaning": "Transaction not authorized by this signing key",
        "action": "Check you're using the correct wallet",
    },
    "tefPAST_SEQ": {
        "category": "failed",
        "meaning": "Sequence number already used",
        "action": "This may be a duplicate. Wait and retry",
    },
    "tefBAD_QUORUM": {
        "category": "failed",
        "meaning": (
            "The multi-signed transaction's signatures are individually valid "
            "but their COMBINED SignerWeight is below the account's "
            "SignerQuorum — together they do not authorize the transaction."
        ),
        "action": (
            "Collect signatures from more (or higher-weighted) signers on the "
            "list until the summed weight meets the quorum, then resubmit."
        ),
    },
    "tefNOT_MULTI_SIGNING": {
        "category": "failed",
        "meaning": (
            "The sending account has no SignerList, so a multi-signed "
            "transaction cannot be authorized for it — multi-signing is "
            "opt-in per account."
        ),
        "action": (
            "Install a signer list first (SignerListSet with a quorum and "
            "1-32 weighted signers), or sign normally with the account's key."
        ),
    },
    "tefBAD_SIGNATURE": {
        "category": "failed",
        "meaning": (
            "A signature in the Signers array doesn't belong to this "
            "transaction's signer list — the co-signer is not on the list "
            "(or appears twice), so its weight cannot count."
        ),
        "action": (
            "Check every co-signer against the account's SignerList entries; "
            "only listed signers contribute weight, each at most once."
        ),
    },
    # Local rejection
    "telINSUF_FEE_P": {
        "category": "local",
        "meaning": (
            "Your fee is below the current network minimum. XRPL adjusts the "
            "minimum dynamically with load — testnet often spikes during high "
            "activity and resets every few minutes."
        ),
        "action": (
            "Wait briefly and retry — fees usually drop. If persistent, "
            "increase the fee manually."
        ),
    },
    # Malformed
    "temBAD_AMOUNT": {
        "category": "malformed",
        "meaning": "Amount is invalid (zero, negative, or wrong format)",
        "action": "Check the amount value and currency format",
    },
    "temBAD_FEE": {
        "category": "malformed",
        "meaning": "Fee value is malformed",
        "action": "Use a valid fee in drops (minimum 10)",
    },
    "temBAD_QUORUM": {
        "category": "malformed",
        "meaning": (
            "The SignerListSet's SignerQuorum is unachievable — zero/negative "
            "for a create, or greater than the sum of the SignerWeights, so "
            "no combination of signatures could ever authorize anything."
        ),
        "action": (
            "Set 0 < SignerQuorum <= sum of the SignerWeight values in the "
            "entries list."
        ),
    },
    "temBAD_SIGNER": {
        "category": "malformed",
        "meaning": (
            "A SignerEntry is invalid — the account listed ITSELF as a "
            "signer, or the same signer appears more than once. A signer "
            "list delegates authority to OTHER keys, each listed once."
        ),
        "action": (
            "Remove the owner's own address and any duplicates from "
            "SignerEntries (raise a signer's weight instead of repeating it)."
        ),
    },
    "temBAD_WEIGHT": {
        "category": "malformed",
        "meaning": (
            "A SignerEntry carries a non-positive SignerWeight — a "
            "zero-weight signer could never contribute toward the quorum."
        ),
        "action": "Give every signer entry a positive integer weight.",
    },
    # Retry
    "terPRE_SEQ": {
        "category": "retry",
        "meaning": "Sequence number is ahead — a prior tx is still pending",
        "action": "Wait for the pending transaction to finalize, then retry",
    },
    "terQUEUED": {
        "category": "retry",
        "meaning": "Transaction queued for a future ledger",
        "action": "Wait — the transaction should be included soon",
    },
    # Local errors
    "local_error": {
        "category": "local",
        "meaning": "Rejected by your client before reaching the network",
        "action": "Check the error message for details",
    },
}


def explain_result_code(code: str) -> dict[str, str]:
    """Look up a result code and return its explanation.

    Returns a dict with 'category', 'meaning', and 'action' keys.
    """
    if code in RESULT_CODE_INFO:
        return RESULT_CODE_INFO[code]

    # Infer category from prefix
    prefix_map = {
        "tes": ("success", "Transaction succeeded"),
        "tec": ("claimed", "Transaction applied but failed (fee charged on mainnet)"),
        "tef": ("failed", "Transaction not applied to the ledger"),
        "tel": ("local", "Rejected locally by the server"),
        "tem": ("malformed", "Transaction format is invalid"),
        "ter": ("retry", "Transaction may succeed if retried later"),
    }

    for prefix, (cat, desc) in prefix_map.items():
        if code.startswith(prefix):
            return {
                "category": cat,
                "meaning": f"{desc}: {code}",
                "action": "Check XRPL docs for this specific code",
            }

    return {
        "category": "unknown",
        "meaning": f"Unknown result code: {code}",
        "action": "Check XRPL documentation",
    }
