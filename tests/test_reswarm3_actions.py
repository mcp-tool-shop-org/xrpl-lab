"""Re-swarm 3 Stage-A regression tests — surgical fixes to the actions layer.

Covers four findings:

- AC-001 (paychan.redeem_claim): a non-source channel claim carrying a
  Signature MUST also carry Amount (rippled requires it; else temMALFORMED).
- AC-002 (escrow.create_escrow): guard CancelAfter > FinishAfter before submit.
- AC-003 (amm.verify_lp_received): Decimal < float comparison must not raise.
- AC-004 (escrow.verify_escrow): clearer failure when expected_destination is
  absent from the owned escrows (no mismatch against an unrelated escrow).
"""

from __future__ import annotations

import pytest

from xrpl_lab.actions.amm import verify_lp_received
from xrpl_lab.actions.escrow import create_escrow, verify_escrow
from xrpl_lab.actions.paychan import open_channel, redeem_claim, sign_claim
from xrpl_lab.transport.base import AmmInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# ── AC-001 — redeem_claim threads Amount alongside Balance ────────────


class _CapturingChannelTransport(DryRunTransport):
    """Dry-run transport that records the kwargs of submit_payment_channel_claim.

    The finding is about which fields the built PaymentChannelClaim carries, so
    we capture the exact call args the action forwards to the transport.
    """

    def __init__(self) -> None:
        super().__init__()
        self.claim_calls: list[dict] = []

    async def submit_payment_channel_claim(  # type: ignore[override]
        self, wallet_seed, channel_id, balance_xrp="", amount_xrp="",
        signature="", public_key="", close=False,
    ):
        self.claim_calls.append(
            {
                "balance_xrp": balance_xrp,
                "amount_xrp": amount_xrp,
                "signature": signature,
                "public_key": public_key,
                "close": close,
            }
        )
        return await super().submit_payment_channel_claim(
            wallet_seed, channel_id, balance_xrp=balance_xrp,
            amount_xrp=amount_xrp, signature=signature,
            public_key=public_key, close=close,
        )


@pytest.mark.asyncio
async def test_ac001_redeem_claim_includes_amount_equal_to_balance():
    t = _CapturingChannelTransport()
    create = await open_channel(t, "sSENDER", "10", "rRECEIVER", 86400)
    cid = create.channel_id

    sig = await sign_claim(t, "sSENDER", cid, "7")
    redeem = await redeem_claim(t, "sRECEIVER", cid, "7", signature=sig, public_key="")

    # After the fix the dry-run redeem still succeeds (it now carries the amount).
    assert redeem.success

    assert t.claim_calls, "redeem_claim did not call the transport"
    call = t.claim_calls[-1]
    # The claim must carry Amount alongside Balance, and they must be equal here.
    assert call["amount_xrp"] == "7"
    assert call["amount_xrp"] == call["balance_xrp"]


# ── AC-002 — create_escrow guards CancelAfter > FinishAfter ────────────


class _RecordingEscrowTransport(DryRunTransport):
    """Records whether submit_escrow_create was ever reached."""

    def __init__(self) -> None:
        super().__init__()
        self.submitted = False

    async def submit_escrow_create(  # type: ignore[override]
        self, wallet_seed, amount, destination, finish_after, cancel_after=None,
    ):
        self.submitted = True
        return await super().submit_escrow_create(
            wallet_seed, amount, destination, finish_after, cancel_after
        )


@pytest.mark.asyncio
async def test_ac002_create_escrow_rejects_bad_time_ordering():
    t = _RecordingEscrowTransport()
    # cancel_after <= finish_after is invalid on XRPL.
    result = await create_escrow(
        t, "sSENDER", "10", "rDEST", finish_after=1000, cancel_after=1000
    )
    assert not result.success
    assert result.result_code == "local_error"
    assert not t.submitted, "invalid ordering should be caught before submission"


@pytest.mark.asyncio
async def test_ac002_create_escrow_allows_valid_ordering():
    t = _RecordingEscrowTransport()
    result = await create_escrow(
        t, "sSENDER", "10", "rDEST", finish_after=1000, cancel_after=2000
    )
    assert result.success
    assert t.submitted


# ── AC-003 — verify_lp_received tolerates a nonzero float min_expected ──


class _LpBalanceTransport(DryRunTransport):
    """Returns a fixed LP balance and a minimal AMM pool for the pair."""

    def __init__(self, balance: str) -> None:
        super().__init__()
        self._lp = balance

    async def get_lp_token_balance(self, address, lp_token_currency, lp_token_issuer):  # type: ignore[override]
        return self._lp

    async def get_amm_info(self, a_cur, a_iss, b_cur, b_iss):  # type: ignore[override]
        return None


@pytest.mark.asyncio
async def test_ac003_verify_lp_received_nonzero_float_no_typeerror():
    t = _LpBalanceTransport("5")
    info = AmmInfo(asset_a="XRP", asset_b="LAB")
    # min_expected is a float; balance is parsed to Decimal internally.
    # Before the fix, Decimal < float raised TypeError here.
    result = await verify_lp_received(t, "rHOLDER", info, min_expected=2.5)
    # 5 >= 2.5 → no "below minimum" failure.
    assert result.passed
    assert result.lp_balance == "5"


@pytest.mark.asyncio
async def test_ac003_verify_lp_received_below_float_minimum_flags():
    t = _LpBalanceTransport("1")
    info = AmmInfo(asset_a="XRP", asset_b="LAB")
    result = await verify_lp_received(t, "rHOLDER", info, min_expected=2.5)
    # 1 < 2.5 → below-minimum failure (and no TypeError).
    assert not result.passed
    assert any("below expected minimum" in f for f in result.failures)


@pytest.mark.asyncio
async def test_ac003_verify_lp_received_float_precision_equal_boundary():
    # The real bite of comparing Decimal against a raw float: float 0.1 is
    # slightly LARGER than the exact decimal 0.1, so Decimal("0.1") < 0.1 is
    # True — a false "below minimum" failure at an exactly-met boundary. The
    # Decimal(str(min_expected)) coercion compares exact-to-exact and passes.
    t = _LpBalanceTransport("0.1")
    info = AmmInfo(asset_a="XRP", asset_b="LAB")
    result = await verify_lp_received(t, "rHOLDER", info, min_expected=0.1)
    assert result.passed, (
        "balance exactly equals the threshold; float imprecision must not "
        "produce a spurious below-minimum failure"
    )
    assert not any("below expected minimum" in f for f in result.failures)


# ── AC-004 — verify_escrow: clearer failure when destination absent ────


class _EscrowListTransport(DryRunTransport):
    """Returns a fixed list of escrows for verify_escrow to inspect."""

    def __init__(self, escrows) -> None:
        super().__init__()
        self._escrows = escrows

    async def get_escrows(self, address):  # type: ignore[override]
        return self._escrows


@pytest.mark.asyncio
async def test_ac004_verify_escrow_missing_destination_clear_message():
    from xrpl_lab.transport.base import EscrowInfo

    escrows = [
        EscrowInfo(sequence=1, amount="10", destination="rOTHER_A"),
        EscrowInfo(sequence=2, amount="20", destination="rOTHER_B"),
    ]
    t = _EscrowListTransport(escrows)
    result = await verify_escrow(t, "rOWNER", expected_destination="rWANTED")
    assert not result.passed
    joined = " ".join(result.failures).lower()
    # Should NOT be a bare "destination mismatch" against an unrelated escrow.
    assert "no escrow" in joined and "rwanted" in joined
    assert "mismatch" not in joined
