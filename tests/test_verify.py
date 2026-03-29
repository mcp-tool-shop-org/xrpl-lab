"""Tests for transaction verification action."""

from __future__ import annotations

import pytest

from xrpl_lab.actions.verify import verify_tx
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


def _make_tx(
    txid: str = "TXABC",
    result_code: str = "tesSUCCESS",
    destination: str = "rDEST123",
    amount: str = "10000000",
    validated: bool = True,
    ledger_index: int = 99999,
) -> TxInfo:
    return TxInfo(
        txid=txid,
        tx_type="Payment",
        account="rSENDER",
        destination=destination,
        amount=amount,
        fee="12",
        result_code=result_code,
        ledger_index=ledger_index,
        validated=validated,
    )


class TestVerifyTxSuccess:
    @pytest.mark.asyncio
    async def test_passes_on_tes_success(self, transport):
        tx = _make_tx(txid="TX001", result_code="tesSUCCESS")
        transport.set_tx_fixtures({"TX001": tx})
        result = await verify_tx(transport, "TX001", expected_success=True)
        assert result.passed is True
        assert result.failures == []

    @pytest.mark.asyncio
    async def test_result_code_check_added(self, transport):
        tx = _make_tx(txid="TX002", result_code="tesSUCCESS")
        transport.set_tx_fixtures({"TX002": tx})
        result = await verify_tx(transport, "TX002", expected_success=True)
        assert any("tesSUCCESS" in c for c in result.checks)


class TestVerifyTxFailure:
    @pytest.mark.asyncio
    async def test_fails_when_expected_success_but_not_tes(self, transport):
        tx = _make_tx(txid="TX003", result_code="tecUNFUNDED_PAYMENT")
        transport.set_tx_fixtures({"TX003": tx})
        result = await verify_tx(transport, "TX003", expected_success=True)
        assert result.passed is False
        assert len(result.failures) >= 1
        assert any("tesSUCCESS" in f for f in result.failures)

    @pytest.mark.asyncio
    async def test_expected_failure_path_passes_when_not_tes(self, transport):
        tx = _make_tx(txid="TX004", result_code="tecUNFUNDED_PAYMENT")
        transport.set_tx_fixtures({"TX004": tx})
        result = await verify_tx(transport, "TX004", expected_success=False)
        assert result.passed is True
        assert any("expected failure" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_expected_failure_fails_when_tes_success(self, transport):
        tx = _make_tx(txid="TX005", result_code="tesSUCCESS")
        transport.set_tx_fixtures({"TX005": tx})
        result = await verify_tx(transport, "TX005", expected_success=False)
        assert result.passed is False
        assert any("tesSUCCESS" in f for f in result.failures)


class TestVerifyTxDestination:
    @pytest.mark.asyncio
    async def test_passes_correct_destination(self, transport):
        tx = _make_tx(txid="TX006", destination="rCORRECT123")
        transport.set_tx_fixtures({"TX006": tx})
        result = await verify_tx(transport, "TX006", expected_destination="rCORRECT123")
        assert result.passed is True
        assert any("rCORRECT123" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_fails_wrong_destination(self, transport):
        tx = _make_tx(txid="TX007", destination="rWRONG999")
        transport.set_tx_fixtures({"TX007": tx})
        result = await verify_tx(transport, "TX007", expected_destination="rEXPECTED123")
        assert result.passed is False
        assert any("Destination mismatch" in f for f in result.failures)


class TestVerifyTxAmount:
    @pytest.mark.asyncio
    async def test_passes_correct_amount(self, transport):
        tx = _make_tx(txid="TX008", amount="5000000")
        transport.set_tx_fixtures({"TX008": tx})
        result = await verify_tx(transport, "TX008", expected_amount="5000000")
        assert result.passed is True
        assert any("5000000" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_fails_wrong_amount(self, transport):
        tx = _make_tx(txid="TX009", amount="9999999")
        transport.set_tx_fixtures({"TX009": tx})
        result = await verify_tx(transport, "TX009", expected_amount="1000000")
        assert result.passed is False
        assert any("Amount mismatch" in f for f in result.failures)


class TestVerifyTxMetadata:
    @pytest.mark.asyncio
    async def test_fee_always_in_checks(self, transport):
        tx = _make_tx(txid="TX010")
        transport.set_tx_fixtures({"TX010": tx})
        result = await verify_tx(transport, "TX010")
        assert any("Fee" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_ledger_index_in_checks_when_present(self, transport):
        tx = _make_tx(txid="TX011", ledger_index=12345)
        transport.set_tx_fixtures({"TX011": tx})
        result = await verify_tx(transport, "TX011")
        assert any("Ledger" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_validated_in_checks_when_true(self, transport):
        tx = _make_tx(txid="TX012", validated=True)
        transport.set_tx_fixtures({"TX012": tx})
        result = await verify_tx(transport, "TX012")
        assert any("Validated" in c for c in result.checks)

    @pytest.mark.asyncio
    async def test_tx_info_returned(self, transport):
        tx = _make_tx(txid="TX013")
        transport.set_tx_fixtures({"TX013": tx})
        result = await verify_tx(transport, "TX013")
        assert result.tx_info is tx
