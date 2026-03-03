"""XRPL Lab CLI — learn by doing, prove by artifact."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .actions.verify import verify_tx
from .modules import load_all_modules
from .reporting import write_certificate, write_proof_pack
from .state import (
    ensure_home_dir,
    ensure_workspace,
    load_state,
    reset_state,
    save_state,
)

console = Console()


def _get_transport(dry_run: bool = False):
    """Get the appropriate transport."""
    if dry_run:
        from .transport.dry_run import DryRunTransport

        return DryRunTransport()

    from .transport.xrpl_testnet import XRPLTestnetTransport

    return XRPLTestnetTransport()


def _detect_camp_certificate() -> Path | None:
    """Look for XRPL Camp certificate in common locations."""
    candidates = [
        Path.cwd() / "xrpl_camp_certificate.json",
        Path.cwd() / ".xrpl-camp" / "xrpl_camp_certificate.json",
        Path.home() / ".xrpl-camp" / "xrpl_camp_certificate.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


@click.group()
@click.version_option(version=__version__, prog_name="xrpl-lab")
def main():
    """XRPL Lab — learn by doing, prove by artifact."""


@main.command()
@click.option("--dry-run", is_flag=True, help="Run without network (offline mode)")
def start(dry_run: bool):
    """Guided launcher — pick a module and start learning."""
    console.print()
    console.print(
        Panel(
            f"[bold]XRPL Lab v{__version__}[/]\n"
            "Learn by doing, prove by artifact.",
            border_style="blue",
        )
    )
    console.print()

    ensure_home_dir()
    state = load_state()

    # Check for XRPL Camp certificate
    camp_cert = _detect_camp_certificate()
    if camp_cert:
        console.print("[green]XRPL Camp detected![/] Starting with your existing wallet.")
        try:
            data = json.loads(camp_cert.read_text(encoding="utf-8"))
            camp_address = data.get("address")
            if camp_address and not state.wallet_address:
                console.print(f"  Camp address: [cyan]{camp_address}[/]")
                console.print("  (You can reuse this or create a new wallet)")
        except (json.JSONDecodeError, KeyError):
            pass
        console.print()
    else:
        console.print("[dim]No XRPL Camp certificate found (that's fine).[/]")
        console.print()

    # Network info
    network_label = "dry-run (offline)" if dry_run else "XRPL Testnet"
    console.print(f"Network: [cyan]{network_label}[/]")
    if dry_run:
        console.print("[yellow]Dry-run mode: no real transactions will be submitted.[/]")
    console.print()

    # Show modules
    modules = load_all_modules()
    if not modules:
        console.print("[red]No modules found. Check your installation.[/]")
        sys.exit(1)

    console.print("[bold]Available modules:[/]")
    console.print()

    for mod in modules.values():
        completed = state.is_module_completed(mod.id)
        status = "[green]\u2713[/]" if completed else "[dim]\u25cb[/]"
        console.print(f"  {status} [bold]{mod.id}[/] — {mod.title}  [{mod.level}, ~{mod.time}]")

    console.print()

    # Pick a module
    next_module = None
    for mod in modules.values():
        if not state.is_module_completed(mod.id):
            next_module = mod
            break

    if next_module is None:
        console.print("[green]All modules completed! Run 'xrpl-lab proof-pack' to export.[/]")
        return

    console.print(f"Next up: [bold]{next_module.title}[/]")
    console.print()

    try:
        answer = console.input("Start this module? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\nBye!")
        return

    if answer in ("", "y", "yes"):
        from .runner import run_module

        transport = _get_transport(dry_run)
        asyncio.run(run_module(next_module, transport, dry_run=dry_run))


@main.command("list")
def list_modules():
    """Show all modules with status."""
    modules = load_all_modules()
    state = load_state()

    table = Table(title="XRPL Lab Modules")
    table.add_column("Status", width=4, justify="center")
    table.add_column("ID", style="bold")
    table.add_column("Title")
    table.add_column("Level")
    table.add_column("Time")
    table.add_column("Produces")

    for mod in modules.values():
        completed = state.is_module_completed(mod.id)
        status = "\u2713" if completed else "\u25cb"
        style = "green" if completed else ""
        table.add_row(
            status,
            mod.id,
            mod.title,
            mod.level,
            mod.time,
            ", ".join(mod.produces),
            style=style,
        )

    console.print()
    console.print(table)
    console.print()


@main.command()
@click.argument("module_id")
@click.option("--dry-run", is_flag=True, help="Run without network")
@click.option("--force", is_flag=True, help="Re-run even if already completed")
def run(module_id: str, dry_run: bool, force: bool):
    """Run a specific module by ID."""
    modules = load_all_modules()

    if module_id not in modules:
        console.print(f"[red]Module '{module_id}' not found.[/]")
        console.print(f"Available: {', '.join(modules.keys())}")
        sys.exit(1)

    state = load_state()
    if state.is_module_completed(module_id) and not force:
        console.print(
            f"[yellow]Module '{module_id}' already completed. Use --force to redo.[/]"
        )
        return

    transport = _get_transport(dry_run)

    from .runner import run_module

    asyncio.run(run_module(modules[module_id], transport, dry_run=dry_run))


@main.command()
def status():
    """Show progress, wallet, and recent transactions."""
    state = load_state()
    modules = load_all_modules()

    console.print()
    console.print(Panel("[bold]XRPL Lab Status[/]", border_style="blue"))
    console.print()

    # Wallet
    if state.wallet_address:
        console.print(f"Wallet: [cyan]{state.wallet_address}[/]")
    else:
        console.print("Wallet: [dim]not created yet[/]")

    console.print(f"Network: [cyan]{state.network}[/]")

    # Show env overrides if set
    rpc_override = os.environ.get("XRPL_LAB_RPC_URL")
    faucet_override = os.environ.get("XRPL_LAB_FAUCET_URL")
    if rpc_override:
        console.print(f"RPC endpoint: [yellow]{rpc_override}[/] (override)")
    if faucet_override:
        console.print(f"Faucet: [yellow]{faucet_override}[/] (override)")
    console.print()

    # Module progress
    total = len(modules)
    completed = len(state.completed_modules)
    console.print(f"Modules: {completed}/{total} completed")

    for mod in modules.values():
        done = state.is_module_completed(mod.id)
        icon = "[green]\u2713[/]" if done else "[dim]\u25cb[/]"
        console.print(f"  {icon} {mod.title}")

    # Recent transactions
    if state.tx_index:
        console.print()
        total_tx = len(state.tx_index)
        ok_tx = sum(1 for tx in state.tx_index if tx.success)
        fail_tx = total_tx - ok_tx
        console.print(f"Transactions: {total_tx} total ({ok_tx} ok, {fail_tx} failed)")
        recent = state.tx_index[-5:]
        for tx in reversed(recent):
            status_icon = "[green]\u2713[/]" if tx.success else "[red]\u2717[/]"
            console.print(f"  {status_icon} {tx.txid[:16]}... ({tx.module_id})")

    # Workspace
    ws = Path(".xrpl-lab")
    if ws.exists():
        reports = list((ws / "reports").glob("*.md")) if (ws / "reports").exists() else []
        proofs = list((ws / "proofs").glob("*.json")) if (ws / "proofs").exists() else []
        console.print()
        console.print(f"Workspace: {ws.resolve()}")
        console.print(f"  Reports: {len(reports)}  |  Proofs: {len(proofs)}")

    console.print()


@main.command()
def doctor():
    """Run diagnostic checks on your XRPL Lab environment."""
    from .doctor import run_doctor

    console.print()
    console.print(Panel("[bold]XRPL Lab Doctor[/]", border_style="blue"))
    console.print()

    report = asyncio.run(run_doctor())

    for check in report.checks:
        icon = "[green]\u2713[/]" if check.passed else "[red]\u2717[/]"
        console.print(f"  {icon} [bold]{check.name}[/]")
        if check.detail:
            console.print(f"    {check.detail}")
        if check.hint and not check.passed:
            console.print(f"    [yellow]Hint: {check.hint}[/]")

    console.print()
    if report.all_passed:
        console.print(f"[green]{report.summary} — all good![/]")
    else:
        console.print(f"[yellow]{report.summary}[/]")
    console.print()


@main.command("self-check")
def self_check():
    """Alias for 'doctor' — ecosystem-consistent diagnostic."""
    doctor.callback()


@main.command("proof-pack")
def proof_pack():
    """Generate a shareable proof pack."""
    state = load_state()

    if not state.completed_modules:
        console.print("[yellow]No completed modules yet. Nothing to export.[/]")
        return

    ensure_workspace()
    path = write_proof_pack(state)
    console.print(f"[green]Proof pack written:[/] {path}")


@main.command()
def certificate():
    """Generate a completion certificate."""
    state = load_state()

    if not state.completed_modules:
        console.print("[yellow]No completed modules yet. Nothing to export.[/]")
        return

    ensure_workspace()
    path = write_certificate(state)
    console.print(f"[green]Certificate written:[/] {path}")


@main.command()
def feedback():
    """Generate an issue-ready feedback block (markdown)."""
    from .feedback import generate_feedback

    md = generate_feedback()
    console.print()
    console.print(md)
    console.print()

    # Also copy to clipboard hint
    console.print("[dim]Copy the block above into a GitHub issue or support message.[/]")
    console.print()


@main.command()
@click.option("--keep-wallet", is_flag=True, help="Keep wallet file, only wipe progress")
def reset(keep_wallet: bool):
    """Wipe all local state and workspace (requires confirmation)."""
    console.print()
    console.print("[yellow]This will delete:[/]")
    console.print("  - State: ~/.xrpl-lab/state.json")
    console.print("  - Workspace: ./.xrpl-lab/")
    console.print()
    if keep_wallet:
        console.print("[green]--keep-wallet: Your wallet file will be preserved.[/]")
    else:
        console.print("[red bold]Your wallet file will NOT be deleted.[/]")
        console.print("[dim](Use --keep-wallet to make this explicit.)[/]")
    console.print()

    try:
        confirm = console.input("Type 'RESET' to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\nCancelled.")
        return

    if confirm != "RESET":
        console.print("Cancelled. (Must type exactly: RESET)")
        return

    reset_state()
    console.print("[green]State and workspace cleared.[/]")


# ── Standalone wallet commands ──────────────────────────────────────


@main.group()
def wallet():
    """Wallet management commands."""


@wallet.command("create")
@click.option("--path", type=click.Path(), default=None, help="Custom wallet path")
def wallet_create(path: str | None):
    """Create a new XRPL wallet."""
    from .actions.wallet import create_wallet, save_wallet, wallet_exists

    p = Path(path) if path else None

    if wallet_exists(p):
        console.print("[yellow]Wallet already exists at this location.[/]")
        console.print("Use 'xrpl-lab wallet show' to view it.")
        return

    w = create_wallet()
    saved = save_wallet(w, p)
    console.print("[green]Wallet created![/]")
    console.print(f"  Address: [cyan]{w.address}[/]")
    console.print(f"  Saved to: {saved}")
    console.print()
    console.print("[yellow]Warning: Never share your wallet seed with anyone.[/]")

    # Update state
    state = load_state()
    state.wallet_address = w.address
    state.wallet_path = str(saved)
    save_state(state)


@wallet.command("show")
def wallet_show():
    """Show wallet info (no secrets)."""
    from .actions.wallet import load_wallet, wallet_info

    w = load_wallet()
    if not w:
        console.print("[dim]No wallet found. Run 'xrpl-lab wallet create' first.[/]")
        return

    info = wallet_info(w)
    console.print(f"  Address:    [cyan]{info['address']}[/]")
    console.print(f"  Public key: [dim]{info['public_key']}[/]")


# ── Standalone network commands ─────────────────────────────────────


@main.command()
@click.option("--dry-run", is_flag=True, help="Use dry-run transport")
def fund(dry_run: bool):
    """Fund your wallet from the testnet faucet."""
    state = load_state()
    if not state.wallet_address:
        console.print("[red]No wallet found. Run 'xrpl-lab wallet create' first.[/]")
        return

    transport = _get_transport(dry_run)
    result = asyncio.run(transport.fund_from_faucet(state.wallet_address))

    if result.success:
        console.print(f"[green]Funded![/] Balance: {result.balance} XRP")
    else:
        console.print(f"[red]Funding failed:[/] {result.message}")


@main.command()
@click.option("--to", "destination", required=True, help="Destination address")
@click.option("--amount", required=True, help="Amount in XRP")
@click.option("--memo", default="", help="Optional memo text")
@click.option("--dry-run", is_flag=True)
def send(destination: str, amount: str, memo: str, dry_run: bool):
    """Send a payment transaction."""
    from .actions.wallet import load_wallet

    w = load_wallet()
    if not w:
        console.print("[red]No wallet found. Run 'xrpl-lab wallet create' first.[/]")
        return

    transport = _get_transport(dry_run)
    result = asyncio.run(
        transport.submit_payment(w.seed, destination, amount, memo)
    )

    if result.success:
        console.print("[green]Payment sent![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        console.print(f"  Result: {result.result_code}")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"[red]Payment failed:[/] {result.error}")
        console.print(f"  Result code: {result.result_code}")


@main.command()
@click.option("--tx", "txid", required=True, help="Transaction ID to verify")
@click.option("--dry-run", is_flag=True)
def verify(txid: str, dry_run: bool):
    """Verify a transaction on the ledger."""
    transport = _get_transport(dry_run)
    result = asyncio.run(verify_tx(transport, txid))

    console.print()
    if result.passed:
        console.print("[green]Verification passed![/]")
    else:
        console.print("[red]Verification failed.[/]")

    console.print()
    for check in result.checks:
        console.print(f"  [green]\u2713[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]\u2717[/] {fail}")

    console.print()
    tx = result.tx_info
    console.print(f"  Type: {tx.tx_type}")
    console.print(f"  From: {tx.account}")
    console.print(f"  To: {tx.destination}")
    console.print(f"  Amount: {tx.amount}")
    if tx.memos:
        console.print(f"  Memos: {', '.join(tx.memos)}")
