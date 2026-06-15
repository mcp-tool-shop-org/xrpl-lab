"""Tests for MPT transport, actions, and the mpt_issuance_101 module."""

from pathlib import Path

import pytest

from xrpl_lab.actions.mpt import create_mpt_issuance, verify_mpt_issuance
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestMPTTransport:
    @pytest.mark.asyncio
    async def test_create_success(self, transport):
        r = await transport.submit_mpt_issuance_create(
            "sFAKE", "1000000", asset_scale=2, transfer_fee=500
        )
        assert r.success is True
        assert r.txid != ""

    @pytest.mark.asyncio
    async def test_create_fail(self, transport):
        transport.set_fail_next()
        r = await transport.submit_mpt_issuance_create("sFAKE", "1000000")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_tracked(self, transport):
        await transport.submit_mpt_issuance_create(
            "sFAKE", "1000000", asset_scale=2, transfer_fee=500
        )
        iss = await transport.get_mpt_issuances("rANY")
        assert len(iss) == 1
        assert iss[0].maximum_amount == "1000000"
        assert iss[0].asset_scale == 2
        assert iss[0].flags & 0x20  # tfMPTCanTransfer


class TestMPTActions:
    @pytest.mark.asyncio
    async def test_create_and_verify(self, transport):
        await create_mpt_issuance(transport, "sFAKE", "1000000", asset_scale=2)
        v = await verify_mpt_issuance(transport, "rANY", expected_maximum="1000000")
        assert v.found and v.passed
        assert v.issuance is not None and v.issuance.maximum_amount == "1000000"

    @pytest.mark.asyncio
    async def test_verify_none(self, transport):
        v = await verify_mpt_issuance(transport, "rEMPTY")
        assert not v.found and not v.passed

    @pytest.mark.asyncio
    async def test_verify_max_mismatch(self, transport):
        await create_mpt_issuance(transport, "sFAKE", "1000000")
        v = await verify_mpt_issuance(transport, "rANY", expected_maximum="999")
        assert not v.passed


class TestMPTModule:
    def test_lints_clean(self):
        issues = lint_module_file(Path(__file__).parent.parent / "modules" / "mpt_issuance_101.md")
        assert not [i for i in issues if i.level == "error"]
