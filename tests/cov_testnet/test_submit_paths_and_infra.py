"""``_submit_tx`` retry/timeout/failure policy, network guards, faucet and helpers."""

from __future__ import annotations

import errno
import logging
import ssl  # noqa: F401  (keeps SSL wording tests honest about the stdlib name)

import httpx
import pytest
from xrpl.asyncio.transaction import XRPLReliableSubmissionException

from tests.cov_testnet import _fakes
from tests.cov_testnet._fakes import (
    ADDR,
    DEST,
    HASH64,
    ISSUER,
    PINNED_SEQ,
    SEED,
    TXID,
    install,
    make_transport,
    submit_ok,
)
from xrpl_lab.transport import xrpl_testnet as xt
from xrpl_lab.transport.base import SubmitResult

pytestmark = pytest.mark.asyncio


def _failed(code: str) -> dict:
    r = submit_ok()
    r["meta"]["TransactionResult"] = code
    return r


# ── result handling ──────────────────────────────────────────────────────────

async def test_non_tes_result_is_failure_with_teach_text_and_no_retry(monkeypatch):
    env = install(monkeypatch, submit=_failed("tecUNFUNDED_PAYMENT"))
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is False
    assert r.result_code == "tecUNFUNDED_PAYMENT"
    assert r.txid == TXID
    assert r.error  # explain_result_code meaning + action
    assert len(env.submitted) == 1


async def test_unknown_result_code_without_meta_uses_engine_result(monkeypatch):
    resp = {"hash": TXID, "engine_result": "terQUEUED", "tx_json": {"Fee": "10"}}
    install(monkeypatch, submit=resp)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is False and r.result_code == "terQUEUED"


async def test_sequence_none_when_response_omits_it(monkeypatch):
    resp = submit_ok()
    del resp["tx_json"]["Sequence"]
    install(monkeypatch, submit=resp)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success and r.sequence is None


async def test_extract_callback_exception_is_swallowed(monkeypatch):
    install(monkeypatch)
    t = make_transport()

    def boom(meta):
        raise RuntimeError("bad meta")

    from xrpl.models import Payment
    from xrpl.wallet import Wallet

    w = Wallet.from_seed(SEED)
    tx = Payment(account=w.address, destination=DEST, amount="1")
    r = await t._submit_tx(tx, w, "Payment", extract=boom)
    assert r.success is True and r.nft_id == ""


# ── pre-signing ──────────────────────────────────────────────────────────────

async def test_presigned_tx_is_submitted_without_wallet_and_hash_known(monkeypatch):
    env = install(monkeypatch, autofill="fill")
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success
    tx, wallet = env.submitted[0]
    assert wallet is None                      # signed locally already
    assert tx.is_signed()
    assert tx.sequence == PINNED_SEQ
    assert tx.fee == "10" and tx.last_ledger_sequence == 99_999_999
    assert tx.account == ADDR


async def test_timeout_reports_precomputed_hash_and_never_resubmits(monkeypatch):
    env = install(monkeypatch, autofill="fill", submit=TimeoutError())
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is False
    assert r.result_code == "submit_timeout"
    signed_hash = env.submitted[0][0].get_hash()
    assert r.txid == signed_hash
    assert signed_hash in r.error
    assert r.explorer_url == f"https://testnet.xrpl.org/transactions/{signed_hash}"
    assert "Not resubmitting automatically" in r.error
    assert len(env.submitted) == 1


async def test_timeout_without_presign_has_no_hash(monkeypatch):
    env = install(monkeypatch, autofill="raise", submit=TimeoutError())
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "submit_timeout" and r.txid == "" and r.explorer_url == ""
    assert len(env.submitted) == 1


# ── reliable-submission exceptions ───────────────────────────────────────────

async def test_validated_tec_is_structured_failure_with_precomputed_txid(monkeypatch):
    exc = XRPLReliableSubmissionException("Transaction failed: tecNO_PERMISSION")
    env = install(monkeypatch, autofill="fill", submit=exc)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is False and r.result_code == "tecNO_PERMISSION"
    assert r.txid == env.submitted[0][0].get_hash()
    assert r.explorer_url.endswith(r.txid)
    assert len(env.submitted) == 1          # a validated tec is never resubmitted


async def test_prelim_tem_rejection_never_retries(monkeypatch):
    exc = XRPLReliableSubmissionException("temBAD_FEE: Invalid fee")
    env = install(monkeypatch, submit=exc)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "temBAD_FEE" and r.success is False
    assert len(env.submitted) == 1


async def test_unmapped_reliable_exception_retries_then_gives_local_error(monkeypatch):
    exc = XRPLReliableSubmissionException("something transient happened")
    env = install(monkeypatch, submit=exc)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is False and r.result_code == "local_error"
    assert "something transient happened" in r.error
    assert len(env.submitted) == xt.MAX_RETRIES + 1
    # every attempt re-used the SAME pinned Sequence (no duplicate-spend path)
    assert {tx.sequence for tx, _ in env.submitted} == {PINNED_SEQ}


async def test_unmapped_reliable_exception_not_retried_when_sequence_unpinned(
    monkeypatch, caplog
):
    exc = XRPLReliableSubmissionException("something transient happened")
    env = install(monkeypatch, submit=exc)

    async def _no_seq(account, c, *a, **k):
        raise RuntimeError("account lookup failed")

    monkeypatch.setattr(xt, "get_next_valid_seq_number", _no_seq)
    with caplog.at_level(logging.WARNING):
        r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "local_error"
    assert len(env.submitted) == 1
    assert env.submitted[0][0].sequence is None
    assert "not retrying" in caplog.text


async def test_generic_error_retries_with_same_sequence_then_succeeds(monkeypatch):
    env = install(monkeypatch, submit=[ConnectionError("reset"), submit_ok()])
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is True
    assert len(env.submitted) == 2
    assert env.submitted[0][0].sequence == env.submitted[1][0].sequence == PINNED_SEQ


async def test_generic_error_exhausts_retries(monkeypatch):
    env = install(monkeypatch, submit=ConnectionRefusedError("down"))
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "local_error"
    assert "Cannot connect to RPC endpoint" in r.error
    assert len(env.submitted) == xt.MAX_RETRIES + 1


async def test_generic_error_with_tem_code_is_not_retried(monkeypatch):
    env = install(monkeypatch, submit=RuntimeError("engine said temMALFORMED"))
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "local_error" and "temMALFORMED" in r.error
    assert len(env.submitted) == 1


async def test_generic_error_not_retried_when_unpinned(monkeypatch):
    env = install(monkeypatch, submit=RuntimeError("flaky"))

    async def _no_seq(account, c, *a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(xt, "get_next_valid_seq_number", _no_seq)
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.result_code == "local_error" and "flaky" in r.error
    assert len(env.submitted) == 1


async def test_pin_sequence_skips_signed_or_already_sequenced_tx(monkeypatch):
    install(monkeypatch)
    from xrpl.models import Payment

    tx = Payment(account=ADDR, destination=DEST, amount="1", sequence=3)
    assert await xt._pin_sequence("http://x", tx, "Payment") is tx


# ── _map_reliable_submission_failure (non-expired-window parts only) ─────────

async def test_map_failure_validated_tec_and_tem():
    f = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("Transaction failed: tecPATH_DRY"))
    assert isinstance(f, SubmitResult)
    assert (f.success, f.result_code) == (False, "tecPATH_DRY")
    f2 = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("temINVALID_FLAG: nope"))
    assert f2.result_code == "temINVALID_FLAG"


async def test_map_failure_without_result_code_defers_to_retry_policy():
    assert xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("connection hiccup")) is None


async def test_structured_failure_unknown_code_still_explained():
    f = xt._structured_failure("tecMADE_UP")
    assert f.result_code == "tecMADE_UP" and f.success is False and f.error


async def test_no_retry_regex_matches_codes_not_prose():
    assert xt._is_no_retry_error("temBAD_AMOUNT happened")
    assert xt._is_no_retry_error("tefBAD_AUTH")
    assert not xt._is_no_retry_error("temporary failure, Invalid response")
    assert not xt._is_no_retry_error("")


# ── network guards ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://s.altnet.rippletest.net:51234", "testnet"),
    ("https://faucet.altnet.rippletest.net/accounts", "testnet"),
    ("https://s.devnet.rippletest.net:51234", "devnet"),
    ("https://devnet.rippletest.net", "devnet"),
    ("http://localhost:5005", "local"),
    ("http://127.0.0.1:5005", "local"),
    ("https://s1.ripple.com:51234", "mainnet"),
    ("https://xrplcluster.com", "mainnet"),
    ("https://foo.ripple.com", "mainnet"),
    ("https://example.com", "unknown"),
    ("not a url", "unknown"),
    ("", "unknown"),
    ("http://[::1", "unknown"),   # urlparse raises ValueError
])
async def test_classify_network(url, expected):
    assert xt.classify_network(url) == expected


async def test_mainnet_override_refuses_every_signing_path(monkeypatch):
    env = install(monkeypatch, url="https://s1.ripple.com:51234")
    t = make_transport()
    assert t.network_name == "mainnet"
    r = await t.submit_payment(SEED, DEST, "1")
    assert r.success is False and r.result_code == "local_error"
    assert "testnet-only" in r.error and "'mainnet'" in r.error
    assert env.submitted == [] and env.client.requests == []
    f = await t.fund_from_faucet(ADDR)
    assert f.success is False and f.code == "CONFIG_NON_TESTNET"


@pytest.mark.parametrize("url,base", [
    ("https://s.altnet.rippletest.net:51234", "https://testnet.xrpl.org/transactions/"),
    ("https://s.devnet.rippletest.net:51234", "https://devnet.xrpl.org/transactions/"),
])
async def test_explorer_url_follows_network(monkeypatch, url, base):
    install(monkeypatch, url=url)
    t = make_transport()
    assert t._explorer_url(TXID) == base + TXID
    assert t._explorer_url("") == ""


async def test_explorer_url_empty_for_local_and_unknown(monkeypatch):
    install(monkeypatch, url="http://localhost:5005")
    assert make_transport()._explorer_url(TXID) == ""
    install(monkeypatch, url="https://example.com")
    assert make_transport()._explorer_url(TXID) == ""


def _server_info(network_id):
    info = {} if network_id is None else {"network_id": network_id}
    return {"ServerInfo": {"info": info}}


@pytest.mark.parametrize("nid", [1, 2])
async def test_local_chain_verified_testnet_caches_verdict(monkeypatch, nid):
    env = install(monkeypatch, url="http://localhost:5005", results=_server_info(nid))
    t = make_transport()
    assert await t._guard_write() is None
    assert await t._guard_write() is None
    assert env.client.names() == ["ServerInfo"]       # second call hit the cache


@pytest.mark.parametrize("nid", [0, None, "1"])
async def test_local_chain_not_a_test_network_is_refused_and_cached(monkeypatch, nid):
    env = install(monkeypatch, url="http://localhost:5005", results=_server_info(nid))
    t = make_transport()
    first = await t._guard_write()
    assert first and "not a known test network" in first
    assert await t._guard_write() == first
    assert env.client.names() == ["ServerInfo"]
    r = await t.submit_payment(SEED, DEST, "1")
    assert r.result_code == "local_error" and env.submitted == []


async def test_local_chain_probe_failure_is_refused_but_not_cached(monkeypatch):
    env = install(monkeypatch, url="http://localhost:5005",
                  results={"ServerInfo": ConnectionRefusedError("down")})
    t = make_transport()
    msg = await t._guard_write()
    assert msg and "could not verify the chain identity" in msg
    assert "Cannot connect to RPC endpoint" in msg
    await t._guard_write()
    assert env.client.names() == ["ServerInfo", "ServerInfo"]   # re-probed


@pytest.mark.parametrize("val", ["1", "true", "YES"])
async def test_allow_local_env_bypasses_probe(monkeypatch, val):
    env = install(monkeypatch, url="http://localhost:5005")
    monkeypatch.setenv("XRPL_LAB_ALLOW_LOCAL", val)
    assert await make_transport()._guard_write() is None
    assert env.client.requests == []
    r = await make_transport().submit_payment(SEED, DEST, "1")
    assert r.success is True


async def test_allow_local_env_ignores_other_values(monkeypatch):
    install(monkeypatch, url="http://localhost:5005", results=_server_info(0))
    monkeypatch.setenv("XRPL_LAB_ALLOW_LOCAL", "0")
    assert await make_transport()._guard_write() is not None


# ── get_network_info ─────────────────────────────────────────────────────────

async def test_get_network_info_connected(monkeypatch):
    install(monkeypatch)

    async def _ledger(client):
        return 4242

    monkeypatch.setattr(xt, "get_latest_validated_ledger_sequence", _ledger)
    info = await make_transport().get_network_info()
    assert (info.network, info.connected, info.ledger_index) == ("testnet", True, 4242)
    assert info.rpc_url == xt.DEFAULT_RPC_URL


async def test_get_network_info_disconnected_on_error(monkeypatch):
    install(monkeypatch, url="https://s.devnet.rippletest.net:51234")

    async def _ledger(client):
        raise ConnectionError("no route")

    monkeypatch.setattr(xt, "get_latest_validated_ledger_sequence", _ledger)
    info = await make_transport().get_network_info()
    assert (info.network, info.connected, info.ledger_index) == ("devnet", False, None)


# ── faucet ───────────────────────────────────────────────────────────────────

class _HttpResp:
    def __init__(self, status=200, body=None, text="", json_error=False):
        self.status_code = status
        self._body = body
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._body


def _fake_http(monkeypatch, script):
    """Replace httpx.AsyncClient; each POST consumes the next scripted item."""
    calls = []
    items = list(script)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append((url, json))
            item = items[min(len(calls) - 1, len(items) - 1)]
            if isinstance(item, BaseException):
                raise item
            return item

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return calls


async def test_faucet_success(monkeypatch):
    install(monkeypatch)
    calls = _fake_http(monkeypatch, [_HttpResp(200, {"balance": 1000})])
    r = await make_transport().fund_from_faucet(ADDR)
    assert (r.success, r.address, r.balance, r.code) == (True, ADDR, "1000", "")
    assert r.message == "Funded from testnet faucet"
    assert calls == [(xt.DEFAULT_FAUCET_URL, {"destination": ADDR})]


async def test_faucet_success_without_balance_field(monkeypatch):
    install(monkeypatch)
    _fake_http(monkeypatch, [_HttpResp(200, {})])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success and r.balance == "unknown"


async def test_faucet_timeout_retries_then_reports(monkeypatch):
    install(monkeypatch)
    calls = _fake_http(monkeypatch, [httpx.ReadTimeout("slow")])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success is False and "timed out" in r.message and r.code == ""
    assert len(calls) == xt.MAX_RETRIES + 1


async def test_faucet_generic_error_stops_immediately(monkeypatch):
    install(monkeypatch)
    calls = _fake_http(monkeypatch, [ConnectionRefusedError("refused")])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success is False
    assert "Cannot connect to RPC endpoint" in r.message
    assert len(calls) == 1


async def test_faucet_rate_limit_tags_code_and_backs_off(monkeypatch):
    install(monkeypatch)
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(xt.asyncio, "sleep", _sleep)
    calls = _fake_http(monkeypatch, [_HttpResp(429)])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success is False and r.code == "RUNTIME_FAUCET_RATE_LIMITED"
    assert "429" in r.message
    assert len(calls) == xt.MAX_RETRIES + 1
    assert sleeps == [3, 6]      # escalating, capped by FAUCET_MAX_BACKOFF


async def test_faucet_http_error_clears_code_and_backs_off(monkeypatch):
    install(monkeypatch)
    sleeps = []

    async def _sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(xt.asyncio, "sleep", _sleep)
    calls = _fake_http(monkeypatch, [_HttpResp(429), _HttpResp(503, text="x" * 500)])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.code == ""
    assert r.message == "Faucet returned 503: " + "x" * 200
    assert len(calls) == 3 and len(sleeps) == 2


async def test_faucet_bad_json_200_is_degraded_and_recovers(monkeypatch):
    install(monkeypatch)
    calls = _fake_http(monkeypatch, [_HttpResp(200, json_error=True),
                                     _HttpResp(200, {"balance": 5})])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success and r.balance == "5" and len(calls) == 2


async def test_faucet_bad_json_200_every_time(monkeypatch):
    install(monkeypatch)
    _fake_http(monkeypatch, [_HttpResp(200, json_error=True)])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success is False and r.code == "RUNTIME_FAUCET_DEGRADED"
    assert "captive portal" in r.message


async def test_faucet_url_override_to_mainnet_is_refused(monkeypatch):
    install(monkeypatch)
    monkeypatch.setenv("XRPL_LAB_FAUCET_URL", "https://s1.ripple.com/faucet")
    calls = _fake_http(monkeypatch, [_HttpResp(200, {"balance": 1})])
    r = await make_transport().fund_from_faucet(ADDR)
    assert r.success is False and r.code == "CONFIG_NON_TESTNET"
    assert "XRPL_LAB_FAUCET_URL" in r.message
    assert calls == []


async def test_endpoint_getters_honour_env(monkeypatch):
    monkeypatch.setenv("XRPL_LAB_RPC_URL", "http://localhost:1")
    monkeypatch.setenv("XRPL_LAB_FAUCET_URL", "http://localhost:2")
    assert xt.get_rpc_url() == "http://localhost:1"
    assert xt.get_faucet_url() == "http://localhost:2"
    monkeypatch.delenv("XRPL_LAB_RPC_URL")
    monkeypatch.delenv("XRPL_LAB_FAUCET_URL")
    assert xt.get_rpc_url() == xt.DEFAULT_RPC_URL
    assert xt.get_faucet_url() == xt.DEFAULT_FAUCET_URL


# ── _rpc_client wrapper ──────────────────────────────────────────────────────

async def test_rpc_client_yields_json_rpc_client_without_connecting():
    from xrpl.asyncio.clients import AsyncJsonRpcClient

    async with xt._rpc_client("http://localhost:5005") as c:
        assert isinstance(c, AsyncJsonRpcClient)
        assert c.url == "http://localhost:5005"


# ── friendly errors / memos / extractors ────────────────────────────────────

@pytest.mark.parametrize("exc,needle", [
    (TimeoutError(), "timed out"),
    (ConnectionRefusedError(), "Cannot connect"),
    (ConnectionError("reset"), "Connection error"),
    (OSError(errno.ECONNREFUSED if errno.ECONNREFUSED == 111 else 111, "refused"),
     "Cannot connect"),
    (RuntimeError("boom ConnectError boom"), "Cannot connect"),
    (RuntimeError("the TimeoutError happened"), "timed out"),
    (RuntimeError("Operation Timed Out"), "timed out"),
    (RuntimeError("SSL handshake failed"), "SSL/TLS error"),
    (RuntimeError("bad Certificate chain"), "SSL/TLS error"),
])
async def test_friendly_error_classifies(exc, needle):
    assert needle.lower() in xt._friendly_error(exc).lower()


async def test_friendly_error_passthrough_and_no_seed_echo():
    assert xt._friendly_error(ValueError("plain message")) == "plain message"


async def test_memo_field_and_decode_roundtrip():
    assert xt._memo_field("") == []
    memos = xt._memo_field("héllo")
    assert len(memos) == 1
    assert memos[0].memo_type == b"text/plain".hex()
    assert xt._decode_memos([{"Memo": {"MemoData": memos[0].memo_data}}]) == ["héllo"]


async def test_decode_memos_shapes():
    from xrpl.models import Memo

    assert xt._decode_memos(None) == [] and xt._decode_memos([]) == []
    out = xt._decode_memos([
        {"Memo": {"MemoData": "6869"}},       # wrapped
        {"memo_data": "6F6B"},                # flat lower-case
        Memo(memo_data="796573"),             # model object
        {"Memo": {"MemoType": "AA"}},         # no data -> skipped
        {"Memo": {"MemoData": "ZZ"}},         # bad hex -> raw kept
    ])
    assert out == ["hi", "ok", "yes", "ZZ"]


async def test_decode_memos_invalid_utf8_is_replaced_not_raised():
    out = xt._decode_memos([{"Memo": {"MemoData": "FF"}}])
    assert out == ["�"]


async def test_extractors_return_empty_when_node_absent():
    for fn in (xt._extract_mpt_issuance_id, xt._extract_channel_id,
               xt._extract_domain_id, xt._extract_check_id):
        assert fn({}) == ""
        assert fn({"AffectedNodes": [{"ModifiedNode": {}}]}) == ""


async def test_extract_mpt_issuance_id_field_precedence():
    node = lambda nf, idx="IDX": {"AffectedNodes": [  # noqa: E731
        {"CreatedNode": {"LedgerEntryType": "MPTokenIssuance", "LedgerIndex": idx,
                         "NewFields": nf}}]}
    assert xt._extract_mpt_issuance_id({"mpt_issuance_id": "DIRECT", **node({})}) == "DIRECT"
    assert xt._extract_mpt_issuance_id(node({"mpt_issuance_id": "F1"})) == "F1"
    assert xt._extract_mpt_issuance_id(node({"MPTokenIssuanceID": "F2"})) == "F2"
    assert xt._extract_mpt_issuance_id(node({})) == "IDX"


async def test_extract_nft_offer_index():
    ex = xt.XRPLTestnetTransport._extract_nft_offer_index
    assert ex({}) == ""
    assert ex({"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "NFTokenOffer"}}]}) == ""
    assert ex({"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "NFTokenOffer", "LedgerIndex": HASH64}}]}) == HASH64
    assert ex({"AffectedNodes": [{"CreatedNode": {
        "LedgerEntryType": "NFTokenOffer"}}]}) == ""


async def test_parse_submit_fields_v1_and_v2_shapes():
    code, txid, fee, idx, seq = xt._parse_submit_fields(submit_ok())
    assert (code, txid, fee, idx, seq) == ("tesSUCCESS", TXID, "12", 12345678, PINNED_SEQ)
    v1 = {"engine_result": "tecFOO", "tx_json": {}, "Fee": "9", "Sequence": 4,
          "meta": {"ledger_index": "77"}}
    code, txid, fee, idx, seq = xt._parse_submit_fields({
        "engine_result": "tecFOO", "meta": {"ledger_index": "77"}, "hash": "H",
    })
    assert (code, txid, fee, idx, seq) == ("tecFOO", "H", "0", 77, None)
    assert v1  # shape documentation only


async def test_tx_body_and_amount_prefer_v2_names():
    assert xt._tx_body({"tx_json": {"A": 1}, "A": 2}) == {"A": 1}
    assert xt._tx_body({"A": 2}) == {"A": 2}
    assert xt._tx_amount_raw({"DeliverMax": "5", "Amount": "9"}) == "5"
    assert xt._tx_amount_raw({"Amount": "9"}) == "9"
    assert xt._tx_amount_raw({}) == "0"


_ = (_fakes, ISSUER)
