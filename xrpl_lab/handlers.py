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
from .actions.did import delete_did, set_did, verify_did, verify_did_deleted
from .actions.escrow import (
    cancel_escrow,
    create_escrow,
    finish_escrow,
    verify_escrow,
    verify_escrow_finished,
)
from .actions.mpt import create_mpt_issuance, verify_mpt_issuance
from .actions.nft import (
    accept_nft_offer,
    burn_nft,
    create_nft_offer,
    get_nft_offers,
    mint_nft,
    modify_nft,
    verify_nft,
    verify_nft_burned,
    verify_nft_modified,
    verify_nft_owned_by,
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
    clawback_tokens,
    enable_clawback,
    issue_token,
    remove_trust_line,
    set_trust_line,
    verify_clawback,
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

    if result.success:
        # CORE-A-004: the failing-tx demo can unexpectedly succeed (e.g. a
        # dry-run/offline transport that doesn't simulate the chosen failure,
        # or a flaky reason). When it does, the txid MUST be recorded in
        # tx_index — otherwise it lands in the proof pack's completed-modules
        # list with no matching tx record (no explorer link, undercounts
        # total_transactions). Mirror the success branch of the other submit
        # handlers so tx_index stays the single source of truth.
        console.print(
            f"  [yellow]Unexpected success — tx confirmed "
            f"({result.result_code}). The chosen failure did not occur "
            f"on this transport.[/]"
        )
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
        save_state(state)
    else:
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
    # DD-1: this is a workspace-rooted seed file. save_wallet() will
    # call _ensure_secure_parent which tightens the parent to 0o700 —
    # that's intentional because the issuer wallet IS a secret, even
    # though the rest of the workspace is workshop-shareable. The
    # mkdir below is redundant with _ensure_secure_parent; we keep
    # it as a no-op safety net (mkdir(exist_ok=True) is idempotent
    # and the subsequent _ensure_secure_parent will do the chmod).
    # Intra-workspace tension noted for the threat-model doc — this
    # site is the one place the workspace becomes 0o700 at runtime.
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
    elif getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        # COREBCD-003: a 429 is not a transient "retry now" — re-running
        # immediately just gets rate-limited again. Mirror `cli.py fund` /
        # runtime.ensure_funded: surface the clock-cued wait guidance + the
        # --dry-run escape hatch instead of the generic retry line.
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
        console.print(f"  [dim]{err.hint}[/]")
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
        if getattr(result, "result_code", None) == "tecNO_LINE":
            console.print(
                "  [yellow]Hint: Trust lines are directional — the recipient "
                "must set up the trust line BEFORE you can send them this "
                "token. If you're issuing, run the recipient through the "
                "'set trust line' step first.[/]"
            )
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
        # VC-001 (sibling of CORE-A-004): the expect-fail token issuance can
        # unexpectedly succeed (e.g. a dry-run transport that doesn't simulate
        # the chosen failure, or a pre-existing trust line). When it does, the
        # successful txid MUST be recorded in tx_index WITH its explorer_url —
        # otherwise the proof pack lists a completed module with no matching tx
        # record (no explorer link, undercounts total_transactions). And it must
        # NOT be appended to failed_txids: a confirmed tx is not a failure.
        console.print(
            f"  [yellow]Unexpected success — {amount} {currency} "
            f"delivered. Trust line may already exist.[/]"
        )
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context.setdefault("txids", []).append(result.txid)
        state.record_tx(
            txid=result.txid or "failed",
            module_id=context.get("module_id", ""),
            network=state.network,
            success=True,
            explorer_url=result.explorer_url,
        )
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
            success=False,
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
    for seq, success, _txid in results:
        if success:
            console.print(f"  [green]\u2713[/] Offer seq {seq} cancelled")
            cancelled += 1
        else:
            console.print(f"  [red]\u2717[/] Offer seq {seq} cancel failed")

    # F-BACKEND-006: record the REAL OfferCancel txid returned by the
    # transport, not a ``synthetic-cancel-<seq>`` placeholder. A fake id
    # lands in the proof pack / certificate with a dead testnet.xrpl.org
    # explorer link and inflates tx counts. Only record when a real txid
    # is present (a successful cancel with no txid \u2014 e.g. some dry-run /
    # offline paths \u2014 is skipped rather than fabricated).
    for _seq, success, txid in results:
        if success and txid:
            state.record_tx(
                txid=txid,
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


async def handle_mint_nft(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    uri = args.get("uri", "ipfs://example/game-asset.json")
    try:
        taxon = int(args.get("taxon", "0"))
    except ValueError:
        taxon = 0
    try:
        transfer_fee = int(args.get("transfer_fee", "0"))
    except ValueError:
        transfer_fee = 0
    transferable = str(args.get("transferable", "true")).lower() != "false"
    mutable = str(args.get("mutable", "false")).lower() in ("true", "1", "yes")

    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()

    console.print(
        f"  Minting NFToken — taxon [cyan]{taxon}[/], "
        f"transferable [cyan]{transferable}[/], mutable [cyan]{mutable}[/], "
        f"uri [cyan]{uri}[/]"
    )
    if transfer_fee:
        console.print(f"  Royalty (TransferFee): {transfer_fee / 1000:.3f}%")
    result = await mint_nft(transport, seed, uri, taxon, transfer_fee, transferable, mutable)

    if result.success:
        console.print("  [green]NFToken minted![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.nft_id:
            console.print(f"  NFTokenID: [cyan]{result.nft_id}[/]")
            context["nft_id"] = result.nft_id
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
        console.print(f"  [red]Mint failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
        state.record_tx(
            txid=result.txid or "failed",
            module_id=context.get("module_id", ""),
            network=state.network,
            success=False,
        )
    save_state(state)
    return context


async def handle_verify_nft(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context

    expected = context.get("nft_id")
    result = await verify_nft(transport, address, expected_nft_id=expected)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]NFT ownership verified on-ledger.[/]")
    context["last_nft_verify"] = result
    return context


async def handle_burn_nft(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    # Resolve the NFTokenID: an explicit module arg wins, else the one captured
    # at mint, else the most recently owned NFT on-ledger (so the module flows
    # mint -> verify -> burn without the author pasting an id).
    nft_id = step.action_args.get("nftoken_id", "") or context.get("nft_id", "")
    if not nft_id:
        owned = await transport.get_account_nfts(state.wallet_address or "")
        if owned:
            nft_id = owned[-1].nft_id
    if not nft_id:
        console.print(
            "  [red]No NFToken to burn — run the mint step first so an "
            "NFTokenID is captured.[/]"
        )
        return context
    console.print(f"  Burning NFToken [cyan]{nft_id[:24]}...[/]")
    result = await burn_nft(transport, seed, nft_id)
    if result.success:
        console.print("  [green]NFToken burned — destroyed, reserve freed![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["burned_nft_id"] = nft_id
    else:
        console.print(f"  [red]NFTokenBurn failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_nft_burned(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    nft_id = context.get("burned_nft_id") or context.get("nft_id")
    result = await verify_nft_burned(transport, address, nftoken_id=nft_id)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]NFT lifecycle complete — asset destroyed, reserve freed.[/]")
    context["last_nft_burned_verify"] = result
    return context


_RIPPLE_EPOCH = 946684800  # seconds between Unix epoch and Ripple epoch (2000-01-01)


def _explain_failure(console: Console, result_code: str) -> None:
    """Print the Category/Meaning/Action triplet for a failing result_code.

    COREBCD-006: the KB-sourced create handlers (mint_nft / create_escrow /
    set_did / create_mpt_issuance) previously printed only the bare
    ``result.error`` on failure. Older handlers (e.g.
    handle_issue_token_expect_fail) route the code through
    ``explain_result_code`` so every failing tx teaches its XRPL concept
    inline. This shared helper gives the create handlers the same treatment.
    """
    if not result_code:
        return
    from .doctor import explain_result_code

    info = explain_result_code(result_code)
    console.print(f"  Category: [cyan]{info['category']}[/]")
    console.print(f"  Meaning: {info['meaning']}")
    console.print(f"  Action: [yellow]{info['action']}[/]")


def _record_submit(state: LabState, context: dict, result) -> None:
    """Record a submission outcome to state + context (shared by the create handlers)."""
    if result.success:
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)


async def handle_create_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    amount = args.get("amount", "10")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    destination = args.get("destination") or state.wallet_address or ""
    try:
        delay = int(args.get("finish_seconds", "120"))
    except ValueError:
        delay = 120
    finish_after = int(time.time()) - _RIPPLE_EPOCH + delay
    cancel_after = finish_after + 86400
    console.print(f"  Creating time-based escrow: [cyan]{amount}[/] XRP, finishable in ~{delay}s")
    result = await create_escrow(transport, seed, amount, destination, finish_after, cancel_after)
    if result.success:
        console.print("  [green]Escrow created![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        # Capture the create-sequence (OfferSequence for finish/cancel) and the
        # owner so a later finish_escrow / cancel_escrow step can consume them.
        # Both transports populate EscrowInfo.sequence (TRANSPORT-A-003), so we
        # read it back from the ledger rather than guessing.
        owner = state.wallet_address or ""
        escrows = await transport.get_escrows(owner)
        if escrows:
            seq = escrows[-1].sequence
            context["escrow_owner"] = owner
            context["escrow_destination"] = destination
            context["escrow_finish_after"] = finish_after
            context["escrow_cancel_after"] = cancel_after
            if seq:
                context["escrow_sequence"] = seq
                console.print(f"  Escrow create-sequence: [cyan]{seq}[/]")
    else:
        console.print(f"  [red]Escrow failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    result = await verify_escrow(transport, address)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]Escrow verified on-ledger.[/]")
    context["last_escrow_verify"] = result
    return context


def _resolve_escrow_target(state: LabState, context: dict) -> tuple[str, int | None]:
    """Resolve (owner, offer_sequence) for an escrow finish/cancel step.

    Owner defaults to the learner's own wallet (escrow-to-self is the module
    pattern); the create-sequence comes from context, populated by
    handle_create_escrow when it read the escrow back from the ledger.
    """
    owner = context.get("escrow_owner") or state.wallet_address or ""
    seq = context.get("escrow_sequence")
    return owner, seq


async def handle_finish_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    owner, seq = _resolve_escrow_target(state, context)
    if not owner or seq is None:
        console.print(
            "  [red]No escrow to finish — run the create-escrow step first "
            "so its create-sequence is captured.[/]"
        )
        return context
    console.print(f"  Finishing escrow (owner {owner[:12]}..., OfferSequence {seq})...")
    result = await finish_escrow(transport, seed, owner, seq)
    if result.success:
        console.print("  [green]Escrow finished — funds released to destination![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]EscrowFinish failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_cancel_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    owner, seq = _resolve_escrow_target(state, context)
    if not owner or seq is None:
        console.print(
            "  [red]No escrow to cancel — run the create-escrow step first "
            "so its create-sequence is captured.[/]"
        )
        return context
    console.print(f"  Cancelling escrow (owner {owner[:12]}..., OfferSequence {seq})...")
    result = await cancel_escrow(transport, seed, owner, seq)
    if result.success:
        console.print("  [green]Escrow cancelled — funds reclaimed by owner![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]EscrowCancel failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_escrow_finished(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = context.get("escrow_owner") or state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    seq = context.get("escrow_sequence")
    result = await verify_escrow_finished(transport, address, offer_sequence=seq)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Escrow lifecycle complete — reserve freed.[/]")
    context["last_escrow_finished_verify"] = result
    return context


async def handle_set_did(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    uri = args.get("uri", "did:xrpl:example")
    data = args.get("data", "")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    console.print(f"  Setting DID — uri [cyan]{uri}[/]")
    result = await set_did(transport, seed, uri, data)
    if result.success:
        console.print("  [green]DID set![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["did_uri"] = uri
    else:
        console.print(f"  [red]DIDSet failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_did(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    result = await verify_did(transport, address, expected_uri=context.get("did_uri"))
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]DID verified on-ledger.[/]")
    context["last_did_verify"] = result
    return context


async def handle_delete_did(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    console.print("  Deleting DID — revoking on-ledger identity...")
    result = await delete_did(transport, seed)
    if result.success:
        console.print("  [green]DID deleted — identity revoked, reserve freed![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]DIDDelete failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_did_deleted(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    result = await verify_did_deleted(transport, address)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Identity hygiene complete — DID removed.[/]")
    context["last_did_deleted_verify"] = result
    return context


async def handle_create_mpt_issuance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    maximum_amount = args.get("maximum_amount", "1000000")
    try:
        asset_scale = int(args.get("asset_scale", "0"))
    except ValueError:
        asset_scale = 0
    try:
        transfer_fee = int(args.get("transfer_fee", "0"))
    except ValueError:
        transfer_fee = 0
    transferable = str(args.get("transferable", "true")).lower() != "false"
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    console.print(f"  Creating MPT issuance — max supply [cyan]{maximum_amount}[/], "
                  f"scale [cyan]{asset_scale}[/], transferable [cyan]{transferable}[/]")
    result = await create_mpt_issuance(
        transport, seed, maximum_amount, asset_scale, transfer_fee, transferable
    )
    if result.success:
        console.print("  [green]MPT issuance created![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["mpt_max"] = str(maximum_amount)
    else:
        console.print(f"  [red]MPT issuance failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_mpt_issuance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        return context
    result = await verify_mpt_issuance(transport, address, expected_maximum=context.get("mpt_max"))
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]MPT issuance verified on-ledger.[/]")
    context["last_mpt_verify"] = result
    return context


# ---------------------------------------------------------------------------
# Clawback actions (tokens track) — issuer recall (XLS-39)
# ---------------------------------------------------------------------------


async def handle_enable_clawback(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Enable asfAllowTrustLineClawback on the issuer BEFORE issuing tokens."""
    _raw_issuer = context.get("issuer_seed", "")
    issuer_seed = _raw_issuer.get() if isinstance(_raw_issuer, _SecretValue) else _raw_issuer
    if not issuer_seed:
        console.print("  [red]No issuer wallet in context. Run the issuer step first.[/]")
        return context
    issuer_address = context.get("issuer_address", "")
    console.print(
        "  Enabling clawback on the issuer "
        "([cyan]asfAllowTrustLineClawback[/]) — must precede any issuance..."
    )
    result = await enable_clawback(transport, issuer_seed, issuer_address)
    if result.success:
        console.print("  [green]Clawback enabled on the issuer.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["clawback_enabled"] = True
    else:
        console.print(f"  [red]Enabling clawback failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_snapshot_token_balance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Capture the holder's trust-line balance for a currency (clawback before/after)."""
    args = step.action_args
    currency = args.get("currency", "LAB")
    label = args.get("label", "before")
    holder_address = state.wallet_address or ""
    issuer_address = context.get("issuer_address", "")
    if not holder_address:
        console.print("  [red]No wallet address found.[/]")
        return context
    lines = await transport.get_trust_lines(holder_address)
    bal = "0"
    for tl in lines:
        if tl.currency == currency and (not issuer_address or tl.peer == issuer_address):
            bal = tl.balance
            break
    context[f"token_balance_{label}"] = bal
    console.print(f"  Holder {currency} balance ({label}): [cyan]{bal}[/]")
    return context


async def handle_clawback(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Forcibly recall a portion of issued tokens from the holder (Clawback)."""
    args = step.action_args
    currency = args.get("currency", "LAB")
    amount = args.get("amount", "30")
    _raw_issuer = context.get("issuer_seed", "")
    issuer_seed = _raw_issuer.get() if isinstance(_raw_issuer, _SecretValue) else _raw_issuer
    issuer_address = context.get("issuer_address", "")
    holder_address = state.wallet_address or ""
    if not issuer_seed or not holder_address:
        console.print("  [red]Missing issuer or holder wallet. Run previous steps first.[/]")
        return context
    console.print(
        f"  Clawing back [cyan]{amount} {currency}[/] from holder "
        f"[cyan]{holder_address[:12]}...[/]"
    )
    console.print(
        "  [dim]XRPL quirk: the Clawback Amount.issuer field carries the "
        "HOLDER address, not the issuer.[/]"
    )
    result = await clawback_tokens(
        transport, issuer_seed, holder_address, currency, amount, issuer_address
    )
    if result.success:
        console.print("  [green]Clawback succeeded — tokens recalled to the issuer.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["clawback_currency"] = currency
        context["clawback_amount"] = amount
    else:
        console.print(f"  [red]Clawback failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_clawback(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify the holder's balance dropped by exactly the clawed amount."""
    args = step.action_args
    currency = args.get("currency", context.get("clawback_currency", "LAB"))
    before = context.get("token_balance_before", "0")
    clawed = context.get("clawback_amount", args.get("amount", "30"))
    holder_address = state.wallet_address or ""
    issuer_address = context.get("issuer_address", "")
    if not holder_address:
        console.print("  [red]No wallet address found.[/]")
        return context
    result = await verify_clawback(
        transport, holder_address, currency, issuer_address, before, clawed
    )
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Issuer recall verified — exact-amount debit confirmed.[/]")
    context["last_clawback_verify"] = result
    return context


async def handle_clawback_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attempt a clawback against an issuer that NEVER enabled the flag (tec).

    Uses a dedicated second issuer that issued tokens WITHOUT first setting
    asfAllowTrustLineClawback, so the recall is refused — the failure-literacy
    half of the lesson. The result code routes through explain_result_code.
    """
    args = step.action_args
    currency = args.get("currency", context.get("noclaw_currency", "NOC"))
    amount = args.get("amount", "10")
    _raw = context.get("noclaw_issuer_seed", "")
    issuer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    issuer_address = context.get("noclaw_issuer_address", "")
    holder_address = state.wallet_address or ""
    if not issuer_seed or not holder_address:
        console.print("  [red]Missing no-clawback issuer or holder. Run previous steps first.[/]")
        return context
    console.print(
        f"  [yellow]Attempting clawback of {amount} {currency} from an issuer "
        f"that never enabled the flag (expecting failure)...[/]"
    )
    result = await clawback_tokens(
        transport, issuer_seed, holder_address, currency, amount, issuer_address
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — this issuer should have lacked the "
            "clawback flag. Verify the issuance order.[/]"
        )
        _record_submit(state, context, result)
    else:
        console.print(f"  [green]Expected failure:[/] {result.result_code}")
        console.print(f"  Error: {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
        save_state(state)
    return context


async def handle_create_noclaw_issuer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund a SECOND issuer that does NOT enable clawback, then issue.

    Sets up the clawback-without-flag failure case: this issuer issues a token
    to the holder having never set asfAllowTrustLineClawback, so a later
    clawback attempt is refused with a tec error.
    """
    args = step.action_args
    currency = args.get("currency", "NOC")
    amount = args.get("amount", "50")
    console.print("  Creating a second issuer (no clawback flag)...")
    issuer = create_wallet()
    fund = await transport.fund_from_faucet(issuer.address)
    if not fund.success and getattr(fund, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    context["noclaw_issuer_seed"] = _SecretValue(issuer.seed)
    context["noclaw_issuer_address"] = issuer.address
    context["noclaw_currency"] = currency
    # Holder trusts this issuer, then it issues tokens (no clawback flag set).
    holder_seed = context["wallet_seed"].get()
    await set_trust_line(transport, holder_seed, issuer.address, currency, "1000")
    issue = await issue_token(
        transport, issuer.seed, state.wallet_address or "",
        currency, issuer.address, amount,
        memo=f"XRPLLAB|ISSUE|{currency}|{amount}",
    )
    if issue.success:
        console.print(
            f"  [green]Issued {amount} {currency} from a no-clawback issuer.[/]"
        )
    else:
        console.print(f"  [yellow]Issuance setup note: {issue.error}[/]")
    return context


# ---------------------------------------------------------------------------
# NFT marketplace + dynamic-NFT actions (nfts track)
# ---------------------------------------------------------------------------


async def handle_create_buyer_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund a second wallet to act as the marketplace counterparty."""
    console.print("  Creating a second player wallet (buyer/reseller)...")
    buyer = create_wallet()
    fund = await transport.fund_from_faucet(buyer.address)
    if fund.success:
        console.print(f"  Buyer funded: [cyan]{buyer.address}[/] ({fund.balance} XRP)")
    elif getattr(fund, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    else:
        console.print(f"  [yellow]Buyer funding note: {fund.message}[/]")
    context["buyer_seed"] = _SecretValue(buyer.seed)
    context["buyer_address"] = buyer.address
    return context


async def handle_list_nft_sell_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """List the caller's NFT for sale (NFTokenCreateOffer, tfSellNFToken).

    ``seller`` arg selects whose wallet signs: "creator" (the learner's wallet,
    the issuer — first sale) or "buyer" (the second wallet — a resale that
    triggers the issuer royalty). Directed to a counterparty so the dry-run
    transport can settle ownership deterministically (testnet uses the signer).
    """
    args = step.action_args
    nft_id = context.get("nft_id", "")
    amount = args.get("amount", "100")
    seller_role = args.get("seller", "creator")
    if not nft_id:
        console.print("  [red]No NFTokenID in context. Mint an NFT first.[/]")
        return context

    if seller_role == "buyer":
        _raw = context.get("buyer_seed", "")
        seller_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
        seller_addr = context.get("buyer_address", "")
        # Resale: directed back to the creator so the creator (issuer) re-acquires
        # it and we can observe the protocol royalty leaving the reseller.
        dest = state.wallet_address or ""
    else:
        seller_seed = context["wallet_seed"].get()
        seller_addr = state.wallet_address or ""
        # First sale: directed to the second player (buyer).
        dest = context.get("buyer_address", "")

    if not seller_seed:
        console.print("  [red]Missing seller wallet for this offer.[/]")
        return context

    console.print(
        f"  Listing NFT for sale: [cyan]{amount} XRP[/] "
        f"(seller [cyan]{seller_role}[/], to [cyan]{dest[:12]}...[/])"
    )
    result = await create_nft_offer(
        transport, seller_seed, nft_id, amount,
        sell=True, destination=dest, owner=seller_addr,
    )
    if result.success:
        console.print("  [green]Sell offer listed![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.nft_offer_index:
            context["nft_sell_offer"] = result.nft_offer_index
            console.print(f"  Offer index: [cyan]{result.nft_offer_index[:24]}...[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["nft_offer_price"] = amount
        context["nft_offer_seller_role"] = seller_role
    else:
        console.print(f"  [red]Sell offer failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_nft_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Read the NFT's open sell offers back from the ledger (nft_sell_offers)."""
    nft_id = context.get("nft_id", "")
    if not nft_id:
        console.print("  [red]No NFTokenID in context.[/]")
        return context
    offers = await get_nft_offers(transport, nft_id, sell=True)
    if offers:
        for o in offers:
            console.print(
                f"  [green]Sell offer:[/] {o.amount} "
                f"(index {o.offer_index[:16]}...)"
            )
        console.print(f"  [green]{len(offers)} open sell offer(s) on the book.[/]")
    else:
        console.print("  [yellow]No open sell offers for this NFT.[/]")
    context["last_nft_offers"] = offers
    return context


async def handle_accept_nft_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Accept the open sell offer, settling the trade (NFTokenAcceptOffer).

    ``buyer`` arg selects the accepting wallet: "buyer" (the second player, a
    first purchase) or "creator" (the learner's wallet buying back a resale).
    """
    args = step.action_args
    buyer_role = args.get("buyer", "buyer")
    sell_offer = context.get("nft_sell_offer", "")
    if not sell_offer:
        console.print("  [red]No sell offer in context. List one first.[/]")
        return context

    if buyer_role == "creator":
        buyer_seed = context["wallet_seed"].get()
        buyer_addr = state.wallet_address or ""
    else:
        _raw = context.get("buyer_seed", "")
        buyer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
        buyer_addr = context.get("buyer_address", "")

    if not buyer_seed:
        console.print("  [red]Missing buyer wallet to accept the offer.[/]")
        return context

    # Capture issuer balance before, so we can show the royalty arriving.
    issuer_addr = state.wallet_address or ""
    issuer_before = await transport.get_balance(issuer_addr)

    console.print(
        f"  Accepting sell offer as [cyan]{buyer_role}[/] "
        f"([cyan]{buyer_addr[:12]}...[/])..."
    )
    result = await accept_nft_offer(transport, buyer_seed, sell_offer=sell_offer)
    if result.success:
        console.print("  [green]Trade settled — NFT ownership transferred![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["nft_buyer_address"] = buyer_addr
        context["nft_seller_address"] = (
            issuer_addr if context.get("nft_offer_seller_role") == "buyer"
            else context.get("buyer_address", "")
        )
        # Re-read the issuer balance to surface the royalty delta (resale only).
        issuer_after = await transport.get_balance(issuer_addr)
        context["nft_issuer_balance_before"] = issuer_before
        context["nft_issuer_balance_after"] = issuer_after
        # The seller for THIS offer is whoever listed it.
        seller_role = context.get("nft_offer_seller_role", "creator")
        context["nft_prev_owner"] = (
            context.get("buyer_address", "") if seller_role == "buyer"
            else issuer_addr
        )
        # The offer is consumed.
        context.pop("nft_sell_offer", None)
    else:
        console.print(f"  [red]Accept failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_accept_nft_offer_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Accept a nonexistent NFTokenOffer (tec) — failure-literacy path."""
    bogus = step.action_args.get("offer_index", "0" * 64)
    buyer_seed = context["wallet_seed"].get()
    console.print(
        "  [yellow]Attempting to accept a nonexistent offer (expecting failure)...[/]"
    )
    result = await accept_nft_offer(transport, buyer_seed, sell_offer=bogus)
    if result.success:
        console.print("  [yellow]Unexpected success — the offer index resolved.[/]")
        _record_submit(state, context, result)
    else:
        console.print(f"  [green]Expected failure:[/] {result.result_code}")
        console.print(f"  Error: {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_verify_nft_trade(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify ownership transferred AND (on a resale) the royalty reached the issuer."""
    nft_id = context.get("nft_id", "")
    buyer_addr = context.get("nft_buyer_address", "")
    prev_owner = context.get("nft_prev_owner", "")
    if not nft_id or not buyer_addr:
        console.print("  [red]No completed trade in context.[/]")
        return context

    result = await verify_nft_owned_by(
        transport, buyer_addr, nft_id, previous_owner=prev_owner
    )
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")

    # Royalty observation (resale only — first sale from the issuer pays none).
    before = context.get("nft_issuer_balance_before")
    after = context.get("nft_issuer_balance_after")
    if before is not None and after is not None:
        try:
            delta = Decimal(str(after)) - Decimal(str(before))
        except (InvalidOperation, ValueError):
            delta = Decimal("0")
        if delta > 0:
            console.print(
                f"  [green]Royalty (TransferFee) paid to issuer: "
                f"+{delta} XRP — protocol-enforced creator royalty.[/]"
            )
        else:
            console.print(
                "  [dim]No royalty on this hop (first sale from the issuer pays "
                "none; the TransferFee is enforced on resales).[/]"
            )
    if result.passed:
        console.print("  [green]NFT trade verified on-ledger.[/]")
    context["last_nft_trade_verify"] = result
    return context


async def handle_modify_nft(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Change a mutable NFT's URI (NFTokenModify) — level up / evolve a game item."""
    args = step.action_args
    uri = args.get("uri", "ipfs://example/item-level-2.json")
    nft_id = step.action_args.get("nftoken_id", "") or context.get("nft_id", "")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    if not nft_id:
        console.print("  [red]No NFTokenID in context. Mint a mutable NFT first.[/]")
        return context
    seed = context["wallet_seed"].get()
    console.print(
        f"  Modifying NFToken [cyan]{nft_id[:24]}...[/] — new URI [cyan]{uri}[/]"
    )
    result = await modify_nft(transport, seed, nft_id, uri)
    if result.success:
        console.print("  [green]NFToken modified — item leveled up (same NFTokenID)![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["nft_modified_uri"] = uri
    else:
        console.print(f"  [red]NFTokenModify failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_modify_nft_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attempt to modify a NON-mutable NFT (tec) — failure-literacy path.

    Mints a fresh NFT WITHOUT tfMutable, then tries to change its URI; XRPL
    refuses because the URI was permanent at mint.
    """
    args = step.action_args
    uri = args.get("uri", "ipfs://example/cannot-change.json")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    seed = context["wallet_seed"].get()
    console.print("  Minting a NON-mutable NFT to demonstrate the failure case...")
    mint = await mint_nft(transport, seed, "ipfs://example/fixed.json", taxon=0, mutable=False)
    if not mint.success or not mint.nft_id:
        console.print(f"  [yellow]Setup mint note: {mint.error}[/]")
        return context
    console.print(
        "  [yellow]Attempting to modify the non-mutable NFT (expecting failure)...[/]"
    )
    result = await modify_nft(transport, seed, mint.nft_id, uri)
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the NFT should not be mutable.[/]"
        )
        _record_submit(state, context, result)
    else:
        console.print(f"  [green]Expected failure:[/] {result.result_code}")
        console.print(f"  Error: {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_verify_nft_modified(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify the NFT's URI advanced on the SAME NFTokenID."""
    address = state.wallet_address or ""
    nft_id = context.get("nft_id", "")
    expected = context.get("nft_modified_uri", "")
    if not address or not nft_id or not expected:
        console.print("  [red]No modified NFT in context. Run the modify step first.[/]")
        return context
    result = await verify_nft_modified(transport, address, nft_id, expected)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Dynamic NFT verified — item evolved on-ledger.[/]")
    context["last_nft_modified_verify"] = result
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
            name="mint_nft",
            handler=handle_mint_nft,
            description="Mint an NFToken (a game asset)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="uri", default="ipfs://example/game-asset.json",
                             description="Metadata URI for the asset"),
                PayloadField(name="taxon", type="int", default="0",
                             description="Collection id (issuer+taxon = collection)"),
                PayloadField(name="transfer_fee", type="int", default="0",
                             description="Royalty 0-50000 (0.001% steps); needs transferable"),
                PayloadField(name="transferable", type="bool", default="true",
                             description="Whether the NFT can be traded"),
                PayloadField(name="mutable", type="bool", default="false",
                             description="tfMutable — allow the URI to change later (XLS-46)"),
            ],
        ),
        ActionDef(
            name="verify_nft",
            handler=handle_verify_nft,
            description="Verify NFToken ownership on-ledger",
        ),
        ActionDef(
            name="burn_nft",
            handler=handle_burn_nft,
            description="Burn an NFToken (NFTokenBurn) — destroy asset, free reserve",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="nftoken_id",
                             description="NFTokenID to burn (defaults to last minted)"),
            ],
        ),
        ActionDef(
            name="verify_nft_burned",
            handler=handle_verify_nft_burned,
            description="Verify an NFToken was burned (gone, reserve freed)",
        ),
        ActionDef(
            name="create_escrow",
            handler=handle_create_escrow,
            description="Create a time-based XRP escrow",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP to escrow"),
                PayloadField(name="destination", description="Recipient (defaults to self)"),
                PayloadField(name="finish_seconds", type="int", default="120",
                             description="Seconds until the escrow becomes finishable"),
            ],
        ),
        ActionDef(
            name="verify_escrow",
            handler=handle_verify_escrow,
            description="Verify an escrow exists on-ledger",
        ),
        ActionDef(
            name="finish_escrow",
            handler=handle_finish_escrow,
            description="Finish a time-based escrow past FinishAfter (EscrowFinish)",
            wallet_required=True,
        ),
        ActionDef(
            name="cancel_escrow",
            handler=handle_cancel_escrow,
            description="Cancel an escrow past CancelAfter, reclaiming funds (EscrowCancel)",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_escrow_finished",
            handler=handle_verify_escrow_finished,
            description="Verify an escrow was finished/cancelled (object gone, reserve freed)",
        ),
        ActionDef(
            name="set_did",
            handler=handle_set_did,
            description="Set a Decentralized Identifier (DIDSet)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="uri", default="did:xrpl:example", description="DID URI"),
                PayloadField(name="data", description="Optional DID data"),
            ],
        ),
        ActionDef(
            name="verify_did",
            handler=handle_verify_did,
            description="Verify the account's DID on-ledger",
        ),
        ActionDef(
            name="delete_did",
            handler=handle_delete_did,
            description="Delete the account's DID (DIDDelete) — revoke identity, free reserve",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_did_deleted",
            handler=handle_verify_did_deleted,
            description="Verify the account's DID was deleted (gone, reserve freed)",
        ),
        ActionDef(
            name="create_mpt_issuance",
            handler=handle_create_mpt_issuance,
            description="Create a Multi-Purpose Token issuance",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="maximum_amount", default="1000000", description="Max supply"),
                PayloadField(name="asset_scale", type="int", default="0", description="Decimals"),
                PayloadField(name="transfer_fee", type="int", default="0",
                             description="Royalty 0-50000; needs transferable"),
                PayloadField(name="transferable", type="bool", default="true",
                             description="Whether holders can transfer"),
            ],
        ),
        ActionDef(
            name="verify_mpt_issuance",
            handler=handle_verify_mpt_issuance,
            description="Verify an MPT issuance on-ledger",
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
        # ── v2.0.0 game-economy control: clawback (tokens track) ──
        ActionDef(
            name="enable_clawback",
            handler=handle_enable_clawback,
            description="Enable issuer clawback (AccountSet asfAllowTrustLineClawback)",
            wallet_required=True,
        ),
        ActionDef(
            name="snapshot_token_balance",
            handler=handle_snapshot_token_balance,
            description="Snapshot a holder's trust-line balance for a currency",
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
                PayloadField(name="label", default="before"),
            ],
        ),
        ActionDef(
            name="clawback",
            handler=handle_clawback,
            description="Forcibly recall issued tokens from a holder (Clawback, XLS-39)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
                PayloadField(name="amount", default="30", description="Amount to claw back"),
            ],
        ),
        ActionDef(
            name="verify_clawback",
            handler=handle_verify_clawback,
            description="Verify the holder's balance dropped by exactly the clawed amount",
            payload_fields=[
                PayloadField(name="currency", default="LAB"),
            ],
        ),
        ActionDef(
            name="create_noclaw_issuer",
            handler=handle_create_noclaw_issuer,
            description="Create a second issuer WITHOUT clawback (sets up the failure case)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="NOC"),
                PayloadField(name="amount", default="50"),
            ],
        ),
        ActionDef(
            name="clawback_expect_fail",
            handler=handle_clawback_expect_fail,
            description="Attempt clawback without the flag (expects a tec error)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="NOC"),
                PayloadField(name="amount", default="10"),
            ],
        ),
        # ── v2.0.0 game-economy control: NFT marketplace (nfts track) ──
        ActionDef(
            name="create_buyer_wallet",
            handler=handle_create_buyer_wallet,
            description="Create + fund a second player wallet (marketplace counterparty)",
        ),
        ActionDef(
            name="list_nft_sell_offer",
            handler=handle_list_nft_sell_offer,
            description="List an NFT for sale (NFTokenCreateOffer, tfSellNFToken)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="100", description="Sale price in XRP"),
                PayloadField(name="seller", default="creator",
                             description="Whose wallet signs: creator | buyer"),
            ],
        ),
        ActionDef(
            name="verify_nft_offer",
            handler=handle_verify_nft_offer,
            description="Read the NFT's open sell offers on-ledger",
        ),
        ActionDef(
            name="accept_nft_offer",
            handler=handle_accept_nft_offer,
            description="Accept a sell offer, settling the trade (NFTokenAcceptOffer)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="buyer", default="buyer",
                             description="Whose wallet accepts: buyer | creator"),
            ],
        ),
        ActionDef(
            name="accept_nft_offer_expect_fail",
            handler=handle_accept_nft_offer_expect_fail,
            description="Accept a nonexistent NFT offer (expects a tec error)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="offer_index", description="Bogus offer index"),
            ],
        ),
        ActionDef(
            name="verify_nft_trade",
            handler=handle_verify_nft_trade,
            description="Verify NFT ownership transferred + royalty paid to issuer",
        ),
        # ── v2.0.0 game-economy control: dynamic NFT (nfts track) ──
        ActionDef(
            name="modify_nft",
            handler=handle_modify_nft,
            description="Change a mutable NFT's URI (NFTokenModify) — level up an item",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="uri", default="ipfs://example/item-level-2.json",
                             description="New metadata URI (the item's new state)"),
                PayloadField(name="nftoken_id",
                             description="NFTokenID to modify (defaults to last minted)"),
            ],
        ),
        ActionDef(
            name="modify_nft_expect_fail",
            handler=handle_modify_nft_expect_fail,
            description="Modify a non-mutable NFT (expects a tec error)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="uri", default="ipfs://example/cannot-change.json"),
            ],
        ),
        ActionDef(
            name="verify_nft_modified",
            handler=handle_verify_nft_modified,
            description="Verify the NFT's URI advanced on the same NFTokenID",
        ),
    ]

    for action_def in _actions:
        register(action_def)


# Auto-register on import
_register_all()
