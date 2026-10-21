"""2.7.3 (#20 item 14): a validated failure keeps its explorer link in state.

Book Keeper's 2.7.1 live checks: every expected-failure record in state.json
had ``explorer_url: ""``, including validated tecs, while the proof pack
(which recomputes the link) had them. The failed-record sites never passed the
result's link. ``record_tx`` still drops it for a tx that never validated.
"""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult

TEC, TEM = "A" * 64, "B" * 64
URL = "https://testnet.xrpl.org/transactions/"


def test_record_submit_keeps_a_validated_failures_link(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    state = LabState(network="testnet")
    ctx = {"module_id": "m"}
    handlers._record_submit(state, ctx, SubmitResult(
        success=False, txid=TEC, result_code="tecNO_PERMISSION", validated=True,
        explorer_url=URL + TEC))
    handlers._record_submit(state, ctx, SubmitResult(
        success=False, txid=TEM, result_code="temCANNOT_PREAUTH_SELF",
        explorer_url=URL + TEM))
    assert [r.explorer_url for r in state.tx_index] == [URL + TEC, ""]


def test_every_failed_record_from_a_result_passes_its_link() -> None:
    import ast
    import inspect
    import textwrap

    for name, fn in inspect.getmembers(handlers, inspect.isfunction) + \
            inspect.getmembers(handlers, inspect.iscoroutinefunction):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call)
                    and getattr(call.func, "attr", "") == "record_tx"):
                continue
            kw = {k.arg for k in call.keywords}
            success = next((k.value for k in call.keywords if k.arg == "success"), None)
            if isinstance(success, ast.Constant) and success.value is False and "validated" in kw:
                assert "explorer_url" in kw, name


@pytest.mark.asyncio
async def test_a_live_style_expected_tec_keeps_its_link_in_state(monkeypatch) -> None:
    """The deposit_gate case: an expected tecNO_PERMISSION, judged and recorded."""
    import io

    from rich.console import Console

    from xrpl_lab.modules import ModuleStep
    from xrpl_lab.transport.dry_run import DryRunTransport

    monkeypatch.setattr(handlers, "save_state", lambda state: None)

    async def _blocked(*args, **kwargs):
        return SubmitResult(success=False, txid=TEC, result_code="tecNO_PERMISSION",
                            validated=True, explorer_url=URL + TEC)

    monkeypatch.setattr(handlers, "send_gated_payment", _blocked)
    state = LabState(wallet_address="rTREASURY", network="testnet")
    ctx = {"module_id": "deposit_gate_101", "sender_seed": "sSENDER",
           "sender_address": "rSENDER"}
    step = ModuleStep(text="x", action="send_sender_payment_expect_blocked",
                      action_args={"amount": "10"})
    await handlers.handle_send_sender_payment_expect_blocked(
        step, state, DryRunTransport(), "sSEED", ctx, Console(file=io.StringIO()))
    rec = state.tx_index[-1]
    assert rec.expected is True and rec.explorer_url == URL + TEC
