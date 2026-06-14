"""Tests for dry-run transport."""

import pytest

from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport():
    return DryRunTransport()


class TestDryRunTransport:
    @pytest.mark.asyncio
    async def test_network_info(self, transport):
        info = await transport.get_network_info()
        assert info.connected is True
        assert info.network == "dry-run"
        assert info.ledger_index is not None

    @pytest.mark.asyncio
    async def test_fund(self, transport):
        result = await transport.fund_from_faucet("rTEST123")
        assert result.success is True
        assert result.address == "rTEST123"
        assert "1000" in result.balance

    @pytest.mark.asyncio
    async def test_submit_success(self, transport):
        result = await transport.submit_payment(
            wallet_seed="sFAKESEED",
            destination="rDEST",
            amount="10",
            memo="test",
        )
        assert result.success is True
        assert result.txid != ""
        assert result.result_code == "tesSUCCESS"
        assert result.explorer_url != ""

    @pytest.mark.asyncio
    async def test_submit_fail(self, transport):
        """Exercise the REAL failure path inside DryRunTransport.submit_payment.

        F-TESTS-004: previously this test toggled ``set_fail_next()`` — a
        back-door switch — so the production failure code (``Decimal(amount)``
        validation) was never exercised. We now feed a non-numeric amount,
        which goes through the actual ``except`` branch in submit_payment and
        returns ``temBAD_AMOUNT``.
        """
        result = await transport.submit_payment(
            wallet_seed="sFAKESEED",
            destination="rDEST",
            amount="not_a_number",
        )
        assert result.success is False
        assert result.result_code == "temBAD_AMOUNT"
        assert result.txid == ""
        assert "not_a_number" in result.error
        assert "Invalid amount" in result.error

    @pytest.mark.asyncio
    async def test_fail_resets(self, transport):
        transport.set_fail_next()
        await transport.submit_payment("s", "r", "1")
        # Second submit should succeed
        result = await transport.submit_payment("s", "r", "1")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_fetch_tx(self, transport):
        result = await transport.submit_payment("s", "r", "1")
        tx = await transport.fetch_tx(result.txid)
        assert tx.txid == result.txid
        assert tx.tx_type == "Payment"
        assert tx.validated is True

    @pytest.mark.asyncio
    async def test_balance(self, transport):
        assert await transport.get_balance("rUNFUNDED") == "0"
        await transport.fund_from_faucet("rFUNDED")
        assert await transport.get_balance("rFUNDED") == "1000.000000"

    @pytest.mark.asyncio
    async def test_unique_txids(self, transport):
        r1 = await transport.submit_payment("s", "r", "1")
        r2 = await transport.submit_payment("s", "r", "1")
        assert r1.txid != r2.txid

    @pytest.mark.asyncio
    async def test_payment_rejects_when_insufficient_balance(self, transport):
        """F-BRIDGE-B-DRY-NEG-BAL — funded sender can't go negative.

        Previously submit_payment debited unconditionally; the sender's
        balance went negative and ``get_balance()`` clamped the display to
        "0", masking the violation. The fix pre-validates the balance and
        returns tecUNFUNDED_PAYMENT (matching real testnet behavior).
        """
        # Fund the sender so its balance is tracked (1000 XRP = 1e9 drops).
        from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS

        await transport.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)

        # Attempt to send 2000 XRP — double the balance. Must be rejected.
        result = await transport.submit_payment(
            wallet_seed="sFAKESEED",
            destination="rDEST",
            amount="2000",
        )

        assert result.success is False
        assert result.result_code == "tecUNFUNDED_PAYMENT"
        assert result.txid == ""
        assert "insufficient" in result.error.lower()

        # Sender balance must NOT have been debited on rejection.
        balance = await transport.get_balance(_DRY_RUN_WALLET_ADDRESS)
        # 1000 XRP, untouched.
        assert balance == "1000.000000"


# ── XRPLTestnetTransport — real-network paths (mocked, no live calls) ──
#
# The dry-run transport above is fully exercised; the REAL transport's
# retry/timeout/backoff loops, the network-aware explorer URL, the faucet
# backoff cap, and the RPC-down branch of get_network_info were untested
# (B-TESTS-001, B-TESTS-003, B-CIDOCS-002, B-BRIDGE-NET-006). Every test
# here MOCKS the network — no socket is ever opened.

# A real, structurally-valid testnet seed so ``Wallet.from_seed`` succeeds
# offline (it derives a keypair locally, no network). Using a real seed
# lets the retry loop reach ``submit_and_wait`` (the part we mock) instead
# of failing early in wallet construction.
_VALID_TESTNET_SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"


class _FakeResponse:
    """Minimal stand-in for an xrpl-py submit_and_wait response."""

    def __init__(self, result: dict) -> None:
        self.result = result


def _success_result(txid: str = "ABCD1234") -> dict:
    """A tesSUCCESS submit_and_wait result payload."""
    return {
        "hash": txid,
        "Fee": "12",
        "ledger_index": 99,
        "meta": {"TransactionResult": "tesSUCCESS"},
    }


class _FakeAsyncClient:
    """Async-context-manager stand-in for AsyncJsonRpcClient.

    The transport only uses it as ``async with AsyncJsonRpcClient(url) as
    client``; the actual submit goes through ``submit_and_wait`` which we
    patch separately, so this client needs no behavior beyond the CM
    protocol.
    """

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def _patch_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the testnet transport's network surface so no socket opens.

    Replaces ``AsyncJsonRpcClient`` (the RPC client CM) and short-circuits
    ``asyncio.sleep`` so retry backoff doesn't actually wait. Tests still
    patch ``submit_and_wait`` themselves to drive the per-attempt outcome.
    """
    from xrpl_lab.transport import xrpl_testnet as xt

    monkeypatch.setattr(xt, "AsyncJsonRpcClient", _FakeAsyncClient)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(xt.asyncio, "sleep", _no_sleep)


class TestTestnetSubmitRetry:
    """B-TESTS-001 — submit retry/timeout/backoff loops, network mocked."""

    @pytest.fixture()
    def testnet(self, monkeypatch: pytest.MonkeyPatch):
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        _patch_no_network(monkeypatch)
        return XRPLTestnetTransport()

    @pytest.mark.asyncio
    async def test_submit_payment_retries_after_timeout_then_succeeds(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First submit_and_wait raises TimeoutError, second succeeds.

        Asserts the retry actually fired (2 calls) and the final result is
        the success from the second attempt — locking in that a transient
        testnet timeout is recovered, not surfaced to the learner.
        """
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _fake_submit(tx, client, wallet):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("first attempt times out")
            return _FakeResponse(_success_result("TXRETRY"))

        monkeypatch.setattr(xt, "submit_and_wait", _fake_submit)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED,
            destination="rDEST",
            amount="10",
        )

        assert calls["n"] == 2, "expected exactly one retry after the timeout"
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid == "TXRETRY"

    @pytest.mark.asyncio
    async def test_submit_payment_retries_exhausted_returns_local_error(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every attempt times out → all MAX_RETRIES+1 attempts run, and the
        final result is a structured local_error (not a raised exception)."""
        from xrpl_lab.transport import xrpl_testnet as xt
        from xrpl_lab.transport.xrpl_testnet import MAX_RETRIES

        calls = {"n": 0}

        async def _always_timeout(tx, client, wallet):
            calls["n"] += 1
            raise TimeoutError("perpetual timeout")

        monkeypatch.setattr(xt, "submit_and_wait", _always_timeout)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED,
            destination="rDEST",
            amount="10",
        )

        assert calls["n"] == MAX_RETRIES + 1, (
            f"expected {MAX_RETRIES + 1} attempts (initial + retries), "
            f"got {calls['n']}"
        )
        assert result.success is False
        assert result.result_code == "local_error"
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_submit_trust_set_retries_after_timeout_then_succeeds(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """B-TESTS-001 (second submit_* path) — TrustSet timeout-then-success.

        Covers a non-payment write path so the shared retry-loop contract
        is pinned on more than one method.
        """
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _fake_submit(tx, client, wallet):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("trust set first attempt times out")
            return _FakeResponse(_success_result("TXTRUST"))

        monkeypatch.setattr(xt, "submit_and_wait", _fake_submit)

        result = await testnet.submit_trust_set(
            wallet_seed=_VALID_TESTNET_SEED,
            issuer="rISSUER",
            currency="USD",
            limit="1000",
        )

        assert calls["n"] == 2
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid == "TXTRUST"

    @pytest.mark.asyncio
    async def test_submit_payment_malformed_tx_does_not_retry(
        self, testnet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed-tx error (temBAD...) must break immediately — the
        retry loop only retries transient faults, never deterministic
        rejections. Asserts a single attempt and a local_error result."""
        from xrpl_lab.transport import xrpl_testnet as xt

        calls = {"n": 0}

        async def _malformed(tx, client, wallet):
            calls["n"] += 1
            raise ValueError("temBAD_AMOUNT: malformed")

        monkeypatch.setattr(xt, "submit_and_wait", _malformed)

        result = await testnet.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED,
            destination="rDEST",
            amount="10",
        )

        assert calls["n"] == 1, "malformed-tx errors must not be retried"
        assert result.success is False
        assert result.result_code == "local_error"


class TestTestnetExplorerUrl:
    """B-CIDOCS-002 — SubmitResult.explorer_url is network-aware."""

    def _transport_for(self, monkeypatch: pytest.MonkeyPatch, rpc_url: str):
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.setenv("XRPL_LAB_RPC_URL", rpc_url)
        _patch_no_network(monkeypatch)
        return xt.XRPLTestnetTransport()

    async def _submit_and_get_url(
        self, monkeypatch: pytest.MonkeyPatch, rpc_url: str
    ) -> str:
        from xrpl_lab.transport import xrpl_testnet as xt

        async def _ok(tx, client, wallet):
            return _FakeResponse(_success_result("EXPLORERTX"))

        monkeypatch.setattr(xt, "submit_and_wait", _ok)
        transport = self._transport_for(monkeypatch, rpc_url)
        result = await transport.submit_payment(
            wallet_seed=_VALID_TESTNET_SEED, destination="rDEST", amount="1"
        )
        assert result.success is True
        return result.explorer_url

    @pytest.mark.asyncio
    async def test_testnet_rpc_yields_testnet_explorer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        url = await self._submit_and_get_url(
            monkeypatch, "https://s.altnet.rippletest.net:51234"
        )
        assert url == "https://testnet.xrpl.org/transactions/EXPLORERTX"

    @pytest.mark.asyncio
    async def test_devnet_rpc_yields_devnet_explorer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        url = await self._submit_and_get_url(
            monkeypatch, "https://s.devnet.rippletest.net:51234"
        )
        assert url == "https://devnet.xrpl.org/transactions/EXPLORERTX"

    @pytest.mark.asyncio
    async def test_local_rpc_yields_no_explorer_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """local/unknown endpoints get an empty explorer URL — a broken
        link to a public explorer is worse than no link."""
        url = await self._submit_and_get_url(
            monkeypatch, "http://localhost:5005"
        )
        assert url == ""

    def test_explorer_url_helper_empty_for_empty_txid(self) -> None:
        """The helper returns "" when there's no txid, regardless of network."""
        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        transport = XRPLTestnetTransport()
        assert transport._explorer_url("") == ""


class TestTestnetGetNetworkInfo:
    """B-TESTS-003 — get_network_info connected=False (RPC-down) branch."""

    @pytest.mark.asyncio
    async def test_rpc_down_reports_disconnected_with_real_network_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the RPC ledger lookup raises, get_network_info must return
        connected=False, ledger_index=None, and the network label derived
        from the (now network-aware) endpoint classification — not a hard
        "testnet" and not a raised exception."""
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s.altnet.rippletest.net:51234")
        monkeypatch.setattr(xt, "AsyncJsonRpcClient", _FakeAsyncClient)

        async def _boom(client):
            raise ConnectionError("RPC unreachable")

        monkeypatch.setattr(xt, "get_latest_validated_ledger_sequence", _boom)

        transport = xt.XRPLTestnetTransport()
        info = await transport.get_network_info()

        assert info.connected is False
        assert info.ledger_index is None
        assert info.network == "testnet"
        assert info.rpc_url == "https://s.altnet.rippletest.net:51234"

    @pytest.mark.asyncio
    async def test_rpc_down_on_devnet_reports_devnet_label(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The disconnected branch reports the ACTUAL network (devnet here),
        proving the label isn't hard-coded to testnet on the failure path."""
        from xrpl_lab.transport import xrpl_testnet as xt

        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s.devnet.rippletest.net:51234")
        monkeypatch.setattr(xt, "AsyncJsonRpcClient", _FakeAsyncClient)

        async def _boom(client):
            raise ConnectionError("RPC unreachable")

        monkeypatch.setattr(xt, "get_latest_validated_ledger_sequence", _boom)

        transport = xt.XRPLTestnetTransport()
        info = await transport.get_network_info()

        assert info.connected is False
        assert info.network == "devnet"


class TestFaucetBackoffCap:
    """B-BRIDGE-NET-006 — the 429 retry backoff sleep is bounded."""

    @pytest.mark.asyncio
    async def test_faucet_429_backoff_is_capped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive 3 consecutive 429s and capture the sleep durations. Each
        in-request backoff sleep must be <= FAUCET_MAX_BACKOFF — so a caller
        (and the dashboard queue) never eats an unbounded blocking wait.
        The retry COUNT is unchanged: exactly MAX_RETRIES backoff sleeps."""
        from unittest.mock import AsyncMock, MagicMock

        from xrpl_lab.transport import xrpl_testnet as xt
        from xrpl_lab.transport.xrpl_testnet import (
            FAUCET_MAX_BACKOFF,
            MAX_RETRIES,
            XRPLTestnetTransport,
        )

        fake_429 = MagicMock()
        fake_429.status_code = 429
        fake_429.text = "rate limit exceeded"

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.post = AsyncMock(return_value=fake_429)

        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake_client)

        slept: list[float] = []

        async def _record_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(xt.asyncio, "sleep", _record_sleep)

        result = await XRPLTestnetTransport().fund_from_faucet("rTEST")

        assert result.success is False
        assert result.code == "RUNTIME_FAUCET_RATE_LIMITED"
        # Retry count unchanged: one backoff sleep per retry attempt.
        assert len(slept) == MAX_RETRIES, (
            f"expected {MAX_RETRIES} backoff sleeps, got {len(slept)}: {slept}"
        )
        # Every sleep is bounded by the documented ceiling.
        for s in slept:
            assert s <= FAUCET_MAX_BACKOFF, (
                f"backoff sleep {s}s exceeds cap {FAUCET_MAX_BACKOFF}s"
            )
