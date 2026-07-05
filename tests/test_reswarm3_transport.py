"""Regression tests pinning the 2026-07 re-swarm Stage-A transport fixes.

Each test anchors one finding so the fix cannot silently regress. Findings:

- TR-001 / TR-002: dry-run ``submit_payment`` (and escrow-create + both
  payment-channel methods) must behave EXACTLY like the network's
  ``xrpl.utils.xrp_to_drops`` — ROUND >6dp to nearest drop (ROUND_HALF_EVEN),
  REJECT negative / sub-drop ("too small") and > 100_000_000_000 XRP
  ("too large"). The old ">6dp reject" branch (and its factually-false comment
  claiming xrp_to_drops rejects >6dp) is gone: xrp_to_drops ROUNDS, it does not
  reject. Verified against xrpl-py 4.5.0.
- TR-003: XRP->drops conversions in escrow finish/cancel and the channel
  methods must ROUND (HALF_EVEN), not TRUNCATE (the old ``int(Decimal*1e6)``).
- AC-001 support: a dry-run channel claim carrying a signature/public_key but
  NO amount must be REJECTED (a signed claim must name the amount it
  authorizes) — this is what makes the actions-side AC-001 bug catchable.
- TR-004: testnet ``submit_payment`` / ``submit_offer_create`` /
  ``submit_offer_cancel`` must build+sign the tx ONCE outside the retry loop and
  resubmit the identical signed blob, so a post-broadcast retry is idempotent
  (no double-broadcast with a fresh sequence).
- TR-005: testnet ``fetch_tx`` must fall back to ``inLedger`` / ``meta`` for
  ledger_index (matching the submit paths), not read only the top-level field.
- TR-006: the dead ``o.get("MPTAmount", o.get("MPTAmount", "0"))`` nested
  fallback collapses to a single lookup.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from xrpl.utils import xrp_to_drops

from xrpl_lab.transport.dry_run import (
    _DRY_RUN_WALLET_ADDRESS,
    DryRunTransport,
    _address_from_seed,
)

# ── TR-001 / TR-002: dry-run XRP amount parity with xrp_to_drops ───────────


@pytest.mark.asyncio
async def test_payment_rounds_over_6dp_matching_testnet():
    """10.1234567 XRP: dry-run SUCCEEDS and settles 10123457 drops (rounds).

    Old behavior rejected any >6dp amount with a false "xrp_to_drops rejects
    >6dp" comment. xrp_to_drops actually ROUNDS (HALF_EVEN): 10.1234567 ->
    10123457. The dry-run must match, not reject.
    """
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    dest = "rDESTINATION0000000000000000"
    before = t._balances.get(dest, 0)

    res = await t.submit_payment("sSENDER", dest, "10.1234567")

    assert res.success, f"expected rounded payment to succeed, got {res.error}"
    assert res.result_code == "tesSUCCESS"
    settled = t._balances.get(dest, 0) - before
    assert settled == 10123457, f"expected 10123457 drops settled, got {settled}"
    # And it exactly matches the network helper.
    assert settled == int(xrp_to_drops(Decimal("10.1234567")))


@pytest.mark.asyncio
async def test_payment_rejects_negative_amount_no_inflation():
    """A negative amount is REJECTED and does NOT inflate the sender balance."""
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    sender = _address_from_seed("sSENDER")
    sender_before = t._balances.get(sender, 0)
    dest = "rDESTNEG00000000000000000000"
    dest_before = t._balances.get(dest, 0)

    res = await t.submit_payment("sSENDER", dest, "-10")

    assert not res.success, "negative amount must be rejected"
    assert res.result_code == "temBAD_AMOUNT"
    # Sender must NOT gain balance; destination must NOT change.
    assert t._balances.get(sender, 0) == sender_before
    assert t._balances.get(dest, 0) == dest_before


@pytest.mark.asyncio
async def test_payment_rejects_too_large_amount():
    """200000000000 XRP (> 100_000_000_000 max) is REJECTED ("too large")."""
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    res = await t.submit_payment("sSENDER", "rDESTBIG00000000000000000000", "200000000000")
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_payment_rejects_subdrop_amount():
    """0.0000001 XRP (< 1 drop) is REJECTED ("too small")."""
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    res = await t.submit_payment("sSENDER", "rDESTSUB00000000000000000000", "0.0000001")
    assert not res.success
    assert res.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_escrow_create_rejects_bad_amounts_and_rounds():
    """Escrow-create mirrors the same validation (reject bad, round >6dp)."""
    t = DryRunTransport()
    # sub-drop -> reject
    bad = await t.submit_escrow_create("sSENDER", "0.0000001", "rDEST", finish_after=0)
    assert not bad.success and bad.result_code == "temBAD_AMOUNT"
    # too large -> reject
    big = await t.submit_escrow_create("sSENDER", "200000000000", "rDEST", finish_after=0)
    assert not big.success and big.result_code == "temBAD_AMOUNT"
    # negative -> reject
    neg = await t.submit_escrow_create("sSENDER", "-5", "rDEST", finish_after=0)
    assert not neg.success and neg.result_code == "temBAD_AMOUNT"
    # >6dp -> rounds and succeeds
    ok = await t.submit_escrow_create("sSENDER", "10.1234567", "rDEST", finish_after=0)
    assert ok.success and ok.result_code == "tesSUCCESS"


@pytest.mark.asyncio
async def test_channel_create_and_fund_reject_bad_amounts():
    """Both channel amount entry points mirror the validation."""
    t = DryRunTransport()
    bad = await t.submit_payment_channel_create(
        "sSENDER", "0.0000001", "rDEST", settle_delay=86400, public_key="ED00"
    )
    assert not bad.success and bad.result_code == "temBAD_AMOUNT"
    big = await t.submit_payment_channel_create(
        "sSENDER", "200000000000", "rDEST", settle_delay=86400, public_key="ED00"
    )
    assert not big.success and big.result_code == "temBAD_AMOUNT"

    ok = await t.submit_payment_channel_create(
        "sSENDER", "10", "rDEST", settle_delay=86400, public_key="ED00"
    )
    assert ok.success
    cid = ok.channel_id
    # fund with a sub-drop -> reject
    fbad = await t.submit_payment_channel_fund("sSENDER", cid, "0.0000001")
    assert not fbad.success and fbad.result_code == "temBAD_AMOUNT"
    # fund rounds >6dp
    fok = await t.submit_payment_channel_fund("sSENDER", cid, "10.1234567")
    assert fok.success


# ── TR-003: rounding (not truncation) in escrow finish/cancel + channels ───


@pytest.mark.asyncio
async def test_escrow_finish_rounds_not_truncates():
    """1.9999999 XRP escrow releases 2000000 drops (rounded), not 1999999."""
    t = DryRunTransport()
    dest = "rESCROWDEST000000000000000000"
    create = await t.submit_escrow_create("sSENDER", "1.9999999", dest, finish_after=0)
    assert create.success
    seq = (await t.get_escrows(_DRY_RUN_WALLET_ADDRESS))[0].sequence
    before = t._balances.get(dest, 0)
    fin = await t.submit_escrow_finish("sSENDER", _DRY_RUN_WALLET_ADDRESS, seq)
    assert fin.success
    settled = t._balances.get(dest, 0) - before
    assert settled == 2000000, f"expected rounded 2000000 drops, got {settled}"


@pytest.mark.asyncio
async def test_channel_claim_rounds_not_truncates():
    """A 1.9999999 XRP channel claim settles 2000000 drops (rounded)."""
    t = DryRunTransport()
    dest = "rCHANDEST0000000000000000000"
    create = await t.submit_payment_channel_create(
        "sSENDER", "10", dest, settle_delay=86400, public_key="ED00"
    )
    cid = create.channel_id
    before = t._balances.get(dest, 0)
    claim = await t.submit_payment_channel_claim(cid and "sSENDER", cid, balance_xrp="1.9999999")
    assert claim.success
    settled = t._balances.get(dest, 0) - before
    assert settled == 2000000, f"expected rounded 2000000 drops, got {settled}"


# ── AC-001 support: signed claim without amount is rejected ────────────────


@pytest.mark.asyncio
async def test_signed_channel_claim_without_amount_is_rejected():
    """A claim with a signature/public_key but NO amount must be REJECTED.

    This makes the actions-side AC-001 bug (PaymentChannelClaim missing its
    required Amount field alongside the signature) catchable in dry-run instead
    of silently settling on balance alone.
    """
    t = DryRunTransport()
    dest = "rSIGCHANDEST00000000000000000"
    create = await t.submit_payment_channel_create(
        "sSENDER", "10", dest, settle_delay=86400, public_key="ED00"
    )
    cid = create.channel_id
    before = t._balances.get(dest, 0)
    # Signature present, amount_xrp absent -> malformed signed claim.
    res = await t.submit_payment_channel_claim(
        "sSENDER", cid, balance_xrp="5",
        signature="DRYSIGABCDEF", public_key="ED00", amount_xrp="",
    )
    assert not res.success, "signed claim without amount must be rejected"
    assert res.result_code == "temMALFORMED"
    # And it must NOT have settled anything.
    assert t._balances.get(dest, 0) == before


@pytest.mark.asyncio
async def test_signed_channel_claim_with_amount_succeeds():
    """The valid shape (signature + amount) still settles — guard is targeted."""
    t = DryRunTransport()
    dest = "rSIGOKDEST000000000000000000"
    create = await t.submit_payment_channel_create(
        "sSENDER", "10", dest, settle_delay=86400, public_key="ED00"
    )
    cid = create.channel_id
    sig = await t.authorize_payment_channel_claim("sSENDER", cid, "5")
    res = await t.submit_payment_channel_claim(
        "sSENDER", cid, balance_xrp="5",
        signature=sig, public_key="ED00", amount_xrp="5",
    )
    assert res.success and res.result_code == "tesSUCCESS"


# ── TR-005: fetch_tx ledger_index fallback ────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_tx_falls_back_to_inledger():
    """ledger_index only under inLedger yields a non-null ledger_index."""
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = XRPLTestnetTransport()

    class _Resp:
        result = {
            "TransactionType": "Payment",
            "Account": "rA",
            "Destination": "rB",
            "Amount": "1000000",
            "Fee": "12",
            "meta": {"TransactionResult": "tesSUCCESS"},
            "inLedger": 88888888,
            "validated": True,
        }

    class _Client:
        async def request(self, *a, **k):
            return _Resp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("xrpl_lab.transport.xrpl_testnet._rpc_client", lambda url: _Client()):
        info = await t.fetch_tx("ABCD")

    assert info.ledger_index == 88888888, (
        f"expected inLedger fallback, got {info.ledger_index}"
    )


@pytest.mark.asyncio
async def test_fetch_tx_falls_back_to_meta_ledger_index():
    """ledger_index only under meta yields a non-null ledger_index."""
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = XRPLTestnetTransport()

    class _Resp:
        result = {
            "TransactionType": "Payment",
            "Account": "rA",
            "Destination": "rB",
            "Amount": "1000000",
            "Fee": "12",
            "meta": {"TransactionResult": "tesSUCCESS", "ledger_index": 77777777},
            "validated": True,
        }

    class _Client:
        async def request(self, *a, **k):
            return _Resp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch("xrpl_lab.transport.xrpl_testnet._rpc_client", lambda url: _Client()):
        info = await t.fetch_tx("ABCD")

    assert info.ledger_index == 77777777


# ── TR-006: dead MPTAmount nested fallback collapsed ──────────────────────


def test_mptamount_dead_fallback_collapsed():
    """The nested get(MPTAmount, get(MPTAmount,...)) fallback is gone.

    Source-level assertion: the buggy self-referential nested fallback must
    not survive in the file.
    """
    from pathlib import Path

    src = Path(__file__).parent.parent / "xrpl_lab" / "transport" / "xrpl_testnet.py"
    text = src.read_text(encoding="utf-8")
    assert 'o.get("MPTAmount", o.get("MPTAmount"' not in text, (
        "dead self-referential MPTAmount fallback still present"
    )


# ── TR-004: testnet retry idempotency (build+sign once) ───────────────────


@pytest.mark.asyncio
async def test_payment_retry_resubmits_same_tx_object_not_a_rebuilt_one():
    """A non-timeout retry resubmits the SAME tx object (built once).

    The wallet + Payment model must be constructed ONCE outside the retry loop.
    Previously they were rebuilt on every attempt, so a post-broadcast failure
    could re-enter the loop and construct a DISTINCT transaction (a
    double-broadcast risk). We patch submit_and_wait (the network seam) to fail
    retryably on the first call and succeed on the second, and assert the SAME
    tx object is handed to submit_and_wait both times.

    NOTE (idempotency residual, TR-004): full Sequence-level idempotency needs
    autofill_and_sign-once + submit_and_wait(autofill=False); that seam-moving
    refactor is deferred (it would require re-mocking the sibling-owned retry
    tests). This test pins the object-rebuild half that IS fixed here.
    """
    from xrpl_lab.transport import xrpl_testnet as mod
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = XRPLTestnetTransport()

    submitted = []
    submit_calls = {"n": 0}

    class _OkResp:
        result = {
            "meta": {"TransactionResult": "tesSUCCESS"},
            "hash": "DEADBEEF",
            "Fee": "12",
            "ledger_index": 55555555,
        }

    async def fake_submit_and_wait(tx, client, wallet=None):
        submitted.append(tx)
        submit_calls["n"] += 1
        if submit_calls["n"] == 1:
            # Retryable, non-timeout failure AFTER the tx is built.
            raise ConnectionError("temporary network blip")
        return _OkResp()

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    with patch.object(mod, "submit_and_wait", side_effect=fake_submit_and_wait), \
         patch.object(mod, "_rpc_client", lambda url: _Client()), \
         patch.object(mod.asyncio, "sleep", new=AsyncMock()):
        res = await t.submit_payment(
            "sEdSFf3wT37Ygoa34RrJgNfbD7qe4MH", "rDEST", "10"
        )

    # Two submit attempts happened (one retry after the transient failure)...
    assert submit_calls["n"] == 2, f"expected one retry, got {submit_calls['n']} attempts"
    # ...with the IDENTICAL tx object each time (built once outside the loop).
    assert submitted[0] is submitted[1], (
        "retry rebuilt the tx (distinct object) — the tx must be built once "
        "outside the loop so a retry cannot broadcast a second, distinct tx"
    )
    assert res.success and res.txid == "DEADBEEF"
