"""Module runner — executes module steps interactively."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .actions.amm import (
    amm_deposit,
    amm_withdraw,
    ensure_amm_pair,
    verify_lp_received,
    verify_withdrawal,
)
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
from .actions.strategy import (
    cancel_module_offers,
    check_inventory,
    compare_positions,
    hygiene_summary,
    snapshot_position,
    strategy_memo,
    write_last_run,
)
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
    default_wallet_path,
    load_wallet,
    save_wallet,
    wallet_exists,
)
from .audit import run_audit, write_audit_pack, write_audit_report_md
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
            state.wallet_path = str(default_wallet_path())
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

    elif action == "run_audit":
        txids = context.get("txids", [])
        if not txids:
            console.print("  [yellow]No transactions to audit yet.[/]")
            return context

        console.print(f"  Auditing {len(txids)} transaction(s)...")
        audit_report = await run_audit(transport, txids)

        console.print()
        console.print(f"  Checked: [bold]{audit_report.total}[/]")
        console.print(f"  Pass:    [green]{audit_report.passed}[/]")
        console.print(f"  Fail:    [red]{audit_report.failed}[/]")
        console.print(f"  Missing: [yellow]{audit_report.not_found}[/]")

        # Show per-tx verdicts
        console.print()
        for v in audit_report.verdicts:
            icon = "[green]\u2713[/]" if v.status == "pass" else "[red]\u2717[/]"
            console.print(f"  {icon} {v.txid[:16]}... [{v.status}]")
            for check in v.checks[:3]:  # Show first 3 checks
                console.print(f"      {check}")
            for fail in v.failures:
                console.print(f"      [red]{fail}[/]")

        # Write reports
        ensure_workspace()
        ts = int(time.time())
        md_path = Path(f".xrpl-lab/reports/audit_{ts}.md")
        write_audit_report_md(audit_report, md_path)
        console.print()
        console.print(f"  Report: [green]{md_path}[/]")

        pack_path = Path(f".xrpl-lab/proofs/audit_pack_{ts}.json")
        write_audit_pack(audit_report, pack_path)
        console.print(f"  Audit pack: [green]{pack_path}[/]")

        context["last_audit"] = audit_report

    elif action == "ensure_amm_pair":
        args = step.action_args
        a_currency = args.get("a_currency", "XRP")
        a_value = args.get("a_value", "100")
        b_currency = args.get("b_currency", "LAB")
        b_value = args.get("b_value", "100")
        issuer_address = context.get("issuer_address", "")

        a_issuer = "" if a_currency == "XRP" else issuer_address
        b_issuer = "" if b_currency == "XRP" else issuer_address

        console.print(
            f"  Checking for AMM pool: "
            f"[cyan]{a_currency}[/] / [cyan]{b_currency}[/]"
        )

        amm_info, create_result = await ensure_amm_pair(
            transport, context["wallet_seed"],
            a_currency, a_value, a_issuer,
            b_currency, b_value, b_issuer,
        )

        if create_result is None:
            console.print("  [green]AMM pool already exists[/]")
        elif create_result.success:
            console.print("  [green]AMM pool created![/]")
            console.print(f"  TXID: [cyan]{create_result.txid}[/]")
            if create_result.explorer_url:
                console.print(
                    f"  Explorer: [blue]{create_result.explorer_url}[/]"
                )
            state.record_tx(
                txid=create_result.txid,
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
                explorer_url=create_result.explorer_url,
            )
            context.setdefault("txids", []).append(create_result.txid)
            save_state(state)
        else:
            console.print(
                f"  [red]AMM creation failed: {create_result.error}[/]"
            )

        console.print(f"  Pool A: {amm_info.pool_a}")
        console.print(f"  Pool B: {amm_info.pool_b}")
        console.print(f"  LP token: {amm_info.lp_token_currency}")
        console.print(f"  LP issuer: {amm_info.lp_token_issuer[:16]}...")

        context["amm_info"] = amm_info
        context["a_currency"] = a_currency
        context["a_issuer"] = a_issuer
        context["b_currency"] = b_currency
        context["b_issuer"] = b_issuer

    elif action == "get_amm_info":
        args = step.action_args
        a_currency = args.get("a_currency", context.get("a_currency", "XRP"))
        b_currency = args.get("b_currency", context.get("b_currency", "LAB"))
        a_issuer = context.get("a_issuer", "")
        b_issuer = context.get("b_issuer", "")

        amm_info = await transport.get_amm_info(
            a_currency, a_issuer, b_currency, b_issuer,
        )

        if amm_info:
            console.print(f"  Pool {a_currency}: [cyan]{amm_info.pool_a}[/]")
            console.print(f"  Pool {b_currency}: [cyan]{amm_info.pool_b}[/]")
            console.print(f"  LP supply: [cyan]{amm_info.lp_supply}[/]")
            console.print(f"  Trading fee: {amm_info.trading_fee}")
            context["amm_info"] = amm_info
        else:
            console.print("  [red]No AMM found for this pair.[/]")

    elif action == "amm_deposit":
        args = step.action_args
        a_currency = args.get("a_currency", context.get("a_currency", "XRP"))
        a_value = args.get("a_value", "10")
        b_currency = args.get("b_currency", context.get("b_currency", "LAB"))
        b_value = args.get("b_value", "10")
        a_issuer = context.get("a_issuer", "")
        b_issuer = context.get("b_issuer", "")

        console.print(
            f"  Depositing: [cyan]{a_value} {a_currency}[/] + "
            f"[cyan]{b_value} {b_currency}[/]"
        )

        result = await amm_deposit(
            transport, context["wallet_seed"],
            a_currency, a_value, a_issuer,
            b_currency, b_value, b_issuer,
        )

        if result.success:
            console.print("  [green]Deposit succeeded![/]")
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
            console.print(f"  [red]Deposit failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_lp_received":
        amm_info = context.get("amm_info")
        holder_address = state.wallet_address or ""

        if not amm_info:
            console.print("  [red]No AMM info in context. Run AMM steps first.[/]")
            return context

        result = await verify_lp_received(
            transport, holder_address, amm_info,
        )

        for check in result.checks:
            console.print(f"  [green]\u2713[/] {check}")
        for fail in result.failures:
            console.print(f"  [red]\u2717[/] {fail}")

        context["lp_balance_before_withdraw"] = result.lp_balance
        context["last_amm_verify"] = result

    elif action == "amm_withdraw":
        args = step.action_args
        a_currency = args.get("a_currency", context.get("a_currency", "XRP"))
        b_currency = args.get("b_currency", context.get("b_currency", "LAB"))
        a_issuer = context.get("a_issuer", "")
        b_issuer = context.get("b_issuer", "")
        lp_value = args.get("lp_value", "")  # empty = withdraw all

        console.print(
            f"  Withdrawing from AMM: "
            f"[cyan]{a_currency}[/] / [cyan]{b_currency}[/]"
        )
        if not lp_value:
            console.print("  (returning all LP tokens)")

        result = await amm_withdraw(
            transport, context["wallet_seed"],
            a_currency, a_issuer,
            b_currency, b_issuer,
            lp_token_value=lp_value,
        )

        if result.success:
            console.print("  [green]Withdrawal succeeded![/]")
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
            console.print(f"  [red]Withdrawal failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_withdrawal":
        amm_info = context.get("amm_info")
        holder_address = state.wallet_address or ""
        lp_before = context.get("lp_balance_before_withdraw", "0")

        if not amm_info:
            console.print("  [red]No AMM info in context. Run AMM steps first.[/]")
            return context

        result = await verify_withdrawal(
            transport, holder_address, amm_info,
            lp_before=lp_before,
        )

        for check in result.checks:
            console.print(f"  [green]\u2713[/] {check}")
        for fail in result.failures:
            console.print(f"  [red]\u2717[/] {fail}")

        context["last_amm_verify"] = result

    elif action == "snapshot_position":
        args = step.action_args
        label = args.get("label", "snapshot")
        holder_address = state.wallet_address or ""

        if not holder_address:
            console.print("  [red]No wallet address found.[/]")
            return context

        snap = await snapshot_position(transport, holder_address)
        context[f"position_{label}"] = snap

        balance_xrp = _drops_to_xrp(snap.xrp_balance)
        console.print(f"  Account: [cyan]{snap.account.address[:16]}...[/]")
        console.print(
            f"  Balance: [green]{balance_xrp} XRP[/] "
            f"({snap.xrp_balance} drops)"
        )
        console.print(f"  Owner count: [cyan]{snap.owner_count}[/]")
        console.print(f"  Open offers: [cyan]{snap.offer_count}[/]")
        console.print(f"  Trust lines: [cyan]{len(snap.trust_lines)}[/]")

    elif action == "strategy_offer_bid":
        args = step.action_args
        pays_currency = args.get("pays_currency", "LAB")
        pays_value = args.get("pays_value", "10")
        gets_currency = args.get("gets_currency", "XRP")
        gets_value = args.get("gets_value", "1")
        memo_action = args.get("memo_action", "OFFER_BID")
        issuer_address = context.get("issuer_address", "")
        module_id = context.get("module_id", "MM101")

        pays_issuer = "" if pays_currency == "XRP" else issuer_address
        gets_issuer = "" if gets_currency == "XRP" else issuer_address

        memo = strategy_memo(
            module_id.upper().replace("_", ""),
            memo_action,
            context.get("run_id", ""),
        )

        console.print(
            f"  [yellow]BID[/]: pay {gets_value} {gets_currency} "
            f"to get {pays_value} {pays_currency}"
        )
        console.print(f"  Memo: [dim]{memo}[/]")

        result = await create_offer(
            transport, context["wallet_seed"],
            pays_currency, pays_value, pays_issuer,
            gets_currency, gets_value, gets_issuer,
        )

        if result.success:
            console.print("  [green]Bid placed![/]")
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

            # Track offer sequence for strategy management
            offers = await transport.get_account_offers(
                state.wallet_address or ""
            )
            if offers:
                seq = offers[-1].sequence
                context.setdefault("strategy_offer_sequences", []).append(seq)
                console.print(f"  Offer sequence: [cyan]{seq}[/]")
        else:
            console.print(f"  [red]Bid failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "strategy_offer_ask":
        args = step.action_args
        pays_currency = args.get("pays_currency", "LAB")
        pays_value = args.get("pays_value", "10")
        gets_currency = args.get("gets_currency", "XRP")
        gets_value = args.get("gets_value", "2")
        memo_action = args.get("memo_action", "OFFER_ASK")
        issuer_address = context.get("issuer_address", "")
        module_id = context.get("module_id", "MM101")

        pays_issuer = "" if pays_currency == "XRP" else issuer_address
        gets_issuer = "" if gets_currency == "XRP" else issuer_address

        memo = strategy_memo(
            module_id.upper().replace("_", ""),
            memo_action,
            context.get("run_id", ""),
        )

        console.print(
            f"  [yellow]ASK[/]: sell {pays_value} {pays_currency} "
            f"for {gets_value} {gets_currency}"
        )
        console.print(f"  Memo: [dim]{memo}[/]")

        result = await create_offer(
            transport, context["wallet_seed"],
            pays_currency, pays_value, pays_issuer,
            gets_currency, gets_value, gets_issuer,
        )

        if result.success:
            console.print("  [green]Ask placed![/]")
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

            offers = await transport.get_account_offers(
                state.wallet_address or ""
            )
            if offers:
                seq = offers[-1].sequence
                context.setdefault("strategy_offer_sequences", []).append(seq)
                console.print(f"  Offer sequence: [cyan]{seq}[/]")
        else:
            console.print(f"  [red]Ask failed: {result.error}[/]")
            state.record_tx(
                txid=result.txid or "failed",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=False,
            )
        save_state(state)

    elif action == "verify_module_offers":
        seqs = context.get("strategy_offer_sequences", [])
        holder_address = state.wallet_address or ""

        if not seqs:
            console.print("  [red]No strategy offers to verify.[/]")
            return context

        all_found = True
        for seq in seqs:
            result = await verify_offer_present(
                transport, holder_address, seq
            )
            if result.found:
                for check in result.checks:
                    console.print(f"  [green]\u2713[/] {check}")
            else:
                all_found = False
                for fail in result.failures:
                    console.print(f"  [red]\u2717[/] {fail}")

        if all_found:
            console.print(
                f"  [green]All {len(seqs)} strategy offers verified[/]"
            )

    elif action == "cancel_module_offers":
        seqs = context.get("strategy_offer_sequences", [])

        if not seqs:
            console.print("  [yellow]No strategy offers to cancel.[/]")
            return context

        console.print(f"  Cancelling {len(seqs)} offer(s)...")
        results = await cancel_module_offers(
            transport, context["wallet_seed"], seqs,
        )

        cancelled = 0
        for seq, success in results:
            if success:
                console.print(f"  [green]\u2713[/] Offer seq {seq} cancelled")
                cancelled += 1
            else:
                console.print(f"  [red]\u2717[/] Offer seq {seq} cancel failed")

        # Record cancel txids
        for seq, success in results:
            if success:
                state.record_tx(
                    txid=f"cancel-{seq}",
                    module_id=context.get("module_id", ""),
                    network=state.network,
                    success=True,
                )
        save_state(state)
        context["offers_cancelled"] = cancelled
        context["strategy_offer_sequences"] = []

    elif action == "verify_module_offers_absent":
        seqs = context.get("strategy_offer_sequences", [])
        holder_address = state.wallet_address or ""

        # Check there are no offers from this module
        offers = await transport.get_account_offers(holder_address)
        remaining = len(offers)

        if remaining == 0:
            console.print("  [green]\u2713 No open offers — all cleared[/]")
        else:
            console.print(
                f"  [yellow]{remaining} offer(s) still open[/]"
            )

    elif action == "verify_position_delta":
        args = step.action_args
        before_key = f"position_{args.get('before', 'before')}"
        after_key = f"position_{args.get('after', 'after')}"

        before_snap = context.get(before_key)
        after_snap = context.get(after_key)

        if not before_snap or not after_snap:
            console.print(
                "  [red]Missing position snapshots. "
                "Run snapshot_position steps first.[/]"
            )
            return context

        result = compare_positions(
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

        context["last_position_comparison"] = result

    elif action == "check_inventory":
        args = step.action_args
        currency = args.get("currency", "LAB")
        min_xrp = int(args.get("min_xrp_drops", "20000000"))
        min_token = float(args.get("min_token", "10"))
        holder_address = state.wallet_address or ""

        if not holder_address:
            console.print("  [red]No wallet address found.[/]")
            return context

        snap = await snapshot_position(transport, holder_address)
        inv = check_inventory(
            snap, token_currency=currency,
            min_xrp_drops=min_xrp, min_token_balance=min_token,
        )

        for check in inv.checks:
            if "OK" in check:
                console.print(f"  [green]\u2713[/] {check}")
            else:
                console.print(f"  [yellow]\u26a0[/] {check}")

        console.print()
        if inv.any_allowed:
            console.print(
                f"  Sides allowed: [green]{', '.join(inv.sides_allowed)}[/]"
            )
        else:
            console.print("  [red]No sides allowed — inventory too low[/]")

        context["inventory_check"] = inv
        context["position_baseline"] = snap

    elif action == "place_safe_sides":
        inv = context.get("inventory_check")
        if not inv:
            console.print(
                "  [red]No inventory check in context. "
                "Run check_inventory first.[/]"
            )
            return context

        if not inv.any_allowed:
            console.print(
                "  [yellow]No sides allowed by inventory check. "
                "Skipping offer placement.[/]"
            )
            return context

        args = step.action_args
        pays_currency = args.get("pays_currency", "LAB")
        gets_currency = args.get("gets_currency", "XRP")
        bid_value = args.get("bid_value", "10")
        ask_value = args.get("ask_value", "10")
        bid_price = args.get("bid_price", "1")
        ask_price = args.get("ask_price", "2")
        issuer_address = context.get("issuer_address", "")
        module_id = context.get("module_id", "INV")

        pays_issuer = "" if pays_currency == "XRP" else issuer_address
        gets_issuer = "" if gets_currency == "XRP" else issuer_address

        placed = 0

        if inv.can_bid:
            memo = strategy_memo(
                module_id.upper().replace("_", ""),
                "OFFER_BID",
                context.get("run_id", ""),
            )
            console.print(
                f"  [yellow]BID[/]: pay {bid_price} {gets_currency} "
                f"to get {bid_value} {pays_currency}"
            )
            console.print(f"  Memo: [dim]{memo}[/]")

            result = await create_offer(
                transport, context["wallet_seed"],
                pays_currency, bid_value, pays_issuer,
                gets_currency, bid_price, gets_issuer,
            )

            if result.success:
                console.print("  [green]Bid placed![/]")
                console.print(f"  TXID: [cyan]{result.txid}[/]")
                state.record_tx(
                    txid=result.txid,
                    module_id=context.get("module_id", ""),
                    network=state.network,
                    success=True,
                    explorer_url=result.explorer_url,
                )
                context.setdefault("txids", []).append(result.txid)
                offers = await transport.get_account_offers(
                    state.wallet_address or ""
                )
                if offers:
                    seq = offers[-1].sequence
                    context.setdefault(
                        "strategy_offer_sequences", []
                    ).append(seq)
                placed += 1
            else:
                console.print(f"  [red]Bid failed: {result.error}[/]")
            save_state(state)
        else:
            console.print("  [dim]Bid skipped (XRP too low)[/]")

        if inv.can_ask:
            memo = strategy_memo(
                module_id.upper().replace("_", ""),
                "OFFER_ASK",
                context.get("run_id", ""),
            )
            console.print(
                f"  [yellow]ASK[/]: sell {ask_value} {pays_currency} "
                f"for {ask_price} {gets_currency}"
            )
            console.print(f"  Memo: [dim]{memo}[/]")

            result = await create_offer(
                transport, context["wallet_seed"],
                pays_currency, ask_value, pays_issuer,
                gets_currency, ask_price, gets_issuer,
            )

            if result.success:
                console.print("  [green]Ask placed![/]")
                console.print(f"  TXID: [cyan]{result.txid}[/]")
                state.record_tx(
                    txid=result.txid,
                    module_id=context.get("module_id", ""),
                    network=state.network,
                    success=True,
                    explorer_url=result.explorer_url,
                )
                context.setdefault("txids", []).append(result.txid)
                offers = await transport.get_account_offers(
                    state.wallet_address or ""
                )
                if offers:
                    seq = offers[-1].sequence
                    context.setdefault(
                        "strategy_offer_sequences", []
                    ).append(seq)
                placed += 1
            else:
                console.print(f"  [red]Ask failed: {result.error}[/]")
            save_state(state)
        else:
            console.print("  [dim]Ask skipped (token too low)[/]")

        console.print(
            f"  [green]{placed} offer(s) placed[/] "
            f"out of {len(inv.sides_allowed)} allowed"
        )

    elif action == "hygiene_summary":
        baseline = context.get("position_baseline")
        final = context.get("position_final")

        if not baseline or not final:
            console.print(
                "  [red]Missing baseline or final snapshots.[/]"
            )
            return context

        summary = hygiene_summary(
            baseline, final,
            offers_cancelled=context.get("offers_cancelled", 0),
        )

        console.print()
        console.print(Panel(
            "\n".join(summary.checks),
            title="Hygiene Summary",
            border_style="green" if summary.clean else "yellow",
        ))

        # Write last run files
        txids = context.get("txids", [])
        if txids:
            run_path = write_last_run(
                txids=txids,
                module_id=context.get("module_id", ""),
                preset="strategy_mm101",
            )
            console.print(f"  Last run txids: [green]{run_path}[/]")

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

    # Build completion message with audit hint if last_run exists
    completion_lines = [
        f"[bold green]Module completed: {module.title}[/]",
        f"Report: {report_path}",
        f"Transactions: {len(context['txids'])}",
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
