"""Tests for payment channels (FT-CURRIC-001) — create/fund/claim + off-ledger signing."""

from pathlib import Path

import pytest

from xrpl_lab.actions.paychan import (
    check_claim,
    fund_channel,
    open_channel,
    redeem_claim,
    sign_claim,
    verify_channel,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport


@pytest.mark.asyncio
async def test_channel_create_fund_and_verify():
    t = DryRunTransport()
    create = await open_channel(t, "sSENDER", "10", "rRECEIVER", 86400)
    assert create.success and create.channel_id
    cid = create.channel_id

    v = await verify_channel(t, _DRY_RUN_WALLET_ADDRESS, channel_id=cid, expect_amount_xrp="10")
    assert v.passed

    f = await fund_channel(t, "sSENDER", cid, "5")
    assert f.success
    v2 = await verify_channel(t, _DRY_RUN_WALLET_ADDRESS, channel_id=cid, expect_amount_xrp="15")
    assert v2.passed


@pytest.mark.asyncio
async def test_offledger_claim_sign_and_verify():
    t = DryRunTransport()
    create = await open_channel(t, "sSENDER", "10", "rRECEIVER", 86400)
    cid = create.channel_id

    sig = await sign_claim(t, "sSENDER", cid, "3")
    assert sig
    assert await check_claim(t, cid, "3", "", sig) is True
    # A claim for a different amount is a different signed message → must not verify.
    assert await check_claim(t, cid, "9", "", sig) is False


@pytest.mark.asyncio
async def test_claim_redeem_settles_to_receiver():
    t = DryRunTransport()
    create = await open_channel(t, "sSENDER", "10", "rRECEIVER", 86400)
    cid = create.channel_id

    sig = await sign_claim(t, "sSENDER", cid, "7")
    redeem = await redeem_claim(t, "sRECEIVER", cid, "7", signature=sig, public_key="")
    assert redeem.success

    v = await verify_channel(t, _DRY_RUN_WALLET_ADDRESS, channel_id=cid, expect_balance_xrp="7")
    assert v.passed


@pytest.mark.asyncio
async def test_claim_cannot_exceed_deposit():
    t = DryRunTransport()
    create = await open_channel(t, "sSENDER", "5", "rRECEIVER", 86400)
    cid = create.channel_id
    sig = await sign_claim(t, "sSENDER", cid, "9")  # more than the 5 deposited
    redeem = await redeem_claim(t, "sRECEIVER", cid, "9", signature=sig, public_key="")
    assert not redeem.success
    assert redeem.result_code == "tecUNFUNDED_PAYMENT"


@pytest.mark.asyncio
async def test_testnet_offledger_claim_crypto_roundtrip():
    # The OFF-LEDGER claim sign/verify is pure crypto (no network) — exercise the
    # real testnet path with a real wallet to prove the encode_for_signing_claim
    # + keypairs roundtrip is correct.
    from xrpl.wallet import Wallet

    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = XRPLTestnetTransport()
    w = Wallet.create()
    cid = "5" * 64

    sig = await t.authorize_payment_channel_claim(w.seed, cid, "3")
    assert sig
    assert await t.verify_payment_channel_claim(cid, "3", w.public_key, sig) is True
    # Tampered amount must fail verification against the same signature.
    assert await t.verify_payment_channel_claim(cid, "9", w.public_key, sig) is False


def test_payment_channel_module_lints_clean():
    issues = lint_module_file(
        Path(__file__).parent.parent / "modules" / "payment_channel_101.md"
    )
    assert not [i for i in issues if i.level == "error"]
