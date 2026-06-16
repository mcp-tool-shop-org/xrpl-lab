"""v2.0.0 game-economy CONTROL tests (f2-engine domain).

v1.8.0 taught asset CREATION; v2.0.0 teaches CONTROL + TRADE. This module pins
three KB-verified, mainnet-live capabilities fully offline against
``DryRunTransport`` (no network, no live ``xrpl`` client), plus source/signature
inspection of the testnet transport:

  1. Clawback (XLS-39) — issuer recall. Enable-before-issue ordering, exact
     balance debit, and the clawback-without-the-flag tec failure.
  2. NFT marketplace (XLS-20) — list / read / accept offers, atomic ownership
     transfer, protocol-enforced TransferFee royalty on RESALE (not first
     sale), and the accept-nonexistent-offer tec failure.
  3. Dynamic NFTs (XLS-46) — mint mutable (tfMutable), NFTokenModify the URI on
     the SAME NFTokenID, and the modify-non-mutable tec failure.

Financial math (clawback amounts, royalty splits) is asserted Decimal-exact.
dry-run ↔ testnet PARITY is pinned by signature + result-code checks: every
dry-run error code is a real XRPL token that ``explain_result_code`` teaches,
and every new testnet signing method calls ``_network_guard()`` before
``Wallet.from_seed``. The mainnet-refusal guarantee itself is pinned by
``tests/test_network_safety.py`` (reflection completeness gate).
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from xrpl_lab.actions.nft import (
    accept_nft_offer,
    create_nft_offer,
    get_nft_offers,
    mint_nft,
    modify_nft,
    verify_nft_modified,
    verify_nft_owned_by,
)
from xrpl_lab.actions.trust_line import (
    clawback_tokens,
    enable_clawback,
    verify_clawback,
)
from xrpl_lab.doctor import explain_result_code
from xrpl_lab.transport.base import NFTOfferInfo, Transport, TrustLineInfo
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

ISSUER = _DRY_RUN_WALLET_ADDRESS
HOLDER = "rHolderXXXXXXXXXXXXXXXXXXXXXXX"
BUYER = "rBuyerXXXXXXXXXXXXXXXXXXXXXXXX"
ISSUER_SEED = "sISSUER"
BUYER_SEED = "sBUYER"


@pytest.fixture
def transport() -> DryRunTransport:
    return DryRunTransport()


# ════════════════════════════════════════════════════════════════════════
# 1. CLAWBACK (XLS-39) — issuer recall
# ════════════════════════════════════════════════════════════════════════


class TestClawbackHappyPath:
    """Enable clawback, issue, recall an exact amount, verify the exact debit."""

    @pytest.mark.asyncio
    async def test_enable_then_clawback_debits_exactly(self, transport):
        # Holder holds 100 GOLD from the issuer.
        transport._trust_lines[HOLDER] = [
            TrustLineInfo(account=HOLDER, peer=ISSUER, currency="GOLD",
                          balance="100", limit="1000")
        ]
        # Enable clawback on the issuer FIRST.
        en = await enable_clawback(transport, ISSUER_SEED)
        assert en.success

        # Claw back 30 of 100.
        cb = await clawback_tokens(transport, ISSUER_SEED, HOLDER, "GOLD", "30")
        assert cb.success
        assert cb.result_code == "tesSUCCESS"

        lines = await transport.get_trust_lines(HOLDER)
        assert lines[0].balance == "70", "holder must drop by exactly 30 (100 -> 70)"

    @pytest.mark.asyncio
    async def test_verify_clawback_confirms_exact_delta(self, transport):
        transport._trust_lines[HOLDER] = [
            TrustLineInfo(account=HOLDER, peer=ISSUER, currency="GOLD",
                          balance="100", limit="1000")
        ]
        await enable_clawback(transport, ISSUER_SEED)
        await clawback_tokens(transport, ISSUER_SEED, HOLDER, "GOLD", "30")

        result = await verify_clawback(
            transport, HOLDER, "GOLD", ISSUER,
            balance_before="100", clawed_amount="30",
        )
        assert result.passed
        assert result.after == "70"
        assert result.expected_after == "70"

    @pytest.mark.asyncio
    async def test_clawback_clamped_to_balance(self, transport):
        """Clawing more than the holder holds debits only what they have (clamp)."""
        transport._trust_lines[HOLDER] = [
            TrustLineInfo(account=HOLDER, peer=ISSUER, currency="GOLD",
                          balance="40", limit="1000")
        ]
        await enable_clawback(transport, ISSUER_SEED)
        cb = await clawback_tokens(transport, ISSUER_SEED, HOLDER, "GOLD", "999")
        assert cb.success
        lines = await transport.get_trust_lines(HOLDER)
        assert lines[0].balance == "0", "clawback clamps to the holder's balance"

        # And the verifier accepts the clamped floor (expected_after >= 0).
        result = await verify_clawback(
            transport, HOLDER, "GOLD", ISSUER,
            balance_before="40", clawed_amount="999",
        )
        assert result.passed
        assert result.expected_after == "0"

    @pytest.mark.asyncio
    async def test_fractional_clawback_decimal_exact(self, transport):
        """Decimal-exact fractional debit (no float drift)."""
        transport._trust_lines[HOLDER] = [
            TrustLineInfo(account=HOLDER, peer=ISSUER, currency="GOLD",
                          balance="100.5", limit="1000")
        ]
        await enable_clawback(transport, ISSUER_SEED)
        cb = await clawback_tokens(transport, ISSUER_SEED, HOLDER, "GOLD", "0.3")
        assert cb.success
        lines = await transport.get_trust_lines(HOLDER)
        assert Decimal(lines[0].balance) == Decimal("100.2")


class TestClawbackFailurePaths:
    """The flag is load-bearing: no flag, no recall."""

    @pytest.mark.asyncio
    async def test_clawback_without_flag_is_refused(self, transport):
        transport._trust_lines[HOLDER] = [
            TrustLineInfo(account=HOLDER, peer=ISSUER, currency="GOLD",
                          balance="100", limit="1000")
        ]
        # NO enable_clawback call.
        cb = await clawback_tokens(transport, ISSUER_SEED, HOLDER, "GOLD", "30")
        assert cb.success is False
        assert cb.result_code == "tecNO_PERMISSION"
        assert "asfAllowTrustLineClawback" in cb.error
        # The teaching seam recognizes the code.
        info = explain_result_code(cb.result_code)
        assert info["meaning"] and info["action"]
        # Balance untouched.
        lines = await transport.get_trust_lines(HOLDER)
        assert lines[0].balance == "100"

    @pytest.mark.asyncio
    async def test_clawback_no_trust_line_is_refused(self, transport):
        await enable_clawback(transport, ISSUER_SEED)
        cb = await clawback_tokens(transport, ISSUER_SEED, "rNoLineXXXXXXXXXXXXXX", "GOLD", "5")
        assert cb.success is False
        assert cb.result_code == "tecNO_LINE"


# ════════════════════════════════════════════════════════════════════════
# 2. NFT MARKETPLACE (XLS-20) — trade + enforced royalty
# ════════════════════════════════════════════════════════════════════════


class TestNFTMarketplaceHappyPath:
    @pytest.mark.asyncio
    async def test_list_read_accept_transfers_ownership(self, transport):
        # Creator mints a transferable NFT with a 5% royalty.
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://item.json",
            taxon=11, transfer_fee=5000, transferable=True,
        )
        assert mint.success and mint.nft_id

        # List a directed sell offer to the buyer.
        offer = await create_nft_offer(
            transport, ISSUER_SEED, mint.nft_id, "100",
            sell=True, destination=BUYER, owner=ISSUER,
        )
        assert offer.success and offer.nft_offer_index

        # Read it back on-ledger.
        offers = await get_nft_offers(transport, mint.nft_id, sell=True)
        assert len(offers) == 1
        assert offers[0].is_sell is True
        assert offers[0].amount == "100"

        # Buyer accepts → ownership moves.
        accept = await accept_nft_offer(transport, BUYER_SEED, sell_offer=offer.nft_offer_index)
        assert accept.success

        ownership = await verify_nft_owned_by(
            transport, BUYER, mint.nft_id, previous_owner=ISSUER
        )
        assert ownership.passed

    @pytest.mark.asyncio
    async def test_offer_consumed_after_accept(self, transport):
        mint = await mint_nft(transport, ISSUER_SEED, "ipfs://i.json", transfer_fee=5000)
        offer = await create_nft_offer(
            transport, ISSUER_SEED, mint.nft_id, "100",
            sell=True, destination=BUYER, owner=ISSUER,
        )
        await accept_nft_offer(transport, BUYER_SEED, sell_offer=offer.nft_offer_index)
        remaining = await get_nft_offers(transport, mint.nft_id, sell=True)
        assert remaining == [], "an accepted offer must leave the book"


class TestNFTRoyaltyMath:
    """The TransferFee royalty is Decimal-exact and fires only on a RESALE."""

    @pytest.mark.asyncio
    async def test_first_sale_from_issuer_pays_no_royalty(self, transport):
        # Issuer == seller on the first sale → XLS-20 charges no fee.
        transport._balances[BUYER] = 1_000_000_000  # 1000 XRP
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://i.json", transfer_fee=5000, transferable=True
        )
        issuer_before = transport._balances.get(ISSUER, 0)
        offer = await create_nft_offer(
            transport, ISSUER_SEED, mint.nft_id, "100",
            sell=True, destination=BUYER, owner=ISSUER,
        )
        await accept_nft_offer(transport, BUYER_SEED, sell_offer=offer.nft_offer_index)
        # Seller (==issuer) received the FULL 100 XRP; royalty is 0 on first sale.
        issuer_after = transport._balances.get(ISSUER, 0)
        assert issuer_after - issuer_before == 100_000_000

    @pytest.mark.asyncio
    async def test_resale_pays_exact_royalty_to_issuer(self, transport):
        """Reseller (≠ issuer) pays the 5% fee; issuer nets exactly that."""
        # Mint, first-sell to BUYER so BUYER holds it and is NOT the issuer.
        transport._balances[BUYER] = 1_000_000_000
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://i.json", transfer_fee=5000, transferable=True
        )
        first = await create_nft_offer(
            transport, ISSUER_SEED, mint.nft_id, "100",
            sell=True, destination=BUYER, owner=ISSUER,
        )
        await accept_nft_offer(transport, BUYER_SEED, sell_offer=first.nft_offer_index)
        assert any(n.nft_id == mint.nft_id for n in await transport.get_account_nfts(BUYER))

        # RESALE: BUYER lists, directed back to the issuer (a third actor would
        # be cleaner but the issuer is a valid distinct-from-seller buyer here).
        issuer_before = transport._balances.get(ISSUER, 0)
        resale = await create_nft_offer(
            transport, BUYER_SEED, mint.nft_id, "200",
            sell=True, destination=ISSUER, owner=BUYER,
        )
        assert resale.success
        # Issuer buys it back.
        accept = await accept_nft_offer(transport, ISSUER_SEED, sell_offer=resale.nft_offer_index)
        assert accept.success

        # Royalty = 200 XRP * 5000/100000 = 10 XRP → to the issuer.
        issuer_after = transport._balances.get(ISSUER, 0)
        # Issuer paid 200 (as buyer) and received 10 royalty (as issuer): net -190.
        delta = issuer_after - issuer_before
        assert delta == -190_000_000, (
            f"issuer net should be -200 + 10 royalty = -190 XRP, got {delta} drops"
        )
        # Reseller (BUYER) netted 200 - 10 = 190.
        # (We assert the royalty itself is exactly 10 XRP via the math identity.)
        royalty = Decimal("200") * Decimal("5000") / Decimal("100000")
        assert royalty == Decimal("10.000")

    @pytest.mark.asyncio
    async def test_royalty_fractional_decimal_exact(self, transport):
        """A fractional-royalty resale rounds to drops, Decimal-exact."""
        transport._balances[BUYER] = 10_000_000_000
        transport._balances[ISSUER] = 10_000_000_000
        # 2.5% royalty on a 33 XRP resale = 0.825 XRP.
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://i.json", transfer_fee=2500, transferable=True
        )
        first = await create_nft_offer(
            transport, ISSUER_SEED, mint.nft_id, "1",
            sell=True, destination=BUYER, owner=ISSUER,
        )
        await accept_nft_offer(transport, BUYER_SEED, sell_offer=first.nft_offer_index)
        issuer_before = transport._balances.get(ISSUER, 0)
        resale = await create_nft_offer(
            transport, BUYER_SEED, mint.nft_id, "33",
            sell=True, destination=ISSUER, owner=BUYER,
        )
        await accept_nft_offer(transport, ISSUER_SEED, sell_offer=resale.nft_offer_index)
        issuer_after = transport._balances.get(ISSUER, 0)
        # Issuer: -33 (buyer) + 0.825 (royalty) = -32.175 XRP = -32_175_000 drops.
        assert issuer_after - issuer_before == -32_175_000


class TestNFTMarketplaceFailurePaths:
    @pytest.mark.asyncio
    async def test_accept_nonexistent_offer_is_refused(self, transport):
        accept = await accept_nft_offer(transport, BUYER_SEED, sell_offer="0" * 64)
        assert accept.success is False
        assert accept.result_code == "tecOBJECT_NOT_FOUND"
        info = explain_result_code(accept.result_code)
        assert info["meaning"] and info["action"]

    @pytest.mark.asyncio
    async def test_sell_offer_for_unowned_nft_is_refused(self, transport):
        offer = await create_nft_offer(
            transport, ISSUER_SEED, "DEADBEEF" * 8, "100", sell=True, owner=ISSUER
        )
        assert offer.success is False
        assert offer.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_royalty_on_nontransferable_mint_is_refused(self, transport):
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://i.json", transfer_fee=5000, transferable=False
        )
        assert mint.success is False
        assert mint.result_code == "temBAD_NFTOKEN_TRANSFER_FEE"


# ════════════════════════════════════════════════════════════════════════
# 3. DYNAMIC NFTs (XLS-46) — leveling items via NFTokenModify
# ════════════════════════════════════════════════════════════════════════


class TestDynamicNFTHappyPath:
    @pytest.mark.asyncio
    async def test_mutable_mint_then_modify_same_id(self, transport):
        mint = await mint_nft(
            transport, ISSUER_SEED, "ipfs://blade-l1.json", taxon=21, mutable=True
        )
        assert mint.success and mint.nft_id
        # tfMutable (0x10) set on the minted NFT.
        nfts = await transport.get_account_nfts(ISSUER)
        minted = next(n for n in nfts if n.nft_id == mint.nft_id)
        assert minted.flags & 0x10, "tfMutable must be set"

        mod = await modify_nft(transport, ISSUER_SEED, mint.nft_id, "ipfs://blade-l2.json")
        assert mod.success

        result = await verify_nft_modified(
            transport, ISSUER, mint.nft_id, "ipfs://blade-l2.json"
        )
        assert result.passed
        assert result.nft.nft_id == mint.nft_id, "NFTokenID must be unchanged"
        assert result.nft.uri == "ipfs://blade-l2.json"

    @pytest.mark.asyncio
    async def test_modify_preserves_identity_across_levels(self, transport):
        mint = await mint_nft(transport, ISSUER_SEED, "ipfs://l1.json", mutable=True)
        await modify_nft(transport, ISSUER_SEED, mint.nft_id, "ipfs://l2.json")
        await modify_nft(transport, ISSUER_SEED, mint.nft_id, "ipfs://l3.json")
        nfts = await transport.get_account_nfts(ISSUER)
        ids = [n.nft_id for n in nfts]
        assert ids.count(mint.nft_id) == 1, "still one object — identity preserved"
        match = next(n for n in nfts if n.nft_id == mint.nft_id)
        assert match.uri == "ipfs://l3.json"


class TestDynamicNFTFailurePaths:
    @pytest.mark.asyncio
    async def test_modify_nonmutable_is_refused(self, transport):
        mint = await mint_nft(transport, ISSUER_SEED, "ipfs://fixed.json", mutable=False)
        assert mint.success
        mod = await modify_nft(transport, ISSUER_SEED, mint.nft_id, "ipfs://changed.json")
        assert mod.success is False
        assert mod.result_code == "tecNO_PERMISSION"
        assert "not mutable" in mod.error.lower()
        info = explain_result_code(mod.result_code)
        assert info["meaning"] and info["action"]
        # URI unchanged.
        nfts = await transport.get_account_nfts(ISSUER)
        match = next(n for n in nfts if n.nft_id == mint.nft_id)
        assert match.uri == "ipfs://fixed.json"

    @pytest.mark.asyncio
    async def test_modify_nonexistent_nft_is_refused(self, transport):
        mod = await modify_nft(transport, ISSUER_SEED, "CAFE" * 16, "ipfs://x.json")
        assert mod.success is False
        assert mod.result_code == "tecNO_ENTRY"


# ════════════════════════════════════════════════════════════════════════
# dry-run ↔ testnet PARITY
# ════════════════════════════════════════════════════════════════════════


class TestTransportParity:
    """New methods exist with matching signatures on both transports; dry-run
    error codes are real XRPL tokens the teaching seam recognizes; and every
    new testnet signing method guards the network before loading the wallet."""

    _NEW_SIGNING_METHODS = [
        "submit_clawback",
        "submit_account_set_clawback",
        "submit_nft_create_offer",
        "submit_nft_accept_offer",
        "submit_nft_modify",
    ]
    _NEW_READ_METHODS = ["get_nft_offers"]

    @pytest.mark.parametrize("method", _NEW_SIGNING_METHODS + _NEW_READ_METHODS)
    def test_method_on_base_and_both_transports(self, method):
        assert hasattr(Transport, method), f"{method} missing from base contract"
        assert hasattr(DryRunTransport, method)
        assert hasattr(XRPLTestnetTransport, method)

    @pytest.mark.parametrize("method", _NEW_SIGNING_METHODS + _NEW_READ_METHODS)
    def test_signatures_match_across_transports(self, method):
        dry_sig = inspect.signature(getattr(DryRunTransport, method))
        net_sig = inspect.signature(getattr(XRPLTestnetTransport, method))
        assert list(dry_sig.parameters) == list(net_sig.parameters), (
            f"{method} parameter list differs between transports"
        )

    @pytest.mark.parametrize(
        "code",
        [
            "tecNO_PERMISSION", "tecNO_ENTRY", "tecOBJECT_NOT_FOUND",
            "tecNO_LINE", "temBAD_NFTOKEN_TRANSFER_FEE", "temMALFORMED",
        ],
    )
    def test_dry_run_error_codes_are_real_and_explained(self, code):
        info = explain_result_code(code)
        assert info["meaning"], f"{code} has no meaning in the doctor"
        assert info["action"], f"{code} has no action guidance in the doctor"

    @pytest.mark.parametrize("method", _NEW_SIGNING_METHODS)
    def test_testnet_methods_network_guard_before_wallet(self, method):
        src = inspect.getsource(getattr(XRPLTestnetTransport, method))
        guard_pos = src.find("_network_guard")
        wallet_pos = src.find("Wallet.from_seed")
        assert guard_pos != -1, f"{method} must call _network_guard()"
        assert wallet_pos != -1, f"{method} must build a wallet"
        assert guard_pos < wallet_pos, (
            f"{method}: _network_guard() must run BEFORE Wallet.from_seed"
        )

    def test_clawback_amount_issuer_carries_holder_on_testnet(self):
        """XLS-39 quirk pinned at the source level: the testnet Clawback builds
        IssuedCurrencyAmount(issuer=holder_address), not the issuer."""
        src = inspect.getsource(XRPLTestnetTransport.submit_clawback)
        assert "issuer=holder_address" in src, (
            "Clawback Amount.issuer must carry the HOLDER address (XLS-39 quirk)"
        )

    def test_nft_offer_info_dataclass_shape(self):
        o = NFTOfferInfo(offer_index="abc", nft_id="def", amount="100",
                         owner="rX", is_sell=True)
        assert o.offer_index == "abc" and o.is_sell is True


class TestMintMutableParity:
    """submit_nft_mint gained a ``mutable`` param on both transports."""

    @pytest.mark.parametrize("cls", [DryRunTransport, XRPLTestnetTransport])
    def test_mint_signature_has_mutable(self, cls):
        params = list(inspect.signature(cls.submit_nft_mint).parameters)
        assert "mutable" in params, f"{cls.__name__}.submit_nft_mint missing 'mutable'"

    def test_testnet_mint_sets_mutable_flag(self):
        src = inspect.getsource(XRPLTestnetTransport.submit_nft_mint)
        assert "TF_MUTABLE" in src, "testnet mint must set tfMutable when mutable=True"
        assert "TF_TRANSFERABLE" in src
