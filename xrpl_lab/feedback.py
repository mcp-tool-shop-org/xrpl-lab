"""Feedback generator — issue-ready markdown block for support."""

from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime

from . import __version__
from .doctor import run_doctor
from .state import get_workspace_dir, load_state
from .transport.xrpl_testnet import get_faucet_url, get_rpc_url


def generate_feedback() -> str:
    """Generate an issue-ready markdown block pulling from doctor, state, and env."""
    state = load_state()

    # Run doctor (async).  generate_feedback() is only called from the CLI
    # (sync click command), so asyncio.run() is safe here.  If this is ever
    # called from an already-running event loop, refactor to await instead.
    report = asyncio.run(run_doctor())

    lines: list[str] = []
    lines.append("## XRPL Lab Feedback")
    lines.append("")
    lines.append("```")
    lines.append(f"xrpl-lab v{__version__}")
    lines.append(f"Python {platform.python_version()} on {platform.system()}")
    lines.append(f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("```")
    lines.append("")

    # Doctor summary
    lines.append("### Doctor")
    lines.append("")
    for check in report.checks:
        icon = "PASS" if check.passed else "FAIL"
        line = f"- [{icon}] {check.name}"
        if check.detail:
            line += f": {check.detail}"
        lines.append(line)
        if check.hint and not check.passed:
            lines.append(f"  - Hint: {check.hint}")
    lines.append("")

    # Endpoint + network
    lines.append("### Environment")
    lines.append("")
    lines.append(f"- Network: {state.network}")
    lines.append(f"- RPC: `{get_rpc_url()}`")
    lines.append(f"- Faucet: `{get_faucet_url()}`")
    if state.wallet_address:
        lines.append(f"- Wallet: `{state.wallet_address}`")
    lines.append("")

    # Proof pack reference
    proof_path = get_workspace_dir() / "proofs" / "xrpl_lab_proof_pack.json"
    if proof_path.exists():
        import json

        try:
            content = proof_path.read_text(encoding="utf-8")
            data = json.loads(content)
            sha = data.get("sha256", "unknown")
            lines.append("### Proof Pack")
            lines.append("")
            lines.append(f"- Path: `{proof_path}`")
            lines.append(f"- SHA-256: `{sha}`")
            lines.append(f"- Transactions: {data.get('total_transactions', '?')}")
            lines.append("")
        except (json.JSONDecodeError, OSError):
            pass

    # Last error
    failed = [tx for tx in state.tx_index if not tx.success]
    if failed:
        last = failed[-1]
        lines.append("### Last Error")
        lines.append("")
        lines.append(f"- Module: `{last.module_id}`")
        lines.append(f"- TXID: `{last.txid}`")
        lines.append(f"- Network: {last.network}")
        lines.append("")

    # Progress
    lines.append("### Progress")
    lines.append("")
    lines.append(f"- Modules completed: {len(state.completed_modules)}")
    total_tx = len(state.tx_index)
    ok_tx = sum(1 for tx in state.tx_index if tx.success)
    lines.append(f"- Transactions: {total_tx} ({ok_tx} ok, {total_tx - ok_tx} failed)")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Attach proof pack if relevant. "
                 "Run `xrpl-lab proof-pack` to generate.*")

    return "\n".join(lines)
