"""Action handlers — each action extracted as a registered handler.

Import this module to populate the registry. All handlers follow the
uniform signature::

    async def handle_*(step, state, transport, wallet_seed, context, console) -> dict
"""

from __future__ import annotations

import asyncio
import logging
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
from .actions.credentials import (
    accept_credential,
    create_credential,
    delete_credential,
    verify_credential,
)
from .actions.custodial import (
    credit_player_deposit,
    enable_require_dest,
    send_tagged_deposit,
)
from .actions.deposit_gate import (
    authorize_deposit_address,
    authorize_deposit_credential,
    enable_deposit_auth,
    get_credential_id,
    send_gated_payment,
    unauthorize_deposit_address,
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
from .actions.freeze import set_global_freeze, set_individual_freeze, verify_freeze
from .actions.mpt import (
    authorize_mpt,
    create_mpt_issuance,
    send_mpt,
    verify_mpt_balance,
    verify_mpt_issuance,
)
from .actions.multisig import (
    delete_signer_list,
    send_multisig_payment,
    set_signer_list,
    verify_signer_list,
)
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
from .actions.partial_payment import (
    send_partial_payment,
    verify_delivered_amount,
)
from .actions.paychan import (
    check_claim,
    fund_channel,
    open_channel,
    redeem_claim,
    sign_claim,
    verify_channel,
)
from .actions.permissioned_domains import (
    create_permissioned_offer,
    delete_permissioned_domain,
    set_permissioned_domain,
    verify_domain,
    verify_permissioned_offer,
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
from .actions.token_escrow import (
    create_token_escrow,
    set_allow_trustline_locking,
    verify_token_moved,
)
from .actions.token_escrow import finish_escrow as finish_token_escrow
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

logger = logging.getLogger(__name__)


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


def _record_verification(
    context: dict,
    action: str,
    passed: bool,
    failures: list | None = None,
) -> None:
    """Append this verify handler's pass/fail verdict to ``context``.

    RESWARM3 (verified flag + honest pack): before this, every ``handle_verify_*``
    handler printed its checks/failures to the console but signalled NOTHING to
    the runner — so a module whose on-ledger verification FAILED still recorded
    as a green "completed" module and the proof pack claimed a verification that
    never passed. This helper is the single, uniform channel every verify
    handler now uses to report its REAL verdict. The runner
    (``run_module``) inspects ``context["verifications"]`` after each step,
    flips that step's ``on_step_complete`` success to False on any failure, and
    marks the module ``verified=False`` in state so the pack is honest.

    Entry shape (kept minimal — no secrets, JSON-serializable): each append is
    ``{"action": action, "passed": bool, "failures": list}``. ``passed`` is the
    handler's real verdict (``len(failures) == 0`` for assertion handlers). The
    two comparison-only handlers (verify_reserve_change / verify_position_delta)
    have no pass/fail concept — they teach OBSERVATION, not assertion — so they
    record ``passed=True`` (informational) and never fabricate a failure.
    """
    context.setdefault("verifications", []).append(
        {
            "action": action,
            "passed": bool(passed),
            "failures": list(failures or []),
        }
    )


async def handle_verify_tx(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    txid = context.get("txids", [""])[-1] if context.get("txids") else ""
    if not txid:
        console.print("  [red]No transaction to verify yet.[/]")
        # FT-001: a verify step that could not run (no txid to check because a
        # prior step never produced one) is an honest FAILED verification, not an
        # invisible skip — otherwise the module stays vacuously verified=True.
        _record_verification(
            context, "verify_tx", passed=False,
            failures=["txid missing — the step that produces it did not run"],
        )
        return context

    result = await verify_tx(transport, txid)
    context["last_verify"] = result

    for check in result.checks:
        console.print(f"  [green]\u2713[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]\u2717[/] {fail}")
    _record_verification(
        context, "verify_tx", len(result.failures) == 0, result.failures
    )
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
        # F-d18b2348: on the unexpected-success branch, record ONLY when a real
        # txid exists (mirror handle_cancel_module_offers). The old
        # `txid=result.txid or "failed"` could mint a {txid:"failed",
        # success:true} record — a dead explorer link that inflates the proof
        # pack's success count.
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid,
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
        # FT-001: no wallet → this on-ledger assertion could not run. Record it
        # as a FAILED verification so the module is honestly unverified.
        _record_verification(
            context, "verify_trust_line", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_trust_line",
        result.found and len(result.failures) == 0, result.failures,
    )
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_trust_line_removed", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    # Passing verdict: the trust line is GONE (not found) with no failures.
    _record_verification(
        context, "verify_trust_line_removed",
        (not result.found) and len(result.failures) == 0, result.failures,
    )
    return context


# ---------------------------------------------------------------------------
# Token-freeze actions (FT-CURRIC-003 — tokens track)
# ---------------------------------------------------------------------------


def _parse_bool_arg(raw: str | None) -> bool | None:
    """Parse a module-arg flag to True/False, or None when the arg is absent."""
    if raw is None:
        return None
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


async def handle_set_freeze(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    currency = args.get("currency", "GLD")
    freeze = _parse_bool_arg(args.get("freeze", "true"))
    _raw = context.get("issuer_seed", "")
    issuer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    issuer_address = context.get("issuer_address", "")
    holder = state.wallet_address or ""

    if not issuer_seed or not holder:
        console.print("  [red]Missing issuer or holder wallet. Run previous steps first.[/]")
        return context

    verb = "Freezing" if freeze else "Unfreezing"
    console.print(f"  {verb} the holder's [cyan]{currency}[/] trust line (issuer-side)...")
    result = await set_individual_freeze(
        transport, issuer_seed, holder, currency, bool(freeze), issuer_address
    )

    if result.success:
        console.print(f"  [green]Individual freeze {'set' if freeze else 'cleared'}![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        console.print(f"  [red]Freeze tx failed: {result.error}[/]")
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)
    return context


async def handle_set_global_freeze(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    enable = _parse_bool_arg(args.get("enable", "true"))
    _raw = context.get("issuer_seed", "")
    issuer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    issuer_address = context.get("issuer_address", "")

    if not issuer_seed:
        console.print("  [red]No issuer wallet. Run the issuer step first.[/]")
        return context

    verb = "Enabling" if enable else "Clearing"
    console.print(f"  {verb} Global Freeze on the issuer (halts ALL its tokens)...")
    result = await set_global_freeze(transport, issuer_seed, bool(enable), issuer_address)

    if result.success:
        console.print(f"  [green]Global freeze {'enabled' if enable else 'cleared'}![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        console.print(f"  [red]Global freeze tx failed: {result.error}[/]")
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)
    return context


async def handle_verify_freeze(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    currency = args.get("currency", "GLD")
    issuer_address = context.get("issuer_address", "")
    holder = state.wallet_address or ""
    expect_individual = _parse_bool_arg(args.get("expect_individual"))
    expect_global = _parse_bool_arg(args.get("expect_global"))

    result = await verify_freeze(
        transport, issuer_address, holder, currency,
        expect_individual=expect_individual, expect_global=expect_global,
    )

    for check in result.checks:
        console.print(f"  [green]✓[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]✗[/] {fail}")

    context["last_freeze_verify"] = result
    _record_verification(
        context, "verify_freeze", len(result.failures) == 0, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Payment-channel actions (FT-CURRIC-001 — payments track)
# ---------------------------------------------------------------------------


async def handle_create_channel_receiver(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    console.print("  Creating the receiver (merchant) wallet...")
    receiver = create_wallet()
    context["receiver_seed"] = _SecretValue(receiver.seed)
    context["receiver_address"] = receiver.address
    console.print(f"  Receiver wallet: [cyan]{receiver.address}[/]")
    console.print("  Funding the receiver from the faucet...")
    result = await transport.fund_from_faucet(receiver.address)
    if result.success:
        console.print(f"  Receiver funded! Balance: [green]{result.balance} XRP[/]")
    elif getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    else:
        console.print(f"  [yellow]Receiver funding: {result.message}[/]")
    return context


async def handle_open_channel(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    amount = args.get("amount", "10")
    try:
        settle_delay = int(args.get("settle_delay", "86400"))
    except ValueError:
        # PB-003: a non-numeric settle_delay silently fell back before —
        # surface a one-line note (matching the check_inventory precedent) so a
        # malformed module arg is visible rather than swallowed.
        console.print("  [yellow]Invalid settle_delay, using default (86400).[/]")
        settle_delay = 86400
    # BC-005: a bare `except ValueError` lets a negative settle_delay through to
    # the tx builder (SettleDelay is an unsigned field on-ledger). Floor at 0.
    if settle_delay < 0:
        console.print(
            f"  [yellow]settle_delay {settle_delay} is invalid "
            f"(must be >= 0); using 0.[/]"
        )
        settle_delay = 0
    receiver = context.get("receiver_address", "")
    if "wallet_seed" not in context or not receiver:
        console.print("  [red]Missing sender wallet or receiver. Run previous steps first.[/]")
        return context

    console.print(f"  Opening a [cyan]{amount} XRP[/] channel to the receiver...")
    result = await open_channel(
        transport, context["wallet_seed"].get(), amount, receiver, settle_delay
    )
    if result.success:
        console.print("  [green]Channel opened — XRP locked once, ready for many claims![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        console.print(f"  Channel ID: [cyan]{result.channel_id}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["channel_id"] = result.channel_id
        # Capture the channel's signing key (the sender's) so the receiver can
        # verify off-ledger claims against it later.
        #
        # BC-001: this read-back is a network round-trip. If it raises (a
        # transient RPC error), the channel is ALREADY open on-ledger and its
        # XRP is locked — losing the txid here would leave a real, funded
        # channel with no recorded transaction. The public key is only used to
        # verify off-ledger claims and the downstream verify tolerates an empty
        # value, so on failure we record an empty key and continue straight to
        # record_tx. The successful on-ledger action must ALWAYS be recorded.
        try:
            chans = await transport.get_account_channels(state.wallet_address or "")
            match = next((c for c in chans if c.channel_id == result.channel_id), None)
            context["channel_public_key"] = match.public_key if match else ""
        except Exception as exc:
            logger.warning(
                "channel public-key read-back failed for channel %s: %s",
                result.channel_id, type(exc).__name__,
            )
            console.print(
                "  [yellow]Note: could not read back the channel's signing key "
                "(transient). The channel is open and recorded; off-ledger claim "
                "verification may need the key re-fetched later.[/]"
            )
            context["channel_public_key"] = ""
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        console.print(f"  [red]Channel open failed: {result.error}[/]")
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)
    return context


async def handle_fund_channel(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    amount = args.get("amount", "5")
    channel_id = context.get("channel_id", "")
    if "wallet_seed" not in context or not channel_id:
        console.print("  [red]No channel to fund. Open a channel first.[/]")
        return context

    console.print(f"  Adding [cyan]{amount} XRP[/] to the channel...")
    result = await fund_channel(transport, context["wallet_seed"].get(), channel_id, amount)
    if result.success:
        console.print("  [green]Channel funded![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        console.print(f"  [red]Channel fund failed: {result.error}[/]")
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)
    return context


async def handle_sign_claim(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    amount = args.get("amount", "3")
    channel_id = context.get("channel_id", "")
    if "wallet_seed" not in context or not channel_id:
        console.print("  [red]No channel. Open a channel first.[/]")
        return context

    console.print(f"  Signing an OFF-LEDGER claim for [cyan]{amount} XRP[/] (cumulative)...")
    sig = await sign_claim(transport, context["wallet_seed"].get(), channel_id, amount)
    context["claim_signature"] = sig
    context["claim_amount"] = amount
    console.print("  [green]Claim signed — no transaction, no fee.[/] Hand it to the receiver.")
    console.print(f"  Signature: [dim]{sig[:40]}...[/]")
    return context


async def handle_verify_claim_signature(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    channel_id = context.get("channel_id", "")
    amount = context.get("claim_amount", "")
    sig = context.get("claim_signature", "")
    pubkey = context.get("channel_public_key", "")
    if not channel_id or not sig:
        console.print("  [red]No signed claim to verify. Sign a claim first.[/]")
        # FT-001: no channel/signature → the off-ledger claim check could not
        # run because a prior step never produced them. Record FAILED so the
        # module is honestly unverified rather than vacuously green.
        _record_verification(
            context, "verify_claim_signature", passed=False,
            failures=[
                "channel_id/claim signature missing — the step that produces them did not run"
            ],
        )
        return context

    ok = await check_claim(transport, channel_id, amount, pubkey, sig)
    if ok:
        console.print(
            f"  [green]✓[/] Receiver verified the claim for {amount} XRP — "
            "valid, off-ledger, instant."
        )
    else:
        console.print("  [red]✗[/] Claim signature did NOT verify.")
    context["last_claim_verify"] = ok
    # PB-006-adjacent: this handler stores a bool verdict — wire it in so a
    # failed off-ledger claim check flags the module unverified.
    _record_verification(
        context, "verify_claim_signature", bool(ok),
        [] if ok else ["Claim signature did not verify."],
    )
    return context


async def handle_redeem_claim(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    channel_id = context.get("channel_id", "")
    balance = context.get("claim_amount", "")
    sig = context.get("claim_signature", "")
    pubkey = context.get("channel_public_key", "")
    _raw = context.get("receiver_seed", "")
    receiver_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    close = str(step.action_args.get("close", "false")).lower() in ("true", "1", "yes")

    if not channel_id or not receiver_seed or not balance:
        console.print("  [red]Missing channel, receiver, or claim. Run previous steps first.[/]")
        return context

    console.print(f"  Receiver redeeming the [cyan]{balance} XRP[/] claim on-ledger...")
    result = await redeem_claim(
        transport, receiver_seed, channel_id, balance,
        signature=sig, public_key=pubkey, close=close,
    )
    if result.success:
        console.print("  [green]Claim redeemed — funds settled to the receiver![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        state.record_tx(
            txid=result.txid, module_id=context.get("module_id", ""),
            network=state.network, success=True, explorer_url=result.explorer_url,
        )
        context.setdefault("txids", []).append(result.txid)
    else:
        console.print(f"  [red]Claim redeem failed: {result.error}[/]")
        state.record_tx(
            txid=result.txid or "failed", module_id=context.get("module_id", ""),
            network=state.network, success=False,
        )
    save_state(state)
    return context


async def handle_verify_channel(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    channel_id = context.get("channel_id", "")
    result = await verify_channel(
        transport, state.wallet_address or "", channel_id=channel_id,
        expect_amount_xrp=args.get("expect_amount"),
        expect_balance_xrp=args.get("expect_balance"),
    )
    for check in result.checks:
        console.print(f"  [green]✓[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]✗[/] {fail}")
    context["last_channel_verify"] = result
    _record_verification(
        context, "verify_channel", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# DEX actions
# ---------------------------------------------------------------------------


def _canon_currency(code: str) -> str:
    """Canonicalize a currency code for comparison.

    XRPL renders non-standard (>3 char) codes as 40-char hex on-ledger, so a
    handler that submitted ``HYGIENE`` reads back ``48594749454E45…00``. Decode
    the hex form back to ASCII when possible so identity matching works on both
    representations.
    """
    c = (code or "").strip()
    if len(c) == 40:
        try:
            decoded = bytes.fromhex(c).rstrip(b"\x00").decode("ascii")
            if decoded:
                return decoded.upper()
        except (ValueError, UnicodeDecodeError):
            return c.upper()
    return c.upper()


def _offer_leg_currency(leg: str) -> str:
    """Currency of an ``OfferInfo`` display leg (``value/CUR/issuer`` or drops)."""
    parts = (leg or "").split("/")
    if len(parts) >= 2:
        return _canon_currency(parts[1])
    return "XRP"


def _offer_leg_matches(leg: str, currency: str, value: str) -> bool:
    """True when a display leg matches the submitted ``(currency, value)`` pair.

    Transports render XRP legs differently (testnet: drops; dry-run: the raw
    XRP value), so an XRP leg matches either representation.
    """
    try:
        want = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return False
    if _canon_currency(currency) == "XRP":
        if "/" in (leg or ""):
            return False
        try:
            got = Decimal(leg)
        except (InvalidOperation, ValueError, TypeError):
            return False
        return got == want or got == want * 1_000_000
    parts = (leg or "").split("/")
    if len(parts) < 2 or _canon_currency(parts[1]) != _canon_currency(currency):
        return False
    try:
        return Decimal(parts[0]) == want
    except (InvalidOperation, ValueError, TypeError):
        return False


async def _resolve_created_offer_sequence(
    transport: Transport,
    address: str,
    result,
    *,
    taker_pays_currency: str,
    taker_pays_value: str,
    taker_gets_currency: str,
    taker_gets_value: str,
    console: Console,
) -> int | None:
    """Identify the JUST-PLACED offer's sequence instead of trusting ``offers[-1]``.

    F-ee815beb: ``account_offers`` walks the owner directory in book/hash
    order, NOT creation order — and an offer that crosses on placement leaves
    no resting entry at all, so ``offers[-1]`` can capture a stale pre-existing
    offer. A wrong sequence later sends OfferCancel at an innocent resting
    offer (a real, wrong on-ledger action). Resolution order:

    1. ``result.offer_sequence`` when the transport surfaced the placing tx's
       Sequence (the permissioned-offer precedent) — exact.
    2. Identity match on both legs (currency AND value); among matches the
       HIGHEST sequence is the newest (account Sequence is monotonic).
    3. Direction-only match (leg currencies) — covers a partially-crossed
       offer whose resting amounts shrank.
    4. No match → the offer likely fully crossed; capture NOTHING rather than
       a stale offer's sequence.
    """
    seq = getattr(result, "offer_sequence", None)
    if seq is not None:
        return seq
    offers = await transport.get_account_offers(address)
    if not offers:
        return None
    exact = [
        o for o in offers
        if _offer_leg_matches(o.taker_pays, taker_pays_currency, taker_pays_value)
        and _offer_leg_matches(o.taker_gets, taker_gets_currency, taker_gets_value)
    ]
    if exact:
        return max(o.sequence for o in exact)
    directional = [
        o for o in offers
        if _offer_leg_currency(o.taker_pays) == _canon_currency(taker_pays_currency)
        and _offer_leg_currency(o.taker_gets) == _canon_currency(taker_gets_currency)
    ]
    if directional:
        console.print(
            "  [dim]Offer amounts differ from the resting entry (it may have "
            "partially crossed); matched by direction.[/]"
        )
        return max(o.sequence for o in directional)
    console.print(
        "  [yellow]The new offer left no matching resting entry (it may have "
        "fully crossed on placement) — sequence not captured.[/]"
    )
    return None


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
        # F-ee815beb: select the created offer by identity, not offers[-1]
        # (account_offers is book/hash-ordered, not creation-ordered).
        seq = await _resolve_created_offer_sequence(
            transport, state.wallet_address or "", result,
            taker_pays_currency=pays_currency, taker_pays_value=pays_value,
            taker_gets_currency=gets_currency, taker_gets_value=gets_value,
            console=console,
        )
        if seq is not None:
            context["offer_sequence"] = seq
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
        # FT-001: no offer sequence → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_offer_present", passed=False,
            failures=["offer sequence missing — the step that produces it did not run"],
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
    _record_verification(
        context, "verify_offer_present",
        result.found and len(result.failures) == 0, result.failures,
    )
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
        # FT-001: no offer sequence → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_offer_absent", passed=False,
            failures=["offer sequence missing — the step that produces it did not run"],
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
    _record_verification(
        context, "verify_offer_absent", result.passed, result.failures
    )
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
        # BC-004: a missing (or mislabeled) snapshot must FAIL the step, not
        # silently `return context`. Silently passing lets a mislabeled
        # snapshot slip a verify step through without verifying anything — the
        # proof pack would then imply a lesson that was never checked. Surface
        # a structured failure via the existing LabException pipeline.
        raise LabException(
            LabError(
                code="STATE_MISSING_SNAPSHOT",
                message=(
                    f"Cannot verify reserve change: missing snapshot "
                    f"'{args.get('before', 'before')}' and/or "
                    f"'{args.get('after', 'after')}'."
                ),
                hint=(
                    "Run the snapshot_reserves steps that capture the "
                    "'before' and 'after' states before this verify step, and "
                    "check the before/after labels match those snapshots."
                ),
            )
        )

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
    # INFORMATIONAL: this is a COMPARISON handler — it teaches observation of a
    # reserve delta, it does not assert a pass/fail condition. Record passed=True
    # (never fabricate a failure verdict here) so it neither flips the module
    # unverified nor claims a verification it didn't run.
    _record_verification(context, "verify_reserve_change", True, [])
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
        # FT-001: no AMM pool → this on-ledger LP assertion could not run.
        _record_verification(
            context, "verify_lp_received", passed=False,
            failures=["amm_info missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_lp_received", len(result.failures) == 0, result.failures
    )
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
        # FT-001: no AMM pool → this on-ledger withdrawal assertion could not run.
        _record_verification(
            context, "verify_withdrawal", passed=False,
            failures=["amm_info missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_withdrawal", len(result.failures) == 0, result.failures
    )
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

        # F-ee815beb: identity-match the created bid, don't trust offers[-1].
        seq = await _resolve_created_offer_sequence(
            transport, state.wallet_address or "", result,
            taker_pays_currency=pays_currency, taker_pays_value=pays_value,
            taker_gets_currency=gets_currency, taker_gets_value=gets_value,
            console=console,
        )
        if seq is not None:
            context.setdefault("strategy_offer_sequences", []).append(seq)
            # F-d0b4cddf: record the intended direction so verify_module_offers
            # can assert it against the resting offer (a bid REQUESTS the token).
            context.setdefault("strategy_offer_directions", {})[seq] = {
                "side": "bid", "token": pays_currency,
            }
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

    # F-d0b4cddf (CRITICAL): XRPL semantics — TakerGets is what the offer
    # creator PROVIDES (sells), TakerPays what it REQUESTS (buys). An ASK
    # sells the token, so the token amount (pays_value/pays_currency) goes on
    # taker_GETS and the price (gets_value/gets_currency, XRP) on taker_PAYS.
    # The old mapping built the OPPOSITE — a second BUY of the token — so the
    # learner's "two-sided market" was two same-side bids on-ledger.
    result = await create_offer(
        transport, context["wallet_seed"].get(),
        gets_currency, gets_value, gets_issuer,   # taker_pays: the price we request
        pays_currency, pays_value, pays_issuer,   # taker_gets: the token we sell
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

        # F-ee815beb: identity-match the created ask, don't trust offers[-1].
        seq = await _resolve_created_offer_sequence(
            transport, state.wallet_address or "", result,
            taker_pays_currency=gets_currency, taker_pays_value=gets_value,
            taker_gets_currency=pays_currency, taker_gets_value=pays_value,
            console=console,
        )
        if seq is not None:
            context.setdefault("strategy_offer_sequences", []).append(seq)
            # F-d0b4cddf: an ask PROVIDES the token — verify_module_offers
            # asserts the resting offer's taker_gets currency is the token.
            context.setdefault("strategy_offer_directions", {})[seq] = {
                "side": "ask", "token": pays_currency,
            }
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
        # FT-001: no strategy offers recorded → this on-ledger assertion could
        # not run because the create-offers step never produced any.
        _record_verification(
            context, "verify_module_offers", passed=False,
            failures=["strategy offer sequences missing — the step that produces them did not run"],
        )
        return context

    directions = context.get("strategy_offer_directions", {})
    all_found = True
    failures: list[str] = []
    for seq in seqs:
        result = await verify_offer_present(
            transport, holder_address, seq
        )
        if result.found:
            for check in result.checks:
                console.print(f"  [green]\u2713[/] {check}")
            # F-d0b4cddf: DIRECTION assertion \u2014 a future leg inversion must not
            # pass silently. A resting ASK must PROVIDE the token
            # (taker_gets currency == token); a BID must REQUEST it
            # (taker_pays currency == token).
            direction = directions.get(seq)
            if direction and result.offer is not None:
                side = direction.get("side", "")
                token = _canon_currency(direction.get("token", ""))
                gets_cur = _offer_leg_currency(result.offer.taker_gets)
                pays_cur = _offer_leg_currency(result.offer.taker_pays)
                if side == "ask" and gets_cur != token:
                    all_found = False
                    msg = (
                        f"Offer seq {seq} direction INVERTED: the ask must SELL "
                        f"{token} (taker_gets={token}), but taker_gets is "
                        f"{gets_cur} \u2014 this offer BUYS instead of selling"
                    )
                    console.print(f"  [red]\u2717[/] {msg}")
                    failures.append(msg)
                elif side == "bid" and pays_cur != token:
                    all_found = False
                    msg = (
                        f"Offer seq {seq} direction INVERTED: the bid must BUY "
                        f"{token} (taker_pays={token}), but taker_pays is "
                        f"{pays_cur} \u2014 this offer SELLS instead of buying"
                    )
                    console.print(f"  [red]\u2717[/] {msg}")
                    failures.append(msg)
                elif side:
                    console.print(
                        f"  [green]\u2713[/] Offer seq {seq} direction OK: "
                        f"{side} of {token}"
                    )
        else:
            all_found = False
            for fail in result.failures:
                console.print(f"  [red]\u2717[/] {fail}")
                failures.append(fail)

    if all_found:
        console.print(
            f"  [green]All {len(seqs)} strategy offers verified[/]"
        )
    # PB-006: this handler computed all_found but stored NOTHING \u2014 a missing
    # strategy offer left the module falsely verified. Wire the real verdict in.
    _record_verification(context, "verify_module_offers", all_found, failures)
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
    context["strategy_offer_directions"] = {}
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
    _record_verification(
        context, "verify_module_offers_absent", remaining == 0,
        [] if remaining == 0 else [f"{remaining} offer(s) still open"],
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
        # BC-004: same contract as verify_reserve_change — a missing or
        # mislabeled position snapshot must fail the step, never silently pass.
        raise LabException(
            LabError(
                code="STATE_MISSING_SNAPSHOT",
                message=(
                    f"Cannot verify position delta: missing position snapshot "
                    f"'{args.get('before', 'before')}' and/or "
                    f"'{args.get('after', 'after')}'."
                ),
                hint=(
                    "Run the snapshot_position steps that capture the 'before' "
                    "and 'after' states before this verify step, and check the "
                    "before/after labels match those snapshots."
                ),
            )
        )

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
    # INFORMATIONAL: like verify_reserve_change, this COMPARISON handler teaches
    # observation of a position delta rather than asserting pass/fail. Record
    # passed=True (never fabricate a failure verdict for a comparison).
    _record_verification(context, "verify_position_delta", True, [])
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
            # F-ee815beb: identity-match the created bid, not offers[-1].
            seq = await _resolve_created_offer_sequence(
                transport, state.wallet_address or "", result,
                taker_pays_currency=pays_currency, taker_pays_value=bid_value,
                taker_gets_currency=gets_currency, taker_gets_value=bid_price,
                console=console,
            )
            if seq is not None:
                context.setdefault(
                    "strategy_offer_sequences", []
                ).append(seq)
                context.setdefault("strategy_offer_directions", {})[seq] = {
                    "side": "bid", "token": pays_currency,
                }
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

        # F-d0b4cddf (CRITICAL): the ask SELLS the token — the token amount
        # goes on taker_GETS (what the creator provides) and the XRP price on
        # taker_PAYS. The old mapping committed XRP while the inventory
        # guardrail above (inv.can_ask) gated on TOKEN balance, so the
        # guardrail did not protect the asset the offer actually spent.
        result = await create_offer(
            transport, context["wallet_seed"].get(),
            gets_currency, ask_price, gets_issuer,   # taker_pays: price requested
            pays_currency, ask_value, pays_issuer,   # taker_gets: token sold
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
            # F-ee815beb: identity-match the created ask, not offers[-1].
            seq = await _resolve_created_offer_sequence(
                transport, state.wallet_address or "", result,
                taker_pays_currency=gets_currency, taker_pays_value=ask_price,
                taker_gets_currency=pays_currency, taker_gets_value=ask_value,
                console=console,
            )
            if seq is not None:
                context.setdefault(
                    "strategy_offer_sequences", []
                ).append(seq)
                context.setdefault("strategy_offer_directions", {})[seq] = {
                    "side": "ask", "token": pays_currency,
                }
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
        # PB-003: surface the non-numeric fallback (matches check_inventory).
        console.print("  [yellow]Invalid taxon, using default (0).[/]")
        taxon = 0
    try:
        transfer_fee = int(args.get("transfer_fee", "0"))
    except ValueError:
        console.print("  [yellow]Invalid transfer_fee, using default (0).[/]")
        transfer_fee = 0
    # BC-005: transfer_fee is the NFT royalty in units of 1/1000 of a percent;
    # the protocol caps it at 50000 (= 50%). A bare `except ValueError` only
    # catches NON-numeric input, so a valid-but-out-of-range int (e.g. 999999)
    # would flow to the builder and fail on-ledger with an opaque error. Clamp
    # into range with a warning so the lesson still runs.
    if transfer_fee < 0 or transfer_fee > 50000:
        clamped = max(0, min(transfer_fee, 50000))
        console.print(
            f"  [yellow]transfer_fee {transfer_fee} is out of range "
            f"(0–50000 = 0–50%); clamping to {clamped}.[/]"
        )
        transfer_fee = clamped
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
        # F-b1ebc369: keep the mint's TransferFee so verify_nft_trade can
        # compute the protocol royalty when the issuer is a trade principal
        # (the raw balance delta mixes price and royalty on those hops).
        context["nft_transfer_fee"] = transfer_fee
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_nft", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_nft",
        result.found and result.passed, result.failures,
    )
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
    # at mint. F-ee815beb: the old third fallback burned owned[-1] claiming
    # "most recently owned" — but account_nfts is sorted by NFTokenID, not mint
    # order, so a module authored with burn-but-no-mint burned an essentially
    # ARBITRARY NFT, irreversibly. Burning now requires an explicit id.
    nft_id = step.action_args.get("nftoken_id", "") or context.get("nft_id", "")
    if not nft_id:
        console.print(
            "  [red]No NFToken to burn — pass `nftoken_id:` explicitly or run "
            "the mint step first so an NFTokenID is captured. (Burns are "
            "irreversible, so nothing is guessed from the on-ledger list.)[/]"
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_nft_burned", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_nft_burned", result.passed, result.failures
    )
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


async def _resolve_created_escrow_sequence(
    transport: Transport,
    owner: str,
    destination: str,
    finish_after: int | None,
    cancel_after: int | None,
    console: Console,
) -> int | None:
    """Identify the JUST-CREATED escrow's create-sequence by identity.

    F-25d8d8e1: ``account_objects`` returns Escrow entries in ledger-object-
    index (hash) order, NOT creation order, so ``escrows[-1]`` is a coin flip
    whenever the account already owns another escrow — the DEFAULT curriculum
    path (escrow_101 leaves an escrow; escrow_finish_101 / token_escrow_101
    then create a second one). A wrong capture makes EscrowFinish release the
    WRONG escrow. Match on the identity the handler just submitted
    (destination + FinishAfter + CancelAfter); fall back to
    destination + CancelAfter; among matches the highest create-sequence is
    the newest (account Sequence is monotonic). No match → capture nothing.
    """
    escrows = await transport.get_escrows(owner)
    if not escrows:
        return None
    exact = [
        e for e in escrows
        if e.destination == destination
        and e.finish_after == finish_after
        and e.cancel_after == cancel_after
    ]
    candidates = exact
    if not candidates:
        candidates = [
            e for e in escrows
            if e.destination == destination and e.cancel_after == cancel_after
        ]
        if candidates:
            console.print(
                "  [dim]Escrow matched by destination + CancelAfter "
                "(FinishAfter differed on read-back).[/]"
            )
    if not candidates:
        console.print(
            "  [yellow]Could not identify the created escrow among the "
            "account's escrows — create-sequence not captured.[/]"
        )
        return None
    seq = max(e.sequence for e in candidates)
    return seq if seq else None


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
        # PB-003: surface the non-numeric fallback (matches check_inventory).
        console.print("  [yellow]Invalid finish_seconds, using default (120).[/]")
        delay = 120
    # BC-005: a bare `except ValueError` lets a valid-but-nonsensical negative
    # delay (e.g. -100) through, producing a FinishAfter in the PAST — the
    # escrow would be finishable immediately (or the tx rejected), silently
    # breaking the time-lock lesson. Require at least 1 second in the future.
    if delay < 1:
        console.print(
            f"  [yellow]finish_seconds {delay} is invalid "
            f"(must be >= 1); using 1.[/]"
        )
        delay = 1
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
        # Both transports populate EscrowInfo.sequence (TRANSPORT-A-003).
        # F-25d8d8e1: select the created escrow by IDENTITY (destination +
        # FinishAfter + CancelAfter), not escrows[-1] — account_objects is
        # hash-ordered, so [-1] is a coin flip once a second escrow exists.
        owner = state.wallet_address or ""
        context["escrow_owner"] = owner
        context["escrow_destination"] = destination
        context["escrow_finish_after"] = finish_after
        context["escrow_cancel_after"] = cancel_after
        seq = await _resolve_created_escrow_sequence(
            transport, owner, destination, finish_after, cancel_after, console,
        )
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_escrow", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
        return context
    result = await verify_escrow(transport, address)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]Escrow verified on-ledger.[/]")
    context["last_escrow_verify"] = result
    _record_verification(
        context, "verify_escrow",
        result.found and result.passed, result.failures,
    )
    return context


async def _wait_for_finish_after(
    transport: Transport, finish_after, console: Console, max_wait: int = 300,
) -> None:
    """Wait (bounded) until an escrow's FinishAfter has elapsed on a real network.

    EscrowFinish before FinishAfter fails ``tecNO_PERMISSION`` — and a tec is
    FINAL once validated, so submitting early burns the fee and fails the
    lesson. Skips instantly on the dry-run transport (its deterministic clock
    treats a fresh escrow as already finishable) and caps the wait so a module
    authored with a huge FinishAfter cannot hang the runner.
    """
    if finish_after is None:
        return
    if getattr(transport, "network_name", "") == "dry-run":
        return
    try:
        remaining = int(finish_after) - (int(time.time()) - _RIPPLE_EPOCH)
    except (TypeError, ValueError):
        return
    if remaining <= 0:
        return
    # +2s margin: rippled gates on the ledger's close time, which can trail
    # wall-clock by a close interval.
    wait = min(remaining + 2, max_wait)
    console.print(
        f"  Waiting ~{wait}s for FinishAfter to elapse (the time-lock)..."
    )
    await asyncio.sleep(wait)


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
    await _wait_for_finish_after(
        transport, context.get("escrow_finish_after"), console
    )
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
        # FT-001: no wallet/escrow owner → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_escrow_finished", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_escrow_finished", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Token escrow actions (FC-001 — XLS-85, payments track)
# ---------------------------------------------------------------------------


async def handle_set_allow_trustline_locking(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Issuer opts in per-asset (AccountSet asfAllowTrustLineLocking, XLS-85)."""
    _raw_issuer = context.get("issuer_seed", "")
    issuer_seed = _raw_issuer.get() if isinstance(_raw_issuer, _SecretValue) else _raw_issuer
    if not issuer_seed:
        console.print("  [red]No issuer wallet in context. Run the issuer step first.[/]")
        return context
    issuer_address = context.get("issuer_address", "")
    console.print(
        "  Issuer opting in to token escrow "
        "([cyan]asfAllowTrustLineLocking[/]) — required before this IOU can be escrowed..."
    )
    result = await set_allow_trustline_locking(transport, issuer_seed, issuer_address)
    if result.success:
        console.print("  [green]Allow Trust Line Locking enabled on the issuer.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["allow_trustline_locking"] = True
    else:
        console.print(f"  [red]Opt-in failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_token_recipient(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund a third-party recipient wallet and set its trust line.

    The recipient must trust the issuer for the currency BEFORE the escrowed
    token can land on their line at finish.
    """
    args = step.action_args
    currency = args.get("currency", "GLD")
    limit = args.get("limit", "1000")
    issuer_address = context.get("issuer_address", "")
    if not issuer_address:
        console.print("  [red]No issuer in context. Run the issuer step first.[/]")
        return context

    console.print("  Creating the recipient (third-party) wallet...")
    recipient = create_wallet()
    context["recipient_seed"] = _SecretValue(recipient.seed)
    context["recipient_address"] = recipient.address
    console.print(f"  Recipient wallet: [cyan]{recipient.address}[/]")

    fund = await transport.fund_from_faucet(recipient.address)
    if fund.success:
        console.print(f"  Recipient funded! Balance: [green]{fund.balance} XRP[/]")
    elif getattr(fund, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    else:
        console.print(f"  [yellow]Recipient funding: {fund.message}[/]")

    console.print(f"  Recipient trusting the issuer for [cyan]{currency}[/]...")
    ts = await set_trust_line(
        transport, recipient.seed, issuer_address, currency, limit
    )
    if ts.success:
        console.print("  [green]Recipient trust line set.[/]")
    else:
        console.print(f"  [yellow]Recipient trust line: {ts.error}[/]")
    return context


async def handle_create_noopt_issuer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund a SECOND issuer that never opts in to token escrow, then issue.

    F-59ba7d9d: asfAllowTrustLineLocking is ACCOUNT-WIDE, so once the MAIN
    issuer opts in (step 5 of token_escrow_101), escrowing ANY currency it
    issues passes the opt-in check — the "no opt-in → tecNO_PERMISSION" lesson
    can never fire against it. This mirrors handle_create_noclaw_issuer: a
    distinct issuer that NEVER sets the flag issues a token to the holder, so
    the expect-fail step exercises the real missing-opt-in rejection.
    """
    args = step.action_args
    currency = args.get("currency", "NOP")
    amount = args.get("amount", "50")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    console.print(
        "  Creating a second issuer (never sets asfAllowTrustLineLocking)..."
    )
    issuer = create_wallet()
    fund = await transport.fund_from_faucet(issuer.address)
    if not fund.success and getattr(fund, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    context["noopt_issuer_seed"] = _SecretValue(issuer.seed)
    context["noopt_issuer_address"] = issuer.address
    context["noopt_currency"] = currency
    # Holder trusts this issuer, then it issues tokens (opt-in NEVER set) so
    # the later escrow attempt fails on the opt-in rule, not on tecNO_LINE.
    holder_seed = context["wallet_seed"].get()
    await set_trust_line(transport, holder_seed, issuer.address, currency, "1000")
    issue = await issue_token(
        transport, issuer.seed, state.wallet_address or "",
        currency, issuer.address, amount,
        memo=f"XRPLLAB|ISSUE|{currency}|{amount}",
    )
    if issue.success:
        console.print(
            f"  [green]Issued {amount} {currency} from a no-opt-in issuer.[/]"
        )
    else:
        console.print(f"  [yellow]Issuance setup note: {issue.error}[/]")
    return context


async def handle_snapshot_recipient_balance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Capture the recipient's issued balance (the before-value for the checkpoint)."""
    args = step.action_args
    currency = args.get("currency", "GLD")
    label = args.get("label", "before")
    recipient = context.get("recipient_address", "")
    issuer_address = context.get("issuer_address", "")
    if not recipient:
        console.print("  [red]No recipient wallet. Run the recipient step first.[/]")
        return context
    lines = await transport.get_trust_lines(recipient)
    bal = "0"
    for tl in lines:
        if tl.currency == currency and (not issuer_address or tl.peer == issuer_address):
            bal = tl.balance
            break
    context[f"recipient_balance_{label}"] = bal
    if label == "before":
        context["token_balance_before"] = bal
    console.print(f"  Recipient {currency} balance ({label}): [cyan]{bal}[/]")
    return context


async def handle_create_token_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Holder escrows N of an issued token to the recipient (XLS-85 EscrowCreate)."""
    args = step.action_args
    currency = args.get("currency", "GLD")
    value = args.get("amount", "50")
    issuer_address = context.get("issuer_address", "")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    holder_seed = context["wallet_seed"].get()
    holder_address = state.wallet_address or ""
    recipient = context.get("recipient_address") or args.get("destination") or ""
    if not issuer_address or not recipient:
        console.print(
            "  [red]Missing issuer or recipient. Run the issuer and recipient "
            "steps first.[/]"
        )
        return context

    # CancelAfter is MANDATORY for a token escrow (XLS-85). Default a day out.
    try:
        cancel_seconds = int(args.get("cancel_seconds", "86400"))
    except ValueError:
        console.print("  [yellow]Invalid cancel_seconds, using default (86400).[/]")
        cancel_seconds = 86400
    if cancel_seconds < 1:
        cancel_seconds = 1
    cancel_after = int(time.time()) - _RIPPLE_EPOCH + cancel_seconds

    # F-12f62ad2: fix1571 requires EVERY EscrowCreate to carry FinishAfter or a
    # Condition — XLS-85 only ADDS the mandatory-CancelAfter rule, it does not
    # relax fix1571. The old hardcoded finish_after=None was signed, submitted,
    # and rejected temMALFORMED on every real-network run. Mirror
    # handle_create_escrow: a short FinishAfter (the "release time" step 11 of
    # token_escrow_101 already narrates).
    try:
        finish_seconds = int(args.get("finish_seconds", "30"))
    except ValueError:
        console.print("  [yellow]Invalid finish_seconds, using default (30).[/]")
        finish_seconds = 30
    if finish_seconds < 1:
        console.print(
            f"  [yellow]finish_seconds {finish_seconds} is invalid "
            f"(must be >= 1); using 1.[/]"
        )
        finish_seconds = 1
    finish_after = int(time.time()) - _RIPPLE_EPOCH + finish_seconds

    console.print(
        f"  Holder escrowing [cyan]{value} {currency}[/] to the recipient "
        f"(release in ~{finish_seconds}s, mandatory CancelAfter "
        f"~{cancel_seconds}s out)..."
    )
    result = await create_token_escrow(
        transport, holder_seed, currency, issuer_address, value, recipient,
        cancel_after=cancel_after, finish_after=finish_after,
        source_address=holder_address,
    )
    if result.success:
        console.print("  [green]Token escrow created — IOU locked on-ledger![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["token_escrow_currency"] = currency
        context["token_escrow_issuer"] = issuer_address
        context["token_escrow_amount"] = value
        context["token_escrow_recipient"] = recipient
        owner = holder_address
        context["token_escrow_owner"] = owner
        context["token_escrow_finish_after"] = finish_after
        context["token_escrow_cancel_after"] = cancel_after
        # F-25d8d8e1: identity-match the created escrow (destination +
        # FinishAfter + CancelAfter) instead of escrows[-1] — with a leftover
        # escrow from escrow_101, [-1] could capture the OLD XRP escrow and
        # finish_token_escrow would release the wrong object.
        seq = await _resolve_created_escrow_sequence(
            transport, owner, recipient, finish_after, cancel_after, console,
        )
        if seq:
            context["token_escrow_sequence"] = seq
            console.print(f"  Escrow create-sequence: [cyan]{seq}[/]")
    else:
        console.print(f"  [red]Token escrow failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_token_escrow_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attempt a token escrow WITHOUT the issuer opt-in — expects tecNO_PERMISSION.

    Submit-and-learn: this is the failure a learner hits if the issuer never set
    asfAllowTrustLineLocking. It routes the tec code through explain_result_code
    so the failure teaches the opt-in rule inline.
    """
    args = step.action_args
    currency = args.get("currency") or context.get("noopt_currency") or "NOP"
    value = args.get("amount", "50")
    # A second, DELIBERATELY-not-opted-in issuer keyed by a separate address so
    # the main issuer's opt-in doesn't accidentally satisfy this one.
    # F-59ba7d9d: the noopt issuer comes from the create_noopt_issuer setup
    # step. asfAllowTrustLineLocking is ACCOUNT-WIDE, so falling back to the
    # (opted-in) main issuer can never produce the taught tecNO_PERMISSION —
    # surface that degradation honestly instead of silently reusing it.
    issuer_address = context.get("noopt_issuer_address", "")
    if not issuer_address:
        console.print(
            "  [yellow]No non-opted-in issuer in context (run the "
            "create_noopt_issuer step first). Falling back to the MAIN issuer, "
            "which HAS opted in — the failure below cannot demonstrate the "
            "missing-opt-in tecNO_PERMISSION.[/]"
        )
        issuer_address = context.get("issuer_address", "")
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    holder_seed = context["wallet_seed"].get()
    holder_address = state.wallet_address or ""
    recipient = context.get("recipient_address") or holder_address

    try:
        cancel_seconds = int(args.get("cancel_seconds", "86400"))
    except ValueError:
        cancel_seconds = 86400
    cancel_after = int(time.time()) - _RIPPLE_EPOCH + max(1, cancel_seconds)
    # F-12f62ad2: carry a FinishAfter here too — without it, fix1571 rejects
    # the tx temMALFORMED BEFORE the opt-in check, so the step would teach the
    # wrong failure. This step's lesson is the XLS-85 opt-in rule.
    try:
        finish_seconds = int(args.get("finish_seconds", "30"))
    except ValueError:
        finish_seconds = 30
    finish_after = int(time.time()) - _RIPPLE_EPOCH + max(1, finish_seconds)

    console.print(
        f"  [yellow]Attempting to escrow {value} {currency} with NO issuer "
        f"opt-in (expecting tecNO_PERMISSION)...[/]"
    )
    result = await create_token_escrow(
        transport, holder_seed, currency, issuer_address, value, recipient,
        cancel_after=cancel_after, finish_after=finish_after,
        source_address=holder_address,
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the issuer may already be opted in "
            "on this transport.[/]"
        )
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        # F-d18b2348: record only a REAL txid on the unexpected-success branch
        # (no {txid:"failed", success:true} records in the proof pack).
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid, module_id=context.get("module_id", ""),
                network=state.network, success=True,
                explorer_url=result.explorer_url,
            )
    else:
        # F-59ba7d9d: name the code honestly — only tecNO_PERMISSION is the
        # taught opt-in failure; anything else is a DIFFERENT failure and must
        # not be green-printed as the expected one.
        if result.result_code == "tecNO_PERMISSION":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"tecNO_PERMISSION (the missing-opt-in rejection). The "
                f"demonstration did not exercise the opt-in rule.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    save_state(state)
    return context


async def handle_finish_token_escrow(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Recipient finishes the token escrow, releasing the IOU (EscrowFinish)."""
    owner = context.get("token_escrow_owner") or state.wallet_address or ""
    seq = context.get("token_escrow_sequence")
    if not owner or seq is None:
        console.print(
            "  [red]No token escrow to finish — run the create-token-escrow "
            "step first so its create-sequence is captured.[/]"
        )
        return context
    # The recipient submits the finish (either party may finish a time-based
    # escrow; the funds always go to the destination). Fall back to the holder's
    # wallet if a dedicated recipient seed wasn't created.
    _raw = context.get("recipient_seed", "")
    finisher_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    if not finisher_seed and "wallet_seed" in context:
        finisher_seed = context["wallet_seed"].get()
    if not finisher_seed:
        console.print("  [red]No wallet to submit EscrowFinish.[/]")
        return context

    # F-12f62ad2: the escrow now carries a real FinishAfter — wait it out on a
    # real network so the finish isn't rejected tecNO_PERMISSION for being
    # early (a tec is final once validated).
    await _wait_for_finish_after(
        transport, context.get("token_escrow_finish_after"), console
    )
    console.print(
        f"  Recipient finishing the token escrow "
        f"(owner {owner[:12]}..., OfferSequence {seq})..."
    )
    result = await finish_token_escrow(transport, finisher_seed, owner, seq)
    if result.success:
        console.print("  [green]Token escrow finished — IOU released to the recipient![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]EscrowFinish failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_token_moved(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Checkpoint: the escrowed IOU reached the recipient's trust line."""
    recipient = context.get("token_escrow_recipient") or context.get("recipient_address", "")
    currency = context.get("token_escrow_currency", "GLD")
    issuer = context.get("token_escrow_issuer") or context.get("issuer_address", "")
    before = context.get("token_balance_before", "0")
    expected = context.get("token_escrow_amount")

    if not recipient or not issuer:
        console.print(
            "  [red]No recipient/issuer in context — the token-escrow steps did "
            "not run.[/]"
        )
        # Honest-pack contract: a verify that COULD NOT run is a FAILED
        # verification, not a silent skip (else the module stays vacuously
        # verified=True). Record on this missing-prerequisite path too.
        _record_verification(
            context, "verify_token_moved", passed=False,
            failures=[
                "recipient/issuer missing — the token-escrow steps that produce "
                "them did not run"
            ],
        )
        return context

    result = await verify_token_moved(
        transport, recipient, currency, issuer,
        before=before, expected_increase=expected,
    )
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    if result.passed:
        console.print("  [green]Token moved — the escrowed IOU is now the recipient's.[/]")
    context["last_token_moved_verify"] = result
    _record_verification(
        context, "verify_token_moved", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Multisig treasury actions (SignerListSet + multi-signed Payment)
# ---------------------------------------------------------------------------


async def handle_create_signer_wallets(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create N keyholder wallets for the treasury's signer list.

    Deliberately NOT funded: a SignerEntry does not need to be a funded
    on-ledger account — the ledger checks each co-signature against the key
    that derives the listed address, so cold keys that have never touched the
    ledger work. That keeps keyholder onboarding free.
    """
    args = step.action_args
    try:
        count = int(args.get("count", "3"))
    except ValueError:
        console.print("  [yellow]Invalid count, using default (3).[/]")
        count = 3
    if not 1 <= count <= 8:
        console.print(
            f"  [yellow]count {count} is outside this lesson's 1-8 range; "
            f"using 3.[/]"
        )
        count = 3
    console.print(
        f"  Creating [cyan]{count}[/] keyholder wallets (kept UNFUNDED — "
        "signer entries don't need on-ledger accounts, only keys)..."
    )
    seeds: list[_SecretValue] = []
    addresses: list[str] = []
    for i in range(count):
        signer = create_wallet()
        seeds.append(_SecretValue(signer.seed))
        addresses.append(signer.address)
        console.print(f"  Signer {i + 1}: [cyan]{signer.address}[/]")
    context["signer_seeds"] = seeds
    context["signer_addresses"] = addresses
    return context


async def handle_set_signer_list(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Install the N-of-M signer list on the treasury (SignerListSet)."""
    args = step.action_args
    try:
        quorum = int(args.get("quorum", "2"))
    except ValueError:
        console.print("  [yellow]Invalid quorum, using default (2).[/]")
        quorum = 2
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    addresses: list[str] = context.get("signer_addresses", [])
    if not addresses:
        console.print(
            "  [red]No signer wallets in context. Run the create-signer-wallets "
            "step first.[/]"
        )
        return context

    # Per-signer weights, padded with 1s so "1,1,1" and a bare "1" both work.
    raw_weights = [w.strip() for w in args.get("weights", "").split(",") if w.strip()]
    weights: list[int] = []
    for i in range(len(addresses)):
        try:
            weights.append(int(raw_weights[i]) if i < len(raw_weights) else 1)
        except ValueError:
            weights.append(1)
    entries = list(zip(addresses, weights, strict=True))

    owner_seed = context["wallet_seed"].get()
    owner_address = state.wallet_address or ""
    weight_sum = sum(w for _a, w in entries)
    console.print(
        f"  Installing a [cyan]{quorum}-of-{weight_sum}[/] signer list on the "
        f"treasury ({len(entries)} signers, quorum {quorum})..."
    )
    result = await set_signer_list(
        transport, owner_seed, quorum, entries, owner_address
    )
    if result.success:
        console.print("  [green]Signer list installed — the treasury is now N-of-M.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        console.print(
            "  [dim]The SignerList object holds one owner-reserve increment "
            "(~0.2 XRP) while it exists — freed if you delete the list.[/]"
        )
        context["multisig_quorum"] = quorum
        context["multisig_entries"] = entries
    else:
        console.print(f"  [red]SignerListSet failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_signer_list(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Checkpoint: the signer list on-ledger matches what was installed."""
    owner = state.wallet_address or ""
    expected_quorum = context.get("multisig_quorum")
    expected_entries = context.get("multisig_entries")
    if not owner or expected_quorum is None:
        console.print(
            "  [red]No signer list in context — the SignerListSet step did "
            "not run.[/]"
        )
        # Honest-pack contract: a verify that COULD NOT run is a FAILED
        # verification, not a silent skip.
        _record_verification(
            context, "verify_signer_list", passed=False,
            failures=[
                "treasury/quorum missing — the SignerListSet step that "
                "produces them did not run"
            ],
        )
        return context

    result = await verify_signer_list(
        transport, owner,
        expected_quorum=expected_quorum,
        expected_entries=expected_entries,
    )
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    if result.passed:
        console.print(
            "  [green]The ledger holds exactly the quorum and roster you "
            "installed.[/]"
        )
    context["last_signer_list_verify"] = result
    _record_verification(
        context, "verify_signer_list", result.passed, result.failures
    )
    return context


def _pick_signers(
    context: dict, signer_count: int,
) -> tuple[list[str], list[str]]:
    """Resolve the first *signer_count* signer (seeds, addresses) from context."""
    raw_seeds = context.get("signer_seeds", [])[:signer_count]
    seeds = [
        s.get() if isinstance(s, _SecretValue) else s for s in raw_seeds
    ]
    addresses = list(context.get("signer_addresses", [])[:signer_count])
    return seeds, addresses


def _combined_weight(context: dict, addresses: list[str]) -> int:
    """Sum the installed weights of *addresses* (0 for unknown signers)."""
    weights = dict(context.get("multisig_entries", []))
    return sum(weights.get(a, 0) for a in addresses)


async def handle_send_multisig_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Submit a multi-signed Payment that MEETS the quorum."""
    args = step.action_args
    amount = args.get("amount", "10")
    try:
        signer_count = int(args.get("signer_count", "2"))
    except ValueError:
        console.print("  [yellow]Invalid signer_count, using default (2).[/]")
        signer_count = 2
    owner_address = state.wallet_address or ""
    if not owner_address or "signer_seeds" not in context:
        console.print(
            "  [red]Missing treasury or signer wallets. Run the earlier steps "
            "first.[/]"
        )
        return context
    seeds, addresses = _pick_signers(context, signer_count)
    if len(seeds) < signer_count:
        console.print(
            f"  [red]Only {len(seeds)} signer wallet(s) in context — cannot "
            f"co-sign with {signer_count}.[/]"
        )
        return context
    # The payout destination: explicit arg, else the first keyholder's ops
    # wallet. On XRPL a payment >= the base reserve CREATES an unfunded
    # account, so the treasury's first payout also activates it.
    destination = args.get("destination") or context.get(
        "multisig_payee", (context.get("signer_addresses") or [""])[0]
    )
    quorum = context.get("multisig_quorum")
    combined = _combined_weight(context, addresses)
    console.print(
        f"  Co-signing with [cyan]{signer_count}[/] of "
        f"{len(context.get('signer_addresses', []))} keyholders — combined "
        f"weight [cyan]{combined}[/] vs quorum [cyan]{quorum}[/]..."
    )
    console.print(
        f"  [dim]Multisig fee rule: base fee × (1 + {signer_count} "
        f"signatures) — every co-signature is paid for.[/]"
    )
    result = await send_multisig_payment(
        transport, owner_address, destination, amount, seeds,
        signer_addresses=addresses,
        memo=f"XRPLLAB|MULTISIG|{signer_count}sig",
    )
    if result.success:
        console.print(
            f"  [green]Multi-signed payment validated — {amount} XRP moved "
            "with the treasury key never touching it![/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        console.print(f"  Fee paid: [cyan]{result.fee}[/] drops (scaled per-signature)")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["multisig_payment_txid"] = result.txid
    else:
        console.print(f"  [red]Multi-signed payment failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_send_multisig_payment_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attempt a BELOW-QUORUM multi-signed payment — expects tefBAD_QUORUM.

    Submit-and-learn: one valid signature whose weight is below the quorum.
    The signature itself verifies fine; the ledger rejects the COMBINATION —
    that distinction (tefBAD_QUORUM, not tefBAD_SIGNATURE) is the lesson.
    """
    args = step.action_args
    amount = args.get("amount", "10")
    try:
        signer_count = int(args.get("signer_count", "1"))
    except ValueError:
        signer_count = 1
    owner_address = state.wallet_address or ""
    if not owner_address or "signer_seeds" not in context:
        console.print(
            "  [red]Missing treasury or signer wallets. Run the earlier steps "
            "first.[/]"
        )
        return context
    seeds, addresses = _pick_signers(context, signer_count)
    if not seeds:
        console.print("  [red]No signer wallets in context.[/]")
        return context
    destination = args.get("destination") or (
        context.get("signer_addresses") or [""]
    )[0]
    quorum = context.get("multisig_quorum")
    combined = _combined_weight(context, addresses)
    console.print(
        f"  [yellow]Attempting a payment with only {signer_count} "
        f"signature(s) — combined weight {combined} vs quorum {quorum} "
        f"(expecting tefBAD_QUORUM)...[/]"
    )
    result = await send_multisig_payment(
        transport, owner_address, destination, amount, seeds,
        signer_addresses=addresses,
        memo=f"XRPLLAB|MULTISIG|{signer_count}sig",
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the signature set met the quorum "
            "on this transport.[/]"
        )
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        # Record only a REAL txid on the unexpected-success branch (no
        # {txid:'failed', success:true} records in the proof pack).
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid, module_id=context.get("module_id", ""),
                network=state.network, success=True,
                explorer_url=result.explorer_url,
            )
    else:
        # Name the code honestly — only tefBAD_QUORUM is the taught
        # below-quorum failure; anything else is a DIFFERENT failure and must
        # not be green-printed as the expected one.
        if result.result_code == "tefBAD_QUORUM":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"tefBAD_QUORUM (the below-quorum rejection). The "
                f"demonstration did not exercise the quorum rule.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    save_state(state)
    return context


async def handle_delete_signer_list(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Delete the signer list (SignerQuorum=0, SignerEntries omitted)."""
    if "wallet_seed" not in context:
        console.print("  [red]No wallet in context. Run the wallet step first.[/]")
        return context
    owner_seed = context["wallet_seed"].get()
    owner_address = state.wallet_address or ""
    console.print(
        "  Deleting the signer list ([cyan]SignerQuorum=0[/] with "
        "SignerEntries OMITTED — supplying only one of the two is "
        "temMALFORMED)..."
    )
    result = await delete_signer_list(transport, owner_seed, owner_address)
    if result.success:
        console.print(
            "  [green]Signer list deleted — its owner reserve is freed.[/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        console.print(
            "  [dim]Safety rule: with the master key disabled and no regular "
            "key, the network refuses this delete (tecNO_ALTERNATIVE_KEY) — "
            "an account can't sign away its last key.[/]"
        )
        context["signer_list_deleted"] = True
    else:
        console.print(f"  [red]Delete failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_signer_list_deleted(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Checkpoint: the SignerList object is gone from the account."""
    owner = state.wallet_address or ""
    if not owner:
        console.print("  [red]No treasury wallet in context.[/]")
        _record_verification(
            context, "verify_signer_list_deleted", passed=False,
            failures=["treasury address missing — the wallet step did not run"],
        )
        return context
    result = await verify_signer_list(transport, owner, expect_absent=True)
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    if result.passed:
        console.print(
            "  [green]The treasury is back to single-key control — quorum "
            "rules no longer apply.[/]"
        )
    _record_verification(
        context, "verify_signer_list_deleted", result.passed, result.failures
    )
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_did", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
        return context
    result = await verify_did(transport, address, expected_uri=context.get("did_uri"))
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]DID verified on-ledger.[/]")
    context["last_did_verify"] = result
    _record_verification(
        context, "verify_did",
        result.found and result.passed, result.failures,
    )
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_did_deleted", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
        return context
    result = await verify_did_deleted(transport, address)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Identity hygiene complete — DID removed.[/]")
    context["last_did_deleted_verify"] = result
    _record_verification(
        context, "verify_did_deleted", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Credential actions (FC-002 — identity track, XLS-70)
# ---------------------------------------------------------------------------


async def handle_create_subject_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund the SUBJECT wallet the learner's account will attest.

    Two-party credentials need a second account: the learner's wallet is the
    ISSUER, this one is the SUBJECT. The subject is funded so a CredentialCreate
    against it does NOT hit tecNO_TARGET (the unfunded-subject error is taught
    on a separate, intentionally-unfunded address below).
    """
    console.print("  Creating the subject (player) wallet...")
    subject = create_wallet()
    context["subject_seed"] = _SecretValue(subject.seed)
    context["subject_address"] = subject.address
    console.print(f"  Subject wallet: [cyan]{subject.address}[/]")
    console.print("  Funding the subject from the faucet (so it's a real target)...")
    result = await transport.fund_from_faucet(subject.address)
    if result.success:
        console.print(f"  Subject funded! Balance: [green]{result.balance} XRP[/]")
    elif getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
        console.print(f"  [dim]{err.hint}[/]")
    else:
        console.print(f"  [yellow]Subject funding: {result.message}[/]")
    return context


async def handle_create_credential_unfunded(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attest a credential against an UNFUNDED subject — teaches tecNO_TARGET.

    A CredentialCreate whose Subject is not a funded account on-ledger fails
    ``tecNO_TARGET``: you cannot attest an account that doesn't exist yet.
    """
    args = step.action_args
    credential_type = args.get("credential_type", "over21")
    # A syntactically-valid but unfunded classic address (never faucet-funded).
    unfunded = args.get("subject", "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe")
    if "wallet_seed" not in context:
        console.print("  [red]No issuer wallet in context. Run the wallet step first.[/]")
        return context
    issuer_seed = context["wallet_seed"].get()
    issuer_address = state.wallet_address or ""
    console.print(
        f"  [yellow]Attempting to attest '{credential_type}' against an "
        f"UNFUNDED subject (expecting tecNO_TARGET)...[/]"
    )
    result = await create_credential(
        transport, issuer_seed, unfunded, credential_type,
        issuer_address=issuer_address,
    )
    if result.success:
        # Unexpected success (e.g. a transport that doesn't model the unfunded
        # case): record the real tx so the pack stays honest, per CORE-A-004.
        console.print(
            "  [yellow]Unexpected success — the subject was fundable on this "
            "transport. Recording the tx.[/]"
        )
    else:
        console.print(f"  [green]Expected failure:[/] {result.result_code}")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Issuer attests a credential about the funded subject (CredentialCreate)."""
    args = step.action_args
    credential_type = args.get("credential_type", "over21")
    uri = args.get("uri", "")
    if "wallet_seed" not in context:
        console.print("  [red]No issuer wallet in context. Run the wallet step first.[/]")
        return context
    subject_address = context.get("subject_address", "")
    if not subject_address:
        console.print("  [red]No subject wallet. Run the subject-wallet step first.[/]")
        return context
    issuer_seed = context["wallet_seed"].get()
    issuer_address = state.wallet_address or ""
    console.print(
        f"  Attesting credential type [cyan]{credential_type}[/] about "
        f"subject [cyan]{subject_address[:12]}...[/] (PROVISIONAL until accepted)"
    )
    result = await create_credential(
        transport, issuer_seed, subject_address, credential_type, uri=uri,
        issuer_address=issuer_address,
    )
    if result.success:
        console.print("  [green]Credential created — provisional, awaiting subject accept.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["credential_type"] = credential_type
        context["credential_issuer"] = issuer_address
        context["credential_subject"] = subject_address
    else:
        console.print(f"  [red]CredentialCreate failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_credential_duplicate(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Re-attest the SAME (subject, issuer, type) — teaches tecDUPLICATE.

    (subject, issuer, CredentialType) is unique per issuer: a second identical
    credential fails ``tecDUPLICATE``.
    """
    args = step.action_args
    credential_type = args.get("credential_type", context.get("credential_type", "over21"))
    if "wallet_seed" not in context:
        console.print("  [red]No issuer wallet in context. Run the wallet step first.[/]")
        return context
    subject_address = context.get("subject_address", "")
    if not subject_address:
        console.print("  [red]No subject wallet. Run the subject-wallet step first.[/]")
        return context
    issuer_seed = context["wallet_seed"].get()
    issuer_address = state.wallet_address or ""
    console.print(
        "  [yellow]Re-attesting the SAME credential (expecting tecDUPLICATE)...[/]"
    )
    result = await create_credential(
        transport, issuer_seed, subject_address, credential_type,
        issuer_address=issuer_address,
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — no live duplicate existed on this "
            "transport. Recording the tx.[/]"
        )
    else:
        console.print(f"  [green]Expected failure:[/] {result.result_code}")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_accept_credential_wrong_party(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The ISSUER tries to accept — teaches that ONLY the subject can accept.

    CredentialAccept must be signed by the subject. When the issuer (or any
    non-subject) tries, there is no matching provisional credential under their
    own address and the ledger rejects it (tecNO_ENTRY / temMALFORMED).
    """
    credential_type = context.get("credential_type", "over21")
    issuer_address = context.get("credential_issuer", state.wallet_address or "")
    if "wallet_seed" not in context:
        console.print("  [red]No issuer wallet in context. Run the wallet step first.[/]")
        return context
    issuer_seed = context["wallet_seed"].get()
    console.print(
        "  [yellow]Issuer attempting to accept its own credential "
        "(expecting rejection — only the subject may accept)...[/]"
    )
    # The issuer signs an accept naming ITSELF as the acting account — there is
    # no provisional credential keyed under the issuer-as-subject, so it fails.
    result = await accept_credential(
        transport, issuer_seed, issuer_address, credential_type,
        subject_address=issuer_address,
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the transport did not enforce "
            "subject-only accept. Recording the tx.[/]"
        )
    else:
        console.print(f"  [green]Expected rejection:[/] {result.result_code}")
        console.print(
            "  [dim]Only the subject account named in the credential can accept "
            "it — this is the 'you hold your own passport' rule.[/]"
        )
    _record_submit(state, context, result)
    return context


async def handle_accept_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Subject accepts the credential — makes it valid, reserve moves to subject."""
    credential_type = context.get("credential_type", "over21")
    issuer_address = context.get("credential_issuer", state.wallet_address or "")
    subject_address = context.get("subject_address", "")
    _raw = context.get("subject_seed", "")
    subject_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    if not subject_seed or not subject_address:
        console.print("  [red]No subject wallet. Run the subject-wallet step first.[/]")
        return context
    console.print(
        "  Subject accepting the credential — clears provisional state, "
        "reserve moves from issuer to subject..."
    )
    result = await accept_credential(
        transport, subject_seed, issuer_address, credential_type,
        subject_address=subject_address,
    )
    if result.success:
        console.print("  [green]Credential accepted — now VALID on-ledger![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]CredentialAccept failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify the subject holds a VALID (accepted) credential from the issuer."""
    credential_type = context.get("credential_type", "over21")
    issuer_address = context.get("credential_issuer", state.wallet_address or "")
    subject_address = context.get("subject_address", "")
    if not subject_address or not issuer_address:
        console.print("  [red]No credential in context. Run the create/accept steps first.[/]")
        # FT-001: prerequisites missing → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_credential", passed=False,
            failures=[
                "subject/issuer missing — the steps that produce them did not run"
            ],
        )
        return context
    result = await verify_credential(
        transport, subject_address, issuer_address, credential_type
    )
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    if result.passed:
        console.print("  [green]Credential is VALID — the gate would pass this player.[/]")
    context["last_credential_verify"] = result
    _record_verification(
        context, "verify_credential", result.passed, result.failures
    )
    return context


async def handle_delete_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Subject deletes the credential, reclaiming its reserve (CredentialDelete)."""
    credential_type = context.get("credential_type", "over21")
    issuer_address = context.get("credential_issuer", state.wallet_address or "")
    subject_address = context.get("subject_address", "")
    _raw = context.get("subject_seed", "")
    subject_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    if not subject_seed or not subject_address:
        console.print("  [red]No subject wallet. Run the subject-wallet step first.[/]")
        return context
    console.print("  Subject deleting the credential — reclaiming the owner reserve...")
    result = await delete_credential(
        transport, subject_seed, issuer_address, subject_address, credential_type,
        wallet_address=subject_address,
    )
    if result.success:
        console.print("  [green]Credential deleted — reserve freed (revocation path).[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]CredentialDelete failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


# ---------------------------------------------------------------------------
# Permissioned Domains & Gated DEX actions (FC-004 — XLS-80 / XLS-81)
# ---------------------------------------------------------------------------
#
# Composes with credentials (FC-002): the learner's wallet is the ISSUER and
# the domain OWNER; the funded SUBJECT holds the accepted credential and is the
# eligible trader; a second uncredentialed wallet demonstrates the eligibility
# gate. The credential must be CREATED and ACCEPTED (reuse the FC-002 steps in
# the module) before the domain lists it.


async def handle_create_permissioned_domain(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Owner creates a Permissioned Domain listing the accepted credential.

    Omits DomainID → CREATE. AcceptedCredentials lists the {issuer,
    credential_type} the FC-002 steps issued. The derived DomainID is tracked
    in context (off-ledger) — it is NOT idempotently recreatable.
    """
    if "wallet_seed" not in context:
        console.print("  [red]No owner wallet in context. Run the wallet step first.[/]")
        return context
    owner_seed = context["wallet_seed"].get()
    owner_address = state.wallet_address or ""
    credential_type = context.get("credential_type", "over21")
    # The domain accepts the SAME {issuer, type} the credential module issued.
    issuer_address = context.get("credential_issuer", owner_address)
    console.print(
        f"  Creating a Permissioned Domain accepting credential "
        f"[cyan]{credential_type}[/] from issuer [cyan]{issuer_address[:12]}...[/]"
    )
    result = await set_permissioned_domain(
        transport, owner_seed,
        [(issuer_address, credential_type)],
        owner_address=owner_address,
    )
    if result.success:
        console.print("  [green]Permissioned Domain created![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        console.print(f"  DomainID: [cyan]{result.domain_id}[/]")
        console.print(
            "  [dim]Track this DomainID off-ledger — each (owner, sequence) yields "
            "a DISTINCT id; re-running create makes a NEW domain.[/]"
        )
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["domain_id"] = result.domain_id
        context["domain_issuer"] = issuer_address
        context["domain_credential_type"] = credential_type
    else:
        console.print(f"  [red]PermissionedDomainSet failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_permissioned_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The CREDENTIALED account places a permissioned offer (DomainID) — succeeds.

    The subject holds the accepted credential the domain lists, so the offer,
    scoped to the DomainID, is eligible and rests on the permissioned book.
    ``hybrid`` (optional) sets tfHybrid so it also matches the open DEX.
    """
    args = step.action_args
    pays_currency = args.get("pays_currency", "LAB")
    pays_value = args.get("pays_value", "50")
    gets_currency = args.get("gets_currency", "XRP")
    gets_value = args.get("gets_value", "10")
    hybrid = _parse_bool_arg(args.get("hybrid", "false")) or False
    domain_id = context.get("domain_id", "")
    if not domain_id:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        return context
    _raw = context.get("subject_seed", "")
    subject_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    subject_address = context.get("subject_address", "")
    if not subject_seed or not subject_address:
        console.print("  [red]No credentialed (subject) wallet. Run the FC-002 steps first.[/]")
        return context
    issuer_address = context.get("domain_issuer", context.get("credential_issuer", ""))
    pays_issuer = "" if pays_currency == "XRP" else issuer_address
    gets_issuer = "" if gets_currency == "XRP" else issuer_address
    console.print(
        f"  Credentialed account placing a permissioned offer "
        f"({'hybrid' if hybrid else 'plain'}) scoped to the DomainID..."
    )
    result = await create_permissioned_offer(
        transport, subject_seed,
        pays_currency, pays_value, pays_issuer,
        gets_currency, gets_value, gets_issuer,
        domain_id=domain_id, hybrid=hybrid,
        wallet_address=subject_address,
    )
    if result.success:
        console.print("  [green]Permissioned offer placed — the credential admits it![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        console.print(f"  Offer sequence: [cyan]{result.offer_sequence}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["permissioned_offer_seq"] = result.offer_sequence
    else:
        console.print(f"  [red]Permissioned offer failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_uncredentialed_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund a second wallet that holds NO accepted credential.

    Used to demonstrate the eligibility gate: this account's permissioned offer
    will be REJECTED because it holds no credential the domain accepts.
    """
    console.print("  Creating an un-credentialed (outsider) wallet...")
    outsider = create_wallet()
    context["outsider_seed"] = _SecretValue(outsider.seed)
    context["outsider_address"] = outsider.address
    console.print(f"  Outsider wallet: [cyan]{outsider.address}[/]")
    console.print("  Funding it from the faucet (so it's a real account)...")
    result = await transport.fund_from_faucet(outsider.address)
    if result.success:
        console.print(f"  Outsider funded! Balance: [green]{result.balance} XRP[/]")
    elif getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
        console.print(f"  [dim]{err.hint}[/]")
    else:
        console.print(f"  [yellow]Outsider funding: {result.message}[/]")
    return context


async def handle_create_permissioned_offer_uncredentialed(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The UN-credentialed account places a permissioned offer — FAILS.

    It holds no credential the domain accepts, so the offer scoped to the
    DomainID is rejected before it can rest. This is the eligibility gate.
    """
    args = step.action_args
    pays_currency = args.get("pays_currency", "LAB")
    pays_value = args.get("pays_value", "50")
    gets_currency = args.get("gets_currency", "XRP")
    gets_value = args.get("gets_value", "10")
    domain_id = context.get("domain_id", "")
    if not domain_id:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        return context
    _raw = context.get("outsider_seed", "")
    outsider_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    outsider_address = context.get("outsider_address", "")
    if not outsider_seed or not outsider_address:
        console.print("  [red]No outsider wallet. Run the outsider-wallet step first.[/]")
        return context
    issuer_address = context.get("domain_issuer", context.get("credential_issuer", ""))
    pays_issuer = "" if pays_currency == "XRP" else issuer_address
    gets_issuer = "" if gets_currency == "XRP" else issuer_address
    console.print(
        "  [yellow]Un-credentialed account attempting a permissioned offer "
        "(expecting rejection — it holds no accepted credential)...[/]"
    )
    result = await create_permissioned_offer(
        transport, outsider_seed,
        pays_currency, pays_value, pays_issuer,
        gets_currency, gets_value, gets_issuer,
        domain_id=domain_id, hybrid=False,
        wallet_address=outsider_address,
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the transport did not enforce the "
            "eligibility gate. Recording the tx.[/]"
        )
        context["uncredentialed_offer_seq"] = result.offer_sequence
    else:
        console.print(f"  [green]Expected rejection:[/] {result.result_code}")
        console.print(
            "  [dim]Eligibility to trade in a domain is proven by holding an "
            "accepted credential via DomainID — NOT by CredentialIDs (the "
            "deposit-auth rail). This account holds neither.[/]"
        )
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_modify_domain_drop_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Modify the domain with an EMPTY-of-the-old-entry accepted set (full replace).

    Teaches the full-replace revocation gotcha: AcceptedCredentials is replaced
    wholesale. Re-listing a DIFFERENT credential (and dropping the original)
    silently revokes access for everyone holding the dropped type — invalidating
    their open permissioned offers. Here we swap the accepted set to a decoy
    {issuer, type} so the previously-eligible subject is now excluded.
    """
    if "wallet_seed" not in context:
        console.print("  [red]No owner wallet in context. Run the wallet step first.[/]")
        return context
    owner_seed = context["wallet_seed"].get()
    owner_address = state.wallet_address or ""
    domain_id = context.get("domain_id", "")
    if not domain_id:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        return context
    issuer_address = context.get("domain_issuer", owner_address)
    decoy_type = step.action_args.get("replacement_type", "region-XX")
    console.print(
        "  [yellow]Modifying the domain — replacing the accepted set with a "
        "DECOY credential (dropping the original)...[/]"
    )
    console.print(
        "  [dim]AcceptedCredentials is a FULL REPLACE — the original type is "
        "silently revoked, stranding its holders' permissioned offers.[/]"
    )
    result = await set_permissioned_domain(
        transport, owner_seed,
        [(issuer_address, decoy_type)],
        domain_id=domain_id,
        owner_address=owner_address,
    )
    if result.success:
        console.print("  [green]Domain modified — accepted set fully replaced.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]PermissionedDomainSet (modify) failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_modify_domain_nonowner(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """A NON-owner tries to modify the domain — rejected (owner-only).

    Only the original owner may modify a domain. The un-credentialed outsider
    wallet (created above) attempts the modify and is rejected.
    """
    domain_id = context.get("domain_id", "")
    if not domain_id:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        return context
    _raw = context.get("outsider_seed", "")
    outsider_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    outsider_address = context.get("outsider_address", "")
    if not outsider_seed or not outsider_address:
        console.print("  [red]No outsider wallet. Run the outsider-wallet step first.[/]")
        return context
    issuer_address = context.get("domain_issuer", "")
    console.print(
        "  [yellow]Non-owner attempting to modify the domain "
        "(expecting rejection — owner-only)...[/]"
    )
    result = await set_permissioned_domain(
        transport, outsider_seed,
        [(issuer_address, "hijack")],
        domain_id=domain_id,
        owner_address=outsider_address,
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the transport did not enforce "
            "owner-only modify. Recording the tx.[/]"
        )
    else:
        console.print(f"  [green]Expected rejection:[/] {result.result_code}")
        console.print(
            "  [dim]Domain-owner key custody matters — only the owner may "
            "rotate a domain's policy.[/]"
        )
    _record_submit(state, context, result)
    return context


async def handle_delete_permissioned_domain(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Owner deletes the domain, freeing its reserve (PermissionedDomainDelete).

    The named compensator: frees the owner-reserve slot. A domain blocks
    owner-account deletion until it is removed.
    """
    if "wallet_seed" not in context:
        console.print("  [red]No owner wallet in context. Run the wallet step first.[/]")
        return context
    owner_seed = context["wallet_seed"].get()
    owner_address = state.wallet_address or ""
    domain_id = context.get("domain_id", "")
    if not domain_id:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        return context
    console.print("  Owner deleting the domain — reclaiming the owner reserve (compensator)...")
    result = await delete_permissioned_domain(
        transport, owner_seed, domain_id, owner_address=owner_address
    )
    if result.success:
        console.print("  [green]Domain deleted — reserve freed.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context.pop("domain_id", None)
    else:
        console.print(f"  [red]PermissionedDomainDelete failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_domain(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify the domain exists and (optionally) accepts the expected credential."""
    owner_address = state.wallet_address or ""
    domain_id = context.get("domain_id", "")
    expect_issuer = context.get("domain_issuer", "")
    expect_type = context.get("domain_credential_type", "")
    if not domain_id or not owner_address:
        console.print("  [red]No domain in context. Create the domain first.[/]")
        # FT-001: prerequisites missing → the on-ledger assertion could not run.
        _record_verification(
            context, "verify_domain", passed=False,
            failures=["domain_id/owner missing — the step that produces it did not run"],
        )
        return context
    result = await verify_domain(
        transport, owner_address, domain_id,
        expect_issuer=expect_issuer, expect_credential_type=expect_type,
    )
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    context["last_domain_verify"] = result
    _record_verification(
        context, "verify_domain", result.passed, result.failures
    )
    return context


async def handle_verify_permissioned_offer(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Verify the credentialed account's permissioned offer is resting on-ledger."""
    subject_address = context.get("subject_address", "")
    offer_seq = context.get("permissioned_offer_seq")
    if not subject_address or offer_seq is None:
        console.print("  [red]No permissioned offer in context. Place it first.[/]")
        # FT-001: prerequisites missing → the on-ledger assertion could not run.
        _record_verification(
            context, "verify_permissioned_offer", passed=False,
            failures=[
                "subject/offer sequence missing — the step that produces them did not run"
            ],
        )
        return context
    result = await verify_permissioned_offer(
        transport, subject_address, offer_seq, expect_placed=True
    )
    for c in result.checks:
        console.print(f"  [green]✓[/] {c}")
    for f in result.failures:
        console.print(f"  [red]✗[/] {f}")
    context["last_permissioned_offer_verify"] = result
    _record_verification(
        context, "verify_permissioned_offer", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Deposit Gate: DepositAuth + DepositPreauth (identity track, XLS-70 extension)
# ---------------------------------------------------------------------------
#
# Completes the XLS-70 arc: composes with credentials_101 (reusing
# CredentialCreate/CredentialAccept unchanged — no new credential machinery
# here) to gate INBOUND value to a treasury, rather than a trading book
# (permissioned_domains_101's DomainID rail). The learner's wallet plays BOTH
# the protected treasury AND the credential issuer, exactly like
# permissioned_domains_101's dual owner/issuer role.


async def handle_enable_deposit_auth(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Enable asfDepositAuth on the treasury (AccountSet).

    From this point the treasury REJECTS any unsolicited incoming Payment
    from a non-preauthorized sender (tecNO_PERMISSION) — pull-style txns
    (CheckCash / EscrowFinish / OfferCreate / PaymentChannelClaim) still work.
    """
    address = state.wallet_address or ""
    console.print(
        "  Enabling [cyan]asfDepositAuth[/] on the treasury — unsolicited "
        "incoming Payments will now be rejected unless the sender is "
        "preauthorized..."
    )
    result = await enable_deposit_auth(transport, wallet_seed, wallet_address=address)
    if result.success:
        console.print(
            "  [green]Deposit Authorization enabled.[/] Only a preauthorized "
            "sender — by address or by credential — can pay this account now."
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["deposit_auth_enabled"] = True
    else:
        console.print(f"  [red]Enabling Deposit Authorization failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_sender_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund the SENDER wallet — a random player, no preauthorization yet."""
    console.print(
        "  Creating the sender's wallet (a random player with no "
        "preauthorization yet)..."
    )
    sender = create_wallet()
    context["sender_seed"] = _SecretValue(sender.seed)
    context["sender_address"] = sender.address
    console.print(f"  Sender wallet: [cyan]{sender.address}[/]")
    result = await transport.fund_from_faucet(sender.address)
    if result.success:
        console.print(f"  Sender funded! Balance: [green]{result.balance} XRP[/]")
    elif getattr(result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
        console.print(f"  [dim]{err.hint}[/]")
    else:
        console.print(f"  [yellow]Sender funding: {result.message}[/]")
    return context


async def handle_send_sender_payment_expect_blocked(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The sender's Payment is BLOCKED — expects tecNO_PERMISSION.

    DepositAuth is on and the sender holds no preauthorization yet (neither
    by address nor by credential) — the ledger refuses the unsolicited Payment.
    """
    args = step.action_args
    amount = args.get("amount", "10")
    _raw = context.get("sender_seed", "")
    sender_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    treasury = state.wallet_address or ""
    if not sender_seed or not treasury:
        console.print(
            "  [red]Missing sender wallet or treasury address. Run the "
            "wallet steps first.[/]"
        )
        return context
    console.print(
        f"  [yellow]Sender attempting to pay {amount} XRP into the treasury "
        "(expecting tecNO_PERMISSION — no preauthorization yet)...[/]"
    )
    result = await send_gated_payment(
        transport, sender_seed, treasury, amount, memo="XRPLLAB|DEPOSITGATE",
        sender_address=context.get("sender_address", ""),
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the Payment landed despite no "
            "preauthorization. Recording the tx.[/]"
        )
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid, module_id=context.get("module_id", ""),
                network=state.network, success=True,
                explorer_url=result.explorer_url,
            )
            save_state(state)
    else:
        if result.result_code == "tecNO_PERMISSION":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(
                "  [dim]The treasury rejected the unsolicited Payment — "
                "Deposit Authorization blocks anyone not preauthorized.[/]"
            )
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"tecNO_PERMISSION. The demonstration did not exercise the gate.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_preauthorize_self_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Treasury tries to preauthorize ITS OWN address — expects temCANNOT_PREAUTH_SELF."""
    address = state.wallet_address or ""
    console.print(
        "  [yellow]Treasury attempting to preauthorize its OWN address "
        "(expecting temCANNOT_PREAUTH_SELF)...[/]"
    )
    result = await authorize_deposit_address(
        transport, wallet_seed, address, wallet_address=address
    )
    if result.success:
        console.print("  [yellow]Unexpected success — recording the tx.[/]")
        _record_submit(state, context, result)
    else:
        if result.result_code == "temCANNOT_PREAUTH_SELF":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(
                "  [dim]An account can never preauthorize itself — that's not "
                "what the field is for.[/]"
            )
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"temCANNOT_PREAUTH_SELF.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_authorize_sender_address(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Treasury preauthorizes the sender BY ADDRESS (DepositPreauth Authorize)."""
    address = state.wallet_address or ""
    sender_address = context.get("sender_address", "")
    if not sender_address:
        console.print(
            "  [red]No sender wallet in context. Run the sender-wallet step first.[/]"
        )
        return context
    console.print(
        f"  Preauthorizing sender [cyan]{sender_address[:12]}...[/] by "
        "address (DepositPreauth Authorize)..."
    )
    result = await authorize_deposit_address(
        transport, wallet_seed, sender_address, wallet_address=address
    )
    if result.success:
        console.print(
            "  [green]Sender preauthorized — its Payments will now be admitted.[/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]Preauthorization failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_authorize_sender_address_duplicate(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Re-preauthorize the SAME sender address — expects tecDUPLICATE."""
    address = state.wallet_address or ""
    sender_address = context.get("sender_address", "")
    console.print(
        "  [yellow]Re-preauthorizing the SAME sender address (expecting "
        "tecDUPLICATE)...[/]"
    )
    result = await authorize_deposit_address(
        transport, wallet_seed, sender_address, wallet_address=address
    )
    if result.success:
        console.print("  [yellow]Unexpected success — recording the tx.[/]")
        _record_submit(state, context, result)
    else:
        if result.result_code == "tecDUPLICATE":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(
                "  [dim]This DepositPreauth object already exists — nothing "
                "to add.[/]"
            )
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected tecDUPLICATE.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_send_sender_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The now-preauthorized sender's Payment lands."""
    args = step.action_args
    amount = args.get("amount", "10")
    _raw = context.get("sender_seed", "")
    sender_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    treasury = state.wallet_address or ""
    if not sender_seed or not treasury:
        console.print(
            "  [red]Missing sender wallet or treasury address. Run the "
            "wallet steps first.[/]"
        )
        return context
    console.print(f"  Preauthorized sender paying {amount} XRP into the treasury...")
    result = await send_gated_payment(
        transport, sender_seed, treasury, amount, memo="XRPLLAB|DEPOSITGATE",
        sender_address=context.get("sender_address", ""),
    )
    if result.success:
        console.print(
            "  [green]Payment landed — the address preauthorization admitted it.[/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]Payment failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_authorize_kyc_credential(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Treasury preauthorizes BY CREDENTIAL (DepositPreauth AuthorizeCredentials).

    Reuses the {issuer, credential_type} the FC-002 steps issued — any sender
    holding a currently valid (accepted, unexpired) credential of this type
    from this issuer may now deposit, without being individually whitelisted.
    """
    address = state.wallet_address or ""
    credential_type = context.get("credential_type", "kyc-deposit")
    issuer_address = context.get("credential_issuer", address)
    console.print(
        f"  Preauthorizing BY CREDENTIAL — any sender holding an accepted "
        f"[cyan]{credential_type}[/] credential from "
        f"[cyan]{issuer_address[:12]}...[/] may now deposit..."
    )
    result = await authorize_deposit_credential(
        transport, wallet_seed, issuer_address, credential_type, wallet_address=address
    )
    if result.success:
        console.print("  [green]Credential-based preauthorization installed.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]Credential preauthorization failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_send_kyc_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The KYC'd player attaches CredentialIDs and pays — succeeds.

    Resolves the accepted credential's on-ledger CredentialID and attaches it
    via Payment.CredentialIDs — the deposit-authorization rail, distinct from
    Permissioned Domains' DomainID (trading) rail.
    """
    args = step.action_args
    amount = args.get("amount", "10")
    _raw = context.get("subject_seed", "")
    subject_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    subject_address = context.get("subject_address", "")
    treasury = state.wallet_address or ""
    credential_type = context.get("credential_type", "kyc-deposit")
    issuer_address = context.get("credential_issuer", treasury)
    if not subject_seed or not subject_address:
        console.print(
            "  [red]No KYC'd player wallet. Run the credential steps first.[/]"
        )
        return context
    cred_id = await get_credential_id(
        transport, subject_address, issuer_address, credential_type
    )
    if not cred_id:
        console.print(
            "  [red]Could not resolve the accepted credential's on-ledger "
            "id. Run the create/accept-credential steps first.[/]"
        )
        return context
    console.print(
        f"  KYC'd player paying {amount} XRP, attaching "
        f"CredentialIDs=[cyan]{cred_id[:16]}...[/]"
    )
    result = await send_gated_payment(
        transport, subject_seed, treasury, amount,
        credential_ids=[cred_id], memo="XRPLLAB|DEPOSITGATE-KYC",
        sender_address=subject_address,
    )
    if result.success:
        console.print(
            "  [green]Payment landed — the credential satisfied the "
            "treasury's AuthorizeCredentials policy.[/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]Payment failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_send_outsider_payment_expect_blocked(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The outsider's Payment stays BLOCKED — expects tecNO_PERMISSION.

    Holds no address preauthorization and no credential the treasury accepts
    — proves the credential-based gate is not a general bypass.
    """
    args = step.action_args
    amount = args.get("amount", "10")
    _raw = context.get("outsider_seed", "")
    outsider_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    treasury = state.wallet_address or ""
    if not outsider_seed:
        console.print(
            "  [red]No outsider wallet in context. Run the outsider-wallet "
            "step first.[/]"
        )
        return context
    console.print(
        f"  [yellow]Outsider attempting to pay {amount} XRP — no address "
        "preauthorization, no credential (expecting tecNO_PERMISSION)...[/]"
    )
    result = await send_gated_payment(
        transport, outsider_seed, treasury, amount, memo="XRPLLAB|DEPOSITGATE-OUT",
        sender_address=context.get("outsider_address", ""),
    )
    if result.success:
        console.print("  [yellow]Unexpected success — recording the tx.[/]")
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid, module_id=context.get("module_id", ""),
                network=state.network, success=True,
                explorer_url=result.explorer_url,
            )
            save_state(state)
    else:
        if result.result_code == "tecNO_PERMISSION":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(
                "  [dim]No address preauth, no matching credential — the "
                "gate holds for anyone outside both policies.[/]"
            )
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"tecNO_PERMISSION.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_unauthorize_sender_address(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Revoke the sender's address preauthorization — the named compensator."""
    address = state.wallet_address or ""
    sender_address = context.get("sender_address", "")
    console.print(
        "  Revoking the sender's address preauthorization (compensator)..."
    )
    result = await unauthorize_deposit_address(
        transport, wallet_seed, sender_address, wallet_address=address
    )
    if result.success:
        console.print("  [green]Preauthorization revoked — reserve freed.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]Revocation failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_unauthorize_sender_address_duplicate(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Revoke the SAME (already-revoked) preauthorization again — expects tecNO_ENTRY."""
    address = state.wallet_address or ""
    sender_address = context.get("sender_address", "")
    console.print(
        "  [yellow]Revoking the SAME preauthorization again (expecting "
        "tecNO_ENTRY)...[/]"
    )
    result = await unauthorize_deposit_address(
        transport, wallet_seed, sender_address, wallet_address=address
    )
    if result.success:
        console.print("  [yellow]Unexpected success — recording the tx.[/]")
        _record_submit(state, context, result)
    else:
        if result.result_code == "tecNO_ENTRY":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print("  [dim]Nothing to revoke — it's already gone.[/]")
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected tecNO_ENTRY.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
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
        # PB-003: surface the non-numeric fallback (matches check_inventory).
        console.print("  [yellow]Invalid asset_scale, using default (0).[/]")
        asset_scale = 0
    try:
        transfer_fee = int(args.get("transfer_fee", "0"))
    except ValueError:
        console.print("  [yellow]Invalid transfer_fee, using default (0).[/]")
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
        # Thread the new issuance id forward so mpt_authorize / mpt_payment /
        # verify_mpt_balance can address this exact MPT (FT-CURRIC-004).
        if result.mpt_issuance_id:
            context["mpt_issuance_id"] = result.mpt_issuance_id
            console.print(f"  Issuance ID: [cyan]{result.mpt_issuance_id}[/]")
    else:
        console.print(f"  [red]MPT issuance failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_mpt_authorize(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    issuance_id = context.get("mpt_issuance_id", "")
    if not issuance_id:
        console.print("  [red]No MPT issuance id in context. Create the issuance first.[/]")
        return context
    if "wallet_seed" not in context:
        console.print("  [red]No holder wallet in context. Run the wallet step first.[/]")
        return context
    console.print("  Authorizing this wallet to hold the MPT (MPTokenAuthorize)...")
    result = await authorize_mpt(transport, context["wallet_seed"].get(), issuance_id)
    if result.success:
        console.print("  [green]Authorized — the holder can now receive this MPT.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]MPTokenAuthorize failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_mpt_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    amount = args.get("amount", "100")
    issuance_id = context.get("mpt_issuance_id", "")
    _raw = context.get("issuer_seed", "")
    issuer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    holder = state.wallet_address or ""

    if not issuance_id or not issuer_seed or not holder:
        console.print("  [red]Missing issuance id, issuer wallet, or holder. Run prior steps.[/]")
        return context

    console.print(f"  Issuer paying [cyan]{amount}[/] MPT to the holder...")
    result = await send_mpt(transport, issuer_seed, holder, issuance_id, amount)
    if result.success:
        console.print(f"  [green]{amount} MPT delivered to the player![/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
    else:
        console.print(f"  [red]MPT payment failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_mpt_balance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    args = step.action_args
    expected = args.get("expected")
    issuance_id = context.get("mpt_issuance_id", "")
    holder = state.wallet_address or ""
    if not issuance_id or not holder:
        console.print("  [red]Missing issuance id or holder. Run previous steps first.[/]")
        # FT-001: no issuance/holder → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_mpt_balance", passed=False,
            failures=["MPT issuance id/holder missing — the step that produces them did not run"],
        )
        return context
    result = await verify_mpt_balance(transport, holder, issuance_id, expected=expected)
    for check in result.checks:
        console.print(f"  [green]✓[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]✗[/] {fail}")
    context["last_mpt_balance_verify"] = result
    _record_verification(
        context, "verify_mpt_balance", len(result.failures) == 0, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Partial-payment exploit / delivered_amount (FC-003 — payments track)
# ---------------------------------------------------------------------------


async def handle_send_partial_payment(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Issuer sends an issued-currency Payment WITH tfPartialPayment that
    UNDER-delivers — the setup for the delivered_amount lesson (FC-003)."""
    args = step.action_args
    currency = args.get("currency", "LAB")
    amount = args.get("amount", "100")          # Amount field / DeliverMax — the CAP
    deliver_min = args.get("deliver_min", "10")  # what actually gets delivered
    send_max = args.get("send_max", "10")        # caps source spend (forces the reduction)
    _raw = context.get("issuer_seed", "")
    issuer_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    issuer_address = context.get("issuer_address", "")
    holder = state.wallet_address or ""

    if not issuer_seed or not issuer_address or not holder:
        console.print(
            "  [red]Missing issuer wallet or holder. Run the trust-line / issuer "
            "steps first.[/]"
        )
        return context

    console.print(
        f"  Issuer sending [cyan]{amount} {currency}[/] with "
        f"[yellow]tfPartialPayment[/] (SendMax {send_max}, DeliverMin "
        f"{deliver_min})..."
    )
    console.print(
        "  [dim]The Amount field will claim the full amount; the flag lets the "
        "ledger deliver LESS and still return tesSUCCESS.[/]"
    )
    result = await send_partial_payment(
        transport, issuer_seed, holder, currency, issuer_address,
        amount, deliver_min, send_max, memo="XRPLLAB|PARTIAL",
    )
    if result.success:
        console.print("  [green]Partial payment submitted — tesSUCCESS.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        console.print(
            "  [yellow]But how much actually arrived? Read delivered_amount to "
            "find out — never the Amount field.[/]"
        )
        context["partial_payment_txid"] = result.txid
        context["partial_payment_amount"] = amount
        context["partial_payment_delivered"] = deliver_min
    else:
        console.print(f"  [red]Partial payment failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_verify_delivered_amount(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Read delivered_amount off the validated tx and contrast it with the
    Amount field — proving the partial-payment exploit (FC-003)."""
    txid = context.get("partial_payment_txid", "")
    expected = context.get("partial_payment_delivered")
    if not txid:
        console.print(
            "  [red]No partial-payment tx to inspect. Run the partial-payment "
            "step first.[/]"
        )
        # FT-001: the step that produces the txid never ran → honest FAILED
        # verification, not an invisible skip.
        _record_verification(
            context, "verify_delivered_amount", passed=False,
            failures=[
                "partial_payment_txid missing — the step that produces it did not run"
            ],
        )
        return context

    result = await verify_delivered_amount(transport, txid, expected_delivered=expected)
    for check in result.checks:
        console.print(f"  [green]✓[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]✗[/] {fail}")

    if result.exploit_demonstrated:
        console.print()
        console.print(
            "  [bold yellow]THE EXPLOIT:[/] the tx said tesSUCCESS and its "
            f"Amount field claimed [cyan]{result.amount_field}[/], but only "
            f"[cyan]{result.delivered_amount}[/] was actually delivered. A "
            "backend crediting the Amount field would hand out money it never "
            "received."
        )
        console.print(
            "  [dim]Lesson (RECEIVING): always read delivered_amount, never "
            "DeliverMax, and only after tesSUCCESS + validated:true.[/]"
        )

    context["last_delivered_amount_verify"] = result
    _record_verification(
        context, "verify_delivered_amount", result.passed, result.failures
    )
    return context


# ---------------------------------------------------------------------------
# Custodial player crediting (destination tags — payments track)
# ---------------------------------------------------------------------------


async def handle_enable_require_dest(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Enable asfRequireDest on the pooled treasury (AccountSet).

    From this point the pool REJECTS any untagged incoming Payment with
    tecDST_TAG_NEEDED — fail-closed custody hygiene, always on for a shared
    hot wallet.
    """
    address = state.wallet_address or ""
    console.print(
        "  Enabling [cyan]asfRequireDest[/] on the pooled treasury — "
        "untagged deposits will now bounce (tecDST_TAG_NEEDED)..."
    )
    result = await enable_require_dest(
        transport, wallet_seed, wallet_address=address
    )
    if result.success:
        console.print(
            "  [green]RequireDest enabled — every incoming Payment must "
            "carry a DestinationTag.[/]"
        )
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        context["require_dest_enabled"] = True
    else:
        console.print(f"  [red]RequireDest enable failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_create_player_wallet(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Create + fund the PLAYER wallet — the depositor on the other side.

    The player is a distinct account so the deposit is a real third-party
    Payment into the pool, exactly like production traffic.
    """
    console.print("  Creating the player's wallet (the depositor)...")
    player = create_wallet()
    context["player_seed"] = _SecretValue(player.seed)
    context["player_address"] = player.address
    console.print(f"  Player wallet: [cyan]{player.address}[/]")

    fund = await transport.fund_from_faucet(player.address)
    if fund.success:
        console.print(f"  Player funded! Balance: [green]{fund.balance} XRP[/]")
    elif getattr(fund, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED":
        from .errors import faucet_rate_limited

        err = faucet_rate_limited()
        console.print(f"  [yellow]{err.message}[/]")
    else:
        console.print(f"  [yellow]Player funding: {fund.message}[/]")
    return context


async def handle_assign_player_tag(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Assign the player a deposit tag in the backend's OFF-LEDGER registry.

    No transaction here on purpose: the tag→player map has NO on-ledger
    representation. It lives in the studio's database, it is load-bearing
    (lose it and every pooled deposit becomes unattributable), and it must be
    backed up like any other production table.
    """
    args = step.action_args
    try:
        tag = int(args.get("tag", "1001"))
    except (TypeError, ValueError):
        console.print("  [yellow]Invalid tag, using default (1001).[/]")
        tag = 1001
    player = args.get("player", "arya") or "arya"

    registry = context.setdefault("tag_registry", {})
    if tag in registry and registry[tag] != player:
        console.print(
            f"  [yellow]Tag {tag} is already assigned to "
            f"'{registry[tag]}' — never reuse a live tag for a second "
            f"player. Reassigning for this lesson.[/]"
        )
    registry[tag] = player
    context["player_tag"] = tag
    context["player_name"] = player
    console.print(
        f"  Backend registry entry: tag [cyan]{tag}[/] -> player "
        f"[cyan]{player}[/]"
    )
    console.print(
        "  [dim]Off-ledger only — the ledger never sees this map. It is "
        "load-bearing: back it up.[/]"
    )
    return context


async def handle_send_tagged_deposit(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The player deposits XRP into the pool WITH a DestinationTag."""
    args = step.action_args
    amount = args.get("amount", "25")
    try:
        tag = int(args.get("tag") or context.get("player_tag") or 1001)
    except (TypeError, ValueError):
        tag = 1001
    source_tag: int | None = None
    raw_source = args.get("source_tag", "")
    if raw_source:
        try:
            source_tag = int(raw_source)
        except (TypeError, ValueError):
            console.print(
                f"  [yellow]Invalid source_tag {raw_source!r}; omitting it.[/]"
            )

    _raw = context.get("player_seed", "")
    player_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    pool = state.wallet_address or ""
    if not player_seed or not pool:
        console.print(
            "  [red]Missing player wallet or pool address. Run the wallet / "
            "player steps first.[/]"
        )
        return context

    console.print(
        f"  Player sending [cyan]{amount} XRP[/] to the pool with "
        f"DestinationTag [cyan]{tag}[/]"
        + (f" (SourceTag {source_tag})" if source_tag is not None else "")
        + "..."
    )
    result = await send_tagged_deposit(
        transport, player_seed, pool, amount,
        destination_tag=tag, source_tag=source_tag, memo="XRPLLAB|DEPOSIT",
    )
    if result.success:
        console.print("  [green]Tagged deposit validated.[/]")
        console.print(f"  TXID: [cyan]{result.txid}[/]")
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        console.print(
            "  [dim]The tag rode the transaction on-ledger — but it MEANS "
            "nothing until the backend maps it. That attribution is next.[/]"
        )
        context["deposit_txid"] = result.txid
        context["deposit_amount"] = amount
        context["deposit_tag"] = tag
    else:
        console.print(f"  [red]Deposit failed: {result.error}[/]")
        _explain_failure(console, result.result_code)
    _record_submit(state, context, result)
    return context


async def handle_send_untagged_deposit_expect_fail(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """The player sends an UNTAGGED deposit — expects tecDST_TAG_NEEDED.

    Submit-and-learn: with asfRequireDest on the pool, the ledger refuses the
    payment rather than let it land unattributable. This is the wall a real
    integration hits the first time a wallet omits the tag.
    """
    args = step.action_args
    amount = args.get("amount", "10")
    _raw = context.get("player_seed", "")
    player_seed = _raw.get() if isinstance(_raw, _SecretValue) else _raw
    pool = state.wallet_address or ""
    if not player_seed or not pool:
        console.print(
            "  [red]Missing player wallet or pool address. Run the wallet / "
            "player steps first.[/]"
        )
        return context
    if not context.get("require_dest_enabled"):
        console.print(
            "  [yellow]asfRequireDest was not enabled on this pool (run the "
            "enable step first) — an untagged deposit will LAND, "
            "unattributable, instead of bouncing.[/]"
        )

    console.print(
        f"  [yellow]Player sending {amount} XRP with NO DestinationTag "
        "(expecting tecDST_TAG_NEEDED)...[/]"
    )
    result = await send_tagged_deposit(
        transport, player_seed, pool, amount,
        destination_tag=None, memo="XRPLLAB|UNTAGGED",
    )
    if result.success:
        console.print(
            "  [yellow]Unexpected success — the untagged deposit LANDED. "
            "Without RequireDest these funds would sit unattributable in "
            "the pool.[/]"
        )
        if result.explorer_url:
            console.print(f"  Explorer: [blue]{result.explorer_url}[/]")
        # Record only a REAL txid on the unexpected-success branch (mirrors
        # the F-d18b2348 rule — no {txid:"failed", success:true} records).
        if result.txid:
            context.setdefault("txids", []).append(result.txid)
            state.record_tx(
                txid=result.txid, module_id=context.get("module_id", ""),
                network=state.network, success=True,
                explorer_url=result.explorer_url,
            )
            save_state(state)
    else:
        # Name the code honestly — only tecDST_TAG_NEEDED is the taught
        # missing-tag rejection; anything else is a DIFFERENT failure and must
        # not be green-printed as the expected one (F-59ba7d9d discipline).
        if result.result_code == "tecDST_TAG_NEEDED":
            console.print(f"  [green]Expected failure:[/] {result.result_code}")
            console.print(
                "  [dim]The pool refused the deposit rather than accept "
                "funds it cannot attribute. Fail-closed is the point.[/]"
            )
        else:
            console.print(
                f"  [yellow]Failed with {result.result_code} — expected "
                f"tecDST_TAG_NEEDED (the missing-tag rejection). The "
                f"demonstration did not exercise the RequireDest rule.[/]"
            )
        console.print(f"  {result.error}")
        _explain_failure(console, result.result_code)
        context.setdefault("failed_txids", []).append(
            {"result_code": result.result_code, "error": result.error}
        )
    return context


async def handle_credit_player_deposit(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    """Attribute the deposit via its DestinationTag and credit delivered_amount.

    The custodial receiving discipline end-to-end: tesSUCCESS + validated
    first, tag read from the tx, tag validated against the backend's OWN
    registry (a tag is a routing hint, not authentication), and the credit
    taken from delivered_amount — never the Amount field.
    """
    args = step.action_args
    txid = context.get("deposit_txid", "")
    registry = context.get("tag_registry", {}) or {}
    if not txid:
        console.print(
            "  [red]No deposit to credit. Run the tagged-deposit step first.[/]"
        )
        # FT-001: the step that produces the txid never ran → honest FAILED
        # verification, not an invisible skip.
        _record_verification(
            context, "credit_player_deposit", passed=False,
            failures=["deposit_txid missing — the step that produces it did not run"],
        )
        return context

    expected_xrp = args.get("expected") or context.get("deposit_amount")
    expected_drops: str | None = None
    if expected_xrp:
        try:
            expected_drops = str(int(Decimal(str(expected_xrp)) * 1_000_000))
        except (InvalidOperation, ValueError):
            console.print(
                f"  [yellow]Could not parse expected amount "
                f"{expected_xrp!r}; skipping the exact-amount assertion.[/]"
            )

    result = await credit_player_deposit(
        transport, txid, registry, expected_drops=expected_drops
    )
    for check in result.checks:
        console.print(f"  [green]✓[/] {check}")
    for fail in result.failures:
        console.print(f"  [red]✗[/] {fail}")

    if result.passed:
        console.print()
        console.print(
            f"  [bold green]CREDITED:[/] player [cyan]{result.player}[/] "
            f"(tag {result.tag}) +[cyan]{result.credited_drops}[/] drops — "
            "attributed by the tag, validated against the registry, credited "
            "from delivered_amount."
        )
    context["last_player_credit"] = result
    _record_verification(
        context, "credit_player_deposit", result.passed, result.failures
    )
    return context


async def handle_verify_mpt_issuance(
    step: ModuleStep, state: LabState, transport: Transport,
    wallet_seed: str, context: dict, console: Console,
) -> dict:
    address = state.wallet_address or ""
    if not address:
        console.print("  [red]No wallet address. Run the wallet step first.[/]")
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_mpt_issuance", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
        return context
    result = await verify_mpt_issuance(transport, address, expected_maximum=context.get("mpt_max"))
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.found and result.passed:
        console.print("  [green]MPT issuance verified on-ledger.[/]")
    context["last_mpt_verify"] = result
    _record_verification(
        context, "verify_mpt_issuance",
        result.found and result.passed, result.failures,
    )
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
        # FT-001: no wallet → this on-ledger assertion could not run.
        _record_verification(
            context, "verify_clawback", passed=False,
            failures=["wallet address missing — the step that produces it did not run"],
        )
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
    _record_verification(
        context, "verify_clawback", result.passed, result.failures
    )
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
    # INFORMATIONAL: this handler READS the NFT's open offers back for
    # observation — it prints a note when none exist rather than asserting a
    # failure. Record passed=True (never fabricate a failure verdict); the
    # trade's real pass/fail assertion lives in verify_nft_trade.
    _record_verification(context, "verify_nft_offer", True, [])
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
        # BC-006: the former `context["nft_seller_address"] = ...` write was
        # dead — handle_verify_nft_trade verifies ownership against
        # `nft_prev_owner` (set below), never `nft_seller_address`. Removed.
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
        # FT-001: no completed trade → this on-ledger ownership assertion could
        # not run because the mint/accept steps never produced it.
        _record_verification(
            context, "verify_nft_trade", passed=False,
            failures=["nft_id/buyer address missing — the step that produces them did not run"],
        )
        return context

    result = await verify_nft_owned_by(
        transport, buyer_addr, nft_id, previous_owner=prev_owner
    )
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")

    # Royalty observation. F-b1ebc369: the issuer's raw balance delta is only
    # a royalty when the issuer is a THIRD PARTY to the trade. In this module
    # the issuer (the learner's wallet) is a PRINCIPAL on both hops — seller on
    # the first sale (delta = full sale PRICE, no royalty paid) and buyer on
    # the resale (delta ≈ -(price - royalty)) — so the old "+delta = royalty"
    # print labeled the sale price a royalty and reported "no royalty" on the
    # only hop that actually paid one. When the issuer is a principal, compute
    # the royalty from the mint's TransferFee (units of 1/100000) × price.
    before = context.get("nft_issuer_balance_before")
    after = context.get("nft_issuer_balance_after")
    if before is not None and after is not None:
        try:
            delta = Decimal(str(after)) - Decimal(str(before))
        except (InvalidOperation, ValueError):
            delta = Decimal("0")
        issuer_addr = state.wallet_address or ""
        principals = {buyer_addr, prev_owner}
        if issuer_addr and issuer_addr not in principals:
            # Third-party issuer: the balance delta IS the protocol royalty.
            if delta > 0:
                console.print(
                    f"  [green]Royalty (TransferFee) paid to issuer: "
                    f"+{delta} XRP — protocol-enforced creator royalty.[/]"
                )
            else:
                console.print(
                    "  [dim]No royalty on this hop (first sale from the issuer "
                    "pays none; the TransferFee is enforced on resales).[/]"
                )
        elif prev_owner == issuer_addr:
            # First sale: the issuer IS the seller — the delta is the sale
            # price, not a royalty (you don't pay yourself a royalty).
            console.print(
                f"  [dim]No royalty on this hop — the issuer is the SELLER "
                f"(first sale): the +{delta} XRP delta is the sale price "
                f"itself. The TransferFee is enforced on resales.[/]"
            )
        else:
            # Resale where the issuer takes part (here: buys the NFT back).
            # The delta mixes the price paid with the royalty received, so
            # compute the royalty from the protocol fields instead.
            royalty = None
            fee = context.get("nft_transfer_fee")
            price = context.get("nft_offer_price")
            try:
                if fee and price is not None:
                    royalty = Decimal(str(price)) * Decimal(int(fee)) / Decimal(100000)
            except (InvalidOperation, ValueError, TypeError):
                royalty = None
            if royalty is not None and royalty > 0:
                console.print(
                    f"  [green]Royalty (TransferFee) enforced on this resale: "
                    f"{royalty} XRP of the {price} XRP price went to the "
                    f"issuer — protocol-enforced, no marketplace code needed. "
                    f"(The issuer also took part in the trade, so its raw "
                    f"balance delta of {delta:+} XRP mixes price and "
                    f"royalty.)[/]"
                )
            else:
                console.print(
                    "  [dim]Royalty note: the issuer took part in this trade, "
                    "so its balance delta mixes price and royalty; no "
                    "TransferFee was recorded at mint to compute it from.[/]"
                )
    if result.passed:
        console.print("  [green]NFT trade verified on-ledger.[/]")
    context["last_nft_trade_verify"] = result
    _record_verification(
        context, "verify_nft_trade", result.passed, result.failures
    )
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
        # FT-001: no modified NFT in context → this on-ledger assertion could
        # not run because the mint/modify steps never produced it.
        _record_verification(
            context, "verify_nft_modified", passed=False,
            failures=[
                "modified NFT (address/nft_id/uri) missing — the step that produces it did not run"
            ],
        )
        return context
    result = await verify_nft_modified(transport, address, nft_id, expected)
    for c in result.checks:
        console.print(f"  [green]{c}[/]")
    for f in result.failures:
        console.print(f"  [red]{f}[/]")
    if result.passed:
        console.print("  [green]Dynamic NFT verified — item evolved on-ledger.[/]")
    context["last_nft_modified_verify"] = result
    _record_verification(
        context, "verify_nft_modified", result.passed, result.failures
    )
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
                             description="NFTokenID to burn (defaults to the id "
                                         "captured at mint; never guessed from "
                                         "the on-ledger list)"),
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
        # ── FC-001: token escrow (XLS-85) — payments track ──
        ActionDef(
            name="set_allow_trustline_locking",
            handler=handle_set_allow_trustline_locking,
            description="Issuer opts in to token escrow (AccountSet asfAllowTrustLineLocking)",
            wallet_required=True,
        ),
        ActionDef(
            name="create_token_recipient",
            handler=handle_create_token_recipient,
            description="Create + fund a third-party recipient and set its trust line",
            payload_fields=[
                PayloadField(name="currency", default="GLD"),
                PayloadField(name="limit", default="1000"),
            ],
        ),
        ActionDef(
            name="snapshot_recipient_balance",
            handler=handle_snapshot_recipient_balance,
            description="Snapshot the recipient's issued balance (before/after the escrow)",
            payload_fields=[
                PayloadField(name="currency", default="GLD"),
                PayloadField(name="label", default="before"),
            ],
        ),
        ActionDef(
            name="create_token_escrow",
            handler=handle_create_token_escrow,
            description="Holder escrows an issued token (IOU) to a recipient (XLS-85)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="GLD"),
                PayloadField(name="amount", default="50", description="IOU amount to escrow"),
                PayloadField(name="destination", description="Recipient (defaults to context)"),
                PayloadField(name="finish_seconds", type="int", default="30",
                             description="Seconds until FinishAfter (fix1571 requires "
                                         "FinishAfter or a Condition on every EscrowCreate)"),
                PayloadField(name="cancel_seconds", type="int", default="86400",
                             description="Seconds until CancelAfter (mandatory for token escrow)"),
            ],
        ),
        ActionDef(
            name="create_noopt_issuer",
            handler=handle_create_noopt_issuer,
            description=(
                "Create a second issuer WITHOUT the token-escrow opt-in "
                "(sets up the failure case)"
            ),
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="NOP"),
                PayloadField(name="amount", default="50"),
            ],
        ),
        ActionDef(
            name="create_token_escrow_expect_fail",
            handler=handle_create_token_escrow_expect_fail,
            description="Attempt a token escrow without issuer opt-in (expects tecNO_PERMISSION)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="NOP"),
                PayloadField(name="amount", default="50"),
                PayloadField(name="finish_seconds", type="int", default="30"),
                PayloadField(name="cancel_seconds", type="int", default="86400"),
            ],
        ),
        ActionDef(
            name="finish_token_escrow",
            handler=handle_finish_token_escrow,
            description="Recipient finishes the token escrow, releasing the IOU (EscrowFinish)",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_token_moved",
            handler=handle_verify_token_moved,
            description="Verify the escrowed IOU reached the recipient's trust line",
        ),
        # ── Multisig treasury (SignerListSet) — foundations track ──
        ActionDef(
            name="create_signer_wallets",
            handler=handle_create_signer_wallets,
            description="Create N unfunded keyholder wallets for the signer list",
            payload_fields=[
                PayloadField(name="count", type="int", default="3",
                             description="How many keyholder wallets (1-8)"),
            ],
        ),
        ActionDef(
            name="set_signer_list",
            handler=handle_set_signer_list,
            description="Install an N-of-M signer list on the treasury (SignerListSet)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="quorum", type="int", default="2",
                             description="Min combined weight to authorize"),
                PayloadField(name="weights", default="1,1,1",
                             description="Comma-separated per-signer weights"),
            ],
        ),
        ActionDef(
            name="verify_signer_list",
            handler=handle_verify_signer_list,
            description="Verify the on-ledger signer list matches the installed quorum + roster",
        ),
        ActionDef(
            name="send_multisig_payment",
            handler=handle_send_multisig_payment,
            description="Submit a multi-signed Payment meeting the quorum",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
                PayloadField(name="signer_count", type="int", default="2",
                             description="How many keyholders co-sign"),
                PayloadField(name="destination",
                             description="Payee (defaults to signer 1's address)"),
            ],
        ),
        ActionDef(
            name="send_multisig_payment_expect_fail",
            handler=handle_send_multisig_payment_expect_fail,
            description="Attempt a below-quorum multi-signed payment (expects tefBAD_QUORUM)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="10"),
                PayloadField(name="signer_count", type="int", default="1",
                             description="Signers to use (below quorum)"),
                PayloadField(name="destination"),
            ],
        ),
        ActionDef(
            name="delete_signer_list",
            handler=handle_delete_signer_list,
            description="Delete the signer list (SignerQuorum=0, entries omitted), freeing reserve",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_signer_list_deleted",
            handler=handle_verify_signer_list_deleted,
            description="Verify the SignerList object is gone from the account",
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
        # ── Credentials (FC-002, XLS-70) ──
        ActionDef(
            name="create_subject_wallet",
            handler=handle_create_subject_wallet,
            description="Create + fund the subject (player) wallet to be attested",
        ),
        ActionDef(
            name="create_credential_unfunded",
            handler=handle_create_credential_unfunded,
            description="Attest a credential against an unfunded subject (teaches tecNO_TARGET)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="credential_type", default="over21",
                             description="Credential tag (hex-encoded automatically)"),
                PayloadField(name="subject",
                             description="Unfunded subject address to attest against"),
            ],
        ),
        ActionDef(
            name="create_credential",
            handler=handle_create_credential,
            description="Issuer attests a credential about the subject (CredentialCreate)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="credential_type", default="over21",
                             description="Credential tag (e.g. kyc, over21; hex-encoded)"),
                PayloadField(name="uri",
                             description="Optional URI to an off-chain VC (immutable)"),
            ],
        ),
        ActionDef(
            name="create_credential_duplicate",
            handler=handle_create_credential_duplicate,
            description="Re-attest the same credential (teaches tecDUPLICATE)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="credential_type", default="over21",
                             description="Credential tag (must match the first)"),
            ],
        ),
        ActionDef(
            name="accept_credential_wrong_party",
            handler=handle_accept_credential_wrong_party,
            description="Issuer tries to accept (teaches only-the-subject-can-accept)",
            wallet_required=True,
        ),
        ActionDef(
            name="accept_credential",
            handler=handle_accept_credential,
            description="Subject accepts the credential — makes it valid, reserve moves",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_credential",
            handler=handle_verify_credential,
            description="Verify the subject holds a VALID (accepted) credential on-ledger",
        ),
        ActionDef(
            name="delete_credential",
            handler=handle_delete_credential,
            description="Delete the credential, reclaiming reserve (CredentialDelete / revoke)",
            wallet_required=True,
        ),
        # ── Permissioned Domains & Gated DEX (FC-004, XLS-80 / XLS-81) ──
        ActionDef(
            name="create_permissioned_domain",
            handler=handle_create_permissioned_domain,
            description="Owner creates a Permissioned Domain accepting the credential (XLS-80)",
            wallet_required=True,
        ),
        ActionDef(
            name="create_permissioned_offer",
            handler=handle_create_permissioned_offer,
            description="Credentialed account places a permissioned offer (DomainID) — succeeds",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="pays_value", default="50"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="gets_value", default="10"),
                PayloadField(name="hybrid", type="bool", default="false",
                             description="tfHybrid — also match the open DEX"),
            ],
        ),
        ActionDef(
            name="create_uncredentialed_wallet",
            handler=handle_create_uncredentialed_wallet,
            description="Create + fund an outsider wallet that holds no accepted credential",
        ),
        ActionDef(
            name="create_permissioned_offer_uncredentialed",
            handler=handle_create_permissioned_offer_uncredentialed,
            description="Un-credentialed account's permissioned offer is rejected (gate)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="pays_currency", default="LAB"),
                PayloadField(name="pays_value", default="50"),
                PayloadField(name="gets_currency", default="XRP"),
                PayloadField(name="gets_value", default="10"),
            ],
        ),
        ActionDef(
            name="modify_domain_drop_credential",
            handler=handle_modify_domain_drop_credential,
            description="Full-replace modify that drops the credential (teaches silent revocation)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="replacement_type", default="region-XX",
                             description="Decoy credential type that replaces the accepted set"),
            ],
        ),
        ActionDef(
            name="modify_domain_nonowner",
            handler=handle_modify_domain_nonowner,
            description="Non-owner tries to modify the domain (teaches owner-only)",
            wallet_required=True,
        ),
        ActionDef(
            name="delete_permissioned_domain",
            handler=handle_delete_permissioned_domain,
            description="Owner deletes the domain, freeing reserve (compensator, XLS-80)",
            wallet_required=True,
        ),
        ActionDef(
            name="verify_domain",
            handler=handle_verify_domain,
            description="Verify the Permissioned Domain exists and accepts the credential",
        ),
        ActionDef(
            name="verify_permissioned_offer",
            handler=handle_verify_permissioned_offer,
            description="Verify the credentialed account's permissioned offer is resting",
        ),
        # ── Deposit Gate: DepositAuth + DepositPreauth (identity track, XLS-70 ext.) ──
        ActionDef(
            name="enable_deposit_auth",
            handler=handle_enable_deposit_auth,
            description=(
                "Enable asfDepositAuth on the treasury (AccountSet) — "
                "unsolicited deposits now bounce tecNO_PERMISSION"
            ),
            wallet_required=True,
        ),
        ActionDef(
            name="create_sender_wallet",
            handler=handle_create_sender_wallet,
            description="Create + fund a random sender wallet with no preauthorization yet",
        ),
        ActionDef(
            name="send_sender_payment_expect_blocked",
            handler=handle_send_sender_payment_expect_blocked,
            description="Non-preauthorized sender's Payment is rejected (teaches tecNO_PERMISSION)",
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
            ],
        ),
        ActionDef(
            name="preauthorize_self_expect_fail",
            handler=handle_preauthorize_self_expect_fail,
            description="Treasury tries to preauthorize itself (teaches temCANNOT_PREAUTH_SELF)",
            wallet_required=True,
        ),
        ActionDef(
            name="authorize_sender_address",
            handler=handle_authorize_sender_address,
            description="Preauthorize the sender BY ADDRESS (DepositPreauth Authorize)",
            wallet_required=True,
        ),
        ActionDef(
            name="authorize_sender_address_duplicate",
            handler=handle_authorize_sender_address_duplicate,
            description="Re-preauthorize the same address (teaches tecDUPLICATE)",
            wallet_required=True,
        ),
        ActionDef(
            name="send_sender_payment",
            handler=handle_send_sender_payment,
            description="The address-preauthorized sender's Payment lands",
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
            ],
        ),
        ActionDef(
            name="authorize_kyc_credential",
            handler=handle_authorize_kyc_credential,
            description="Preauthorize BY CREDENTIAL (DepositPreauth AuthorizeCredentials)",
            wallet_required=True,
        ),
        ActionDef(
            name="send_kyc_payment",
            handler=handle_send_kyc_payment,
            description="KYC'd player attaches CredentialIDs and pays — succeeds",
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
            ],
        ),
        ActionDef(
            name="send_outsider_payment_expect_blocked",
            handler=handle_send_outsider_payment_expect_blocked,
            description=(
                "Non-credentialed, non-preauthorized outsider's Payment stays "
                "blocked (tecNO_PERMISSION)"
            ),
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
            ],
        ),
        ActionDef(
            name="unauthorize_sender_address",
            handler=handle_unauthorize_sender_address,
            description="Revoke the sender's address preauthorization (compensator)",
            wallet_required=True,
        ),
        ActionDef(
            name="unauthorize_sender_address_duplicate",
            handler=handle_unauthorize_sender_address_duplicate,
            description="Revoke the same preauthorization again (teaches tecNO_ENTRY)",
            wallet_required=True,
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
                # F-feb389a6 (same class): the handler _require()s currency,
                # so advertising default="LAB" contradicted the contract.
                PayloadField(name="currency",
                             description="Currency code (required, e.g. LAB)"),
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
                # F-feb389a6: the handler REQUIRES a_value/b_value via
                # _require (F-BACKEND-B-001) and the runner discards schema
                # defaults, so the previously-advertised default="10" was a
                # lie — a module relying on it failed INPUT_REQUIRED_FIELD.
                PayloadField(name="a_value",
                             description="Amount of asset A (required)"),
                PayloadField(name="b_currency"),
                PayloadField(name="b_value",
                             description="Amount of asset B (required)"),
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
        # ── game-economy control: token freeze (tokens track) ──
        ActionDef(
            name="set_freeze",
            handler=handle_set_freeze,
            description="Issuer freezes/unfreezes a holder's trust line (TrustSet tfSetFreeze)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="GLD"),
                PayloadField(name="freeze", default="true",
                             description="true to freeze, false to unfreeze"),
            ],
        ),
        ActionDef(
            name="set_global_freeze",
            handler=handle_set_global_freeze,
            description="Issuer enables/clears Global Freeze (AccountSet asfGlobalFreeze)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="enable", default="true",
                             description="true to enable, false to clear"),
            ],
        ),
        ActionDef(
            name="verify_freeze",
            handler=handle_verify_freeze,
            description="Verify on-ledger freeze state matches expected Individual/Global flags",
            payload_fields=[
                PayloadField(name="currency", default="GLD"),
                PayloadField(name="expect_individual",
                             description="Expected individual-freeze state (true|false)"),
                PayloadField(name="expect_global",
                             description="Expected global-freeze state (true|false)"),
            ],
        ),
        # ── game-economy control: MPT distribution (tokens track) ──
        ActionDef(
            name="mpt_authorize",
            handler=handle_mpt_authorize,
            description="Holder opts in to hold the MPT issuance (MPTokenAuthorize)",
            wallet_required=True,
        ),
        ActionDef(
            name="mpt_payment",
            handler=handle_mpt_payment,
            description="Issuer pays an MPT amount to the holder (Payment with MPT Amount)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="100", description="MPT amount to send"),
            ],
        ),
        ActionDef(
            name="verify_mpt_balance",
            handler=handle_verify_mpt_balance,
            description="Verify the holder's MPT balance (optionally equals an expected amount)",
            payload_fields=[
                PayloadField(name="expected", description="Expected MPT balance"),
            ],
        ),
        # ── micropayments: payment channels (payments track) ──
        ActionDef(
            name="create_channel_receiver",
            handler=handle_create_channel_receiver,
            description="Create + fund the receiver (merchant) wallet for a payment channel",
        ),
        ActionDef(
            name="open_channel",
            handler=handle_open_channel,
            description="Open an XRP payment channel to the receiver (PaymentChannelCreate)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP to lock in the channel"),
                PayloadField(name="settle_delay", default="86400"),
            ],
        ),
        ActionDef(
            name="fund_channel",
            handler=handle_fund_channel,
            description="Add more XRP to an open channel (PaymentChannelFund)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="5", description="XRP to add"),
            ],
        ),
        ActionDef(
            name="sign_claim",
            handler=handle_sign_claim,
            description="Sign an OFF-LEDGER cumulative channel claim (no tx, no fee)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="3", description="Cumulative XRP claimed"),
            ],
        ),
        ActionDef(
            name="verify_claim_signature",
            handler=handle_verify_claim_signature,
            description="Receiver verifies a signed off-ledger claim against the channel key",
        ),
        ActionDef(
            name="redeem_claim",
            handler=handle_redeem_claim,
            description="Receiver redeems a signed claim on-ledger (PaymentChannelClaim)",
            wallet_required=True,
            payload_fields=[
                PayloadField(name="close", default="false",
                             description="Also close the channel (true|false)"),
            ],
        ),
        ActionDef(
            name="verify_channel",
            handler=handle_verify_channel,
            description="Verify a channel's deposited / claimed amounts on-ledger",
            payload_fields=[
                PayloadField(name="expect_amount", description="Expected deposited XRP"),
                PayloadField(name="expect_balance", description="Expected claimed XRP"),
            ],
        ),
        # ── partial-payment exploit / delivered_amount (payments track) ──
        ActionDef(
            name="send_partial_payment",
            handler=handle_send_partial_payment,
            description=(
                "Issuer sends an issued-currency Payment WITH tfPartialPayment "
                "that under-delivers (sets up the delivered_amount exploit)"
            ),
            wallet_required=True,
            payload_fields=[
                PayloadField(name="currency", default="LAB",
                             description="Issued currency to send"),
                PayloadField(name="amount", default="100",
                             description="Amount field / DeliverMax — the requested CAP"),
                PayloadField(name="deliver_min", default="10",
                             description="DeliverMin — the floor actually delivered"),
                PayloadField(name="send_max", default="10",
                             description="SendMax — caps source spend, forcing the reduction"),
            ],
        ),
        ActionDef(
            name="verify_delivered_amount",
            handler=handle_verify_delivered_amount,
            description=(
                "Read delivered_amount off the validated tx and contrast it with "
                "the Amount field — proves the partial-payment exploit"
            ),
        ),
        # ── custodial player crediting: destination tags (payments track) ──
        ActionDef(
            name="enable_require_dest",
            handler=handle_enable_require_dest,
            description=(
                "Enable asfRequireDest on the pooled treasury (AccountSet) — "
                "untagged deposits bounce tecDST_TAG_NEEDED"
            ),
            wallet_required=True,
        ),
        ActionDef(
            name="create_player_wallet",
            handler=handle_create_player_wallet,
            description="Create + fund the player (depositor) wallet",
        ),
        ActionDef(
            name="assign_player_tag",
            handler=handle_assign_player_tag,
            description=(
                "Assign the player a deposit tag in the OFF-LEDGER backend "
                "registry (the load-bearing tag -> player map)"
            ),
            payload_fields=[
                PayloadField(name="tag", type="int", default="1001",
                             description="32-bit DestinationTag assigned to the player"),
                PayloadField(name="player", default="arya",
                             description="Player id the tag routes to"),
            ],
        ),
        ActionDef(
            name="send_tagged_deposit",
            handler=handle_send_tagged_deposit,
            description=(
                "Player deposits XRP into the pool WITH a DestinationTag "
                "(and optional SourceTag for refund routing)"
            ),
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="25", description="XRP amount"),
                PayloadField(name="tag", type="int",
                             description="DestinationTag (defaults to the assigned player tag)"),
                PayloadField(name="source_tag", type="int",
                             description="Optional SourceTag — the sender's return/bounce hint"),
            ],
        ),
        ActionDef(
            name="send_untagged_deposit_expect_fail",
            handler=handle_send_untagged_deposit_expect_fail,
            description=(
                "Player sends an UNTAGGED deposit to the RequireDest pool "
                "(expects tecDST_TAG_NEEDED)"
            ),
            wallet_required=True,
            payload_fields=[
                PayloadField(name="amount", default="10", description="XRP amount"),
            ],
        ),
        ActionDef(
            name="credit_player_deposit",
            handler=handle_credit_player_deposit,
            description=(
                "Attribute the deposit via its DestinationTag against the "
                "registry and credit delivered_amount (never Amount)"
            ),
            payload_fields=[
                PayloadField(name="expected", description="Expected credited amount in XRP"),
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
