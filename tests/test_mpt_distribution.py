"""Tests for MPT distribution (FT-CURRIC-004) — authorize, pay, verify balance."""

from pathlib import Path

import pytest

from xrpl_lab.actions.mpt import (
    authorize_mpt,
    create_mpt_issuance,
    send_mpt,
    verify_mpt_balance,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport, _address_from_seed


@pytest.mark.asyncio
async def test_create_returns_issuance_id():
    t = DryRunTransport()
    create = await create_mpt_issuance(t, "sISSUER", "1000000")
    assert create.success
    assert create.mpt_issuance_id  # threaded forward for authorize/pay/verify


@pytest.mark.asyncio
async def test_mpt_distribution_happy_path():
    t = DryRunTransport()
    create = await create_mpt_issuance(t, "sISSUER", "1000000")
    iid = create.mpt_issuance_id
    holder = _address_from_seed("sHOLDER")

    auth = await authorize_mpt(t, "sHOLDER", iid)
    assert auth.success

    pay = await send_mpt(t, "sISSUER", holder, iid, "500")
    assert pay.success

    result = await verify_mpt_balance(t, holder, iid, expected="500")
    assert result.passed
    assert result.balance == "500"


@pytest.mark.asyncio
async def test_mpt_payment_requires_authorize():
    # The opt-in gate: paying an MPT to an account that never authorized the
    # issuance must fail with tecNO_AUTH (the lesson's load-bearing concept).
    t = DryRunTransport()
    create = await create_mpt_issuance(t, "sISSUER", "1000000")
    iid = create.mpt_issuance_id
    holder = _address_from_seed("sHOLDER")

    pay = await send_mpt(t, "sISSUER", holder, iid, "500")
    assert not pay.success
    assert pay.result_code == "tecNO_AUTH"


@pytest.mark.asyncio
async def test_verify_mpt_balance_detects_mismatch():
    t = DryRunTransport()
    create = await create_mpt_issuance(t, "sISSUER", "1000000")
    iid = create.mpt_issuance_id
    holder = _address_from_seed("sHOLDER")
    await authorize_mpt(t, "sHOLDER", iid)
    await send_mpt(t, "sISSUER", holder, iid, "500")

    result = await verify_mpt_balance(t, holder, iid, expected="999")
    assert not result.passed
    assert any("mismatch" in f.lower() for f in result.failures)


def test_mpt_distribution_module_lints_clean():
    issues = lint_module_file(
        Path(__file__).parent.parent / "modules" / "mpt_distribution_101.md"
    )
    assert not [i for i in issues if i.level == "error"]
