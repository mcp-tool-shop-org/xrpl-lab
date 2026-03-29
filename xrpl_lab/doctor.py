"""xrpl-lab doctor — checklist diagnostic, not stack traces."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

from .state import get_home_dir, get_workspace_dir, load_state, state_path


@dataclass
class Check:
    """Single diagnostic check result."""

    name: str
    passed: bool
    detail: str = ""
    hint: str = ""


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
        return Check("State file", False, f"Unreadable: {exc}", "Check file permissions")


def _check_workspace() -> Check:
    """Check if workspace is writable."""
    ws = get_workspace_dir()
    if not ws.exists():
        # Try to create it
        try:
            ws.mkdir(parents=True, exist_ok=True)
            (ws / ".doctor-probe").write_text("ok", encoding="utf-8")
            (ws / ".doctor-probe").unlink()
            return Check("Workspace", True, f"Created: {ws.resolve()}")
        except OSError as exc:
            return Check("Workspace", False, f"Cannot create: {exc}", "Check directory permissions")

    # Exists — check writable
    try:
        probe = ws / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("Workspace", True, f"Writable: {ws.resolve()}")
    except OSError as exc:
        return Check("Workspace", False, f"Not writable: {exc}", "Check directory permissions")


async def _check_rpc() -> Check:
    """Check if XRPL RPC endpoint is reachable."""
    from .transport.xrpl_testnet import XRPLTestnetTransport

    transport = XRPLTestnetTransport()
    try:
        info = await asyncio.wait_for(transport.get_network_info(), timeout=30)  # Match RPC_TIMEOUT from xrpl_testnet transport
        if info.connected:
            return Check(
                "RPC endpoint",
                True,
                f"Connected to {info.rpc_url} (ledger {info.ledger_index})",
            )
        return Check(
            "RPC endpoint",
            False,
            f"Not connected: {info.rpc_url}",
            "Check your internet connection or set XRPL_LAB_RPC_URL",
        )
    except TimeoutError:
        rpc_url = os.environ.get("XRPL_LAB_RPC_URL", "https://s.altnet.rippletest.net:51234")
        return Check(
            "RPC endpoint",
            False,
            f"Timeout connecting to {rpc_url}",
            "The testnet RPC may be down. Try again later or set XRPL_LAB_RPC_URL",
        )
    except Exception as exc:
        return Check("RPC endpoint", False, str(exc), "Check XRPL_LAB_RPC_URL")


async def _check_faucet() -> Check:
    """Check if testnet faucet is reachable."""
    import httpx

    faucet_url = os.environ.get(
        "XRPL_LAB_FAUCET_URL", "https://faucet.altnet.rippletest.net/accounts"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            # HEAD or GET to check reachability (don't actually fund)
            resp = await http.get(faucet_url.replace("/accounts", ""))
            # Any response means it's reachable
            return Check("Faucet", True, f"Reachable: {faucet_url} (HTTP {resp.status_code})")
    except httpx.TimeoutException:
        return Check(
            "Faucet",
            False,
            f"Timeout: {faucet_url}",
            "The faucet may be down. Try again later or set XRPL_LAB_FAUCET_URL",
        )
    except Exception as exc:
        return Check("Faucet", False, str(exc), "Check XRPL_LAB_FAUCET_URL")


def _check_env_overrides() -> Check:
    """Report any environment variable overrides."""
    overrides = []
    rpc = os.environ.get("XRPL_LAB_RPC_URL")
    faucet = os.environ.get("XRPL_LAB_FAUCET_URL")
    if rpc:
        overrides.append(f"RPC: {rpc}")
    if faucet:
        overrides.append(f"Faucet: {faucet}")

    if overrides:
        return Check("Env overrides", True, "; ".join(overrides))
    return Check("Env overrides", True, "None (using defaults)")


def _check_last_error() -> Check:
    """Check state for last failed transaction and give a hint."""
    state = load_state()
    failed = [tx for tx in state.tx_index if not tx.success]
    if not failed:
        return Check("Last error", True, "No failed transactions")

    last = failed[-1]
    return Check(
        "Last error",
        True,  # Informational, not a failure
        f"Last failure in '{last.module_id}': tx {last.txid[:24]}{'...' if len(last.txid) > 24 else ''}",
        f"Run: xrpl-lab verify --tx {last.txid} for details",
    )



async def run_doctor() -> DoctorReport:
    """Run all diagnostic checks and return a report."""
    report = DoctorReport()

    # Local checks (fast)
    report.checks.append(_check_wallet())
    report.checks.append(_check_state())
    report.checks.append(_check_workspace())
    report.checks.append(_check_env_overrides())

    # Network checks (may be slow)
    rpc_check = await _check_rpc()
    report.checks.append(rpc_check)

    faucet_check = await _check_faucet()
    report.checks.append(faucet_check)

    # Informational
    report.checks.append(_check_last_error())

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
        "meaning": "Destination account not found on ledger",
        "action": "Verify the destination address exists and is funded",
    },
    "tecNO_DST_INSUF_XRP": {
        "category": "claimed",
        "meaning": "Destination exists but below reserve requirement",
        "action": "Send enough XRP to meet the reserve (currently 10 XRP)",
    },
    "tecPATH_DRY": {
        "category": "claimed",
        "meaning": "No liquidity path for this issued currency payment",
        "action": "Check trust lines and order book liquidity",
    },
    "tecNO_LINE": {
        "category": "claimed",
        "meaning": "Destination has no trust line for this currency",
        "action": "Recipient must create a trust line first",
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
    # Local rejection
    "telINSUF_FEE_P": {
        "category": "local",
        "meaning": "Fee below the server's current minimum",
        "action": "Increase the fee or wait for load to decrease",
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
