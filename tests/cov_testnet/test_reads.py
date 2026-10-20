"""Read methods of the testnet transport parse realistic rippled responses.

Covers the happy path, empty results, malformed entries and RPC failures for
every read (account_lines/nfts/offers/channels/objects, tx, info, AMM, ...).
"""

from __future__ import annotations

import logging

import pytest

from tests.cov_testnet._fakes import (
    ADDR,
    CRED_TYPE,
    DEST,
    HASH64,
    HASH64_B,
    HOLDER,
    ISSUER,
    MPT_ID,
    SEED,
    TXID,
    install,
    make_transport,
)

pytestmark = pytest.mark.asyncio


# ── account_lines ────────────────────────────────────────────────────────────

async def test_get_trust_lines_parses_lines(monkeypatch):
    env = install(monkeypatch, results={"AccountLines": {"lines": [
        {"account": ISSUER, "currency": "LAB", "balance": "5", "limit": "100"},
        {"account": HOLDER, "currency": "USD"},  # missing balance/limit -> defaults
    ]}})
    lines = await make_transport().get_trust_lines(ADDR)
    assert [(ln.account, ln.peer, ln.currency, ln.balance, ln.limit) for ln in lines] == [
        (ADDR, ISSUER, "LAB", "5", "100"),
        (ADDR, HOLDER, "USD", "0", "0"),
    ]
    assert env.client.of("AccountLines")[0].ledger_index == "validated"


async def test_get_trust_lines_empty_and_failure(monkeypatch, caplog):
    install(monkeypatch, results={"AccountLines": {}})
    assert await make_transport().get_trust_lines(ADDR) == []
    install(monkeypatch, results={"AccountLines": RuntimeError("rpc down")})
    with caplog.at_level(logging.WARNING):
        assert await make_transport().get_trust_lines(ADDR) == []
    assert "get_trust_lines failed" in caplog.text


# ── account_nfts ─────────────────────────────────────────────────────────────

async def test_get_account_nfts_parses_and_defaults_issuer(monkeypatch):
    from xrpl.utils import str_to_hex

    install(monkeypatch, results={"AccountNFTs": {"account_nfts": [
        {"NFTokenID": HASH64, "Issuer": ISSUER, "NFTokenTaxon": 3,
         "URI": str_to_hex("ipfs://x"), "Flags": 8, "TransferFee": 500, "nft_serial": 9},
        {"NFTokenID": HASH64_B},   # no issuer -> queried address; no URI
        {"NFTokenID": "N3", "Issuer": ISSUER, "URI": "ZZ", "NFTokenTaxon": "bad"},
    ]}})
    nfts = await make_transport().get_account_nfts(ADDR)
    assert len(nfts) == 3
    a, b, c = nfts
    assert (a.nft_id, a.issuer, a.taxon, a.uri, a.flags, a.transfer_fee, a.serial) == (
        HASH64, ISSUER, 3, "ipfs://x", 8, 500, 9)
    assert b.issuer == ADDR and b.uri == "" and b.taxon == 0
    # undecodable URI hex is kept as-is; garbage taxon coerces to 0
    assert c.uri == "ZZ" and c.taxon == 0


async def test_get_account_nfts_skips_malformed_entry(monkeypatch, caplog):
    install(monkeypatch, results={"AccountNFTs": {"account_nfts": [
        "garbage-not-a-dict",
        {"NFTokenID": HASH64, "Issuer": ISSUER},
    ]}})
    with caplog.at_level(logging.WARNING):
        nfts = await make_transport().get_account_nfts(ADDR)
    assert [n.nft_id for n in nfts] == [HASH64]
    assert "skipping malformed NFT entry" in caplog.text


async def test_get_account_nfts_rpc_failure(monkeypatch):
    install(monkeypatch, results={"AccountNFTs": RuntimeError("down")})
    assert await make_transport().get_account_nfts(ADDR) == []


# ── nft offers ───────────────────────────────────────────────────────────────

async def test_get_nft_offers_sell_and_buy_use_distinct_requests(monkeypatch):
    offers = {"offers": [
        {"nft_offer_index": "AA" * 32, "amount": "1000000", "owner": ADDR,
         "destination": DEST},
        {"index": "BB" * 32, "amount": {"currency": "LAB", "issuer": ISSUER, "value": "3"},
         "owner": HOLDER},
    ]}
    env = install(monkeypatch, results={"NFTSellOffers": offers, "NFTBuyOffers": offers})
    t = make_transport()
    sell = await t.get_nft_offers(HASH64, sell=True)
    buy = await t.get_nft_offers(HASH64, sell=False)
    assert env.client.names() == ["NFTSellOffers", "NFTBuyOffers"]
    assert all(o.is_sell for o in sell) and not any(o.is_sell for o in buy)
    o1, o2 = sell
    assert (o1.offer_index, o1.amount, o1.owner, o1.destination, o1.nft_id) == (
        "AA" * 32, "1000000", ADDR, DEST, HASH64)
    assert o2.offer_index == "BB" * 32
    assert o2.amount == "3/LAB/" + ISSUER[:12]
    assert o2.destination == ""


async def test_get_nft_offers_object_not_found_is_empty(monkeypatch):
    install(monkeypatch, results={"NFTSellOffers": RuntimeError("objectNotFound")})
    assert await make_transport().get_nft_offers(HASH64) == []


# ── default ripple / freeze ──────────────────────────────────────────────────

@pytest.mark.parametrize("flags,expected", [(0x00800000, True), (0x00400000, False), (0, False)])
async def test_has_default_ripple_reads_flag_bit(monkeypatch, flags, expected):
    install(monkeypatch, results={"AccountInfo": {"account_data": {"Flags": flags}}})
    assert await make_transport().has_default_ripple(ADDR) is expected


async def test_has_default_ripple_failure_is_false(monkeypatch):
    install(monkeypatch, results={"AccountInfo": RuntimeError("x")})
    assert await make_transport().has_default_ripple(ADDR) is False


async def test_freeze_status_individual_and_global(monkeypatch):
    env = install(monkeypatch, results={
        "AccountLines": {"lines": [
            {"account": ISSUER, "currency": "LAB", "freeze": False},
            {"account": HOLDER, "currency": "LAB", "freeze": True},
        ]},
        "AccountInfo": {"account_data": {"Flags": 0x00400000}},
    })
    st = await make_transport().get_freeze_status(ADDR, HOLDER, "LAB")
    assert (st.found, st.individual_frozen, st.global_frozen) == (True, True, True)
    req = env.client.of("AccountLines")[0]
    assert req.account == ADDR and req.peer == HOLDER


async def test_freeze_status_no_line_not_global(monkeypatch):
    install(monkeypatch, results={
        "AccountLines": {"lines": [{"account": HOLDER, "currency": "USD", "freeze": True}]},
        "AccountInfo": {"account_data": {"Flags": 0}},
    })
    st = await make_transport().get_freeze_status(ADDR, HOLDER, "LAB")
    assert (st.found, st.individual_frozen, st.global_frozen) == (False, False, False)


async def test_freeze_status_rpc_failure_defaults(monkeypatch):
    install(monkeypatch, results={"AccountLines": RuntimeError("x")})
    st = await make_transport().get_freeze_status(ADDR, HOLDER, "LAB")
    assert (st.found, st.individual_frozen, st.global_frozen) == (False, False, False)


# ── payment channels ─────────────────────────────────────────────────────────

async def test_get_account_channels_parses_and_filters_destination(monkeypatch):
    env = install(monkeypatch, results={"AccountChannels": {"channels": [{
        "channel_id": HASH64, "amount": "5000000", "balance": "1000000",
        "destination_account": DEST, "settle_delay": 60, "public_key": "ED01",
        "expiration": 800_000_000, "cancel_after": "800000100",
    }, {"channel_id": HASH64_B}]}})
    chans = await make_transport().get_account_channels(ADDR, destination=DEST)
    c1, c2 = chans
    assert (c1.channel_id, c1.amount, c1.balance, c1.destination, c1.settle_delay) == (
        HASH64, "5000000", "1000000", DEST, 60)
    assert c1.expiration == 800_000_000 and c1.cancel_after == 800_000_100
    assert (c2.amount, c2.balance, c2.settle_delay, c2.expiration) == ("0", "0", 0, None)
    assert env.client.of("AccountChannels")[0].destination_account == DEST


async def test_get_account_channels_failure(monkeypatch):
    install(monkeypatch, results={"AccountChannels": RuntimeError("x")})
    assert await make_transport().get_account_channels(ADDR) == []


async def test_channel_claim_sign_and_verify_roundtrip():
    from xrpl.core.keypairs import derive_keypair

    t = make_transport()
    pub = derive_keypair(SEED)[0]
    sig = await t.authorize_payment_channel_claim(SEED, HASH64, "1.5")
    assert await t.verify_payment_channel_claim(HASH64, "1.5", pub, sig) is True
    # tampered amount, wrong channel, and garbage signatures all fail closed
    assert await t.verify_payment_channel_claim(HASH64, "1.6", pub, sig) is False
    assert await t.verify_payment_channel_claim(HASH64_B, "1.5", pub, sig) is False
    assert await t.verify_payment_channel_claim(HASH64, "1.5", pub, "not-hex") is False


# ── account_objects based reads ──────────────────────────────────────────────

def _objs(*objects):
    return {"AccountObjects": {"account_objects": list(objects)}}


async def test_get_signer_list(monkeypatch):
    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "Escrow"},
        {"LedgerEntryType": "SignerList", "SignerQuorum": 3, "SignerEntries": [
            {"SignerEntry": {"Account": DEST, "SignerWeight": 2}},
            {"SignerEntry": {"Account": HOLDER, "SignerWeight": "1"}},
            {"SignerEntry": {"SignerWeight": 1}},  # no account -> dropped
        ]},
    ))
    sl = await make_transport().get_signer_list(ADDR)
    assert sl.signer_quorum == 3
    assert sl.entries == [(DEST, 2), (HOLDER, 1)]


async def test_get_signer_list_absent_and_failure(monkeypatch):
    install(monkeypatch, results=_objs({"LedgerEntryType": "Escrow"}))
    assert await make_transport().get_signer_list(ADDR) is None
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_signer_list(ADDR) is None


async def test_get_did_decodes_fields(monkeypatch):
    from xrpl.utils import str_to_hex

    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "DID", "URI": str_to_hex("ipfs://d"),
         "Data": "ZZ", "DIDDocument": "doc"},
    ))
    did = await make_transport().get_did(ADDR)
    assert (did.account, did.uri, did.data, did.did_document) == (ADDR, "ipfs://d", "ZZ", "doc")


async def test_get_did_absent_and_failure(monkeypatch):
    install(monkeypatch, results=_objs({"LedgerEntryType": "Check"}))
    assert await make_transport().get_did(ADDR) is None
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_did(ADDR) is None


def _cred(**over):
    base = {"LedgerEntryType": "Credential", "Subject": DEST, "Issuer": ISSUER,
            "CredentialType": CRED_TYPE, "Flags": 0x00010000, "index": HASH64}
    base.update(over)
    return base


async def test_get_credential_accepted(monkeypatch):
    from xrpl.utils import str_to_hex

    install(monkeypatch, results=_objs(
        _cred(CredentialType=CRED_TYPE.lower(), URI=str_to_hex("u"), Expiration=123),
    ))
    c = await make_transport().get_credential(DEST, ISSUER, CRED_TYPE)  # case-insensitive
    assert c.accepted is True and c.uri == "u" and c.expiration == 123
    assert (c.subject, c.issuer, c.credential_id) == (DEST, ISSUER, HASH64)


async def test_get_credential_undecodable_uri_kept_raw(monkeypatch):
    install(monkeypatch, results=_objs(_cred(URI="ZZ")))
    c = await make_transport().get_credential(DEST, ISSUER, CRED_TYPE)
    assert c.uri == "ZZ" and c.expiration is None


async def test_get_credential_provisional_falls_back_to_issuer_objects(monkeypatch):
    def by_owner(req):
        if req.account == DEST:
            return {"account_objects": []}
        return {"account_objects": [_cred(Flags=0)]}

    env = install(monkeypatch, results={"AccountObjects": by_owner})
    c = await make_transport().get_credential(DEST, ISSUER, CRED_TYPE)
    assert c is not None and c.accepted is False
    assert [r.account for r in env.client.of("AccountObjects")] == [DEST, ISSUER]


@pytest.mark.parametrize("over", [
    {"LedgerEntryType": "Check"},
    {"Subject": HOLDER},
    {"Issuer": HOLDER},
    {"CredentialType": "FFFF"},
])
async def test_get_credential_mismatches_return_none(monkeypatch, over):
    install(monkeypatch, results=_objs(_cred(**over)))
    assert await make_transport().get_credential(DEST, ISSUER, CRED_TYPE) is None


async def test_get_credential_rpc_failure_skips_both_owners(monkeypatch):
    env = install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_credential(DEST, ISSUER, CRED_TYPE) is None
    assert len(env.client.of("AccountObjects")) == 2


async def test_get_permissioned_domains(monkeypatch):
    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "PermissionedDomain", "index": HASH64,
         "AcceptedCredentials": [
             {"Credential": {"Issuer": ISSUER, "CredentialType": "4b5943"}},
             {"Issuer": HOLDER, "CredentialType": "AA"},   # unwrapped shape
             {"Credential": {"CredentialType": "BB"}},      # no issuer -> dropped
         ]},
        {"LedgerEntryType": "PermissionedDomain", "DomainID": HASH64_B,
         "AcceptedCredentials": []},
        {"LedgerEntryType": "Escrow"},
    ))
    doms = await make_transport().get_permissioned_domains(ADDR)
    assert [d.domain_id for d in doms] == [HASH64, HASH64_B]
    assert doms[0].owner == ADDR
    assert doms[0].accepted_credentials == [(ISSUER, "4B5943"), (HOLDER, "AA")]
    assert doms[1].accepted_credentials == []


async def test_get_permissioned_domains_failure(monkeypatch):
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_permissioned_domains(ADDR) == []


async def test_get_mpt_balance(monkeypatch):
    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "MPToken", "MPTokenIssuanceID": "OTHER", "MPTAmount": "9"},
        {"LedgerEntryType": "Escrow"},
        {"LedgerEntryType": "MPToken", "mpt_issuance_id": MPT_ID, "MPTAmount": "25"},
    ))
    assert await make_transport().get_mpt_balance(ADDR, MPT_ID) == "25"
    assert await make_transport().get_mpt_balance(ADDR, "00" * 24) == "0"


async def test_get_mpt_balance_zero_and_failure(monkeypatch):
    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "MPToken", "MPTokenIssuanceID": MPT_ID}))
    assert await make_transport().get_mpt_balance(ADDR, MPT_ID) == "0"
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_mpt_balance(ADDR, MPT_ID) == "0"


async def test_get_mpt_issuances(monkeypatch):
    install(monkeypatch, results=_objs(
        {"LedgerEntryType": "MPTokenIssuance", "mpt_issuance_id": MPT_ID,
         "MaximumAmount": "1000", "AssetScale": 2, "TransferFee": 100, "Flags": 0x20,
         "OutstandingAmount": "40"},
        {"LedgerEntryType": "MPTokenIssuance", "MPTokenIssuanceID": "00" * 24},
        {"LedgerEntryType": "MPToken"},
    ))
    iss = await make_transport().get_mpt_issuances(ADDR)
    assert len(iss) == 2
    a, b = iss
    assert (a.issuance_id, a.maximum_amount, a.asset_scale, a.transfer_fee,
            a.flags, a.outstanding_amount) == (MPT_ID, "1000", 2, 100, 0x20, "40")
    assert (b.issuance_id, b.maximum_amount, b.asset_scale, b.outstanding_amount) == (
        "00" * 24, "0", 0, "0")


async def test_get_mpt_issuances_failure(monkeypatch):
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_mpt_issuances(ADDR) == []


# ── escrows (account_objects + account_tx join) ──────────────────────────────

def _escrow(prev, **over):
    base = {"LedgerEntryType": "Escrow", "Amount": "3000000", "Destination": DEST,
            "FinishAfter": 800_000_000, "CancelAfter": "800000100", "PreviousTxnID": prev}
    base.update(over)
    return base


async def test_get_escrows_joins_create_sequence_via_account_tx(monkeypatch):
    env = install(monkeypatch, results={
        **_objs(
            _escrow(HASH64),
            _escrow(HASH64_B, Amount={"currency": "LAB", "issuer": ISSUER, "value": "2"},
                    Condition="A025"),
            _escrow("77" * 32),                 # create not in history -> sequence 0
            {"LedgerEntryType": "SignerList"},
        ),
        "AccountTx": {"transactions": [
            {"tx": {"TransactionType": "EscrowCreate", "Sequence": 11, "hash": HASH64}},
            {"tx_json": {"TransactionType": "EscrowCreate", "Sequence": 12},
             "hash": HASH64_B},                                    # API v2 shape
            {"tx": {"TransactionType": "Payment", "Sequence": 99, "hash": "77" * 32}},
            {"tx": {"TransactionType": "EscrowCreate", "Sequence": "x", "hash": "88" * 32}},
        ]},
    })
    escrows = await make_transport().get_escrows(ADDR)
    assert [e.sequence for e in escrows] == [11, 12, 0]
    e1, e2, _ = escrows
    assert (e1.amount, e1.destination, e1.finish_after, e1.cancel_after, e1.condition) == (
        "3000000", DEST, 800_000_000, 800_000_100, "")
    assert e2.amount == "2/LAB/" + ISSUER[:12] and e2.condition == "A025"
    assert env.client.of("AccountTx")[0].limit == 200


async def test_escrow_create_sequences_paginate_with_marker(monkeypatch):
    pages = [
        {"transactions": [{"tx": {"TransactionType": "EscrowCreate", "Sequence": 1,
                                  "hash": HASH64}}], "marker": {"ledger": 5, "seq": 1}},
        {"transactions": [{"tx": {"TransactionType": "EscrowCreate", "Sequence": 2,
                                  "hash": HASH64_B}}]},
    ]
    it = iter(pages)
    env = install(monkeypatch, results={"AccountTx": lambda req: next(it)})
    index = await make_transport()._escrow_create_sequences(ADDR)
    assert index == {HASH64: 1, HASH64_B: 2}
    reqs = env.client.of("AccountTx")
    assert len(reqs) == 2 and reqs[0].marker is None and reqs[1].marker is not None


async def test_escrow_create_sequences_bounded_to_ten_pages(monkeypatch):
    env = install(monkeypatch, results={"AccountTx": {"transactions": [], "marker": {"x": 1}}})
    assert await make_transport()._escrow_create_sequences(ADDR) == {}
    assert len(env.client.of("AccountTx")) == 10


async def test_escrow_create_sequences_failure_is_empty_map(monkeypatch):
    install(monkeypatch, results={"AccountTx": RuntimeError("x")})
    assert await make_transport()._escrow_create_sequences(ADDR) == {}


async def test_get_escrows_account_tx_failure_leaves_sequence_zero(monkeypatch):
    install(monkeypatch, results={**_objs(_escrow(HASH64)),
                                  "AccountTx": RuntimeError("x")})
    escrows = await make_transport().get_escrows(ADDR)
    assert [e.sequence for e in escrows] == [0]


async def test_get_escrows_objects_failure(monkeypatch):
    install(monkeypatch, results={"AccountObjects": RuntimeError("x")})
    assert await make_transport().get_escrows(ADDR) == []


# ── offers / account info / balance ─────────────────────────────────────────

async def test_get_account_offers_parses_and_skips_malformed(monkeypatch):
    install(monkeypatch, results={"AccountOffers": {"offers": [
        {"seq": 7, "taker_pays": "1000000",
         "taker_gets": {"currency": "LAB", "issuer": ISSUER, "value": "4"},
         "quality": "4000000"},
        {"Sequence": "9", "taker_pays": "5", "taker_gets": "6"},
        "garbage",
    ]}})
    offers = await make_transport().get_account_offers(ADDR)
    assert [o.sequence for o in offers] == [7, 9]
    assert offers[0].taker_pays == "1000000"
    assert offers[0].taker_gets == "4/LAB/" + ISSUER[:12]
    assert offers[0].quality == "4000000" and offers[1].quality == ""


async def test_get_account_offers_failure(monkeypatch):
    install(monkeypatch, results={"AccountOffers": RuntimeError("x")})
    assert await make_transport().get_account_offers(ADDR) == []


async def test_get_account_info(monkeypatch):
    install(monkeypatch, results={"AccountInfo": {"account_data": {
        "Balance": "123456", "OwnerCount": 3, "Sequence": 77}}})
    snap = await make_transport().get_account_info(ADDR)
    assert (snap.address, snap.balance_drops, snap.owner_count, snap.sequence) == (
        ADDR, "123456", 3, 77)


async def test_get_account_info_failure_returns_blank_snapshot(monkeypatch):
    install(monkeypatch, results={"AccountInfo": RuntimeError("actNotFound")})
    snap = await make_transport().get_account_info(ADDR)
    assert (snap.address, snap.balance_drops, snap.owner_count, snap.sequence) == (
        ADDR, "0", 0, 0)


async def test_get_balance_converts_drops_to_xrp(monkeypatch):
    install(monkeypatch, results={"AccountInfo": {"account_data": {"Balance": "12500000"}}})
    assert await make_transport().get_balance(ADDR) == "12.500000"


async def test_get_balance_missing_and_failure(monkeypatch):
    install(monkeypatch, results={"AccountInfo": {}})
    assert await make_transport().get_balance(ADDR) == "0.000000"
    install(monkeypatch, results={"AccountInfo": RuntimeError("x")})
    assert await make_transport().get_balance(ADDR) == "0"


async def test_get_reserves(monkeypatch):
    install(monkeypatch, results={"ServerState": {"state": {"validated_ledger": {
        "reserve_base": 1000000, "reserve_inc": "200000"}}}})
    assert await make_transport().get_reserves() == (1000000, 200000)


async def test_get_reserves_missing_fields_and_failure(monkeypatch):
    install(monkeypatch, results={"ServerState": {"state": {"validated_ledger": {
        "reserve_base": 1000000}}}})
    assert await make_transport().get_reserves() is None
    install(monkeypatch, results={"ServerState": RuntimeError("x")})
    assert await make_transport().get_reserves() is None


# ── fetch_tx ─────────────────────────────────────────────────────────────────

def _tx_result(**over):
    r = {
        "hash": TXID, "ledger_index": 100, "validated": True,
        "meta": {"TransactionResult": "tesSUCCESS", "delivered_amount": "9000000"},
        "tx_json": {"TransactionType": "Payment", "Account": ADDR, "Destination": DEST,
                    "DeliverMax": "10000000", "Fee": "12", "DestinationTag": 5,
                    "SourceTag": "6",
                    "Memos": [{"Memo": {"MemoData": "68656C6C6F"}}]},
    }
    r.update(over)
    return r


async def test_fetch_tx_parses_api_v2_shape(monkeypatch):
    env = install(monkeypatch, results={"Tx": _tx_result()})
    info = await make_transport().fetch_tx(TXID)
    assert env.client.of("Tx")[0].transaction == TXID
    assert (info.txid, info.tx_type, info.account, info.destination) == (
        TXID, "Payment", ADDR, DEST)
    assert (info.amount, info.fee, info.result_code, info.ledger_index) == (
        "10000000", "12", "tesSUCCESS", 100)
    assert info.delivered_amount == "9000000"
    assert info.memos == ["hello"] and info.validated is True
    assert (info.destination_tag, info.source_tag) == (5, 6)
    assert info.fetch_error is None


async def test_fetch_tx_delivered_amount_variants(monkeypatch):
    base = _tx_result()
    base["meta"] = {"TransactionResult": "tesSUCCESS", "delivered_amount": "unavailable"}
    install(monkeypatch, results={"Tx": base})
    assert (await make_transport().fetch_tx(TXID)).delivered_amount == "unavailable"

    base["meta"] = {"TransactionResult": "tesSUCCESS", "delivered_amount":
                    {"currency": "LAB", "issuer": ISSUER, "value": "2"}}
    install(monkeypatch, results={"Tx": base})
    assert (await make_transport().fetch_tx(TXID)).delivered_amount == "2/LAB/" + ISSUER[:12]

    base["meta"] = {"TransactionResult": "tesSUCCESS"}
    install(monkeypatch, results={"Tx": base})
    assert (await make_transport().fetch_tx(TXID)).delivered_amount == ""


async def test_fetch_tx_ledger_index_fallbacks(monkeypatch):
    r = _tx_result()
    del r["ledger_index"]
    r["inLedger"] = 55
    install(monkeypatch, results={"Tx": r})
    assert (await make_transport().fetch_tx(TXID)).ledger_index == 55
    del r["inLedger"]
    r["meta"] = {"TransactionResult": "tesSUCCESS", "ledger_index": "66"}
    install(monkeypatch, results={"Tx": r})
    assert (await make_transport().fetch_tx(TXID)).ledger_index == 66


async def test_fetch_tx_v1_flat_shape(monkeypatch):
    flat = {"TransactionType": "Payment", "Account": ADDR, "Destination": DEST,
            "Amount": "42", "Fee": "10", "ledger_index": 9,
            "meta": {"TransactionResult": "tecUNFUNDED_PAYMENT"}}
    install(monkeypatch, results={"Tx": flat})
    info = await make_transport().fetch_tx(TXID)
    assert (info.tx_type, info.amount, info.result_code) == ("Payment", "42", "tecUNFUNDED_PAYMENT")
    assert info.validated is False and info.memos == []


async def test_fetch_tx_timeout_sets_fetch_error_not_result_code(monkeypatch):
    install(monkeypatch, results={"Tx": TimeoutError()})
    info = await make_transport().fetch_tx(TXID)
    assert info.txid == TXID
    assert info.result_code == ""
    assert "Timed out" in info.fetch_error


async def test_fetch_tx_other_error_is_friendly_fetch_error(monkeypatch):
    install(monkeypatch, results={"Tx": ConnectionRefusedError("nope")})
    info = await make_transport().fetch_tx(TXID)
    assert info.result_code == ""
    assert "Cannot connect to RPC endpoint" in info.fetch_error


# ── AMM reads ────────────────────────────────────────────────────────────────

def _amm(**over):
    amm = {"account": DEST, "amount": "100000000",
           "amount2": {"currency": "LAB", "issuer": ISSUER, "value": "100"},
           "lp_token": {"currency": "AB" * 20, "issuer": DEST, "value": "100"},
           "trading_fee": 500}
    amm.update(over)
    return {"AMMInfo": {"amm": amm}}


async def test_get_amm_info_parses_pool(monkeypatch):
    env = install(monkeypatch, results=_amm())
    info = await make_transport().get_amm_info("XRP", "", "LAB", ISSUER)
    assert (info.asset_a, info.asset_b) == ("XRP", f"LAB/{ISSUER}")
    assert (info.pool_a, info.pool_b) == ("100", "100")
    assert (info.lp_token_currency, info.lp_token_issuer, info.lp_supply) == (
        "AB" * 20, DEST, "100")
    assert info.trading_fee == "500"
    assert (info.asset_a_issuer, info.asset_b_issuer) == ("", ISSUER)
    assert env.client.names() == ["AMMInfo"]


async def test_get_amm_info_lp_issuer_falls_back_to_amm_account(monkeypatch):
    install(monkeypatch, results=_amm(lp_token={"currency": "AB" * 20, "value": "5"}))
    info = await make_transport().get_amm_info("XRP", "", "LAB", ISSUER)
    assert info.lp_token_issuer == DEST and info.lp_supply == "5"


@pytest.mark.parametrize("err", ["actNotFound", "entryNotFound", "somethingElse"])
async def test_get_amm_info_error_results_are_none(monkeypatch, err):
    install(monkeypatch, results={"AMMInfo": {"error": err}})
    assert await make_transport().get_amm_info("XRP", "", "LAB", ISSUER) is None


async def test_get_amm_info_non_dict_amm_and_rpc_failure(monkeypatch):
    install(monkeypatch, results={"AMMInfo": {"amm": "weird"}})
    assert await make_transport().get_amm_info("XRP", "", "LAB", ISSUER) is None
    install(monkeypatch, results={"AMMInfo": RuntimeError("x")})
    assert await make_transport().get_amm_info("XRP", "", "LAB", ISSUER) is None


async def test_amm_create_fee_probe_variants(monkeypatch):
    t = make_transport()
    install(monkeypatch, results={"ServerState": {"state": {"validated_ledger": {
        "reserve_inc": 2000000}}}})
    assert await t._amm_create_fee_drops() == "2000000"
    install(monkeypatch, results={"ServerState": {"state": {"validated_ledger": {}}}})
    assert await t._amm_create_fee_drops() is None
    install(monkeypatch, results={"ServerState": RuntimeError("x")})
    assert await t._amm_create_fee_drops() is None


async def test_amm_create_fee_unpinned_when_probe_fails(monkeypatch):
    env = install(monkeypatch, results={"ServerState": RuntimeError("x")})
    r = await make_transport().submit_amm_create(SEED, "XRP", "1", "", "LAB", "1", ISSUER)
    assert r.success
    assert env.tx.fee is None  # autofill supplies the identical figure at submit


async def test_get_lp_token_balance(monkeypatch):
    lp = "AB" * 20
    install(monkeypatch, results={"AccountLines": {"lines": [
        {"account": HOLDER, "currency": lp, "balance": "9"},
        {"account": DEST, "currency": lp, "balance": "12.5"},
    ]}})
    t = make_transport()
    assert await t.get_lp_token_balance(ADDR, lp, DEST) == "12.5"
    assert await t.get_lp_token_balance(ADDR, "XX", DEST) == "0"


async def test_get_lp_token_balance_failure(monkeypatch):
    install(monkeypatch, results={"AccountLines": RuntimeError("x")})
    assert await make_transport().get_lp_token_balance(ADDR, "AB" * 20, DEST) == "0"


# ── pure helpers ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("amt,expected", [
    ("100000000", "100"),
    ("12", "0.000012"),
    ("1500000", "1.5"),
    ({"currency": "LAB", "issuer": ISSUER, "value": "7.5"}, "7.5"),
    ({"currency": "LAB"}, "0"),
    (42, "42"),
    pytest.param("not-drops", "not-drops", marks=pytest.mark.xfail(
        strict=True,
        reason="BUG: _parse_amm_amount catches (ValueError, TypeError, InvalidOperation) "
               "but drops_to_xrp raises XRPRangeException, so a non-numeric string "
               "leg escapes get_amm_info instead of being returned as-is")),
])
async def test_parse_amm_amount(amt, expected):
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    assert XRPLTestnetTransport._parse_amm_amount(amt) == expected


@pytest.mark.parametrize("amt,expected", [
    ("1000", "1000"),
    ({"value": "3", "currency": "LAB", "issuer": "rABCDEFGHIJKLMNOP"}, "3/LAB/rABCDEFGHIJK"),
    ({}, "?/?/"),
    (None, "None"),
    (5, "5"),
])
async def test_format_amount(amt, expected):
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    assert XRPLTestnetTransport._format_amount(amt) == expected


async def test_amm_asset_builds_xrp_and_issued():
    from xrpl.models.currencies import XRP, IssuedCurrency

    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    assert isinstance(XRPLTestnetTransport._amm_asset("XRP", ""), XRP)
    iss = XRPLTestnetTransport._amm_asset("LAB", ISSUER)
    assert isinstance(iss, IssuedCurrency) and iss.issuer == ISSUER


async def test_amount_obj_xrp_and_issued():
    t = make_transport()
    assert t._amount_obj("XRP", "1.5", "") == "1500000"
    iou = t._amount_obj("LAB", "3", ISSUER)
    assert (iou.currency, iou.issuer, iou.value) == ("LAB", ISSUER, "3")
    with pytest.raises(ValueError, match="Invalid XRP amount"):
        t._amount_obj("XRP", "abc", "")


async def test_parse_entry_helpers():
    from xrpl_lab.transport.xrpl_testnet import (
        _int_or_none,
        _parse_nft_entry,
        _parse_offer_entry,
        _safe_int,
    )

    assert _safe_int(None) == 0 and _safe_int("") == 0 and _safe_int("x") == 0
    assert _safe_int("12") == 12
    assert _int_or_none(None) is None and _int_or_none(True) is None
    assert _int_or_none(5) == 5 and _int_or_none("7") == 7 and _int_or_none("x") is None
    nft = _parse_nft_entry({"NFTokenID": "N", "URI": "ZZ"})
    assert nft.uri == "ZZ" and nft.issuer == ""
    offer = _parse_offer_entry({"seq": 3, "taker_pays": "9", "taker_gets": "8"})
    assert (offer.sequence, offer.taker_pays, offer.taker_gets) == (3, "9", "8")
