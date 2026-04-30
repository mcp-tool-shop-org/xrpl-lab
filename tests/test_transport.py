"""Tests for dry-run transport."""

import pytest

from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestDryRunTransport:
    @pytest.mark.asyncio
    async def test_network_info(self, transport):
        info = await transport.get_network_info()
        assert info.connected is True
        assert info.network == "dry-run"
        assert info.ledger_index is not None

    @pytest.mark.asyncio
    async def test_fund(self, transport):
        result = await transport.fund_from_faucet("rTEST123")
        assert result.success is True
        assert result.address == "rTEST123"
        assert "1000" in result.balance

    @pytest.mark.asyncio
    async def test_submit_success(self, transport):
        result = await transport.submit_payment(
            wallet_seed="sFAKESEED",
            destination="rDEST",
            amount="10",
            memo="test",
        )
        assert result.success is True
        assert result.txid != ""
        assert result.result_code == "tesSUCCESS"
        assert result.explorer_url != ""

    @pytest.mark.asyncio
    async def test_submit_fail(self, transport):
        """Exercise the REAL failure path inside DryRunTransport.submit_payment.

        F-TESTS-004: previously this test toggled ``set_fail_next()`` — a
        back-door switch — so the production failure code (``Decimal(amount)``
        validation) was never exercised. We now feed a non-numeric amount,
        which goes through the actual ``except`` branch in submit_payment and
        returns ``temBAD_AMOUNT``.
        """
        result = await transport.submit_payment(
            wallet_seed="sFAKESEED",
            destination="rDEST",
            amount="not_a_number",
        )
        assert result.success is False
        assert result.result_code == "temBAD_AMOUNT"
        assert result.txid == ""
        assert "not_a_number" in result.error
        assert "Invalid amount" in result.error

    @pytest.mark.asyncio
    async def test_fail_resets(self, transport):
        transport.set_fail_next()
        await transport.submit_payment("s", "r", "1")
        # Second submit should succeed
        result = await transport.submit_payment("s", "r", "1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_fetch_tx(self, transport):
        result = await transport.submit_payment("s", "r", "1")
        tx = await transport.fetch_tx(result.txid)
        assert tx.txid == result.txid
        assert tx.tx_type == "Payment"
        assert tx.validated is True

    @pytest.mark.asyncio
    async def test_balance(self, transport):
        assert await transport.get_balance("rUNFUNDED") == "0"
        await transport.fund_from_faucet("rFUNDED")
        assert await transport.get_balance("rFUNDED") == "1000.000000"

    @pytest.mark.asyncio
    async def test_unique_txids(self, transport):
        r1 = await transport.submit_payment("s", "r", "1")
        r2 = await transport.submit_payment("s", "r", "1")
        assert r1.txid != r2.txid
