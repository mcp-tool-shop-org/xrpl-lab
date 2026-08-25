"""Wave-5 handlers Stage B — F-ebcf1f43 + F-04a4915c.

``PlayerCreditResult.credited_drops`` is "" for issued currency. The
``handle_credit_player_deposit`` success banner still hard-coded "drops",
so an issued-currency credit rendered as blank amount + the word drops.
``handle_credit_check_cash`` hard-coded "drops" onto ``delivered_amount``
(same class). Sweep the whole handlers.py file for this class.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers_mod
from xrpl_lab.actions.custodial import PlayerCreditResult
from xrpl_lab.actions.partial_payment import DeliveredAmountResult
from xrpl_lab.handlers import handle_credit_check_cash, handle_credit_player_deposit
from xrpl_lab.modules import ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport

HANDLERS_PATH = Path(handlers_mod.__file__).resolve()


def test_source_sweep_no_hardcoded_drops_on_polymorphic_credit_fields():
    """Call-site / source gate: no remaining ``credited_drops``+drops or
    ``delivered_amount``+drops hardcode in handlers.py success banners."""
    src = HANDLERS_PATH.read_text(encoding="utf-8")
    offenders: list[str] = []
    for i, line in enumerate(src.splitlines(), 1):
        if "credited_drops" in line and "drops" in line and "credited_value" not in line:
            # Allow docstrings / comments naming the field, not banner prints.
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if "console.print" in line or "f\"" in line or "f'" in line:
                offenders.append(f"L{i}: {line.strip()}")
        if "delivered_amount" in line and " drops" in line:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "console.print" in line or "f\"" in line or "f'" in line:
                offenders.append(f"L{i}: {line.strip()}")
    assert not offenders, (
        "handlers.py still hardcodes 'drops' onto a polymorphic credit field:\n"
        + "\n".join(offenders)
    )


@pytest.mark.asyncio
async def test_credit_player_deposit_banner_uses_credited_value_for_issued_currency(
    monkeypatch: pytest.MonkeyPatch,
):
    """Issued-currency success banner must show a non-blank amount and must
    not append the bare word 'drops'."""
    result = PlayerCreditResult(
        player="arya",
        tag=1001,
        credited_drops="",  # Stage-A contract: empty for non-XRP
        amount_field="50/LAB/rIssuerABCDEFGH",
        checks=["Credited 50 LAB (issuer rIssuerABCDEFGH) to 'arya'"],
        failures=[],
        currency="LAB",
        issuer="rIssuerABCDEFGH",
        credited_value="50",
    )
    monkeypatch.setattr(
        handlers_mod,
        "credit_player_deposit",
        AsyncMock(return_value=result),
    )
    buf = Console(record=True, width=120)
    state = LabState(network="dry-run", wallet_address="rPOOL")
    ctx = {
        "deposit_txid": "FAKETX",
        "tag_registry": {1001: "arya"},
    }
    step = ModuleStep(text="", action="credit_player_deposit", action_args={})
    await handle_credit_player_deposit(
        step, state, DryRunTransport(), "sPOOL", ctx, buf
    )
    text = buf.export_text()
    assert "CREDITED" in text
    assert "50" in text, f"banner amount blank:\n{text}"
    assert "LAB" in text, f"banner missing currency unit:\n{text}"
    # Blank amount + literal 'drops' is the seeded defect.
    assert re.search(r"\+\s*drops\b", text) is None, f"blank+drops banner:\n{text}"
    assert "+ drops" not in text
    # Must not label issued currency as drops.
    assert not re.search(r"\b50\b[^.\n]*\bdrops\b", text), (
        f"issued-currency banner still says drops:\n{text}"
    )


@pytest.mark.asyncio
async def test_credit_player_deposit_banner_still_says_drops_for_xrp(
    monkeypatch: pytest.MonkeyPatch,
):
    result = PlayerCreditResult(
        player="arya",
        tag=1001,
        credited_drops="25000000",
        amount_field="25000000",
        checks=["Credited 25000000 drops to 'arya'"],
        failures=[],
        currency="XRP",
        issuer="",
        credited_value="25000000",
    )
    monkeypatch.setattr(
        handlers_mod,
        "credit_player_deposit",
        AsyncMock(return_value=result),
    )
    buf = Console(record=True, width=120)
    state = LabState(network="dry-run", wallet_address="rPOOL")
    ctx = {"deposit_txid": "FAKETX", "tag_registry": {1001: "arya"}}
    step = ModuleStep(text="", action="credit_player_deposit", action_args={})
    await handle_credit_player_deposit(
        step, state, DryRunTransport(), "sPOOL", ctx, buf
    )
    text = buf.export_text()
    assert "25000000" in text
    assert "drops" in text


@pytest.mark.asyncio
async def test_credit_check_cash_does_not_hardcode_drops_suffix(
    monkeypatch: pytest.MonkeyPatch,
):
    """Mirror verify_delivered_amount: print delivered_amount as-is, no
    hardcoded ' drops' unit that would lie for issued-currency shapes."""
    result = DeliveredAmountResult(
        amount_field="50/LAB/rIssuer",
        delivered_amount="50/LAB/rIssuer",
        checks=["tesSUCCESS", "validated"],
        failures=[],
        exploit_demonstrated=False,
    )
    monkeypatch.setattr(
        handlers_mod,
        "verify_delivered_amount",
        AsyncMock(return_value=result),
    )
    buf = Console(record=True, width=120)
    state = LabState(network="dry-run", wallet_address="rW")
    ctx = {"check_cash_txid": "CHECKTX"}
    step = ModuleStep(text="", action="credit_check_cash", action_args={})
    await handle_credit_check_cash(
        step, state, DryRunTransport(), "s", ctx, buf
    )
    text = buf.export_text()
    assert "50/LAB/rIssuer" in text or "Credited" in text
    assert "drops" not in text.lower() or "delivered_amount" in text.lower()
    # The exact defect: "... {delivered_amount} drops from delivered_amount"
    assert not re.search(
        r"Credited the player .* drops from delivered_amount", text
    ), f"hardcoded drops suffix still present:\n{text}"


def test_enumerate_polymorphic_unit_print_sites():
    """Enumerate print/f-string sites mentioning credited_drops or
    delivered_amount; each must not append a hardcoded drops unit."""
    src_lines = HANDLERS_PATH.read_text(encoding="utf-8").splitlines()
    sites: list[tuple[int, str]] = []
    for i, line in enumerate(src_lines, 1):
        stripped = line.strip()
        mentions = "credited_drops" in line or "delivered_amount" in line
        is_printish = (
            "console.print" in line
            or stripped.startswith('f"')
            or stripped.startswith("f'")
        )
        if mentions and is_printish:
            sites.append((i, stripped))
    assert sites, "expected at least the credit banners to mention these fields"
    bad = [
        (ln, text)
        for ln, text in sites
        if (
            "credited_drops" in text
            and "drops" in text
            and "credited_value" not in text
        )
        or ("delivered_amount" in text and " drops" in text)
    ]
    assert not bad, "polymorphic unit lie sites remain:\n" + "\n".join(
        f"L{ln}: {t}" for ln, t in bad
    )
