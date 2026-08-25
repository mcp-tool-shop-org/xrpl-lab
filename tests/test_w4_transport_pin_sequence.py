"""Wave-4 transport regression for F-5eb1025c (_pin_sequence silent revert).

Advisor lock: failure to pin must be visible (WARNING) AND must not proceed
into a retry loop that can double-submit. unpin = no retry.

These tests exercise the *exception path* of ``_pin_sequence`` — the path
call-site enumeration alone would not catch — not only the happy pin.
"""

from __future__ import annotations

import logging

import pytest

from xrpl_lab.transport import xrpl_testnet as mod
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

_VALID_SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"


@pytest.mark.asyncio
async def test_unpinned_submit_refuses_nontimeout_retry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When Sequence prefetch fails, ``_submit_tx`` must not retry.

    Scripts a ConnectionError on the first ``submit_and_wait`` (the ambiguous
    post-broadcast failure class). With the pin lookup unavailable, a retry
    would autofill a fresh Sequence and re-open F-ad982e08. The contract is
    unpin = no retry: exactly one attempt, failure result, and a WARNING that
    the prefetch failed / retry was refused.
    """

    class _NoLowLevelClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "_rpc_client", lambda url: _NoLowLevelClient())

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)

    calls = {"n": 0}

    async def fake_submit_and_wait(tx, client, wallet=None, **kwargs):
        calls["n"] += 1
        raise ConnectionError("temporary network blip")

    monkeypatch.setattr(mod, "submit_and_wait", fake_submit_and_wait)

    transport = XRPLTestnetTransport()
    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        res = await transport.submit_payment(
            _VALID_SEED, "rDEST", "10",
        )

    assert calls["n"] == 1, (
        "unpin = no retry: expected a single submit attempt when Sequence "
        f"was not pinned, got {calls['n']}"
    )
    assert res.success is False
    assert res.result_code == "local_error"

    warnings = [
        r.getMessage().lower()
        for r in caplog.records
        if r.name == mod.logger.name and r.levelno >= logging.WARNING
    ]
    assert any(
        ("pre-fetch" in w)
        or ("prefetch" in w)
        or ("not retrying" in w)
        or ("refusing" in w)
        or ("sequence" in w and "pin" in w)
        for w in warnings
    ), f"expected a visible pin-failure / no-retry warning; got {warnings}"
