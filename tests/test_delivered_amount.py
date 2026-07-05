"""Tests for the partial-payment exploit / delivered_amount lesson (FC-003).

Proves:
  (a) the dry-run partial payment delivers LESS than the Amount field and
      exposes delivered_amount on the fetch_tx read-back,
  (b) verify_delivered_amount records the correct verdict (exploit demonstrated,
      and the honest pass/fail through the handler's _record_verification), and
  (c) the delivered_amount_101 module lints clean (its action markers resolve).

The mainnet-refusal coverage for the new submit_partial_payment signing method
is enforced by tests/test_network_safety.py (the _MAINNET_REFUSAL_CALLS row +
the reflection completeness gate) — not duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.partial_payment import (
    send_partial_payment,
    verify_delivered_amount,
)
from xrpl_lab.actions.trust_line import set_trust_line
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport

_ISSUER = "rISSUER00000000000000000000"


async def _setup_trust_line(t: DryRunTransport, currency: str = "LAB") -> None:
    """Give the dry-run holder a trust line for ``currency`` from the issuer."""
    res = await set_trust_line(t, "sHOLDER", _ISSUER, currency, "1000")
    assert res.success


# ── (a) dry-run partial payment under-delivers + exposes delivered_amount ──


@pytest.mark.asyncio
async def test_partial_payment_delivers_less_than_amount():
    t = DryRunTransport()
    await _setup_trust_line(t)

    res = await send_partial_payment(
        t, "sISSUER", _DRY_RUN_WALLET_ADDRESS, "LAB", _ISSUER,
        amount="100", deliver_min="10", send_max="10",
    )
    assert res.success
    assert res.result_code == "tesSUCCESS"
    assert res.txid

    tx = await t.fetch_tx(res.txid)
    # The Amount field claims the full requested cap...
    assert tx.amount.startswith("100/LAB/")
    # ...but delivered_amount is the reduced figure that actually moved.
    assert tx.delivered_amount.startswith("10/LAB/")
    assert tx.result_code == "tesSUCCESS"
    assert tx.validated is True

    # And the on-ledger balance moved by delivered_amount (10), NOT Amount (100).
    lines = await t.get_trust_lines(_DRY_RUN_WALLET_ADDRESS)
    lab = next(tl for tl in lines if tl.currency == "LAB")
    assert lab.balance == "10"


@pytest.mark.asyncio
async def test_xrp_to_xrp_partial_payment_is_forbidden():
    # XRP→XRP partial payments are rejected on-ledger (temBAD_SEND_XRP_PARTIAL);
    # the dry-run must reject them the same way so the lesson uses an issued
    # currency, per the KB fact.
    t = DryRunTransport()
    res = await send_partial_payment(
        t, "sISSUER", "rDEST", "XRP", "", "10", "1", "10",
    )
    assert not res.success
    assert res.result_code == "temBAD_SEND_XRP_PARTIAL"


@pytest.mark.asyncio
async def test_partial_payment_without_trust_line_fails():
    t = DryRunTransport()  # no trust line set
    res = await send_partial_payment(
        t, "sISSUER", _DRY_RUN_WALLET_ADDRESS, "LAB", _ISSUER, "100", "10", "10",
    )
    assert not res.success
    assert res.result_code == "tecPATH_DRY"


# ── (b) verify_delivered_amount records the correct verdict ────────────────


@pytest.mark.asyncio
async def test_verify_delivered_amount_demonstrates_exploit():
    t = DryRunTransport()
    await _setup_trust_line(t)
    sent = await send_partial_payment(
        t, "sISSUER", _DRY_RUN_WALLET_ADDRESS, "LAB", _ISSUER, "100", "10", "10",
    )

    result = await verify_delivered_amount(t, sent.txid)
    assert result.passed
    assert result.exploit_demonstrated is True
    assert result.amount_field.startswith("100/LAB/")
    assert result.delivered_amount.startswith("10/LAB/")


@pytest.mark.asyncio
async def test_verify_delivered_amount_expected_match():
    t = DryRunTransport()
    await _setup_trust_line(t)
    sent = await send_partial_payment(
        t, "sISSUER", _DRY_RUN_WALLET_ADDRESS, "LAB", _ISSUER, "100", "10", "10",
    )
    # expected_delivered matches → pass
    ok = await verify_delivered_amount(t, sent.txid, expected_delivered="10")
    assert ok.passed
    # expected_delivered wrong → honest failure
    bad = await verify_delivered_amount(t, sent.txid, expected_delivered="100")
    assert not bad.passed
    assert any("mismatch" in f for f in bad.failures)


@pytest.mark.asyncio
async def test_handle_verify_delivered_amount_records_verification():
    """The verify handler must call _record_verification on BOTH the success
    path and the missing-prerequisite path (honest-pack contract)."""
    from rich.console import Console

    from xrpl_lab.handlers import (
        handle_send_partial_payment,
        handle_verify_delivered_amount,
    )
    from xrpl_lab.modules import ModuleStep
    from xrpl_lab.runtime import _SecretValue
    from xrpl_lab.state import LabState

    console = Console(quiet=True)
    t = DryRunTransport()
    await _setup_trust_line(t)

    state = LabState(network="dry-run")
    state.wallet_address = _DRY_RUN_WALLET_ADDRESS

    # --- missing-prerequisite path: no partial_payment_txid in context ---
    ctx_missing: dict = {"module_id": "delivered_amount_101"}
    step = ModuleStep(text="", action="verify_delivered_amount", action_args={})
    ctx_missing = await handle_verify_delivered_amount(
        step, state, t, "", ctx_missing, console
    )
    recs = ctx_missing.get("verifications", [])
    assert recs and recs[-1]["action"] == "verify_delivered_amount"
    assert recs[-1]["passed"] is False  # honest FAILED, not an invisible skip

    # --- success path: send the partial payment, then verify ---
    ctx: dict = {
        "module_id": "delivered_amount_101",
        "issuer_seed": _SecretValue("sISSUER"),
        "issuer_address": _ISSUER,
    }
    send_step = ModuleStep(
        text="", action="send_partial_payment",
        action_args={"currency": "LAB", "amount": "100",
                     "deliver_min": "10", "send_max": "10"},
    )
    ctx = await handle_send_partial_payment(send_step, state, t, "", ctx, console)
    assert ctx.get("partial_payment_txid")

    ctx = await handle_verify_delivered_amount(step, state, t, "", ctx, console)
    recs = ctx.get("verifications", [])
    assert recs and recs[-1]["action"] == "verify_delivered_amount"
    assert recs[-1]["passed"] is True
    assert recs[-1]["failures"] == []


# ── (c) the module lints clean (action markers resolve) ────────────────────


def test_delivered_amount_module_lints_clean():
    issues = lint_module_file(
        Path(__file__).parent.parent / "modules" / "delivered_amount_101.md"
    )
    errors = [i for i in issues if i.level == "error"]
    assert not errors, f"delivered_amount_101 lint errors: {errors}"
