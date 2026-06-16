"""v2.0.0 transport regression tests (dogfood swarm — transport domain).

Covers four findings against the transport layer. All tests run fully
offline: ``DryRunTransport`` needs no network and no ``xrpl`` client, and the
testnet-contract test (TRANSPORT-A-003) only inspects source/dataclasses, so
the whole module stays network-free.

- TRANSPORT-A-001: dry-run ``submit_issued_payment`` must credit the
  *destination's* trust line, not the first match across all addresses.
- TRANSPORT-A-002: ``owner_count`` is per-account, not a single global int.
- TRANSPORT-A-004: the retry-abort heuristic must key on real XRPL result-code
  tokens, not the bare English word "Invalid".
- TRANSPORT-A-003: the two transports agree on the ``EscrowInfo.sequence``
  contract.
"""

from __future__ import annotations

import inspect
import logging

import pytest

from xrpl_lab.transport.base import EscrowInfo, TrustLineInfo, TxInfo
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport


@pytest.fixture
def transport() -> DryRunTransport:
    return DryRunTransport()


# ── TRANSPORT-A-001: issued-payment destination scoping ──────────────────


class TestIssuedPaymentDestinationScoping:
    """submit_issued_payment must credit the destination's own trust line."""

    @pytest.mark.asyncio
    async def test_credits_destination_not_first_match(self, transport):
        """Two holders A and B both trust USD/rISSUER; paying B credits only B."""
        issuer = "rISSUERxxxxxxxxxxxxxxxxxxxxxxx"
        addr_a = "rHolderAAAAAAAAAAAAAAAAAAAAAAA"
        addr_b = "rHolderBBBBBBBBBBBBBBBBBBBBBBB"

        # Seed two DISTINCT per-address trust-line buckets (both balance 0).
        # We populate the store directly because _address_from_seed collapses
        # every seed to one dry-run address, so submit_trust_set cannot build
        # two distinct holder buckets in dry-run.
        transport._trust_lines[addr_a] = [
            TrustLineInfo(account=addr_a, peer=issuer, currency="USD",
                          balance="0", limit="1000")
        ]
        transport._trust_lines[addr_b] = [
            TrustLineInfo(account=addr_b, peer=issuer, currency="USD",
                          balance="0", limit="1000")
        ]

        result = await transport.submit_issued_payment(
            wallet_seed="sISSUER",
            destination=addr_b,
            currency="USD",
            issuer=issuer,
            amount="50",
        )
        assert result.success is True

        a_lines = await transport.get_trust_lines(addr_a)
        b_lines = await transport.get_trust_lines(addr_b)
        assert b_lines[0].balance == "50", "destination B must be credited"
        assert a_lines[0].balance == "0", "non-destination A must stay untouched"

    @pytest.mark.asyncio
    async def test_single_collapsed_bucket_still_works(self, transport):
        """Backward compat: the single-wallet collapse path still credits."""
        # Trust line created via seed lands in the collapsed dry-run bucket,
        # while the payment destination is an arbitrary address.
        await transport.submit_trust_set("sFAKE", "rISSUER", "LAB", "1000")
        result = await transport.submit_issued_payment(
            "sISSUER", "rHOLDER", "LAB", "rISSUER", "100"
        )
        assert result.success is True
        lines = await transport.get_trust_lines("rANY")
        assert lines[0].balance == "100"


# ── TRANSPORT-A-002: per-address owner_count ─────────────────────────────


class TestPerAddressOwnerCount:
    """OwnerCount is strictly per-account on testnet — mirror that."""

    @pytest.mark.asyncio
    async def test_address_with_no_objects_starts_zero(self, transport):
        snap = await transport.get_account_info("rFreshAddrNoObjectsXXXXXXXXXX")
        assert snap.owner_count == 0

    @pytest.mark.asyncio
    async def test_object_under_wallet_increments_that_address(self, transport):
        """An object created via a wallet increments that wallet's address count."""
        wallet_addr = _DRY_RUN_WALLET_ADDRESS
        assert (await transport.get_account_info(wallet_addr)).owner_count == 0

        await transport.submit_trust_set("sWALLET", "rISSUER", "LAB", "1000")

        assert (await transport.get_account_info(wallet_addr)).owner_count == 1
        # Per-address ledger reflects it under the acting wallet's address.
        assert transport._owner_counts.get(wallet_addr, 0) == 1

    @pytest.mark.asyncio
    async def test_distinct_tracked_address_not_moved(self, transport):
        """A distinct, explicitly-tracked address is NOT moved by another
        wallet's object creation."""
        other_addr = "rDistinctTrackedAddrXXXXXXXXXX"
        # Explicitly track 'other_addr' at 0 so it is a real per-address entry,
        # not the global fallback.
        transport._owner_counts[other_addr] = 0

        # Create an object under the dry-run wallet (a DIFFERENT address).
        await transport.submit_offer_create(
            "sWALLET", "LAB", "50", "rISSUER", "XRP", "10", "",
        )

        snap = await transport.get_account_info(other_addr)
        assert snap.owner_count == 0, "other address must not move"
        # And the acting wallet's address did move.
        assert transport._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 1

    @pytest.mark.asyncio
    async def test_decrement_under_acting_address(self, transport):
        """Removing an object decrements the acting wallet's per-address count."""
        await transport.submit_offer_create(
            "sWALLET", "LAB", "50", "rISSUER", "XRP", "10", "",
        )
        assert transport._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 1
        await transport.submit_offer_cancel("sWALLET", 100)
        assert transport._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 0


# ── TRANSPORT-A-004: retry-abort token matching ──────────────────────────


class TestRetryAbortTokenMatching:
    """The retry-abort heuristic must not short-circuit on generic 'Invalid'."""

    def test_transient_invalid_does_not_abort(self):
        """A transient message containing the word 'Invalid' (no tem/tef code)
        must NOT be classified as a no-retry malformed error."""
        from xrpl_lab.transport.xrpl_testnet import _is_no_retry_error

        transient = "Invalid response received from RPC endpoint; please retry"
        assert _is_no_retry_error(transient) is False

    def test_tem_code_aborts(self):
        """A genuine temBAD* result code aborts the retry loop."""
        from xrpl_lab.transport.xrpl_testnet import _is_no_retry_error

        assert _is_no_retry_error("temBADAmount: bad amount field") is True

    def test_tef_code_aborts(self):
        from xrpl_lab.transport.xrpl_testnet import _is_no_retry_error

        assert _is_no_retry_error("tefBAD_AUTH: signature mismatch") is True

    def test_no_retry_helper_is_used_by_signing_paths(self):
        """All signing retry blocks must route through the shared helper,
        not the old bare-substring tuple (regression guard)."""
        from xrpl_lab.transport import xrpl_testnet

        src = inspect.getsource(xrpl_testnet)
        # The old broad heuristic scanned the friendly message with an
        # ``any(... for code/c in (...))`` comprehension containing the bare
        # English words 'Invalid'/'malformed'. That CODE construct must be gone
        # from the retry paths (the explanatory comment may still quote the old
        # tuple verbatim, so we match the comprehension form, not the literal).
        assert "for code in (" not in src
        assert "for c in (" not in src
        assert "_is_no_retry_error" in src


# ── TRANSPORT-A-003: EscrowInfo.sequence contract parity ─────────────────


class TestEscrowSequenceContractParity:
    """Both transports must agree on whether EscrowInfo.sequence is populated."""

    @pytest.mark.asyncio
    async def test_dry_run_still_sets_sequence(self, transport):
        """Dry-run continues to populate a non-zero create-sequence as before."""
        result = await transport.submit_escrow_create(
            "sWALLET", "10", "rDEST", finish_after=1_000_000_000,
        )
        assert result.success is True
        escrows = await transport.get_escrows(_DRY_RUN_WALLET_ADDRESS)
        assert len(escrows) == 1
        assert escrows[0].sequence > 0

    def test_base_docstring_does_not_promise_finish_until_implemented(self):
        """The base.py EscrowInfo.sequence doc must not claim it is 'needed to
        finish' while testnet leaves it 0 and no EscrowFinish exists — the two
        transports' contracts must agree (doc-route honesty fix)."""
        doc = (EscrowInfo.__doc__ or "")
        field_comments = inspect.getsource(EscrowInfo)
        combined = doc + field_comments
        assert "needed to finish" not in combined, (
            "sequence must not be documented as 'needed to finish' until "
            "EscrowFinish lands and testnet populates it"
        )


# ── Stage C (v2.0.0 proactive resilience) — TXBCD findings ────────────────


class _FetchErrorTransport(DryRunTransport):
    """DryRunTransport whose fetch_tx simulates a read-back NETWORK failure.

    Returns a TxInfo with ``fetch_error`` set (and result_code left empty),
    exactly as the testnet transport now does on a timeout / RPC error. Used to
    prove verify_tx special-cases the network-issue path without attributing a
    tx failure. Fully offline.
    """

    async def fetch_tx(self, txid: str) -> TxInfo:  # type: ignore[override]
        return TxInfo(
            txid=txid,
            fetch_error="Timed out fetching transaction. Try again.",
        )


# ── TXBCD-002: fetch failure must not be reported as a tx failure ─────────


class TestFetchErrorNotTxFailure:
    """verify_tx must treat a read-back failure as a network issue, not a
    transaction failure (TXBCD-002)."""

    @pytest.mark.asyncio
    async def test_verify_tx_surfaces_network_issue_message(self):
        from xrpl_lab.actions.verify import verify_tx

        transport = _FetchErrorTransport()
        result = await verify_tx(transport, "SOME_TXID", expected_success=True)

        assert result.passed is False
        # Exactly one failure, and it is the NON-failure-attributing message.
        assert len(result.failures) == 1
        msg = result.failures[0]
        assert "network issue" in msg
        assert "may still have succeeded on-ledger" in msg
        # It must NOT mis-report the network timeout as the tx failing
        # on-ledger via the old result_code comparison path.
        assert "Expected tesSUCCESS" not in msg
        assert not any("Expected tesSUCCESS" in f for f in result.failures)
        # The distinct field carried the network reason, not result_code.
        assert result.tx_info.fetch_error
        assert result.tx_info.result_code == ""

    @pytest.mark.asyncio
    async def test_normal_dry_run_fetch_still_verifies_success(self):
        """Regression: a normal (no fetch_error) tx still verifies as before."""
        from xrpl_lab.actions.verify import verify_tx

        transport = DryRunTransport()
        result = await verify_tx(transport, "ANYTXID", expected_success=True)
        assert result.passed is True
        assert result.tx_info.fetch_error is None
        assert any("tesSUCCESS" in c for c in result.checks)

    def test_txinfo_fetch_error_defaults_none(self):
        """Dry-run parity: TxInfo.fetch_error defaults None so existing
        construction (dry-run + success paths) is unchanged."""
        assert TxInfo(txid="x").fetch_error is None


# ── TXBCD-001: one bad entry must not zero the whole list ─────────────────


class TestPerEntryParseGuards:
    """The extracted per-entry parsers tolerate a single malformed entry."""

    def test_parse_nft_entry_well_formed(self):
        from xrpl_lab.transport.xrpl_testnet import _parse_nft_entry

        nft = _parse_nft_entry({
            "NFTokenID": "00080000ABC",
            "Issuer": "rISSUER",
            "NFTokenTaxon": 7,
            "Flags": 8,
            "TransferFee": 250,
            "nft_serial": 3,
        })
        assert nft.nft_id == "00080000ABC"
        assert nft.taxon == 7
        assert nft.transfer_fee == 250

    def test_parse_nft_entry_garbage_numeric_does_not_raise(self):
        """A non-numeric taxon/flag/fee must coerce to 0, not raise — so the
        caller doesn't drop the entry (and the loop doesn't zero the list)."""
        from xrpl_lab.transport.xrpl_testnet import _parse_nft_entry

        nft = _parse_nft_entry({
            "NFTokenID": "ID1",
            "NFTokenTaxon": "not-a-number",
            "Flags": None,
            "TransferFee": "",
        })
        assert nft.nft_id == "ID1"
        assert nft.taxon == 0
        assert nft.flags == 0
        assert nft.transfer_fee == 0

    def test_parse_nft_entry_missing_keys_uses_int_or_zero(self):
        from xrpl_lab.transport.xrpl_testnet import _parse_nft_entry

        nft = _parse_nft_entry({})
        assert nft.nft_id == ""
        assert nft.taxon == 0
        assert nft.serial == 0

    def test_parse_offer_entry_well_formed(self):
        from xrpl_lab.transport.xrpl_testnet import _parse_offer_entry

        offer = _parse_offer_entry({
            "Sequence": 42,
            "taker_pays": "1000000",
            "taker_gets": {"value": "10", "currency": "USD", "issuer": "rISSUERxxxxxxxxx"},
            "quality": "0.5",
        })
        assert offer.sequence == 42
        assert offer.taker_pays == "1000000"
        # dict amount renders cleanly, not as a Python repr.
        assert offer.taker_gets == "10/USD/rISSUERxxxxx"
        assert "{" not in offer.taker_gets

    def test_parse_offer_entry_garbage_sequence_coerces_zero(self):
        from xrpl_lab.transport.xrpl_testnet import _parse_offer_entry

        offer = _parse_offer_entry({"Sequence": "bad", "taker_pays": "1", "taker_gets": "2"})
        assert offer.sequence == 0

    def test_one_bad_entry_does_not_zero_the_list(self):
        """Simulate the get_account_nfts per-entry loop: a single malformed
        entry is skipped, the good ones survive (TXBCD-001 core guarantee)."""
        from xrpl_lab.transport.xrpl_testnet import _parse_nft_entry

        entries = [
            {"NFTokenID": "GOOD1", "NFTokenTaxon": 1},
            "this is not a dict — malformed",  # would raise in _parse_nft_entry
            {"NFTokenID": "GOOD2", "NFTokenTaxon": 2},
        ]
        out = []
        for n in entries:
            try:
                out.append(_parse_nft_entry(n))
            except Exception:
                continue
        assert [n.nft_id for n in out] == ["GOOD1", "GOOD2"], (
            "one malformed entry must not drop the good ones"
        )


# ── TXBCD-004: faucet 200 + non-JSON body triggers a retry, not opaque break ─


class TestFaucetNonJsonBody:
    """A 200 with a non-JSON body must yield a faucet-degraded message via the
    bounded retry loop, not an immediate opaque break (TXBCD-004)."""

    @pytest.mark.asyncio
    async def test_200_non_json_retries_then_returns_degraded(self, monkeypatch):
        from xrpl_lab.transport import xrpl_testnet
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        # Speed up the bounded retry's sleeps.
        async def _no_sleep(_):
            return None

        monkeypatch.setattr(xrpl_testnet.asyncio, "sleep", _no_sleep)

        class _HtmlResp:
            status_code = 200
            text = "<html>captive portal</html>"

            def json(self):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        calls = {"n": 0}

        class _FakeAsyncClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                calls["n"] += 1
                return _HtmlResp()

        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

        transport = XRPLTestnetTransport()
        result = await transport.fund_from_faucet("rDEST")

        assert result.success is False
        # The bounded retry ran (MAX_RETRIES + 1 attempts), not a single break.
        assert calls["n"] == xrpl_testnet.MAX_RETRIES + 1
        assert "not valid JSON" in result.message
        assert "--dry-run" in result.message
        assert result.code == "RUNTIME_FAUCET_DEGRADED"


# ── TXBCD-003: network-info failure logs at >= INFO with a safe reason ─────


class TestNetworkInfoFailureVisible:
    """get_network_info failure must be visible to a facilitator (TXBCD-003)."""

    @pytest.mark.asyncio
    async def test_failure_logs_at_warning_with_safe_reason(self, monkeypatch, caplog):
        from xrpl_lab.transport import xrpl_testnet
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        async def _boom(_client):
            raise ConnectionRefusedError("refused")

        monkeypatch.setattr(
            xrpl_testnet, "get_latest_validated_ledger_sequence", _boom
        )

        transport = XRPLTestnetTransport()
        with caplog.at_level(logging.INFO, logger=xrpl_testnet.logger.name):
            info = await transport.get_network_info()

        assert info.connected is False
        # A record at >= INFO must exist (the old logger.debug was invisible).
        relevant = [
            r for r in caplog.records
            if r.name == xrpl_testnet.logger.name and r.levelno >= logging.INFO
        ]
        assert relevant, "get_network_info failure must log at >= INFO"
        record = relevant[0]
        assert record.levelno >= logging.WARNING
        text = record.getMessage()
        assert text.strip(), "log message must not be empty"
        # Secret-safe: the friendly classifier maps to a fixed string and must
        # never echo a wallet seed (none is in scope here, but assert the
        # classified phrase is present).
        assert "Cannot connect to RPC endpoint" in text


# ── TXBCD-005: token-amount escrow Amount renders cleanly ─────────────────


class TestEscrowAmountFormatting:
    """_format_amount on a dict Amount yields value/currency/issuer, not a repr
    (TXBCD-005)."""

    def test_format_amount_dict_is_clean(self):
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        out = XRPLTestnetTransport._format_amount(
            {"value": "100", "currency": "USD", "issuer": "rISSUERxxxxxxxxxxxx"}
        )
        assert out == "100/USD/rISSUERxxxxx"
        assert "{" not in out and "'" not in out

    def test_format_amount_xrp_drops_passthrough(self):
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        assert XRPLTestnetTransport._format_amount("10000000") == "10000000"


# ── TXBCD-008: ledger_index coercion helper ───────────────────────────────


class TestIntOrNoneHelper:
    """_int_or_none normalizes RPC ledger_index into int | None (TXBCD-008)."""

    def test_int_passthrough(self):
        from xrpl_lab.transport.xrpl_testnet import _int_or_none

        assert _int_or_none(12345) == 12345

    def test_numeric_string_coerced(self):
        from xrpl_lab.transport.xrpl_testnet import _int_or_none

        assert _int_or_none("12345") == 12345

    def test_none_stays_none(self):
        from xrpl_lab.transport.xrpl_testnet import _int_or_none

        assert _int_or_none(None) is None

    def test_garbage_string_becomes_none(self):
        from xrpl_lab.transport.xrpl_testnet import _int_or_none

        assert _int_or_none("validated") is None

    def test_bool_rejected(self):
        """bool is an int subclass; a stray True/False must not become 1/0."""
        from xrpl_lab.transport.xrpl_testnet import _int_or_none

        assert _int_or_none(True) is None
