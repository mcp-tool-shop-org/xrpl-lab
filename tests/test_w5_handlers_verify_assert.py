"""Wave-5 handlers Stage B — F-305bb7e8.

``handle_verify_reserve_change`` and ``handle_verify_position_delta`` were
recording ``_record_verification(..., True, [])`` unconditionally while
modules list them as ``checks:``. An observed delta that contradicts an
opt-in expected fact must fail (passed=False, failures populated).

Module authors pass e.g. ``expected_owner_delta=1`` or
``expected_direction=up|down|unchanged`` for the assert to fire.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from xrpl_lab.actions.strategy import PositionSnapshot
from xrpl_lab.handlers import (
    handle_verify_position_delta,
    handle_verify_reserve_change,
)
from xrpl_lab.modules import ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import AccountSnapshot
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> Console:
    return Console(quiet=True)


def _acct(owner_count: int, balance_drops: str = "1000000000") -> AccountSnapshot:
    return AccountSnapshot(
        address="rTEST",
        balance_drops=balance_drops,
        owner_count=owner_count,
        sequence=1,
    )


def _pos(owner_count: int, offer_count: int = 0) -> PositionSnapshot:
    acct = _acct(owner_count)
    return PositionSnapshot(
        timestamp=0.0,
        account=acct,
        trust_lines=[],
        offers=[],
        xrp_balance=acct.balance_drops,
        owner_count=owner_count,
        offer_count=offer_count,
    )


@pytest.mark.asyncio
async def test_verify_reserve_change_fails_when_owner_delta_contradicts_expected():
    """RED gate: expected_owner_delta=1 but observed delta is 0 → passed=False."""
    t = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rTEST")
    ctx = {
        "snapshot_before": _acct(0),
        "snapshot_after": _acct(0),  # no owner-count change
    }
    step = ModuleStep(
        text="",
        action="verify_reserve_change",
        action_args={
            "before": "before",
            "after": "after",
            "expected_owner_delta": "1",
        },
    )
    ctx = await handle_verify_reserve_change(
        step, state, t, "s", ctx, _console()
    )
    recs = ctx.get("verifications", [])
    assert recs, "must record a verification"
    assert recs[-1]["action"] == "verify_reserve_change"
    assert recs[-1]["passed"] is False, (
        "unconditional True is the defect — contradicting expected_owner_delta "
        f"must fail; got {recs[-1]!r}"
    )
    assert recs[-1]["failures"], "failures must be populated on contradiction"


@pytest.mark.asyncio
async def test_verify_reserve_change_passes_when_owner_delta_matches():
    t = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rTEST")
    ctx = {
        "snapshot_before": _acct(0),
        "snapshot_after": _acct(1),
    }
    step = ModuleStep(
        text="",
        action="verify_reserve_change",
        action_args={
            "before": "before",
            "after": "after",
            "expected_owner_delta": "1",
        },
    )
    ctx = await handle_verify_reserve_change(
        step, state, t, "s", ctx, _console()
    )
    recs = ctx["verifications"]
    assert recs[-1]["passed"] is True
    assert recs[-1]["failures"] == []


@pytest.mark.asyncio
async def test_verify_reserve_change_fails_on_expected_direction_mismatch():
    t = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rTEST")
    ctx = {
        "snapshot_before": _acct(2),
        "snapshot_after": _acct(1),  # down
    }
    step = ModuleStep(
        text="",
        action="verify_reserve_change",
        action_args={
            "before": "before",
            "after": "after",
            "expected_direction": "up",
        },
    )
    ctx = await handle_verify_reserve_change(
        step, state, t, "s", ctx, _console()
    )
    recs = ctx["verifications"]
    assert recs[-1]["passed"] is False
    assert any("direction" in f.lower() or "owner" in f.lower() for f in recs[-1]["failures"])


@pytest.mark.asyncio
async def test_verify_position_delta_fails_when_owner_delta_contradicts_expected():
    t = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rTEST")
    ctx = {
        "position_before": _pos(1, offer_count=0),
        "position_after": _pos(1, offer_count=0),
    }
    step = ModuleStep(
        text="",
        action="verify_position_delta",
        action_args={
            "before": "before",
            "after": "after",
            "expected_owner_delta": "2",
        },
    )
    ctx = await handle_verify_position_delta(
        step, state, t, "s", ctx, _console()
    )
    recs = ctx.get("verifications", [])
    assert recs, "must record a verification"
    assert recs[-1]["action"] == "verify_position_delta"
    assert recs[-1]["passed"] is False, (
        "unconditional True is the defect — contradicting expected_owner_delta "
        f"must fail; got {recs[-1]!r}"
    )
    assert recs[-1]["failures"]


@pytest.mark.asyncio
async def test_verify_position_delta_passes_when_deltas_match():
    t = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rTEST")
    ctx = {
        "position_before": _pos(0, offer_count=0),
        "position_after": _pos(2, offer_count=2),
    }
    step = ModuleStep(
        text="",
        action="verify_position_delta",
        action_args={
            "before": "before",
            "after": "after",
            "expected_owner_delta": "2",
            "expected_offer_delta": "2",
        },
    )
    ctx = await handle_verify_position_delta(
        step, state, t, "s", ctx, _console()
    )
    recs = ctx["verifications"]
    assert recs[-1]["passed"] is True
    assert recs[-1]["failures"] == []
