"""Regression tests for the re-swarm #4 backend-handlers amend wave.

Each test pins one approved finding so it FAILS on the pre-fix code and
PASSES after:

- F-d0b4cddf (CRITICAL): the strategy/guardrail ASK built OfferCreate with the
  legs INVERTED — TakerGets=XRP(price) / TakerPays=token(amount) — i.e. a
  second BUY of the token while the console narrated a sell. XRPL semantics:
  TakerGets is what the offer creator PROVIDES. The fix swaps the ask's legs
  in handle_strategy_offer_ask and the ask leg of handle_place_safe_sides, and
  verify_module_offers now asserts direction so a future inversion cannot pass
  silently.
- F-12f62ad2 (HIGH): token escrow was created with finish_after=None and no
  Condition — rippled's fix1571 preflight rejects that temMALFORMED on every
  real-network run. The action layer now enforces FinishAfter-or-Condition as
  a structured local_error and the handler passes a real FinishAfter.
- F-25d8d8e1 (HIGH): escrow create-sequence captured as escrows[-1] —
  account_objects is hash-ordered, so with a leftover escrow the capture was a
  coin flip and EscrowFinish could release the WRONG escrow. Created objects
  are now selected by identity (destination + FinishAfter + CancelAfter).
- F-ee815beb (MEDIUM): same last-element fallacy for offers[-1] and the
  burn_nft owned[-1] fallback (irreversible burn of an arbitrary NFT).
- F-59ba7d9d (MEDIUM): the "no opt-in → tecNO_PERMISSION" lesson reused the
  MAIN (opted-in) issuer, so the taught failure could never occur. A
  create_noopt_issuer setup handler now exists.
- F-b1ebc369 (MEDIUM): the royalty lesson printed the full sale PRICE as a
  royalty on the first sale and "no royalty" on the resale that actually paid
  one. The delta is only presented as a royalty when the issuer is a third
  party; otherwise the royalty is computed from the mint's TransferFee.
- F-feb389a6 (MEDIUM): amm_deposit's schema advertised default="10" for
  fields the handler hard-requires; the phantom defaults are removed and a
  conformance test keeps every _require()d field default-free.
- F-d18b2348 (LOW): expect-fail handlers recorded {txid:"failed",
  success:true} when a transport returned success with an empty txid.
- F-b5dcccb5 (LOW): verify_tx passed on an UNVALIDATED tesSUCCESS.
"""

from __future__ import annotations

import inspect
import io
import re
from decimal import Decimal

import pytest
from rich.console import Console

from xrpl_lab import handlers
from xrpl_lab.actions.token_escrow import create_token_escrow
from xrpl_lab.actions.verify import verify_tx
from xrpl_lab.modules import ModuleStep
from xrpl_lab.registry import all_actions, is_registered
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult, TrustLineInfo, TxInfo
from xrpl_lab.transport.dry_run import (
    _DRY_RUN_WALLET_ADDRESS,
    _FAKE_ADDRESS,
    DryRunTransport,
)

ISSUER = "rISSUER00000000000000000000000"
RECIPIENT = "rRECIP000000000000000000000000"
CANCEL = 950_000_000
FINISH = 900_000_000


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Keep handler save_state() writes inside the test sandbox."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / "home"))
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)


def _console() -> Console:
    return Console(file=io.StringIO(), no_color=True, markup=True, width=200)


def _out(console: Console) -> str:
    """Console text with whitespace normalized (rich wraps long lines)."""
    return " ".join(console.file.getvalue().split())


def _step(action: str = "x", **action_args) -> ModuleStep:
    return ModuleStep(text="", action=action, action_args=dict(action_args))


def _ctx(**extra) -> dict:
    ctx = {"wallet_seed": _SecretValue("sSeedTest"), "module_id": "reswarm4"}
    ctx.update(extra)
    return ctx


def _state() -> LabState:
    return LabState(network="dry-run", wallet_address=_DRY_RUN_WALLET_ADDRESS)


def _leg_currency(leg: str) -> str:
    parts = leg.split("/")
    return parts[1] if len(parts) >= 2 else "XRP"


# ── F-d0b4cddf (CRITICAL): the ask must SELL the token ─────────────────────


class TestAskDirection:
    @pytest.mark.asyncio
    async def test_strategy_ask_sells_the_token_on_ledger(self):
        """After the fix, an ask (pays_currency=LAB, gets_currency=XRP) rests
        with TakerGets=LAB(amount) / TakerPays=XRP(price): the creator
        PROVIDES the token. The old code built the opposite — a BUY."""
        t = DryRunTransport()
        state = _state()
        context = _ctx(issuer_address=ISSUER)
        await handlers.handle_strategy_offer_ask(
            _step("strategy_offer_ask", pays_currency="LAB", pays_value="10",
                  gets_currency="XRP", gets_value="2"),
            state, t, "", context, _console(),
        )
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        assert len(offers) == 1
        ask = offers[0]
        # TakerGets = what we provide = 10 LAB (the sold token)
        assert _leg_currency(ask.taker_gets) == "LAB", (
            f"ask direction inverted: taker_gets={ask.taker_gets!r} — the ask "
            "must PROVIDE the token"
        )
        assert Decimal(ask.taker_gets.split("/")[0]) == 10
        # TakerPays = what we request = 2 XRP (the price)
        assert _leg_currency(ask.taker_pays) == "XRP"
        assert Decimal(ask.taker_pays) == 2

    @pytest.mark.asyncio
    async def test_strategy_bid_still_buys_the_token(self):
        """The bid was CORRECT — it must remain a buy (TakerPays=token)."""
        t = DryRunTransport()
        state = _state()
        context = _ctx(issuer_address=ISSUER)
        await handlers.handle_strategy_offer_bid(
            _step("strategy_offer_bid", pays_currency="LAB", pays_value="10",
                  gets_currency="XRP", gets_value="1"),
            state, t, "", context, _console(),
        )
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        assert len(offers) == 1
        bid = offers[0]
        assert _leg_currency(bid.taker_pays) == "LAB"  # requested (bought)
        assert _leg_currency(bid.taker_gets) == "XRP"  # provided (spent)

    @pytest.mark.asyncio
    async def test_built_offer_create_decodes_with_taker_gets_token(self):
        """Decode the actual OfferCreate an ask produces: TakerGets must be
        the issued token (currency LAB, the amount) and TakerPays the XRP
        price in drops — built exactly as the testnet transport builds it."""
        from xrpl.models.amounts import IssuedCurrencyAmount
        from xrpl.models.transactions import OfferCreate
        from xrpl.utils import xrp_to_drops

        captured: dict = {}

        class _CapturingTransport(DryRunTransport):
            async def submit_offer_create(self, **kwargs):
                captured.update(kwargs)
                return SubmitResult(success=True, txid="CAPTURED-TX")

        t = _CapturingTransport()
        state = _state()
        context = _ctx(issuer_address=_FAKE_ADDRESS)
        await handlers.handle_strategy_offer_ask(
            _step("strategy_offer_ask", pays_currency="LAB", pays_value="10",
                  gets_currency="XRP", gets_value="2"),
            state, t, "", context, _console(),
        )
        assert captured, "the ask never reached submit_offer_create"

        def _amount(currency: str, value: str, issuer: str):
            if currency == "XRP":
                return xrp_to_drops(Decimal(value))
            return IssuedCurrencyAmount(currency=currency, issuer=issuer, value=value)

        tx = OfferCreate(
            account=_FAKE_ADDRESS,
            taker_pays=_amount(
                captured["taker_pays_currency"],
                captured["taker_pays_value"],
                captured["taker_pays_issuer"],
            ),
            taker_gets=_amount(
                captured["taker_gets_currency"],
                captured["taker_gets_value"],
                captured["taker_gets_issuer"],
            ),
        )
        decoded = tx.to_xrpl()
        # The ask SELLS 10 LAB: TakerGets is the issued-currency amount.
        assert isinstance(decoded["TakerGets"], dict), (
            f"ask TakerGets must be the token, got {decoded['TakerGets']!r}"
        )
        assert decoded["TakerGets"]["currency"] == "LAB"
        assert Decimal(decoded["TakerGets"]["value"]) == 10
        # ...for a price of 2 XRP: TakerPays is a drops string.
        assert decoded["TakerPays"] == xrp_to_drops(Decimal("2"))

    @pytest.mark.asyncio
    async def test_place_safe_sides_ask_commits_the_token(self):
        """The inventory guardrail gates the ask on TOKEN balance — after the
        fix the constructed offer actually spends the token (TakerGets=LAB),
        so the guardrail protects the asset the offer commits."""
        from xrpl_lab.actions.strategy import InventoryCheck

        t = DryRunTransport()
        state = _state()
        inv = InventoryCheck(
            can_bid=False, can_ask=True, xrp_spendable_drops=0,
            token_balance="100", min_xrp_drops=20_000_000,
            min_token=Decimal("10"), checks=[], sides_allowed=["ask"],
        )
        context = _ctx(issuer_address=ISSUER, inventory_check=inv)
        await handlers.handle_place_safe_sides(
            _step("place_safe_sides", pays_currency="LAB", gets_currency="XRP",
                  ask_value="10", ask_price="2"),
            state, t, "", context, _console(),
        )
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        assert len(offers) == 1
        assert _leg_currency(offers[0].taker_gets) == "LAB", (
            "place_safe_sides ask must commit the token the can_ask guardrail "
            "gated on"
        )
        assert _leg_currency(offers[0].taker_pays) == "XRP"

    @pytest.mark.asyncio
    async def test_verify_module_offers_flags_an_inverted_ask(self):
        """The new direction assertion: a resting 'ask' whose taker_gets is
        NOT the token records a FAILED verification."""
        t = DryRunTransport()
        # Rest an INVERTED ask (taker_pays=LAB → a buy) directly.
        await t.submit_offer_create(
            wallet_seed="sSeedTest",
            taker_pays_currency="LAB", taker_pays_value="10",
            taker_pays_issuer=ISSUER,
            taker_gets_currency="XRP", taker_gets_value="2",
            taker_gets_issuer="",
        )
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        seq = offers[0].sequence
        state = _state()
        context = _ctx(
            strategy_offer_sequences=[seq],
            strategy_offer_directions={seq: {"side": "ask", "token": "LAB"}},
        )
        out = await handlers.handle_verify_module_offers(
            _step("verify_module_offers"), state, t, "", context, _console(),
        )
        rec = out["verifications"][-1]
        assert rec["action"] == "verify_module_offers"
        assert rec["passed"] is False
        assert any("INVERTED" in f for f in rec["failures"])

    @pytest.mark.asyncio
    async def test_verify_module_offers_passes_a_correct_ask(self):
        t = DryRunTransport()
        await t.submit_offer_create(
            wallet_seed="sSeedTest",
            taker_pays_currency="XRP", taker_pays_value="2",
            taker_pays_issuer="",
            taker_gets_currency="LAB", taker_gets_value="10",
            taker_gets_issuer=ISSUER,
        )
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        seq = offers[0].sequence
        state = _state()
        context = _ctx(
            strategy_offer_sequences=[seq],
            strategy_offer_directions={seq: {"side": "ask", "token": "LAB"}},
        )
        out = await handlers.handle_verify_module_offers(
            _step("verify_module_offers"), state, t, "", context, _console(),
        )
        rec = out["verifications"][-1]
        assert rec["passed"] is True, rec["failures"]


# ── F-12f62ad2 (HIGH): fix1571 — FinishAfter or Condition required ──────────


class TestTokenEscrowFinishAfter:
    @pytest.mark.asyncio
    async def test_only_cancel_after_token_escrow_is_rejected_locally(self):
        """fix1571: an EscrowCreate with neither FinishAfter nor Condition is
        temMALFORMED on-network — the action layer must reject it locally as a
        structured error, never sign-and-submit it."""
        t = DryRunTransport()
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)
        r = await create_token_escrow(
            t, "sHOLDER", "GLD", ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=None,
            source_address="rHOLDER00000000000000000000000",
        )
        assert r.success is False
        assert r.result_code == "local_error"
        assert "FinishAfter" in r.error
        assert "fix1571" in r.error or "temMALFORMED" in r.error

    @pytest.mark.asyncio
    async def test_missing_cancel_after_still_reported_first(self):
        """The XLS-85 mandatory-CancelAfter gate stays the first check."""
        t = DryRunTransport()
        r = await create_token_escrow(
            t, "sHOLDER", "GLD", ISSUER, "50", RECIPIENT,
            cancel_after=None, finish_after=None,
        )
        assert r.success is False
        assert "CancelAfter" in r.error

    @pytest.mark.asyncio
    async def test_handler_creates_token_escrow_with_finish_after(self):
        """handle_create_token_escrow must produce an escrow carrying a real
        FinishAfter strictly before its CancelAfter (old code: None)."""
        t = DryRunTransport()
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)
        t._trust_lines.setdefault(_DRY_RUN_WALLET_ADDRESS, []).append(
            TrustLineInfo(account=_DRY_RUN_WALLET_ADDRESS, peer=ISSUER,
                          currency="GLD", balance="100", limit="1000")
        )
        state = _state()
        context = _ctx(issuer_address=ISSUER, recipient_address=RECIPIENT)
        out = await handlers.handle_create_token_escrow(
            _step("create_token_escrow", currency="GLD", amount="50"),
            state, t, "", context, _console(),
        )
        escrows = await t.get_escrows(_DRY_RUN_WALLET_ADDRESS)
        assert len(escrows) == 1
        escrow = escrows[0]
        assert escrow.finish_after is not None, (
            "token escrow was created without FinishAfter — fix1571 rejects "
            "this temMALFORMED on any real network"
        )
        assert escrow.cancel_after is not None
        assert escrow.cancel_after > escrow.finish_after
        assert out.get("token_escrow_finish_after") == escrow.finish_after
        assert out.get("token_escrow_sequence") == escrow.sequence

    @pytest.mark.asyncio
    async def test_expect_fail_handler_also_carries_finish_after(self):
        """The expect-fail step must fail on the OPT-IN rule, not on fix1571 —
        so its EscrowCreate carries a FinishAfter too and the dry-run rejects
        it tecNO_PERMISSION (issuer never opted in)."""
        t = DryRunTransport()
        state = _state()
        context = _ctx(noopt_issuer_address="rNOOPT0000000000000000000000")
        out = await handlers.handle_create_token_escrow_expect_fail(
            _step("create_token_escrow_expect_fail", currency="NOP", amount="50"),
            state, t, "", context, _console(),
        )
        failed = out.get("failed_txids", [])
        assert failed, "the expect-fail step recorded no failure"
        assert failed[-1]["result_code"] == "tecNO_PERMISSION"


# ── F-25d8d8e1 (HIGH): escrow selected by identity, not position ────────────


class _HashOrderedEscrows(DryRunTransport):
    """Simulates account_objects hash order by reversing creation order."""

    async def get_escrows(self, address):
        return list(reversed(await super().get_escrows(address)))


class TestEscrowIdentitySelection:
    @pytest.mark.asyncio
    async def test_create_escrow_captures_the_new_escrow_not_last_element(self):
        t = _HashOrderedEscrows()
        # A leftover escrow from an earlier module (different destination).
        await t.submit_escrow_create(
            "sSeedTest", "5", "rOLDDEST0000000000000000000000",
            finish_after=111_111, cancel_after=222_222,
        )
        state = _state()
        context = _ctx()
        out = await handlers.handle_create_escrow(
            _step("create_escrow", amount="10", finish_seconds="60"),
            state, t, "", context, _console(),
        )
        escrows = await DryRunTransport.get_escrows(t, _DRY_RUN_WALLET_ADDRESS)
        new = next(
            e for e in escrows if e.destination == _DRY_RUN_WALLET_ADDRESS
        )
        stale = next(
            e for e in escrows if e.destination != _DRY_RUN_WALLET_ADDRESS
        )
        assert out.get("escrow_sequence") == new.sequence, (
            f"captured {out.get('escrow_sequence')} — the STALE escrow is "
            f"{stale.sequence}; EscrowFinish would release the wrong escrow"
        )

    @pytest.mark.asyncio
    async def test_token_escrow_ignores_leftover_xrp_escrow(self):
        t = _HashOrderedEscrows()
        # Leftover XRP escrow-to-self from escrow_101.
        await t.submit_escrow_create(
            "sSeedTest", "10", _DRY_RUN_WALLET_ADDRESS,
            finish_after=111_111, cancel_after=222_222,
        )
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)
        t._trust_lines.setdefault(_DRY_RUN_WALLET_ADDRESS, []).append(
            TrustLineInfo(account=_DRY_RUN_WALLET_ADDRESS, peer=ISSUER,
                          currency="GLD", balance="100", limit="1000")
        )
        state = _state()
        context = _ctx(issuer_address=ISSUER, recipient_address=RECIPIENT)
        out = await handlers.handle_create_token_escrow(
            _step("create_token_escrow", currency="GLD", amount="50"),
            state, t, "", context, _console(),
        )
        escrows = await DryRunTransport.get_escrows(t, _DRY_RUN_WALLET_ADDRESS)
        token_escrow = next(e for e in escrows if e.destination == RECIPIENT)
        assert out.get("token_escrow_sequence") == token_escrow.sequence, (
            "the token-escrow step captured the leftover XRP escrow's "
            "sequence — finish would release the wrong (XRP) escrow"
        )


# ── F-ee815beb (MEDIUM): offers by identity; no arbitrary NFT burn ──────────


class _HashOrderedOffers(DryRunTransport):
    async def get_account_offers(self, address):
        return list(reversed(await super().get_account_offers(address)))


class TestOfferIdentitySelection:
    @pytest.mark.asyncio
    async def test_create_offer_captures_the_new_offer_not_last_element(self):
        t = _HashOrderedOffers()
        # A stale resting offer for a DIFFERENT pair.
        await t.submit_offer_create(
            wallet_seed="sSeedTest",
            taker_pays_currency="ZZZ", taker_pays_value="7",
            taker_pays_issuer=ISSUER,
            taker_gets_currency="XRP", taker_gets_value="3",
            taker_gets_issuer="",
        )
        state = _state()
        context = _ctx(issuer_address=ISSUER)
        out = await handlers.handle_create_offer(
            _step("create_offer", pays_currency="LAB", pays_value="50",
                  gets_currency="XRP", gets_value="10"),
            state, t, "", context, _console(),
        )
        offers = await DryRunTransport.get_account_offers(
            t, _DRY_RUN_WALLET_ADDRESS
        )
        new = next(o for o in offers if "LAB" in o.taker_pays)
        stale = next(o for o in offers if "ZZZ" in o.taker_pays)
        assert out.get("offer_sequence") == new.sequence, (
            f"captured {out.get('offer_sequence')} (stale={stale.sequence}) — "
            "cancel/verify would target an innocent offer"
        )

    @pytest.mark.asyncio
    async def test_burn_nft_never_guesses_from_the_on_ledger_list(self):
        """With no explicit nftoken_id and no mint capture, burn must REFUSE —
        the old owned[-1] fallback burned an arbitrary NFT (irreversible)."""
        t = DryRunTransport()
        mint = await t.submit_nft_mint("sSeedTest", "ipfs://precious")
        assert mint.success and mint.nft_id
        state = _state()
        context = _ctx()  # no nft_id captured
        out = await handlers.handle_burn_nft(
            _step("burn_nft"), state, t, "", context, _console(),
        )
        owned = await t.get_account_nfts(_DRY_RUN_WALLET_ADDRESS)
        assert len(owned) == 1, (
            "burn_nft destroyed an NFT it was never told to burn — the "
            "owned[-1] fallback is back"
        )
        assert "burned_nft_id" not in out


# ── F-59ba7d9d (MEDIUM): the no-opt-in failure needs a no-opt-in issuer ─────


class TestNooptIssuer:
    def test_create_noopt_issuer_is_registered(self):
        assert is_registered("create_noopt_issuer")

    @pytest.mark.asyncio
    async def test_noopt_setup_then_expect_fail_hits_no_permission(self):
        """create_noopt_issuer seeds a second issuer that never opts in; the
        expect-fail step then produces the REAL tecNO_PERMISSION instead of
        falling back to the opted-in main issuer (which cannot fail that way:
        asfAllowTrustLineLocking is account-wide)."""
        t = DryRunTransport()
        state = _state()
        context = _ctx(issuer_address=ISSUER)
        # Main issuer opted in (as in token_escrow_101 step 5).
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)

        out = await handlers.handle_create_noopt_issuer(
            _step("create_noopt_issuer"), state, t, "", context, _console(),
        )
        assert out.get("noopt_issuer_address"), "noopt issuer address not stored"
        assert out.get("noopt_currency") == "NOP"
        assert out["noopt_issuer_address"] != ISSUER

        out = await handlers.handle_create_token_escrow_expect_fail(
            _step("create_token_escrow_expect_fail", currency="NOP", amount="50"),
            state, t, "", out, _console(),
        )
        failed = out.get("failed_txids", [])
        assert failed, "expect-fail step recorded no failure"
        assert failed[-1]["result_code"] == "tecNO_PERMISSION", (
            f"got {failed[-1]['result_code']} — the step did not exercise the "
            "missing-opt-in rule"
        )

    @pytest.mark.asyncio
    async def test_expect_fail_warns_when_noopt_issuer_missing(self):
        """Without the setup step, the handler must SAY the demonstration is
        degraded instead of silently reusing the opted-in issuer."""
        t = DryRunTransport()
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)
        state = _state()
        console = _console()
        context = _ctx(issuer_address=ISSUER)  # no noopt_issuer_address
        await handlers.handle_create_token_escrow_expect_fail(
            _step("create_token_escrow_expect_fail", currency="NOP"),
            state, t, "", context, console,
        )
        text = _out(console)
        assert "create_noopt_issuer" in text
        assert "cannot demonstrate" in text


# ── F-b1ebc369 (MEDIUM): royalty reporting on principal-issuer hops ─────────


class TestRoyaltyReporting:
    @pytest.mark.asyncio
    async def test_first_sale_by_creator_is_not_reported_as_royalty(self):
        """First sale: the issuer IS the seller — its +100 delta is the sale
        PRICE. The old code printed it as 'Royalty (TransferFee) paid'."""
        t = DryRunTransport()
        state = _state()
        console = _console()
        creator = _DRY_RUN_WALLET_ADDRESS
        context = _ctx(
            nft_id="000800001234", nft_buyer_address="rBUYER0000000000000000000000",
            nft_prev_owner=creator,  # the creator sold
            nft_issuer_balance_before="100", nft_issuer_balance_after="200",
            nft_transfer_fee=5000, nft_offer_price="100",
        )
        await handlers.handle_verify_nft_trade(
            _step("verify_nft_trade"), state, t, "", context, console,
        )
        text = _out(console)
        assert "Royalty (TransferFee) paid to issuer: +100" not in text, (
            "the full sale price was misreported as a protocol royalty"
        )
        assert "the issuer is the SELLER" in text

    @pytest.mark.asyncio
    async def test_resale_royalty_computed_from_transfer_fee(self):
        """Resale bought back by the creator: delta is ≈ -(price - royalty);
        the royalty (5% of 200 = 10) must be computed from the TransferFee,
        not read from the (negative) delta as 'no royalty'."""
        t = DryRunTransport()
        state = _state()
        console = _console()
        creator = _DRY_RUN_WALLET_ADDRESS
        context = _ctx(
            nft_id="000800001234", nft_buyer_address=creator,  # creator buys back
            nft_prev_owner="rBUYER0000000000000000000000",
            nft_issuer_balance_before="300", nft_issuer_balance_after="110",
            nft_transfer_fee=5000, nft_offer_price="200",
        )
        await handlers.handle_verify_nft_trade(
            _step("verify_nft_trade"), state, t, "", context, console,
        )
        text = _out(console)
        assert "No royalty on this hop" not in text, (
            "the only hop that actually paid a royalty was reported as paying "
            "none"
        )
        assert "Royalty (TransferFee) enforced on this resale" in text
        assert "10 XRP of the 200 XRP" in text


# ── F-feb389a6 (MEDIUM): schema defaults must not contradict _require ───────


class TestRegistryConformance:
    def test_amm_deposit_declares_no_phantom_defaults(self):
        adef = all_actions()["amm_deposit"]
        by_name = {f.name: f for f in adef.payload_fields}
        assert by_name["a_value"].default is None, (
            "amm_deposit advertises a default for a_value while the handler "
            "hard-requires it (INPUT_REQUIRED_FIELD)"
        )
        assert by_name["b_value"].default is None

    def test_no_required_field_advertises_a_default(self):
        """Conformance: for every `_require(args, context, "<key>",
        action="<name>")` site, the registry's ActionDef for <name> must not
        declare a default for <key> — the runner discards schema defaults, so
        an advertised default that the handler then requires is a lie."""
        src = inspect.getsource(handlers)
        pat = re.compile(
            r"_require\(\s*args,\s*context,\s*\"(?P<key>\w+)\",\s*"
            r"action=\"(?P<action>\w+)\"",
            re.S,
        )
        pairs = pat.findall(src)
        assert pairs, "expected at least one _require call site"
        actions = all_actions()
        offenders = []
        for key, action in pairs:
            adef = actions.get(action)
            if adef is None:
                continue
            for f in adef.payload_fields:
                if f.name == key and f.default is not None:
                    offenders.append(f"{action}.{key} default={f.default!r}")
        assert not offenders, (
            "schema defaults contradict handler _require sites: "
            f"{offenders} — omitting these fields fails INPUT_REQUIRED_FIELD "
            "despite the advertised default"
        )


# ── F-d18b2348 (LOW): no {txid:'failed', success:true} records ──────────────


class TestExpectFailRecordGuards:
    @pytest.mark.asyncio
    async def test_issue_token_expect_fail_skips_record_on_empty_txid(
        self, monkeypatch,
    ):
        async def _fake_issue(*args, **kwargs):
            return SubmitResult(success=True, txid="")  # success, no txid

        monkeypatch.setattr(handlers, "issue_token", _fake_issue)
        state = _state()
        context = _ctx(issuer_seed=_SecretValue("sISSUER"), issuer_address=ISSUER)
        out = await handlers.handle_issue_token_expect_fail(
            _step("issue_token_expect_fail"), state, DryRunTransport(), "",
            context, _console(),
        )
        bogus = [r for r in state.tx_index if r.txid == "failed" and r.success]
        assert not bogus, (
            "unexpected-success with an empty txid minted a "
            "{txid:'failed', success:true} record (dead explorer link, "
            "inflated success count)"
        )
        assert "" not in out.get("txids", [])

    @pytest.mark.asyncio
    async def test_token_escrow_expect_fail_skips_record_on_empty_txid(
        self, monkeypatch,
    ):
        async def _fake_create(*args, **kwargs):
            return SubmitResult(success=True, txid="")

        monkeypatch.setattr(handlers, "create_token_escrow", _fake_create)
        state = _state()
        context = _ctx(
            issuer_address=ISSUER,
            noopt_issuer_address="rNOOPT0000000000000000000000",
        )
        await handlers.handle_create_token_escrow_expect_fail(
            _step("create_token_escrow_expect_fail"), state, DryRunTransport(),
            "", context, _console(),
        )
        bogus = [r for r in state.tx_index if r.txid == "failed" and r.success]
        assert not bogus


# ── F-b5dcccb5 (LOW): verify_tx must not pass an unvalidated tesSUCCESS ─────


class TestVerifyTxValidatedGate:
    @pytest.mark.asyncio
    async def test_unvalidated_tessuccess_fails_verification(self):
        transport = DryRunTransport()
        tx = TxInfo(
            txid="TXUNVAL", tx_type="Payment", account="rSENDER",
            destination="rDEST", amount="1000000", fee="12",
            result_code="tesSUCCESS", ledger_index=123, validated=False,
        )
        transport.set_tx_fixtures({"TXUNVAL": tx})
        result = await verify_tx(transport, "TXUNVAL", expected_success=True)
        assert result.passed is False
        assert any("not validated" in f for f in result.failures)

    @pytest.mark.asyncio
    async def test_validated_tessuccess_still_passes(self):
        transport = DryRunTransport()
        tx = TxInfo(
            txid="TXVAL", tx_type="Payment", account="rSENDER",
            destination="rDEST", amount="1000000", fee="12",
            result_code="tesSUCCESS", ledger_index=123, validated=True,
        )
        transport.set_tx_fixtures({"TXVAL": tx})
        result = await verify_tx(transport, "TXVAL", expected_success=True)
        assert result.passed is True
