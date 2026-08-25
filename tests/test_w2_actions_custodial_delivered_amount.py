"""Regression tests for F-c918543c: credit_player_deposit() mislabeling a
non-XRP delivered_amount as drops.

``_format_amount`` (xrpl_testnet.py, mirrored in dry_run.py) renders an
issued-currency ``delivered_amount`` as ``"value/currency/issuer"`` (e.g.
``"50/LAB/rIssuer12345678"``) -- never a bare integer. Before this fix,
``credit_player_deposit()`` read that string straight into
``credited_drops`` and hard-coded the word "drops" in its check message
regardless of currency: a non-XRP deposit produced a nonsensical
"Credited 50/LAB/rIssuer... drops" message and a mis-shaped
``credited_drops`` value. ``tests/test_custodial.py`` (the pre-existing
suite) only ever exercises XRP-denominated deposits, so this path shipped
completely unguarded and untested -- this file closes that gap.

A minimal duck-typed ``Transport`` stub is used instead of driving
``DryRunTransport`` end-to-end: ``credit_player_deposit``'s only contact
with the transport is ``await transport.fetch_tx(txid)``, and
``send_tagged_deposit`` is itself XRP-only by design (its docstring says
so), so it cannot produce an issued-currency deposit to fetch back. The
real bug surface is any transaction landing on the pool address with a
valid tag, regardless of how it got sent -- the stub isolates exactly
that.
"""

from __future__ import annotations

import pytest

from xrpl_lab.actions.custodial import credit_player_deposit
from xrpl_lab.transport.base import TxInfo

_POOL = "rPOOLTREASURY00000000000000"


class _OneShotTransport:
    """Minimal Transport stub: fetch_tx always returns one canned TxInfo."""

    def __init__(self, tx: TxInfo) -> None:
        self._tx = tx

    async def fetch_tx(self, txid: str) -> TxInfo:
        return self._tx


def _deposit_with_delivered(delivered_amount: str, tag: int = 1001) -> _OneShotTransport:
    return _OneShotTransport(
        TxInfo(
            txid="FAKETX",
            tx_type="Payment",
            destination=_POOL,
            amount=delivered_amount,
            result_code="tesSUCCESS",
            validated=True,
            delivered_amount=delivered_amount,
            destination_tag=tag,
        )
    )


@pytest.mark.asyncio
async def test_issued_currency_deposit_is_not_labeled_drops():
    """The literal bug: the check message must not say 'drops' for a
    non-XRP delivered_amount."""
    t = _deposit_with_delivered("50/LAB/rIssuer12345678")
    result = await credit_player_deposit(t, "FAKETX", {1001: "arya"})
    assert result.passed, result.failures
    assert not any("drops" in c.lower() for c in result.checks), (
        f"non-XRP deposit's checks still say 'drops': {result.checks}"
    )


@pytest.mark.asyncio
async def test_issued_currency_credited_drops_field_is_not_the_raw_display_string():
    """``credited_drops`` is a drops-shaped field; a 'value/currency/issuer'
    display string must never land in it -- that IS the mislabeling."""
    t = _deposit_with_delivered("50/LAB/rIssuer12345678")
    result = await credit_player_deposit(t, "FAKETX", {1001: "arya"})
    assert result.passed, result.failures
    assert "/" not in result.credited_drops, (
        f"credited_drops still holds an issued-currency display string: "
        f"{result.credited_drops!r}"
    )


@pytest.mark.asyncio
async def test_issued_currency_deposit_reports_correct_currency_and_issuer():
    """Credit must be derived from the real delivered value WITH its
    correct currency/issuer (the advisor contract's affirmative
    requirement -- not merely 'don't say drops')."""
    t = _deposit_with_delivered("50/LAB/rIssuer12345678")
    result = await credit_player_deposit(t, "FAKETX", {1001: "arya"})
    assert result.passed, result.failures
    assert result.currency == "LAB"
    assert result.issuer == "rIssuer12345678"
    assert result.credited_value == "50"


@pytest.mark.asyncio
async def test_xrp_deposit_still_labeled_drops_and_credited_drops_populated():
    """Guard the happy path: the fix must not regress existing, correct
    XRP behaviour."""
    t = _deposit_with_delivered("25000000")
    result = await credit_player_deposit(t, "FAKETX", {1001: "arya"})
    assert result.passed, result.failures
    assert result.credited_drops == "25000000"
    assert result.credited_value == "25000000"
    assert result.currency == "XRP"
    assert result.issuer == ""
    assert any("drops" in c.lower() for c in result.checks)


@pytest.mark.asyncio
async def test_issued_currency_expected_drops_mismatch_still_an_honest_failure():
    """A caller that (mis)uses ``expected_drops`` against a non-XRP
    deposit still gets an honest, non-crashing failure -- no silent
    mislabeling, no traceback."""
    t = _deposit_with_delivered("50/LAB/rIssuer12345678")
    result = await credit_player_deposit(
        t, "FAKETX", {1001: "arya"}, expected_drops="999"
    )
    assert not result.passed
    assert any("mismatch" in f for f in result.failures)
