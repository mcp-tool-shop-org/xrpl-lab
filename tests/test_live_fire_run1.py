"""Regression tests for the defects 2.6.0's live-fire run 1 exposed.

Run 1 (docs/receipts/2.6.0-amm-live-fire/, module #30 on XRPL Testnet) created
no AMM. The chain, each link pinned by a test below:

1. **Funding was trusted to the faucet's reply.** ``ensure_funded`` counted a
   wallet as funded only when ``FundResult.balance`` parsed above zero; the live
   faucet's reply carried no usable balance, so three real fundings read as
   failures. The issuer path didn't wait at all, and its AccountSet went out
   before the new account was on a validated ledger. Funding is now decided by
   the account's balance on a validated ledger, polled for a bounded time, and
   the faucet is never asked twice after a success.
2. **A held ``ter`` result read as a bare timeout.** rippled holds a ``ter``
   instead of validating it; ``submit_and_wait`` keeps polling until
   ``LastLedgerSequence`` passes, which outlasted the 60 s client timeout, so
   the hash and the preliminary code (``terNO_RIPPLE``) were thrown away. The
   client now outwaits the window and reports the code and the hash.
3. **A failed step left the module looking verified.** Within the re-swarm-3
   ruling (a failing module still completes, recorded ``verified: false``), a
   failed submit or funding now counts like a failed verification, and the
   report and the completion panel say so.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console
from xrpl.asyncio.transaction import XRPLReliableSubmissionException
from xrpl.models.transactions import AccountSet
from xrpl.wallet import Wallet

import xrpl_lab.runtime as runtime
import xrpl_lab.transport.xrpl_testnet as xt
from xrpl_lab.handlers import handle_fund_issuer
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda *args, **kwargs: ""  # answer "Press Enter" between steps
    return console, buf


class _FaucetTransport:
    """A transport whose faucet answers success with no usable balance, and
    whose validated balance appears only after ``appear_after`` polls."""

    def __init__(self, appear_after: int | None) -> None:
        self.appear_after = appear_after
        self.balance_calls = 0
        self.fund_calls = 0
        self.funded = False

    async def get_balance(self, address: str) -> str:
        self.balance_calls += 1
        if not self.funded or self.appear_after is None:
            return "0"
        polls_since_fund = self.balance_calls - self._calls_at_fund
        return "100" if polls_since_fund >= self.appear_after else "0"

    async def fund_from_faucet(self, address: str) -> FundResult:
        self.fund_calls += 1
        self.funded = True
        self._calls_at_fund = self.balance_calls
        return FundResult(success=True, address=address, balance="unknown", message="ok")


@pytest.fixture()
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)


# ── 1. Funding is decided on the validated ledger ─────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_faucet_reply_without_balance_counts_once_the_account_appears() -> None:
    transport = _FaucetTransport(appear_after=2)
    console, _ = _console()
    funded = await runtime.ensure_funded(LabState(), transport, "rLEARNER", console)
    assert funded is True
    assert transport.fund_calls == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_faucet_is_not_asked_again_when_the_account_never_appears() -> None:
    transport = _FaucetTransport(appear_after=None)
    console, buf = _console()
    funded = await runtime.ensure_funded(LabState(), transport, "rLEARNER", console)
    assert funded is False
    assert transport.fund_calls == 1
    assert "validated ledger" in buf.getvalue()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_issuer_funding_waits_for_the_account_before_returning() -> None:
    transport = _FaucetTransport(appear_after=3)
    console, _ = _console()
    ctx = {"issuer_address": "rISSUER"}
    step = ModuleStep(text="fund", action="fund_issuer", action_args={})
    ctx = await handle_fund_issuer(step, LabState(), transport, "", ctx, console)
    assert transport.fund_calls == 1
    # The account was on a validated ledger before the handler returned.
    assert await transport.get_balance("rISSUER") == "100"
    assert all(v.get("passed", True) for v in ctx.get("verifications", []))


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_issuer_that_never_appears_is_a_failed_step() -> None:
    transport = _FaucetTransport(appear_after=None)
    console, _ = _console()
    ctx = {"issuer_address": "rISSUER"}
    step = ModuleStep(text="fund", action="fund_issuer", action_args={})
    ctx = await handle_fund_issuer(step, LabState(), transport, "", ctx, console)
    assert any(not v.get("passed", True) for v in ctx.get("verifications", []))


# ── 2. A held ter result keeps its code and hash ──────────────────────

_LLS_EXPIRED = (
    "The latest validated ledger sequence 21692400 is greater than "
    "LastLedgerSequence 21692383 in the transaction. Prelim result: terNO_RIPPLE"
)


def _wire_presign(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the local pre-sign succeed offline: autofill returns the tx with a
    fee and window, and signing is real (local keypair, no network)."""

    async def _fake_autofill(tx, client, *args, **kwargs):
        return type(tx).from_dict(
            {**tx.to_dict(), "fee": "12", "last_ledger_sequence": 21692383}
        )

    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(xt, "autofill", _fake_autofill)
    monkeypatch.setattr(xt, "_rpc_client", lambda url: _Ctx())


@pytest.mark.asyncio
async def test_held_ter_reports_its_code_and_hash_and_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_presign(monkeypatch)
    calls: list = []

    async def _held(tx, client, wallet=None):
        calls.append(tx)
        raise XRPLReliableSubmissionException(_LLS_EXPIRED)

    monkeypatch.setattr(xt, "submit_and_wait", _held)
    wallet = Wallet.create()
    tx = AccountSet(account=wallet.address, set_flag=8, sequence=7)
    result: SubmitResult = await xt.XRPLTestnetTransport()._submit_tx(
        tx, wallet, "AccountSet"
    )

    assert result.success is False
    assert result.result_code == "terNO_RIPPLE"
    assert len(result.txid) == 64
    assert result.txid == calls[0].get_hash()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_client_timeout_keeps_the_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_presign(monkeypatch)

    async def _slow(tx, client, wallet=None):
        raise TimeoutError

    monkeypatch.setattr(xt, "submit_and_wait", _slow)
    wallet = Wallet.create()
    tx = AccountSet(account=wallet.address, set_flag=8, sequence=7)
    result = await xt.XRPLTestnetTransport()._submit_tx(tx, wallet, "AccountSet")

    assert result.success is False
    assert result.result_code == "submit_timeout"
    assert len(result.txid) == 64
    assert "before reaching the network" not in result.error


def test_client_waits_past_the_ledger_window() -> None:
    """xrpl-py's autofill gives a 20-ledger window; at ~4 s a ledger that is
    ~80 s, so the client must wait longer than that to learn the outcome."""
    assert xt.SUBMIT_TIMEOUT >= 120


# ── 3. A failed step shows in the module's status and report ──────────


async def _failed_submit_handler(step, state, transport, wallet_seed, ctx, console):
    result = SubmitResult(success=False, txid="", result_code="terNO_RIPPLE")
    ctx["last_submit"] = result
    ctx.setdefault("failed_txids", []).append("terNO_RIPPLE")
    return ctx


async def _ok_submit_handler(step, state, transport, wallet_seed, ctx, console):
    txid = "A" * 64
    ctx["last_submit"] = SubmitResult(success=True, txid=txid, result_code="tesSUCCESS")
    ctx.setdefault("txids", []).append(txid)
    return ctx


def _register() -> None:
    for name, handler in (
        ("test_failed_submit", _failed_submit_handler),
        ("test_ok_submit", _ok_submit_handler),
    ):
        try:
            resolve(name)
        except Exception:
            register(ActionDef(name=name, handler=handler, description="test-only"))


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(tmp_path)
    _register()
    return tmp_path


@pytest.mark.asyncio
async def test_failed_submit_marks_the_module_not_verified_and_counts_it(
    _env: Path,
) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = ModuleDef(
        id="live_fire_mod", title="Live fire", time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[
            ModuleStep(text="## Step 1: Submit ok", action="test_ok_submit", action_args={}),
            ModuleStep(text="## Step 2: Submit held", action="test_failed_submit", action_args={}),
        ],
    )
    console, buf = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)

    cm = next(m for m in load_state().completed_modules if m.module_id == "live_fire_mod")
    assert cm.verified is False

    report = Path(cm.report_path).read_text(encoding="utf-8")
    assert "1 successful, 1 failed" in report
    assert "Steps: 1 passed, 1 failed" in report
    # Each step lists only its own transactions.
    step2 = report.split("Step 2: Submit held", 1)[1]
    assert "A" * 64 not in step2.split("Summary", 1)[0]

    out = buf.getvalue()
    assert "not verified" in out.lower()


@pytest.mark.asyncio
async def test_all_steps_passing_still_completes_verified(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = ModuleDef(
        id="live_fire_ok", title="Live fire ok", time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: Submit ok", action="test_ok_submit", action_args={})],
    )
    console, _ = _console()
    assert await run_module(mod, DryRunTransport(), dry_run=True, console=console) is True
    cm = next(m for m in load_state().completed_modules if m.module_id == "live_fire_ok")
    assert cm.verified is True

