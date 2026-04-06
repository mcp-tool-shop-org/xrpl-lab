"""Tests for DEX transport and actions."""

import pytest

from xrpl_lab.actions.dex import (
    cancel_offer,
    create_offer,
    get_offers,
    verify_offer_absent,
    verify_offer_present,
)
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestDEXTransport:
    @pytest.mark.asyncio
    async def test_submit_offer_create_success(self, transport):
        result = await transport.submit_offer_create(
            wallet_seed="sFAKE",
            taker_pays_currency="LAB",
            taker_pays_value="50",
            taker_pays_issuer="rISSUER123",
            taker_gets_currency="XRP",
            taker_gets_value="10",
            taker_gets_issuer="",
        )
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid != ""

    @pytest.mark.asyncio
    async def test_submit_offer_create_fail(self, transport):
        transport.set_fail_next()
        result = await transport.submit_offer_create(
            wallet_seed="sFAKE",
            taker_pays_currency="LAB",
            taker_pays_value="50",
            taker_pays_issuer="rISSUER",
            taker_gets_currency="XRP",
            taker_gets_value="10",
            taker_gets_issuer="",
        )
        assert result.success is False
        assert result.result_code == "tecUNFUNDED_OFFER"

    @pytest.mark.asyncio
    async def test_offer_tracked(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        # 'rANY' works here because DryRunTransport returns all offers
        # regardless of address (global offer pool, not per-address scoped).
        offers = await transport.get_account_offers("rANY")
        assert len(offers) == 1
        assert offers[0].sequence == 100
        assert "50" in offers[0].taker_pays
        assert "10" in offers[0].taker_gets

    @pytest.mark.asyncio
    async def test_submit_offer_cancel_success(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        result = await transport.submit_offer_cancel("sFAKE", 100)
        assert result.success is True
        assert result.result_code == "tesSUCCESS"

        # Offer should be gone
        offers = await transport.get_account_offers("rANY")
        assert len(offers) == 0

    @pytest.mark.asyncio
    async def test_submit_offer_cancel_fail(self, transport):
        transport.set_fail_next()
        result = await transport.submit_offer_cancel("sFAKE", 999)
        assert result.success is False
        assert result.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_get_account_offers_empty(self, transport):
        offers = await transport.get_account_offers("rANY")
        assert offers == []

    @pytest.mark.asyncio
    async def test_multiple_offers(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        await transport.submit_offer_create(
            "sFAKE", "USD", "100", "rISSUER2",
            "XRP", "20", "",
        )
        offers = await transport.get_account_offers("rANY")
        assert len(offers) == 2
        assert offers[0].sequence == 100
        assert offers[1].sequence == 101

    @pytest.mark.asyncio
    async def test_cancel_specific_offer(self, transport):
        """Cancel one offer, leave the other."""
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        await transport.submit_offer_create(
            "sFAKE", "USD", "100", "rISSUER2",
            "XRP", "20", "",
        )
        await transport.submit_offer_cancel("sFAKE", 100)
        offers = await transport.get_account_offers("rANY")
        assert len(offers) == 1
        assert offers[0].sequence == 101


class TestDEXActions:
    @pytest.mark.asyncio
    async def test_create_offer_action(self, transport):
        result = await create_offer(
            transport, "sFAKE",
            "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_cancel_offer_action(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        result = await cancel_offer(transport, "sFAKE", 100)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_offers_action(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        offers = await get_offers(transport, "rANY")
        assert len(offers) == 1

    @pytest.mark.asyncio
    async def test_verify_offer_present_found(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        result = await verify_offer_present(transport, "rANY", 100)
        assert result.found is True
        assert result.passed is True
        assert result.offer is not None
        assert result.offer.sequence == 100

    @pytest.mark.asyncio
    async def test_verify_offer_present_not_found(self, transport):
        result = await verify_offer_present(transport, "rANY", 999)
        assert result.found is False
        assert result.passed is False
        assert "not found" in result.failures[0]

    @pytest.mark.asyncio
    async def test_verify_offer_absent_success(self, transport):
        """Offer doesn't exist — absent verification passes."""
        result = await verify_offer_absent(transport, "rANY", 999)
        assert result.found is False
        assert result.passed is True
        assert "confirmed absent" in result.checks[0]

    @pytest.mark.asyncio
    async def test_verify_offer_absent_fails(self, transport):
        """Offer exists — absent verification fails."""
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        result = await verify_offer_absent(transport, "rANY", 100)
        assert result.found is True
        assert result.passed is False
        assert "still active" in result.failures[0]


class TestDEXLifecycle:
    """Full create → verify → cancel → verify lifecycle."""

    @pytest.mark.asyncio
    async def test_full_offer_lifecycle(self, transport):
        # 1. Create offer
        create_result = await create_offer(
            transport, "sFAKE",
            "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        assert create_result.success is True

        # 2. Verify present
        offers = await get_offers(transport, "rANY")
        seq = offers[0].sequence
        present = await verify_offer_present(transport, "rANY", seq)
        assert present.found is True

        # 3. Cancel
        cancel_result = await cancel_offer(transport, "sFAKE", seq)
        assert cancel_result.success is True

        # 4. Verify absent
        absent = await verify_offer_absent(transport, "rANY", seq)
        assert absent.passed is True
        assert absent.found is False
