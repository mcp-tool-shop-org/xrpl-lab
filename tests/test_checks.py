"""Tests for Checks — deferred pull-payments (CheckCreate / CheckCash / CheckCancel).

The claimable-reward pattern: the studio writes a Check authorizing a player
to pull up to an amount (SendMax); the player cashes it whenever they choose.
Coverage (all offline, dry-run transport):

  (a) CheckCreate: returns a check_id, moves/locks NOTHING (the funds-NOT-
      locked property — contrast Escrow), increments the WRITER's owner
      count, and never checks the writer's balance at write time.
  (b) CheckCash: exact Amount and flexible DeliverMin happy paths, moves
      funds writer -> destination, frees the writer's reserve, and populates
      delivered_amount on the validated tx. Every tec failure: tecNO_ENTRY
      (missing/already-consumed), tecNO_PERMISSION (wrong casher),
      tecEXPIRED (past Expiration), tecUNFUNDED (exceeds SendMax, and
      writer's live balance too low) — plus the local_error "exactly one of
      amount/deliver_min" rule.
  (c) CheckCancel: writer or destination may cancel a LIVE check; ANY address
      may cancel once expired; credits NOBODY (contrast EscrowCancel, which
      refunds); tecNO_ENTRY / tecNO_PERMISSION failures.
  (d) Actions layer: thin wrappers forward to the transport unchanged.
  (e) delivered_amount reuse: verify_delivered_amount (FC-003) reads a
      CheckCash's delivered_amount unchanged, no Checks-specific verifier.
  (f) Handlers: the full module flow end-to-end, including the
      funds-not-locked assertion via the reused snapshot/reserve-change
      actions.
  (g) The module lints clean and pins its confirmed kb_source + prereq.

The mainnet-refusal coverage for submit_check_create/cash/cancel is enforced
by tests/test_network_safety.py (the _MAINNET_REFUSAL_CALLS rows + the
reflection completeness gate) — not duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.checks import cancel_check, cash_check, create_check
from xrpl_lab.actions.partial_payment import verify_delivered_amount
from xrpl_lab.linter import lint_module_file
from xrpl_lab.modules import parse_module
from xrpl_lab.transport.dry_run import DryRunTransport

_WRITER = "rStudioAAAAAAAAAAAAAAAAAAAAAAAAA"
_PLAYER = "rPlayerBBBBBBBBBBBBBBBBBBBBBBBBB"
_OUTSIDER = "rOutsiderCCCCCCCCCCCCCCCCCCCCCCCC"
_MODULE_PATH = Path(__file__).parent.parent / "modules" / "checks_101.md"


@pytest.fixture
def transport() -> DryRunTransport:
    return DryRunTransport()


async def _fund(t: DryRunTransport, address: str) -> None:
    await t.fund_from_faucet(address)


async def _create(
    t: DryRunTransport,
    send_max: str = "50",
    expiration: int | None = None,
    destination: str = _PLAYER,
) -> str:
    """Fund the writer and write a Check, returning its check_id."""
    await _fund(t, _WRITER)
    r = await t.submit_check_create(
        "sFAKE", destination, send_max, expiration=expiration, wallet_address=_WRITER
    )
    assert r.success, r.error
    return r.check_id


# ── (a) CheckCreate ──────────────────────────────────────────────────────


class TestCheckCreateTransport:
    @pytest.mark.asyncio
    async def test_create_success_returns_check_id(self, transport):
        r = await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", wallet_address=_WRITER
        )
        assert r.success is True
        assert r.result_code == "tesSUCCESS"
        assert r.txid
        assert len(r.check_id) == 64

    @pytest.mark.asyncio
    async def test_create_does_not_debit_balance(self, transport):
        # THE PROPERTY: funds are NOT locked at create time.
        await _fund(transport, _WRITER)
        before = transport._balances[_WRITER]
        await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", wallet_address=_WRITER
        )
        assert transport._balances[_WRITER] == before

    @pytest.mark.asyncio
    async def test_create_increments_writer_owner_count(self, transport):
        assert transport._owner_counts.get(_WRITER, 0) == 0
        await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", wallet_address=_WRITER
        )
        assert transport._owner_counts.get(_WRITER, 0) == 1

    @pytest.mark.asyncio
    async def test_create_succeeds_even_when_writer_cannot_cover_send_max(self, transport):
        # THE CONTRAST: EscrowCreate would reject this outright (tecUNFUNDED)
        # — CheckCreate never checks the writer's balance at write time.
        await _fund(transport, _WRITER)  # 1000 XRP
        r = await transport.submit_check_create(
            "sFAKE", _PLAYER, "5000", wallet_address=_WRITER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_create_fail_next(self, transport):
        transport.set_fail_next()
        r = await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", wallet_address=_WRITER
        )
        assert r.success is False

    @pytest.mark.asyncio
    async def test_create_rejects_bad_amount(self, transport):
        r = await transport.submit_check_create(
            "sFAKE", _PLAYER, "-5", wallet_address=_WRITER
        )
        assert r.success is False
        assert r.result_code == "temBAD_AMOUNT"

    @pytest.mark.asyncio
    async def test_create_rejects_out_of_range_destination_tag(self, transport):
        r = await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", destination_tag=2**32, wallet_address=_WRITER
        )
        assert r.success is False
        assert r.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_create_two_checks_get_distinct_ids(self, transport):
        r1 = await transport.submit_check_create(
            "sFAKE", _PLAYER, "50", wallet_address=_WRITER
        )
        r2 = await transport.submit_check_create(
            "sFAKE", _PLAYER, "20", wallet_address=_WRITER
        )
        assert r1.check_id != r2.check_id


# ── (b) CheckCash ────────────────────────────────────────────────────────


class TestCheckCashTransport:
    @pytest.mark.asyncio
    async def test_cash_exact_amount_success(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is True
        assert r.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_cash_moves_funds_writer_to_destination(self, transport):
        check_id = await _create(transport)
        writer_before = transport._balances[_WRITER]
        await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert transport._balances[_WRITER] == writer_before - 50_000_000
        assert transport._balances.get(_PLAYER, 0) == 50_000_000

    @pytest.mark.asyncio
    async def test_cash_removes_check_and_frees_writer_reserve(self, transport):
        check_id = await _create(transport)
        assert transport._owner_counts.get(_WRITER, 0) == 1
        await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert transport._owner_counts.get(_WRITER, 0) == 0
        assert check_id not in transport._checks

    @pytest.mark.asyncio
    async def test_cash_sets_delivered_amount_on_fetch_tx(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        tx = await transport.fetch_tx(r.txid)
        assert tx.delivered_amount == "50000000"
        assert tx.result_code == "tesSUCCESS"
        assert tx.validated is True

    @pytest.mark.asyncio
    async def test_cash_requires_exactly_one_of_amount_deliver_min(self, transport):
        check_id = await _create(transport)

        neither = await transport.submit_check_cash(
            "sFAKE", check_id, wallet_address=_PLAYER
        )
        assert neither.success is False
        assert neither.result_code == "local_error"

        both = await transport.submit_check_cash(
            "sFAKE", check_id, amount="10", deliver_min="5", wallet_address=_PLAYER
        )
        assert both.success is False
        assert both.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_cash_deliver_min_delivers_full_send_max(self, transport):
        check_id = await _create(transport, send_max="50")
        r = await transport.submit_check_cash(
            "sFAKE", check_id, deliver_min="10", wallet_address=_PLAYER
        )
        assert r.success is True
        assert transport._balances.get(_PLAYER, 0) == 50_000_000

    @pytest.mark.asyncio
    async def test_cash_nonexistent_check_rejected(self, transport):
        r = await transport.submit_check_cash(
            "sFAKE", "F" * 64, amount="10", wallet_address=_PLAYER
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_cash_already_cashed_check_rejected(self, transport):
        check_id = await _create(transport)
        await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        again = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert again.success is False
        assert again.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_cash_wrong_destination_rejected(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_OUTSIDER
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_cash_expired_check_rejected(self, transport):
        check_id = await _create(transport, expiration=500)
        transport._dry_clock = 500  # at Expiration -> expired
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is False
        assert r.result_code == "tecEXPIRED"

    @pytest.mark.asyncio
    async def test_cash_before_expiration_succeeds(self, transport):
        check_id = await _create(transport, expiration=500)
        transport._dry_clock = 499
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_cash_exceeding_send_max_rejected(self, transport):
        check_id = await _create(transport, send_max="50")
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="1000", wallet_address=_PLAYER
        )
        assert r.success is False
        assert r.result_code == "tecUNFUNDED"

    @pytest.mark.asyncio
    async def test_cash_fails_when_writer_balance_drops_below_send_max(self, transport):
        # THE GOTCHA: CheckCreate succeeding is never a guaranteed payout.
        check_id = await _create(transport, send_max="50")
        transport._balances[_WRITER] = 1_000  # far below 50 XRP, after the fact
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is False
        assert r.result_code == "tecUNFUNDED"

    @pytest.mark.asyncio
    async def test_cash_fail_next(self, transport):
        check_id = await _create(transport)
        transport.set_fail_next()
        r = await transport.submit_check_cash(
            "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is False


# ── (c) CheckCancel ──────────────────────────────────────────────────────


class TestCheckCancelTransport:
    @pytest.mark.asyncio
    async def test_writer_can_cancel(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_WRITER
        )
        assert r.success is True
        assert check_id not in transport._checks

    @pytest.mark.asyncio
    async def test_destination_can_cancel(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_PLAYER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_cancel_credits_nobody(self, transport):
        # THE CONTRAST: unlike EscrowCancel, nothing is refunded — nothing
        # was ever taken.
        check_id = await _create(transport)
        writer_before = transport._balances[_WRITER]
        await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_WRITER
        )
        assert transport._balances[_WRITER] == writer_before

    @pytest.mark.asyncio
    async def test_cancel_frees_writer_reserve(self, transport):
        check_id = await _create(transport)
        assert transport._owner_counts.get(_WRITER, 0) == 1
        await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_WRITER
        )
        assert transport._owner_counts.get(_WRITER, 0) == 0

    @pytest.mark.asyncio
    async def test_outsider_cannot_cancel_live_check(self, transport):
        check_id = await _create(transport)
        r = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_OUTSIDER
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_anyone_can_cancel_once_expired(self, transport):
        check_id = await _create(transport, expiration=500)
        transport._dry_clock = 500
        r = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_OUTSIDER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_check_rejected(self, transport):
        r = await transport.submit_check_cancel(
            "sFAKE", "F" * 64, wallet_address=_WRITER
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_check_rejected(self, transport):
        check_id = await _create(transport)
        await transport.submit_check_cancel("sFAKE", check_id, wallet_address=_WRITER)
        again = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_WRITER
        )
        assert again.success is False
        assert again.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_cancel_fail_next(self, transport):
        check_id = await _create(transport)
        transport.set_fail_next()
        r = await transport.submit_check_cancel(
            "sFAKE", check_id, wallet_address=_WRITER
        )
        assert r.success is False


# ── (d) Actions layer — thin wrappers ────────────────────────────────────


class TestCheckActions:
    @pytest.mark.asyncio
    async def test_create_check_action(self, transport):
        await _fund(transport, _WRITER)
        r = await create_check(transport, "sFAKE", _PLAYER, "50", wallet_address=_WRITER)
        assert r.success is True
        assert r.check_id

    @pytest.mark.asyncio
    async def test_cash_check_action(self, transport):
        check_id = await _create(transport)
        r = await cash_check(
            transport, "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_cancel_check_action(self, transport):
        check_id = await _create(transport)
        r = await cancel_check(transport, "sFAKE", check_id, wallet_address=_WRITER)
        assert r.success is True


# ── (e) delivered_amount reuse (FC-003, unchanged) ───────────────────────


class TestDeliveredAmountReuse:
    @pytest.mark.asyncio
    async def test_verify_delivered_amount_reads_check_cash(self, transport):
        check_id = await _create(transport, send_max="50")
        cashed = await cash_check(
            transport, "sFAKE", check_id, amount="50", wallet_address=_PLAYER
        )
        assert cashed.success

        result = await verify_delivered_amount(
            transport, cashed.txid, expected_delivered="50000000"
        )
        assert result.passed
        assert result.delivered_amount == "50000000"


# ── (f) Handlers: the full module flow end-to-end ───────────────────────


class TestHandlersFullFlow:
    @pytest.mark.asyncio
    async def test_full_flow_through_handlers(self):
        from rich.console import Console

        from xrpl_lab.handlers import (
            handle_cancel_check,
            handle_cash_check,
            handle_cash_check_wrong_destination_expect_fail,
            handle_create_check,
            handle_create_outsider_wallet,
            handle_create_recipient_wallet,
            handle_credit_check_cash,
            handle_snapshot_account,
            handle_verify_reserve_change,
        )
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.runtime import _SecretValue
        from xrpl_lab.state import LabState

        console = Console(quiet=True)
        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address=_WRITER)
        ctx: dict = {
            "module_id": "checks_101",
            "wallet_seed": _SecretValue("sFAKE"),
        }
        await t.fund_from_faucet(_WRITER)

        def step(action: str, **args) -> ModuleStep:
            return ModuleStep(text="", action=action, action_args=args)

        seed = "sFAKE"

        # Step 3: create the player wallet.
        ctx = await handle_create_recipient_wallet(
            step("create_recipient_wallet"), state, t, seed, ctx, console
        )
        assert ctx.get("recipient_address")

        # Steps 4-7: funds-not-locked proof, through the REUSED generic actions.
        ctx = await handle_snapshot_account(
            step("snapshot_account", label="before_check"), state, t, seed, ctx, console
        )
        ctx = await handle_create_check(
            step("create_check", amount="50"), state, t, seed, ctx, console
        )
        assert ctx.get("check_id")
        first_check_id = ctx["check_id"]
        ctx = await handle_snapshot_account(
            step("snapshot_account", label="after_check"), state, t, seed, ctx, console
        )
        ctx = await handle_verify_reserve_change(
            step("verify_reserve_change", before="before_check", after="after_check"),
            state, t, seed, ctx, console,
        )
        comparison = ctx["last_reserve_comparison"]
        assert comparison.balance_delta_drops == 0
        assert comparison.owner_count_delta == 1

        # Step 8: the player cashes the Check.
        txids_before = len(ctx.get("txids", []))
        ctx = await handle_cash_check(
            step("cash_check", amount="50"), state, t, seed, ctx, console
        )
        assert len(ctx["txids"]) == txids_before + 1
        assert ctx["check_id"] == ""
        assert first_check_id not in t._checks

        # Step 9: credit from delivered_amount.
        ctx = await handle_credit_check_cash(
            step("credit_check_cash"), state, t, seed, ctx, console
        )
        assert ctx["verifications"][-1]["passed"] is True

        # Step 10: write a second Check.
        ctx = await handle_create_check(
            step("create_check", amount="20"), state, t, seed, ctx, console
        )
        second_check_id = ctx["check_id"]
        assert second_check_id and second_check_id != first_check_id

        # Step 11: the outsider wallet.
        ctx = await handle_create_outsider_wallet(
            step("create_outsider_wallet"), state, t, seed, ctx, console
        )
        assert ctx.get("outsider_address")

        # Step 12: outsider fails to cash it.
        ctx = await handle_cash_check_wrong_destination_expect_fail(
            step("cash_check_wrong_destination_expect_fail", amount="20"),
            state, t, seed, ctx, console,
        )
        assert ctx["failed_txids"][-1]["result_code"] == "tecNO_PERMISSION"
        # The failed attempt must not have consumed the Check.
        assert second_check_id in t._checks

        # Step 13: the studio cancels it — nothing refunded.
        writer_balance_before_cancel = t._balances[_WRITER]
        ctx = await handle_cancel_check(
            step("cancel_check"), state, t, seed, ctx, console
        )
        assert second_check_id not in t._checks
        assert t._balances[_WRITER] == writer_balance_before_cancel
        assert ctx["check_id"] == ""

    @pytest.mark.asyncio
    async def test_cash_check_without_check_id_is_a_guarded_noop(self):
        """No Check in context -> the handler refuses to guess an id."""
        from rich.console import Console

        from xrpl_lab.handlers import handle_cash_check
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        console = Console(quiet=True)
        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address=_WRITER)
        ctx: dict = {"module_id": "checks_101"}
        step = ModuleStep(text="", action="cash_check", action_args={"amount": "50"})
        result_ctx = await handle_cash_check(step, state, t, "sFAKE", ctx, console)
        assert "txids" not in result_ctx


# ── (g) module lints clean + pins its confirmed kb_source ───────────────


class TestChecksModule:
    def test_lints_clean(self):
        issues = lint_module_file(_MODULE_PATH)
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"checks_101 lint errors: {errors}"

    def test_frontmatter_pins_kb_source_and_prereq(self):
        mod = parse_module(_MODULE_PATH.read_text(encoding="utf-8"))
        assert mod.id == "checks_101"
        assert mod.track == "payments"
        # Confirmed against the xrpl-knowledge KB capabilities table — the
        # more specific of two matching rows (kb id 649, "checks-deferred-
        # pull-payment"); its gotchas/tec-code list is the exact source for
        # this module's KB-verified spec.
        assert mod.kb_source == "checks-deferred-pull-payment"
        assert "receipt_literacy" in mod.requires
