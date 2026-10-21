"""Shared builders for the handlers.py (part A) coverage tests."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.modules import ModuleStep
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport

TXID = "A" * 64
FAILED_TXID = "B" * 64
EXPLORER = "https://testnet.xrpl.org/transactions/" + TXID


def ok(txid: str = TXID, explorer: str = EXPLORER, **kw: Any) -> SubmitResult:
    return SubmitResult(
        success=True, txid=txid, result_code="tesSUCCESS", fee="12",
        explorer_url=explorer, **kw,
    )


def bad(
    code: str = "tecNO_PERMISSION", txid: str = FAILED_TXID,
    error: str = "the ledger said no", **kw: Any,
) -> SubmitResult:
    return SubmitResult(
        success=False, txid=txid, result_code=code, error=error, **kw,
    )


def secret(value: str = "sSEED") -> _SecretValue:
    return _SecretValue(value)


class Env:
    """One handler call's world: state, context, console and a monkeypatcher."""

    def __init__(self, tmp_path: Path, monkeypatch: Any) -> None:
        self.tmp_path = tmp_path
        self.mp = monkeypatch
        self.buf = io.StringIO()
        self.console = Console(file=self.buf, no_color=True, width=200)
        self.state = LabState(wallet_address="rLEARNER", network="testnet")
        self.transport = DryRunTransport()
        self.ctx: dict = {"wallet_seed": secret(), "module_id": "mod_x"}
        self.saved = 0

        def _save(_s: Any) -> None:
            self.saved += 1

        monkeypatch.setattr(handlers, "save_state", _save)

    # -- output ---------------------------------------------------------
    @property
    def out(self) -> str:
        return self.buf.getvalue()

    # -- stubbing -------------------------------------------------------
    def stub(self, name: str, ret: Any) -> list:
        """Replace ``handlers.<name>`` with an async fake; returns its call log."""
        calls: list = []

        async def _fake(*a: Any, **k: Any) -> Any:
            calls.append((a, k))
            if isinstance(ret, BaseException):
                raise ret
            return ret() if callable(ret) else ret

        self.mp.setattr(handlers, name, _fake)
        return calls

    def stub_sync(self, name: str, ret: Any) -> list:
        calls: list = []

        def _fake(*a: Any, **k: Any) -> Any:
            calls.append((a, k))
            return ret

        self.mp.setattr(handlers, name, _fake)
        return calls

    def on_transport(self, name: str, ret: Any) -> list:
        calls: list = []

        async def _fake(*a: Any, **k: Any) -> Any:
            calls.append((a, k))
            if isinstance(ret, BaseException):
                raise ret
            return ret

        self.mp.setattr(self.transport, name, _fake)
        return calls

    # -- running --------------------------------------------------------
    async def run(self, handler: str, args: dict | None = None, **ctx: Any) -> dict:
        self.ctx.update(ctx)
        step = ModuleStep(text="t", action=handler, action_args=dict(args or {}))
        fn = getattr(handlers, handler)
        out = await fn(step, self.state, self.transport, "", self.ctx, self.console)
        assert out is self.ctx
        return out

    # -- recorded transactions ------------------------------------------
    def records(self) -> list:
        return list(self.state.tx_index)

    def last(self) -> Any:
        return self.state.tx_index[-1]


def verdict(ctx: dict, action: str) -> dict:
    """The (single) recorded verification entry for *action*."""
    hits = [v for v in ctx.get("verifications", []) if v["action"] == action]
    assert len(hits) == 1, f"expected one {action} verification, got {hits}"
    return hits[0]


def checks_result(
    passed: bool = True, checks: list | None = None,
    failures: list | None = None, **kw: Any,
) -> SimpleNamespace:
    """A duck-typed verify result."""
    failures = list(failures or [])
    return SimpleNamespace(
        passed=passed, found=kw.pop("found", passed), checks=list(checks or []),
        failures=failures, **kw,
    )
