"""Tests for MPT distribution (FT-CURRIC-004) — authorize, pay, verify balance."""

from pathlib import Path

import pytest

from tests._shipped_module import assert_no_failed_checks, run_shipped_module
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


# ── Shipped module runs clean in --dry-run ────────────────────────────────


class TestShippedMptDistributionModule:
    """``modules/mpt_distribution_101.md`` must not false-fail its balance check.

    The learner opted in (MPTokenAuthorize returned tesSUCCESS, the module
    printed "Authorized — the holder can now receive this MPT"), and the very
    next step failed ``tecNO_AUTH`` — "the destination has not authorized this
    MPT issuance" — against the holder who had just authorized it. The closing
    balance check then read 0 and went red.

    The cause: ``submit_mpt_authorize`` keyed ``_mpt_auths`` by
    ``_address_from_seed(holder_seed)``, which collapses every dry-run seed to
    one synthetic address, while ``submit_mpt_payment`` and
    ``get_mpt_balance`` key the same dicts by the real ``destination`` /
    ``holder``. The opt-in landed under one key and the payment looked up
    another.
    """

    @pytest.mark.asyncio
    async def test_no_failed_checks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out, _ = await run_shipped_module(
            "mpt_distribution_101.md", tmp_path, monkeypatch
        )

        # The distribution step must not fail against a holder that authorized.
        # Matched on the failure line, not the bare result code — the module's
        # prose teaches tecNO_AUTH by name, so the code itself is expected in
        # the output of a HEALTHY run.
        assert "MPT payment failed" not in out, (
            "the payment hit tecNO_AUTH: the opt-in was stored under the "
            "seed-collapsed address, not the destination the payment addresses"
        )
        assert "MPT balance mismatch" not in out

        assert_no_failed_checks(out, "mpt_distribution_101.md")

    @pytest.mark.asyncio
    async def test_holder_actually_received_the_mpt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The balance check passes because the 500 units arrived."""
        out, _ = await run_shipped_module(
            "mpt_distribution_101.md", tmp_path, monkeypatch
        )
        assert "Holder MPT balance: 500" in out, (
            "the holder did not end up with the 500 units the issuer sent"
        )
