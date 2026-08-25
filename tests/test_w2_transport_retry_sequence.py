"""Wave-2 transport regression tests for F-ad982e08.

F-ad982e08: a non-timeout, post-broadcast retry in ``submit_payment`` / the
shared ``_submit_tx`` helper could land a genuine DUPLICATE transaction on
live testnet. The prior regression test (test_reswarm3_transport.py::
test_payment_retry_resubmits_same_tx_object_not_a_rebuilt_one) mocked
``submit_and_wait`` entirely and asserted Python object IDENTITY across the
two attempts. That is not the property at risk: ``Transaction`` is a frozen
dataclass, and xrpl-py's ``autofill()`` (called inside the REAL
``submit_and_wait`` for any unsigned tx) calls ``get_next_valid_seq_number()``
fresh whenever the model has no ``sequence`` set — on EVERY call, regardless
of whether the exact same Python object is handed back in. So the old test
could (and did) pass against code that re-autofills a brand-new Sequence on
every retry attempt, because it never let real autofill machinery run at
all — mocking away ``submit_and_wait`` wholesale also mocks away the only
place the bug could show itself.

The fix (xrpl_lab/transport/xrpl_testnet.py: ``_pin_sequence``, called from
``_submit_tx`` and therefore from every submit_* method that delegates to
it, including ``submit_payment``) fetches the account's next Sequence via
the REAL ``xrpl.asyncio.account.get_next_valid_seq_number`` exactly ONCE,
before the retry loop, and bakes it into the unsigned tx model. Because
xrpl-py's ``autofill()`` only fetches a Sequence when the model doesn't
already have one, every attempt (including retries) reuses that SAME pinned
value — closing the duplicate-Sequence gap without needing to mock away
``submit_and_wait`` (whose OWN retry/timeout/tec-code semantics are already
covered by test_transport.py / test_reswarm4_transport.py and are
deliberately left alone here).

These tests exercise the REAL ``get_next_valid_seq_number`` /
``get_account_root`` call graph — the actual xrpl-py "fresh Sequence"
machinery named in the advisor contract — faking only the raw JSON-RPC
transport (``Client._request_impl``), which is the network seam every other
test in this suite also fakes. ``submit_and_wait`` itself is mocked (to
script "fails once, then succeeds" deterministically) because it is not the
code under test here; what matters is what Sequence gets baked into the tx
BEFORE submit_and_wait ever sees it, on every attempt.

If ``_pin_sequence`` (or the call to it) is removed, these tests go RED:
the account-info lookup never happens (asserted via a call counter) and the
tx handed to submit_and_wait carries ``sequence=None`` on every attempt
instead of the fetched value — see the docstring of each test for the exact
failure this was verified to produce against the unfixed tree.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from xrpl.models.requests import AccountInfo

from xrpl_lab.transport import xrpl_testnet as mod
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

# A real, structurally-valid testnet seed so Wallet.from_seed succeeds
# offline (it derives a keypair locally, no network) — same style as the
# sibling-owned tests in test_transport.py / test_reswarm3_transport.py.
_VALID_SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"

_PINNED_SEQUENCE = 5_010_042


class _FakeAccountInfoResponse:
    """Duck-typed stand-in for the xrpl-py Response returned by AccountInfo."""

    def __init__(self, sequence: int) -> None:
        self.result = {"account_data": {"Sequence": sequence}}

    def is_successful(self) -> bool:
        return True


class _SeqOnlyClient:
    """Fake RPC client that answers ONLY AccountInfo (via ``_request_impl``).

    This is the exact low-level method ``get_next_valid_seq_number`` ->
    ``get_account_root`` calls — NOT the higher-level ``.request()``
    convenience wrapper other fakes in this suite implement — so this fake
    genuinely exercises xrpl-py's real sequence-lookup code path rather than
    a hand-rolled stand-in for it. Records every request it sees.
    """

    def __init__(self, sequence: int, calls: list) -> None:
        self._sequence = sequence
        self._calls = calls

    async def _request_impl(self, request, *, timeout=None):
        self._calls.append(request)
        if isinstance(request, AccountInfo):
            return _FakeAccountInfoResponse(self._sequence)
        raise AssertionError(f"unexpected RPC request in test: {request!r}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _patch_network(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    monkeypatch.setattr(
        mod, "_rpc_client", lambda url: _SeqOnlyClient(_PINNED_SEQUENCE, calls)
    )

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)


@pytest.mark.asyncio
async def test_submit_payment_pins_sequence_across_nontimeout_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """submit_payment: a non-timeout retry reuses the ONE fetched Sequence.

    Scripts submit_and_wait to fail with a plain ConnectionError (the
    ambiguous, non-timeout, post-broadcast failure class F-ad982e08 is about)
    on the first attempt and succeed on the second, and records the
    ``.sequence`` xrpl-py would have baked into the tx on each attempt.

    Verified RED against the unfixed tree (``_submit_tx`` calling
    ``submit_and_wait(tx, client, wallet)`` directly, no ``_pin_sequence``):
    this test failed with
        AssertionError: assert 0 == 1
    on the ``account_info_requests`` count — the old code never calls
    ``get_next_valid_seq_number`` at all, so the AccountInfo lookup this test
    installs is never reached, and (checked via the second assertion)
    ``submitted_sequences`` was ``[None, None]`` instead of
    ``[5010042, 5010042]`` — the exact "object identity but no real sequence
    pinning" gap the advisor contract describes.
    """
    account_info_requests: list = []
    _patch_network(monkeypatch, account_info_requests)

    submitted_sequences: list = []
    calls = {"n": 0}

    class _OkResp:
        result = {
            "meta": {"TransactionResult": "tesSUCCESS"},
            "hash": "DEADBEEF" + "0" * 56,
            "Fee": "12",
            "ledger_index": 55_555_555,
        }

    async def fake_submit_and_wait(tx, client, wallet=None, **kwargs):
        submitted_sequences.append(tx.sequence)
        calls["n"] += 1
        if calls["n"] == 1:
            # The ambiguous, non-timeout, post-broadcast failure class this
            # finding is about (e.g. a dropped connection on one of
            # submit_and_wait's internal Tx-by-hash polling calls) — NOT a
            # TimeoutError and NOT an XRPLReliableSubmissionException, both
            # of which already have separate, correct handling.
            raise ConnectionError("temporary network blip")
        return _OkResp()

    monkeypatch.setattr(mod, "submit_and_wait", fake_submit_and_wait)

    transport = XRPLTestnetTransport()
    res = await transport.submit_payment(_VALID_SEED, "rDEST", "10")

    assert calls["n"] == 2, f"expected one retry, got {calls['n']} attempts"
    assert res.success is True

    # The real get_next_valid_seq_number -> get_account_root -> AccountInfo
    # lookup ran exactly ONCE — not once per attempt.
    assert len(account_info_requests) == 1, (
        "sequence must be fetched ONCE before the retry loop, not per "
        f"attempt — saw {len(account_info_requests)} AccountInfo lookups"
    )

    # Both attempts carried the SAME, REAL fetched Sequence — not None
    # (never pinned) and not two DIFFERENT freshly-autofilled values.
    assert submitted_sequences == [_PINNED_SEQUENCE, _PINNED_SEQUENCE], (
        f"expected both attempts to reuse the pinned Sequence "
        f"{_PINNED_SEQUENCE}, got {submitted_sequences} — a retry that gets "
        "a fresh Sequence can land a second, independent, valid transaction "
        "if the first one actually broadcast successfully"
    )


@pytest.mark.asyncio
async def test_submit_offer_create_pins_sequence_across_nontimeout_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SHARED ``_submit_tx`` helper (~30 other submit_* methods) is fixed
    too, not just submit_payment's own (former) bespoke loop.

    Same scripted failure-then-success shape as the submit_payment test
    above, driven through a completely different write method
    (``submit_offer_create``) that has always delegated to ``_submit_tx``.
    Verified RED the same way: on the unfixed ``_submit_tx``, the AccountInfo
    lookup count is 0 and ``submitted_sequences`` is ``[None, None]``.
    """
    account_info_requests: list = []
    _patch_network(monkeypatch, account_info_requests)

    submitted_sequences: list = []
    calls = {"n": 0}

    class _OkResp:
        result = {
            "meta": {"TransactionResult": "tesSUCCESS"},
            "hash": "FEEDFACE" + "0" * 56,
            "Fee": "12",
            "ledger_index": 55_555_556,
        }

    async def fake_submit_and_wait(tx, client, wallet=None, **kwargs):
        submitted_sequences.append(tx.sequence)
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("temporary network blip")
        return _OkResp()

    monkeypatch.setattr(mod, "submit_and_wait", fake_submit_and_wait)

    transport = XRPLTestnetTransport()
    res = await transport.submit_offer_create(
        _VALID_SEED, "USD", "10", "rISSUER", "XRP", "5", "",
    )

    assert calls["n"] == 2
    assert res.success is True
    assert len(account_info_requests) == 1, (
        "the shared _submit_tx helper must pin the Sequence ONCE too — saw "
        f"{len(account_info_requests)} AccountInfo lookups"
    )
    assert submitted_sequences == [_PINNED_SEQUENCE, _PINNED_SEQUENCE]


@pytest.mark.asyncio
async def test_pin_sequence_falls_back_silently_when_lookup_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_pin_sequence`` degrades to a no-op, not an exception, when the
    account-info lookup can't be served (e.g. every other test's fully
    network-mocked fixture, which fakes only the higher-level
    ``client.request()`` convenience method rather than ``_request_impl``).

    This is what keeps the fix's blast radius at zero on the ~15 pre-existing
    submit_and_wait-mocking tests across test_transport.py /
    test_reswarm3_transport.py / test_reswarm3_stagec_transport.py /
    test_reswarm4_transport.py: none of those fakes implement
    ``_request_impl``, so the lookup raises AttributeError internally, which
    ``_pin_sequence`` swallows and returns the tx UNCHANGED.
    """
    from xrpl.models.transactions import Payment
    from xrpl.utils import xrp_to_drops

    class _NoLowLevelClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "_rpc_client", lambda url: _NoLowLevelClient())

    tx = Payment(
        account="rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
        destination="rDEST",
        amount=xrp_to_drops(10),
    )
    assert tx.sequence is None

    pinned = await mod._pin_sequence("https://example.invalid", tx, "Payment")

    assert pinned.sequence is None
    assert pinned is tx


@pytest.mark.asyncio
async def test_pin_sequence_noop_when_already_signed_or_sequenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already-signed (multisig combine) or already-sequenced transactions
    are left alone — the lookup must not even be attempted."""
    from xrpl.models.transactions import Payment
    from xrpl.utils import xrp_to_drops

    account_info_requests: list = []
    _patch_network(monkeypatch, account_info_requests)

    tx_with_sequence = Payment(
        account="rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
        destination="rDEST",
        amount=xrp_to_drops(10),
        sequence=777,
    )
    pinned = await mod._pin_sequence("https://example.invalid", tx_with_sequence, "Payment")
    assert pinned is tx_with_sequence
    assert pinned.sequence == 777
    assert account_info_requests == []
