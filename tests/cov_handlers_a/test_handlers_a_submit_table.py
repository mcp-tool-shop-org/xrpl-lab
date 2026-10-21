"""Every submitting handler: what a validated success and a failed submit leave behind.

The action function each handler calls is replaced by a fake that returns a
crafted SubmitResult, so these tests pin the handler's own bookkeeping:
the TxRecord in ``state.tx_index``, ``context["txids"]``, the printed hash,
explorer link and error, and that state was saved.
"""

from __future__ import annotations

import pytest

from ._h import EXPLORER, FAILED_TXID, TXID, Env, bad, ok, secret

ISSUER = "rISSUERADDRESS123"

# (handler, stubbed action fn, action_args, extra context, teaches the code on failure)
CASES = {
    "set_trust_line": (
        "handle_set_trust_line", "set_trust_line",
        {"currency": "LAB"}, {"issuer_address": ISSUER}, False,
    ),
    "issue_token": (
        "handle_issue_token", "issue_token", {},
        {"issuer_seed": secret("sISS"), "issuer_address": ISSUER}, False,
    ),
    "remove_trust_line": (
        "handle_remove_trust_line", "remove_trust_line",
        {"currency": "LAB"}, {"issuer_address": ISSUER}, False,
    ),
    "set_freeze": (
        "handle_set_freeze", "set_individual_freeze", {},
        {"issuer_seed": secret("sISS"), "issuer_address": ISSUER}, False,
    ),
    "set_global_freeze": (
        "handle_set_global_freeze", "set_global_freeze", {},
        {"issuer_seed": secret("sISS"), "issuer_address": ISSUER}, False,
    ),
    "fund_channel": (
        "handle_fund_channel", "fund_channel", {}, {"channel_id": "CHAN1"}, False,
    ),
    "redeem_claim": (
        "handle_redeem_claim", "redeem_claim", {},
        {"channel_id": "CHAN1", "receiver_seed": secret("sREC"),
         "claim_amount": "3", "claim_signature": "SIG", "channel_public_key": "PK"},
        False,
    ),
    "create_offer": (
        "handle_create_offer", "create_offer", {}, {"issuer_address": ISSUER}, False,
    ),
    "cancel_offer": (
        "handle_cancel_offer", "cancel_offer", {}, {"offer_sequence": 7}, False,
    ),
    "amm_deposit": (
        "handle_amm_deposit", "amm_deposit",
        {"a_value": "5", "b_value": "5"}, {}, False,
    ),
    "amm_withdraw": (
        "handle_amm_withdraw", "amm_withdraw",
        {"a_currency": "XRP", "b_currency": "LAB"}, {}, False,
    ),
    "strategy_offer_bid": (
        "handle_strategy_offer_bid", "create_offer", {}, {"issuer_address": ISSUER}, False,
    ),
    "strategy_offer_ask": (
        "handle_strategy_offer_ask", "create_offer", {}, {"issuer_address": ISSUER}, False,
    ),
    "mint_nft": ("handle_mint_nft", "mint_nft", {}, {}, True),
    "burn_nft": ("handle_burn_nft", "burn_nft", {}, {"nft_id": "N" * 64}, True),
    "create_escrow": ("handle_create_escrow", "create_escrow", {}, {}, True),
    "finish_escrow": (
        "handle_finish_escrow", "finish_escrow", {},
        {"escrow_owner": "rOWNER12345678", "escrow_sequence": 5}, True,
    ),
    "cancel_escrow": (
        "handle_cancel_escrow", "cancel_escrow", {},
        {"escrow_owner": "rOWNER12345678", "escrow_sequence": 5}, True,
    ),
    "allow_trustline_locking": (
        "handle_set_allow_trustline_locking", "set_allow_trustline_locking", {},
        {"issuer_seed": secret("sISS"), "issuer_address": ISSUER}, True,
    ),
    "create_token_escrow": (
        "handle_create_token_escrow", "create_token_escrow", {},
        {"issuer_address": ISSUER, "recipient_address": "rRECIPIENT123"}, True,
    ),
    "finish_token_escrow": (
        "handle_finish_token_escrow", "finish_token_escrow", {},
        {"token_escrow_owner": "rOWNER12345678", "token_escrow_sequence": 3,
         "recipient_seed": secret("sREC")}, True,
    ),
    "set_signer_list": (
        "handle_set_signer_list", "set_signer_list", {},
        {"signer_addresses": ["rS1", "rS2", "rS3"]}, True,
    ),
    "send_multisig_payment": (
        "handle_send_multisig_payment", "send_multisig_payment", {},
        {"signer_seeds": [secret("s1"), secret("s2"), secret("s3")],
         "signer_addresses": ["rS1", "rS2", "rS3"],
         "multisig_entries": [("rS1", 1), ("rS2", 1), ("rS3", 1)],
         "multisig_quorum": 2}, True,
    ),
}


@pytest.fixture(params=sorted(CASES), ids=sorted(CASES))
def case(request):
    return CASES[request.param]


@pytest.mark.asyncio
async def test_success_records_hash_explorer_and_txids(env: Env, case) -> None:
    handler, stub, args, ctx, _explains = case
    env.stub(stub, ok())
    out = await env.run(handler, args, **ctx)

    rec = env.last()
    assert rec.success is True
    assert rec.txid == TXID
    assert rec.explorer_url == EXPLORER
    assert rec.module_id == "mod_x"
    assert rec.network == "testnet"
    assert out["txids"] == [TXID]
    assert "failed_txids" not in out
    assert TXID in env.out
    assert EXPLORER in env.out
    assert env.saved >= 1


@pytest.mark.asyncio
async def test_failed_submit_records_a_failed_tx_and_prints_the_error(env: Env, case) -> None:
    handler, stub, args, ctx, explains = case
    env.stub(stub, bad(error="ledger rejected it"))
    out = await env.run(handler, args, **ctx)

    rec = env.last()
    assert rec.success is False
    assert rec.txid == FAILED_TXID
    assert "txids" not in out
    assert "ledger rejected it" in env.out
    assert len(env.records()) == 1
    assert env.saved >= 1
    if explains:
        # KB-sourced handlers teach the code inline.
        assert "Category:" in env.out
        assert "Meaning:" in env.out
        assert "Action:" in env.out


@pytest.mark.asyncio
async def test_failed_submit_without_a_hash_is_indexed_as_failed(env: Env, case) -> None:
    handler, stub, args, ctx, _explains = case
    env.stub(stub, bad(txid="", code="tefPAST_SEQ"))
    await env.run(handler, args, **ctx)

    rec = env.last()
    assert rec.success is False
    assert rec.txid == "failed"


@pytest.mark.asyncio
async def test_success_without_explorer_url_prints_no_explorer_line(env: Env, case) -> None:
    handler, stub, args, ctx, _explains = case
    env.stub(stub, ok(explorer=""))
    await env.run(handler, args, **ctx)

    assert env.last().explorer_url == ""
    assert "Explorer:" not in env.out
    assert TXID in env.out
