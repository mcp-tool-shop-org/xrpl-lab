"""Tests for DID transport, actions, and the did_101 module."""

from pathlib import Path

import pytest

from xrpl_lab.actions.did import set_did, verify_did
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestDIDTransport:
    @pytest.mark.asyncio
    async def test_set_success(self, transport):
        r = await transport.submit_did_set("sFAKE", uri="did:xrpl:x")
        assert r.success is True
        assert r.txid != ""

    @pytest.mark.asyncio
    async def test_set_fail(self, transport):
        transport.set_fail_next()
        r = await transport.submit_did_set("sFAKE", uri="did:xrpl:x")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_tracked(self, transport):
        await transport.submit_did_set("sFAKE", uri="did:xrpl:player1")
        did = await transport.get_did("rANY")
        assert did is not None
        assert did.uri == "did:xrpl:player1"


class TestDIDActions:
    @pytest.mark.asyncio
    async def test_set_and_verify(self, transport):
        await set_did(transport, "sFAKE", uri="did:xrpl:player1")
        v = await verify_did(transport, "rANY", expected_uri="did:xrpl:player1")
        assert v.found and v.passed
        assert v.did is not None and v.did.uri == "did:xrpl:player1"

    @pytest.mark.asyncio
    async def test_verify_none(self, transport):
        v = await verify_did(transport, "rEMPTY")
        assert not v.found and not v.passed

    @pytest.mark.asyncio
    async def test_verify_uri_mismatch(self, transport):
        await set_did(transport, "sFAKE", uri="did:xrpl:a")
        v = await verify_did(transport, "rANY", expected_uri="did:xrpl:b")
        assert not v.passed


class TestDIDModule:
    def test_lints_clean(self):
        issues = lint_module_file(Path(__file__).parent.parent / "modules" / "did_101.md")
        assert not [i for i in issues if i.level == "error"]
