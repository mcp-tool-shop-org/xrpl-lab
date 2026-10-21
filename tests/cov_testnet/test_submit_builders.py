"""Every ``submit_*`` method builds the right XRPL transaction.

The network is fully faked (see ``_fakes``): each case drives one transport
method, captures the model handed to ``submit_and_wait`` and checks its type
and key fields, the pinned Sequence, and the returned ``SubmitResult``.
"""

from __future__ import annotations

import pytest
from xrpl.models.transactions import (
    AccountSetAsfFlag,
    AMMDepositFlag,
    AMMWithdrawFlag,
    NFTokenCreateOfferFlag,
    NFTokenMintFlag,
    OfferCreateFlag,
    PaymentChannelClaimFlag,
    PaymentFlag,
    TrustSetFlag,
)
from xrpl.utils import str_to_hex

from tests.cov_testnet._fakes import (
    ADDR,
    ADDR2,
    CRED_TYPE,
    DEST,
    HASH64,
    HASH64_B,
    HOLDER,
    ISSUER,
    MPT_ID,
    PINNED_SEQ,
    SEED,
    SEED2,
    TXID,
    WALLET,
    WALLET2,
    WALLET3,
    install,
    make_transport,
    submit_ok,
)

pytestmark = pytest.mark.asyncio

COND = "A0258020E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855810100"
FULF = "A0028000"

IOU = {"currency": "LAB", "issuer": ISSUER, "value": "10"}

# (id, method, kwargs, expected tx fields as they appear on the wire)
CASES = [
    ("payment", "submit_payment",
     dict(wallet_seed=SEED, destination=DEST, amount="1.5", memo="hi",
          destination_tag=7, source_tag=9),
     {"TransactionType": "Payment", "Destination": DEST, "Amount": "1500000",
      "DestinationTag": 7, "SourceTag": 9}),
    ("trust_set", "submit_trust_set",
     dict(wallet_seed=SEED, issuer=ISSUER, currency="LAB", limit="1000"),
     {"TransactionType": "TrustSet",
      "LimitAmount": {"currency": "LAB", "issuer": ISSUER, "value": "1000"}}),
    ("issued_payment", "submit_issued_payment",
     dict(wallet_seed=SEED, destination=DEST, currency="LAB", issuer=ISSUER,
          amount="10", memo="m"),
     {"TransactionType": "Payment", "Destination": DEST, "Amount": IOU}),
    ("partial_payment", "submit_partial_payment",
     dict(issuer_seed=SEED, destination=DEST, currency="LAB", issuer=ISSUER,
          amount="10", deliver_min="5", send_max="12", memo="m"),
     {"TransactionType": "Payment", "Amount": IOU,
      "DeliverMin": {"currency": "LAB", "issuer": ISSUER, "value": "5"},
      "SendMax": {"currency": "LAB", "issuer": ISSUER, "value": "12"},
      "Flags": int(PaymentFlag.TF_PARTIAL_PAYMENT)}),
    ("nft_mint", "submit_nft_mint",
     dict(wallet_seed=SEED, uri="ipfs://x", taxon=3, transfer_fee=500,
          transferable=True, mutable=True),
     {"TransactionType": "NFTokenMint", "NFTokenTaxon": 3, "TransferFee": 500,
      "URI": str_to_hex("ipfs://x"),
      "Flags": int(NFTokenMintFlag.TF_TRANSFERABLE | NFTokenMintFlag.TF_MUTABLE)}),
    ("nft_burn", "submit_nft_burn",
     dict(wallet_seed=SEED, nftoken_id=HASH64),
     {"TransactionType": "NFTokenBurn", "NFTokenID": HASH64}),
    ("nft_accept", "submit_nft_accept_offer",
     dict(wallet_seed=SEED, sell_offer=HASH64),
     {"TransactionType": "NFTokenAcceptOffer", "NFTokenSellOffer": HASH64}),
    ("nft_modify", "submit_nft_modify",
     dict(wallet_seed=SEED, nftoken_id=HASH64, uri="ipfs://y", owner=DEST),
     {"TransactionType": "NFTokenModify", "NFTokenID": HASH64, "Owner": DEST,
      "URI": str_to_hex("ipfs://y")}),
    ("clawback_enable", "submit_account_set_clawback",
     dict(wallet_seed=SEED),
     {"TransactionType": "AccountSet",
      "SetFlag": int(AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_CLAWBACK)}),
    ("default_ripple", "submit_default_ripple",
     dict(wallet_seed=SEED),
     {"TransactionType": "AccountSet",
      "SetFlag": int(AccountSetAsfFlag.ASF_DEFAULT_RIPPLE)}),
    ("clawback", "submit_clawback",
     dict(issuer_seed=SEED, holder_address=HOLDER, currency="LAB", amount="3"),
     # XLS-39: Amount.issuer carries the HOLDER
     {"TransactionType": "Clawback",
      "Amount": {"currency": "LAB", "issuer": HOLDER, "value": "3"}}),
    ("freeze_set", "submit_set_freeze",
     dict(issuer_seed=SEED, holder=HOLDER, currency="LAB", freeze=True),
     {"TransactionType": "TrustSet", "Flags": int(TrustSetFlag.TF_SET_FREEZE),
      "LimitAmount": {"currency": "LAB", "issuer": HOLDER, "value": "0"}}),
    ("freeze_clear", "submit_set_freeze",
     dict(issuer_seed=SEED, holder=HOLDER, currency="LAB", freeze=False),
     {"TransactionType": "TrustSet", "Flags": int(TrustSetFlag.TF_CLEAR_FREEZE)}),
    ("global_freeze_on", "submit_global_freeze",
     dict(issuer_seed=SEED, enable=True),
     {"TransactionType": "AccountSet",
      "SetFlag": int(AccountSetAsfFlag.ASF_GLOBAL_FREEZE)}),
    ("global_freeze_off", "submit_global_freeze",
     dict(issuer_seed=SEED, enable=False),
     {"TransactionType": "AccountSet",
      "ClearFlag": int(AccountSetAsfFlag.ASF_GLOBAL_FREEZE)}),
    ("channel_create", "submit_payment_channel_create",
     dict(wallet_seed=SEED, amount_xrp="5", destination=DEST, settle_delay=60,
          public_key="", cancel_after=800_000_000),
     {"TransactionType": "PaymentChannelCreate", "Amount": "5000000",
      "Destination": DEST, "SettleDelay": 60, "CancelAfter": 800_000_000,
      "PublicKey": WALLET.public_key}),
    ("channel_fund", "submit_payment_channel_fund",
     dict(wallet_seed=SEED, channel_id=HASH64, amount_xrp="2", expiration=800_000_000),
     {"TransactionType": "PaymentChannelFund", "Channel": HASH64,
      "Amount": "2000000", "Expiration": 800_000_000}),
    ("channel_claim_close", "submit_payment_channel_claim",
     dict(wallet_seed=SEED, channel_id=HASH64, balance_xrp="1", amount_xrp="1",
          signature="AABBCC", public_key=WALLET.public_key, close=True),
     {"TransactionType": "PaymentChannelClaim", "Channel": HASH64,
      "Balance": "1000000", "Amount": "1000000", "Signature": "AABBCC",
      "Flags": int(PaymentChannelClaimFlag.TF_CLOSE)}),
    ("escrow_create", "submit_escrow_create",
     dict(wallet_seed=SEED, amount="3", destination=DEST, finish_after=800_000_000,
          cancel_after=800_000_100),
     {"TransactionType": "EscrowCreate", "Amount": "3000000", "Destination": DEST,
      "FinishAfter": 800_000_000, "CancelAfter": 800_000_100}),
    ("require_dest_on", "submit_require_dest",
     dict(wallet_seed=SEED, enable=True),
     {"TransactionType": "AccountSet", "SetFlag": int(AccountSetAsfFlag.ASF_REQUIRE_DEST)}),
    ("require_dest_off", "submit_require_dest",
     dict(wallet_seed=SEED, enable=False),
     {"TransactionType": "AccountSet",
      "ClearFlag": int(AccountSetAsfFlag.ASF_REQUIRE_DEST)}),
    ("deposit_auth_on", "submit_deposit_auth",
     dict(wallet_seed=SEED, enable=True),
     {"TransactionType": "AccountSet", "SetFlag": int(AccountSetAsfFlag.ASF_DEPOSIT_AUTH)}),
    ("deposit_auth_off", "submit_deposit_auth",
     dict(wallet_seed=SEED, enable=False),
     {"TransactionType": "AccountSet",
      "ClearFlag": int(AccountSetAsfFlag.ASF_DEPOSIT_AUTH)}),
    ("preauth_addr", "submit_deposit_preauth",
     dict(wallet_seed=SEED, authorize=DEST),
     {"TransactionType": "DepositPreauth", "Authorize": DEST}),
    ("unpreauth_addr", "submit_deposit_preauth",
     dict(wallet_seed=SEED, unauthorize=DEST),
     {"TransactionType": "DepositPreauth", "Unauthorize": DEST}),
    ("preauth_cred", "submit_deposit_preauth",
     dict(wallet_seed=SEED, authorize_credentials=[(ISSUER, CRED_TYPE)]),
     {"TransactionType": "DepositPreauth",
      "AuthorizeCredentials": [
          {"Credential": {"Issuer": ISSUER, "CredentialType": CRED_TYPE}}]}),
    ("unpreauth_cred", "submit_deposit_preauth",
     dict(wallet_seed=SEED, unauthorize_credentials=[(ISSUER, CRED_TYPE)]),
     {"TransactionType": "DepositPreauth",
      "UnauthorizeCredentials": [
          {"Credential": {"Issuer": ISSUER, "CredentialType": CRED_TYPE}}]}),
    ("allow_locking", "submit_allow_trustline_locking",
     dict(issuer_seed=SEED),
     {"TransactionType": "AccountSet",
      "SetFlag": int(AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_LOCKING)}),
    ("token_escrow", "submit_token_escrow_create",
     dict(source_seed=SEED, currency="LAB", issuer=ISSUER, value="10",
          destination=DEST, cancel_after=800_000_100, finish_after=800_000_000),
     {"TransactionType": "EscrowCreate", "Amount": IOU, "Destination": DEST,
      "CancelAfter": 800_000_100, "FinishAfter": 800_000_000}),
    ("signer_list", "submit_signer_list_set",
     dict(owner_seed=SEED, quorum=2, entries=[(ADDR2, 1), (DEST, 1)]),
     {"TransactionType": "SignerListSet", "SignerQuorum": 2,
      "SignerEntries": [
          {"SignerEntry": {"Account": ADDR2, "SignerWeight": 1}},
          {"SignerEntry": {"Account": DEST, "SignerWeight": 1}}]}),
    ("signer_list_delete", "submit_signer_list_set",
     dict(owner_seed=SEED, quorum=0, entries=[]),
     {"TransactionType": "SignerListSet", "SignerQuorum": 0}),
    ("escrow_finish", "submit_escrow_finish",
     dict(wallet_seed=SEED, owner=DEST, offer_sequence=12, condition=COND,
          fulfillment=FULF),
     {"TransactionType": "EscrowFinish", "Owner": DEST, "OfferSequence": 12,
      "Condition": COND, "Fulfillment": FULF}),
    ("escrow_cancel", "submit_escrow_cancel",
     dict(wallet_seed=SEED, owner=DEST, offer_sequence=12),
     {"TransactionType": "EscrowCancel", "Owner": DEST, "OfferSequence": 12}),
    ("check_create", "submit_check_create",
     dict(wallet_seed=SEED, destination=DEST, send_max="4", expiration=800_000_000,
          destination_tag=5, invoice_id=HASH64),
     {"TransactionType": "CheckCreate", "Destination": DEST, "SendMax": "4000000",
      "Expiration": 800_000_000, "DestinationTag": 5, "InvoiceID": HASH64}),
    ("check_cash_amount", "submit_check_cash",
     dict(wallet_seed=SEED, check_id=HASH64, amount="2"),
     {"TransactionType": "CheckCash", "CheckID": HASH64, "Amount": "2000000"}),
    ("check_cash_min", "submit_check_cash",
     dict(wallet_seed=SEED, check_id=HASH64, deliver_min="1"),
     {"TransactionType": "CheckCash", "CheckID": HASH64, "DeliverMin": "1000000"}),
    ("check_cancel", "submit_check_cancel",
     dict(wallet_seed=SEED, check_id=HASH64),
     {"TransactionType": "CheckCancel", "CheckID": HASH64}),
    ("did_set", "submit_did_set",
     dict(wallet_seed=SEED, uri="ipfs://d", data="blob"),
     {"TransactionType": "DIDSet", "URI": str_to_hex("ipfs://d"),
      "Data": str_to_hex("blob")}),
    ("did_delete", "submit_did_delete",
     dict(wallet_seed=SEED),
     {"TransactionType": "DIDDelete"}),
    ("cred_create", "submit_credential_create",
     dict(issuer_seed=SEED, subject=DEST, credential_type=CRED_TYPE, uri="ipfs://c",
          expiration=800_000_000),
     {"TransactionType": "CredentialCreate", "Subject": DEST,
      "CredentialType": CRED_TYPE, "URI": str_to_hex("ipfs://c"),
      "Expiration": 800_000_000}),
    ("cred_accept", "submit_credential_accept",
     dict(subject_seed=SEED, issuer=ISSUER, credential_type=CRED_TYPE),
     {"TransactionType": "CredentialAccept", "Issuer": ISSUER,
      "CredentialType": CRED_TYPE}),
    ("cred_delete", "submit_credential_delete",
     dict(wallet_seed=SEED, issuer=ISSUER, subject=DEST, credential_type=CRED_TYPE),
     {"TransactionType": "CredentialDelete", "Issuer": ISSUER, "Subject": DEST,
      "CredentialType": CRED_TYPE}),
    ("domain_delete", "submit_permissioned_domain_delete",
     dict(owner_seed=SEED, domain_id=HASH64),
     {"TransactionType": "PermissionedDomainDelete", "DomainID": HASH64}),
    ("mpt_create", "submit_mpt_issuance_create",
     dict(wallet_seed=SEED, maximum_amount="1000", asset_scale=2, transfer_fee=100,
          can_transfer=True),
     {"TransactionType": "MPTokenIssuanceCreate", "MaximumAmount": "1000",
      "AssetScale": 2, "TransferFee": 100, "Flags": 0x20}),
    ("mpt_create_plain", "submit_mpt_issuance_create",
     dict(wallet_seed=SEED, maximum_amount="1000", can_transfer=False),
     {"TransactionType": "MPTokenIssuanceCreate", "MaximumAmount": "1000"}),
    ("mpt_authorize", "submit_mpt_authorize",
     dict(holder_seed=SEED, issuance_id=MPT_ID),
     {"TransactionType": "MPTokenAuthorize", "MPTokenIssuanceID": MPT_ID}),
    ("mpt_unauthorize", "submit_mpt_authorize",
     dict(holder_seed=SEED, issuance_id=MPT_ID, unauthorize=True),
     {"TransactionType": "MPTokenAuthorize", "Flags": 0x01}),
    ("mpt_payment", "submit_mpt_payment",
     dict(issuer_seed=SEED, destination=DEST, issuance_id=MPT_ID, amount="25"),
     {"TransactionType": "Payment", "Destination": DEST,
      "Amount": {"mpt_issuance_id": MPT_ID, "value": "25"}}),
    ("offer_create_xrp_iou", "submit_offer_create",
     dict(wallet_seed=SEED, taker_pays_currency="LAB", taker_pays_value="10",
          taker_pays_issuer=ISSUER, taker_gets_currency="XRP", taker_gets_value="5",
          taker_gets_issuer=""),
     {"TransactionType": "OfferCreate", "TakerPays": IOU, "TakerGets": "5000000"}),
    ("offer_cancel", "submit_offer_cancel",
     dict(wallet_seed=SEED, offer_sequence=44),
     {"TransactionType": "OfferCancel", "OfferSequence": 44}),
    ("permissioned_offer", "submit_permissioned_offer_create",
     dict(wallet_seed=SEED, taker_pays_currency="LAB", taker_pays_value="10",
          taker_pays_issuer=ISSUER, taker_gets_currency="XRP", taker_gets_value="5",
          taker_gets_issuer="", domain_id=HASH64, hybrid=True),
     {"TransactionType": "OfferCreate", "DomainID": HASH64,
      "Flags": int(OfferCreateFlag.TF_HYBRID)}),
    ("amm_deposit", "submit_amm_deposit",
     dict(wallet_seed=SEED, asset_a_currency="XRP", asset_a_value="10",
          asset_a_issuer="", asset_b_currency="LAB", asset_b_value="10",
          asset_b_issuer=ISSUER),
     {"TransactionType": "AMMDeposit", "Amount": "10000000", "Amount2": IOU,
      "Flags": int(AMMDepositFlag.TF_TWO_ASSET)}),
    ("amm_withdraw_all", "submit_amm_withdraw",
     dict(wallet_seed=SEED, asset_a_currency="XRP", asset_a_issuer="",
          asset_b_currency="LAB", asset_b_issuer=ISSUER),
     {"TransactionType": "AMMWithdraw",
      "Flags": int(AMMWithdrawFlag.TF_WITHDRAW_ALL)}),
]


@pytest.mark.parametrize("cid,method,kwargs,expected", CASES, ids=[c[0] for c in CASES])
async def test_submit_builds_expected_tx(monkeypatch, cid, method, kwargs, expected):
    env = install(monkeypatch)
    t = make_transport()
    result = await getattr(t, method)(**kwargs)

    assert result.success is True, result.error
    assert result.txid == TXID
    assert result.result_code == "tesSUCCESS"
    assert result.ledger_index == 12345678
    assert result.fee == "12"
    assert result.sequence == PINNED_SEQ
    # testnet explorer link is built from the txid
    assert result.explorer_url == f"https://testnet.xrpl.org/transactions/{TXID}"

    assert len(env.submitted) == 1
    wire = env.xrpl()
    assert wire["Account"] == ADDR
    for key, value in expected.items():
        assert wire.get(key) == value, f"{cid}: {key} -> {wire.get(key)!r}"
    # the Sequence was pinned BEFORE submit (duplicate-submission protection)
    assert env.tx.sequence == PINNED_SEQ
    # pre-sign was unavailable (autofill raised) -> unsigned tx + wallet handed over
    assert env.submitted[0][1] is not None
    assert env.submitted[0][1].address == ADDR


async def test_unset_optional_fields_are_omitted(monkeypatch):
    env = install(monkeypatch)
    await make_transport().submit_payment(SEED, DEST, "1")
    wire = env.xrpl()
    for absent in ("DestinationTag", "SourceTag", "Memos", "CredentialIds"):
        assert absent not in wire


async def test_payment_with_credential_ids(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_payment(SEED, DEST, "1", credential_ids=[HASH64, HASH64_B])
    assert r.success
    assert env.tx.credential_ids == [HASH64, HASH64_B]


async def test_nft_mint_default_flags_and_nft_id_extracted(monkeypatch):
    nft_id = "000800" + "11" * 29
    meta = {"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "NFTokenPage",
        "NewFields": {"NFTokens": [{"NFToken": {"NFTokenID": nft_id}}]},
    }}]}
    env = install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_nft_mint(SEED, "")
    assert r.success and r.nft_id == nft_id
    wire = env.xrpl()
    assert wire["TransactionType"] == "NFTokenMint"
    assert wire["Flags"] == int(NFTokenMintFlag.TF_TRANSFERABLE)
    assert "URI" not in wire and "TransferFee" not in wire


async def test_nft_mint_extract_failure_is_swallowed(monkeypatch):
    # get_nftoken_id raises TypeError without AffectedNodes: the tx still succeeded.
    install(monkeypatch)
    r = await make_transport().submit_nft_mint(SEED, "ipfs://x", transferable=False)
    assert r.success is True
    assert r.nft_id == ""


async def test_channel_create_extracts_channel_id(monkeypatch):
    meta = {"AffectedNodes": [
        {"ModifiedNode": {"LedgerEntryType": "AccountRoot"}},
        {"CreatedNode": {"LedgerEntryType": "PayChannel", "LedgerIndex": HASH64}},
    ]}
    install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_payment_channel_create(SEED, "1", DEST, 30, "")
    assert r.success and r.channel_id == HASH64


async def test_check_create_extracts_check_id(monkeypatch):
    meta = {"AffectedNodes": [
        {"CreatedNode": {"LedgerEntryType": "Check", "LedgerIndex": HASH64_B}},
    ]}
    install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_check_create(SEED, DEST, "1")
    assert r.success and r.check_id == HASH64_B


async def test_mpt_create_extracts_issuance_id_from_meta(monkeypatch):
    install(monkeypatch, submit=submit_ok(meta={"mpt_issuance_id": MPT_ID}))
    r = await make_transport().submit_mpt_issuance_create(SEED, "100")
    assert r.success and r.mpt_issuance_id == MPT_ID


async def test_mpt_create_extracts_issuance_id_from_created_node(monkeypatch):
    meta = {"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "MPTokenIssuance", "LedgerIndex": "FF" * 24,
        "NewFields": {"Issuer": ADDR},
    }}]}
    install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_mpt_issuance_create(SEED, "100")
    assert r.mpt_issuance_id == "FF" * 24


async def test_permissioned_domain_set_create_extracts_domain_id(monkeypatch):
    meta = {"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "PermissionedDomain", "LedgerIndex": HASH64, "NewFields": {},
    }}]}
    env = install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_permissioned_domain_set(
        SEED, [(ISSUER, CRED_TYPE)]
    )
    assert r.success and r.domain_id == HASH64
    wire = env.xrpl()
    assert wire["TransactionType"] == "PermissionedDomainSet"
    assert "DomainID" not in wire
    assert wire["AcceptedCredentials"] == [
        {"Credential": {"Issuer": ISSUER, "CredentialType": CRED_TYPE}}
    ]


async def test_permissioned_domain_set_domain_id_prefers_newfields(monkeypatch):
    meta = {"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "PermissionedDomain", "LedgerIndex": HASH64,
        "NewFields": {"DomainID": HASH64_B},
    }}]}
    install(monkeypatch, submit=submit_ok(meta=meta))
    r = await make_transport().submit_permissioned_domain_set(SEED, [(ISSUER, CRED_TYPE)])
    assert r.domain_id == HASH64_B


async def test_permissioned_domain_set_modify_echoes_supplied_id(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_permissioned_domain_set(
        SEED, [(ISSUER, CRED_TYPE)], domain_id=HASH64
    )
    assert r.success and r.domain_id == HASH64
    assert env.xrpl()["DomainID"] == HASH64


async def test_permissioned_offer_sequence_comes_from_submit_response(monkeypatch):
    install(monkeypatch)
    r = await make_transport().submit_permissioned_offer_create(
        SEED, "LAB", "10", ISSUER, "XRP", "5", "", HASH64
    )
    assert r.success
    assert r.offer_sequence == PINNED_SEQ


async def test_permissioned_offer_no_sequence_on_failure(monkeypatch):
    bad = submit_ok()
    bad["meta"]["TransactionResult"] = "tecNO_PERMISSION"
    install(monkeypatch, submit=bad)
    r = await make_transport().submit_permissioned_offer_create(
        SEED, "LAB", "10", ISSUER, "XRP", "5", "", HASH64
    )
    assert r.success is False
    assert r.offer_sequence is None
    assert r.result_code == "tecNO_PERMISSION"


async def test_nft_create_offer_sell_and_recovers_offer_index(monkeypatch):
    offer_idx = "EE" * 32
    tx_meta = {"AffectedNodes": [
        {"CreatedNode": {"LedgerEntryType": "AccountRoot", "LedgerIndex": "00" * 32}},
        {"CreatedNode": {"LedgerEntryType": "NFTokenOffer", "LedgerIndex": offer_idx}},
    ]}
    env = install(monkeypatch, results={"Tx": {
        "hash": TXID, "meta": {"TransactionResult": "tesSUCCESS", **tx_meta},
        "tx_json": {"TransactionType": "NFTokenCreateOffer", "Account": ADDR},
        "validated": True,
    }})
    r = await make_transport().submit_nft_create_offer(
        SEED, HASH64, "2", sell=True, destination=DEST
    )
    assert r.success and r.nft_offer_index == offer_idx
    wire = env.xrpl()
    assert wire["TransactionType"] == "NFTokenCreateOffer"
    assert wire["NFTokenID"] == HASH64 and wire["Amount"] == "2000000"
    assert wire["Flags"] == int(NFTokenCreateOfferFlag.TF_SELL_NFTOKEN)
    assert wire["Destination"] == DEST
    assert "Owner" not in wire
    assert env.client.names().count("Tx") == 1


async def test_nft_create_offer_buy_names_owner_and_iou_amount(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_nft_create_offer(
        SEED, HASH64, "10", sell=False, owner=DEST, currency="LAB", issuer=ISSUER
    )
    assert r.success is True
    wire = env.xrpl()
    assert wire["Owner"] == DEST
    assert wire["Amount"] == IOU
    assert "Flags" not in wire or wire["Flags"] == 0


async def test_nft_create_offer_recovery_failure_is_nonfatal(monkeypatch):
    # fetch_tx swallows RPC errors into fetch_error; the offer is still reported.
    install(monkeypatch, results={"Tx": RuntimeError("boom")})
    r = await make_transport().submit_nft_create_offer(SEED, HASH64, "1")
    assert r.success is True
    assert r.nft_offer_index == ""


async def test_nft_create_offer_recovery_exception_is_caught(monkeypatch):
    install(monkeypatch)
    t = make_transport()

    async def _boom(txid):
        raise RuntimeError("fetch exploded")

    monkeypatch.setattr(t, "fetch_tx", _boom)
    r = await t.submit_nft_create_offer(SEED, HASH64, "1")
    assert r.success is True and r.nft_offer_index == ""


async def test_amm_withdraw_lp_token_mode_uses_pool_lp_currency(monkeypatch):
    lp = "AB" * 20
    env = install(monkeypatch, results={"AMMInfo": {"amm": {
        "account": DEST,
        "amount": "100000000",
        "amount2": {"currency": "LAB", "issuer": ISSUER, "value": "100"},
        "lp_token": {"currency": lp, "issuer": DEST, "value": "100"},
        "trading_fee": 500,
    }}})
    r = await make_transport().submit_amm_withdraw(
        SEED, "XRP", "", "LAB", ISSUER, lp_token_value="7"
    )
    assert r.success
    wire = env.xrpl()
    assert wire["LPTokenIn"] == {"currency": lp, "issuer": DEST, "value": "7"}
    assert wire["Flags"] == int(AMMWithdrawFlag.TF_LP_TOKEN)


async def test_amm_withdraw_lp_token_mode_without_pool_fails_cleanly(monkeypatch):
    env = install(monkeypatch, results={"AMMInfo": {"error": "actNotFound"}})
    r = await make_transport().submit_amm_withdraw(
        SEED, "XRP", "", "LAB", ISSUER, lp_token_value="7"
    )
    assert r.success is False and r.result_code == "tecAMM_NOT_FOUND"
    assert env.submitted == []


async def test_multisig_payment_combines_signatures_without_owner_key(monkeypatch):
    env = install(monkeypatch, autofill="fill")
    r = await make_transport().submit_multisig_payment(
        owner_address=DEST, destination=HOLDER, amount="2",
        signer_seeds=[SEED, SEED2], memo="m",
    )
    assert r.success is True
    assert len(env.autofill_calls) >= 1
    wire = env.xrpl()
    assert wire["TransactionType"] == "Payment"
    assert wire["Account"] == DEST          # owner never signs
    assert wire["SigningPubKey"] == ""
    assert wire["Amount"] == "2000000"
    signers = {s["Signer"]["Account"] for s in wire["Signers"]}
    assert signers == {ADDR, ADDR2}
    # fee scales with signer count (base 10 * (1 + 2)) per fake autofill
    assert wire["Fee"] == "30"
    # already-signed: no wallet is handed to submit_and_wait
    assert env.submitted[0][1] is None


async def test_multisig_payment_rejects_empty_signers(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_multisig_payment(DEST, HOLDER, "1", [])
    assert r.success is False and r.result_code == "temMALFORMED"
    assert env.submitted == []


async def test_multisig_payment_rejects_non_numeric_amount(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_multisig_payment(DEST, HOLDER, "abc", [SEED])
    assert r.result_code == "local_error" and "Invalid amount" in r.error
    assert env.submitted == []


async def test_multisig_payment_bad_signer_seed_is_local_error(monkeypatch):
    env = install(monkeypatch)
    r = await make_transport().submit_multisig_payment(DEST, HOLDER, "1", ["notaseed"])
    assert r.result_code == "local_error" and r.error
    assert env.submitted == []


async def test_multisig_payment_autofill_failure_is_local_error(monkeypatch):
    env = install(monkeypatch, autofill="raise")
    r = await make_transport().submit_multisig_payment(DEST, HOLDER, "1", [SEED])
    assert r.result_code == "local_error"
    assert "autofill unavailable" in r.error
    assert env.submitted == []


async def test_multisig_payment_combine_failure_is_local_error(monkeypatch):
    from xrpl_lab.transport import xrpl_testnet as xt

    install(monkeypatch, autofill="fill")

    def _bad_multisign(*a, **k):
        raise ValueError("cannot combine")

    monkeypatch.setattr(xt, "multisign", _bad_multisign)
    r = await make_transport().submit_multisig_payment(DEST, HOLDER, "1", [SEED])
    assert r.result_code == "local_error" and "cannot combine" in r.error


# ── bad seed / bad input: the model never reaches the network ────────────────

_BAD_SEED_METHODS = sorted({(c[1], tuple(sorted(c[2]))) for c in CASES})


@pytest.mark.parametrize("cid,method,kwargs,expected", CASES, ids=[c[0] for c in CASES])
async def test_bad_seed_is_local_error_and_never_submits(
    monkeypatch, cid, method, kwargs, expected
):
    env = install(monkeypatch)
    seed_key = next(k for k in kwargs if k.endswith("seed"))
    bad = dict(kwargs)
    bad[seed_key] = "not-a-seed"
    result = await getattr(make_transport(), method)(**bad)
    assert result.success is False
    assert result.result_code == "local_error"
    assert result.error
    assert env.submitted == []


async def test_nft_create_offer_bad_seed_and_accept_bad_seed(monkeypatch):
    env = install(monkeypatch)
    t = make_transport()
    r = await t.submit_nft_create_offer("bad", HASH64, "1")
    assert r.result_code == "local_error"
    r = await t.submit_permissioned_domain_set("bad", [(ISSUER, CRED_TYPE)])
    assert r.result_code == "local_error"
    r = await t.submit_permissioned_offer_create(
        "bad", "LAB", "1", ISSUER, "XRP", "1", "", HASH64
    )
    assert r.result_code == "local_error"
    assert env.submitted == []


async def test_invalid_payment_amount_and_self_payment(monkeypatch):
    env = install(monkeypatch)
    t = make_transport()
    r = await t.submit_payment(SEED, DEST, "not-a-number")
    assert r.result_code == "local_error" and "Invalid amount" in r.error
    r = await t.submit_payment(SEED, ADDR, "1")
    assert r.result_code == "local_error"
    assert "same sender and destination" in r.error
    assert env.submitted == []


async def test_offer_create_invalid_xrp_amount_raises_clear_error(monkeypatch):
    env = install(monkeypatch)
    t = make_transport()
    r = await t.submit_offer_create(
        SEED, "XRP", "nope", "", "LAB", "5", ISSUER
    )
    assert r.result_code == "local_error"
    assert "Invalid XRP amount" in r.error
    assert env.submitted == []


async def test_check_cash_requires_exactly_one_of_amount_or_deliver_min(monkeypatch):
    env = install(monkeypatch)
    t = make_transport()
    r = await t.submit_check_cash(SEED, HASH64)
    assert r.result_code == "local_error"
    r = await t.submit_check_cash(SEED, HASH64, amount="1", deliver_min="1")
    assert r.result_code == "local_error"
    assert env.submitted == []


async def test_amm_create_pins_special_fee_and_bad_seed(monkeypatch):
    env = install(monkeypatch, results={"ServerState": {
        "state": {"validated_ledger": {"reserve_base": 1_000_000, "reserve_inc": 2_000_000}}
    }})
    t = make_transport()
    r = await t.submit_amm_create(SEED, "XRP", "10", "", "LAB", "10", ISSUER, trading_fee=300)
    assert r.success
    wire = env.xrpl()
    assert wire["TransactionType"] == "AMMCreate"
    assert wire["Fee"] == "2000000"
    assert wire["TradingFee"] == 300
    assert wire["Amount"] == "10000000" and wire["Amount2"] == IOU

    r2 = await t.submit_amm_create("bad", "XRP", "10", "", "LAB", "10", ISSUER)
    assert r2.result_code == "local_error"


async def test_amm_deposit_and_withdraw_bad_seed(monkeypatch):
    env = install(monkeypatch)
    t = make_transport()
    r = await t.submit_amm_deposit("bad", "XRP", "1", "", "LAB", "1", ISSUER)
    assert r.result_code == "local_error"
    r = await t.submit_amm_withdraw("bad", "XRP", "", "LAB", ISSUER)
    assert r.result_code == "local_error"
    assert env.submitted == []


_ = (WALLET, WALLET2, WALLET3)
