"""2.6.1: the first lessons' payments work on the real ledger.

receipt_literacy (module 1), failure_literacy and receipt_audit send their
practice payments with ``destination=self``. Nothing resolved "self", so the
handler sent the literal string, which xrpl-py's binary codec rejects
("Invalid value to construct an AccountID"): the lessons couldn't run on
testnet, and the dry run hid it. Resolving "self" to the learner's own address
wouldn't help either: XRPL rejects an XRP payment to yourself (temREDUNDANT).

So practice payments go to a fresh address created once per run, which the
payment itself creates (it carries at least the 1 XRP base reserve). The
deliberate "underfunded" failure sends more XRP than the wallet holds, so
the ledger answers tecUNFUNDED_PAYMENT, the code the lesson teaches, instead
of a self-payment's temREDUNDANT.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.modules import ModuleStep, load_all_modules
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport

LEARNER = "rLEARNER1234567890abcdefghijkLM"


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, no_color=True, markup=True, width=200), buf


def _is_classic_address(value: str) -> bool:
    from xrpl.core.addresscodec import is_valid_classic_address

    return is_valid_classic_address(value)


@pytest.fixture()
def _sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def _send(transport, seed, dest, amount, memo=""):
        sent.append((dest, amount))
        return SubmitResult(success=True, txid="A" * 64, result_code="tesSUCCESS")

    monkeypatch.setattr(handlers, "send_payment", _send)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    return sent


@pytest.mark.asyncio
async def test_a_self_payment_goes_to_a_fresh_practice_address(_sent) -> None:
    state = LabState(wallet_address=LEARNER)
    ctx: dict = {}
    step = ModuleStep(text="pay", action="submit_payment",
                      action_args={"destination": "self", "amount": "10"})
    console, buf = _console()
    for _ in range(2):
        ctx = await handlers.handle_submit_payment(step, state, DryRunTransport(), "", ctx, console)
    (first, _), (second, _) = _sent
    assert _is_classic_address(first)
    assert first != LEARNER
    assert first == second  # one practice address per run
    out = buf.getvalue()
    assert "temREDUNDANT" in out
    assert out.count("practice payments go to a fresh address") == 1  # said once


@pytest.mark.asyncio
async def test_a_payment_with_no_destination_also_uses_the_practice_address(_sent) -> None:
    state = LabState(wallet_address=LEARNER)
    console, _ = _console()
    step = ModuleStep(text="pay", action="submit_payment", action_args={"amount": "10"})
    await handlers.handle_submit_payment(step, state, DryRunTransport(), "", {}, console)
    assert _sent[0][0] != LEARNER and _is_classic_address(_sent[0][0])


@pytest.mark.asyncio
async def test_the_underfunded_failure_really_is_underfunded(monkeypatch) -> None:
    sent: list[tuple[str, str]] = []

    async def _send(transport, seed, dest, amount, memo=""):
        sent.append((dest, amount))
        return SubmitResult(success=False, result_code="tecUNFUNDED_PAYMENT")

    class _Ledger(DryRunTransport):
        async def get_balance(self, address):
            return "100"

    monkeypatch.setattr(handlers, "send_payment", _send)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    console, _ = _console()
    step = ModuleStep(text="fail", action="submit_payment_fail",
                      action_args={"reason": "underfunded"})
    ctx = await handlers.handle_submit_payment_fail(
        step, LabState(wallet_address=LEARNER), _Ledger(), "", {}, console,
    )
    dest, amount = sent[0]
    assert dest != LEARNER and _is_classic_address(dest)
    assert float(amount) > 100
    assert ctx.get("expected_failures") == 1


@pytest.mark.asyncio
async def test_an_underfunded_lesson_that_gets_another_code_fails(monkeypatch) -> None:
    async def _send(transport, seed, dest, amount, memo=""):
        return SubmitResult(success=False, result_code="temREDUNDANT", validated=False)

    monkeypatch.setattr(handlers, "send_payment", _send)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    console, _ = _console()
    step = ModuleStep(text="fail", action="submit_payment_fail",
                      action_args={"reason": "underfunded"})
    ctx = await handlers.handle_submit_payment_fail(
        step, LabState(wallet_address=LEARNER), DryRunTransport(), "", {}, console,
    )
    assert not ctx.get("expected_failures")
    assert any(not v["passed"] for v in ctx.get("verifications", []))


@pytest.mark.parametrize("module_id", ["receipt_literacy", "failure_literacy", "receipt_audit"])
def test_the_lessons_no_longer_promise_a_self_payment(module_id: str) -> None:
    body = load_all_modules()[module_id].raw_body.lower()
    assert "self-payment" not in body
    assert "amount to yourself" not in body
    assert "your own address (a" not in body
