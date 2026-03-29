"""Tests for send_payment and fund_wallet actions."""

from __future__ import annotations

import pytest

from xrpl_lab.actions.fund import fund_wallet
from xrpl_lab.actions.send import send_payment
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestSendPayment:
    @pytest.mark.asyncio
    async def test_returns_submit_result(self, transport):
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="1000000",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_success_flag(self, transport):
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="1000000",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_returns_txid(self, transport):
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="1000000",
        )
        assert result.txid
        assert len(result.txid) > 0

    @pytest.mark.asyncio
    async def test_result_code_tes_success(self, transport):
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="1000000",
        )
        assert result.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_with_memo(self, transport):
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="500000",
            memo="XRPLLAB|test-memo",
        )
        assert result.success is True
        assert result.txid

    @pytest.mark.asyncio
    async def test_unique_txids(self, transport):
        r1 = await send_payment(transport, "sEd123", "rDEST1", "100")
        r2 = await send_payment(transport, "sEd123", "rDEST2", "200")
        assert r1.txid != r2.txid

    @pytest.mark.asyncio
    async def test_failure_when_fail_next_set(self, transport):
        transport.set_fail_next(True)
        result = await send_payment(
            transport,
            wallet_seed="sEd123",
            destination="rDEST999",
            amount="1000000",
        )
        assert result.success is False
        assert result.result_code == "tecUNFUNDED_PAYMENT"


class TestFundWallet:
    @pytest.mark.asyncio
    async def test_returns_fund_result(self, transport):
        result = await fund_wallet(transport, "rTEST123")
        assert result is not None

    @pytest.mark.asyncio
    async def test_success_flag(self, transport):
        result = await fund_wallet(transport, "rTEST123")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_address_in_result(self, transport):
        result = await fund_wallet(transport, "rTEST123")
        assert result.address == "rTEST123"

    @pytest.mark.asyncio
    async def test_balance_in_result(self, transport):
        result = await fund_wallet(transport, "rTEST123")
        assert result.balance
        assert "1000" in result.balance

    @pytest.mark.asyncio
    async def test_message_in_result(self, transport):
        result = await fund_wallet(transport, "rTEST123")
        assert result.message
        assert len(result.message) > 0
