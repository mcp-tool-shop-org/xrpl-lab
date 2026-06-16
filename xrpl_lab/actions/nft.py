"""NFT actions — mint an NFToken (a game asset) and verify ownership on-ledger."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import NFTInfo, NFTOfferInfo, SubmitResult, Transport


async def mint_nft(
    transport: Transport,
    wallet_seed: str,
    uri: str,
    taxon: int = 0,
    transfer_fee: int = 0,
    transferable: bool = True,
    mutable: bool = False,
) -> SubmitResult:
    """Mint an NFToken on the ledger. Returns SubmitResult with nft_id set on success.

    ``mutable`` sets tfMutable (XLS-46) so the URI can later be changed via
    NFTokenModify — the basis for evolving/leveling game items.
    """
    return await transport.submit_nft_mint(
        wallet_seed=wallet_seed,
        uri=uri,
        taxon=taxon,
        transfer_fee=transfer_fee,
        transferable=transferable,
        mutable=mutable,
    )


async def create_nft_offer(
    transport: Transport,
    wallet_seed: str,
    nftoken_id: str,
    amount: str,
    sell: bool = True,
    destination: str = "",
    owner: str = "",
    currency: str = "XRP",
    issuer: str = "",
) -> SubmitResult:
    """List an NFToken for sale (or place a buy offer) — NFTokenCreateOffer."""
    return await transport.submit_nft_create_offer(
        wallet_seed=wallet_seed,
        nftoken_id=nftoken_id,
        amount=amount,
        sell=sell,
        destination=destination,
        owner=owner,
        currency=currency,
        issuer=issuer,
    )


async def accept_nft_offer(
    transport: Transport,
    wallet_seed: str,
    sell_offer: str = "",
    buy_offer: str = "",
) -> SubmitResult:
    """Accept an NFTokenOffer, settling the trade atomically (NFTokenAcceptOffer)."""
    return await transport.submit_nft_accept_offer(
        wallet_seed=wallet_seed,
        sell_offer=sell_offer,
        buy_offer=buy_offer,
    )


async def get_nft_offers(
    transport: Transport,
    nftoken_id: str,
    sell: bool = True,
) -> list[NFTOfferInfo]:
    """List open sell (or buy) offers for an NFToken."""
    return await transport.get_nft_offers(nftoken_id, sell=sell)


async def modify_nft(
    transport: Transport,
    wallet_seed: str,
    nftoken_id: str,
    uri: str,
    owner: str = "",
) -> SubmitResult:
    """Change a mutable NFToken's URI (NFTokenModify) — level up / evolve an item."""
    return await transport.submit_nft_modify(
        wallet_seed=wallet_seed,
        nftoken_id=nftoken_id,
        uri=uri,
        owner=owner,
    )


async def get_account_nfts(transport: Transport, address: str) -> list[NFTInfo]:
    """List NFTokens owned by an address."""
    return await transport.get_account_nfts(address)


async def burn_nft(
    transport: Transport,
    wallet_seed: str,
    nftoken_id: str,
) -> SubmitResult:
    """Burn (permanently destroy) an NFToken, freeing its reserve (NFTokenBurn)."""
    return await transport.submit_nft_burn(wallet_seed, nftoken_id)


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


@dataclass
class NFTBurnedResult:
    """Result of verifying an NFToken has been burned (no longer owned)."""

    gone: bool
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.gone and len(self.failures) == 0


async def verify_nft_burned(
    transport: Transport,
    address: str,
    nftoken_id: str | None = None,
) -> NFTBurnedResult:
    """Verify an NFToken is gone after a burn (reserve freed).

    If ``nftoken_id`` is given, that specific token must no longer be owned by
    *address*; otherwise the account must own no NFTokens at all.
    """
    nfts = await transport.get_account_nfts(address)
    checks: list[str] = []
    failures: list[str] = []

    if nftoken_id:
        still_owned = any(n.nft_id == nftoken_id for n in nfts)
        if still_owned:
            failures.append(
                f"NFToken {nftoken_id[:16]}... is still owned — burn did not remove it"
            )
            return NFTBurnedResult(False, checks, failures)
        checks.append(
            f"NFToken {nftoken_id[:16]}... is gone — burned, reserve freed"
        )
        return NFTBurnedResult(True, checks, failures)

    if nfts:
        failures.append(f"{len(nfts)} NFToken(s) still owned by this account")
        return NFTBurnedResult(False, checks, failures)
    checks.append("No NFTokens remain — burned, reserve freed")
    return NFTBurnedResult(True, checks, failures)


@dataclass
class NFTModifiedResult:
    """Result of verifying a mutable NFToken's URI was changed in place."""

    changed: bool
    nft: NFTInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.changed and len(self.failures) == 0


async def verify_nft_modified(
    transport: Transport,
    address: str,
    nftoken_id: str,
    expected_uri: str,
) -> NFTModifiedResult:
    """Verify an NFToken's URI now equals *expected_uri* on the SAME NFTokenID.

    This is the on-ledger proof that a dynamic NFT leveled up: the asset's
    identity (NFTokenID) is unchanged, but its state (URI) advanced.
    """
    nfts = await transport.get_account_nfts(address)
    checks: list[str] = []
    failures: list[str] = []

    match = next((n for n in nfts if n.nft_id == nftoken_id), None)
    if match is None:
        failures.append(
            f"NFToken {nftoken_id[:16]}... not found — cannot confirm modification"
        )
        return NFTModifiedResult(False, None, checks, failures)

    checks.append(f"Same NFTokenID: {match.nft_id[:24]}... (identity preserved)")
    if match.uri == expected_uri:
        checks.append(f"URI advanced to: {match.uri}")
        return NFTModifiedResult(True, match, checks, failures)

    failures.append(
        f"URI did not change as expected: have {match.uri!r}, "
        f"expected {expected_uri!r}"
    )
    return NFTModifiedResult(False, match, checks, failures)


@dataclass
class NFTOwnershipResult:
    """Result of verifying an NFToken is owned by an expected address (trade settled)."""

    transferred: bool
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.transferred and len(self.failures) == 0


async def verify_nft_owned_by(
    transport: Transport,
    expected_owner: str,
    nftoken_id: str,
    previous_owner: str = "",
) -> NFTOwnershipResult:
    """Verify *nftoken_id* is now owned by *expected_owner* (and gone from the seller).

    The on-ledger proof that an NFT trade settled: ``account_nfts`` for the
    buyer lists the token, and (when ``previous_owner`` is given) the seller no
    longer holds it.
    """
    checks: list[str] = []
    failures: list[str] = []

    buyer_nfts = await transport.get_account_nfts(expected_owner)
    if any(n.nft_id == nftoken_id for n in buyer_nfts):
        checks.append(
            f"Buyer {expected_owner[:12]}... now owns {nftoken_id[:16]}..."
        )
    else:
        failures.append(
            f"NFToken {nftoken_id[:16]}... is NOT owned by {expected_owner[:12]}... "
            "— the trade did not settle"
        )

    if previous_owner and previous_owner != expected_owner:
        seller_nfts = await transport.get_account_nfts(previous_owner)
        if any(n.nft_id == nftoken_id for n in seller_nfts):
            failures.append(
                f"Seller {previous_owner[:12]}... still holds the NFToken "
                "— ownership did not move"
            )
        else:
            checks.append(
                f"Seller {previous_owner[:12]}... no longer holds it — clean transfer"
            )

    transferred = not failures
    return NFTOwnershipResult(transferred, checks, failures)
