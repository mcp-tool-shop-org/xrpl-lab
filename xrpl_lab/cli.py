"""XRPL Lab CLI — learn by doing, prove by artifact."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .actions.verify import verify_tx
from .errors import LabException, faucet_rate_limited
from .modules import load_all_modules
from .reporting import write_certificate, write_proof_pack
from .state import (
    LabState,
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


def _detect_camp_wallet() -> Path | None:
    """Look for an XRPL Camp wallet in common locations."""
    candidates = [
        Path.cwd() / ".xrpl-camp" / "wallet.json",
        Path.home() / ".xrpl-camp" / "wallet.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _try_import_camp_wallet(state: LabState) -> bool:
    """Try to import a Camp wallet into Lab state. Returns True if imported."""
    from .actions.wallet import save_wallet, wallet_exists
    from .state import save_state

    # Already have a lab wallet — don't overwrite
    if wallet_exists():
        return False

    camp_path = _detect_camp_wallet()
    if not camp_path:
        return False

    try:
        data = json.loads(camp_path.read_text(encoding="utf-8"))
        seed = data.get("seed")
        if not seed:
            return False

        from xrpl.wallet import Wallet as XWallet
        wallet = XWallet.from_seed(seed)

        path = save_wallet(wallet)
        state.wallet_address = wallet.address
        state.wallet_path = str(path)
        save_state(state)
        return True
    except (json.JSONDecodeError, KeyError, ValueError):
        return False


@click.group()
@click.version_option(version=__version__, prog_name="xrpl-lab")
def main():
    """XRPL Lab — learn by doing, prove by artifact.

    Quick start:

    \b
        xrpl-lab start           Interactive guided tour
        xrpl-lab list            Show all modules
        xrpl-lab run MODULE_ID   Run a specific module
        xrpl-lab proof verify    Verify a proof pack
        xrpl-lab cert-verify     Verify a certificate
        xrpl-lab doctor          Check your setup
        xrpl-lab serve           Start the web dashboard
    """


@main.command()
@click.option(
    "--dry-run", is_flag=True,
    help=(
        "Offline sandbox mode: transactions are simulated (won't execute on "
        "testnet), but state and progress are saved locally. Use this to "
        "learn without network access, or to repeat modules without "
        "consuming testnet faucet requests."
    ),
)
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

    # Check for XRPL Camp continuity
    camp_cert = _detect_camp_certificate()
    if camp_cert:
        try:
            data = json.loads(camp_cert.read_text(encoding="utf-8"))
            camp_address = data.get("address", "")
        except (json.JSONDecodeError, KeyError):
            camp_address = ""

        if not state.wallet_address and _try_import_camp_wallet(state):
            state = load_state()
            console.print(
                "[green]XRPL Camp wallet imported.[/] "
                "Continuing with the same identity."
            )
            console.print(f"  Address: [cyan]{escape(state.wallet_address or '')}[/]")
        elif camp_address:
            console.print(
                f"[green]XRPL Camp certificate found.[/] "
                f"Camp address: [cyan]{escape(camp_address)}[/]"
            )
            if state.wallet_address and state.wallet_address != camp_address:
                console.print(
                    "  [dim]Lab is using a different wallet. "
                    "Run 'xrpl-lab reset' to start fresh if you want to re-import.[/dim]"
                )
        console.print()
    else:
        console.print("[dim]No XRPL Camp certificate found (that's fine).[/]")
        console.print()

    # Network info
    network_label = "dry-run (offline sandbox)" if dry_run else "XRPL Testnet"
    console.print(f"Network: [cyan]{network_label}[/]")
    if dry_run:
        console.print(
            "[yellow]Offline sandbox: transactions are simulated, "
            "but wallets, state, and reports are saved locally.[/]"
        )
    console.print()

    # Show modules
    modules = load_all_modules()
    if not modules:
        console.print("[red]No modules found. Check your installation.[/]")
        sys.exit(1)

    console.print("[bold]Available modules:[/]")
    console.print()

    # F-BACKEND-D-003: icon + color + TEXT label so color-blind
    # facilitators can distinguish completed from todo modules in the
    # start launcher without relying on hue alone.
    for mod in modules.values():
        completed = state.is_module_completed(mod.id)
        status = "[green]✓ done[/]" if completed else "[dim]◌ todo[/]"
        sandbox_tag = " [yellow](dry-run only)[/]" if mod.dry_run_only else ""
        console.print(
            f"  {status} [bold]{mod.id}[/] — {mod.title}"
            f"  [{mod.level}, ~{mod.time}]{sandbox_tag}"
        )

    console.print()

    # Pick next module using curriculum graph
    from .curriculum import build_graph

    graph = build_graph(modules)
    completed = {m.module_id for m in state.completed_modules}
    next_id = graph.next_module(completed)

    if next_id is None:
        console.print("[green]All modules completed! Run 'xrpl-lab proof-pack' to export.[/]")
        return

    next_module = modules[next_id]
    console.print(f"Next up: [bold]{next_module.title}[/]")
    if next_module.summary:
        console.print(f"  [dim]{next_module.summary}[/]")
    console.print(
        f"  Track: [cyan]{next_module.track}[/]  |  "
        f"Mode: [cyan]{next_module.mode}[/]  |  "
        f"~{next_module.time}"
    )
    if next_module.requires:
        console.print(f"  Requires: {', '.join(next_module.requires)}")
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
    """Show all modules with status, track, and progression info."""
    from .curriculum import build_graph

    modules = load_all_modules()
    state = load_state()
    graph = build_graph(modules)
    ordered = graph.canonical_order()
    completed = {m.module_id for m in state.completed_modules}
    next_id = graph.next_module(completed)

    # F-BACKEND-D-001: expand=True so Title (ratio=2) actually consumes
    # the leftover horizontal budget instead of auto-shrinking; merge
    # Track+ID into one stacked column so Title gets enough room to
    # render short titles ("Receipt Literacy", "Failure Literacy") on
    # one line at the common 80-char projector terminal width.
    # Information density is preserved (track on top, ID below) and the
    # Mode column ("testnet" / "dry-run") stays in view for facilitators
    # scanning at a glance.
    table = Table(title="XRPL Lab Modules", expand=True)
    table.add_column("", width=4, justify="center")
    table.add_column("Track / ID", style="dim", ratio=1)
    table.add_column("Title", ratio=2)
    table.add_column("Level", ratio=1)
    table.add_column("Time", ratio=1)
    table.add_column("Mode", ratio=1)

    # F-BACKEND-D-003: shape-distinct icons (✓ check, → arrow, · dot) so
    # next-up vs todo is distinguishable WITHOUT color. Previously cyan ▸
    # and dim ◌ were both circle-like and indistinguishable for color-blind
    # facilitators. The narrow icon column can't fit DONE/ACTIVE/TODO text
    # — distinct shapes carry the semantic instead.
    for mid in ordered:
        mod = modules[mid]
        done = state.is_module_completed(mid)
        is_next = mid == next_id
        if done:
            icon = "✓"
            style = "green"
        elif is_next:
            icon = "→"
            style = "bold cyan"
        else:
            icon = "·"
            style = ""
        # Track / ID combined cell: "track\n[bold]id[/]" — track on top,
        # id (the load-bearing identifier for `xrpl-lab run <id>`) below.
        track_id_cell = f"{mod.track}\n[bold]{mod.id}[/]"
        table.add_row(
            icon,
            track_id_cell,
            mod.title,
            mod.level,
            mod.time,
            mod.mode,
            style=style,
        )

    console.print()
    console.print(table)
    console.print()


@main.command()
@click.argument("module_id")
@click.option(
    "--dry-run", is_flag=True,
    help=(
        "Offline sandbox mode: transactions are simulated (won't execute on "
        "testnet), but state and progress are saved locally. Use this to "
        "learn without network access, or to repeat modules without "
        "consuming testnet faucet requests."
    ),
)
@click.option(
    "--force", is_flag=True,
    help=(
        "Re-run a completed module — useful for practice or retrying with "
        "different values"
    ),
)
def run(module_id: str, dry_run: bool, force: bool):
    """Run a specific module by ID (e.g., xrpl-lab run receipt_literacy)."""
    modules = load_all_modules()

    if module_id not in modules:
        console.print(f"[red]Module '{module_id}' not found.[/]")
        console.print(f"Available: {', '.join(modules.keys())}")
        sys.exit(1)

    state = load_state()
    if state.is_module_completed(module_id) and not force:
        console.print(
            f"[yellow]Module '{module_id}' already completed. "
            f"Run with --force to redo (progress and reports update; previous "
            f"transaction IDs are preserved in the proof pack).[/]"
        )
        return

    transport = _get_transport(dry_run)

    from .runner import run_module

    asyncio.run(run_module(modules[module_id], transport, dry_run=dry_run, force=force))


@main.command()
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def status(json_output: bool):
    """Show progress, wallet, curriculum position, and blockers."""
    from .workshop import get_learner_status

    ls = get_learner_status()

    if json_output:
        print(json.dumps(ls.to_dict(), indent=2))
        return

    console.print()
    console.print(Panel("[bold]Status[/]", border_style="blue"))
    console.print()

    # Wallet + network
    if ls.wallet_address:
        console.print(f"Wallet: [cyan]{ls.wallet_address}[/]")
    else:
        console.print("Wallet: [dim]not created yet[/]")
    console.print(f"Network: [cyan]{ls.network}[/]")

    rpc_override = os.environ.get("XRPL_LAB_RPC_URL")
    faucet_override = os.environ.get("XRPL_LAB_FAUCET_URL")
    if rpc_override:
        console.print(f"RPC endpoint: [yellow]{rpc_override}[/] (override)")
    if faucet_override:
        console.print(f"Faucet: [yellow]{faucet_override}[/] (override)")
    console.print()

    # Curriculum position
    console.print(f"Progress: {ls.completed_count}/{ls.total_modules} modules")
    if ls.current_module:
        console.print(
            f"Next up: [bold]{ls.current_module}[/]"
            f"  [dim]({ls.current_track}, {ls.current_mode})[/]"
        )
    else:
        console.print("[green]All modules completed![/]")

    # Blockers
    # F-BACKEND-D-002: blank line before Blockers always (not just when
    # present) so facilitators see a consistent rhythm scanning multiple
    # learners' status output side by side.
    console.print()
    if ls.blockers:
        for b in ls.blockers:
            if ls.is_blocked:
                console.print(f"  [red]✗ {b}[/]")
            else:
                console.print(f"  [yellow]⚠ {b}[/]")

    # Track progress
    # F-BACKEND-D-002: blank line before Tracks summary for breathing room.
    console.print()
    # F-BACKEND-D-003: icon + color + TEXT label (DONE/ACTIVE/TODO) so
    # color-blind facilitators (protanopia/deuteranopia) can distinguish
    # in-progress from not-started without relying on hue alone. Matches
    # the doctor.py icon+color+text pattern.
    for tp in ls.track_progress:
        if tp.total == 0:
            continue
        if tp.is_complete:
            console.print(
                f"  [green]✓ DONE[/]   {tp.track}: {tp.done}/{tp.total}"
            )
        elif tp.done > 0:
            console.print(
                f"  [cyan]▸ ACTIVE[/] {tp.track}: {tp.done}/{tp.total}"
            )
        else:
            console.print(
                f"  [dim]◌ TODO[/]   {tp.track}: {tp.done}/{tp.total}"
            )

    # Activity
    if ls.last_module:
        console.print()
        console.print(f"Last completed: [dim]{ls.last_module}[/]")
        if ls.last_activity:
            console.print(f"  [dim]{ls.last_activity}[/]")

    # Transactions
    if ls.total_transactions > 0:
        ok = ls.total_transactions - ls.failed_transactions
        console.print()
        console.print(
            f"Transactions: {ls.total_transactions} "
            f"({ok} ok, {ls.failed_transactions} failed)"
        )

    # Artifacts
    console.print()
    parts = []
    if ls.report_count:
        parts.append(f"Reports: {ls.report_count}")
    parts.append(f"Proof pack: {'yes' if ls.has_proof_pack else 'no'}")
    parts.append(f"Certificate: {'yes' if ls.has_certificate else 'no'}")
    console.print("  |  ".join(parts))

    console.print()


def _run_doctor_and_display():
    """Shared logic for doctor and self-check commands."""
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
            console.print(f"    [yellow]{check.hint}[/]")

    console.print()
    if report.all_passed:
        console.print(f"[green]{report.summary} — all good.[/]")
    else:
        console.print(f"[yellow]{report.summary}[/]")
    console.print()


@main.command()
def doctor():
    """Run diagnostic checks on your XRPL Lab environment."""
    _run_doctor_and_display()


@main.command("self-check")
def self_check():
    """Alias for 'doctor' — ecosystem-consistent diagnostic."""
    _run_doctor_and_display()


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


# ---------------------------------------------------------------------------
# Proof subgroup
# ---------------------------------------------------------------------------


@main.group()
def proof():
    """Proof pack commands: generate and verify."""


@proof.command("generate")
def proof_generate():
    """Generate a shareable proof pack (same as proof-pack)."""
    state = load_state()

    if not state.completed_modules:
        console.print("[yellow]No completed modules yet. Nothing to export.[/]")
        return

    ensure_workspace()
    path = write_proof_pack(state)
    console.print(f"[green]Proof pack written:[/] {path}")


@proof.command("verify")
@click.argument("file", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def proof_verify(file: str, json_output: bool):
    """Verify a proof pack's integrity."""
    from .reporting import verify_proof_pack

    path = Path(file)
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        if json_output:
            print(json.dumps({"valid": False, "message": f"Invalid JSON: {e}"}))
        else:
            console.print(f"[red]Invalid JSON: {e}[/]")
        sys.exit(1)

    valid, message = verify_proof_pack(pack)

    if json_output:
        result = {
            "valid": valid,
            "file": str(path),
            "version": pack.get("version", ""),
            "address": pack.get("address", ""),
            "network": pack.get("network", ""),
            "modules_completed": len(pack.get("completed_modules", [])),
            "total_transactions": pack.get("total_transactions", 0),
            "sha256": pack.get("sha256", ""),
            "message": message,
        }
        print(json.dumps(result, indent=2))
    else:
        if valid:
            console.print("\n  [green]✅ PASS[/] — Proof pack integrity verified.\n")
        else:
            console.print(f"\n  [red]❌ FAIL[/] — {message}\n")

        console.print(f"  [bold]File:[/]         {path}")
        console.print(f"  [bold]Version:[/]      {pack.get('version', '?')}")
        console.print(f"  [bold]Address:[/]      {pack.get('address', '?')}")
        console.print(f"  [bold]Network:[/]      {pack.get('network', '?')}")
        console.print(f"  [bold]Modules:[/]      {len(pack.get('completed_modules', []))}")
        console.print(f"  [bold]Transactions:[/] {pack.get('total_transactions', 0)}")
        console.print(f"  [bold]SHA-256:[/]      {pack.get('sha256', 'none')}")
        console.print()

    if not valid:
        sys.exit(1)


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


# ---------------------------------------------------------------------------
# Certificate verify
# ---------------------------------------------------------------------------


@main.command("cert-verify")
@click.argument("file", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
def cert_verify(file: str, json_output: bool):
    """Verify a certificate's integrity."""
    from .reporting import verify_certificate

    path = Path(file)
    try:
        cert = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        if json_output:
            print(json.dumps({"valid": False, "message": f"Invalid JSON: {e}"}))
        else:
            console.print(f"[red]Invalid JSON: {e}[/]")
        sys.exit(1)

    valid, message = verify_certificate(cert)

    if json_output:
        result = {
            "valid": valid,
            "file": str(path),
            "version": cert.get("version", ""),
            "address": cert.get("address", ""),
            "network": cert.get("network", ""),
            "modules_completed": cert.get("total_modules", 0),
            "total_transactions": cert.get("total_transactions", 0),
            "sha256": cert.get("sha256", ""),
            "message": message,
        }
        print(json.dumps(result, indent=2))
    else:
        if valid:
            console.print("\n  [green]✅ PASS[/] — Certificate integrity verified.\n")
        else:
            console.print(f"\n  [red]❌ FAIL[/] — {message}\n")

        console.print(f"  [bold]File:[/]         {path}")
        console.print(f"  [bold]Version:[/]      {cert.get('version', '?')}")
        console.print(f"  [bold]Address:[/]      {cert.get('address', '?')}")
        console.print(f"  [bold]Network:[/]      {cert.get('network', '?')}")
        console.print(f"  [bold]Modules:[/]      {cert.get('total_modules', 0)}")
        console.print(f"  [bold]Transactions:[/] {cert.get('total_transactions', 0)}")
        console.print(f"  [bold]SHA-256:[/]      {cert.get('sha256', 'none')}")
        console.print()

    if not valid:
        sys.exit(1)


@main.command()
def feedback():
    """Generate an issue-ready feedback block (markdown)."""
    from .workshop import generate_support_bundle

    bundle = generate_support_bundle()
    md = bundle.to_markdown()
    console.print()
    console.print(md)
    console.print()
    console.print("[dim]Copy the block above into a GitHub issue or support message.[/]")
    console.print()


@main.command("support-bundle")
@click.option("--json", "json_output", is_flag=True, help="JSON output instead of markdown")
@click.option("--verify", "verify_path", type=click.Path(exists=True),
              help="Verify an existing support bundle file")
def support_bundle(json_output: bool, verify_path: str | None):
    """Generate or verify a support bundle for facilitator handoff."""
    from .workshop import generate_support_bundle, verify_support_bundle

    if verify_path:
        raw = Path(verify_path).read_text(encoding="utf-8")
        valid, message = verify_support_bundle(raw)
        if json_output:
            print(json.dumps({"valid": valid, "message": message}))
        else:
            if valid:
                console.print(f"\n  [green]✅ PASS[/] — {message}\n")
            else:
                console.print(f"\n  [red]❌ FAIL[/] — {message}\n")
        if not valid:
            sys.exit(1)
        return

    bundle = generate_support_bundle()

    if json_output:
        print(bundle.to_json())
    else:
        console.print()
        console.print(bundle.to_markdown())
        console.print()


@main.command("tracks")
def tracks():
    """Show track-level completion summaries."""
    from .workshop import get_track_summaries

    summaries = get_track_summaries()

    console.print()
    console.print(Panel("[bold]Tracks[/]", border_style="blue"))
    console.print()

    # F-BACKEND-D-003: icon + color + TEXT label (DONE/ACTIVE/TODO) so
    # color-blind facilitators can distinguish track state without hue.
    # F-BACKEND-D-005: drop redundant "(none)" mode-breakdown when no
    # modules are done; keep breakdown when at least one is complete (so
    # mixed/testnet/dry-run signal stays visible).
    for ts in summaries:
        done_count = len(ts.completed_modules)
        total_count = done_count + len(ts.remaining_modules)
        if ts.is_complete:
            label = "[green]✓ DONE[/]  "
        elif ts.completed_modules:
            label = "[cyan]▸ ACTIVE[/]"
        else:
            label = "[dim]◌ TODO[/]  "

        # Suppress (none) when no modules completed; show breakdown otherwise.
        breakdown_suffix = (
            "" if done_count == 0 else f"  [dim]({ts.mode_breakdown})[/]"
        )

        console.print(
            f"  {label} [bold]{ts.track}[/]"
            f"  {done_count}/{total_count}"
            f"{breakdown_suffix}"
        )

        if ts.completed_modules:
            for mid in ts.completed_modules:
                console.print(f"      [green]✓ done[/]  {mid}")
        if ts.remaining_modules:
            for mid in ts.remaining_modules:
                console.print(f"      [dim]◌ todo[/]  {mid}")

        if ts.skills_practiced:
            console.print(f"      Skills: {', '.join(ts.skills_practiced[:5])}")
        if ts.transaction_count:
            console.print(f"      Transactions: {ts.transaction_count}")
        if ts.artifacts:
            console.print(f"      Reports: {', '.join(ts.artifacts[:3])}")
        console.print()

    console.print()


@main.command()
def recovery():
    """Diagnose stuck states and show recovery commands."""
    from .workshop import diagnose_recovery

    hints = diagnose_recovery()

    console.print()
    if not hints:
        console.print("[green]No known blockers found.[/]")
        console.print(
            "Next: run [cyan]xrpl-lab start[/] to see your next module, or "
            "[cyan]xrpl-lab status[/] for detailed progress."
        )
        console.print()
        return

    console.print(Panel("[bold]Recovery[/]", border_style="yellow"))
    console.print()

    for h in hints:
        console.print(f"  [yellow]⚠[/] {h.situation}")
        console.print(f"    [cyan]{h.command}[/]")
        console.print(f"    [dim]{h.explanation}[/]")
        console.print()

    console.print()


@main.command()
@click.option(
    "--txids", "txids_path", required=True,
    type=click.Path(exists=True), help="File with one txid per line",
)
@click.option(
    "--expect", "expect_path", default=None,
    type=click.Path(exists=True), help="Expectations JSON file",
)
@click.option("--csv", "csv_path", default=None, help="Write CSV report to this path")
@click.option("--md", "md_path", default=None, help="Write markdown report to this path")
@click.option("--dry-run", is_flag=True, help="Offline sandbox")
@click.option("--no-pack", is_flag=True, help="Skip writing audit pack JSON")
def audit(txids_path: str, expect_path: str | None, csv_path: str | None,
          md_path: str | None, dry_run: bool, no_pack: bool):
    """Batch verify transactions and produce an audit report."""
    from .audit import (
        AuditConfig,
        parse_expectations,
        parse_txids_file,
        run_audit,
        write_audit_pack,
        write_audit_report_csv,
        write_audit_report_md,
    )

    # Parse inputs
    txids = parse_txids_file(Path(txids_path))
    if not txids:
        console.print("[yellow]No txids found in file.[/]")
        return

    config = parse_expectations(Path(expect_path)) if expect_path else AuditConfig()

    transport = _get_transport(dry_run)
    report = asyncio.run(run_audit(transport, txids, config))

    # Console summary
    console.print()
    console.print(Panel("[bold]XRPL Lab Audit[/]", border_style="blue"))
    console.print()
    console.print(f"  Checked: [bold]{report.total}[/] transactions")
    console.print(f"  Pass:    [green]{report.passed}[/]")
    console.print(f"  Fail:    [red]{report.failed}[/]")
    console.print(f"  Missing: [yellow]{report.not_found}[/]")
    console.print()

    # Failure reasons
    summary = report.failure_summary()
    if summary:
        console.print("  [bold]Top failure reasons:[/]")
        for reason, count in summary.items():
            console.print(f"    {reason}: {count}")
        console.print()

    # Write reports
    ensure_workspace()
    ts = time.strftime("%Y%m%d_%H%M%S")

    # Markdown report (always write, or to custom path)
    md_out = Path(md_path) if md_path else Path(f".xrpl-lab/reports/audit_{ts}.md")
    write_audit_report_md(report, md_out)
    console.print(f"  Report:     [green]{md_out}[/]")

    # CSV report (optional)
    if csv_path:
        csv_out = Path(csv_path)
        write_audit_report_csv(report, csv_out)
        console.print(f"  CSV:        [green]{csv_out}[/]")

    # Audit pack (skipped when --no-pack is passed)
    if not no_pack:
        pack_out = Path(f".xrpl-lab/proofs/audit_pack_{ts}.json")
        write_audit_pack(report, pack_out)
        console.print(f"  Audit pack: [green]{pack_out}[/]")
    console.print()


@main.command("last-run")
def last_run():
    """Show last module run info and the audit command to verify it."""
    ws = Path(".xrpl-lab")
    meta_path = ws / "last_run_meta.json"
    txids_path = ws / "last_run_txids.txt"

    if not meta_path.exists():
        console.print("[yellow]No last run found. Run a strategy module first.[/]")
        return

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        console.print("[yellow]Last run data is unreadable. Try running a module first.[/]")
        return

    console.print()
    console.print(Panel("[bold]Last Run[/]", border_style="blue"))
    console.print()
    console.print(f"  Module:    [bold]{meta.get('module', '?')}[/]")
    console.print(f"  Run ID:    [cyan]{meta.get('run_id', '?')}[/]")
    console.print(f"  Timestamp: {meta.get('timestamp', '?')}")
    console.print(f"  TX count:  [green]{meta.get('txid_count', 0)}[/]")

    preset = meta.get("preset", "")
    if preset:
        console.print(f"  Preset:    {preset}")

    console.print()
    console.print("[bold]Verify with:[/]")

    cmd = f"  xrpl-lab audit --txids {txids_path}"
    if preset:
        preset_file = f"presets/{preset}.json"
        if Path(preset_file).exists():
            cmd += f" --expect {preset_file}"
    console.print(f"  [cyan]{cmd}[/]")
    console.print()


@main.command()
@click.option('--port', default=8321, help='API server port')
@click.option('--host', default='127.0.0.1', help='API server host')
@click.option('--dry-run', is_flag=True, help='Offline sandbox for all operations')
def serve(port: int, host: str, dry_run: bool):
    """Start the XRPL Lab web dashboard and API server.

API docs available at http://localhost:{port}/docs after starting.
"""
    import uvicorn

    from .server import create_app

    console.print(Panel.fit(
        f"[bold]XRPL Lab Web Dashboard[/]\n"
        f"API: [cyan]http://{host}:{port}[/]\n"
        f"Dashboard: [cyan]http://localhost:4321/xrpl-lab/app/[/]\n"
        f"Mode: [yellow]{'Dry Run' if dry_run else 'Testnet'}[/]",
        title="serve"
    ))
    console.print("[dim]Start the Astro dev server separately: cd site && npm run dev[/]")

    app = create_app(dry_run=dry_run)
    uvicorn.run(app, host=host, port=port)


# ---------------------------------------------------------------------------
# Cohort + session-export — workshop facilitator commands
# (F-BACKEND-FT-001 + F-BACKEND-FT-002)
# ---------------------------------------------------------------------------


@main.command("cohort-status")
@click.option(
    "--dir", "cohort_dir",
    default=".", type=click.Path(exists=True, file_okay=False),
    help="Cohort directory containing per-learner subdirectories.",
)
@click.option(
    "--format", "fmt",
    type=click.Choice(["table", "json"]), default="table",
    help="Output format. Use json for scripting.",
)
def cohort_status(cohort_dir: str, fmt: str):
    """Aggregate per-learner status across a cohort directory.

    Walks ``COHORT_DIR/<learner>/.xrpl-lab/state.json`` for each
    subdir; surfaces completed_count, current module, blockers, and
    last activity in one row per learner. Subdirs without state.json
    are skipped silently. A corrupt state.json yields a warning row
    but never aborts the aggregation — facilitators need the partial
    view, not a hard fail.

    Single-shared-workspace mode: if ``COHORT_DIR/.xrpl-lab/state.json``
    exists, reports it as a single row.
    """
    from .state import load_state_from_path

    cohort_path = Path(cohort_dir)
    rows: list[dict] = []
    warnings: list[tuple[str, str]] = []

    # Single-shared-workspace mode: cohort dir itself has the state.
    if (cohort_path / ".xrpl-lab" / "state.json").exists():
        candidates = [cohort_path]
    else:
        candidates = sorted(p for p in cohort_path.iterdir() if p.is_dir())

    for sub in candidates:
        state_file = sub / ".xrpl-lab" / "state.json"
        if not state_file.exists():
            continue
        learner_id = sub.name if sub != cohort_path else "_cohort"
        try:
            state = load_state_from_path(state_file)
        except (FileNotFoundError, ValueError) as e:
            warnings.append((learner_id, str(e)))
            continue
        # Reuse status math: derive minimal facilitator view from the
        # raw state, mirroring fields exposed by `xrpl-lab status --json`.
        completed_ids = [m.module_id for m in state.completed_modules]
        last_activity_ts = max(
            (m.completed_at for m in state.completed_modules), default=None,
        )
        last_activity_iso = (
            datetime.fromtimestamp(last_activity_ts, tz=UTC).isoformat()
            if last_activity_ts else None
        )
        # Current module + blockers via workshop helper
        from .workshop import get_learner_status
        ls = get_learner_status(state)
        rows.append({
            "learner_id": learner_id,
            "wallet_address": state.wallet_address,
            "network": state.network,
            "completed_count": len(completed_ids),
            "total_modules": ls.total_modules,
            "current_module": ls.current_module,
            "blockers": ls.blockers,
            "last_activity": last_activity_iso,
        })

    # Sort by learner-id alphabetically (deterministic)
    rows.sort(key=lambda r: r["learner_id"])

    if fmt == "json":
        out = {
            "cohort_dir": str(cohort_path.resolve()),
            "learners": rows,
            "warnings": [
                {"learner_id": lid, "error": err} for lid, err in warnings
            ],
        }
        print(json.dumps(out, indent=2))
        return

    # Rich table for facilitator at-a-glance
    table = Table(title=f"Cohort Status — {cohort_path}", expand=True)
    table.add_column("Learner", style="bold")
    table.add_column("Progress")
    table.add_column("Current")
    table.add_column("Blockers")
    table.add_column("Last activity", style="dim")

    for row in rows:
        progress = f"{row['completed_count']}/{row['total_modules']}"
        current = row["current_module"] or "(complete)"
        blockers = "; ".join(row["blockers"]) if row["blockers"] else "-"
        last = row["last_activity"] or "-"
        table.add_row(row["learner_id"], progress, current, blockers, last)

    for lid, err in warnings:
        table.add_row(
            f"[yellow]{lid}[/]",
            "[yellow]?[/]",
            "[yellow]?[/]",
            f"[yellow]warning: {err[:60]}[/]",
            "-",
        )

    console.print()
    if not rows and not warnings:
        console.print(
            f"[yellow]No learner workspaces found under {cohort_path}.[/] "
            "Each learner subdir should contain .xrpl-lab/state.json."
        )
        console.print()
        return
    console.print(table)
    console.print()
    if warnings:
        console.print(
            f"[yellow]{len(warnings)} learner(s) had unreadable state — "
            "see warning rows.[/]"
        )
        console.print()


@main.command("session-export")
@click.option(
    "--dir", "cohort_dir",
    default=".", type=click.Path(exists=True, file_okay=False),
    help="Cohort directory containing per-learner subdirectories.",
)
@click.option(
    "--format", "fmt",
    type=click.Choice(["tar.gz", "zip"]), default="tar.gz",
    help="Archive format.",
)
@click.option(
    "--outfile", default=None, type=click.Path(),
    help="Output archive path (default: xrpl_lab_session_<timestamp>.<fmt>).",
)
def session_export(cohort_dir: str, fmt: str, outfile: str | None):
    """Archive all learner artifacts with a SHA-256 manifest.

    Walks ``COHORT_DIR`` for per-learner workspaces and packs each
    learner's proofs/, reports/, audit_packs/, certificates/ into a
    single archive. wallet.json, state.json, and doctor.log are
    NEVER archived (workshop threat-model line). MANIFEST.json at the
    archive root lists every included file with its source SHA-256.
    """
    from .reporting import write_session_export

    if outfile is None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        ext = "tar.gz" if fmt == "tar.gz" else "zip"
        outfile = f"xrpl_lab_session_{ts}.{ext}"

    summary = write_session_export(
        cohort_dir=Path(cohort_dir),
        outfile=Path(outfile),
        archive_format=fmt,
    )

    console.print()
    if summary["learners"] == 0:
        console.print(
            f"[yellow]No learner workspaces found under {cohort_dir}.[/] "
            "Archive written with empty MANIFEST.json — nothing to share."
        )
    else:
        console.print(
            f"[green]Exported {summary['learners']} learner(s), "
            f"{summary['files']} file(s), {summary['bytes']} bytes "
            f"→ {summary['outfile']}[/]"
        )
    console.print()


@main.command()
@click.option(
    "--keep-wallet", is_flag=True,
    help="Keep wallet file, only wipe progress",
)
@click.option(
    "--module", "module_id", default=None,
    help=(
        "Granular reset: remove only the specified module from "
        "completed_modules + clear its workspace artifacts. Preserves "
        "wallet and all other modules' state. Workshop-day workflow "
        "for a stuck learner who needs to retry one module without "
        "losing the rest."
    ),
)
@click.option(
    "--confirm", "skip_confirm", is_flag=True,
    help="Skip the confirmation prompt (granular --module mode only).",
)
def reset(keep_wallet: bool, module_id: str | None, skip_confirm: bool):
    """Wipe all local state and workspace (requires confirmation).

    With --module MODULE_ID, removes only that module from completed
    state and clears its workspace artifacts. Preserves wallet,
    doctor.log, audit packs, and all other modules.
    """
    # Granular path: --module MODULE_ID
    if module_id:
        from .state import reset_module

        # Validate against the loaded module catalog so unknown IDs
        # error before any state mutation. Also catches typos before
        # the user is asked to confirm.
        modules = load_all_modules()
        if module_id not in modules:
            console.print(
                f"[red]Unknown module ID: '{module_id}'.[/]"
            )
            console.print(
                f"  Available: {', '.join(sorted(modules.keys()))}"
            )
            sys.exit(2)

        # Confirm if not auto-confirmed
        if not skip_confirm:
            console.print()
            console.print(
                f"[yellow]This will reset module '{module_id}':[/]"
            )
            console.print(
                "  - Remove it from completed_modules"
            )
            console.print(
                "  - Clear its tx_index records + workspace report"
            )
            console.print(
                "[green]Wallet + other modules + audit packs preserved.[/]"
            )
            console.print()
            try:
                confirm = console.input(
                    f"Type '{module_id}' to confirm: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\nCancelled.")
                return
            if confirm != module_id:
                console.print(
                    f"Cancelled. (Must type exactly: {module_id})"
                )
                return

        try:
            summary = reset_module(module_id)
        except ValueError as e:
            console.print(f"[yellow]{e}[/]")
            sys.exit(1)
        console.print(
            f"[green]Module '{module_id}' reset.[/] "
            f"Cleared {summary['tx_records_cleared']} tx record(s); "
            f"report removed: {summary['report_removed']}."
        )
        return

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
@click.option("--dry-run", is_flag=True, help="Offline sandbox")
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
        return
    # F-BRIDGE-PH8-001: structured ``code`` drives richer CLI behavior than
    # printing ``message`` alone — the rate-limited path gets a dedicated
    # banner (clock-cued waiting) + recovery hint + a distinct exit code
    # so scripts can branch on it. Other failure modes keep their generic
    # treatment (no exit code change to preserve existing call-site
    # behavior).
    if getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        err = faucet_rate_limited()
        console.print(f"[yellow]{err.message}[/]")
        console.print(f"  [dim]{err.hint}[/]")
        raise SystemExit(LabException(err).exit_code)
    console.print(f"[red]Funding failed:[/] {result.message}")


@main.command()
@click.option("--to", "destination", required=True, help="Destination address")
@click.option("--amount", required=True, help="Amount in XRP")
@click.option("--memo", default="", help="Optional memo text")
@click.option("--dry-run", is_flag=True)
def send(destination: str, amount: str, memo: str, dry_run: bool):
    """Send a payment transaction."""
    from .actions.wallet import load_wallet

    # Validate amount
    try:
        amount_f = Decimal(amount)
    except (ValueError, InvalidOperation):
        console.print("[red]Invalid amount — must be a number[/]")
        raise SystemExit(2) from None
    if amount_f <= 0:
        console.print("[red]Amount must be positive[/]")
        raise SystemExit(2)

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
    if result.checks or result.failures:
        for check in result.checks:
            console.print(f"  [green]\u2713[/] {check}")
        for fail in result.failures:
            console.print(f"  [red]\u2717[/] {fail}")
    else:
        console.print("  [dim]No checks or failures recorded for this transaction.[/]")

    console.print()
    tx = result.tx_info
    console.print(f"  Type: {tx.tx_type}")
    console.print(f"  From: {tx.account}")
    if tx.destination:
        console.print(f"  To: {tx.destination}")
    console.print(f"  Amount: {tx.amount}")
    if tx.memos:
        console.print(f"  Memos: {', '.join(tx.memos)}")


# ── Module group: scaffolding + lint helpers ────────────────────────


@main.group("module")
def module_group():
    """Module authoring helpers (init scaffolder)."""


@module_group.command("init")
@click.option("--id", "module_id", required=True, help="snake_case module ID")
@click.option(
    "--track", required=True,
    type=click.Choice(["foundations", "dex", "reserves", "audit", "amm"]),
    help="Curriculum track this module belongs to",
)
@click.option("--title", required=True, help="Human-readable module title")
@click.option("--time", required=True, help='Estimated duration (e.g., "20 min")')
@click.option(
    "--requires", default="",
    help="Comma-separated list of prerequisite module IDs (optional)",
)
@click.option(
    "--level",
    type=click.Choice(["beginner", "intermediate", "advanced"]),
    default="beginner",
    help="Difficulty level (default: beginner)",
)
@click.option(
    "--mode", type=click.Choice(["testnet", "dry-run"]), default="testnet",
    help="Default execution mode",
)
@click.option(
    "--outfile", default=None, type=click.Path(),
    help="Output path (default: ./<module_id>.md in current directory)",
)
def module_init(
    module_id: str, track: str, title: str, time: str,
    requires: str, level: str, mode: str, outfile: str | None,
):
    """Generate a lint-passing module skeleton.

    F-BACKEND-FT-006: bootstraps community contributions and custom
    workshop modules. Generates a markdown file with valid frontmatter,
    three step skeleton sections, and action comment hints. Auto-runs
    the linter on the result so contributors see a green pass before
    they edit forward. Pairs with the new CONTRIBUTING.md.
    """
    import re

    from .linter import lint_module_file
    from .modules import render_module_skeleton

    # Validate module ID — snake_case, no spaces
    if not re.match(r"^[a-z][a-z0-9_]*$", module_id):
        console.print(
            f"[red]Invalid module ID: '{module_id}'.[/] "
            "Must be snake_case (lowercase letters, digits, underscores; "
            "must start with a letter)."
        )
        sys.exit(2)

    # Reject duplicates against the loaded module catalog
    existing = load_all_modules()
    if module_id in existing:
        console.print(
            f"[red]Module ID '{module_id}' already exists in the catalog.[/] "
            "Choose a unique ID — or edit the existing module directly:"
        )
        # Help the author find the existing file
        console.print(f"  modules/{module_id}.md")
        sys.exit(2)

    # Parse requires (comma-separated)
    require_list = [r.strip() for r in requires.split(",") if r.strip()]
    # Validate requires reference existing modules (warning, not error —
    # contributors may be authoring two new modules at once and the
    # other isn't yet committed; downgrade to warning so the scaffold
    # still lands).
    unknown_requires = [r for r in require_list if r not in existing]

    # Generate the skeleton
    text = render_module_skeleton(
        module_id=module_id,
        track=track,
        title=title,
        time=time,
        requires=require_list,
        level=level,
        mode=mode,
    )

    # Write to outfile (default: ./<module_id>.md)
    out_path = Path(outfile) if outfile else Path(f"{module_id}.md")
    if out_path.exists():
        console.print(
            f"[red]Output file already exists: {out_path}[/] "
            "Refusing to overwrite. Pass a different --outfile or "
            "remove the existing file first."
        )
        sys.exit(2)
    out_path.write_text(text, encoding="utf-8")

    console.print()
    console.print(f"[green]Created:[/] {out_path}")
    if unknown_requires:
        console.print(
            f"[yellow]Note: requires references unknown modules: "
            f"{', '.join(unknown_requires)}.[/] "
            "If they are sibling new modules, fine; otherwise fix the IDs."
        )

    # Auto-lint
    console.print()
    console.print("[bold]Auto-lint:[/]")
    issues = lint_module_file(out_path)
    if not issues:
        console.print("  [green]PASS[/] — frontmatter + step skeleton are valid.")
    else:
        for issue in issues:
            color = "red" if issue.level == "error" else "yellow"
            console.print(f"  [{color}]{issue}[/]")

    console.print()
    console.print("[dim]Next: edit the TODO sections in the file, then run[/]")
    console.print(f"[cyan]  xrpl-lab lint {out_path}[/]")
    console.print("[dim]to validate your edits.[/]")
    console.print()


# ── Module linter ───────────────────────────────────────────────────


@main.command()
@click.argument("glob_pattern", default="modules/*.md")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.option("--no-curriculum", is_flag=True, help="Skip curriculum-level validation")
def lint(glob_pattern: str, json_output: bool, no_curriculum: bool):
    """Lint module files for authoring errors.

    Validates frontmatter, action names, payloads, mode labeling,
    and curriculum structure (prerequisites, cycles, tracks).

    \b
    Examples:
      xrpl-lab lint                     # lint all modules
      xrpl-lab lint modules/dex*.md     # lint a subset
      xrpl-lab lint --json              # CI-friendly JSON output
      xrpl-lab lint --no-curriculum     # skip cross-module checks
    """
    from .linter import LintResult, lint_curriculum, lint_module_file

    paths = sorted(Path(".").glob(glob_pattern))
    if not paths:
        if json_output:
            print(LintResult().to_json())
        else:
            console.print(f"[yellow]No files matching '{glob_pattern}'[/]")
        return

    result = LintResult()
    for p in paths:
        result.issues.extend(lint_module_file(p))

    # Curriculum-level validation (when linting the full set)
    if not no_curriculum:
        result.issues.extend(lint_curriculum())

    if json_output:
        print(result.to_json())
    else:
        console.print()
        if result.issues:
            for issue in result.issues:
                color = "red" if issue.level == "error" else "yellow"
                console.print(f"  [{color}]{issue}[/]")
            console.print()

        console.print(
            f"  Linted [bold]{len(paths)}[/] module(s): "
            f"[red]{result.error_count} error(s)[/], "
            f"[yellow]{result.warning_count} warning(s)[/]"
        )

        if result.passed:
            console.print("  [green]PASS[/]")
        else:
            console.print("  [red]FAIL[/]")
        console.print()

    if not result.passed:
        sys.exit(1)
