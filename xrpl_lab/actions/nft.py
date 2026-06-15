"""NFT actions — mint an NFToken (a game asset) and verify ownership on-ledger."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import NFTInfo, SubmitResult, Transport


async def mint_nft(
    transport: Transport,
    wallet_seed: str,
    uri: str,
    taxon: int = 0,
    transfer_fee: int = 0,
    transferable: bool = True,
) -> SubmitResult:
    """Mint an NFToken on the ledger. Returns SubmitResult with nft_id set on success."""
    return await transport.submit_nft_mint(
        wallet_seed=wallet_seed,
        uri=uri,
        taxon=taxon,
        transfer_fee=transfer_fee,
        transferable=transferable,
    )


async def get_account_nfts(transport: Transport, address: str) -> list[NFTInfo]:
    """List NFTokens owned by an address."""
    return await transport.get_account_nfts(address)


@dataclass
class NFTVerifyResult:
    """Result of verifying NFT ownership on-ledger."""

    found: bool
    nft: NFTInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_nft(
    transport: Transport,
    address: str,
    expected_nft_id: str | None = None,
    expected_taxon: int | None = None,
) -> NFTVerifyResult:
    """Verify an NFT is owned by *address*, optionally matching a specific NFTokenID / taxon."""
    nfts = await transport.get_account_nfts(address)
    checks: list[str] = []
    failures: list[str] = []

    if not nfts:
        failures.append("No NFTokens found for this account")
        return NFTVerifyResult(found=False, nft=None, checks=checks, failures=failures)

    if expected_nft_id:
        match = next((n for n in nfts if n.nft_id == expected_nft_id), None)
        if match is None:
            failures.append(
                f"NFToken {expected_nft_id[:16]}... not found among {len(nfts)} owned"
            )
            return NFTVerifyResult(found=False, nft=None, checks=checks, failures=failures)
    else:
        match = nfts[-1]  # most recently minted

    checks.append(f"NFToken found: {match.nft_id[:24]}...")
    checks.append(f"Issuer: {match.issuer}")
    checks.append(f"Taxon (collection id): {match.taxon}")
    if match.uri:
        checks.append(f"URI: {match.uri}")
    checks.append(f"Transferable: {'yes' if match.flags & 0x8 else 'no'}")
    if match.transfer_fee:
        checks.append(f"Royalty (TransferFee): {match.transfer_fee / 1000:.3f}%")

    if expected_taxon is not None and match.taxon != expected_taxon:
        failures.append(f"Taxon mismatch: expected {expected_taxon}, got {match.taxon}")

    return NFTVerifyResult(found=True, nft=match, checks=checks, failures=failures)
