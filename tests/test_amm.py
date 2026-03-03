"""Tests for AMM liquidity — create, deposit, withdraw, verify, lifecycle."""

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
