"""Tests for AMM liquidity — create, deposit, withdraw, verify, lifecycle."""

from decimal import Decimal

import pytest

from xrpl_lab.actions.amm import (
    amm_deposit,
    amm_withdraw,
    ensure_amm_pair,
    verify_lp_received,
    verify_withdrawal,
)
from xrpl_lab.actions.reserves import compare_snapshots, snapshot_account
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestAmmCreate:
    @pytest.mark.asyncio
    async def test_create_amm(self, transport):
        """AMMCreate succeeds and pool is queryable."""
        result = await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        assert result.success
        assert result.result_code == "tesSUCCESS"

        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is not None
        assert info.pool_a == "100"
        assert info.pool_b == "100"
        assert info.lp_token_currency != ""
        assert info.lp_token_issuer.startswith("rAMM")

    @pytest.mark.asyncio
    async def test_create_duplicate_fails(self, transport):
        """Cannot create two AMMs for the same pair."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        result = await transport.submit_amm_create(
            "sFAKE", "XRP", "50", "", "LAB", "50", "rISSUER",
        )
        assert not result.success
        assert result.result_code == "tecDUPLICATE"

    @pytest.mark.asyncio
    async def test_create_failure_mode(self, transport):
        """Simulated AMM creation failure."""
        transport.set_fail_next()
        result = await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        assert not result.success
        assert result.result_code == "tecAMM_FAILED"

    @pytest.mark.asyncio
    async def test_no_amm_returns_none(self, transport):
        """get_amm_info returns None when no pool exists."""
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is None

    @pytest.mark.asyncio
    async def test_initial_lp_tokens(self, transport):
        """Creator receives initial LP tokens."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is not None

        # Creator should have LP tokens
        lp = await transport.get_lp_token_balance(
            "rDRYRUN1234567890ABCDEFGHIJK",
            info.lp_token_currency,
            info.lp_token_issuer,
        )
        assert float(lp) > 0
        assert lp == info.lp_supply


class TestAmmDeposit:
    @pytest.mark.asyncio
    async def test_deposit_succeeds(self, transport):
        """Deposit into existing pool increases pool balances and mints LP."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info_before = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_before = float(info_before.lp_supply)

        result = await transport.submit_amm_deposit(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER",
        )
        assert result.success

        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert float(info_after.pool_a) == 110
        assert float(info_after.pool_b) == 110
        assert float(info_after.lp_supply) > lp_before

    @pytest.mark.asyncio
    async def test_deposit_no_pool_fails(self, transport):
        """Deposit into non-existent pool fails."""
        result = await transport.submit_amm_deposit(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER",
        )
        assert not result.success
        assert result.result_code == "tecAMM_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_deposit_failure_mode(self, transport):
        """Simulated deposit failure."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        transport.set_fail_next()
        result = await transport.submit_amm_deposit(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER",
        )
        assert not result.success
        assert result.result_code == "tecAMM_BALANCE"


class TestAmmWithdraw:
    @pytest.mark.asyncio
    async def test_withdraw_all(self, transport):
        """Full withdrawal returns all LP tokens."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")

        result = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )
        assert result.success

        # LP balance should be zero
        lp = await transport.get_lp_token_balance(
            "rDRYRUN1234567890ABCDEFGHIJK",
            info.lp_token_currency,
            info.lp_token_issuer,
        )
        assert float(lp) == 0

    @pytest.mark.asyncio
    async def test_withdraw_partial(self, transport):
        """Partial withdrawal leaves remaining LP tokens."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        total_lp = float(info.lp_supply)
        half_lp = str(round(total_lp / 2, 6))

        result = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
            lp_token_value=half_lp,
        )
        assert result.success

        # Should have ~half LP remaining
        lp = await transport.get_lp_token_balance(
            "rDRYRUN1234567890ABCDEFGHIJK",
            info.lp_token_currency,
            info.lp_token_issuer,
        )
        assert float(lp) > 0
        assert float(lp) < total_lp

    @pytest.mark.asyncio
    async def test_withdraw_no_pool_fails(self, transport):
        """Withdraw from non-existent pool fails."""
        result = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )
        assert not result.success
        assert result.result_code == "tecAMM_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_withdraw_insufficient_lp_fails(self, transport):
        """Withdraw more LP than held fails."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        result = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
            lp_token_value="999999",
        )
        assert not result.success
        assert "insufficient" in result.error.lower()

    @pytest.mark.asyncio
    async def test_withdraw_failure_mode(self, transport):
        """Simulated withdrawal failure."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        transport.set_fail_next()
        result = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )
        assert not result.success


class TestAmmActions:
    @pytest.mark.asyncio
    async def test_ensure_amm_pair_creates(self, transport):
        """ensure_amm_pair creates pool when missing."""
        info, result = await ensure_amm_pair(
            transport, "sFAKE",
            "XRP", "100", "",
            "LAB", "100", "rISSUER",
        )
        assert result is not None
        assert result.success
        assert info.lp_token_currency != ""

    @pytest.mark.asyncio
    async def test_ensure_amm_pair_exists(self, transport):
        """ensure_amm_pair returns existing pool without creating."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info, result = await ensure_amm_pair(
            transport, "sFAKE",
            "XRP", "50", "",
            "LAB", "50", "rISSUER",
        )
        assert result is None  # No creation needed
        assert info.pool_a == "100"  # Original pool values

    @pytest.mark.asyncio
    async def test_deposit_action(self, transport):
        """amm_deposit action wraps transport correctly."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        result = await amm_deposit(
            transport, "sFAKE",
            "XRP", "10", "",
            "LAB", "10", "rISSUER",
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_withdraw_action(self, transport):
        """amm_withdraw action wraps transport correctly."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        result = await amm_withdraw(
            transport, "sFAKE",
            "XRP", "",
            "LAB", "rISSUER",
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_verify_lp_received_success(self, transport):
        """verify_lp_received passes when LP tokens exist."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        result = await verify_lp_received(
            transport, "rDRYRUN1234567890ABCDEFGHIJK", info,
        )
        assert result.ok
        assert float(result.lp_balance) > 0

    @pytest.mark.asyncio
    async def test_verify_withdrawal_success(self, transport):
        """verify_withdrawal passes when LP tokens decreased."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_before = info.lp_supply

        await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )

        result = await verify_withdrawal(
            transport, "rDRYRUN1234567890ABCDEFGHIJK",
            info, lp_before=lp_before,
        )
        assert result.ok
        assert any("returned" in c.lower() or "decreased" in c.lower()
                    for c in result.checks)


class TestAmmLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, transport):
        """Full AMM lifecycle: create -> deposit -> verify -> withdraw -> verify."""
        await transport.fund_from_faucet("rHOLDER")

        # Create AMM
        info, create_result = await ensure_amm_pair(
            transport, "sFAKE",
            "XRP", "100", "",
            "LAB", "100", "rISSUER",
        )
        assert create_result.success
        assert info.lp_token_currency != ""

        # Deposit
        deposit_result = await amm_deposit(
            transport, "sFAKE",
            "XRP", "10", "",
            "LAB", "10", "rISSUER",
        )
        assert deposit_result.success

        # Verify LP received
        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_verify = await verify_lp_received(
            transport, "rDRYRUN1234567890ABCDEFGHIJK", info_after,
        )
        assert lp_verify.ok
        lp_before = lp_verify.lp_balance

        # Withdraw all
        withdraw_result = await amm_withdraw(
            transport, "sFAKE",
            "XRP", "",
            "LAB", "rISSUER",
        )
        assert withdraw_result.success

        # Verify withdrawal
        wd_verify = await verify_withdrawal(
            transport, "rDRYRUN1234567890ABCDEFGHIJK",
            info_after, lp_before=lp_before,
        )
        assert wd_verify.ok

    @pytest.mark.asyncio
    async def test_deposit_withdraw_pool_balances(self, transport):
        """Pool balances move correctly through deposit and withdrawal."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )

        # Deposit 10 + 10
        await transport.submit_amm_deposit(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert float(info.pool_a) == 110
        assert float(info.pool_b) == 110

        # Withdraw all
        await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        # Pool should be empty (all LP burned)
        assert float(info.pool_a) == 0 or float(info.pool_a) < 0.01
        assert float(info.pool_b) == 0 or float(info.pool_b) < 0.01

    @pytest.mark.asyncio
    async def test_owner_count_amm(self, transport):
        """AMM creation increments owner count."""
        await transport.fund_from_faucet("rHOLDER")
        snap_before = await snapshot_account(transport, "rHOLDER")

        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )

        snap_after = await snapshot_account(transport, "rHOLDER")
        cmp = compare_snapshots(snap_before, snap_after, label="amm")
        assert cmp.owner_count_delta >= 1

    @pytest.mark.asyncio
    async def test_pair_key_order_independent(self, transport):
        """AMM lookup works regardless of asset order."""
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )

        # Query in opposite order
        info = await transport.get_amm_info("LAB", "rISSUER", "XRP", "")
        assert info is not None
        assert info.lp_token_currency != ""


# ── F-TESTS-006: AMM boundary tests ─────────────────────────────────


class TestAmmBoundaries:
    """Boundary cases — zero liquidity, XRPL max drops, odd-ratio rounding."""

    @pytest.mark.asyncio
    async def test_amm_zero_liquidity_pool_boundary(self, transport):
        """Deposit and withdraw against a zero-liquidity pool must be well-defined.

        Either the operations are rejected with a recognisable ``E_*`` /
        ``tec*`` code, or they accept with documented zero-amount semantics.
        Whatever the production code does TODAY, lock it in so future
        regressions are caught.
        """
        # Create a pool seeded with zero on both sides — this is the degenerate
        # state we want to characterise.
        create = await transport.submit_amm_create(
            "sFAKE", "XRP", "0", "", "LAB", "0", "rISSUER",
        )
        # Creation does succeed in the current dry-run; lock that in so a
        # future change that decides to reject zero-asset creates becomes
        # visible.
        assert create.success is True

        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is not None
        # Zero × zero ⇒ sqrt = 0 ⇒ no LP supply.
        assert Decimal(info.lp_supply) == Decimal("0")
        assert Decimal(info.pool_a) == Decimal("0")
        assert Decimal(info.pool_b) == Decimal("0")

        # Deposit into a zero-liquidity pool: production code's special-case
        # (``ratio = 1`` when ``old_a == 0``) means the pool absorbs the
        # deposit but mints zero LP.  Lock that behaviour in.
        dep = await transport.submit_amm_deposit(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER",
        )
        assert dep.success is True
        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert Decimal(info_after.pool_a) == Decimal("10")
        assert Decimal(info_after.pool_b) == Decimal("10")
        # LP supply is still zero — depositor got nothing for it (this is
        # the documented degenerate-pool semantic; flag for product review
        # via wave-2 if undesired).
        assert Decimal(info_after.lp_supply) == Decimal("0")

        # Withdraw against the zero-LP pool MUST be rejected — there are no
        # LP tokens to burn.
        wd = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER", "1",
        )
        assert wd.success is False
        assert wd.result_code == "tecAMM_BALANCE"

    @pytest.mark.asyncio
    async def test_amm_max_xrp_drops_no_overflow(self, transport):
        """XRPL's hard cap is 100 000 000 000 XRP = 1e17 drops total supply.

        Decimal must handle this without precision loss, integer overflow
        or unhandled exceptions.  We exercise create + deposit + withdraw
        at this scale.
        """
        # 1e11 XRP — XRPL supply cap.  Use a string so no float ever touches it.
        max_xrp = "100000000000"  # 1e11 XRP

        create = await transport.submit_amm_create(
            "sFAKE", "XRP", max_xrp, "", "LAB", max_xrp, "rISSUER",
        )
        assert create.success is True

        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is not None
        # sqrt(1e11 * 1e11) = 1e11
        assert Decimal(info.lp_supply) == Decimal(max_xrp)
        assert Decimal(info.pool_a) == Decimal(max_xrp)
        assert Decimal(info.pool_b) == Decimal(max_xrp)

        # Deposit another 1e11 on each side — pool grows to 2e11 each.
        dep = await transport.submit_amm_deposit(
            "sFAKE", "XRP", max_xrp, "", "LAB", max_xrp, "rISSUER",
        )
        assert dep.success is True

        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert Decimal(info_after.pool_a) == Decimal("200000000000")
        assert Decimal(info_after.pool_b) == Decimal("200000000000")
        # LP supply doubled — 2e11.
        assert Decimal(info_after.lp_supply) == Decimal("200000000000")

        # Withdraw all and confirm clean unwinding.
        wd = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER",
        )
        assert wd.success is True

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason=(
            "reveals production bug: submit_amm_deposit mints LP using only "
            "the asset_a-side ratio (deposit_a / old_a) but accepts the full "
            "asset_b deposit value, so an unbalanced 7:11 deposit can never "
            "round-trip cleanly. See wave-2 Backend finding "
            "F-BACKEND-W2-AMM-DEPOSIT-RATIO."
        ),
        strict=True,
    )
    async def test_amm_odd_ratio_rounding_bias(self, transport):
        """Round-trip with prime-ratio amounts must stay within 1 drop.

        If we deposit at a ratio like 7:11 and immediately withdraw the
        same proportional LP share, the pool should return to (within 1
        drop of) its pre-deposit state.  Persistent rounding bias across
        deposit↔withdraw would surface here.
        """
        # 1 drop = 1e-6 XRP — the smallest unit XRPL recognises.
        one_drop = Decimal("0.000001")

        # Seed an existing pool so the deposit takes the "real" ratio path
        # (not the zero-pool special case).
        await transport.submit_amm_create(
            "sFAKE", "XRP", "1000", "", "LAB", "1000", "rISSUER",
        )

        info_before = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        pool_a_before = Decimal(info_before.pool_a)
        pool_b_before = Decimal(info_before.pool_b)
        lp_before = Decimal(info_before.lp_supply)

        # Deposit at a 7:11 prime ratio — no clean factoring, so any
        # rounding bias compounds.
        dep = await transport.submit_amm_deposit(
            "sFAKE", "XRP", "7", "", "LAB", "11", "rISSUER",
        )
        assert dep.success is True

        info_mid = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_mid = Decimal(info_mid.lp_supply)
        # The LP minted by this deposit is the round-trip subject.
        lp_minted = lp_mid - lp_before
        assert lp_minted > 0

        # Withdraw exactly that LP share — same proportional stake, immediate.
        wd = await transport.submit_amm_withdraw(
            "sFAKE", "XRP", "", "LAB", "rISSUER", str(lp_minted),
        )
        assert wd.success is True

        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        pool_a_after = Decimal(info_after.pool_a)
        pool_b_after = Decimal(info_after.pool_b)
        lp_after = Decimal(info_after.lp_supply)

        # Round-trip must stay within 1 drop on every dimension.
        assert abs(pool_a_after - pool_a_before) <= one_drop, (
            f"pool_a drift: {pool_a_before} -> {pool_a_after}"
        )
        assert abs(pool_b_after - pool_b_before) <= one_drop, (
            f"pool_b drift: {pool_b_before} -> {pool_b_after}"
        )
        assert abs(lp_after - lp_before) <= one_drop, (
            f"lp_supply drift: {lp_before} -> {lp_after}"
        )
