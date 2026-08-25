"""Wave-5 Stage B — F-21a14172 fee-debit mapping.

Ten write methods call ``_reserve_guard`` (which folds ``fee_drops`` into the
balance check) but never call ``_debit_fee``. SubmitResult still reports
``fee='12'``, yet ``_balances`` is never decremented by that fee. Vacuous
conservation / "no debit" tests previously enshrined a stronger-than-true
zero-fee invariant.

This file asserts the network fee IS actually charged on each of those ten
methods (amount-move lessons stay separate from fee reality).
"""

from __future__ import annotations

import pytest

from xrpl_lab.transport.dry_run import (
    _DRY_FEE_DROPS,
    _DRY_RUN_WALLET_ADDRESS,
    DryRunTransport,
)


async def _funded() -> DryRunTransport:
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    return t


class TestFeeDebitOnPreviouslyExemptWrites:
    """Each of the ten guard-without-debit sites must actually debit the fee."""

    @pytest.mark.asyncio
    async def test_check_create_debits_fee_not_send_max(self) -> None:
        t = await _funded()
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_check_create("sSEED", "rDEST", "50")
        assert r.success
        assert r.fee == str(_DRY_FEE_DROPS)
        # SendMax is NOT locked; only the network fee leaves the writer.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS

    @pytest.mark.asyncio
    async def test_check_cancel_debits_fee(self) -> None:
        t = await _funded()
        created = await t.submit_check_create("sSEED", "rDEST", "50")
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_check_cancel("sSEED", created.check_id)
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS

    @pytest.mark.asyncio
    async def test_check_cash_debits_fee_from_writer_plus_amount(self) -> None:
        t = await _funded()
        dest = "rPLAYERCHECKCASH00000000000000"
        created = await t.submit_check_create("sSEED", dest, "50")
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_check_cash(
            "sPLAYER", created.check_id, amount="50", wallet_address=dest
        )
        assert r.success
        # Writer pays delivered amount + the fee folded into _reserve_guard.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 50_000_000 - _DRY_FEE_DROPS
        )
        assert t._balances[dest] == 50_000_000

    @pytest.mark.asyncio
    async def test_escrow_create_debits_amount_and_fee(self) -> None:
        t = await _funded()
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_escrow_create("sSEED", "100", "rDEST", finish_after=0)
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 100_000_000 - _DRY_FEE_DROPS
        )

    @pytest.mark.asyncio
    async def test_escrow_create_cancel_round_trip_charges_two_fees(self) -> None:
        t = await _funded()
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        create = await t.submit_escrow_create(
            "sSEED", "100", "rDEST", finish_after=0
        )
        cancel = await t.submit_escrow_cancel(
            "sSEED", _DRY_RUN_WALLET_ADDRESS, create.sequence
        )
        assert create.success and cancel.success
        # Real ledger: EscrowCreate + EscrowCancel = 24 drops of fees; locked
        # amount returns. Zero-fee conservation was the bug.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - (2 * _DRY_FEE_DROPS)

    @pytest.mark.asyncio
    async def test_escrow_finish_debits_finisher_fee(self) -> None:
        t = await _funded()
        dest = "rESCROWFINISHDEST000000000000"
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        create = await t.submit_escrow_create(
            "sSEED", "250", dest, finish_after=0
        )
        fin = await t.submit_escrow_finish(
            "sSEED", _DRY_RUN_WALLET_ADDRESS, create.sequence
        )
        assert fin.success
        # create fee + finish fee from same collapsed seed; dest gets amount.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 250_000_000 - (2 * _DRY_FEE_DROPS)
        )
        assert t._balances[dest] == 250_000_000
        total = (
            t._balances[_DRY_RUN_WALLET_ADDRESS] + t._balances[dest]
        )
        assert total == before - (2 * _DRY_FEE_DROPS)

    @pytest.mark.asyncio
    async def test_payment_channel_create_debits_deposit_and_fee(self) -> None:
        t = await _funded()
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_payment_channel_create(
            "sSEED", "200", "rDEST", settle_delay=0, public_key="ED00"
        )
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 200_000_000 - _DRY_FEE_DROPS
        )

    @pytest.mark.asyncio
    async def test_payment_channel_fund_debits_topup_and_fee(self) -> None:
        t = await _funded()
        create = await t.submit_payment_channel_create(
            "sSEED", "100", "rDEST", settle_delay=86400, public_key="ED00"
        )
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        fund = await t.submit_payment_channel_fund(
            "sSEED", create.channel_id, "50"
        )
        assert fund.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 50_000_000 - _DRY_FEE_DROPS
        )

    @pytest.mark.asyncio
    async def test_payment_channel_claim_debits_signer_fee(self) -> None:
        t = await _funded()
        dest = "rCHANCLAIMDEST000000000000000"
        create = await t.submit_payment_channel_create(
            "sSEED", "200", dest, settle_delay=0, public_key="ED00"
        )
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        sig = await t.authorize_payment_channel_claim("sSEED", create.channel_id, "150")
        claim = await t.submit_payment_channel_claim(
            "sSEED",
            create.channel_id,
            balance_xrp="150",
            amount_xrp="150",
            signature=sig,
            public_key="ED00",
        )
        assert claim.success
        # Claim credits destination; fee hits the (collapsed) signer.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS
        assert t._balances[dest] == 150_000_000

    @pytest.mark.asyncio
    async def test_nft_accept_offer_debits_acceptor_fee(self) -> None:
        t = await _funded()
        buyer = "rNFTBUYER000000000000000000000"
        t._balances[buyer] = 1_000_000_000
        mint = await t.submit_nft_mint("sSEED", uri="ipfs://x", transfer_fee=0)
        assert mint.success and mint.nft_id
        offer = await t.submit_nft_create_offer(
            "sSEED", mint.nft_id, "10", sell=True, destination=buyer,
            owner=_DRY_RUN_WALLET_ADDRESS,
        )
        assert offer.success
        before = t._balances[buyer]
        accept = await t.submit_nft_accept_offer(
            "sBUYER", sell_offer=offer.nft_offer_index
        )
        # Directed sell: acceptor/price_payer is the distinct buyer address.
        assert accept.success
        assert t._balances[buyer] == before - 10_000_000 - _DRY_FEE_DROPS
