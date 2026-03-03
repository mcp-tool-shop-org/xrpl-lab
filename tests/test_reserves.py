"""Tests for reserves transport, actions, and snapshot comparisons."""

import pytest

from xrpl_lab.actions.reserves import (
    _drops_to_xrp,
    compare_snapshots,
    snapshot_account,
)
from xrpl_lab.transport.base import AccountSnapshot
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestAccountInfoTransport:
    @pytest.mark.asyncio
    async def test_get_account_info_funded(self, transport):
        await transport.fund_from_faucet("rADDRESS")
        snap = await transport.get_account_info("rADDRESS")
        assert snap.address == "rADDRESS"
        assert int(snap.balance_drops) > 0
        assert snap.owner_count == 0

    @pytest.mark.asyncio
    async def test_get_account_info_unfunded(self, transport):
        snap = await transport.get_account_info("rUNKNOWN")
        assert snap.balance_drops == "0"
        assert snap.owner_count == 0

    @pytest.mark.asyncio
    async def test_owner_count_increases_on_trust_set(self, transport):
        snap_before = await transport.get_account_info("rANY")
        assert snap_before.owner_count == 0

        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        snap_after = await transport.get_account_info("rANY")
        assert snap_after.owner_count == 1

    @pytest.mark.asyncio
    async def test_owner_count_increases_on_offer_create(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        snap = await transport.get_account_info("rANY")
        assert snap.owner_count == 1

    @pytest.mark.asyncio
    async def test_owner_count_decreases_on_offer_cancel(self, transport):
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        assert (await transport.get_account_info("rANY")).owner_count == 1

        await transport.submit_offer_cancel("sFAKE", 100)
        assert (await transport.get_account_info("rANY")).owner_count == 0

    @pytest.mark.asyncio
    async def test_owner_count_multiple_objects(self, transport):
        # Create trust line + offer = 2 objects
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        await transport.submit_offer_create(
            "sFAKE", "LAB", "50", "rISSUER",
            "XRP", "10", "",
        )
        snap = await transport.get_account_info("rANY")
        assert snap.owner_count == 2

        # Cancel offer = back to 1
        await transport.submit_offer_cancel("sFAKE", 100)
        snap = await transport.get_account_info("rANY")
        assert snap.owner_count == 1

    @pytest.mark.asyncio
    async def test_owner_count_never_negative(self, transport):
        """Cancelling non-existent offer shouldn't go negative."""
        await transport.submit_offer_cancel("sFAKE", 999)
        snap = await transport.get_account_info("rANY")
        assert snap.owner_count == 0


class TestSnapshotAction:
    @pytest.mark.asyncio
    async def test_snapshot_account_returns_snapshot(self, transport):
        await transport.fund_from_faucet("rADDR")
        snap = await snapshot_account(transport, "rADDR")
        assert isinstance(snap, AccountSnapshot)
        assert snap.address == "rADDR"


class TestCompareSnapshots:
    def test_no_change(self):
        before = AccountSnapshot("rADDR", "1000000000", 0, 42)
        after = AccountSnapshot("rADDR", "1000000000", 0, 43)
        result = compare_snapshots(before, after)
        assert result.owner_count_delta == 0
        assert result.balance_delta_drops == 0
        assert not result.owner_count_changed
        assert "unchanged" in result.checks[0].lower()

    def test_owner_count_increased(self):
        before = AccountSnapshot("rADDR", "1000000000", 0, 42)
        after = AccountSnapshot("rADDR", "999999988", 1, 43)
        result = compare_snapshots(before, after, label="trust line")
        assert result.owner_count_delta == 1
        assert result.owner_count_changed
        assert "increased" in result.checks[1].lower()
        assert "trust line" in result.explanation

    def test_owner_count_decreased(self):
        before = AccountSnapshot("rADDR", "999999988", 2, 42)
        after = AccountSnapshot("rADDR", "999999976", 1, 43)
        result = compare_snapshots(before, after, label="cancel")
        assert result.owner_count_delta == -1
        assert "decreased" in result.checks[1].lower()
        assert "releases" in result.explanation

    def test_balance_decreased(self):
        before = AccountSnapshot("rADDR", "1000000000", 0, 42)
        after = AccountSnapshot("rADDR", "999999988", 0, 43)
        result = compare_snapshots(before, after)
        assert result.balance_delta_drops == -12
        assert "decreased" in result.checks[0].lower()

    def test_multiple_changes(self):
        before = AccountSnapshot("rADDR", "1000000000", 0, 42)
        after = AccountSnapshot("rADDR", "999999976", 2, 44)
        result = compare_snapshots(before, after, label="objects")
        assert result.owner_count_delta == 2
        assert result.balance_delta_drops == -24
        assert len(result.checks) == 2


class TestDropsToXrp:
    def test_basic_conversion(self):
        assert _drops_to_xrp("1000000") == "1.000000"

    def test_large_balance(self):
        assert _drops_to_xrp("1000000000") == "1000.000000"

    def test_zero(self):
        assert _drops_to_xrp("0") == "0.000000"

    def test_small_amount(self):
        assert _drops_to_xrp("12") == "0.000012"

    def test_invalid(self):
        assert _drops_to_xrp("invalid") == "0.000000"
