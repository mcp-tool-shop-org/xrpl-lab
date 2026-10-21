"""Shared harness for the handlers.py (4120 -> end) coverage tests.

* ``Rig`` wires a ``DryRunTransport``, a ``LabState`` for a funded treasury
  and a context carrying the treasury seed, and captures console output.
* ``patch_action`` swaps an action function that ``xrpl_lab.handlers``
  imported for a fake returning a crafted result, recording its calls.
* ``fail_result`` / ``ok_result`` build ``SubmitResult`` values.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.modules import ModuleStep
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport

TREASURY = "rTreasuryAAAAAAAAAAAAAAAAAAAAAAAAAA"
SEED = "sTREASURYSEED"


def make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda *args, **kwargs: ""
    return console, buf


def ok_result(txid: str = "TXOK1", **kw: Any) -> SubmitResult:
    return SubmitResult(
        success=True, txid=txid, result_code="tesSUCCESS",
        explorer_url=kw.pop("explorer_url", "https://explorer.test/" + txid), **kw,
    )


def fail_result(code: str = "tecFAKE", txid: str = "TXBAD1", **kw: Any) -> SubmitResult:
    return SubmitResult(
        success=False, txid=txid, result_code=code,
        error=kw.pop("error", f"simulated {code}"), **kw,
    )


class Rig:
    """One handler-test fixture: transport + state + context + console."""

    def __init__(
        self, transport: DryRunTransport | None = None, address: str = TREASURY,
    ) -> None:
        self.address = address
        self.transport = transport or DryRunTransport()
        self.state = LabState(network="dry-run", wallet_address=address)
        self.context: dict = {
            "wallet_seed": _SecretValue(SEED),
            "module_id": "mod_test",
        }
        self.console, self.buf = make_console()

    async def fund(self, *addresses: str) -> None:
        for addr in addresses or (self.address,):
            await self.transport.fund_from_faucet(addr)

    async def run(self, handler, **args: Any) -> dict:
        step = ModuleStep(text="t", action="x", action_args=dict(args))
        self.context = await handler(
            step, self.state, self.transport, SEED, self.context, self.console,
        )
        return self.context

    @property
    def out(self) -> str:
        return self.buf.getvalue()

    def clear(self) -> None:
        self.buf.truncate(0)
        self.buf.seek(0)

    @property
    def records(self):
        return self.state.tx_index

    @property
    def failed_records(self):
        return [r for r in self.state.tx_index if not r.success]

    def verdicts(self, action: str | None = None) -> list[dict]:
        vs = self.context.get("verifications", [])
        return [v for v in vs if action is None or v["action"] == action]


def patch_action(
    monkeypatch: pytest.MonkeyPatch, name: str, result: Any,
) -> list[tuple[tuple, dict]]:
    """Replace ``handlers.<name>`` with an async fake; return its call log."""
    calls: list[tuple[tuple, dict]] = []

    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return result(*args, **kwargs) if callable(result) else result

    monkeypatch.setattr(handlers, name, _fake)
    return calls


class FaucetTransport(DryRunTransport):
    """DryRunTransport whose faucet answers with a canned FundResult."""

    def __init__(self, fund: FundResult | None = None, settle: bool = True) -> None:
        super().__init__()
        self._fund = fund
        self._settle = settle

    async def fund_from_faucet(self, address: str) -> FundResult:
        if self._fund is not None:
            return self._fund
        return await super().fund_from_faucet(address)

    async def get_balance(self, address: str) -> str:
        return await super().get_balance(address) if self._settle else "0"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(handlers, "save_state", lambda s: None)
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    import xrpl_lab.runtime as runtime

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)
