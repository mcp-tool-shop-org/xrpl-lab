"""Module runner — executes module steps interactively."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .actions.dex import (
    cancel_offer,
    create_offer,
    verify_offer_absent,
    verify_offer_present,
)
from .actions.reserves import (
    _drops_to_xrp,
    compare_snapshots,
    snapshot_account,
)
from .actions.send import send_payment
from .actions.trust_line import (
    issue_token,
    remove_trust_line,
    set_trust_line,
    verify_trust_line,
    verify_trust_line_removed,
)
from .actions.verify import verify_tx
from .actions.wallet import (
    create_wallet,
    load_wallet,
    save_wallet,
    wallet_exists,
)
from .modules import ModuleDef, ModuleStep
from .reporting import write_module_report
from .state import LabState, ensure_workspace, load_state, save_state
from .transport.base import Transport

console = Console()


async def _ensure_wallet(state: LabState, transport: Transport) -> tuple[LabState, str]:
    """Make sure we have a wallet; return (state, seed)."""
    wallet_path = Path(state.wallet_path) if state.wallet_path else None

    if wallet_path and wallet_exists(wallet_path):
        wallet = load_wallet(wallet_path)
        if wallet:
            console.print(f"  Wallet loaded: [cyan]{wallet.address}[/]")
            return state, wallet.seed
    elif wallet_exists():
        wallet = load_wallet()
        if wallet:
            console.print(f"  Wallet loaded: [cyan]{wallet.address}[/]")
            state.wallet_address = wallet.address
            state.wallet_path = str(wallet_path) if wallet_path else None
            save_state(state)
            return state, wallet.seed

    console.print("  No wallet found. Creating a new one...")
    wallet = create_wallet()
    path = save_wallet(wallet)
    console.print(f"  Wallet created: [cyan]{wallet.address}[/]")
    console.print(f"  Saved to: [dim]{path}[/]")
    console.print()
    console.print(
        "[yellow]  Warning: Your wallet seed is stored locally. "
        "Never share it or paste it anywhere.[/]"
    )

    state.wallet_address = wallet.address
    state.wallet_path = str(path)
    save_state(state)
    return state, wallet.seed


async def _ensure_funded(
    state: LabState, transport: Transport, address: str
) -> None:
    """Check balance and fund from faucet if needed."""
    balance = await transport.get_balance(address)
    if balance and float(balance) > 0:
        console.print(f"  Balance: [green]{balance} XRP[/]")
        return

    console.print("  Requesting funds from testnet faucet...")
    result = await transport.fund_from_faucet(address)
    if result.success:
        console.print(f"  Funded! Balance: [green]{result.balance} XRP[/]")
    else:
        console.print(f"  [red]Funding failed: {result.message}[/]")
        console.print("  You can retry with: [bold]xrpl-lab fund[/]")


async def _execute_action(
    step: ModuleStep,
    state: LabState,
    transport: Transport,
    wallet_seed: str,
    context: dict,
) -> dict:
    """Execute an action embedded in a module step. Returns updated context."""
    action = step.action
    if not action:
        return context

    if action == "ensure_wallet":
        state, wallet_seed = await _ensure_wallet(state, transport)
        context["wallet_seed"] = wallet_seed

    elif action == "ensure_funded":
        address = state.wallet_address
        if address:
            await _ensure_funded(state, transport, address)

    elif action == "submit_payment":
        args = step.action_args
        dest = args.get("destination", context.get("destination", ""))
        amount = args.get("amount", context.get("amount", "10"))
        memo = args.get("memo", context.get("memo", ""))
        memo = memo.replace("{timestamp}", str(int(time.time())))

        if not dest:
            # For receipt_literacy, we send to a known burn address or self
            dest = state.wallet_address or ""
            console.print(f"  Sending to self for practice: [cyan]{dest}[/]")

        result = await send_payment(transport, wallet_seed, dest, amount, memo)
        context["last_submit"] = result

        if result.success:
            console.print("  [green]Payment submitted![/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            console.print(f"  Result: {result.result_code}")
            console.print(f"  Fee: {result.fee} drops")
            if result.explorer_url:
                console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(f"  [red]Payment failed: {result.error}[/]")
            console.print(f"  Result code: {result.result_code}")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
            context.setdefault("failed_txids", []).append(
                {"result_code": result.result_code, "error": result.error}
            )

        save_state(state)

    elif action == "submit_payment_fail":
        # Intentionally submit a failing tx
        args = step.action_args
        fail_reason = args.get("reason", "bad_sequence")
        console.print(f"  [yellow]Intentionally submitting a failing tx ({fail_reason})...[/]")

        if hasattr(transport, "set_fail_next"):
            transport.set_fail_next(True)

        dest = args.get("destination", state.wallet_address or "")
        amount = args.get("amount", "10")
        result = await send_payment(
            transport, wallet_seed, dest, amount, memo="XRPLLAB|FAIL_TEST"
        )
        context["last_submit"] = result
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
        console.print(f"  Result code: [yellow]{result.result_code}[/]")
        console.print(f"  Error: {result.error}")

    elif action == "verify_tx":
        txid = context.get("txids", [""])[-1] if context.get("txids") else ""
        if not txid:
            console.print("  [red]No transaction to verify yet.[/]")
            return context

        result = await verify_tx(transport, txid)
        context["last_verify"] = result

        for check in result.checks:
            console.print(f"  [green]\u2713[/] {check}")
        for fail in result.failures:
            console.print(f"  [red]\u2717[/] {fail}")

    elif action == "create_issuer_wallet":
        console.print("  Creating issuer wallet...")
        issuer = create_wallet()
        issuer_path = Path(".xrpl-lab") / "issuer_wallet.json"
        issuer_path.parent.mkdir(parents=True, exist_ok=True)
        save_wallet(issuer, issuer_path)
        console.print(f"  Issuer wallet created: [cyan]{issuer.address}[/]")
        context["issuer_seed"] = issuer.seed
        context["issuer_address"] = issuer.address

    elif action == "fund_issuer":
        issuer_address = context.get("issuer_address", "")
        if not issuer_address:
            console.print("  [red]No issuer wallet found. Run the previous step first.[/]")
            return context
        console.print("  Funding issuer wallet from faucet...")
        result = await transport.fund_from_faucet(issuer_address)
        if result.success:
            console.print(f"  Issuer funded! Balance: [green]{result.balance} XRP[/]")
        else:
            console.print(f"  [red]Funding failed: {result.message}[/]")
            console.print("  You can retry by re-running this module.")

    elif action == "set_trust_line":
        args = step.action_args
        currency = args.get("currency", "LAB")
        limit = args.get("limit", "1000")
        issuer_address = context.get("issuer_address", "")

        if not issuer_address:
            console.print("  [red]No issuer address in context. Run the issuer step first.[/]")
            return context

        issuer_short = issuer_address[:12]
        console.print(
            f"  Setting trust line: [cyan]{currency}[/] "
            f"from issuer [cyan]{issuer_short}...[/]"
        )
        console.print(f"  Limit: {limit}")
        result = await set_trust_line(
            transport, context["wallet_seed"], issuer_address, currency, limit
        )

        if result.success:
            console.print("  [green]Trust line set![/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            if result.explorer_url:
                console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(f"  [red]Trust line failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "issue_token":
        args = step.action_args
        currency = args.get("currency", "LAB")
        amount = args.get("amount", "100")
        issuer_seed = context.get("issuer_seed", "")
        issuer_address = context.get("issuer_address", "")
        holder_address = state.wallet_address or ""

        if not issuer_seed or not holder_address:
            console.print("  [red]Missing issuer or holder wallet. Run previous steps first.[/]")
            return context

        console.print(f"  Issuing {amount} {currency} to [cyan]{holder_address[:12]}...[/]")
        result = await issue_token(
            transport, issuer_seed, holder_address, currency, issuer_address, amount,
            memo=f"XRPLLAB|ISSUE|{currency}|{amount}",
        )

        if result.success:
            console.print(f"  [green]{amount} {currency} issued![/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            if result.explorer_url:
                console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(f"  [red]Issuance failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "issue_token_expect_fail":
        # Intentionally issue tokens expecting failure (no trust line)
        args = step.action_args
        currency = args.get("currency", "DBG")
        amount = args.get("amount", "100")
        issuer_seed = context.get("issuer_seed", "")
        issuer_address = context.get("issuer_address", "")
        holder_address = state.wallet_address or ""

        if not issuer_seed or not holder_address:
            console.print(
                "  [red]Missing issuer or holder wallet. "
                "Run previous steps first.[/]"
            )
            return context

        console.print(
            f"  [yellow]Attempting to issue {amount} {currency} "
            f"(expecting failure)...[/]"
        )
        result = await issue_token(
            transport, issuer_seed, holder_address,
            currency, issuer_address, amount,
        )

        if result.success:
            console.print(
                f"  [yellow]Unexpected success — {amount} {currency} "
                f"delivered. Trust line may already exist.[/]"
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(f"  Error: {result.error}")

            # Decode the result code for learning
            from .doctor import explain_result_code

            info = explain_result_code(result.result_code)
            console.print()
            console.print(f"  Category: [cyan]{info['category']}[/]")
            console.print(f"  Meaning: {info['meaning']}")
            console.print(f"  Action: [yellow]{info['action']}[/]")

        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
        state.record_tx(
            txid=result.txid or "failed",
            module_id=context.get("module_id", ""),
            network=state.network,
            success=result.success,
        )
        save_state(state)

    elif action == "verify_trust_line":
        args = step.action_args
        currency = args.get("currency", "LAB")
        holder_address = state.wallet_address or ""
        issuer_address = context.get("issuer_address")

        if not holder_address:
            console.print("  [red]No wallet address found.[/]")
            return context

        result = await verify_trust_line(
            transport, holder_address, currency, expected_issuer=issuer_address
        )

        if result.found:
            for check in result.checks:
                console.print(f"  [green]\u2713[/] {check}")
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")
        else:
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")

        context["last_trust_line_verify"] = result

    elif action == "remove_trust_line":
        args = step.action_args
        currency = args.get("currency", "HYGIENE")
        issuer_address = context.get("issuer_address", "")

        if not issuer_address:
            console.print("  [red]No issuer address in context. Run the issuer step first.[/]")
            return context

        console.print(
            f"  Removing trust line: [cyan]{currency}[/] "
            f"(setting limit to 0)"
        )
        result = await remove_trust_line(
            transport, context["wallet_seed"], issuer_address, currency
        )

        if result.success:
            console.print("  [green]Trust line removed (limit 0, balance 0)[/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            if result.explorer_url:
                console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(f"  [red]Removal failed: {result.error}[/]")
            if "balance" in result.error.lower():
                console.print(
                    "  [yellow]Hint: send tokens back to issuer "
                    "before removing the trust line.[/]"
                )
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_trust_line_removed":
        args = step.action_args
        currency = args.get("currency", "HYGIENE")
        holder_address = state.wallet_address or ""
        issuer_address = context.get("issuer_address")

        if not holder_address:
            console.print("  [red]No wallet address found.[/]")
            return context

        result = await verify_trust_line_removed(
            transport, holder_address, currency, expected_issuer=issuer_address
        )

        if not result.found:
            for check in result.checks:
                console.print(f"  [green]\u2713[/] {check}")
        else:
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")

        context["last_trust_line_verify"] = result

    elif action == "create_offer":
        args = step.action_args
        pays_currency = args.get("pays_currency", "LAB")
        pays_value = args.get("pays_value", "50")
        gets_currency = args.get("gets_currency", "XRP")
        gets_value = args.get("gets_value", "10")
        issuer_address = context.get("issuer_address", "")

        # Resolve issuers: XRP has no issuer
        pays_issuer = "" if pays_currency == "XRP" else issuer_address
        gets_issuer = "" if gets_currency == "XRP" else issuer_address

        console.print(
            f"  Creating offer: pay {gets_value} {gets_currency} "
            f"to get {pays_value} {pays_currency}"
        )
        result = await create_offer(
            transport, context["wallet_seed"],
            pays_currency, pays_value, pays_issuer,
            gets_currency, gets_value, gets_issuer,
        )

        if result.success:
            console.print("  [green]Offer created![/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            if result.explorer_url:
                console.print(
                    f"  Explorer: [blue]{result.explorer_url}[/]"
                )
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
            # Store offer sequence for cancel/verify
            # In dry-run, the transport tracks offers internally
            offers = await transport.get_account_offers(
                state.wallet_address or ""
            )
            if offers:
                context["offer_sequence"] = offers[-1].sequence
                console.print(
                    f"  Offer sequence: "
                    f"[cyan]{context['offer_sequence']}[/]"
                )
        else:
            console.print(f"  [red]Offer failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_offer_present":
        offer_seq = context.get("offer_sequence")
        holder_address = state.wallet_address or ""

        if offer_seq is None:
            console.print(
                "  [red]No offer sequence in context. "
                "Create an offer first.[/]"
            )
            return context

        result = await verify_offer_present(
            transport, holder_address, offer_seq
        )

        if result.found:
            for check in result.checks:
                console.print(f"  [green]\u2713[/] {check}")
        else:
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")

        context["last_offer_verify"] = result

    elif action == "cancel_offer":
        offer_seq = context.get("offer_sequence")

        if offer_seq is None:
            console.print(
                "  [red]No offer sequence in context. "
                "Create an offer first.[/]"
            )
            return context

        console.print(f"  Cancelling offer seq {offer_seq}...")
        result = await cancel_offer(
            transport, context["wallet_seed"], offer_seq
        )

        if result.success:
            console.print("  [green]Offer cancelled![/]")
            console.print(f"  TXID: [cyan]{result.txid}[/]")
            if result.explorer_url:
                console.print(
                    f"  Explorer: [blue]{result.explorer_url}[/]"
                )
            state.record_tx(
                txid=result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=result.explorer_url,
            )
            context.setdefault("txids", []).append(result.txid)
        else:
            console.print(
                f"  [red]Cancel failed: {result.error}[/]"
            )
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_offer_absent":
        offer_seq = context.get("offer_sequence")
        holder_address = state.wallet_address or ""

        if offer_seq is None:
            console.print(
                "  [red]No offer sequence in context. "
                "Create an offer first.[/]"
            )
            return context

        result = await verify_offer_absent(
            transport, holder_address, offer_seq
        )

        if result.passed:
            for check in result.checks:
                console.print(f"  [green]\u2713[/] {check}")
        else:
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")

        context["last_offer_verify"] = result

    elif action == "snapshot_account":
        args = step.action_args
        label = args.get("label", "snapshot")
        holder_address = state.wallet_address or ""

        if not holder_address:
            console.print("  [red]No wallet address found.[/]")
            return context

        snap = await snapshot_account(transport, holder_address)
        context[f"snapshot_{label}"] = snap

        balance_xrp = _drops_to_xrp(snap.balance_drops)
        console.print(f"  Account: [cyan]{snap.address[:16]}...[/]")
        console.print(
            f"  Balance: [green]{balance_xrp} XRP[/] "
            f"({snap.balance_drops} drops)"
        )
        console.print(f"  Owner count: [cyan]{snap.owner_count}[/]")
        console.print(f"  Sequence: {snap.sequence}")

    elif action == "verify_reserve_change":
        args = step.action_args
        before_key = f"snapshot_{args.get('before', 'before')}"
        after_key = f"snapshot_{args.get('after', 'after')}"

        before_snap = context.get(before_key)
        after_snap = context.get(after_key)

        if not before_snap or not after_snap:
            console.print(
                "  [red]Missing snapshots. Run snapshot steps "
                "first.[/]"
            )
            return context

        result = compare_snapshots(
            before_snap, after_snap,
            label=args.get("after", "changes"),
        )

        for check in result.checks:
            if "increased" in check or "decreased" in check:
                console.print(f"  [cyan]\u0394[/] {check}")
            else:
                console.print(f"  [dim]\u2022[/] {check}")

        console.print()
        console.print(f"  [yellow]{result.explanation}[/]")

        context["last_reserve_comparison"] = result

    elif action == "write_report":
        # Handled at module completion
        pass

    return context


async def run_module(
    module: ModuleDef,
    transport: Transport,
    dry_run: bool = False,
) -> bool:
    """Run a module interactively. Returns True if completed successfully."""
    state = load_state()
    ensure_workspace()

    if state.is_module_completed(module.id) and not dry_run:
        console.print(
            f"\n[yellow]Module '{module.title}' is already completed. "
            f"Run with --force to redo it.[/]"
        )
        return True

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
        "wallet_seed": "",
        "txids": [],
        "failed_txids": [],
    }

    # Load wallet seed if available
    wallet = load_wallet()
    if wallet:
        context["wallet_seed"] = wallet.seed

    report_sections: list[tuple[str, str]] = []

    for i, step in enumerate(module.steps):
        # Render step text
        console.print(Markdown(step.text))
        console.print()

        # Execute action if present
        if step.action:
            context = await _execute_action(step, state, transport, context["wallet_seed"], context)
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
        ):
            report_sections.append(
                (f"Step {i + 1}", step.text.split("\n")[0][:100])
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
    console.print(Panel(
        f"[bold green]Module completed: {module.title}[/]\n"
        f"Report: {report_path}\n"
        f"Transactions: {len(context['txids'])}",
        title="Complete",
        border_style="green",
    ))

    return True
