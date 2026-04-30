"""Action handlers — each action extracted as a registered handler.

Import this module to populate the registry. All handlers follow the
uniform signature::

    async def handle_*(step, state, transport, wallet_seed, context, console) -> dict
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rich.console import Console
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
from .actions.wallet import create_wallet, save_wallet
from .audit import run_audit, write_audit_pack, write_audit_report_md
from .errors import LabError, LabException
from .modules import ModuleStep
from .registry import ActionDef, PayloadField, register
from .runtime import _SecretValue, ensure_funded, ensure_wallet
from .state import LabState, ensure_workspace, save_state
from .transport.base import Transport


def _require(
    args: dict,
    context: dict,
    key: str,
    *,
    action: str,
    hint: str,
) -> str:
    """Resolve a required key from action_args then context, raising on missing/empty.

    Several handlers chain ``args.get(key, context.get(key, ''))`` and then
    silently degrade or self-send when both are empty (F-BACKEND-B-001).
    This helper makes empty inputs an explicit, structured failure surfaced
    via the existing ``LabException`` pipeline (CLI exit codes + WS event
    framing in ``api/runner_ws.py`` already handle the type).

    Returns the resolved value. The runner's outer try/except logs the
    exception and saves state so progress isn't lost.
    """
    raw = args.get(key, context.get(key, ""))
    value = "" if raw is None else str(raw).strip()
    if not value:
        raise LabException(
            LabError(
                code="INPUT_REQUIRED_FIELD",
                message=f"Missing required '{key}' for action '{action}'.",
                hint=hint,
            )
        )
    return value

# ---------------------------------------------------------------------------
# Wallet / setup actions
# ---------------------------------------------------------------------------


async def handle_ensure_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    state, wrapped_seed = await ensure_wallet(state, transport, console)
    context["wallet_seed"] = wrapped_seed
    return context


async def handle_ensure_funded(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address
    if address:
        await ensure_funded(state, transport, address, console)
    return context


# ---------------------------------------------------------------------------
# Payment actions
# ---------------------------------------------------------------------------


async def handle_submit_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    dest = args.get("destination", context.get("destination", ""))
    amount = args.get("amount", context.get("amount", "10"))
    memo = args.get("memo", context.get("memo", ""))
    memo = memo.replace("{timestamp}", str(int(time.time())))

    if not dest:
        dest = state.wallet_address or ""
        if dest:
            console.print(f"  Sending to self for practice: [cyan]{dest}[/]")

    # F-BACKEND-B-001: after self-send fallback, dest may still be empty
    # if no wallet is available. Surface this as a structured error
    # instead of letting send_payment silently submit a payload with
    # an empty Destination field.
    if not str(dest).strip():
        raise LabException(
            LabError(
                code="INPUT_REQUIRED_FIELD",
                message="Missing required 'destination' for action 'submit_payment'.",
                hint=(
                    "Pass `destination: r...` in the module step, set context "
                    "destination, or run 'xrpl-lab wallet create' so the "
                    "self-send practice fallback has a target address."
                ),
            )
        )

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
    return context


async def handle_submit_payment_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Verify actions
# ---------------------------------------------------------------------------


async def handle_verify_tx(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Issuer wallet actions
# ---------------------------------------------------------------------------


async def handle_create_issuer_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    console.print("  Creating issuer wallet...")
    issuer = create_wallet()
    issuer_path = Path(".xrpl-lab") / "issuer_wallet.json"
    issuer_path.parent.mkdir(parents=True, exist_ok=True)
    save_wallet(issuer, issuer_path)
    console.print(f"  Issuer wallet created: [cyan]{issuer.address}[/]")
    context["issuer_seed"] = _SecretValue(issuer.seed)
    context["issuer_address"] = issuer.address
    return context


async def handle_fund_issuer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Trust line actions
# ---------------------------------------------------------------------------


async def handle_set_trust_line(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    # F-BACKEND-B-001: currency is the trust line's identity — silently
    # falling back to the default LAB when a learner intentionally
    # cleared it (e.g. typed currency: '' in the module file) lets a
    # malformed module write a real ledger object under the wrong code.
    currency = _require(
        args, context, "currency",
        action="set_trust_line",
        hint=(
            "Pass `currency: <CODE>` in the module step (e.g. LAB, USD). "
            "Currency codes are 3 characters or a 40-char hex string."
        ),
    )
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
        transport, context["wallet_seed"].get(), issuer_address, currency, limit
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
    return context


async def handle_issue_token(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    currency = args.get("currency", "LAB")
    amount = args.get("amount", "100")
    _raw_issuer = context.get("issuer_seed", "")
    issuer_seed = _raw_issuer.get() if isinstance(_raw_issuer, _SecretValue) else _raw_issuer
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
    return context


async def handle_issue_token_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    currency = args.get("currency", "DBG")
    amount = args.get("amount", "100")
    _raw_issuer = context.get("issuer_seed", "")
    issuer_seed = _raw_issuer.get() if isinstance(_raw_issuer, _SecretValue) else _raw_issuer
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
    return context


async def handle_verify_trust_line(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_remove_trust_line(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
        transport, context["wallet_seed"].get(), issuer_address, currency
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
    return context


async def handle_verify_trust_line_removed(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# DEX actions
# ---------------------------------------------------------------------------


async def handle_create_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    pays_currency = args.get("pays_currency", "LAB")
    pays_value = args.get("pays_value", "50")
    gets_currency = args.get("gets_currency", "XRP")
    gets_value = args.get("gets_value", "10")
    issuer_address = context.get("issuer_address", "")

    pays_issuer = "" if pays_currency == "XRP" else issuer_address
    gets_issuer = "" if gets_currency == "XRP" else issuer_address

    console.print(
        f"  Creating offer: pay {gets_value} {gets_currency} "
        f"to get {pays_value} {pays_currency}"
    )
    result = await create_offer(
        transport, context["wallet_seed"].get(),
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
    return context


async def handle_verify_offer_present(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_cancel_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    offer_seq = context.get("offer_sequence")

    if offer_seq is None:
        console.print(
            "  [red]No offer sequence in context. "
            "Create an offer first.[/]"
        )
        return context

    console.print(f"  Cancelling offer seq {offer_seq}...")
    result = await cancel_offer(
        transport, context["wallet_seed"].get(), offer_seq
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
    return context


async def handle_verify_offer_absent(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Reserve / snapshot actions
# ---------------------------------------------------------------------------


async def handle_snapshot_account(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_verify_reserve_change(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def handle_run_audit(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    txids = context.get("txids", [])
    if not txids:
        console.print("  [yellow]No transactions to audit yet.[/]")
        return context

    total = len(txids)
    console.print(f"  Auditing {total} transaction(s)...")

    def _audit_progress(i: int, tot: int, txid: str) -> None:
        console.print(f"[dim]  Auditing {i}/{tot}: {txid[:16]}...[/]")

    audit_report = await run_audit(transport, txids, on_progress=_audit_progress)

    console.print()
    console.print(f"  Checked: [bold]{audit_report.total}[/]")
    console.print(f"  Pass:    [green]{audit_report.passed}[/]")
    console.print(f"  Fail:    [red]{audit_report.failed}[/]")
    console.print(f"  Missing: [yellow]{audit_report.not_found}[/]")

    console.print()
    for v in audit_report.verdicts:
        icon = "[green]\u2713[/]" if v.status == "pass" else "[red]\u2717[/]"
        console.print(f"  {icon} {v.txid[:16]}... [{v.status}]")
        for check in v.checks[:3]:
            console.print(f"      {check}")
        for fail in v.failures:
            console.print(f"      [red]{fail}[/]")

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
    return context


# ---------------------------------------------------------------------------
# AMM actions
# ---------------------------------------------------------------------------


async def handle_ensure_amm_pair(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
        transport, context["wallet_seed"].get(),
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
        not_supported = getattr(create_result, 'result_code', '') in (
            'notSupported', 'temDISABLED', 'notYetImplemented',
        )
        if not_supported:
            console.print(
                "[yellow]AMM not supported on this transport. "
                "Use --dry-run to practice.[/]"
            )
            return context
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
    return context


async def handle_get_amm_info(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_amm_deposit(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    a_currency = args.get("a_currency", context.get("a_currency", "XRP"))
    # F-BACKEND-B-001: AMM deposit amount silently defaulting to "10"
    # has hit learners as "I deposited and now my proof shows a different
    # number than I expected." Require explicit amounts.
    a_value = _require(
        args, context, "a_value",
        action="amm_deposit",
        hint="Pass `a_value: <amount>` (numeric string) in the module step.",
    )
    b_currency = args.get("b_currency", context.get("b_currency", "LAB"))
    b_value = _require(
        args, context, "b_value",
        action="amm_deposit",
        hint="Pass `b_value: <amount>` (numeric string) in the module step.",
    )
    a_issuer = context.get("a_issuer", "")
    b_issuer = context.get("b_issuer", "")

    console.print(
        f"  Depositing: [cyan]{a_value} {a_currency}[/] + "
        f"[cyan]{b_value} {b_currency}[/]"
    )

    result = await amm_deposit(
        transport, context["wallet_seed"].get(),
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
    return context


async def handle_verify_lp_received(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_amm_withdraw(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    # F-BACKEND-B-001: AMM withdraw must identify the pair. Empty
    # currency on either leg lets the request reach amm_withdraw with
    # silent defaults that may not match the deposit pair the learner
    # made earlier in the same module.
    a_currency = _require(
        args, context, "a_currency",
        action="amm_withdraw",
        hint="Pass `a_currency: <CODE>` (e.g. XRP) in the module step.",
    )
    b_currency = _require(
        args, context, "b_currency",
        action="amm_withdraw",
        hint="Pass `b_currency: <CODE>` (e.g. LAB) in the module step.",
    )
    a_issuer = context.get("a_issuer", "")
    b_issuer = context.get("b_issuer", "")
    # lp_value is intentionally optional: empty means "withdraw all LP".
    lp_value = args.get("lp_value", "")

    console.print(
        f"  Withdrawing from AMM: "
        f"[cyan]{a_currency}[/] / [cyan]{b_currency}[/]"
    )
    if not lp_value:
        console.print("  (returning all LP tokens)")

    result = await amm_withdraw(
        transport, context["wallet_seed"].get(),
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
    return context


async def handle_verify_withdrawal(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


# ---------------------------------------------------------------------------
# Strategy actions
# ---------------------------------------------------------------------------


async def handle_snapshot_position(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_strategy_offer_bid(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
        transport, context["wallet_seed"].get(),
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
    return context


async def handle_strategy_offer_ask(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
        transport, context["wallet_seed"].get(),
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
    return context


async def handle_verify_module_offers(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_cancel_module_offers(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    seqs = context.get("strategy_offer_sequences", [])

    if not seqs:
        console.print("  [yellow]No strategy offers to cancel.[/]")
        return context

    console.print(f"  Cancelling {len(seqs)} offer(s)...")
    results = await cancel_module_offers(
        transport, context["wallet_seed"].get(), seqs,
    )

    cancelled = 0
    for seq, success in results:
        if success:
            console.print(f"  [green]\u2713[/] Offer seq {seq} cancelled")
            cancelled += 1
        else:
            console.print(f"  [red]\u2717[/] Offer seq {seq} cancel failed")

    for seq, success in results:
        if success:
            state.record_tx(
                txid=f"synthetic-cancel-{seq}",
                module_id=context.get("module_id", ""),
                network=state.network,
                success=True,
            )
    save_state(state)
    context["offers_cancelled"] = cancelled
    context["strategy_offer_sequences"] = []
    return context


async def handle_verify_module_offers_absent(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    holder_address = state.wallet_address or ""

    offers = await transport.get_account_offers(holder_address)
    remaining = len(offers)

    if remaining == 0:
        console.print("  [green]\u2713 No open offers — all cleared[/]")
    else:
        console.print(
            f"  [yellow]{remaining} offer(s) still open[/]"
        )
    return context


async def handle_verify_position_delta(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
    return context


async def handle_check_inventory(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    currency = args.get("currency", "LAB")
    try:
        min_xrp = int(args.get("min_xrp_drops", "20000000"))
    except ValueError:
        console.print("[yellow]Invalid min_xrp_drops, using default[/]")
        min_xrp = 20_000_000
    try:
        min_token = Decimal(args.get("min_token", "10"))
    except (ValueError, TypeError, InvalidOperation):
        min_token = Decimal("10")
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
    return context


async def handle_place_safe_sides(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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
            transport, context["wallet_seed"].get(),
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
            transport, context["wallet_seed"].get(),
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
    return context


async def handle_hygiene_summary(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
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

    txids = context.get("txids", [])
    if txids:
        _module_id = context.get("module_id", "unknown")
        _preset_map = {
            "dex_market_making_101": "strategy_mm101",
            "dex_inventory_guardrails": "strategy_inv",
            "dex_vs_amm_risk_literacy": "strategy_compare",
        }
        _preset = _preset_map.get(_module_id, f"strategy_{_module_id[:20]}")
        run_path = write_last_run(
            txids=txids,
            module_id=_module_id,
            preset=_preset,
        )
        console.print(f"  Last run txids: [green]{run_path}[/]")
    return context


async def handle_write_report(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    # Handled at module completion in run_module
    return context


# ---------------------------------------------------------------------------
# Registration — populate the registry
# ---------------------------------------------------------------------------

def _register_all() -> None:
    """Register every action handler."""
    _actions = [
        ActionDef(
            name="ensure_wallet",
            handler=handle_ensure_wallet,
            description="Create or load a wallet",
        ),
        ActionDef(
            name="ensure_funded",
            handler=handle_ensure_funded,
            description="Fund wallet from faucet if empty",
        ),
        ActionDef(
            name="submit_payment",
            handler=handle_submit_payment,
            description="Submit an XRP payment",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="destination", description="Recipient address"),
                PayloadField(name="amount", default="10", description="XRP amount"),
                PayloadField(name="memo", description="Transaction memo"),
            ],
        ),
        ActionDef(
            name="submit_payment_fail",
            handler=handle_submit_payment_fail,
            description="Intentionally submit a failing payment",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="reason", default="bad_sequence"),
                PayloadField(name="destination"),
                PayloadField(name="amount", default="10"),
            ],
        ),
        ActionDef(
            name="verify_tx",
            handler=handle_verify_tx,
            description="Verify the last transaction on-ledger",
        ),
        ActionDef(
            name="create_issuer_wallet",
            handler=handle_create_issuer_wallet,
            description="Create a separate issuer wallet",
        ),
        ActionDef(
            name="fund_issuer",
            handler=handle_fund_issuer,
            description="Fund the issuer wallet from faucet",
        ),
        ActionDef(
            name="set_trust_line",
            handler=handle_set_trust_line,
            description="Set a trust line to an issuer",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
                PayloadField(name="limit", default="1000"),
            ],
        ),
        ActionDef(
            name="issue_token",
            handler=handle_issue_token,
            description="Issue tokens from issuer to holder",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
                PayloadField(name="amount", default="100"),
            ],
        ),
        ActionDef(
            name="issue_token_expect_fail",
            handler=handle_issue_token_expect_fail,
            description="Issue tokens expecting failure (no trust line)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="DBG"),
                PayloadField(name="amount", default="100"),
            ],
        ),
        ActionDef(
            name="verify_trust_line",
            handler=handle_verify_trust_line,
            description="Verify a trust line exists",
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
            ],
        ),
        ActionDef(
            name="remove_trust_line",
            handler=handle_remove_trust_line,
            description="Remove a trust line (set limit to 0)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="HYGIENE"),
            ],
        ),
        ActionDef(
            name="verify_trust_line_removed",
            handler=handle_verify_trust_line_removed,
            description="Verify a trust line was removed",
            payload_fields=[
                PayloadField(name="currency", default="HYGIENE"),
            ],
        ),
        ActionDef(
            name="create_offer",
            handler=handle_create_offer,
            description="Create a DEX offer",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="pays_value", default="50"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="gets_value", default="10"),
            ],
        ),
        ActionDef(
            name="verify_offer_present",
            handler=handle_verify_offer_present,
            description="Verify an offer is on the book",
        ),
        ActionDef(
            name="cancel_offer",
            handler=handle_cancel_offer,
            description="Cancel a DEX offer",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_offer_absent",
            handler=handle_verify_offer_absent,
            description="Verify an offer was cancelled",
        ),
        ActionDef(
            name="snapshot_account",
            handler=handle_snapshot_account,
            description="Snapshot account state (balance, reserves)",
            payload_fields=[
                PayloadField(name="label", default="snapshot"),
            ],
        ),
        ActionDef(
            name="verify_reserve_change",
            handler=handle_verify_reserve_change,
            description="Compare two account snapshots for reserve changes",
            payload_fields=[
                PayloadField(name="before", default="before"),
                PayloadField(name="after", default="after"),
            ],
        ),
        ActionDef(
            name="run_audit",
            handler=handle_run_audit,
            description="Audit all transactions from this module",
        ),
        ActionDef(
            name="ensure_amm_pair",
            handler=handle_ensure_amm_pair,
            description="Ensure an AMM pool exists (create if needed)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="a_currency", default="XRP"),
                PayloadField(name="a_value", default="100"),
                PayloadField(name="b_currency", default="LAB"),
                PayloadField(name="b_value", default="100"),
            ],
        ),
        ActionDef(
            name="get_amm_info",
            handler=handle_get_amm_info,
            description="Get AMM pool info",
            payload_fields=[
                PayloadField(name="a_currency"),
                PayloadField(name="b_currency"),
            ],
        ),
        ActionDef(
            name="amm_deposit",
            handler=handle_amm_deposit,
            description="Deposit into an AMM pool",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="a_currency"),
                PayloadField(name="a_value", default="10"),
                PayloadField(name="b_currency"),
                PayloadField(name="b_value", default="10"),
            ],
        ),
        ActionDef(
            name="verify_lp_received",
            handler=handle_verify_lp_received,
            description="Verify LP tokens were received",
        ),
        ActionDef(
            name="amm_withdraw",
            handler=handle_amm_withdraw,
            description="Withdraw from an AMM pool",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="a_currency"),
                PayloadField(name="b_currency"),
                PayloadField(name="lp_value", description="LP tokens to return (empty = all)"),
            ],
        ),
        ActionDef(
            name="verify_withdrawal",
            handler=handle_verify_withdrawal,
            description="Verify AMM withdrawal succeeded",
        ),
        ActionDef(
            name="snapshot_position",
            handler=handle_snapshot_position,
            description="Snapshot full trading position",
            payload_fields=[
                PayloadField(name="label", default="snapshot"),
            ],
        ),
        ActionDef(
            name="strategy_offer_bid",
            handler=handle_strategy_offer_bid,
            description="Place a strategy bid offer",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="pays_value", default="10"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="gets_value", default="1"),
                PayloadField(name="memo_action", default="OFFER_BID"),
            ],
        ),
        ActionDef(
            name="strategy_offer_ask",
            handler=handle_strategy_offer_ask,
            description="Place a strategy ask offer",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="pays_value", default="10"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="gets_value", default="2"),
                PayloadField(name="memo_action", default="OFFER_ASK"),
            ],
        ),
        ActionDef(
            name="verify_module_offers",
            handler=handle_verify_module_offers,
            description="Verify all strategy offers are on the book",
        ),
        ActionDef(
            name="cancel_module_offers",
            handler=handle_cancel_module_offers,
            description="Cancel all strategy offers from this module",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_module_offers_absent",
            handler=handle_verify_module_offers_absent,
            description="Verify all strategy offers were cancelled",
        ),
        ActionDef(
            name="verify_position_delta",
            handler=handle_verify_position_delta,
            description="Compare two position snapshots",
            payload_fields=[
                PayloadField(name="before", default="before"),
                PayloadField(name="after", default="after"),
            ],
        ),
        ActionDef(
            name="check_inventory",
            handler=handle_check_inventory,
            description="Check inventory levels for safe trading",
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
                PayloadField(name="min_xrp_drops", type="int", default="20000000"),
                PayloadField(name="min_token", type="decimal", default="10"),
            ],
        ),
        ActionDef(
            name="place_safe_sides",
            handler=handle_place_safe_sides,
            description="Place bid/ask offers respecting inventory guardrails",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="bid_value", default="10"),
                PayloadField(name="ask_value", default="10"),
                PayloadField(name="bid_price", default="1"),
                PayloadField(name="ask_price", default="2"),
            ],
        ),
        ActionDef(
            name="hygiene_summary",
            handler=handle_hygiene_summary,
            description="Generate a hygiene summary for strategy modules",
        ),
        ActionDef(
            name="write_report",
            handler=handle_write_report,
            description="Write module report (handled at completion)",
        ),
    ]

    for action_def in _actions:
        register(action_def)


# Auto-register on import
_register_all()
