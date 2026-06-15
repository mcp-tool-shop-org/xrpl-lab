"""Tests for escrow transport, actions, and the escrow_101 module."""

from pathlib import Path

import pytest

from xrpl_lab.actions.escrow import create_escrow, verify_escrow
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport

FINISH = 900000000  # arbitrary ripple-epoch time for offline tests


@pytest.fixture
def transport():
    return DryRunTransport()


class TestEscrowTransport:
    @pytest.mark.asyncio
    async def test_create_success(self, transport):
        r = await transport.submit_escrow_create("sFAKE", "10", "rDEST", finish_after=FINISH)
        assert r.success is True
        assert r.txid != ""

    @pytest.mark.asyncio
    async def test_create_fail(self, transport):
        transport.set_fail_next()
        r = await transport.submit_escrow_create("sFAKE", "10", "rDEST", finish_after=FINISH)
        assert r.success is False

    @pytest.mark.asyncio
    async def test_tracked(self, transport):
        await transport.submit_escrow_create("sFAKE", "10", "rDEST", finish_after=FINISH)
        es = await transport.get_escrows("rANY")
        assert len(es) == 1
        assert es[0].destination == "rDEST"
        assert es[0].amount == "10"
        assert es[0].finish_after == FINISH


class TestEscrowActions:
    @pytest.mark.asyncio
    async def test_create_and_verify(self, transport):
        await create_escrow(transport, "sFAKE", "10", "rDEST", FINISH)
        v = await verify_escrow(transport, "rANY", expected_destination="rDEST")
        assert v.found and v.passed

    @pytest.mark.asyncio
    async def test_verify_none(self, transport):
        v = await verify_escrow(transport, "rEMPTY")
        assert not v.found and not v.passed


class TestEscrowModule:
    def test_lints_clean(self):
        issues = lint_module_file(Path(__file__).parent.parent / "modules" / "escrow_101.md")
        assert not [i for i in issues if i.level == "error"]
