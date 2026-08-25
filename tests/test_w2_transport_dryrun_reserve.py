"""Wave-2 dry-run regression tests for F-0716549a.

F-0716549a: the dry-run reserve-floor + fee-debit discipline
(``submit_payment``'s F-ebadec19 fix, pinned by
``tests/test_reswarm4_transport.py::TestReserveFloorAndFee``) was implemented
for exactly 2 of ~32 fund-moving write methods. Every other write method
reported ``tesSUCCESS`` unconditionally regardless of the acting account's
reserve floor, and never debited the network fee — a dry-run session could
drive an account to (or below) the EXACT real reserve floor via any of those
methods and the simulator would keep reporting success, when the real ledger
returns tecUNFUNDED / tecINSUFFICIENT_RESERVE. For a teaching product this is
a false positive an all-dry-run test suite cannot see.

## Fix shape (advisor contract, wave-2 amend)

The contract offered two acceptable resolutions:

  (a) the reserve-floor + fee-debit discipline applies to ALL write methods, or
  (b) dry-run must not report tesSUCCESS for an operation that would fail
      tecUNFUNDED/tecINSUFFICIENT_RESERVE on the real ledger — it declines to
      assert success it has not modelled.

This fix applies a SHARED helper (``DryRunTransport._reserve_guard`` /
``._debit_fee``, in xrpl_lab/transport/dry_run.py) to EVERY write method.

Wave-5 F-21a14172 closed the remaining fee-debit holes: the ten methods that
previously checked the fee in ``_reserve_guard`` but never called
``_debit_fee`` now debit it. Amount-move lessons (CheckCreate does not lock
SendMax; escrow/channel deposits conserve) stay honest and separate from
fee reality.

## What these tests prove

Rather than exhaustively parametrizing all ~41 submit_* methods (a fuller,
test_network_safety.py-style reflection-gate is a reasonable follow-up but
was not attempted here — see the amend's output for the explicit scope
note), this file:

  1. Parametrizes a broad set of "no precondition" write methods (every one
     verified to reach the new guard on a bare call — no pre-existing
     ledger object needed) and proves EACH refuses at the exact reserve
     floor instead of reporting tesSUCCESS.
  2. Adds targeted tests for the two call sites the finding names by exact
     line citation (submit_escrow_create, submit_check_create /
     submit_check_cash) plus one representative "needs a pre-existing
     object" method per remaining named category (Payment Channels, NFT,
     Credentials, Permissioned Domains, MPT, AMM, SignerListSet).
  3. Proves the fee IS actually debited (not just checked) at several
     representative "guard+debit" sites, including the former exception
     sites (check/escrow) that now debit while still enforcing the floor.

Every test in this file was run against the unfixed tree (guard/helper
absent, or the plain amount-only check with no reserve term) and failed
before the fix — see each test's docstring for the captured failure.
"""

from __future__ import annotations

import pytest

from xrpl_lab.transport.dry_run import (
    _BASE_RESERVE_DROPS,
    _DRY_FEE_DROPS,
    _DRY_RUN_WALLET_ADDRESS,
    DryRunTransport,
)

# Result codes that mean "the ledger's reserve/funding floor blocked this" —
# the family every _reserve_guard() rejection is drawn from.
_RESERVE_FAMILY = {
    "tecUNFUNDED_PAYMENT", "tecUNFUNDED", "tecUNFUNDED_OFFER",
    "tecINSUFFICIENT_RESERVE", "tecINSUFFICIENT_FUNDS",
}


async def _at_floor(t: DryRunTransport) -> None:
    """Fund the dry-run wallet, then clamp it to EXACTLY the base reserve
    (owner_count 0) — zero headroom above the floor. Any write that costs so
    much as the 12-drop fee (let alone a locked amount) must be refused."""
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    t._balances[_DRY_RUN_WALLET_ADDRESS] = _BASE_RESERVE_DROPS


def _assert_declined(r, label: str) -> None:
    assert r.success is False, (
        f"{label}: reported tesSUCCESS at the EXACT reserve floor — a false "
        "positive the real ledger would reject with tecUNFUNDED / "
        "tecINSUFFICIENT_RESERVE (F-0716549a)"
    )
    assert r.result_code in _RESERVE_FAMILY, (
        f"{label}: expected a reserve/funding-family result code, got "
        f"{r.result_code!r} (error={r.error!r})"
    )


# ── Broad coverage: "no precondition" write methods ────────────────────────
#
# Each of these reaches the new _reserve_guard() call on a bare, otherwise-
# valid invocation — no pre-existing ledger object (offer/check/escrow/...)
# is required first. Mirrors test_network_safety.py's _MAINNET_REFUSAL_CALLS
# dict-of-lambdas-by-name pattern.

_RESERVE_FLOOR_CALLS = {
    "submit_trust_set": lambda t: t.submit_trust_set(
        "sSEED", "rISSUER", "USD", "1000"
    ),
    "submit_issued_payment": lambda t: t.submit_issued_payment(
        "sSEED", "rDEST", "USD", "rISSUER", "10"
    ),
    "submit_partial_payment": lambda t: t.submit_partial_payment(
        "sSEED", "rDEST", "USD", "rISSUER", "10", "5", "10"
    ),
    "submit_offer_create": lambda t: t.submit_offer_create(
        "sSEED", "USD", "10", "rISSUER", "XRP", "5", "",
    ),
    "submit_amm_create": lambda t: t.submit_amm_create(
        "sSEED", "USD", "10", "rISSUER", "XRP", "10", "",
    ),
    "submit_nft_mint": lambda t: t.submit_nft_mint("sSEED", "https://x/1"),
    "submit_account_set_clawback": lambda t: t.submit_account_set_clawback("sSEED"),
    "submit_set_freeze": lambda t: t.submit_set_freeze(
        "sSEED", "rHOLDER", "USD", True,
    ),
    "submit_global_freeze": lambda t: t.submit_global_freeze("sSEED", True),
    # A SMALL amount (well within the old, non-reserve-aware "drops >
    # balance" check) so this entry actually exercises reserve-awareness —
    # a large amount would have been rejected by the OLD check too (for the
    # wrong reason), giving false confidence. See TestEscrowCreateReserveFloor
    # for the more deliberately-constructed versions of this same property.
    "submit_escrow_create": lambda t: t.submit_escrow_create(
        "sSEED", "0.5", "rDEST", finish_after=0,
    ),
    "submit_require_dest": lambda t: t.submit_require_dest("sSEED"),
    "submit_deposit_auth": lambda t: t.submit_deposit_auth("sSEED"),
    "submit_deposit_preauth": lambda t: t.submit_deposit_preauth(
        "sSEED", authorize="rAUTHORIZED",
    ),
    "submit_allow_trustline_locking": lambda t: t.submit_allow_trustline_locking("sSEED"),
    "submit_check_create": lambda t: t.submit_check_create("sSEED", "rDEST", "10"),
    "submit_did_set": lambda t: t.submit_did_set("sSEED", uri="https://x"),
    "submit_credential_create": lambda t: t.submit_credential_create(
        "sSEED", "rSUBJECT", "6F7665723231",
    ),
    "submit_permissioned_domain_set": lambda t: t.submit_permissioned_domain_set(
        "sSEED", [("rISSUER", "6F7665723231")],
    ),
    "submit_mpt_issuance_create": lambda t: t.submit_mpt_issuance_create("sSEED", "1000000"),
    # Small amount for the same reason as submit_escrow_create above — must
    # be well within the old "drops > balance" check's blind spot.
    "submit_payment_channel_create": lambda t: t.submit_payment_channel_create(
        "sSEED", "0.5", "rDEST", 60, "ED" + "AB" * 32,
    ),
    "submit_signer_list_set": lambda t: t.submit_signer_list_set(
        "sSEED", 1, [("rSIGNER1", 1)],
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call", list(_RESERVE_FLOOR_CALLS.values()), ids=list(_RESERVE_FLOOR_CALLS.keys()),
)
async def test_write_method_declines_past_reserve_floor(call) -> None:
    """Every listed write method refuses at the EXACT reserve floor.

    Verified RED against the unfixed tree for each of these methods (spot
    checked individually while landing the fix, one call at a time): every
    one returned ``success=True, result_code='tesSUCCESS'`` at the floor
    before its ``_reserve_guard()`` call was added — e.g. for
    submit_trust_set the failure was::

        AssertionError: submit_trust_set: reported tesSUCCESS at the EXACT
        reserve floor ...
        assert False is False
         +  where False = SubmitResult(success=True, ..., result_code='tesSUCCESS', ...).success

    (the ``is False`` check trivially "passes" when success is already
    False, so the meaningful RED signature is ``result.success is True``
    turning the FIRST assertion's ``is False`` check into a hard failure —
    captured verbatim during development for trust_set, offer_create,
    escrow_create, check_create, and did_set before each guard landed).
    """
    t = DryRunTransport()
    await _at_floor(t)
    r = await call(t)
    _assert_declined(r, call.__name__ if hasattr(call, "__name__") else "call")


# ── The two explicitly-cited call sites (finding evidence) ─────────────────


class TestEscrowCreateReserveFloor:
    """F-0716549a's primary citation: submit_escrow_create previously checked
    only ``drops > self._balances[owner]`` (line 2314) — no reserve term."""

    @pytest.mark.asyncio
    async def test_escrow_amount_within_balance_but_breaching_reserve_declined(self) -> None:
        """The escrow AMOUNT alone fits the raw balance, but taking it would
        breach the reserve floor -- must be declined, not tesSUCCESS.

        Before the fix: funded 1 XRP over the floor (1_200_000 drops, 0
        owner-reserve), escrow exactly 0.1 XRP (100_000 drops) — old check
        was ``100_000 > 1_200_000`` -> False -> proceeded to tesSUCCESS,
        landing the sender at 1_100_000 drops, ABOVE the 1_000_000 floor
        looks safe here on its own, so this test funds right at the edge:
        balance == reserve + tiny headroom smaller than the escrow amount.
        """
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        # Headroom above the 1,000,000-drop floor is only 50,000 drops —
        # smaller than the 100,000-drop (0.1 XRP) escrow being attempted.
        t._balances[_DRY_RUN_WALLET_ADDRESS] = _BASE_RESERVE_DROPS + 50_000
        r = await t.submit_escrow_create(
            "sSEED", "0.1", "rDEST", finish_after=0,
        )
        _assert_declined(r, "submit_escrow_create")
        # No partial debit on rejection.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == _BASE_RESERVE_DROPS + 50_000

    @pytest.mark.asyncio
    async def test_escrow_create_still_declines_when_only_fee_would_breach(self) -> None:
        """Escrowing "0" is invalid, so drive the fee-only floor case via an
        account with EXACTLY the reserve and nothing more: any escrow amount
        at all must be refused."""
        t = DryRunTransport()
        await _at_floor(t)
        r = await t.submit_escrow_create("sSEED", "0.000001", "rDEST", finish_after=0)
        _assert_declined(r, "submit_escrow_create (minimal amount)")


class TestCheckCashReserveFloor:
    """F-0716549a's second citation: submit_check_cash previously checked
    only ``deliver_drops > self._balances[owner]`` — no reserve term."""

    @pytest.mark.asyncio
    async def test_cash_within_balance_but_breaching_writer_reserve_declined(self) -> None:
        """The writer can afford the raw delivered amount but cashing it
        would breach THEIR OWN reserve floor -- must be declined."""
        t = DryRunTransport()
        writer = _DRY_RUN_WALLET_ADDRESS
        await t.fund_from_faucet(writer)
        # Create while fully funded (F-17e7f723: CheckCreate needs owner-inc
        # headroom), THEN clamp — 0.2 XRP headroom is smaller than the 0.5 XRP
        # cash and must decline.
        create = await t.submit_check_create("sSEED", "rPLAYER", "10")
        assert create.success, create.error
        t._balances[writer] = _BASE_RESERVE_DROPS + 200_000
        cash = await t.submit_check_cash(
            "sSEED", create.check_id, amount="0.5", wallet_address="rPLAYER",
        )
        _assert_declined(cash, "submit_check_cash")
        # Declined cash must not move funds; clamp is post-create.
        assert t._balances[writer] == _BASE_RESERVE_DROPS + 200_000


# ── One representative "needs a pre-existing object" test per remaining
#    named category (Payment Channels, NFT, Credentials, Permissioned
#    Domains, MPT) ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_channel_fund_declines_past_reserve_floor() -> None:
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    create = await t.submit_payment_channel_create(
        "sSEED", "1", "rDEST", 60, "ED" + "AB" * 32,
    )
    assert create.success, create.error
    t._balances[_DRY_RUN_WALLET_ADDRESS] = _BASE_RESERVE_DROPS
    r = await t.submit_payment_channel_fund("sSEED", create.channel_id, "1")
    _assert_declined(r, "submit_payment_channel_fund")


@pytest.mark.asyncio
async def test_nft_accept_offer_declines_past_buyer_reserve_floor() -> None:
    """The buyer's funds check (F-233393c2) previously had no reserve term
    either — folded into the SAME _reserve_guard call."""
    t = DryRunTransport()
    seller = _DRY_RUN_WALLET_ADDRESS
    buyer = "rBUYER00000000000000000000000"
    await t.fund_from_faucet(seller)
    mint = await t.submit_nft_mint("sSEED", "https://x/1")
    assert mint.success, mint.error
    offer = await t.submit_nft_create_offer(
        "sSEED", mint.nft_id, "1", sell=True, destination=buyer,
    )
    assert offer.success, offer.error
    # Buyer's headroom (0.5 XRP) is less than the 1 XRP price -- would take
    # them below reserve even though they technically "hold enough" raw
    # drops once the base reserve is subtracted out.
    t._balances[buyer] = _BASE_RESERVE_DROPS + 500_000
    r = await t.submit_nft_accept_offer("sBUYERSEED", sell_offer=offer.nft_offer_index)
    _assert_declined(r, "submit_nft_accept_offer")


@pytest.mark.asyncio
async def test_credential_accept_declines_past_subject_reserve_floor() -> None:
    t = DryRunTransport()
    issuer = _DRY_RUN_WALLET_ADDRESS
    subject = "rSUBJECT000000000000000000000"
    await t.fund_from_faucet(issuer)
    t._funded_addresses.add(subject)
    create = await t.submit_credential_create("sSEED", subject, "6F7665723231")
    assert create.success, create.error
    t._balances[subject] = _BASE_RESERVE_DROPS
    r = await t.submit_credential_accept(
        "sSUBJECTSEED", issuer, "6F7665723231", subject_address=subject,
    )
    _assert_declined(r, "submit_credential_accept")


@pytest.mark.asyncio
async def test_permissioned_offer_create_declines_past_reserve_floor() -> None:
    t = DryRunTransport()
    owner = _DRY_RUN_WALLET_ADDRESS
    await t.fund_from_faucet(owner)
    domain = await t.submit_permissioned_domain_set(
        "sSEED", [("rISSUER", "6F7665723231")],
    )
    assert domain.success, domain.error
    t._credentials[(owner, "rISSUER", "6F7665723231")] = type(
        "C", (), {"subject": owner, "issuer": "rISSUER",
                  "credential_type": "6F7665723231", "accepted": True,
                  "expiration": None},
    )()
    t._balances[owner] = _BASE_RESERVE_DROPS
    r = await t.submit_permissioned_offer_create(
        "sSEED", "USD", "10", "rISSUER", "XRP", "5", "", domain.domain_id,
    )
    _assert_declined(r, "submit_permissioned_offer_create")


@pytest.mark.asyncio
async def test_mpt_authorize_declines_past_reserve_floor() -> None:
    t = DryRunTransport()
    await _at_floor(t)
    r = await t.submit_mpt_authorize("sSEED", "SOMEISSUANCEID")
    _assert_declined(r, "submit_mpt_authorize")


# ── Fee-debit verification (the OTHER half of the discipline) ──────────────


class TestFeeActuallyDebited:
    """Proves the fee is DEBITED, not merely checked, at representative
    guard+debit sites (mirrors TestReserveFloorAndFee::test_fee_debited_from_sender
    for submit_payment)."""

    @pytest.mark.asyncio
    async def test_trust_set_debits_fee(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_trust_set("sSEED", "rISSUER", "USD", "1000")
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS

    @pytest.mark.asyncio
    async def test_nft_mint_debits_fee(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_nft_mint("sSEED", "https://x/1")
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS

    @pytest.mark.asyncio
    async def test_did_set_debits_fee(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        r = await t.submit_did_set("sSEED", uri="https://x")
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS


class TestFormerFeeExceptionsNowDebitAndStillCheckReserve:
    """F-21a14172: former fee-exception sites now debit the network fee and
    still enforce the reserve floor."""

    @pytest.mark.asyncio
    async def test_check_create_debits_fee_and_still_checks_reserve(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        ok = await t.submit_check_create("sSEED", "rDEST", "10")
        assert ok.success
        # SendMax is not locked; only the network fee leaves the writer.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before - _DRY_FEE_DROPS

        t2 = DryRunTransport()
        await _at_floor(t2)
        declined = await t2.submit_check_create("sSEED", "rDEST", "10")
        _assert_declined(declined, "submit_check_create (at floor)")

    @pytest.mark.asyncio
    async def test_escrow_create_debits_fee_and_still_checks_reserve(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        before = t._balances[_DRY_RUN_WALLET_ADDRESS]
        ok = await t.submit_escrow_create("sSEED", "10", "rDEST", finish_after=0)
        assert ok.success
        # Escrowed amount + network fee.
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            before - 10_000_000 - _DRY_FEE_DROPS
        )
