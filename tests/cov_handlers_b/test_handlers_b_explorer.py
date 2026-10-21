"""Every submitting handler prints the explorer link only when the result has one.

The dry-run transport returns no explorer URL, so the link branch is driven here
by faking the action result. Each row: (handler, action it calls, context the
handler needs, step args).
"""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from tests.cov_handlers_b._support import Rig, ok_result, patch_action
from xrpl_lab.runtime import _SecretValue

pytestmark = pytest.mark.asyncio

_SUB = {"subject_seed": _SecretValue("sSub"), "subject_address": "rSubject"}
_ISS = {"issuer_seed": _SecretValue("sIss"), "issuer_address": "rIssuer"}

_ROWS = [
    ("handle_set_did", "set_did", {}, {}),
    ("handle_delete_did", "delete_did", {}, {}),
    ("handle_delete_signer_list", "delete_signer_list", {}, {}),
    ("handle_create_credential", "create_credential", _SUB, {}),
    ("handle_accept_credential", "accept_credential", _SUB, {}),
    ("handle_delete_credential", "delete_credential", _SUB, {}),
    ("handle_create_permissioned_domain", "set_permissioned_domain", {}, {}),
    ("handle_delete_permissioned_domain", "delete_permissioned_domain",
     {"domain_id": "DOM1"}, {}),
    ("handle_enable_deposit_auth", "enable_deposit_auth", {}, {}),
    ("handle_authorize_sender_address", "authorize_deposit_address",
     {"sender_address": "rSender"}, {}),
    ("handle_send_sender_payment", "send_gated_payment",
     {"sender_seed": _SecretValue("sS")}, {}),
    ("handle_authorize_kyc_credential", "authorize_deposit_credential", {}, {}),
    ("handle_unauthorize_sender_address", "unauthorize_deposit_address",
     {"sender_address": "rSender"}, {}),
    ("handle_create_mpt_issuance", "create_mpt_issuance", {}, {}),
    ("handle_mpt_authorize", "authorize_mpt", {"mpt_issuance_id": "ISS1"}, {}),
    ("handle_mpt_payment", "send_mpt", {"mpt_issuance_id": "ISS1", **_ISS}, {}),
    ("handle_send_partial_payment", "send_partial_payment", _ISS, {}),
    ("handle_enable_require_dest", "enable_require_dest", {}, {}),
    ("handle_send_tagged_deposit", "send_tagged_deposit",
     {"player_seed": _SecretValue("sP")}, {}),
    ("handle_enable_clawback", "enable_clawback", _ISS, {}),
    ("handle_enable_default_ripple", "enable_default_ripple", _ISS, {}),
    ("handle_clawback", "clawback_tokens", _ISS, {}),
    ("handle_list_nft_sell_offer", "create_nft_offer",
     {"nft_id": "NFT1", "buyer_address": "rBuyer"}, {}),
    ("handle_accept_nft_offer", "accept_nft_offer",
     {"nft_sell_offer": "OFFER1", "buyer_seed": _SecretValue("sB")}, {}),
    ("handle_modify_nft", "modify_nft", {"nft_id": "NFT1"}, {}),
    ("handle_create_check", "create_check", {}, {"destination": "rDest"}),
    ("handle_cash_check", "cash_check",
     {"check_id": "CHK1", "recipient_seed": _SecretValue("sR")}, {}),
    ("handle_cancel_check", "cancel_check", {"check_id": "CHK1"}, {}),
    ("handle_create_permissioned_offer", "create_permissioned_offer",
     {"domain_id": "DOM1", **_SUB}, {}),
]


def _ids() -> list[str]:
    return [row[0].removeprefix("handle_") for row in _ROWS]


@pytest.mark.parametrize(("handler", "action", "ctx", "args"), _ROWS, ids=_ids())
async def test_explorer_link_is_printed_when_the_result_has_one(
    monkeypatch, handler, action, ctx, args,
) -> None:
    rig = Rig()
    rig.context.update(ctx)
    patch_action(monkeypatch, action, ok_result("TXEXP"))
    await rig.run(getattr(handlers, handler), **args)
    assert "TXID: TXEXP" in rig.out
    assert "Explorer: https://explorer.test/TXEXP" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXEXP", True)]
    assert rig.records[0].explorer_url == "https://explorer.test/TXEXP"


@pytest.mark.parametrize(("handler", "action", "ctx", "args"), _ROWS, ids=_ids())
async def test_no_explorer_line_when_the_result_has_none(
    monkeypatch, handler, action, ctx, args,
) -> None:
    rig = Rig()
    rig.context.update(ctx)
    patch_action(monkeypatch, action, ok_result("TXNOEXP", explorer_url=""))
    await rig.run(getattr(handlers, handler), **args)
    assert "TXID: TXNOEXP" in rig.out
    assert "Explorer:" not in rig.out


async def test_send_kyc_payment_prints_explorer_link(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(_SUB)

    async def _cred_id(*a, **k):
        return "C" * 32

    monkeypatch.setattr(handlers, "get_credential_id", _cred_id)
    patch_action(monkeypatch, "send_gated_payment", ok_result("TXKYC"))
    await rig.run(handlers.handle_send_kyc_payment)
    assert "Explorer: https://explorer.test/TXKYC" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXKYC", True)]
