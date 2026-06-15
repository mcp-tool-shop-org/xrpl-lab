"""Tests for NFT transport, actions, and the nft_minting_101 module."""

from pathlib import Path

import pytest

from xrpl_lab.actions.nft import get_account_nfts, mint_nft, verify_nft
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestNFTTransport:
    @pytest.mark.asyncio
    async def test_mint_success(self, transport):
        result = await transport.submit_nft_mint(
            "sFAKE", "ipfs://x", taxon=7, transfer_fee=500
        )
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid != ""
        assert result.nft_id != ""

    @pytest.mark.asyncio
    async def test_mint_fail(self, transport):
        transport.set_fail_next()
        result = await transport.submit_nft_mint("sFAKE", "ipfs://x")
        assert result.success is False
        assert result.nft_id == ""

    @pytest.mark.asyncio
    async def test_minted_nft_tracked(self, transport):
        r = await transport.submit_nft_mint("sFAKE", "ipfs://sword.json", taxon=7)
        nfts = await transport.get_account_nfts("rANY")
        assert len(nfts) == 1
        assert nfts[0].nft_id == r.nft_id
        assert nfts[0].taxon == 7
        assert nfts[0].uri == "ipfs://sword.json"
        assert nfts[0].flags & 0x8  # tfTransferable


class TestNFTActions:
    @pytest.mark.asyncio
    async def test_mint_and_verify(self, transport):
        r = await mint_nft(transport, "sFAKE", "ipfs://sword.json", taxon=7, transfer_fee=500)
        assert r.success and r.nft_id
        v = await verify_nft(transport, "rANY", expected_nft_id=r.nft_id)
        assert v.found
        assert v.passed
        assert v.nft is not None and v.nft.nft_id == r.nft_id

    @pytest.mark.asyncio
    async def test_verify_no_nfts(self, transport):
        v = await verify_nft(transport, "rEMPTY")
        assert v.found is False
        assert not v.passed
        assert "No NFTokens" in v.failures[0]

    @pytest.mark.asyncio
    async def test_verify_taxon_mismatch(self, transport):
        r = await mint_nft(transport, "sFAKE", "ipfs://x", taxon=7)
        v = await verify_nft(
            transport, "rANY", expected_nft_id=r.nft_id, expected_taxon=9
        )
        assert not v.passed
        assert any("Taxon mismatch" in f for f in v.failures)

    @pytest.mark.asyncio
    async def test_get_account_nfts_empty(self, transport):
        assert await get_account_nfts(transport, "rEMPTY") == []


class TestNFTModule:
    def test_module_lints_clean(self):
        path = Path(__file__).parent.parent / "modules" / "nft_minting_101.md"
        issues = lint_module_file(path)
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"lint errors: {[str(i) for i in errors]}"
