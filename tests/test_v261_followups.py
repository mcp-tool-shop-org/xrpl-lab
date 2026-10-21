"""2.6.1: the follow-ups from 2.6.0's live-fire runs (issue #20).

1. Eleven handlers fund a brand-new helper wallet straight from the faucet and
   go on as soon as the faucet answers. Module #30's issuer did the same, and
   its next transaction, sent before the account was on a validated ledger,
   never landed (live-fire run 1). Every faucet call in the handlers now waits
   for the validated balance, and a wallet that never appears is a failed step.
2. ``xrpl-lab fund`` printed the faucet's own reply as the balance.
3. Argon's three Lows from its round-2 review: assert (not skip) the
   deliberate-failure handlers, count the report's failed transactions from the
   same TxRecords as the step signal, and mark the pool unavailable when the
   transport doesn't support AMMs.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import AmmInfo, FundResult, SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda *args, **kwargs: ""
    return console, buf


@pytest.fixture()
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    import xrpl_lab.runtime as runtime

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── 1. Every faucet call waits for the validated ledger ───────────────


def _functions_calling_the_faucet() -> list[str]:
    tree = ast.parse(inspect.getsource(handlers))
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and getattr(sub.func, "attr", "") == "fund_from_faucet"
            ):
                out.append(node.name)
                break
    return out


def test_handlers_call_the_faucet_somewhere() -> None:
    assert _functions_calling_the_faucet()


@pytest.mark.parametrize("name", _functions_calling_the_faucet())
def test_every_faucet_call_waits_for_the_validated_ledger(name: str) -> None:
    body = textwrap.dedent(inspect.getsource(getattr(handlers, name)))
    assert "await_validated_balance(" in body, (
        f"{name} funds a wallet from the faucet and goes on without waiting for "
        "it to appear on a validated ledger (the live-fire run 1 race)"
    )


class _FaucetTransport(DryRunTransport):
    """The faucet answers success; the account shows a balance only after
    ``appear_after`` validated-balance polls (None: never)."""

    def __init__(self, appear_after: int | None) -> None:
        super().__init__()
        self.appear_after = appear_after
        self.polls = 0
        self.fund_calls = 0

    async def fund_from_faucet(self, address: str) -> FundResult:
        self.fund_calls += 1
        return FundResult(success=True, address=address, balance="unknown", message="ok")

    async def get_balance(self, address: str) -> str:
        self.polls += 1
        if self.appear_after is None or self.polls < self.appear_after:
            return "0"
        return "100"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_a_helper_wallet_is_ready_before_the_step_returns() -> None:
    transport = _FaucetTransport(appear_after=3)
    console, buf = _console()
    step = ModuleStep(text="receiver", action="create_channel_receiver", action_args={})
    ctx = await handlers.handle_create_channel_receiver(
        step, LabState(), transport, "", {}, console,
    )
    assert transport.fund_calls == 1
    assert transport.polls >= 3
    assert all(v.get("passed", True) for v in ctx.get("verifications", []))
    assert "Balance: 100 XRP" in buf.getvalue()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_sleep")
async def test_a_helper_wallet_that_never_appears_is_a_failed_step() -> None:
    transport = _FaucetTransport(appear_after=None)
    console, _ = _console()
    step = ModuleStep(text="receiver", action="create_channel_receiver", action_args={})
    ctx = await handlers.handle_create_channel_receiver(
        step, LabState(), transport, "", {}, console,
    )
    assert transport.fund_calls == 1
    assert any(not v.get("passed", True) for v in ctx.get("verifications", []))


# ── 2. xrpl-lab fund reports the ledger's balance ─────────────────────


def test_cli_fund_waits_for_the_validated_balance(
    _env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    import xrpl_lab.cli as cli
    import xrpl_lab.runtime as runtime
    from xrpl_lab.state import load_state, save_state

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)
    state = load_state()
    state.wallet_address = "rLEARNER"
    save_state(state)
    transport = _FaucetTransport(appear_after=2)
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run: transport)

    result = CliRunner().invoke(cli.main, ["fund"])
    assert result.exit_code == 0, result.output
    assert transport.fund_calls == 1
    assert "100 XRP" in result.output
    assert "unknown" not in result.output


# ── 3a. Deliberate failures are asserted, not skipped ─────────────────


def test_deliberate_failure_handlers_record_their_rejection() -> None:
    """Argon Low 1 asserted these handlers recorded no failed TxRecord, so the
    lesson wouldn't read as failed. Since 2.6.1 the judge acknowledges a
    recorded rejection by txid, and 2.6.2 (#20 item 8) records it, so the
    report and proof pack carry the tec."""
    from tests.test_live_fire_run2 import _DELIBERATE_FAILURES, _records_a_failure

    for name in sorted(_DELIBERATE_FAILURES):
        assert _records_a_failure(name), f"{name} doesn't record its rejection"


def test_the_run2_sweep_no_longer_skips() -> None:
    source = Path("tests/test_live_fire_run2.py").read_text(encoding="utf-8")
    assert 'pytest.skip("its failure is the lesson")' not in source


# ── 3b. The report counts failed transactions from the TxRecords ──────


async def _records_only_handler(step, state, transport, wallet_seed, ctx, console):
    """A failure reported only through record_tx, like AMM deposit/withdraw."""
    state.record_tx(
        txid="C" * 64, module_id=ctx.get("module_id", ""),
        network=state.network, success=False,
    )
    return ctx


@pytest.mark.asyncio
async def test_report_counts_failed_transactions_from_the_records(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    try:
        resolve("test_records_only")
    except Exception:
        register(ActionDef(
            name="test_records_only", handler=_records_only_handler, description="test-only",
        ))
    mod = ModuleDef(
        id="count_mod", title="count", time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: Act", action="test_records_only", action_args={})],
    )
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == "count_mod")
    report = Path(cm.report_path).read_text(encoding="utf-8")
    assert "Transactions: 0 successful, 1 failed" in report


# ── 3c. An unsupported transport leaves no pool ───────────────────────


@pytest.mark.asyncio
async def test_unsupported_amm_marks_the_pool_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unsupported(*args, **kwargs):
        return AmmInfo(asset_a="XRP", asset_b="LAB"), SubmitResult(
            success=False, result_code="notSupported", error="AMM not supported",
        )

    monkeypatch.setattr(handlers, "ensure_amm_pair", _unsupported)

    class _NoPool(DryRunTransport):
        async def get_amm_info(self, *args, **kwargs):
            return None

        async def get_reserves(self):
            return None

    console, _ = _console()
    step = ModuleStep(text="create", action="ensure_amm_pair", action_args={
        "a_currency": "XRP", "a_value": "25", "b_currency": "LAB", "b_value": "25"})
    from xrpl_lab.runtime import _SecretValue

    ctx = await handlers.handle_ensure_amm_pair(
        step, LabState(wallet_address="rLEARNER"), _NoPool(), "",
        {"issuer_address": "rISSUER", "wallet_seed": _SecretValue("sSEED")}, console,
    )
    assert ctx.get("amm_unavailable") is True
    assert any(not v.get("passed", True) for v in ctx.get("verifications", []))
