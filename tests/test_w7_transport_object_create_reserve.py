"""Wave-7/8 F-17e7f723 — object-create reserve vs post-create owner floor.

``_reserve_guard`` historically used the CURRENT ``owner_count`` (extra_drops=0,
or only a locked XRP amount) and callers then ``_inc_owner`` on success. Mid-band
balances that cover fee (+ small lock) against the *current* floor but not
``base + (owner_count+1)*increment`` returned ``tesSUCCESS`` and left the
account under the post-create floor. Real testnet rejects
``tecINSUFFICIENT_RESERVE``.

Why ``tests/test_w2_transport_dryrun_reserve.py`` cannot see this: it clamps to
EXACT base reserve where the 12-drop fee alone fails. The open band
``[base+fee, base+fee+owner_increment)`` was never constructed.

Red-first signature (unfixed tree): each create below returns
``success=True, result_code='tesSUCCESS'`` at mid-band and
``balance < base + 1*owner_increment`` afterward.
"""

from __future__ import annotations

import pytest

from xrpl_lab.transport.dry_run import (
    _BASE_RESERVE_DROPS,
    _DRY_FEE_DROPS,
    _DRY_RUN_WALLET_ADDRESS,
    _OWNER_RESERVE_DROPS,
    DryRunTransport,
)

_RESERVE_FAMILY = {
    "tecUNFUNDED_PAYMENT",
    "tecUNFUNDED",
    "tecUNFUNDED_OFFER",
    "tecINSUFFICIENT_RESERVE",
    "tecINSUFFICIENT_FUNDS",
}

# Mid-band: fee alone clears the current (owner_count=0) floor; post-create
# floor is base+owner_increment. 100_000 < owner_increment so creates must fail.
_MID_BAND = _BASE_RESERVE_DROPS + _DRY_FEE_DROPS + 100_000
_POST_CREATE_FLOOR = _BASE_RESERVE_DROPS + _OWNER_RESERVE_DROPS


async def _at_mid_band(t: DryRunTransport) -> None:
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    t._balances[_DRY_RUN_WALLET_ADDRESS] = _MID_BAND


def _assert_declined(r, label: str) -> None:
    assert r.success is False, (
        f"{label}: reported tesSUCCESS at mid-band balance {_MID_BAND} "
        f"(post-create floor {_POST_CREATE_FLOOR}) — false positive; "
        "testnet would reject tecINSUFFICIENT_RESERVE (F-17e7f723)"
    )
    assert r.result_code in _RESERVE_FAMILY, (
        f"{label}: expected reserve/funding-family code, got "
        f"{r.result_code!r} (error={r.error!r})"
    )


_CREATE_CALLS = {
    "submit_trust_set": lambda t: t.submit_trust_set(
        "sSEED", "rISSUER", "USD", "1000"
    ),
    "submit_offer_create": lambda t: t.submit_offer_create(
        "sSEED", "USD", "10", "rISSUER", "XRP", "5", "",
    ),
    "submit_check_create": lambda t: t.submit_check_create(
        "sSEED", "rDEST", "10"
    ),
    # Small lock so the *amount* alone still fits mid-band headroom; only the
    # missing owner-increment makes this a create-reserve failure.
    "submit_escrow_create": lambda t: t.submit_escrow_create(
        "sSEED", "0.05", "rDEST", finish_after=0,
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    list(_CREATE_CALLS.values()),
    ids=list(_CREATE_CALLS.keys()),
)
async def test_object_create_declines_in_mid_band(call) -> None:
    """Creates must refuse when balance covers fee but not post-create floor.

    Captured RED on unfixed 7ecf174 (mid-band → tesSUCCESS, balance under
    1_200_000 after _inc_owner).
    """
    t = DryRunTransport()
    await _at_mid_band(t)
    before = t._balances[_DRY_RUN_WALLET_ADDRESS]
    r = await call(t)
    _assert_declined(r, getattr(call, "__name__", "create"))
    assert t._balances[_DRY_RUN_WALLET_ADDRESS] == before, (
        "declined create must not debit fee or locked XRP"
    )
    assert t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 0, (
        "declined create must not _inc_owner"
    )


@pytest.mark.asyncio
async def test_object_create_succeeds_when_post_create_floor_covered() -> None:
    """Enough headroom for fee + one owner increment → tesSUCCESS."""
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    t._balances[_DRY_RUN_WALLET_ADDRESS] = (
        _BASE_RESERVE_DROPS + _OWNER_RESERVE_DROPS + _DRY_FEE_DROPS
    )
    r = await t.submit_trust_set("sSEED", "rISSUER", "USD", "1000")
    assert r.success, r.error
    bal = t._balances[_DRY_RUN_WALLET_ADDRESS]
    assert bal >= _POST_CREATE_FLOOR
    assert t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 1


@pytest.mark.asyncio
async def test_trust_set_update_does_not_over_reserve_at_mid_band() -> None:
    """TrustSet on an existing line must NOT charge the owner increment.

    After create (oc=1), headroom is only fee+100_000 above the *current*
    floor — enough for an update, but not enough if update wrongly folds
    ``_OWNER_RESERVE_DROPS`` into the guard.
    """
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    created = await t.submit_trust_set("sSEED", "rISSUER", "USD", "1000")
    assert created.success, created.error
    # current floor with oc=1 is base+owner_inc; mid-band relative to THAT.
    t._balances[_DRY_RUN_WALLET_ADDRESS] = (
        _POST_CREATE_FLOOR + _DRY_FEE_DROPS + 100_000
    )
    oc_before = t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0)
    assert oc_before == 1
    updated = await t.submit_trust_set("sSEED", "rISSUER", "USD", "2000")
    assert updated.success, (
        f"TrustSet update must not over-reserve at mid-band; got "
        f"{updated.result_code!r} {updated.error!r}"
    )
    assert t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == oc_before


@pytest.mark.asyncio
async def test_trust_set_remove_does_not_require_owner_increment() -> None:
    """Removing a zero-balance line frees reserve; fee-only mid-band is enough."""
    t = DryRunTransport()
    await t.fund_from_faucet(_DRY_RUN_WALLET_ADDRESS)
    created = await t.submit_trust_set("sSEED", "rISSUER", "USD", "1000")
    assert created.success, created.error
    t._balances[_DRY_RUN_WALLET_ADDRESS] = (
        _POST_CREATE_FLOOR + _DRY_FEE_DROPS + 100_000
    )
    removed = await t.submit_trust_set("sSEED", "rISSUER", "USD", "0")
    assert removed.success, removed.error
    assert t._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0) == 0
