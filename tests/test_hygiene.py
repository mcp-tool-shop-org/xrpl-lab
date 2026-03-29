"""Tests for account hygiene — trust line removal, offer cleanup, lifecycle."""

import pytest

from xrpl_lab.actions.reserves import compare_snapshots, snapshot_account
from xrpl_lab.actions.trust_line import (
    remove_trust_line,
    verify_trust_line,
    verify_trust_line_removed,
)
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestTrustLineRemoval:
    @pytest.mark.asyncio
    async def test_remove_empty_trust_line(self, transport):
        """Trust line with balance 0 can be removed (limit -> 0)."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        assert (await transport.get_account_info("rANY")).owner_count == 1

        result = await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")
        assert result.success
        assert (await transport.get_account_info("rANY")).owner_count == 0

    @pytest.mark.asyncio
    async def test_remove_nonzero_balance_fails(self, transport):
        """Trust line with non-zero balance cannot be removed."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        # Issue some tokens so balance > 0
        await transport.submit_issued_payment(
            "sISSUER", "rHOLDER", "HYGIENE", "rISSUER", "50"
        )
        result = await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")
        assert not result.success
        assert result.result_code == "tecNO_PERMISSION"
        assert "balance" in result.error.lower()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_trust_line(self, transport):
        """Removing a trust line that doesn't exist is a no-op success."""
        result = await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")
        assert result.success
        assert (await transport.get_account_info("rANY")).owner_count == 0

    @pytest.mark.asyncio
    async def test_trust_line_gone_after_removal(self, transport):
        """Trust line should not appear in get_trust_lines after removal."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        lines = await transport.get_trust_lines("rANY")
        assert len(lines) == 1

        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")
        lines = await transport.get_trust_lines("rANY")
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_update_existing_limit(self, transport):
        """Setting a new limit on an existing trust line updates it, no duplicate."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "500")
        lines = await transport.get_trust_lines("rANY")
        assert len(lines) == 1
        assert lines[0].limit == "500"
        # Owner count should still be 1, not 2
        assert (await transport.get_account_info("rANY")).owner_count == 1


class TestTrustLineRemovalActions:
    @pytest.mark.asyncio
    async def test_remove_trust_line_action(self, transport):
        """remove_trust_line action wraps submit_trust_set with limit=0."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        result = await remove_trust_line(transport, "sFAKE", "rISSUER", "HYGIENE")
        assert result.success
        assert result.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_verify_trust_line_removed_success(self, transport):
        """Verify removal succeeds when trust line is gone."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")

        result = await verify_trust_line_removed(
            transport, "rANY", "HYGIENE", expected_issuer="rISSUER"
        )
        assert not result.found
        assert result.passed
        assert "removed" in result.checks[0].lower()

    @pytest.mark.asyncio
    async def test_verify_trust_line_removed_still_present(self, transport):
        """Verify removal fails when trust line still exists."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")

        result = await verify_trust_line_removed(
            transport, "rANY", "HYGIENE", expected_issuer="rISSUER"
        )
        assert result.found
        assert not result.passed
        assert "still present" in result.failures[0].lower()


class TestHygieneLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, transport):
        """Full hygiene cycle: baseline -> create objects -> remove -> verify."""
        await transport.fund_from_faucet("rHOLDER")

        # Snapshot A — baseline
        snap_a = await snapshot_account(transport, "rHOLDER")
        baseline_owner = snap_a.owner_count

        # Create trust line (owner count +1)
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")

        # Create offer (owner count +1)
        await transport.submit_offer_create(
            "sFAKE", "HYGIENE", "10", "rISSUER",
            "XRP", "1", "",
        )

        # Snapshot B — dirty
        snap_b = await snapshot_account(transport, "rHOLDER")
        assert snap_b.owner_count == baseline_owner + 2

        # Compare A -> B
        cmp_ab = compare_snapshots(snap_a, snap_b, label="dirty")
        assert cmp_ab.owner_count_delta == 2
        assert cmp_ab.owner_count_changed

        # Cancel offer (owner count -1)
        offers = await transport.get_account_offers("rHOLDER")
        assert len(offers) == 1
        await transport.submit_offer_cancel("sFAKE", offers[0].sequence)

        # Remove trust line (owner count -1)
        result = await remove_trust_line(transport, "sFAKE", "rISSUER", "HYGIENE")
        assert result.success

        # Verify trust line is gone
        verify_result = await verify_trust_line_removed(
            transport, "rHOLDER", "HYGIENE"
        )
        assert not verify_result.found

        # Snapshot C — clean
        snap_c = await snapshot_account(transport, "rHOLDER")
        assert snap_c.owner_count == baseline_owner

        # Compare B -> C (should show -2)
        cmp_bc = compare_snapshots(snap_b, snap_c, label="clean")
        assert cmp_bc.owner_count_delta == -2
        assert any("decreased" in c.lower() for c in cmp_bc.checks)

        # Compare A -> C (should be same owner count)
        cmp_ac = compare_snapshots(snap_a, snap_c, label="full cycle")
        assert cmp_ac.owner_count_delta == 0
        assert not cmp_ac.owner_count_changed

    @pytest.mark.asyncio
    async def test_partial_cleanup(self, transport):
        """Remove one of two objects — owner count drops by 1, not 2."""
        # Create 2 objects
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")
        await transport.submit_offer_create(
            "sFAKE", "HYGIENE", "10", "rISSUER",
            "XRP", "1", "",
        )
        snap_dirty = await snapshot_account(transport, "rANY")
        assert snap_dirty.owner_count == 2

        # Remove only the trust line
        await remove_trust_line(transport, "sFAKE", "rISSUER", "HYGIENE")
        snap_partial = await snapshot_account(transport, "rANY")
        assert snap_partial.owner_count == 1

    @pytest.mark.asyncio
    async def test_trust_line_verify_after_creation(self, transport):
        """Existing verify_trust_line still works alongside removal."""
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "100")

        # verify_trust_line should find it
        result = await verify_trust_line(
            transport, "rANY", "HYGIENE", expected_issuer="rISSUER"
        )
        assert result.found

        # Remove it
        await transport.submit_trust_set("sFAKE", "rISSUER", "HYGIENE", "0")

        # verify_trust_line should NOT find it
        result = await verify_trust_line(
            transport, "rANY", "HYGIENE", expected_issuer="rISSUER"
        )
        assert not result.found
