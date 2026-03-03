"""Tests for trust line transport and actions."""

import pytest

from xrpl_lab.actions.trust_line import (
    get_trust_lines,
    issue_token,
    set_trust_line,
    verify_trust_line,
)
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestTrustLineTransport:
    @pytest.mark.asyncio
    async def test_submit_trust_set_success(self, transport):
        result = await transport.submit_trust_set(
            wallet_seed="sFAKE",
            issuer="rISSUER123",
            currency="LAB",
            limit="1000",
        )
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid != ""

    @pytest.mark.asyncio
    async def test_submit_trust_set_fail(self, transport):
        transport.set_fail_next()
        result = await transport.submit_trust_set(
            wallet_seed="sFAKE",
            issuer="rISSUER123",
            currency="LAB",
            limit="1000",
        )
        assert result.success is False
        assert result.result_code == "tecNO_DST"

    @pytest.mark.asyncio
    async def test_trust_line_tracked(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        lines = await transport.get_trust_lines("rANY")
        assert len(lines) == 1
        assert lines[0].currency == "LAB"
        assert lines[0].peer == "rISSUER"
        assert lines[0].limit == "1000"
        assert lines[0].balance == "0"

    @pytest.mark.asyncio
    async def test_issued_payment_success(self, transport):
        # Set trust line first
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")

        result = await transport.submit_issued_payment(
            wallet_seed="sISSUER",
            destination="rHOLDER",
            currency="LAB",
            issuer="rISSUER",
            amount="100",
        )
        assert result.success is True
        assert result.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_issued_payment_updates_balance(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        await transport.submit_issued_payment(
            "sISSUER", "rHOLDER", "LAB", "rISSUER", "100"
        )
        lines = await transport.get_trust_lines("rANY")
        assert lines[0].balance == "100"

    @pytest.mark.asyncio
    async def test_issued_payment_fail(self, transport):
        transport.set_fail_next()
        result = await transport.submit_issued_payment(
            "sISSUER", "rHOLDER", "LAB", "rISSUER", "100"
        )
        assert result.success is False
        assert result.result_code == "tecPATH_DRY"

    @pytest.mark.asyncio
    async def test_get_trust_lines_empty(self, transport):
        lines = await transport.get_trust_lines("rANY")
        assert lines == []


class TestTrustLineActions:
    @pytest.mark.asyncio
    async def test_set_trust_line_action(self, transport):
        result = await set_trust_line(transport, "sFAKE", "rISSUER", "LAB", "500")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_issue_token_action(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        result = await issue_token(
            transport, "sISSUER", "rHOLDER", "LAB", "rISSUER", "50"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_trust_lines_action(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "USD", "500")
        lines = await get_trust_lines(transport, "rANY")
        assert len(lines) == 1
        assert lines[0].currency == "USD"

    @pytest.mark.asyncio
    async def test_verify_trust_line_found(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        await transport.submit_issued_payment(
            "sISSUER", "rHOLDER", "LAB", "rISSUER", "100"
        )
        result = await verify_trust_line(transport, "rHOLDER", "LAB")
        assert result.found is True
        assert result.passed is True
        assert result.trust_line is not None
        assert result.trust_line.currency == "LAB"

    @pytest.mark.asyncio
    async def test_verify_trust_line_not_found(self, transport):
        result = await verify_trust_line(transport, "rHOLDER", "NOPE")
        assert result.found is False
        assert result.passed is False
        assert "No trust line found" in result.failures[0]

    @pytest.mark.asyncio
    async def test_verify_trust_line_with_issuer(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        result = await verify_trust_line(
            transport, "rHOLDER", "LAB", expected_issuer="rISSUER"
        )
        assert result.found is True
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_trust_line_wrong_issuer(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        result = await verify_trust_line(
            transport, "rHOLDER", "LAB", expected_issuer="rOTHER"
        )
        assert result.found is False  # No match with wrong issuer

    @pytest.mark.asyncio
    async def test_multiple_trust_lines(self, transport):
        await transport.submit_trust_set("sFAKE", "rISSUER1", "LAB", "1000")
        await transport.submit_trust_set("sFAKE", "rISSUER2", "USD", "500")
        lines = await transport.get_trust_lines("rANY")
        assert len(lines) == 2
        currencies = {tl.currency for tl in lines}
        assert currencies == {"LAB", "USD"}
