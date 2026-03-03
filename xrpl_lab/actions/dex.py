"""DEX actions — create offers, cancel offers, verify offers."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import OfferInfo, SubmitResult, Transport


async def create_offer(
    transport: Transport,
    wallet_seed: str,
    taker_pays_currency: str,
    taker_pays_value: str,
    taker_pays_issuer: str,
    taker_gets_currency: str,
    taker_gets_value: str,
    taker_gets_issuer: str,
) -> SubmitResult:
    """Create a DEX offer (OfferCreate)."""
    return await transport.submit_offer_create(
        wallet_seed=wallet_seed,
        taker_pays_currency=taker_pays_currency,
        taker_pays_value=taker_pays_value,
        taker_pays_issuer=taker_pays_issuer,
        taker_gets_currency=taker_gets_currency,
        taker_gets_value=taker_gets_value,
        taker_gets_issuer=taker_gets_issuer,
    )


async def cancel_offer(
    transport: Transport,
    wallet_seed: str,
    offer_sequence: int,
) -> SubmitResult:
    """Cancel a DEX offer (OfferCancel)."""
    return await transport.submit_offer_cancel(
        wallet_seed=wallet_seed,
        offer_sequence=offer_sequence,
    )


async def get_offers(
    transport: Transport,
    address: str,
) -> list[OfferInfo]:
    """Get all active offers for an address."""
    return await transport.get_account_offers(address)


@dataclass
class OfferVerifyResult:
    """Result of verifying offer state."""

    found: bool
    offer: OfferInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_offer_present(
    transport: Transport,
    address: str,
    offer_sequence: int,
) -> OfferVerifyResult:
    """Verify an offer exists in the account's active offers."""
    offers = await transport.get_account_offers(address)
    checks: list[str] = []
    failures: list[str] = []

    match = None
    for o in offers:
        if o.sequence == offer_sequence:
            match = o
            break

    if not match:
        failures.append(f"Offer seq {offer_sequence} not found in active offers")
        return OfferVerifyResult(
            found=False, offer=None, checks=checks, failures=failures
        )

    checks.append(f"Offer found: seq {offer_sequence}")
    checks.append(f"Taker pays: {match.taker_pays}")
    checks.append(f"Taker gets: {match.taker_gets}")

    return OfferVerifyResult(
        found=True, offer=match, checks=checks, failures=failures
    )


async def verify_offer_absent(
    transport: Transport,
    address: str,
    offer_sequence: int,
) -> OfferVerifyResult:
    """Verify an offer no longer exists (was cancelled or consumed)."""
    offers = await transport.get_account_offers(address)
    checks: list[str] = []
    failures: list[str] = []

    for o in offers:
        if o.sequence == offer_sequence:
            failures.append(
                f"Offer seq {offer_sequence} still active — expected absent"
            )
            return OfferVerifyResult(
                found=True, offer=o, checks=checks, failures=failures
            )

    checks.append(f"Offer seq {offer_sequence} confirmed absent")

    return OfferVerifyResult(
        found=False, offer=None, checks=checks, failures=failures
    )
