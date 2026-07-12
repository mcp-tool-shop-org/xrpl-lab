"""Regression tests pinning the 2026-07 re-swarm wave-2 TRANSPORT fixes.

Each test anchors one approved finding so the fix cannot silently regress:

Testnet transport (network fully mocked — no socket ever opens):
- F-1947a03d: xrpl-py 4.x ``submit_and_wait`` RAISES XRPLReliableSubmissionException
  on any VALIDATED non-tesSUCCESS ("Transaction failed: tecXXX") and on tem
  prelim rejections — the transport must parse the REAL code, surface the
  structured failure, and NEVER resubmit a validated tec (it consumed a fee +
  sequence).
- F-5e672008: rippled API v2 (xrpl-py 4.x default) nests tx fields under
  ``tx_json`` and renames Payment Amount → DeliverMax. fetch_tx and every
  submit parser must read the v2 shape (v1 kept as fallback).
- F-0cbd05ef: a client timeout must NEVER auto-resubmit (the first broadcast
  can still validate; a resubmit autofills a fresh Sequence → duplicate funds).
- F-4cf20cef: a 'local' endpoint must PROVE it fronts a test chain
  (server_info network_id 1/2) before any signed write; XRPL_LAB_ALLOW_LOCAL=1
  is the explicit opt-out.
- F-88f82c27: permissioned offer_sequence comes from the submit response's
  tx_json.Sequence, not a get_account_offers()[-1] read-back.
- F-69a13b3b: non-429 faucet HTTP errors back off between retries.

Dry-run transport (offline parity — dry-run must never mask a testnet failure):
- F-7ec2c90d: XRP conservation across escrow + payment-channel lifecycles.
- F-c0be844f: negative/zero issued, MPT, clawback, partial amounts →
  temBAD_AMOUNT (no state mutation).
- F-a4147d39: individual + global freeze ENFORCED on issued payments.
- F-8b39e89b: token-escrow issuer opt-in keyed strictly by address.
- F-cbc476b3: EscrowFinish past CancelAfter → tecNO_PERMISSION (expired).
- F-2e2975aa: credential expiration enforced (create + eligibility gate).
- F-233393c2: NFT settlement requires the buyer to fund the price.
- F-95640306: channel-claim signatures verified; close refunds the remainder.
- F-3bdd6cfa: AMM zero legs / trading-fee cap / pool deletion on last-LP exit.
- F-64106db7: unknown txids fetch as NOT FOUND, not fabricated tesSUCCESS.
- F-ebadec19: reserve floor + fee debit in the payment sim.
- F-3d812d44: re-funding ADDS 1000 XRP instead of overwriting.
- F-0feb8f21: txids are deterministic across identical sessions.
- F-1188db18: dry_run.py stays xrpl-py-free (no lazy drops_to_xrp import).
- fix1571: token EscrowCreate with neither FinishAfter nor Condition →
  temMALFORMED.
- SubmitResult.sequence: populated by both transports for the
  sequence-consuming creates.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from xrpl.asyncio.transaction import XRPLReliableSubmissionException

from xrpl_lab.transport.base import TrustLineInfo
from xrpl_lab.transport.dry_run import (
    _DRY_RUN_WALLET_ADDRESS,
    DryRunTransport,
)

_VALID_TESTNET_SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"

ISSUER = "rISSUERAAAAAAAAAAAAAAAAAAAAAAA"
HOLDER = "rHOLDERAAAAAAAAAAAAAAAAAAAAAAA"


class _FakeResponse:
    def __init__(self, result: dict) -> None:
        self.result = result


class _FakeAsyncClient:
    """Stand-in for AsyncJsonRpcClient — CM protocol only (submit is patched)."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def _patch_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from xrpl_lab.transport import xrpl_testnet as xt

    monkeypatch.setattr(xt, "AsyncJsonRpcClient", _FakeAsyncClient)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(xt.asyncio, "sleep", _no_sleep)


# A REAL captured rippled API-v2 tx response shape (tx fields under tx_json,
# Payment Amount renamed DeliverMax, hash/ledger_index/meta/validated top-level).
_V2_HASH = "V2HASH0000000000000000000000000000000000000000000000000000ABCD"


def _v2_tx_response(txid: str = _V2_HASH) -> dict:
    return {
        "close_time_iso": "2026-07-11T21:31:01Z",
        "ctid": "C09CB8E000010001",
        "hash": txid,
        "ledger_hash": "B1E2" + "0" * 60,
        "ledger_index": 10269267,
        "meta": {
            "AffectedNodes": [],
            "TransactionIndex": 1,
            "TransactionResult": "tesSUCCESS",
            "delivered_amount": "10000000",
        },
        "tx_json": {
            "Account": "rV2SENDER00000000000000000000",
            "DeliverMax": "10000000",
            "Destination": "rV2DEST0000000000000000000000",
            "Fee": "12",
            "Flags": 0,
            "LastLedgerSequence": 10269285,
            "Memos": [
                {
                    "Memo": {
                        # "XRPLLAB|demo" / "text/plain"
                        "MemoData": "5852504C4C41427C64656D6F",
                        "MemoType": "746578742F706C61696E",
                    }
                }
            ],
            "Sequence": 5001762,
            "SigningPubKey": "ED" + "0" * 64,
            "TransactionType": "Payment",
            "TxnSignature": "AB" + "0" * 60,
            "date": 806707861,
        },
        "validated": True,
    }


class _V2Client:
    """RPC client whose request() returns the canned v2 tx response."""

    def __init__(self, result: dict) -> None:
        self._result = result

    async def request(self, *a, **k):
        return _FakeResponse(self._result)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


# ── F-1947a03d: validated tec raises — parse the code, never resubmit ─────


class TestReliableSubmissionRaises:
    @pytest.fixture()
    def testnet(self, monkeypatch: pytest.MonkeyPatch):
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        _patch_no_network(monkeypatch)
        return XRPLTestnetTransport()

    @pytest.mark.asyncio
    async def test_validated_tec_maps_to_real_code_single_attempt(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'Transaction failed: tecPATH_DRY' → result_code tecPATH_DRY, ONE
        submit attempt (a validated tec consumed a fee + sequence — a resubmit
        would land ANOTHER fee-claiming failure)."""
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _raise_tec(tx, client, wallet):
            calls["n"] += 1
            raise XRPLReliableSubmissionException("Transaction failed: tecPATH_DRY")

        monkeypatch.setattr(xt, "submit_and_wait", _raise_tec)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED, destination="rDEST", amount="10"
        )

        assert calls["n"] == 1, "a validated tec must never be resubmitted"
        assert result.success is False
        assert result.result_code == "tecPATH_DRY"
        # The doctor teach-moment fired (structured meaning/action, not a raw
        # local_error) — this is what failure_literacy routes through.
        assert result.error
        assert "local_error" not in result.result_code

    @pytest.mark.asyncio
    async def test_validated_tec_via_submit_tx_path(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The shared _submit_tx path (NFT burn here) maps the raise too."""
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _raise_tec(tx, client, wallet):
            calls["n"] += 1
            raise XRPLReliableSubmissionException(
                "Transaction failed: tecNO_ENTRY"
            )

        monkeypatch.setattr(xt, "submit_and_wait", _raise_tec)

        result = await testnet.submit_nft_burn(_VALID_TESTNET_SEED, "00" * 32)

        assert calls["n"] == 1
        assert result.success is False
        assert result.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_tem_prelim_raise_maps_and_does_not_retry(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """xrpl-py raises 'temMALFORMED: <msg>' for prelim tem rejections —
        structurally bad, mapped to the real code, never retried."""
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _raise_tem(tx, client, wallet):
            calls["n"] += 1
            raise XRPLReliableSubmissionException(
                "temMALFORMED: Malformed transaction."
            )

        monkeypatch.setattr(xt, "submit_and_wait", _raise_tem)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED, destination="rDEST", amount="10"
        )

        assert calls["n"] == 1, "tem prelim rejections must not be retried"
        assert result.success is False
        assert result.result_code == "temMALFORMED"

    @pytest.mark.asyncio
    async def test_expired_window_is_retried(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The expired-LastLedgerSequence raise means the tx can NEVER land —
        a retry with a fresh autofill is safe and allowed."""
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _expired_then_ok(tx, client, wallet):
            calls["n"] += 1
            if calls["n"] == 1:
                raise XRPLReliableSubmissionException(
                    "The latest validated ledger sequence 200 is greater than "
                    "LastLedgerSequence 180 in the transaction. "
                    "Prelim result: terQUEUED"
                )
            return _FakeResponse(_v2_tx_response("RETRYOK" + "0" * 57))

        monkeypatch.setattr(xt, "submit_and_wait", _expired_then_ok)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED, destination="rDEST", amount="10"
        )

        assert calls["n"] == 2, "an expired-window failure is safely retryable"
        assert result.success is True
        assert result.result_code == "tesSUCCESS"

    def test_no_retry_regex_widened_to_all_tem_codes(self) -> None:
        """All tem codes are malformed-by-definition; plain English 'temporary'
        must NOT match (it would suppress warranted retries)."""
        from xrpl_lab.transport.xrpl_testnet import _is_no_retry_error

        assert _is_no_retry_error("temMALFORMED: Malformed transaction.")
        assert _is_no_retry_error("temDISABLED: amendment inactive")
        assert _is_no_retry_error("temINVALID_FLAG: bad flag")
        assert _is_no_retry_error("temBAD_AMOUNT: malformed")
        assert _is_no_retry_error("tefBAD_AUTH: wrong key")
        assert not _is_no_retry_error("temporary network blip")
        assert not _is_no_retry_error("Invalid response from RPC endpoint")


# ── F-0cbd05ef: timeout never resubmits (shared _submit_tx path) ──────────


@pytest.mark.asyncio
async def test_submit_tx_timeout_never_resubmits(monkeypatch) -> None:
    from xrpl_lab.transport import xrpl_testnet as xt

    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    _patch_no_network(monkeypatch)
    calls = {"n": 0}

    async def _always_timeout(tx, client, wallet):
        calls["n"] += 1
        raise TimeoutError("submit timed out")

    monkeypatch.setattr(xt, "submit_and_wait", _always_timeout)

    result = await xt.XRPLTestnetTransport().submit_nft_burn(
        _VALID_TESTNET_SEED, "00" * 32
    )

    assert calls["n"] == 1, (
        "the timeout branch must NOT resubmit — the first broadcast may still "
        "be inside its LastLedgerSequence window (double-submit risk)"
    )
    assert result.success is False
    assert result.result_code == "local_error"
    assert "duplicate" in result.error.lower()


# ── F-5e672008: API v2 response shape ──────────────────────────────────────


class TestApiV2Shapes:
    @pytest.mark.asyncio
    async def test_fetch_tx_parses_v2_shape(self, monkeypatch) -> None:
        """A REAL v2 response (tx_json nesting + DeliverMax) yields the actual
        account/type/amount/fee/memos — the fields the honest-pack live
        verifier compares. Before the fix these were ''/''/0/0/[] and the
        verifier branded the learner's own receipt as forged."""
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        t = xt.XRPLTestnetTransport()
        resp = _v2_tx_response()

        with patch.object(
            xt, "_rpc_client", lambda url: _V2Client(resp)
        ):
            info = await t.fetch_tx(resp["hash"])

        assert info.tx_type == "Payment"
        assert info.account == "rV2SENDER00000000000000000000"
        assert info.destination == "rV2DEST0000000000000000000000"
        assert info.amount == "10000000"  # DeliverMax — the v2 Amount rename
        assert info.fee == "12"
        assert info.memos == ["XRPLLAB|demo"]
        assert info.validated is True
        assert info.ledger_index == 10269267
        assert info.result_code == "tesSUCCESS"
        assert info.delivered_amount == "10000000"

    @pytest.mark.asyncio
    async def test_fetch_tx_still_parses_legacy_v1_shape(self, monkeypatch) -> None:
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        t = xt.XRPLTestnetTransport()
        v1 = {
            "TransactionType": "Payment",
            "Account": "rV1SENDER",
            "Destination": "rV1DEST",
            "Amount": "5000000",
            "Fee": "10",
            "meta": {"TransactionResult": "tesSUCCESS"},
            "ledger_index": 777,
            "validated": True,
        }

        with patch.object(xt, "_rpc_client", lambda url: _V2Client(v1)):
            info = await t.fetch_tx("ABCD")

        assert info.tx_type == "Payment"
        assert info.account == "rV1SENDER"
        assert info.amount == "5000000"
        assert info.fee == "10"

    @pytest.mark.asyncio
    async def test_submit_payment_reads_fee_and_sequence_from_v2(
        self, monkeypatch
    ) -> None:
        """The submit parsers read Fee/Sequence from tx_json — the old
        top-level ``result.get("Fee")`` always yielded '0' on real testnet."""
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        _patch_no_network(monkeypatch)
        resp = _v2_tx_response()

        async def _ok(tx, client, wallet):
            return _FakeResponse(resp)

        monkeypatch.setattr(xt, "submit_and_wait", _ok)

        result = await xt.XRPLTestnetTransport().submit_payment(
            wallet_seed=_VALID_TESTNET_SEED, destination="rDEST", amount="10"
        )

        assert result.success is True
        assert result.txid == resp["hash"]
        assert result.fee == "12"
        assert result.sequence == 5001762


# ── F-4cf20cef: local endpoints must prove chain identity ──────────────────


class _ServerInfoClient:
    """RPC client answering server_info with a configurable network_id."""

    def __init__(self, network_id) -> None:
        self._network_id = network_id

    async def request(self, req):
        info: dict = {"build_version": "2.3.0"}
        if self._network_id is not None:
            info["network_id"] = self._network_id
        return _FakeResponse({"info": info})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class TestLocalChainIdentity:
    def _transport(self, monkeypatch, network_id):
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.setenv("XRPL_LAB_RPC_URL", "http://localhost:5005")
        monkeypatch.delenv("XRPL_LAB_ALLOW_LOCAL", raising=False)
        monkeypatch.setattr(
            xt, "AsyncJsonRpcClient", lambda url: _ServerInfoClient(network_id)
        )
        return xt.XRPLTestnetTransport()

    @pytest.mark.asyncio
    async def test_localhost_fronting_mainnet_refused(self, monkeypatch) -> None:
        """network_id 0 (mainnet) behind localhost → the write is REFUSED and
        submit_and_wait is never reached — closing the tunnel/port-forward
        residual mainnet path."""
        from xrpl_lab.transport import xrpl_testnet as xt

        t = self._transport(monkeypatch, network_id=0)
        submit = AsyncMock()
        monkeypatch.setattr(xt, "submit_and_wait", submit)

        res = await t.submit_payment(_VALID_TESTNET_SEED, "rDEST", "10")

        assert res.success is False
        assert "Refusing" in res.error
        assert not res.txid
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_localhost_missing_network_id_refused(self, monkeypatch) -> None:
        """A server_info WITHOUT network_id fails closed (mainnet omits it)."""
        t = self._transport(monkeypatch, network_id=None)
        res = await t.submit_payment(_VALID_TESTNET_SEED, "rDEST", "10")
        assert res.success is False
        assert "Refusing" in res.error

    @pytest.mark.asyncio
    async def test_localhost_fronting_testnet_allowed(self, monkeypatch) -> None:
        """network_id 1 (testnet) verifies — the signed write proceeds."""
        from xrpl_lab.transport import xrpl_testnet as xt

        t = self._transport(monkeypatch, network_id=1)

        async def _ok(tx, client, wallet):
            return _FakeResponse(_v2_tx_response("LOCALOK" + "0" * 57))

        monkeypatch.setattr(xt, "submit_and_wait", _ok)

        async def _no_sleep(_s):
            return None

        monkeypatch.setattr(xt.asyncio, "sleep", _no_sleep)

        res = await t.submit_payment(_VALID_TESTNET_SEED, "rDEST", "10")
        assert res.success is True
        assert res.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_allow_local_env_bypasses_probe(self, monkeypatch) -> None:
        """XRPL_LAB_ALLOW_LOCAL=1 is the explicit standalone-node opt-in: the
        probe is skipped even when server_info would report mainnet."""
        from xrpl_lab.transport import xrpl_testnet as xt

        t = self._transport(monkeypatch, network_id=0)
        monkeypatch.setenv("XRPL_LAB_ALLOW_LOCAL", "1")

        async def _ok(tx, client, wallet):
            return _FakeResponse(_v2_tx_response("ALLOWED" + "0" * 57))

        monkeypatch.setattr(xt, "submit_and_wait", _ok)

        res = await t.submit_payment(_VALID_TESTNET_SEED, "rDEST", "10")
        assert res.success is True

    @pytest.mark.asyncio
    async def test_unreachable_local_probe_fails_closed(self, monkeypatch) -> None:
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.setenv("XRPL_LAB_RPC_URL", "http://127.0.0.1:5005")
        monkeypatch.delenv("XRPL_LAB_ALLOW_LOCAL", raising=False)

        class _Boom:
            def __init__(self, *a, **k):
                pass

            async def request(self, req):
                raise ConnectionError("no rippled here")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(xt, "AsyncJsonRpcClient", _Boom)
        res = await xt.XRPLTestnetTransport().submit_payment(
            _VALID_TESTNET_SEED, "rDEST", "10"
        )
        assert res.success is False
        assert "Refusing" in res.error

    @pytest.mark.asyncio
    async def test_default_testnet_never_probes(self, monkeypatch) -> None:
        """The chain probe is scoped to 'local' — the default testnet endpoint
        goes straight to submit (no server_info round-trip)."""
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        monkeypatch.delenv("XRPL_LAB_ALLOW_LOCAL", raising=False)
        _patch_no_network(monkeypatch)

        async def _ok(tx, client, wallet):
            return _FakeResponse(_v2_tx_response("TESTNET" + "0" * 57))

        monkeypatch.setattr(xt, "submit_and_wait", _ok)
        res = await xt.XRPLTestnetTransport().submit_payment(
            _VALID_TESTNET_SEED, "rDEST", "10"
        )
        assert res.success is True


# ── F-88f82c27: offer_sequence from the submit response ───────────────────


@pytest.mark.asyncio
async def test_permissioned_offer_sequence_from_submit_response(monkeypatch) -> None:
    """offer_sequence == the placing tx's Sequence from tx_json — and the
    wrong-offer-prone get_account_offers read-back is GONE."""
    from xrpl_lab.transport import xrpl_testnet as xt

    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    _patch_no_network(monkeypatch)
    resp = _v2_tx_response("PERMOFF" + "0" * 57)
    resp["tx_json"]["TransactionType"] = "OfferCreate"

    async def _ok(tx, client, wallet):
        return _FakeResponse(resp)

    monkeypatch.setattr(xt, "submit_and_wait", _ok)

    t = xt.XRPLTestnetTransport()
    read_back = AsyncMock()
    monkeypatch.setattr(t, "get_account_offers", read_back)

    res = await t.submit_permissioned_offer_create(
        _VALID_TESTNET_SEED, "LAB", "50", "rISSUER", "XRP", "10", "", "A" * 64
    )

    assert res.success is True
    assert res.offer_sequence == 5001762
    assert res.sequence == 5001762
    read_back.assert_not_awaited()


# ── F-69a13b3b: faucet non-429 HTTP errors back off ────────────────────────


@pytest.mark.asyncio
async def test_faucet_non_429_error_backs_off(monkeypatch) -> None:
    from unittest.mock import MagicMock

    import httpx

    from xrpl_lab.transport import xrpl_testnet as xt
    from xrpl_lab.transport.xrpl_testnet import MAX_RETRIES, XRPLTestnetTransport

    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    monkeypatch.delenv("XRPL_LAB_FAUCET_URL", raising=False)

    fake_503 = MagicMock()
    fake_503.status_code = 503
    fake_503.text = "service degraded"

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.post = AsyncMock(return_value=fake_503)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake_client)

    slept: list[float] = []

    async def _record_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(xt.asyncio, "sleep", _record_sleep)

    result = await XRPLTestnetTransport().fund_from_faucet("rTEST")

    assert result.success is False
    assert fake_client.post.await_count == MAX_RETRIES + 1
    assert len(slept) == MAX_RETRIES, (
        f"a degraded faucet must be backed off between attempts, got {slept}"
    )


# ═══════════════════════ dry-run transport ═══════════════════════


def _seed_line(t: DryRunTransport, address: str, balance: str, limit: str = "1000") -> None:
    t._trust_lines.setdefault(address, []).append(
        TrustLineInfo(account=address, peer=ISSUER, currency="GLD",
                      balance=balance, limit=limit)
    )


# ── F-7ec2c90d: XRP conservation (escrow + channels) ───────────────────────


class TestXrpConservation:
    @pytest.mark.asyncio
    async def test_escrow_create_debits_source_and_cancel_conserves(self) -> None:
        """fund 1000 → escrow 100 locks it (spendable 900) → cancel returns it
        (1000). The old sim left 1000 after create and MINTED to 1100 on
        cancel."""
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)

        create = await t.submit_escrow_create(
            "sSENDER", "100", "rESCROWDEST00000000000000000", finish_after=0
        )
        assert create.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 900_000_000

        seq = create.sequence
        cancel = await t.submit_escrow_cancel("sSENDER", _DRY_RUN_WALLET_ADDRESS, seq)
        assert cancel.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 1_000_000_000, (
            "a create+cancel round trip must conserve XRP, not mint it"
        )

    @pytest.mark.asyncio
    async def test_escrow_finish_conserves_total(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        dest = "rESCROWDEST00000000000000000"

        create = await t.submit_escrow_create(
            "sSENDER", "250", dest, finish_after=0
        )
        fin = await t.submit_escrow_finish(
            "sSENDER", _DRY_RUN_WALLET_ADDRESS, create.sequence
        )
        assert fin.success
        total = t._balances[_DRY_RUN_WALLET_ADDRESS] + t._balances[dest]
        assert total == 1_000_000_000
        assert t._balances[dest] == 250_000_000

    @pytest.mark.asyncio
    async def test_escrow_create_rejects_underfunded_source(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        r = await t.submit_escrow_create("sSENDER", "2000", "rDEST", finish_after=0)
        assert not r.success
        assert r.result_code == "tecUNFUNDED"
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 1_000_000_000

    @pytest.mark.asyncio
    async def test_channel_lifecycle_conserves_xrp(self) -> None:
        """create 200 debits source; claim 150 credits destination; the
        remainder returns to the source on close — total invariant."""
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        dest = "rCHANDEST0000000000000000000"

        create = await t.submit_payment_channel_create(
            "sSENDER", "200", dest, settle_delay=0, public_key="ED00"
        )
        assert create.success
        cid = create.channel_id
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 800_000_000, (
            "the channel deposit must leave the source's spendable balance"
        )

        sig = await t.authorize_payment_channel_claim("sSENDER", cid, "150")
        claim = await t.submit_payment_channel_claim(
            "sRECEIVER", cid, balance_xrp="150",
            amount_xrp="150", signature=sig, public_key="ED00",
        )
        assert claim.success
        assert t._balances[dest] == 150_000_000

        # settle_delay=0 → close is immediate; the 50 XRP remainder refunds.
        close = await t.submit_payment_channel_claim("sSENDER", cid, close=True)
        assert close.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 850_000_000
        total = t._balances[_DRY_RUN_WALLET_ADDRESS] + t._balances[dest]
        assert total == 1_000_000_000, "channel lifecycle must conserve XRP"

    @pytest.mark.asyncio
    async def test_channel_fund_debits_source(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        create = await t.submit_payment_channel_create(
            "sSENDER", "100", "rDEST", settle_delay=86400, public_key="ED00"
        )
        fund = await t.submit_payment_channel_fund("sSENDER", create.channel_id, "50")
        assert fund.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 850_000_000


# ── F-c0be844f / F-03f27a6c: negative & contradictory amounts ──────────────


class TestNegativeAmountsRejected:
    @pytest.mark.asyncio
    async def test_negative_issued_payment_rejected(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        r = await t.submit_issued_payment("sISSUER", HOLDER, "GLD", ISSUER, "-40")
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"
        line = (await t.get_trust_lines(HOLDER))[0]
        assert line.balance == "100", "a rejected payment must not mutate balances"

    @pytest.mark.asyncio
    async def test_zero_issued_payment_rejected(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        r = await t.submit_issued_payment("sISSUER", HOLDER, "GLD", ISSUER, "0")
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"

    @pytest.mark.asyncio
    async def test_negative_clawback_rejected_no_minting(self) -> None:
        """claw -500 previously MINTED 500 to the holder (100 → 560 class)."""
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        await t.submit_account_set_clawback("sISSUER", ISSUER)
        r = await t.submit_clawback("sISSUER", HOLDER, "GLD", "-500", ISSUER)
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"
        line = (await t.get_trust_lines(HOLDER))[0]
        assert line.balance == "100", "negative clawback must not mint tokens"

    @pytest.mark.asyncio
    async def test_negative_mpt_payment_rejected(self) -> None:
        t = DryRunTransport()
        iss = await t.submit_mpt_issuance_create("sISSUER", "1000000")
        iid = iss.mpt_issuance_id
        await t.submit_mpt_authorize("sHOLDER", iid)
        await t.submit_mpt_payment("sISSUER", _DRY_RUN_WALLET_ADDRESS, iid, "50")
        r = await t.submit_mpt_payment("sISSUER", _DRY_RUN_WALLET_ADDRESS, iid, "-30")
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"
        assert await t.get_mpt_balance(_DRY_RUN_WALLET_ADDRESS, iid) == "50"

    @pytest.mark.asyncio
    async def test_negative_deliver_min_rejected(self) -> None:
        t = DryRunTransport()
        _seed_line(t, _DRY_RUN_WALLET_ADDRESS, "0")
        r = await t.submit_partial_payment(
            "sISSUER", _DRY_RUN_WALLET_ADDRESS, "GLD", ISSUER,
            amount="100", deliver_min="-10", send_max="100",
        )
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"

    @pytest.mark.asyncio
    async def test_deliver_min_above_amount_rejected(self) -> None:
        """F-03f27a6c: DeliverMin > Amount is a contradiction — the old sim
        'delivered' MORE than the claimed cap, an impossible on-ledger state."""
        t = DryRunTransport()
        _seed_line(t, _DRY_RUN_WALLET_ADDRESS, "0")
        r = await t.submit_partial_payment(
            "sISSUER", _DRY_RUN_WALLET_ADDRESS, "GLD", ISSUER,
            amount="10", deliver_min="100", send_max="100",
        )
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"

    @pytest.mark.asyncio
    async def test_partial_payment_respects_trust_line_limit(self) -> None:
        """F-03f27a6c: the delivered credit obeys the same limit rule as a
        plain issued payment."""
        t = DryRunTransport()
        _seed_line(t, _DRY_RUN_WALLET_ADDRESS, "995", limit="1000")
        r = await t.submit_partial_payment(
            "sISSUER", _DRY_RUN_WALLET_ADDRESS, "GLD", ISSUER,
            amount="50", deliver_min="10", send_max="50",
        )
        assert not r.success
        assert r.result_code == "tecPATH_DRY"


# ── F-a4147d39: freeze enforcement ─────────────────────────────────────────


class TestFreezeEnforced:
    @pytest.mark.asyncio
    async def test_individual_freeze_blocks_issued_payment(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        await t.submit_set_freeze("sISSUER", HOLDER, "GLD", True, ISSUER)
        status = await t.get_freeze_status(ISSUER, HOLDER, "GLD")
        assert status.individual_frozen

        r = await t.submit_issued_payment("sISSUER", HOLDER, "GLD", ISSUER, "10")
        assert not r.success, "a payment into a frozen line must fail offline too"
        assert r.result_code == "tecPATH_DRY"
        assert (await t.get_trust_lines(HOLDER))[0].balance == "100"

    @pytest.mark.asyncio
    async def test_unfreeze_restores_payments(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        await t.submit_set_freeze("sISSUER", HOLDER, "GLD", True, ISSUER)
        await t.submit_set_freeze("sISSUER", HOLDER, "GLD", False, ISSUER)
        r = await t.submit_issued_payment("sISSUER", HOLDER, "GLD", ISSUER, "10")
        assert r.success

    @pytest.mark.asyncio
    async def test_global_freeze_blocks_issued_payment(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        await t.submit_global_freeze("sISSUER", True, ISSUER)
        r = await t.submit_issued_payment("sISSUER", HOLDER, "GLD", ISSUER, "10")
        assert not r.success
        assert r.result_code == "tecPATH_DRY"

    @pytest.mark.asyncio
    async def test_frozen_line_blocks_partial_payment_too(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "0")
        await t.submit_set_freeze("sISSUER", HOLDER, "GLD", True, ISSUER)
        r = await t.submit_partial_payment(
            "sISSUER", HOLDER, "GLD", ISSUER,
            amount="100", deliver_min="10", send_max="100",
        )
        assert not r.success
        assert r.result_code == "tecPATH_DRY"


# ── F-8b39e89b: issuer opt-in keyed strictly by address ────────────────────


class TestLockingOptInKeying:
    CANCEL = 950_000_000
    FINISH = 900_000_000

    @pytest.mark.asyncio
    async def test_seed_only_optin_does_not_leak_to_other_issuers(self) -> None:
        """Issuer A opts in SEED-ONLY; an escrow of issuer B's IOU must still
        fail tecNO_PERMISSION (previously the collapsed-address fallback made
        EVERY issuer look opted-in)."""
        t = DryRunTransport()
        other_issuer = "rOTHERISSUERBBBBBBBBBBBBBBBBBB"
        t._trust_lines.setdefault(HOLDER, []).append(
            TrustLineInfo(account=HOLDER, peer=other_issuer, currency="SLV",
                          balance="100", limit="1000")
        )
        # Seed-only opt-in (no issuer_address) — keys the collapsed wallet.
        await t.submit_allow_trustline_locking("sISSUER_A")

        r = await t.submit_token_escrow_create(
            "sHOLDER", "SLV", other_issuer, "50", "rRECIP",
            cancel_after=self.CANCEL, finish_after=self.FINISH,
            source_address=HOLDER,
        )
        assert not r.success
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_address_keyed_optin_still_works(self) -> None:
        t = DryRunTransport()
        _seed_line(t, HOLDER, "100")
        await t.submit_allow_trustline_locking("sISSUER", ISSUER)
        r = await t.submit_token_escrow_create(
            "sHOLDER", "GLD", ISSUER, "50", "rRECIP",
            cancel_after=self.CANCEL, finish_after=self.FINISH,
            source_address=HOLDER,
        )
        assert r.success
        assert r.sequence is not None


# ── fix1571: EscrowCreate needs FinishAfter or Condition ───────────────────


@pytest.mark.asyncio
async def test_token_escrow_without_finish_after_is_malformed() -> None:
    t = DryRunTransport()
    _seed_line(t, HOLDER, "100")
    await t.submit_allow_trustline_locking("sISSUER", ISSUER)
    r = await t.submit_token_escrow_create(
        "sHOLDER", "GLD", ISSUER, "50", "rRECIP",
        cancel_after=950_000_000, finish_after=None, source_address=HOLDER,
    )
    assert not r.success
    assert r.result_code == "temMALFORMED"
    assert "FinishAfter" in r.error
    # Nothing was locked.
    assert (await t.get_trust_lines(HOLDER))[0].balance == "100"


# ── F-cbc476b3: EscrowFinish past CancelAfter is expired ───────────────────


class TestEscrowExpiry:
    @pytest.mark.asyncio
    async def test_finish_after_cancel_after_passed_is_expired(self) -> None:
        """Created INSIDE the window, finished AFTER CancelAfter → expired:
        only EscrowCancel can act (tecNO_PERMISSION)."""
        t = DryRunTransport()
        t.set_dry_clock(100)
        create = await t.submit_escrow_create(
            "sSENDER", "10", "rDEST", finish_after=1000, cancel_after=2000
        )
        assert create.success
        seq = create.sequence

        t.set_dry_clock(4_000_000_000)  # far past CancelAfter
        fin = await t.submit_escrow_finish("sSENDER", _DRY_RUN_WALLET_ADDRESS, seq)
        assert not fin.success
        assert fin.result_code == "tecNO_PERMISSION"
        assert "expired" in fin.error.lower()

        # The reclaim path still works.
        cancel = await t.submit_escrow_cancel("sSENDER", _DRY_RUN_WALLET_ADDRESS, seq)
        assert cancel.success

    @pytest.mark.asyncio
    async def test_finish_inside_window_still_succeeds(self) -> None:
        t = DryRunTransport()
        t.set_dry_clock(100)
        create = await t.submit_escrow_create(
            "sSENDER", "10", "rDEST", finish_after=1000, cancel_after=2000
        )
        t.set_dry_clock(1500)  # inside [FinishAfter, CancelAfter)
        fin = await t.submit_escrow_finish(
            "sSENDER", _DRY_RUN_WALLET_ADDRESS, create.sequence
        )
        assert fin.success

    @pytest.mark.asyncio
    async def test_compressed_time_demo_escrow_keeps_legacy_behavior(self) -> None:
        """An escrow created with the clock ALREADY past its CancelAfter could
        never exist on-network — the sim keeps it finishable so the module
        handlers' wall-clock-derived times keep working offline."""
        t = DryRunTransport()  # default far-future clock
        create = await t.submit_escrow_create(
            "sSENDER", "10", "rDEST", finish_after=900, cancel_after=950
        )
        fin = await t.submit_escrow_finish(
            "sSENDER", _DRY_RUN_WALLET_ADDRESS, create.sequence
        )
        assert fin.success


# ── F-2e2975aa: credential expiration ──────────────────────────────────────


class TestCredentialExpiration:
    SUBJECT = "rSUBJECT0000000000000000000000"
    CTYPE = "6F7665723231"  # "over21"

    @pytest.mark.asyncio
    async def test_create_with_past_expiration_rejected(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(self.SUBJECT)
        # Default clock is far-future; expiration=100 is already past.
        r = await t.submit_credential_create(
            "sISSUER", self.SUBJECT, self.CTYPE, expiration=100,
            issuer_address=ISSUER,
        )
        assert not r.success
        assert r.result_code == "temBAD_EXPIRATION"

    @pytest.mark.asyncio
    async def test_expired_credential_fails_domain_gate(self) -> None:
        """Accepted-but-EXPIRED credential no longer satisfies the
        permissioned-domain eligibility gate (tecNO_PERMISSION on-network)."""
        t = DryRunTransport()
        t.set_dry_clock(50)
        await t.fund_from_faucet(self.SUBJECT)
        c = await t.submit_credential_create(
            "sISSUER", self.SUBJECT, self.CTYPE, expiration=100,
            issuer_address=ISSUER,
        )
        assert c.success
        acc = await t.submit_credential_accept(
            "sSUBJECT", ISSUER, self.CTYPE, subject_address=self.SUBJECT
        )
        assert acc.success

        dom = await t.submit_permissioned_domain_set(
            "sOWNER", [(ISSUER, self.CTYPE)], owner_address="rDOMOWNER"
        )
        assert dom.success

        # Valid while the clock is before expiration...
        ok = await t.submit_permissioned_offer_create(
            "sSUBJECT", "GLD", "5", ISSUER, "XRP", "10", "",
            dom.domain_id, wallet_address=self.SUBJECT,
        )
        assert ok.success

        # ...and rejected once the clock passes it.
        t.set_dry_clock(150)
        expired = await t.submit_permissioned_offer_create(
            "sSUBJECT", "GLD", "5", ISSUER, "XRP", "10", "",
            dom.domain_id, wallet_address=self.SUBJECT,
        )
        assert not expired.success
        assert expired.result_code == "tecNO_PERMISSION"


# ── F-233393c2: NFT settlement funding check ───────────────────────────────


@pytest.mark.asyncio
async def test_nft_purchase_requires_funded_buyer() -> None:
    t = DryRunTransport()
    buyer = "rBUYER000000000000000000000000"
    t._balances[buyer] = 0  # tracked AND broke

    mint = await t.submit_nft_mint("sSELLER", "ipfs://sword")
    offer = await t.submit_nft_create_offer(
        "sSELLER", mint.nft_id, "500", sell=True, destination=buyer
    )
    r = await t.submit_nft_accept_offer("sBUYER", sell_offer=offer.nft_offer_index)

    assert not r.success
    assert r.result_code == "tecINSUFFICIENT_FUNDS"
    assert t._balances[buyer] == 0, "no debit on a failed settlement"
    # The NFT did not move — the seller still owns it.
    seller_nfts = await t.get_account_nfts(_DRY_RUN_WALLET_ADDRESS)
    assert any(n.nft_id == mint.nft_id for n in seller_nfts)


# ── F-95640306: channel-claim signature validity ───────────────────────────


class TestChannelClaimSignature:
    @pytest.mark.asyncio
    async def test_garbage_signature_rejected(self) -> None:
        t = DryRunTransport()
        create = await t.submit_payment_channel_create(
            "sSENDER", "10", "rDEST", settle_delay=86400, public_key="ED00"
        )
        r = await t.submit_payment_channel_claim(
            "sRECEIVER", create.channel_id, balance_xrp="5",
            amount_xrp="5", signature="DRYSIGGARBAGE", public_key="ED00",
        )
        assert not r.success
        assert r.result_code == "temBAD_SIGNATURE"
        assert t._balances.get("rDEST", 0) == 0, "no settlement on a bad signature"

    @pytest.mark.asyncio
    async def test_balance_above_signed_amount_rejected(self) -> None:
        t = DryRunTransport()
        create = await t.submit_payment_channel_create(
            "sSENDER", "10", "rDEST", settle_delay=86400, public_key="ED00"
        )
        cid = create.channel_id
        sig = await t.authorize_payment_channel_claim("sSENDER", cid, "3")
        r = await t.submit_payment_channel_claim(
            "sRECEIVER", cid, balance_xrp="7",
            amount_xrp="3", signature=sig, public_key="ED00",
        )
        assert not r.success
        assert r.result_code == "temBAD_AMOUNT"

    @pytest.mark.asyncio
    async def test_source_close_with_outstanding_schedules_settle_delay(self) -> None:
        """Close with unclaimed funds + settle_delay schedules expiration
        (channel stays open for the dispute window), then closes for real —
        refunding the remainder — once the window passes."""
        t = DryRunTransport()
        t.set_dry_clock(1_000_000)
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        create = await t.submit_payment_channel_create(
            "sSENDER", "100", "rDEST", settle_delay=3600, public_key="ED00"
        )
        cid = create.channel_id

        first_close = await t.submit_payment_channel_claim("sSENDER", cid, close=True)
        assert first_close.success
        chans = await t.get_account_channels(_DRY_RUN_WALLET_ADDRESS)
        assert len(chans) == 1, "channel must stay open through the dispute window"
        assert chans[0].expiration == 1_000_000 + 3600

        # After the window passes, a close request finalizes + refunds.
        t.set_dry_clock(1_000_000 + 3600)
        second_close = await t.submit_payment_channel_claim("sSENDER", cid, close=True)
        assert second_close.success
        assert await t.get_account_channels(_DRY_RUN_WALLET_ADDRESS) == []
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 1_000_000_000, (
            "the unclaimed remainder must refund to the source on final close"
        )


# ── F-3bdd6cfa: AMM terminal states ────────────────────────────────────────


class TestAmmTerminalStates:
    @pytest.mark.asyncio
    async def test_trading_fee_above_cap_rejected(self) -> None:
        t = DryRunTransport()
        r = await t.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER", trading_fee=1001,
        )
        assert not r.success
        assert r.result_code == "temBAD_FEE"

    @pytest.mark.asyncio
    async def test_full_withdraw_deletes_pool_and_recreate_succeeds(self) -> None:
        t = DryRunTransport()
        await t.submit_amm_create("sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER")
        wd = await t.submit_amm_withdraw("sFAKE", "XRP", "", "LAB", "rISSUER")
        assert wd.success
        assert await t.get_amm_info("XRP", "", "LAB", "rISSUER") is None, (
            "the network DELETES the AMM object when the last LP withdraws"
        )
        recreate = await t.submit_amm_create(
            "sFAKE", "XRP", "10", "", "LAB", "10", "rISSUER"
        )
        assert recreate.success, "re-creation is legal after deletion"


# ── F-64106db7: unknown txids are not fabricated ───────────────────────────


class TestUnknownTxid:
    @pytest.mark.asyncio
    async def test_unknown_txid_fetches_as_not_found(self) -> None:
        t = DryRunTransport()
        info = await t.fetch_tx("F" * 64)
        assert info.validated is False
        assert info.result_code == ""
        assert info.tx_type == ""

    @pytest.mark.asyncio
    async def test_issued_txid_still_fetches_validated(self) -> None:
        t = DryRunTransport()
        res = await t.submit_payment("sSENDER", "rDEST", "1")
        info = await t.fetch_tx(res.txid)
        assert info.validated is True
        assert info.result_code == "tesSUCCESS"

    @pytest.mark.asyncio
    async def test_fixture_txids_still_win(self) -> None:
        from xrpl_lab.transport.base import TxInfo

        t = DryRunTransport()
        t.set_tx_fixtures({"AA11": TxInfo(txid="AA11", tx_type="Payment",
                                          result_code="tecPATH_DRY")})
        info = await t.fetch_tx("AA11")
        assert info.result_code == "tecPATH_DRY"


# ── F-ebadec19: reserve floor + fee debit ──────────────────────────────────


class TestReserveFloorAndFee:
    @pytest.mark.asyncio
    async def test_spend_into_reserve_rejected(self) -> None:
        """fund 1000 → sending 999.5 would dip below the 1 XRP base reserve →
        tecUNFUNDED_PAYMENT (the old sim allowed spending to exactly 0)."""
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        r = await t.submit_payment("sSENDER", "rDEST", "999.5")
        assert not r.success
        assert r.result_code == "tecUNFUNDED_PAYMENT"
        assert "reserve" in r.error.lower()
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == 1_000_000_000

    @pytest.mark.asyncio
    async def test_send_all_is_rejected_like_testnet(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        r = await t.submit_payment("sSENDER", "rDEST", "1000")
        assert not r.success
        assert r.result_code == "tecUNFUNDED_PAYMENT"

    @pytest.mark.asyncio
    async def test_fee_debited_from_sender(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        r = await t.submit_payment("sSENDER", "rDEST", "10")
        assert r.success
        assert t._balances[_DRY_RUN_WALLET_ADDRESS] == (
            1_000_000_000 - 10_000_000 - 12
        ), "the reported 12-drop fee must actually be debited"
        assert t._balances["rDEST"] == 10_000_000

    @pytest.mark.asyncio
    async def test_owner_count_raises_the_floor(self) -> None:
        t = DryRunTransport()
        await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
        # 5 owned objects → reserve = 1 + 5*0.2 = 2 XRP.
        t._owner_counts[_DRY_RUN_WALLET_ADDRESS] = 5
        r = await t.submit_payment("sSENDER", "rDEST", "998.5")
        assert not r.success
        assert r.result_code == "tecUNFUNDED_PAYMENT"
        ok = await t.submit_payment("sSENDER", "rDEST", "997")
        assert ok.success


# ── F-3d812d44: re-funding adds ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_adds_instead_of_overwriting() -> None:
    t = DryRunTransport()
    first = await t.fund_from_faucet("rREFUND0000000000000000000000")
    assert first.balance == "1000.000000"
    second = await t.fund_from_faucet("rREFUND0000000000000000000000")
    assert second.balance == "2000.000000"
    assert t._balances["rREFUND0000000000000000000000"] == 2_000_000_000


# ── F-0feb8f21: deterministic txids ────────────────────────────────────────


@pytest.mark.asyncio
async def test_txids_deterministic_across_identical_sessions() -> None:
    a = DryRunTransport()
    b = DryRunTransport()
    ra = await a.submit_payment("sSENDER", "rDEST", "1")
    rb = await b.submit_payment("sSENDER", "rDEST", "1")
    assert ra.txid == rb.txid, (
        "identical dry-run sessions must produce byte-identical txids "
        "(deterministic-outputs contract)"
    )
    # Uniqueness within a session is preserved.
    ra2 = await a.submit_payment("sSENDER", "rDEST", "1")
    assert ra2.txid != ra.txid


# ── F-1188db18: dry_run stays xrpl-py-free ─────────────────────────────────


def test_dry_run_has_no_xrpl_import() -> None:
    src = Path(__file__).parent.parent / "xrpl_lab" / "transport" / "dry_run.py"
    text = src.read_text(encoding="utf-8")
    assert "from xrpl" not in text and "import xrpl" not in text, (
        "dry_run.py is the OFFLINE transport and must not import xrpl-py"
    )


# ── SubmitResult.sequence (coordinator: handler sequence capture) ──────────


class TestSubmitResultSequence:
    @pytest.mark.asyncio
    async def test_dry_run_escrow_create_sequence_matches_ledger(self) -> None:
        t = DryRunTransport()
        create = await t.submit_escrow_create("sSENDER", "10", "rDEST", finish_after=0)
        assert create.sequence is not None
        escrows = await t.get_escrows(_DRY_RUN_WALLET_ADDRESS)
        assert escrows[0].sequence == create.sequence

    @pytest.mark.asyncio
    async def test_dry_run_offer_create_sequence_populated(self) -> None:
        t = DryRunTransport()
        r = await t.submit_offer_create(
            "sSENDER", "GLD", "10", ISSUER, "XRP", "10", ""
        )
        assert r.sequence is not None
        offers = await t.get_account_offers(_DRY_RUN_WALLET_ADDRESS)
        assert offers[-1].sequence == r.sequence
