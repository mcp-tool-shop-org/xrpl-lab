"""handlers.py 4120+: clawback, default ripple, NFT marketplace and dynamic NFTs."""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from tests.cov_handlers_b._support import (
    SEED,
    TREASURY,
    Rig,
    fail_result,
    ok_result,
    patch_action,
)
from xrpl_lab.actions.nft import NFTModifiedResult, NFTOwnershipResult
from xrpl_lab.actions.trust_line import ClawbackVerifyResult, set_trust_line
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.transport.base import NFTOfferInfo, TrustLineInfo
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport

pytestmark = pytest.mark.asyncio

ISSUER = "rClawIssuerAAAAAAAAAAAAAAAAAAAAAAAA"


def _failed_verification(rig: Rig) -> bool:
    return any(v["passed"] is False for v in rig.context.get("verifications", []))


# ── enable_clawback / default ripple ──────────────────────────────────


async def test_enable_clawback_requires_issuer() -> None:
    rig = Rig()
    await rig.run(handlers.handle_enable_clawback)
    assert "No issuer wallet in context" in rig.out
    assert rig.records == []


async def test_enable_clawback_success_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.fund(ISSUER)
    rig.context.update(issuer_seed=_SecretValue("sISS"), issuer_address=ISSUER)
    ctx = await rig.run(handlers.handle_enable_clawback)
    assert ctx["clawback_enabled"] is True
    assert "Clawback enabled on the issuer." in rig.out
    assert [r.success for r in rig.records] == [True]

    rig = Rig()
    rig.context["issuer_seed"] = "sISS"  # plain string seed
    patch_action(monkeypatch, "enable_clawback", fail_result("tecOWNERS"))
    ctx = await rig.run(handlers.handle_enable_clawback)
    assert "clawback_enabled" not in ctx
    assert "Enabling clawback failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_enable_default_ripple_requires_issuer() -> None:
    rig = Rig()
    await rig.run(handlers.handle_enable_default_ripple)
    assert "No issuer wallet in context" in rig.out


async def test_enable_default_ripple_is_idempotent_on_dry_run() -> None:
    rig = Rig()
    await rig.fund(ISSUER)
    rig.context.update(issuer_seed=_SecretValue("sISS"), issuer_address=ISSUER)
    ctx = await rig.run(handlers.handle_enable_default_ripple)
    assert ctx["default_ripple_enabled"] is True
    assert "Default Ripple enabled on the issuer." in rig.out
    assert len(rig.records) == 1

    rig.clear()
    await rig.run(handlers.handle_enable_default_ripple)
    assert "already enabled" in rig.out
    assert len(rig.records) == 1  # no second transaction, no second fee


async def test_enable_default_ripple_failure() -> None:
    rig = Rig()
    await rig.fund(ISSUER)
    rig.context.update(issuer_seed=_SecretValue("sISS"), issuer_address=ISSUER)
    rig.transport.set_fail_next()
    ctx = await rig.run(handlers.handle_enable_default_ripple)
    assert "Enabling Default Ripple failed" in rig.out
    assert "default_ripple_enabled" not in ctx
    assert [r.success for r in rig.records] == [False]


# ── token balance snapshot / clawback / verify ────────────────────────


class _LinesTransport(DryRunTransport):
    def __init__(self, lines) -> None:
        super().__init__()
        self._lines = lines

    async def get_trust_lines(self, address: str):
        return self._lines


async def test_snapshot_token_balance_picks_the_issuers_line() -> None:
    lines = [
        TrustLineInfo(account=TREASURY, peer="rOther", currency="LAB", balance="5"),
        TrustLineInfo(account=TREASURY, peer=ISSUER, currency="LAB", balance="70"),
    ]
    rig = Rig(_LinesTransport(lines))
    rig.context["issuer_address"] = ISSUER
    ctx = await rig.run(handlers.handle_snapshot_token_balance, currency="LAB", label="before")
    assert ctx["token_balance_before"] == "70"
    assert "LAB balance (before): 70" in rig.out


async def test_snapshot_token_balance_without_issuer_takes_first_match_and_defaults_zero() -> None:
    lines = [TrustLineInfo(account=TREASURY, peer="rOther", currency="LAB", balance="5")]
    rig = Rig(_LinesTransport(lines))
    ctx = await rig.run(handlers.handle_snapshot_token_balance, label="after")
    assert ctx["token_balance_after"] == "5"

    rig = Rig(_LinesTransport(lines))
    rig.context["issuer_address"] = ISSUER
    ctx = await rig.run(handlers.handle_snapshot_token_balance, currency="GLD")
    assert ctx["token_balance_before"] == "0"


async def test_snapshot_token_balance_without_wallet() -> None:
    rig = Rig()
    rig.state.wallet_address = None
    ctx = await rig.run(handlers.handle_snapshot_token_balance)
    assert "No wallet address found" in rig.out
    assert "token_balance_before" not in ctx


async def _clawback_rig() -> Rig:
    """Issuer enabled clawback, issued 100 LAB to the treasury (the holder)."""
    rig = Rig()
    await rig.fund(TREASURY, ISSUER)
    rig.context.update(issuer_seed=_SecretValue("sISS"), issuer_address=ISSUER)
    await rig.run(handlers.handle_enable_clawback)
    await set_trust_line(
        rig.transport, SEED, ISSUER, "LAB", "1000", wallet_address=TREASURY,
    )
    issued = await rig.transport.submit_issued_payment(
        wallet_seed="sISS", destination=TREASURY, currency="LAB",
        issuer=ISSUER, amount="100",
    )
    assert issued.success
    rig.clear()
    rig.state.tx_index.clear()
    rig.context.pop("txids", None)
    return rig


async def test_clawback_recalls_exact_amount_and_verifies() -> None:
    rig = await _clawback_rig()
    await rig.run(handlers.handle_snapshot_token_balance, label="before")
    assert rig.context["token_balance_before"] == "100"
    ctx = await rig.run(handlers.handle_clawback, amount="30")
    assert "Clawback succeeded" in rig.out
    assert ctx["clawback_amount"] == "30" and ctx["clawback_currency"] == "LAB"
    assert [r.success for r in rig.records] == [True]

    await rig.run(handlers.handle_verify_clawback)
    assert "Issuer recall verified" in rig.out
    assert rig.verdicts("verify_clawback")[-1]["passed"] is True


async def test_clawback_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_clawback)
    assert "Missing issuer or holder wallet" in rig.out

    rig.context["issuer_seed"] = _SecretValue("sISS")
    patch_action(monkeypatch, "clawback_tokens", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_clawback)
    assert "Clawback failed" in rig.out
    assert "clawback_amount" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_verify_clawback_without_wallet_and_with_failure(monkeypatch) -> None:
    rig = Rig()
    rig.state.wallet_address = ""
    await rig.run(handlers.handle_verify_clawback)
    assert "No wallet address found" in rig.out
    assert rig.verdicts("verify_clawback")[0]["passed"] is False

    rig = Rig()
    res = ClawbackVerifyResult(
        correct=False, before="100", after="100", expected_after="70",
        checks=[], failures=["balance unchanged"],
    )
    calls = patch_action(monkeypatch, "verify_clawback", res)
    rig.context["token_balance_before"] = "100"
    rig.context["clawback_amount"] = "30"
    await rig.run(handlers.handle_verify_clawback)
    assert calls[0][0][-2:] == ("100", "30")
    assert "balance unchanged" in rig.out
    assert "Issuer recall verified" not in rig.out
    assert rig.verdicts()[0]["passed"] is False


# ── clawback against an issuer that never opted in ────────────────────


async def test_noclaw_issuer_then_clawback_is_refused() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_create_noclaw_issuer, currency="NOC", amount="50")
    assert isinstance(ctx["noclaw_issuer_seed"], _SecretValue)
    assert ctx["noclaw_currency"] == "NOC"
    assert "Issued 50 NOC from a no-clawback issuer." in rig.out
    assert "Issuer funded!" not in rig.out  # quiet funding

    rig.clear()
    ctx = await rig.run(handlers.handle_clawback_expect_fail, amount="10")
    assert "Expected failure:" in rig.out
    assert ctx["failed_txids"][0]["result_code"]
    assert "Category:" in rig.out


async def test_noclaw_issuer_issuance_note_and_funding_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.fund()
    patch_action(monkeypatch, "issue_token", fail_result("tecPATH_DRY"))
    await rig.run(handlers.handle_create_noclaw_issuer)
    assert "Issuance setup note: simulated tecPATH_DRY" in rig.out


async def test_clawback_expect_fail_prerequisites_and_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_clawback_expect_fail)
    assert "Missing no-clawback issuer or holder" in rig.out

    rig.context.update(noclaw_issuer_seed="sN", noclaw_issuer_address="rN")
    patch_action(monkeypatch, "clawback_tokens", ok_result("TXCLAW"))
    await rig.run(handlers.handle_clawback_expect_fail)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXCLAW", True)]


async def test_clawback_expect_fail_prints_code_and_error(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(
        noclaw_issuer_seed=_SecretValue("sN"), noclaw_issuer_address="rN",
        noclaw_currency="NOC",
    )
    calls = patch_action(monkeypatch, "clawback_tokens", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_clawback_expect_fail)
    assert calls[0][0][3:5] == ("NOC", "10")  # currency from context, default amount
    assert "Expected failure: tecNO_PERMISSION" in rig.out
    assert "Error: simulated tecNO_PERMISSION" in rig.out
    assert ctx["failed_txids"] == [
        {"result_code": "tecNO_PERMISSION", "error": "simulated tecNO_PERMISSION"}
    ]


async def test_clawback_expect_fail_is_acknowledged(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(noclaw_issuer_seed=_SecretValue("sN"), noclaw_issuer_address="rN")
    patch_action(monkeypatch, "clawback_tokens", fail_result("tecNO_PERMISSION"))
    await rig.run(handlers.handle_clawback_expect_fail)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]


# ── NFT marketplace ───────────────────────────────────────────────────

NFT_ID = "NFTID" + "0" * 59


async def _nft_rig(transfer_fee: int = 0) -> Rig:
    """The creator IS the dry-run wallet, so its NFT issuer matches state."""
    rig = Rig(address=_DRY_RUN_WALLET_ADDRESS)
    await rig.fund()
    mint = await rig.transport.submit_nft_mint(
        SEED, "ipfs://item", taxon=0, transfer_fee=transfer_fee, transferable=True,
        mutable=True,
    )
    assert mint.success
    rig.context["nft_id"] = mint.nft_id
    await rig.run(handlers.handle_create_buyer_wallet)
    rig.clear()
    rig.state.tx_index.clear()
    rig.context.pop("txids", None)
    return rig


async def test_create_buyer_wallet() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_buyer_wallet)
    assert isinstance(ctx["buyer_seed"], _SecretValue)
    assert "Buyer funded!" in rig.out


async def test_first_sale_list_verify_accept_verify() -> None:
    rig = await _nft_rig()
    ctx = await rig.run(handlers.handle_list_nft_sell_offer, amount="10")
    assert ctx["nft_sell_offer"]
    assert ctx["nft_offer_price"] == "10" and ctx["nft_offer_seller_role"] == "creator"
    assert "Sell offer listed!" in rig.out

    await rig.run(handlers.handle_verify_nft_offer, expected_min="1")
    assert "1 open sell offer(s) on the book." in rig.out
    assert rig.verdicts("verify_nft_offer")[-1]["passed"] is True
    assert len(ctx["last_nft_offers"]) == 1

    await rig.run(handlers.handle_accept_nft_offer)
    assert "Trade settled" in rig.out
    assert ctx["nft_buyer_address"] == ctx["buyer_address"]
    assert ctx["nft_prev_owner"] == _DRY_RUN_WALLET_ADDRESS
    assert "nft_sell_offer" not in ctx  # offer consumed
    assert ctx["nft_issuer_balance_before"] != ctx["nft_issuer_balance_after"]

    rig.clear()
    await rig.run(handlers.handle_verify_nft_trade)
    assert rig.verdicts("verify_nft_trade")[-1]["passed"] is True
    assert "No royalty on this hop" in rig.out and "SELLER" in rig.out
    assert "NFT trade verified on-ledger." in rig.out
    assert all(r.success for r in rig.records)


async def test_resale_to_creator_enforces_the_royalty() -> None:
    rig = await _nft_rig(transfer_fee=5000)
    await rig.run(handlers.handle_list_nft_sell_offer, amount="10")
    await rig.run(handlers.handle_accept_nft_offer)
    rig.context["nft_transfer_fee"] = 5000

    await rig.run(handlers.handle_list_nft_sell_offer, amount="20", seller="buyer")
    assert rig.context["nft_offer_seller_role"] == "buyer"
    await rig.run(handlers.handle_accept_nft_offer, buyer="creator")
    assert rig.context["nft_prev_owner"] == rig.context["buyer_address"]
    assert rig.context["nft_buyer_address"] == _DRY_RUN_WALLET_ADDRESS

    rig.clear()
    await rig.run(handlers.handle_verify_nft_trade)
    assert "Royalty (TransferFee) enforced on this resale: 1 XRP" in rig.out
    assert "of the 20 XRP price" in " ".join(rig.out.split())
    assert rig.verdicts("verify_nft_trade")[-1]["passed"] is True


async def test_list_offer_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_list_nft_sell_offer)
    assert "No NFTokenID in context" in rig.out

    rig.context["nft_id"] = NFT_ID
    await rig.run(handlers.handle_list_nft_sell_offer, seller="buyer")
    assert "Missing seller wallet" in rig.out
    assert rig.records == []

    patch_action(monkeypatch, "create_nft_offer", fail_result("tecNO_ENTRY"))
    ctx = await rig.run(handlers.handle_list_nft_sell_offer)
    assert "Sell offer failed" in rig.out
    assert "nft_sell_offer" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_list_offer_without_offer_index_keeps_going(monkeypatch) -> None:
    rig = Rig()
    rig.context["nft_id"] = NFT_ID
    calls = patch_action(monkeypatch, "create_nft_offer", ok_result("TXLIST"))
    ctx = await rig.run(handlers.handle_list_nft_sell_offer, amount="9")
    assert "nft_sell_offer" not in ctx
    assert ctx["nft_offer_price"] == "9"
    assert calls[0][1]["sell"] is True


async def test_verify_nft_offer_variants(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_nft_offer)
    assert "No NFTokenID in context" in rig.out
    assert rig.verdicts() == []

    rig.context["nft_id"] = NFT_ID
    await rig.run(handlers.handle_verify_nft_offer)
    assert "No open sell offers for this NFT." in rig.out
    assert rig.verdicts("verify_nft_offer")[-1]["passed"] is True  # observation-only

    await rig.run(handlers.handle_verify_nft_offer, expected_min="2")
    assert "expected_min=2 open sell offer(s), observed 0" in rig.out
    assert rig.verdicts("verify_nft_offer")[-1]["passed"] is False

    await rig.run(handlers.handle_verify_nft_offer, expected_min="two")
    v = rig.verdicts("verify_nft_offer")[-1]
    assert v["passed"] is False  # a malformed module arg fails the step
    assert v["failures"] == ["invalid expected_min: 'two' (expected an integer)"]


async def test_verify_nft_offer_malformed_bound_is_explained_to_the_learner() -> None:
    rig = Rig()
    rig.context["nft_id"] = NFT_ID
    await rig.run(handlers.handle_verify_nft_offer, expected_min="two")
    assert "invalid expected_min" in rig.out


async def test_verify_nft_offer_lists_each_offer(monkeypatch) -> None:
    rig = Rig()
    rig.context["nft_id"] = NFT_ID
    offers = [
        NFTOfferInfo(
            offer_index="A" * 64, nft_id=NFT_ID, amount="10", owner="rO",
            destination="", is_sell=True,
        ),
        NFTOfferInfo(
            offer_index="B" * 64, nft_id=NFT_ID, amount="20", owner="rO",
            destination="", is_sell=True,
        ),
    ]
    patch_action(monkeypatch, "get_nft_offers", offers)
    await rig.run(handlers.handle_verify_nft_offer, expected_min="2")
    assert "Sell offer: 10" in rig.out and "Sell offer: 20" in rig.out
    assert "2 open sell offer(s) on the book." in rig.out
    assert rig.verdicts("verify_nft_offer")[-1]["passed"] is True


async def test_accept_offer_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_accept_nft_offer)
    assert "No sell offer in context" in rig.out

    rig.context["nft_sell_offer"] = "OFFER1"
    await rig.run(handlers.handle_accept_nft_offer)
    assert "Missing buyer wallet" in rig.out
    assert rig.records == []

    rig.context["buyer_seed"] = _SecretValue("sBuy")
    patch_action(monkeypatch, "accept_nft_offer", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_accept_nft_offer)
    assert "Accept failed" in rig.out
    assert ctx["nft_sell_offer"] == "OFFER1"  # not consumed on failure
    assert "nft_buyer_address" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_accept_nonexistent_offer_expected_failure() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_accept_nft_offer_expect_fail)
    assert "Expected failure:" in rig.out and "tecOBJECT_NOT_FOUND" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecOBJECT_NOT_FOUND"
    assert [r.success for r in rig.records] == [False]  # 2.6.2: the rejection is recorded
    assert rig.acknowledged == [rig.records[0].txid]  # ...and acknowledged as the lesson


async def test_accept_nonexistent_offer_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "accept_nft_offer", ok_result("TXACCEPT"))
    await rig.run(handlers.handle_accept_nft_offer_expect_fail)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXACCEPT", True)]


async def test_verify_trade_without_a_trade_fails_verification() -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_nft_trade)
    assert "No completed trade in context" in rig.out
    assert rig.verdicts("verify_nft_trade")[0]["passed"] is False


def _trade_ctx(rig: Rig, **extra) -> None:
    rig.context.update(
        nft_id=NFT_ID, nft_buyer_address="rBuyer", nft_prev_owner="rSeller",
        nft_issuer_balance_before="100", nft_issuer_balance_after="110",
        **extra,
    )


async def test_trade_royalty_third_party_issuer_gets_paid(monkeypatch) -> None:
    rig = Rig()
    _trade_ctx(rig)
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=True, checks=["owner moved"], failures=[]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert "Royalty (TransferFee) paid to issuer: +10 XRP" in rig.out
    assert "owner moved" in rig.out


async def test_trade_no_royalty_when_third_party_issuer_balance_flat(monkeypatch) -> None:
    rig = Rig()
    _trade_ctx(rig)
    rig.context["nft_issuer_balance_after"] = "100"
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=True, checks=[], failures=[]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert "No royalty on this hop" in rig.out
    assert "Royalty (TransferFee) paid" not in rig.out


async def test_trade_unparseable_balances_do_not_crash(monkeypatch) -> None:
    rig = Rig()
    _trade_ctx(rig)
    rig.context["nft_issuer_balance_after"] = "n/a"
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=True, checks=[], failures=[]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert "No royalty on this hop" in rig.out  # delta fell back to 0
    assert rig.verdicts("verify_nft_trade")[-1]["passed"] is True


@pytest.mark.parametrize(
    ("extra", "expect"),
    [
        ({"nft_transfer_fee": 5000, "nft_offer_price": "200"}, "enforced on this resale: 10"),
        ({"nft_transfer_fee": 5000, "nft_offer_price": "oops"}, "no TransferFee was recorded"),
        ({}, "no TransferFee was recorded"),
    ],
)
async def test_trade_resale_with_issuer_as_buyer(monkeypatch, extra, expect) -> None:
    rig = Rig()
    _trade_ctx(rig, **extra)
    rig.context["nft_buyer_address"] = TREASURY  # the issuer buys it back
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=True, checks=[], failures=[]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert expect in " ".join(rig.out.split())


async def test_trade_failure_is_reported(monkeypatch) -> None:
    rig = Rig()
    _trade_ctx(rig)
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=False, checks=[], failures=["still with seller"]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert "still with seller" in rig.out
    assert "NFT trade verified on-ledger." not in rig.out
    assert rig.verdicts("verify_nft_trade")[-1] == {
        "action": "verify_nft_trade", "passed": False, "failures": ["still with seller"],
    }


async def test_trade_without_balance_observations_skips_royalty_note(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(nft_id=NFT_ID, nft_buyer_address="rB", nft_prev_owner="rS")
    patch_action(
        monkeypatch, "verify_nft_owned_by",
        NFTOwnershipResult(transferred=True, checks=[], failures=[]),
    )
    await rig.run(handlers.handle_verify_nft_trade)
    assert "royalty" not in rig.out.lower()


# ── dynamic NFTs ──────────────────────────────────────────────────────


async def test_modify_nft_level_up_and_verify_on_dry_run() -> None:
    rig = await _nft_rig()
    ctx = await rig.run(handlers.handle_modify_nft, uri="ipfs://item-lv2")
    assert ctx["nft_modified_uri"] == "ipfs://item-lv2"
    assert "item leveled up" in rig.out
    assert [r.success for r in rig.records] == [True]

    await rig.run(handlers.handle_verify_nft_modified)
    assert rig.verdicts("verify_nft_modified")[-1]["passed"] is True
    assert "Dynamic NFT verified" in rig.out


async def test_modify_nft_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_modify_nft)
    assert "No wallet in context" in rig.out

    rig = Rig()
    await rig.run(handlers.handle_modify_nft)
    assert "No NFTokenID in context" in rig.out

    patch_action(monkeypatch, "modify_nft", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_modify_nft, nftoken_id=NFT_ID)
    assert "NFTokenModify failed" in rig.out
    assert "nft_modified_uri" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_modify_nft_expect_fail_on_dry_run() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_modify_nft_expect_fail)
    assert "Expected failure:" in rig.out
    assert ctx["failed_txids"][0]["result_code"]
    assert len(rig.failed_records) == 1  # 2.6.2: the rejection is recorded
    assert rig.acknowledged == [rig.failed_records[0].txid]  # ...and acknowledged


async def test_modify_nft_expect_fail_prerequisites_and_branches(monkeypatch) -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_modify_nft_expect_fail)
    assert "No wallet in context" in rig.out

    rig = Rig()
    rig.transport.set_fail_next()  # the setup mint fails
    ctx = await rig.run(handlers.handle_modify_nft_expect_fail)
    assert "Setup mint note:" in rig.out
    assert "failed_txids" not in ctx

    rig = Rig()
    patch_action(monkeypatch, "modify_nft", ok_result("TXMOD"))
    await rig.run(handlers.handle_modify_nft_expect_fail)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXMOD", True)]


async def test_verify_nft_modified_variants(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_nft_modified)
    assert "No modified NFT in context" in rig.out
    assert rig.verdicts("verify_nft_modified")[0]["passed"] is False

    rig.context.update(nft_id=NFT_ID, nft_modified_uri="ipfs://x")
    res = NFTModifiedResult(changed=False, nft=None, checks=[], failures=["URI unchanged"])
    patch_action(monkeypatch, "verify_nft_modified", res)
    await rig.run(handlers.handle_verify_nft_modified)
    assert "URI unchanged" in rig.out
    assert "Dynamic NFT verified" not in rig.out
    assert rig.verdicts("verify_nft_modified")[-1]["passed"] is False
