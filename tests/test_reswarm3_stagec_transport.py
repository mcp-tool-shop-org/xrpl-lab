"""Regression tests pinning the 2026-07 re-swarm Stage-C transport fixes.

Each test anchors one finding so the fix cannot silently regress.

- PT-001: dry-run AMM methods (``submit_amm_create`` / ``submit_amm_deposit`` /
  ``submit_amm_withdraw``) did raw ``Decimal(...)`` math on UNVALIDATED input.
  A negative XRP leg crashed the sqrt with an uncaught ``InvalidOperation`` (the
  runner showed an opaque ``Step failed: InvalidOperation`` instead of a
  teachable ``temBAD_AMOUNT``); a non-numeric leg crashed with
  ``ConversionSyntax``. Every XRP leg now flows through ``_validate_xrp_amount``
  and every issued-currency / LP leg through an explicit negative/non-numeric
  guard, so a bad amount surfaces as ``temBAD_AMOUNT`` with no crash.

- PT-002 (the load-bearing one): a NEGATIVE deposit on an EXISTING pool
  SILENTLY SUCCEEDED (``tesSUCCESS``), SHRANK the pool, and credited negative
  LP — silent state corruption teaching a physically-impossible outcome
  (confirmed: deposit -5 on 100/100 -> tesSUCCESS, pool 95/95, LP 95). It must
  now be REJECTED with ``temBAD_AMOUNT`` BEFORE the ratio math, leaving the pool
  UNCHANGED.

- PT-003: ``actions/paychan.py`` ``verify_channel._want()`` did an unguarded
  ``int(Decimal(xrp) * 1e6)`` (unlike the guarded ``_drops_to_xrp`` right above
  it), so a non-numeric ``expect_amount_xrp`` raised instead of appending a
  parse-failure to ``failures``.

- PT-004: testnet ``submit_payment`` / ``submit_offer_create`` /
  ``submit_offer_cancel`` can resubmit after a NON-TIMEOUT post-broadcast
  failure -> possible duplicate on-ledger tx (the documented residual). The
  non-timeout retry branch now logs a ``warning`` so a facilitator can spot a
  possible double-submit in the logs.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from xrpl_lab.actions.paychan import ChannelVerifyResult, verify_channel
from xrpl_lab.transport.base import ChannelInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# ── PT-001: AMM create rejects bad XRP / issued legs (no crash) ────────────


@pytest.mark.asyncio
async def test_amm_create_negative_xrp_leg_rejected_no_crash():
    """A negative XRP leg on AMMCreate -> temBAD_AMOUNT, not an InvalidOperation.

    Previously ``(Decimal(-100) * Decimal(100)).sqrt()`` raised an uncaught
    InvalidOperation, surfacing as an opaque ``Step failed: InvalidOperation``.
    """
    t = DryRunTransport()
    res = await t.submit_amm_create(
        "sFAKE", "XRP", "-100", "", "LAB", "100", "rISSUER",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"
    # And no pool was created from the bad input.
    assert await t.get_amm_info("XRP", "", "LAB", "rISSUER") is None


@pytest.mark.asyncio
async def test_amm_create_nonnumeric_leg_rejected_no_conversion_error():
    """A non-numeric leg on AMMCreate -> temBAD_AMOUNT, not a ConversionSyntax."""
    t = DryRunTransport()
    res = await t.submit_amm_create(
        "sFAKE", "XRP", "abc", "", "LAB", "100", "rISSUER",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_create_negative_issued_leg_rejected():
    """A negative ISSUED-currency leg is rejected too (guarded like XRP)."""
    t = DryRunTransport()
    res = await t.submit_amm_create(
        "sFAKE", "USD", "100", "rUSDISS", "LAB", "-100", "rLABISS",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_create_nonnumeric_issued_leg_rejected():
    """A non-numeric ISSUED-currency leg -> temBAD_AMOUNT, not ConversionSyntax."""
    t = DryRunTransport()
    res = await t.submit_amm_create(
        "sFAKE", "USD", "100", "rUSDISS", "LAB", "xyz", "rLABISS",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_create_valid_still_succeeds():
    """The validation guard does not break the happy path."""
    t = DryRunTransport()
    res = await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    assert res.success
    assert res.result_code == "tesSUCCESS"


# ── PT-001: AMM deposit / withdraw reject bad legs (no crash) ───────────────


@pytest.mark.asyncio
async def test_amm_deposit_first_liquidity_negative_leg_rejected_no_crash():
    """A negative XRP leg on the FIRST-liquidity deposit path -> temBAD_AMOUNT.

    First-liquidity uses ``(deposit_a * deposit_b).sqrt()`` — the same crash
    shape as create. The pool starts at 0 lp_supply here.
    """
    t = DryRunTransport()
    # Create a pool then drain it to lp_supply == 0 is awkward; instead pin the
    # simpler, more direct guard: a negative leg is rejected before any math.
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    # zero the pool's lp_supply to force the first-liquidity branch
    key = t._amm_pair_key("XRP", "", "LAB", "rISSUER")
    t._amm_pools[key]["lp_supply"] = "0"
    res = await t.submit_amm_deposit(
        "sFAKE", "XRP", "-10", "", "LAB", "10", "rISSUER",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_deposit_nonnumeric_leg_rejected_no_conversion_error():
    """A non-numeric deposit leg -> temBAD_AMOUNT, not ConversionSyntax."""
    t = DryRunTransport()
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    res = await t.submit_amm_deposit(
        "sFAKE", "XRP", "notanumber", "", "LAB", "10", "rISSUER",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_withdraw_negative_lp_rejected_no_crash():
    """A negative lp_token_value on withdraw -> temBAD_AMOUNT, no crash.

    ``Decimal(lp_token_value)`` on a non-numeric value crashed before the
    tecAMM_BALANCE check could run; a negative value flowed straight into
    ``burn_lp <= 0`` (tecAMM_BALANCE) but a MALFORMED one crashed.
    """
    t = DryRunTransport()
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    res = await t.submit_amm_withdraw(
        "sFAKE", "XRP", "", "LAB", "rISSUER", lp_token_value="-5",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_amm_withdraw_nonnumeric_lp_rejected_no_conversion_error():
    """A non-numeric lp_token_value -> temBAD_AMOUNT, not ConversionSyntax."""
    t = DryRunTransport()
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    res = await t.submit_amm_withdraw(
        "sFAKE", "XRP", "", "LAB", "rISSUER", lp_token_value="oops",
    )
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


# ── PT-002 (load-bearing): negative deposit on EXISTING pool ───────────────


@pytest.mark.asyncio
async def test_amm_negative_deposit_on_existing_pool_rejected_pool_unchanged():
    """A NEGATIVE deposit on an existing pool is REJECTED; pool is UNCHANGED.

    This is the load-bearing PT-002 regression. Before the fix, deposit -5 on a
    100/100 pool returned tesSUCCESS, SHRANK the pool to 95/95, and credited
    negative LP (95) — silent state corruption teaching a physically-impossible
    outcome. The fix must reject BEFORE the ratio math with temBAD_AMOUNT and
    leave the pool byte-for-byte unchanged.
    """
    t = DryRunTransport()
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    key = t._amm_pair_key("XRP", "", "LAB", "rISSUER")
    # Snapshot the FULL pool dict before the bad deposit.
    pool_before = dict(t._amm_pools[key])
    info_before = await t.get_amm_info("XRP", "", "LAB", "rISSUER")

    res = await t.submit_amm_deposit(
        "sFAKE", "XRP", "-5", "", "LAB", "-5", "rISSUER",
    )

    assert not res.success, "negative deposit must be rejected, not silently succeed"
    assert res.result_code == "temBAD_AMOUNT"

    # Pool state is UNCHANGED — this is the corruption regression.
    pool_after = dict(t._amm_pools[key])
    assert pool_after == pool_before, (
        f"pool corrupted by rejected negative deposit: "
        f"before={pool_before} after={pool_after}"
    )
    info_after = await t.get_amm_info("XRP", "", "LAB", "rISSUER")
    assert info_after.pool_a == info_before.pool_a == "100"
    assert info_after.pool_b == info_before.pool_b == "100"
    assert info_after.lp_supply == info_before.lp_supply


@pytest.mark.asyncio
async def test_amm_negative_deposit_does_not_credit_negative_lp():
    """The rejected negative deposit must NOT credit negative LP to the depositor."""
    t = DryRunTransport()
    await t.submit_amm_create(
        "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
    )
    info = await t.get_amm_info("XRP", "", "LAB", "rISSUER")
    lp_before = await t.get_lp_token_balance(
        "rDRYRUN1234567890ABCDEFGHIJK",
        info.lp_token_currency, info.lp_token_issuer,
    )
    await t.submit_amm_deposit(
        "sFAKE", "XRP", "-5", "", "LAB", "-5", "rISSUER",
    )
    lp_after = await t.get_lp_token_balance(
        "rDRYRUN1234567890ABCDEFGHIJK",
        info.lp_token_currency, info.lp_token_issuer,
    )
    assert lp_after == lp_before, "negative deposit must not change LP balance"


# ── PT-003: paychan verify_channel guards a bad expect_amount_xrp ───────────


@pytest.mark.asyncio
async def test_verify_channel_nonnumeric_expect_amount_does_not_raise():
    """A non-numeric expect_amount_xrp appends a failure rather than raising."""

    class _StubTransport:
        async def get_account_channels(self, source):  # noqa: ANN001
            return [
                ChannelInfo(
                    channel_id="C" * 64,
                    amount="100000000",
                    balance="0",
                    destination="rDEST",
                    settle_delay=60,
                    public_key="",
                    expiration=None,
                )
            ]

    result = await verify_channel(
        _StubTransport(), source="rSRC", expect_amount_xrp="not-a-number",
    )
    assert isinstance(result, ChannelVerifyResult)
    # It must NOT raise; the parse failure surfaces as a failure line.
    assert result.failures, "a bad expect amount should append a failure, not raise"
    assert not result.passed


@pytest.mark.asyncio
async def test_verify_channel_valid_expect_amount_still_matches():
    """A valid matching expect_amount_xrp still passes (guard didn't break it)."""

    class _StubTransport:
        async def get_account_channels(self, source):  # noqa: ANN001
            return [
                ChannelInfo(
                    channel_id="C" * 64,
                    amount="100000000",  # 100 XRP in drops
                    balance="0",
                    destination="rDEST",
                    settle_delay=60,
                    public_key="",
                    expiration=None,
                )
            ]

    result = await verify_channel(
        _StubTransport(), source="rSRC", expect_amount_xrp="100",
    )
    # 100 XRP == 100000000 drops -> no deposit-mismatch failure.
    assert not any("Deposit mismatch" in f for f in result.failures)


# ── PT-004: testnet non-timeout retry logs a duplicate-risk warning ─────────


@pytest.mark.asyncio
async def test_submit_payment_non_timeout_retry_logs_duplicate_warning(caplog):
    """A non-timeout post-broadcast retry logs a 'possible duplicate' warning.

    The retry loop can resubmit after a NON-TIMEOUT failure that landed AFTER
    broadcast -> a possible duplicate on-ledger tx. The fix adds a
    ``logger.warning`` on that branch so a facilitator can spot a double-submit
    in the logs. We drive the transport's real retry loop (patching only the
    network seam) so the branch actually executes.
    """
    from xrpl_lab.transport import xrpl_testnet as mod
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = XRPLTestnetTransport()
    submit_calls = {"n": 0}

    class _OkResp:
        result = {
            "meta": {"TransactionResult": "tesSUCCESS"},
            "hash": "DEADBEEF",
            "Fee": "12",
            "ledger_index": 55555555,
        }

    async def fake_submit_and_wait(tx, client, wallet=None):
        submit_calls["n"] += 1
        if submit_calls["n"] == 1:
            # Retryable NON-TIMEOUT failure after the tx is built/broadcast.
            raise ConnectionError("temporary network blip")
        return _OkResp()

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _fake_next_seq(account, client, *a, **k):
        # F-5eb1025c: unpin = no retry — pin must succeed for the
        # post-broadcast retry (and its duplicate-risk warning) to run.
        return 5_010_042

    with caplog.at_level(logging.WARNING, logger="xrpl_lab.transport.xrpl_testnet"), \
        patch.object(mod, "submit_and_wait", side_effect=fake_submit_and_wait), \
        patch.object(mod, "_rpc_client", lambda url: _Client()), \
        patch.object(mod, "get_next_valid_seq_number", side_effect=_fake_next_seq), \
        patch.object(mod.asyncio, "sleep", new=AsyncMock()):
        res = await t.submit_payment(
            "sEdSFf3wT37Ygoa34RrJgNfbD7qe4MH", "rDEST", "10"
        )

    assert res.success
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("possible duplicate" in w.lower() for w in warnings), (
        f"expected a duplicate-risk warning on the non-timeout retry; "
        f"got warnings={warnings}"
    )
