"""AMM and market-making strategy handlers."""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import xrpl_lab.handlers as handlers
from xrpl_lab.actions.strategy import InventoryCheck, PositionSnapshot
from xrpl_lab.errors import LabException
from xrpl_lab.transport.base import (
    AccountSnapshot,
    AmmInfo,
    OfferInfo,
    TrustLineInfo,
)

from ._h import EXPLORER, FAILED_TXID, TXID, Env, bad, checks_result, ok, verdict

ISSUER = "rISSUERADDRESS123"


def _amm(**kw) -> AmmInfo:
    base = dict(
        asset_a="XRP", asset_b="LAB/rI", pool_a="100", pool_b="200",
        lp_token_currency="03ABC", lp_token_issuer="rAMMACCOUNT0123456789",
        lp_supply="141", trading_fee="500",
    )
    base.update(kw)
    return AmmInfo(**base)


# -- _print_failed_txid --


def test_print_failed_txid_prints_nothing_without_a_hash(env: Env) -> None:
    handlers._print_failed_txid(env.console, bad(txid=""))
    assert env.out == ""


def test_print_failed_txid_tec_is_on_the_ledger(env: Env) -> None:
    handlers._print_failed_txid(env.console, bad(code="tecUNFUNDED_AMM", explorer_url=EXPLORER))
    assert (
        f"TXID: {FAILED_TXID} (validated failure: tecUNFUNDED_AMM; it's on the ledger)"
        in env.out
    )
    assert f"Explorer: {EXPLORER}" in env.out


def test_print_failed_txid_non_validated_has_no_explorer(env: Env) -> None:
    handlers._print_failed_txid(env.console, bad(code="tefPAST_SEQ", explorer_url=EXPLORER))
    assert "not validated: tefPAST_SEQ" in env.out
    assert "Explorer:" not in env.out


def test_print_failed_txid_unknown_code(env: Env) -> None:
    handlers._print_failed_txid(env.console, bad(code=""))
    assert "not validated: unknown" in env.out


# -- budget check --


@pytest.mark.asyncio
async def test_budget_unknown_reserves_means_no_problem(env: Env) -> None:
    env.on_transport("get_reserves", None)
    assert await handlers._amm_create_budget_problem(env.transport, "rA", "100") is None


@pytest.mark.asyncio
async def test_budget_without_an_address(env: Env) -> None:
    assert await handlers._amm_create_budget_problem(env.transport, "", "100") is None


@pytest.mark.asyncio
async def test_budget_unparsable_leg_is_not_a_problem(env: Env) -> None:
    assert await handlers._amm_create_budget_problem(env.transport, "rA", "lots") is None


@pytest.mark.asyncio
async def test_budget_shortfall_names_what_is_needed(env: Env) -> None:
    env.on_transport("get_reserves", (1_000_000, 200_000))
    env.on_transport(
        "get_account_info", AccountSnapshot(address="rA", balance_drops="50000000", owner_count=2),
    )
    msg = await handlers._amm_create_budget_problem(env.transport, "rA", "100")
    # leg 100 + create fee 0.2 + base 1 + (2 owned + 1) * 0.2 = 101.8 XRP
    assert msg is not None
    assert "needs 101.8 XRP" in msg and "100 XRP leg" in msg and "has 50 XRP" in msg


@pytest.mark.asyncio
async def test_budget_that_fits_is_not_a_problem(env: Env) -> None:
    env.on_transport("get_reserves", (1_000_000, 200_000))
    env.on_transport(
        "get_account_info", AccountSnapshot(address="rA", balance_drops="200000000"),
    )
    assert await handlers._amm_create_budget_problem(env.transport, "rA", "100") is None


# -- skip without a pool --


def test_skip_without_pool(env: Env) -> None:
    assert handlers._skip_without_pool(env.ctx, "amm_deposit", env.console) is False
    assert "verifications" not in env.ctx
    env.ctx["amm_unavailable"] = True
    assert handlers._skip_without_pool(env.ctx, "amm_deposit", env.console) is True
    assert "Skipped: no AMM pool" in env.out
    assert verdict(env.ctx, "amm_deposit") == {
        "action": "amm_deposit", "passed": False, "failures": ["skipped: no AMM pool"],
    }


# -- ensure_amm_pair --


@pytest.mark.asyncio
async def test_ensure_amm_pair_budget_shortfall_stops_before_submitting(env: Env) -> None:
    calls = env.stub("ensure_amm_pair", (_amm(), ok()))
    out = await env.run(
        "handle_ensure_amm_pair", {"a_value": "100", "b_value": "100"},
        issuer_address=ISSUER,
    )
    assert calls == []  # never submitted
    assert "Creating this pool needs" in env.out
    assert "lower the pool amounts" in env.out
    assert out["amm_unavailable"] is True
    v = verdict(out, "ensure_amm_pair")
    assert v["passed"] is False and "Creating this pool needs" in v["failures"][0]


@pytest.mark.asyncio
async def test_ensure_amm_pair_existing_pool(env: Env) -> None:
    env.on_transport("get_amm_info", _amm())
    info = _amm()
    env.stub("ensure_amm_pair", (info, None))
    out = await env.run("handle_ensure_amm_pair", issuer_address=ISSUER, amm_unavailable=True)
    assert "AMM pool already exists" in env.out
    assert out["amm_info"] is info
    assert "amm_unavailable" not in out  # a pool exists: later steps may run
    assert "Pool A: 100" in env.out and "Pool B: 200" in env.out
    assert "LP token: 03ABC" in env.out and "LP issuer: rAMMACCOUNT01234..." in env.out
    assert out["a_currency"] == "XRP" and out["a_issuer"] == ""
    assert out["b_currency"] == "LAB" and out["b_issuer"] == ISSUER


@pytest.mark.asyncio
async def test_ensure_amm_pair_created(env: Env) -> None:
    env.on_transport("get_amm_info", _amm())  # no budget probe needed
    info = _amm()
    env.stub("ensure_amm_pair", (info, ok()))
    out = await env.run("handle_ensure_amm_pair", issuer_address=ISSUER)
    assert "AMM pool created!" in env.out and EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert env.last().success is True and env.last().explorer_url == EXPLORER
    assert env.saved == 1


@pytest.mark.asyncio
async def test_ensure_amm_pair_without_an_xrp_leg_skips_the_budget_probe(env: Env) -> None:
    probe = env.on_transport("get_amm_info", None)
    env.stub("ensure_amm_pair", (_amm(), None))
    await env.run(
        "handle_ensure_amm_pair", {"a_currency": "USD", "b_currency": "LAB"},
        issuer_address=ISSUER,
    )
    assert probe == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["notSupported", "temDISABLED", "notYetImplemented"])
async def test_ensure_amm_pair_unsupported_transport_marks_the_pool_unavailable(
    env: Env, code: str,
) -> None:
    env.on_transport("get_amm_info", _amm())
    env.stub("ensure_amm_pair", (_amm(), bad(code=code, error="amm not here")))
    out = await env.run("handle_ensure_amm_pair", issuer_address=ISSUER)
    assert "AMM not supported on this transport" in env.out
    assert out["amm_unavailable"] is True
    assert verdict(out, "ensure_amm_pair")["failures"] == ["amm not here"]
    assert "amm_info" not in out
    assert env.records() == []  # nothing was submitted, nothing indexed


@pytest.mark.asyncio
async def test_ensure_amm_pair_unsupported_without_error_text_gets_a_default(env: Env) -> None:
    env.on_transport("get_amm_info", _amm())
    env.stub("ensure_amm_pair", (_amm(), bad(code="notSupported", error="")))
    out = await env.run("handle_ensure_amm_pair", issuer_address=ISSUER)
    assert verdict(out, "ensure_amm_pair")["failures"] == [
        "AMM not supported on this transport"
    ]


@pytest.mark.asyncio
async def test_ensure_amm_pair_validated_failure_keeps_its_hash(env: Env) -> None:
    env.on_transport("get_amm_info", _amm())
    env.stub("ensure_amm_pair", (
        _amm(), bad(code="tecUNFUNDED_AMM", error="short", explorer_url=EXPLORER),
    ))
    out = await env.run("handle_ensure_amm_pair", issuer_address=ISSUER)
    assert "AMM creation failed: short" in env.out
    assert "validated failure: tecUNFUNDED_AMM" in env.out
    assert out["amm_unavailable"] is True
    assert out["failed_txids"] == [{"result_code": "tecUNFUNDED_AMM", "error": "short"}]
    assert env.last().txid == FAILED_TXID and env.last().success is False
    assert env.last().explorer_url == EXPLORER
    assert "amm_info" not in out


@pytest.mark.asyncio
async def test_ensure_amm_pair_failure_without_hash_is_indexed_failed(env: Env) -> None:
    env.on_transport("get_amm_info", _amm())
    env.stub("ensure_amm_pair", (_amm(), bad(txid="", code="tefPAST_SEQ")))
    await env.run("handle_ensure_amm_pair", issuer_address=ISSUER)
    assert env.last().txid == "failed"


# -- get_amm_info --


@pytest.mark.asyncio
async def test_get_amm_info_found(env: Env) -> None:
    info = _amm()
    calls = env.on_transport("get_amm_info", info)
    out = await env.run(
        "handle_get_amm_info", {"a_currency": "XRP", "b_currency": "LAB"},
        a_issuer="", b_issuer=ISSUER,
    )
    assert calls[0][0] == ("XRP", "", "LAB", ISSUER)
    assert out["amm_info"] is info
    assert "LP supply: 141" in env.out and "Trading fee: 500" in env.out


@pytest.mark.asyncio
async def test_get_amm_info_missing(env: Env) -> None:
    out = await env.run("handle_get_amm_info")
    assert "No AMM found for this pair" in env.out
    assert "amm_info" not in out


# -- deposit / withdraw --


@pytest.mark.asyncio
async def test_amm_deposit_requires_amounts(env: Env) -> None:
    calls = env.stub("amm_deposit", ok())
    with pytest.raises(LabException) as ei:
        await env.run("handle_amm_deposit", {"a_value": "5"})
    assert "b_value" in ei.value.error.message
    with pytest.raises(LabException) as ei2:
        await env.run("handle_amm_deposit", {"b_value": "5"})
    assert "a_value" in ei2.value.error.message
    assert calls == []


@pytest.mark.asyncio
async def test_amm_deposit_is_skipped_without_a_pool(env: Env) -> None:
    calls = env.stub("amm_deposit", ok())
    out = await env.run(
        "handle_amm_deposit", {"a_value": "5", "b_value": "5"}, amm_unavailable=True,
    )
    assert calls == []
    assert env.records() == []
    assert verdict(out, "amm_deposit")["passed"] is False


@pytest.mark.asyncio
async def test_amm_deposit_failure_prints_the_failed_hash(env: Env) -> None:
    env.stub("amm_deposit", bad(code="tecAMM_EMPTY", error="empty"))
    await env.run("handle_amm_deposit", {"a_value": "5", "b_value": "5"})
    assert "Deposit failed: empty" in env.out
    assert "validated failure: tecAMM_EMPTY" in env.out


@pytest.mark.asyncio
async def test_amm_deposit_takes_currencies_from_the_pool_step(env: Env) -> None:
    calls = env.stub("amm_deposit", ok())
    await env.run(
        "handle_amm_deposit", {"a_value": "5", "b_value": "6"},
        a_currency="XRP", b_currency="GLD", a_issuer="", b_issuer=ISSUER,
    )
    assert calls[0][0][2:] == ("XRP", "5", "", "GLD", "6", ISSUER)
    assert "Depositing: 5 XRP + 6 GLD" in env.out


@pytest.mark.asyncio
async def test_amm_withdraw_requires_the_pair(env: Env) -> None:
    calls = env.stub("amm_withdraw", ok())
    with pytest.raises(LabException) as ei:
        await env.run("handle_amm_withdraw", {"a_currency": "XRP"})
    assert "b_currency" in ei.value.error.message
    with pytest.raises(LabException):
        await env.run("handle_amm_withdraw", {"b_currency": "LAB"})
    assert calls == []


@pytest.mark.asyncio
async def test_amm_withdraw_all_lp_vs_partial(env: Env) -> None:
    calls = env.stub("amm_withdraw", ok())
    await env.run("handle_amm_withdraw", {"a_currency": "XRP", "b_currency": "LAB"})
    assert "(returning all LP tokens)" in env.out
    assert calls[0][1]["lp_token_value"] == ""

    env2 = Env(env.tmp_path, env.mp)
    calls2 = env2.stub("amm_withdraw", ok())
    await env2.run(
        "handle_amm_withdraw",
        {"a_currency": "XRP", "b_currency": "LAB", "lp_value": "12.5"},
    )
    assert "returning all LP tokens" not in env2.out
    assert calls2[0][1]["lp_token_value"] == "12.5"


@pytest.mark.asyncio
async def test_amm_withdraw_is_skipped_without_a_pool(env: Env) -> None:
    calls = env.stub("amm_withdraw", ok())
    out = await env.run(
        "handle_amm_withdraw", {"a_currency": "XRP", "b_currency": "LAB"},
        amm_unavailable=True,
    )
    assert calls == [] and env.records() == []
    assert verdict(out, "amm_withdraw")["failures"] == ["skipped: no AMM pool"]


@pytest.mark.asyncio
async def test_amm_withdraw_failure_prints_the_failed_hash(env: Env) -> None:
    env.stub("amm_withdraw", bad(code="tecAMM_BALANCE", error="no lp"))
    await env.run("handle_amm_withdraw", {"a_currency": "XRP", "b_currency": "LAB"})
    assert "Withdrawal failed: no lp" in env.out
    assert "validated failure: tecAMM_BALANCE" in env.out


# -- LP verifies --


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["handle_verify_lp_received", "handle_verify_withdrawal"])
async def test_lp_verifies_fail_without_a_pool(env: Env, handler: str) -> None:
    out = await env.run(handler)
    assert "No AMM pool to check" in env.out
    action = handler.removeprefix("handle_")
    v = verdict(out, action)
    assert v["passed"] is False and "amm_info missing" in v["failures"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["handle_verify_lp_received", "handle_verify_withdrawal"])
async def test_lp_verifies_fail_for_a_pool_with_no_lp_token(env: Env, handler: str) -> None:
    out = await env.run(handler, amm_info=_amm(lp_token_currency=""))
    assert verdict(out, handler.removeprefix("handle_"))["passed"] is False


@pytest.mark.asyncio
async def test_verify_lp_received_passes_and_remembers_the_balance(env: Env) -> None:
    res = checks_result(checks=["LP token balance: 10"], lp_balance="10")
    calls = env.stub("verify_lp_received", res)
    out = await env.run("handle_verify_lp_received", amm_info=_amm())
    assert calls[0][0][1] == "rLEARNER"
    assert "LP token balance: 10" in env.out
    assert out["lp_balance_before_withdraw"] == "10"
    assert out["last_amm_verify"] is res
    assert verdict(out, "verify_lp_received")["passed"] is True


@pytest.mark.asyncio
async def test_verify_lp_received_failure(env: Env) -> None:
    env.stub("verify_lp_received", checks_result(
        passed=False, failures=["No LP tokens received"], lp_balance="0",
    ))
    out = await env.run("handle_verify_lp_received", amm_info=_amm())
    assert "No LP tokens received" in env.out
    assert verdict(out, "verify_lp_received")["failures"] == ["No LP tokens received"]


@pytest.mark.asyncio
async def test_verify_withdrawal_uses_the_lp_balance_before(env: Env) -> None:
    calls = env.stub("verify_withdrawal", checks_result(checks=["LP returned"]))
    out = await env.run(
        "handle_verify_withdrawal", amm_info=_amm(), lp_balance_before_withdraw="10",
    )
    assert calls[0][1] == {"lp_before": "10"}
    assert "LP returned" in env.out
    assert verdict(out, "verify_withdrawal")["passed"] is True


@pytest.mark.asyncio
async def test_verify_withdrawal_failure(env: Env) -> None:
    env.stub("verify_withdrawal", checks_result(passed=False, failures=["still holding LP"]))
    out = await env.run("handle_verify_withdrawal", amm_info=_amm())
    assert "still holding LP" in env.out
    assert verdict(out, "verify_withdrawal")["passed"] is False


# -- snapshot_position --


def _position(
    *, balance: int = 50_000_000, owners: int = 2, offers: int = 0,
    lines: list | None = None, address: str = "rLEARNER0123456789",
) -> PositionSnapshot:
    return PositionSnapshot(
        timestamp=time.time(),
        account=AccountSnapshot(address=address, balance_drops=str(balance), owner_count=owners),
        trust_lines=lines or [],
        offers=[OfferInfo(sequence=i, taker_pays="1", taker_gets="1") for i in range(offers)],
        xrp_balance=str(balance), owner_count=owners, offer_count=offers,
    )


@pytest.mark.asyncio
async def test_snapshot_position_without_a_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_snapshot_position", {"label": "x"})
    assert "No wallet address found" in env.out
    assert "position_x" not in out


@pytest.mark.asyncio
async def test_snapshot_position_prints_and_stores(env: Env) -> None:
    snap = _position(offers=2, lines=[TrustLineInfo(account="a", peer="p", currency="LAB")])
    env.stub("snapshot_position", snap)
    out = await env.run("handle_snapshot_position", {"label": "before"})
    assert out["position_before"] is snap
    assert "Balance: 50.000000 XRP (50000000 drops)" in env.out
    assert "Owner count: 2" in env.out and "Open offers: 2" in env.out
    assert "Trust lines: 1" in env.out


# -- strategy offers --


@pytest.mark.asyncio
async def test_strategy_bid_records_a_bid_direction(env: Env) -> None:
    calls = env.stub("create_offer", ok(offer_sequence=31))
    out = await env.run(
        "handle_strategy_offer_bid",
        {"pays_currency": "LAB", "pays_value": "10", "gets_currency": "XRP", "gets_value": "1"},
        issuer_address=ISSUER, module_id="dex_mm_101",
    )
    # A bid REQUESTS the token: taker_pays = token.
    assert calls[0][0][2:] == ("LAB", "10", ISSUER, "XRP", "1", "")
    assert out["strategy_offer_sequences"] == [31]
    assert out["strategy_offer_directions"] == {31: {"side": "bid", "token": "LAB"}}
    assert "Offer sequence: 31" in env.out
    assert "Memo: XRPLLAB|STRAT|DEXMM101|OFFER_BID|" in env.out


@pytest.mark.asyncio
async def test_strategy_ask_sells_the_token(env: Env) -> None:
    calls = env.stub("create_offer", ok(offer_sequence=32))
    out = await env.run(
        "handle_strategy_offer_ask",
        {"pays_currency": "LAB", "pays_value": "10", "gets_currency": "XRP", "gets_value": "2"},
        issuer_address=ISSUER,
    )
    # An ask PROVIDES the token: taker_pays = the XRP price, taker_gets = the token.
    assert calls[0][0][2:] == ("XRP", "2", "", "LAB", "10", ISSUER)
    assert out["strategy_offer_directions"] == {32: {"side": "ask", "token": "LAB"}}
    assert out["strategy_offer_sequences"] == [32]


@pytest.mark.asyncio
async def test_strategy_offers_without_a_resting_entry_record_no_sequence(env: Env) -> None:
    env.stub("create_offer", ok())
    env.on_transport("get_account_offers", [])
    out = await env.run("handle_strategy_offer_bid", issuer_address=ISSUER)
    assert "strategy_offer_sequences" not in out
    assert out["txids"] == [TXID]


# -- verify_module_offers --


@pytest.mark.asyncio
async def test_verify_module_offers_without_any_fails(env: Env) -> None:
    out = await env.run("handle_verify_module_offers")
    assert "No strategy offers to verify" in env.out
    assert verdict(out, "verify_module_offers")["passed"] is False


def _found(offer: OfferInfo | None) -> SimpleNamespace:
    return checks_result(found=True, checks=["offer rests"], offer=offer)


@pytest.mark.asyncio
async def test_verify_module_offers_all_directions_ok(env: Env) -> None:
    results = {
        1: _found(OfferInfo(sequence=1, taker_pays="10/LAB/rI", taker_gets="1000000")),  # bid
        2: _found(OfferInfo(sequence=2, taker_pays="2000000", taker_gets="10/LAB/rI")),  # ask
    }

    async def _vp(transport, address, seq):
        return results[seq]

    env.mp.setattr(handlers, "verify_offer_present", _vp)
    out = await env.run(
        "handle_verify_module_offers",
        strategy_offer_sequences=[1, 2],
        strategy_offer_directions={
            1: {"side": "bid", "token": "LAB"}, 2: {"side": "ask", "token": "LAB"},
        },
    )
    assert "Offer seq 1 direction OK: bid of LAB" in env.out
    assert "Offer seq 2 direction OK: ask of LAB" in env.out
    assert "All 2 strategy offers verified" in env.out
    assert verdict(out, "verify_module_offers")["passed"] is True


@pytest.mark.asyncio
async def test_verify_module_offers_catches_an_inverted_ask(env: Env) -> None:
    # An "ask" that actually BUYS the token (taker_gets is XRP).
    env.stub("verify_offer_present", _found(
        OfferInfo(sequence=2, taker_pays="10/LAB/rI", taker_gets="2000000"),
    ))
    out = await env.run(
        "handle_verify_module_offers",
        strategy_offer_sequences=[2],
        strategy_offer_directions={2: {"side": "ask", "token": "LAB"}},
    )
    v = verdict(out, "verify_module_offers")
    assert v["passed"] is False
    assert "direction INVERTED" in v["failures"][0]
    assert "BUYS instead of selling" in v["failures"][0]
    assert "All 1 strategy offers verified" not in env.out


@pytest.mark.asyncio
async def test_verify_module_offers_catches_an_inverted_bid(env: Env) -> None:
    env.stub("verify_offer_present", _found(
        OfferInfo(sequence=1, taker_pays="1000000", taker_gets="10/LAB/rI"),
    ))
    out = await env.run(
        "handle_verify_module_offers",
        strategy_offer_sequences=[1],
        strategy_offer_directions={1: {"side": "bid", "token": "LAB"}},
    )
    v = verdict(out, "verify_module_offers")
    assert v["passed"] is False
    assert "SELLS instead of buying" in v["failures"][0]


@pytest.mark.asyncio
async def test_verify_module_offers_missing_offer_fails_with_its_reason(env: Env) -> None:
    env.stub("verify_offer_present", checks_result(found=False, failures=["offer 5 not found"]))
    out = await env.run("handle_verify_module_offers", strategy_offer_sequences=[5])
    v = verdict(out, "verify_module_offers")
    assert v["passed"] is False and v["failures"] == ["offer 5 not found"]
    assert "offer 5 not found" in env.out


@pytest.mark.asyncio
async def test_verify_module_offers_without_direction_info_still_passes(env: Env) -> None:
    env.stub("verify_offer_present", _found(None))
    out = await env.run(
        "handle_verify_module_offers", strategy_offer_sequences=[5],
        strategy_offer_directions={5: {"side": "bid", "token": "LAB"}},
    )
    assert "direction" not in env.out
    assert verdict(out, "verify_module_offers")["passed"] is True


# -- cancel_module_offers --


@pytest.mark.asyncio
async def test_cancel_module_offers_with_none(env: Env) -> None:
    calls = env.stub("cancel_module_offers", [])
    out = await env.run("handle_cancel_module_offers")
    assert calls == []
    assert "No strategy offers to cancel" in env.out
    assert "offers_cancelled" not in out


@pytest.mark.asyncio
async def test_cancel_module_offers_records_only_real_cancel_hashes(env: Env) -> None:
    calls = env.stub("cancel_module_offers", [
        (1, True, "C1" * 32), (2, False, FAILED_TXID), (3, True, ""),
    ])
    out = await env.run(
        "handle_cancel_module_offers",
        strategy_offer_sequences=[1, 2, 3],
        strategy_offer_directions={1: {"side": "bid", "token": "LAB"}},
    )
    assert calls[0][0][2] == [1, 2, 3]
    assert "Offer seq 1 cancelled" in env.out
    assert "Offer seq 2 cancel failed" in env.out
    assert out["offers_cancelled"] == 2
    assert out["strategy_offer_sequences"] == []
    assert out["strategy_offer_directions"] == {}
    # Only the successful cancel with a real hash is indexed; nothing is fabricated.
    assert [(r.txid, r.success) for r in env.records()] == [("C1" * 32, True)]
    assert env.saved == 1


# -- verify_module_offers_absent --


@pytest.mark.asyncio
async def test_verify_module_offers_absent_clean(env: Env) -> None:
    out = await env.run("handle_verify_module_offers_absent")
    assert "No open offers" in env.out
    assert verdict(out, "verify_module_offers_absent")["passed"] is True


@pytest.mark.asyncio
async def test_verify_module_offers_absent_with_leftovers(env: Env) -> None:
    env.on_transport("get_account_offers", [OfferInfo(sequence=1, taker_pays="1", taker_gets="1")])
    out = await env.run("handle_verify_module_offers_absent")
    assert "1 offer(s) still open" in env.out
    v = verdict(out, "verify_module_offers_absent")
    assert v["passed"] is False and v["failures"] == ["1 offer(s) still open"]


# -- verify_position_delta --


@pytest.mark.asyncio
async def test_verify_position_delta_missing_snapshot_raises(env: Env) -> None:
    with pytest.raises(LabException) as ei:
        await env.run("handle_verify_position_delta", {"before": "a", "after": "b"})
    assert ei.value.error.code == "STATE_MISSING_SNAPSHOT"
    assert "'a'" in ei.value.error.message
    assert "verifications" not in env.ctx


@pytest.mark.asyncio
async def test_verify_position_delta_observation_only(env: Env) -> None:
    out = await env.run(
        "handle_verify_position_delta", {},
        position_before=_position(owners=1, offers=0),
        position_after=_position(owners=3, offers=2),
    )
    assert "Owner count increased" in env.out
    assert out["last_position_comparison"].offer_count_delta == 2
    assert verdict(out, "verify_position_delta")["passed"] is True


@pytest.mark.asyncio
async def test_verify_position_delta_asserts_opted_in_expectations(env: Env) -> None:
    out = await env.run(
        "handle_verify_position_delta",
        {"expected_owner_delta": "0", "expected_direction": "unchanged",
         "expected_offer_delta": "5"},
        position_before=_position(owners=1, offers=0),
        position_after=_position(owners=3, offers=2),
    )
    v = verdict(out, "verify_position_delta")
    assert v["passed"] is False
    assert "owner_count_delta mismatch: expected +0, observed +2" in v["failures"]
    assert any("expected_direction='unchanged'" in f for f in v["failures"])
    assert "offer_count_delta mismatch: expected +5, observed +2" in v["failures"]
    assert "offer_count_delta mismatch" in env.out


@pytest.mark.asyncio
async def test_verify_position_delta_matching_expectations_pass(env: Env) -> None:
    out = await env.run(
        "handle_verify_position_delta",
        {"expected_owner_delta": "2", "expected_offer_delta": "2", "expected_direction": "up"},
        position_before=_position(owners=1, offers=0),
        position_after=_position(owners=3, offers=2),
    )
    assert verdict(out, "verify_position_delta")["passed"] is True


# -- check_inventory --


@pytest.mark.asyncio
async def test_check_inventory_without_a_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_check_inventory")
    assert "No wallet address found" in env.out
    assert "inventory_check" not in out


@pytest.mark.asyncio
async def test_check_inventory_bad_args_fall_back_to_defaults(env: Env) -> None:
    env.stub("snapshot_position", _position(
        balance=100_000_000, owners=0,
        lines=[TrustLineInfo(account="a", peer="p", currency="LAB", balance="50")],
    ))
    out = await env.run(
        "handle_check_inventory", {"min_xrp_drops": "lots", "min_token": "many"},
    )
    assert "Invalid min_xrp_drops, using default" in env.out
    inv = out["inventory_check"]
    assert inv.min_xrp_drops == 20_000_000
    assert inv.min_token == Decimal("10")
    assert inv.sides_allowed == ["bid", "ask"]
    assert "Sides allowed: bid, ask" in env.out
    assert out["position_baseline"] is not None


@pytest.mark.asyncio
async def test_check_inventory_nothing_allowed(env: Env) -> None:
    env.stub("snapshot_position", _position(balance=1_000_000, owners=0))
    out = await env.run("handle_check_inventory", {"currency": "LAB"})
    assert "No sides allowed" in env.out
    assert "bid BLOCKED" in env.out and "ask BLOCKED" in env.out
    assert out["inventory_check"].any_allowed is False


@pytest.mark.asyncio
async def test_check_inventory_marks_ok_and_blocked_lines_differently(env: Env) -> None:
    env.stub("snapshot_position", _position(balance=100_000_000, owners=0))
    await env.run("handle_check_inventory")
    assert "bid OK" in env.out
    assert "ask BLOCKED" in env.out


# -- place_safe_sides --


def _inv(bid: bool, ask: bool) -> InventoryCheck:
    sides = (["bid"] if bid else []) + (["ask"] if ask else [])
    return InventoryCheck(
        can_bid=bid, can_ask=ask, xrp_spendable_drops=0, token_balance="0",
        min_xrp_drops=0, min_token=Decimal("0"), checks=[], sides_allowed=sides,
    )


@pytest.mark.asyncio
async def test_place_safe_sides_needs_a_prior_inventory_check(env: Env) -> None:
    calls = env.stub("create_offer", ok())
    await env.run("handle_place_safe_sides")
    assert calls == [] and "Run check_inventory first" in env.out


@pytest.mark.asyncio
async def test_place_safe_sides_skips_when_nothing_is_allowed(env: Env) -> None:
    calls = env.stub("create_offer", ok())
    await env.run("handle_place_safe_sides", inventory_check=_inv(False, False))
    assert calls == [] and "Skipping offer placement" in env.out


@pytest.mark.asyncio
async def test_place_safe_sides_places_both_with_the_right_legs(env: Env) -> None:
    results = iter([ok(txid="1" * 64, offer_sequence=11), ok(txid="2" * 64, offer_sequence=12)])
    calls = env.stub("create_offer", lambda: next(results))
    out = await env.run(
        "handle_place_safe_sides",
        {"bid_value": "10", "bid_price": "1", "ask_value": "8", "ask_price": "3"},
        inventory_check=_inv(True, True), issuer_address=ISSUER,
    )
    bid_args, ask_args = calls[0][0][2:], calls[1][0][2:]
    assert bid_args == ("LAB", "10", ISSUER, "XRP", "1", "")  # bid requests the token
    assert ask_args == ("XRP", "3", "", "LAB", "8", ISSUER)  # ask provides the token
    assert out["strategy_offer_sequences"] == [11, 12]
    assert out["strategy_offer_directions"] == {
        11: {"side": "bid", "token": "LAB"}, 12: {"side": "ask", "token": "LAB"},
    }
    assert out["txids"] == ["1" * 64, "2" * 64]
    assert "2 offer(s) placed out of 2 allowed" in env.out
    assert [r.success for r in env.records()] == [True, True]


@pytest.mark.asyncio
async def test_place_safe_sides_bid_only(env: Env) -> None:
    env.stub("create_offer", ok(offer_sequence=11))
    out = await env.run(
        "handle_place_safe_sides", inventory_check=_inv(True, False), issuer_address=ISSUER,
    )
    assert "Ask skipped (token too low)" in env.out
    assert "1 offer(s) placed out of 1 allowed" in env.out
    assert out["strategy_offer_sequences"] == [11]


@pytest.mark.asyncio
async def test_place_safe_sides_ask_only(env: Env) -> None:
    env.stub("create_offer", ok(offer_sequence=12))
    out = await env.run(
        "handle_place_safe_sides", inventory_check=_inv(False, True), issuer_address=ISSUER,
    )
    assert "Bid skipped (XRP too low)" in env.out
    assert out["strategy_offer_directions"] == {12: {"side": "ask", "token": "LAB"}}


@pytest.mark.asyncio
async def test_place_safe_sides_failed_submits_are_recorded_not_counted(env: Env) -> None:
    env.stub("create_offer", bad(error="nope"))
    out = await env.run(
        "handle_place_safe_sides", inventory_check=_inv(True, True), issuer_address=ISSUER,
    )
    assert "Bid failed: nope" in env.out and "Ask failed: nope" in env.out
    assert "0 offer(s) placed out of 2 allowed" in env.out
    assert [r.success for r in env.records()] == [False, False]
    assert "txids" not in out and "strategy_offer_sequences" not in out
    assert env.saved == 2


@pytest.mark.asyncio
async def test_place_safe_sides_failure_without_hash(env: Env) -> None:
    env.stub("create_offer", bad(txid=""))
    await env.run("handle_place_safe_sides", inventory_check=_inv(True, False))
    assert env.last().txid == "failed"


# -- hygiene summary / write_report --


@pytest.mark.asyncio
async def test_hygiene_summary_needs_both_snapshots(env: Env) -> None:
    calls = env.stub_sync("write_last_run", Path("x"))
    await env.run("handle_hygiene_summary", position_baseline=_position())
    assert "Missing baseline or final snapshots" in env.out
    assert calls == []


@pytest.mark.asyncio
async def test_hygiene_summary_clean_without_txids(env: Env) -> None:
    calls = env.stub_sync("write_last_run", Path("x"))
    await env.run(
        "handle_hygiene_summary", position_baseline=_position(owners=2),
        position_final=_position(owners=2), offers_cancelled=3,
    )
    assert "Hygiene Summary" in env.out
    assert "Owner count returned to baseline" in env.out
    assert "Offers cancelled during cleanup: 3" in env.out
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_id", "preset"),
    [
        ("dex_market_making_101", "strategy_mm101"),
        ("dex_inventory_guardrails", "strategy_inv"),
        ("dex_vs_amm_risk_literacy", "strategy_compare"),
        ("some_other_module_with_a_long_name", "strategy_some_other_module_wi"),
    ],
)
async def test_hygiene_summary_writes_the_last_run_with_a_preset(
    env: Env, module_id: str, preset: str,
) -> None:
    calls = env.stub_sync("write_last_run", Path("runs/last.txt"))
    await env.run(
        "handle_hygiene_summary", position_baseline=_position(owners=1),
        position_final=_position(owners=2, offers=1), txids=["T1", "T2"], module_id=module_id,
    )
    assert calls[0][1] == {"txids": ["T1", "T2"], "module_id": module_id, "preset": preset}
    assert "Warning: 1 offers still open" in env.out
    assert f"Last run txids: {Path('runs/last.txt')}" in env.out


@pytest.mark.asyncio
async def test_write_report_is_a_noop(env: Env) -> None:
    before = dict(env.ctx)
    out = await env.run("handle_write_report")
    assert out == before
    assert env.out == ""
