"""Dry-run OwnerCount must agree across object types for ONE real account.

Regression for account_hygiene / dex_market_making_101 / escrow_finish_101
failing their own verifications under ``--dry-run``: trust lines were booked
under the caller's real address, offers/escrows under the synthetic
seed-derived address, so ``get_account_info(real)`` saw only part of the
account's objects and the escrow created-at lookup missed.
"""

from __future__ import annotations

import pytest

from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport

REAL = "rLEARNER1234567890abcdefghijkLM"
ISSUER = "rISSUER1234567890abcdefghijkLMN"


@pytest.mark.asyncio
async def test_trust_line_plus_offer_counts_two_for_the_real_address() -> None:
    t = DryRunTransport()
    await t.fund_from_faucet(REAL)
    base = (await t.get_account_info(REAL)).owner_count

    await t.submit_trust_set("sSEED", ISSUER, "HYG", "100", wallet_address=REAL)
    offer = await t.submit_offer_create(
        "sSEED", "HYG", "10", ISSUER, "XRP", "1", "", wallet_address=REAL
    )
    assert (await t.get_account_info(REAL)).owner_count == base + 2  # was +1

    cancel = await t.submit_offer_cancel("sSEED", offer.sequence, wallet_address=REAL)
    assert cancel.success
    await t.submit_trust_set("sSEED", ISSUER, "HYG", "0", wallet_address=REAL)
    assert (await t.get_account_info(REAL)).owner_count == base  # was -1 (clamped)
    assert [o for o in await t.get_account_offers(REAL)] == []


@pytest.mark.asyncio
async def test_finish_escrow_named_by_real_owner_inside_compressed_time() -> None:
    """Handler shape: create under a seed, finish naming the REAL address, with
    wall-clock FinishAfter/CancelAfter far behind the default far-future clock."""
    t = DryRunTransport()
    await t.fund_from_faucet(REAL)
    base = (await t.get_account_info(REAL)).owner_count

    create = await t.submit_escrow_create(
        "sSEED", "10", REAL, finish_after=845_000_000, cancel_after=845_086_400
    )
    assert create.success
    assert (await t.get_account_info(REAL)).owner_count == base + 1

    fin = await t.submit_escrow_finish("sSEED", REAL, create.sequence)
    assert fin.success, fin.error  # was tecNO_PERMISSION "escrow expired"
    assert (await t.get_account_info(REAL)).owner_count == base
    # The synthetic bucket the create incremented was released too.
    assert t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 0
