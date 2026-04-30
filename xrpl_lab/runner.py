"""Module runner — executes module steps interactively."""

from __future__ import annotations

import copy
import inspect
import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Import handlers to trigger registration as a side effect
import xrpl_lab.handlers  # noqa: F401

from .actions.wallet import load_wallet
from .modules import ModuleDef, ModuleStep
from .registry import PayloadError, PayloadSchema, UnknownActionError, resolve
from .reporting import write_module_report
from .runtime import _SecretValue
from .state import LabState, ensure_workspace, load_state, save_state
from .transport.base import Transport

console = Console()


def _snapshot_context(context: dict) -> dict:
    """Deep-copy ``context`` for step rollback (F-BACKEND-B-004).

    ``_SecretValue`` raises TypeError on pickle/deepcopy by design (it's
    meant to be unclonable to prevent accidental leak via copy). The
    runner needs a snapshot of the rest of the context to restore on
    handler exception, so we walk the top level, hold ``_SecretValue``
    instances aside as shared references, and ``deepcopy`` everything
    else. Identity is preserved for the secret wrapper — that's
    intentional; the wrapper's contained string is immutable, and a
    handler that mutates it (replaces the slot in context) would
    correctly be reflected in the snapshot's reference too. What we're
    actually protecting against is partial appends to ``context['txids']``
    leaking out when the step itself raises mid-mutation.
    """
    secrets: dict = {}
    safe: dict = {}
    for k, v in context.items():
        if isinstance(v, _SecretValue):
            secrets[k] = v
        else:
            safe[k] = v
    snapshot = copy.deepcopy(safe)
    snapshot.update(secrets)
    return snapshot


async def _execute_action(
    step: ModuleStep,
    state: LabState,
    transport: Transport,
    wallet_seed: str | _SecretValue,
    context: dict,
    console: Console | None = None,
) -> dict:
    """Execute an action via the registry. Returns updated context."""
    if console is None:
        console = globals()["console"]
    action = step.action
    if not action:
        return context

    # Resolve wallet_seed safely from context
    _raw = context.get('wallet_seed', wallet_seed) or wallet_seed
    wallet_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw

    # Look up action in the registry
    try:
        action_def = resolve(action)
    except UnknownActionError:
        console.print(
            f"[red]Unknown action: '{action}'[/]\n"
            f"[yellow]This action is not registered. "
            f"Check the module for typos, or run 'xrpl-lab lint' "
            f"to validate.[/]"
        )
        return context

    # Wallet gate
    if action_def.wallet_required and not wallet_seed:
        console.print('[red]No wallet available. Run ensure_wallet first.[/]')
        return context

    # Payload validation (when schema is defined)
    if action_def.payload_fields:
        schema = PayloadSchema(fields=tuple(action_def.payload_fields))
        try:
            schema.validate(step.action_args)
        except PayloadError as exc:
            console.print(
                f"[red]Payload error in '{action}':[/] {exc}\n"
                f"[yellow]Check the action arguments in the module file.[/]"
            )
            return context

    # Dispatch to the registered handler
    context = await action_def.handler(
        step, state, transport, wallet_seed, context, console,
    )
    return context


async def run_module(
    module: ModuleDef,
    transport: Transport,
    dry_run: bool = False,
    force: bool = False,
    console: Console | None = None,
    on_step: Callable | None = None,
    on_step_complete: Callable | None = None,
    on_tx: Callable | None = None,
) -> bool:
    """Run a module interactively. Returns True if completed successfully.

    Parameters
    ----------
    console:
        Rich Console to use for output.  Falls back to the module-level global.
    on_step:
        ``on_step(action, index, total)`` — called before each step executes.
    on_step_complete:
        ``on_step_complete(action, success)`` — called after each step.
    on_tx:
        ``on_tx(txid, result_code)`` — called for each new transaction.
    """
    if console is None:
        console = globals()["console"]
    state = load_state()
    ensure_workspace()

    if state.is_module_completed(module.id) and not dry_run:
        console.print(
            f"\n[yellow]Module '{module.title}' is already completed. "
            f"Run with --force to redo it.[/]"
        )
        return True

    # FT-013: Prerequisite check — warn if required modules not completed
    if module.requires and not force:
        completed_ids = {cm.module_id for cm in state.completed_modules}
        missing_prereqs = [r for r in module.requires if r not in completed_ids]
        if missing_prereqs:
            console.print(
                "[yellow]Warning: This module requires the following to be completed first:[/]"
            )
            for prereq in missing_prereqs:
                console.print(f"  [yellow]- {prereq}[/]")
            console.print(
                "[yellow]Run those modules first, or use --force to bypass.[/]"
            )

    # FT-003: Warn if module uses AMM actions but transport is not dry-run
    _AMM_ACTIONS = {"ensure_amm_pair", "amm_deposit", "amm_withdraw"}
    _module_step_actions = {s.action for s in module.steps if s.action}
    if _AMM_ACTIONS & _module_step_actions and transport.network_name != "dry-run":
        console.print(
            "[yellow]This module uses AMM operations which require --dry-run mode.[/]"
        )
        console.print(
            f"[yellow]Run with: xrpl-lab run {module.id} --dry-run[/]"
        )
        return False

    console.print()
    console.print(
        Panel(
            f"[bold]{module.title}[/]\n"
            f"Level: {module.level}  |  Time: ~{module.time}\n"
            f"Produces: {', '.join(module.produces)}",
            title="Module",
            border_style="blue",
        )
    )
    console.print()

    # Initialize context
    context: dict = {
        "module_id": module.id,
        "wallet_seed": _SecretValue(""),
        "txids": [],
        "failed_txids": [],
        "run_id": time.strftime('%Y%m%dT%H%M%S', time.gmtime()),
    }

    # Load wallet seed if available
    wallet = load_wallet()
    if wallet:
        context["wallet_seed"] = _SecretValue(wallet.seed)

    report_sections: list[tuple[str, str]] = []

    for i, step in enumerate(module.steps):
        # Render step text
        console.print(Markdown(step.text))
        console.print()

        # Execute action if present
        if step.action:
            if on_step is not None:
                _r = on_step(step.action, i, len(module.steps))
                if inspect.isawaitable(_r):
                    await _r
            console.print(f"[dim]  → {step.action}...[/]")
            # F-BACKEND-B-004: snapshot context BEFORE the handler runs
            # so we can roll back partial mutations if the handler
            # raises mid-step. Without this, a handler that appends a
            # txid then raises would leak that txid into the saved
            # state — the txid corresponds to a transaction the real
            # ledger never accepted.
            _context_snapshot = _snapshot_context(context)
            try:
                context = await _execute_action(
                    step, state, transport,
                    context.get("wallet_seed", _SecretValue("")),
                    context,
                    console=console,
                )
            except Exception as exc:
                # F-BACKEND-B-004: restore pre-step context. The state
                # object's atomic-write fix (wave 1) handles durability;
                # this handles step-level atomicity at the context layer.
                context = _context_snapshot
                if on_step_complete is not None:
                    _r = on_step_complete(step.action, False)
                    if inspect.isawaitable(_r):
                        await _r
                # F-BACKEND-C-005: action errors come with structured
                # code/message/hint; surface those directly. Generic
                # exception fallback retains the doctor suggestion (the
                # right move for infrastructure issues).
                from .errors import LabException
                if isinstance(exc, LabException):
                    console.print(f"[red]Step failed:[/] {exc.error.code}")
                    console.print(f"  {exc.error.message}")
                    if exc.error.hint:
                        console.print(f"  [yellow]Hint:[/] {exc.error.hint}")
                else:
                    console.print(
                        f"[red]Step failed:[/] "
                        f"{type(exc).__name__}: {exc}"
                    )
                    console.print(
                        "[yellow]Hint: Run 'xrpl-lab doctor' "
                        "to diagnose the issue.[/]"
                    )
                save_state(state)
                console.print(
                    f"[yellow]Progress saved. You can resume with: "
                    f"xrpl-lab run {module.id}[/]"
                )
                return False

            # Fire tx callback for any new transactions from this step
            if on_tx is not None:
                for txid in context.get("txids", []):
                    last_submit = context.get("last_submit")
                    result_code = ""
                    if last_submit and hasattr(last_submit, "result_code"):
                        result_code = last_submit.result_code or ""
                    _r = on_tx(txid, result_code)
                    if inspect.isawaitable(_r):
                        await _r

            # Fire step_complete callback
            if on_step_complete is not None:
                success = True
                last_submit = context.get("last_submit")
                if last_submit and hasattr(last_submit, "success"):
                    success = bool(last_submit.success)
                _r = on_step_complete(step.action, success)
                if inspect.isawaitable(_r):
                    await _r

            console.print()

        # Pause between steps (except last)
        if i < len(module.steps) - 1:
            try:
                console.input("[dim]Press Enter to continue...[/]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Module interrupted.[/]")
                return False

        # Collect report material
        if step.action in (
            "submit_payment", "submit_payment_fail", "verify_tx",
            "set_trust_line", "issue_token", "issue_token_expect_fail",
            "verify_trust_line",
            "create_offer", "cancel_offer",
            "verify_offer_present", "verify_offer_absent",
            "snapshot_account", "verify_reserve_change",
            "remove_trust_line", "verify_trust_line_removed",
            "run_audit",
            "ensure_amm_pair", "get_amm_info",
            "amm_deposit", "verify_lp_received",
            "amm_withdraw", "verify_withdrawal",
            "snapshot_position", "verify_position_delta",
            "strategy_offer_bid", "strategy_offer_ask",
            "verify_module_offers", "cancel_module_offers",
            "verify_module_offers_absent", "hygiene_summary",
            "check_inventory", "place_safe_sides",
        ):
            # FT-006: include action outcome in the report body
            step_heading = step.text.split("\n")[0][:100]
            outcome_lines: list[str] = [f"Action: `{step.action}`"]

            # Capture txids produced by this step
            current_txids = context.get("txids", [])
            if current_txids:
                outcome_lines.append(f"Transactions: {len(current_txids)}")
                for txid in current_txids[-3:]:  # last 3 at most
                    outcome_lines.append(f"- TXID: `{txid}`")

            # Capture last submit result
            last_submit = context.get("last_submit")
            if last_submit and hasattr(last_submit, "result_code") and last_submit.result_code:
                outcome_lines.append(f"Result code: `{last_submit.result_code}`")

            # Capture verify result
            last_verify = context.get("last_verify")
            if last_verify and hasattr(last_verify, "checks"):
                for chk in last_verify.checks[:3]:
                    outcome_lines.append(f"- \u2713 {chk}")

            report_sections.append(
                (f"Step {i + 1}: {step_heading}", "\n".join(outcome_lines))
            )

    # Module completed — write report and update state
    report_sections.append(
        ("Summary", f"Transactions: {len(context['txids'])} successful, "
         f"{len(context['failed_txids'])} failed")
    )

    for txid in context["txids"]:
        report_sections.append(("Transaction", f"TXID: `{txid}`"))

    report_path = write_module_report(
        module_id=module.id,
        title=module.title,
        sections=report_sections,
    )

    state = load_state()  # Reload in case actions modified it
    state.complete_module(
        module_id=module.id,
        txids=context["txids"],
        report_path=str(report_path),
    )
    save_state(state)

    console.print()

    # Build completion message with audit hint if last_run exists
    tx_count = len(context['txids'])
    completion_lines = [
        f"[bold green]{module.title}[/]",
        f"Report saved to {report_path}",
        f"{tx_count} transaction{'s' if tx_count != 1 else ''} recorded",
    ]

    last_run_txids = Path(".xrpl-lab/last_run_txids.txt")
    if last_run_txids.exists():
        completion_lines.append("")
        completion_lines.append("[dim]Verify this run:[/]")
        audit_cmd = f"xrpl-lab audit --txids {last_run_txids}"
        # Check for a matching preset
        preset_candidates = list(Path("presets").glob("*.json")) if Path("presets").exists() else []
        for p in preset_candidates:
            if module.id.split("_")[0] in p.stem or module.id[:6] in p.stem:
                audit_cmd += f" --expect {p}"
                break
        completion_lines.append(f"  [cyan]{audit_cmd}[/]")

    console.print(Panel(
        "\n".join(completion_lines),
        title="Complete",
        border_style="green",
    ))

    return True
