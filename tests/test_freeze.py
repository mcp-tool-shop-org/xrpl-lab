"""Tests for the token-freeze feature (FT-CURRIC-003) — Individual + Global Freeze."""

from pathlib import Path

import pytest

from xrpl_lab.actions.freeze import set_global_freeze, set_individual_freeze, verify_freeze
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.mark.asyncio
async def test_individual_freeze_roundtrip():
    t = DryRunTransport()
    issuer, holder = "rISSUER", "rHOLDER"

    r = await set_individual_freeze(t, "sISSUER", holder, "GLD", True, issuer)
    assert r.success and r.txid
    v = await verify_freeze(t, issuer, holder, "GLD", expect_individual=True)
    assert v.passed
    assert v.status.individual_frozen is True

    r2 = await set_individual_freeze(t, "sISSUER", holder, "GLD", False, issuer)
    assert r2.success
    v2 = await verify_freeze(t, issuer, holder, "GLD", expect_individual=False)
    assert v2.passed
    assert v2.status.individual_frozen is False


@pytest.mark.asyncio
async def test_global_freeze_roundtrip():
    t = DryRunTransport()
    issuer = "rISSUER"

    r = await set_global_freeze(t, "sISSUER", True, issuer)
    assert r.success
    v = await verify_freeze(t, issuer, "rHOLDER", "GLD", expect_global=True)
    assert v.passed
    assert v.status.global_frozen is True

    r2 = await set_global_freeze(t, "sISSUER", False, issuer)
    assert r2.success
    v2 = await verify_freeze(t, issuer, "rHOLDER", "GLD", expect_global=False)
    assert v2.passed
    assert v2.status.global_frozen is False


@pytest.mark.asyncio
async def test_individual_and_global_are_independent():
    t = DryRunTransport()
    issuer, holder = "rISSUER", "rHOLDER"
    await set_individual_freeze(t, "sISSUER", holder, "GLD", True, issuer)
    # Individual frozen, global still off.
    v = await verify_freeze(
        t, issuer, holder, "GLD", expect_individual=True, expect_global=False
    )
    assert v.passed


@pytest.mark.asyncio
async def test_verify_freeze_detects_mismatch():
    t = DryRunTransport()
    issuer, holder = "rISSUER", "rHOLDER"
    # Nothing frozen, but we assert it IS — must fail with a clear mismatch.
    v = await verify_freeze(t, issuer, holder, "GLD", expect_individual=True)
    assert not v.passed
    assert any("mismatch" in f.lower() for f in v.failures)


def test_token_freeze_module_lints_clean():
    issues = lint_module_file(
        Path(__file__).parent.parent / "modules" / "token_freeze_101.md"
    )
    assert not [i for i in issues if i.level == "error"]
