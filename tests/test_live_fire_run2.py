"""Regression tests for the defects 2.6.0's live-fire run 2 exposed.

Run 2 (docs/receipts/2.6.0-amm-live-fire/) held every run-1 fix on the ledger,
and failed one layer deeper:

1. **Sizing.** A fresh testnet wallet gets one 100 XRP grant, and module #30
   pooled 100 XRP plus a 10 XRP deposit: AMMCreate validated tecUNFUNDED_AMM.
   Run 1's triple funding had hidden it.
2. **Accounting.** The runner keyed a failed step on ``context["last_submit"]``,
   which only 2 of 66 submitting handlers set, so the AMM failures counted as
   passed. That rule also misfired the other way: the failure-literacy lesson's
   deliberate failed payment sets ``last_submit``, so a correct lesson read as
   failed. A step now fails when it records a FAILED transaction.
3. **Hashes.** The failed AMMCreate validated, but its hash was neither printed
   nor indexed.
4. **Wasted submits.** After the failed create, the deposit and the withdraw
   were still broadcast.
5. **Exit code.** ``xrpl-lab run`` exited 0 on a run with failed steps.
"""

from __future__ import annotations

import ast
import inspect
import io
import re
import textwrap
from decimal import Decimal
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.actions.amm import verify_withdrawal
from xrpl_lab.modules import ModuleDef, ModuleStep, load_all_modules
from xrpl_lab.registry import ActionDef, all_actions, register, resolve
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import AccountSnapshot, AmmInfo, SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda *args, **kwargs: ""  # answer "Press Enter" between steps
    return console, buf


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── 2a. Every submitting handler records a failed submit ──────────────

# Handlers whose failure IS the lesson: they demonstrate a rejected
# transaction and must not count it as a failed step.
_DELIBERATE_FAILURES = frozenset({
    "handle_submit_payment_fail",
    "handle_create_token_escrow_expect_fail",
    "handle_send_multisig_payment_expect_fail",
    "handle_send_sender_payment_expect_blocked",
    "handle_send_outsider_payment_expect_blocked",
    "handle_send_untagged_deposit_expect_fail",
})


def _submitting_handlers() -> list[tuple[str, str]]:
    """(action, handler) for every registered handler that submits a tx.

    "Submits" means its body reads both ``.success`` and ``.txid`` off a
    result, which every SubmitResult consumer does.
    """
    out = []
    for action, action_def in sorted(all_actions().items()):
        fn = action_def.handler
        if getattr(fn, "__module__", "") != handlers.__name__:
            continue
        body = textwrap.dedent(inspect.getsource(fn))
        if re.search(r"\.success\b", body) and re.search(r"\.txid\b", body):
            out.append((action, fn.__name__))
    return out


def _records_a_failure(handler_name: str) -> bool:
    body = textwrap.dedent(inspect.getsource(getattr(handlers, handler_name)))
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
        if name == "_record_submit":
            return True
        if name == "record_tx":
            for kw in node.keywords:
                if (
                    kw.arg == "success"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                ):
                    return True
    return False


def test_the_registry_has_submitting_handlers() -> None:
    assert len(_submitting_handlers()) >= 60


@pytest.mark.parametrize(("action", "handler_name"), _submitting_handlers())
def test_every_submitting_handler_records_a_failed_submit(
    action: str, handler_name: str,
) -> None:
    if handler_name in _DELIBERATE_FAILURES:
        pytest.skip("its failure is the lesson")
    assert _records_a_failure(handler_name), (
        f"{handler_name} ({action}) submits a transaction but never records a "
        "failed one (record_tx(success=False) or _record_submit), so the runner "
        "can't count its failure"
    )


# ── 2b. The runner's rule ──────────────────────────────────────────────


async def _deliberate_failure_handler(step, state, transport, wallet_seed, ctx, console):
    """Like handle_submit_payment_fail: a rejected tx that IS the lesson."""
    ctx["last_submit"] = SubmitResult(success=False, result_code="tecUNFUNDED_PAYMENT")
    ctx.setdefault("failed_txids", []).append({"result_code": "tecUNFUNDED_PAYMENT"})
    return ctx


async def _recorded_failure_handler(step, state, transport, wallet_seed, ctx, console):
    """A real failure, reported the way _record_submit reports one."""
    state.record_tx(
        txid="B" * 64, module_id=ctx.get("module_id", ""),
        network=state.network, success=False,
    )
    return ctx


def _register(name: str, handler) -> None:
    try:
        resolve(name)
    except Exception:
        register(ActionDef(name=name, handler=handler, description="test-only"))


def _module(mid: str, action: str) -> ModuleDef:
    return ModuleDef(
        id=mid, title=mid, time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: Act", action=action, action_args={})],
    )


@pytest.mark.asyncio
async def test_a_deliberate_failure_keeps_the_module_verified(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    _register("test_deliberate_failure", _deliberate_failure_handler)
    console, _ = _console()
    await run_module(
        _module("lit_mod", "test_deliberate_failure"), DryRunTransport(),
        dry_run=True, console=console,
    )
    cm = next(m for m in load_state().completed_modules if m.module_id == "lit_mod")
    assert cm.verified is True


@pytest.mark.asyncio
async def test_a_recorded_failure_marks_the_step_failed(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    _register("test_recorded_failure", _recorded_failure_handler)
    console, _ = _console()
    await run_module(
        _module("fail_mod", "test_recorded_failure"), DryRunTransport(),
        dry_run=True, console=console,
    )
    cm = next(m for m in load_state().completed_modules if m.module_id == "fail_mod")
    assert cm.verified is False
    assert "Steps: 0 passed, 1 failed" in Path(cm.report_path).read_text(encoding="utf-8")


# ── 3 and 4. A failed AMMCreate keeps its hash; later steps skip ──────

_HASH = "1C14C1C3E9A16FF36961ED3AFC7C64D77E26A4065441CC45267021535E08A1F5"


class _AmmTransport(DryRunTransport):
    def __init__(self, balance_xrp: int, owners: int = 1) -> None:
        super().__init__()
        self._balance = balance_xrp * 1_000_000
        self._owners = owners

    async def get_amm_info(self, *args, **kwargs):
        return None

    async def get_reserves(self):
        return 1_000_000, 200_000

    async def get_account_info(self, address):
        return AccountSnapshot(
            address=address, balance_drops=str(self._balance), owner_count=self._owners,
        )


def _amm_ctx() -> dict:
    from xrpl_lab.runtime import _SecretValue

    return {"module_id": "amm_liquidity_101", "issuer_address": "rISSUER",
            "wallet_seed": _SecretValue("sSEED")}


@pytest.mark.asyncio
async def test_a_validated_tec_create_keeps_its_hash_and_skips_the_pool_steps(
    _env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _tec_create(*args, **kwargs):
        return AmmInfo(asset_a="XRP", asset_b="LAB"), SubmitResult(
            success=False, txid=_HASH, result_code="tecUNFUNDED_AMM",
            error="Insufficient funds to create the AMM",
        )

    async def _must_not_run(*args, **kwargs):
        raise AssertionError("a pool step was submitted with no pool")

    monkeypatch.setattr(handlers, "ensure_amm_pair", _tec_create)
    monkeypatch.setattr(handlers, "amm_deposit", _must_not_run)
    monkeypatch.setattr(handlers, "amm_withdraw", _must_not_run)

    state = LabState(wallet_address="rLEARNER", network="testnet")
    transport = _AmmTransport(balance_xrp=100)
    console, buf = _console()
    ctx = _amm_ctx()
    create = ModuleStep(text="create", action="ensure_amm_pair", action_args={
        "a_currency": "XRP", "a_value": "25", "b_currency": "LAB", "b_value": "25"})
    ctx = await handlers.handle_ensure_amm_pair(create, state, transport, "", ctx, console)

    assert any(r.txid == _HASH and not r.success for r in state.tx_index)
    assert _HASH in buf.getvalue()

    deposit = ModuleStep(text="deposit", action="amm_deposit", action_args={
        "a_currency": "XRP", "a_value": "5", "b_currency": "LAB", "b_value": "5"})
    ctx = await handlers.handle_amm_deposit(deposit, state, transport, "", ctx, console)
    withdraw = ModuleStep(text="withdraw", action="amm_withdraw", action_args={
        "a_currency": "XRP", "b_currency": "LAB"})
    ctx = await handlers.handle_amm_withdraw(withdraw, state, transport, "", ctx, console)

    skipped = [v for v in ctx.get("verifications", []) if not v.get("passed", True)]
    assert len(skipped) == 2
    assert "Skipped: no AMM pool" in buf.getvalue()


@pytest.mark.asyncio
async def test_preflight_names_the_shortfall_and_does_not_create(
    _env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _must_not_create(*args, **kwargs):
        raise AssertionError("AMMCreate was submitted without the XRP to fund it")

    monkeypatch.setattr(handlers, "ensure_amm_pair", _must_not_create)
    state = LabState(wallet_address="rLEARNER", network="testnet")
    console, buf = _console()
    step = ModuleStep(text="create", action="ensure_amm_pair", action_args={
        "a_currency": "XRP", "a_value": "100", "b_currency": "LAB", "b_value": "100"})
    ctx = await handlers.handle_ensure_amm_pair(
        step, state, _AmmTransport(balance_xrp=100), "", _amm_ctx(), console,
    )
    out = buf.getvalue()
    assert "needs 101.6 XRP" in out and "has 100 XRP" in out
    assert any(not v.get("passed", True) for v in ctx.get("verifications", []))


# ── 1. Module #30 fits one faucet grant ───────────────────────────────


def test_module_30_fits_one_faucet_grant() -> None:
    """A fresh testnet wallet gets 100 XRP once. The pool's XRP leg, the
    deposit, the create fee (0.2) and the reserves (1 base + 0.2 for each of
    the LAB line and the LP line) must fit, with room to spare."""
    module = load_all_modules()["amm_liquidity_101"]
    create = next(s for s in module.steps if s.action == "ensure_amm_pair")
    deposit = next(s for s in module.steps if s.action == "amm_deposit")
    xrp = Decimal(create.action_args["a_value"]) + Decimal(deposit.action_args["a_value"])
    needed = xrp + Decimal("0.2") + Decimal("1") + 2 * Decimal("0.2")
    assert needed <= 50, f"module #30 needs {needed} XRP of a 100 XRP grant"


# ── the withdrawal verdict ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_withdrawal_with_nothing_returned_has_no_success_line() -> None:
    class _NoLp(DryRunTransport):
        async def get_lp_token_balance(self, *args, **kwargs):
            return "0"

    result = await verify_withdrawal(
        _NoLp(), "rLEARNER", AmmInfo(asset_a="XRP", asset_b="LAB"), lp_before="0",
    )
    assert result.failures
    assert not any("All LP tokens returned" in c for c in result.checks)


# ── 5. Exit code ───────────────────────────────────────────────────────


def test_run_exits_partial_when_the_module_completed_unverified(_env: Path) -> None:
    from xrpl_lab.cli import _exit_if_unverified
    from xrpl_lab.state import load_state, save_state

    state = load_state()
    state.complete_module("amm_liquidity_101", txids=[], verified=False)
    save_state(state)
    console, _ = _console()
    with pytest.raises(SystemExit) as exc:
        _exit_if_unverified("amm_liquidity_101", True, console)
    assert exc.value.code == 3


def test_run_exits_normally_when_verified(_env: Path) -> None:
    from xrpl_lab.cli import _exit_if_unverified
    from xrpl_lab.state import load_state, save_state

    state = load_state()
    state.complete_module("amm_liquidity_101", txids=[], verified=True)
    save_state(state)
    console, _ = _console()
    _exit_if_unverified("amm_liquidity_101", True, console)


# ── Argon's review of run 2 (F3, F4, F5.3, F6) ─────────────────────────


@pytest.mark.asyncio
async def test_a_failed_create_keeps_the_pool_issuers() -> None:
    """F4: a failed AMMCreate used to return AmmInfo with empty issuers, and
    the verify step's pool refresh then sent amm_info for LAB with issuer ""
    (rippled: issueMalformed, seen in runs 1 and 2)."""
    from xrpl_lab.actions.amm import ensure_amm_pair as action_ensure

    class _FailCreate(DryRunTransport):
        async def get_amm_info(self, *args, **kwargs):
            return None

        async def submit_amm_create(self, **kwargs):
            return SubmitResult(success=False, txid=_HASH, result_code="tecUNFUNDED_AMM")

    info, result = await action_ensure(
        _FailCreate(), "sSEED", "XRP", "25", "", "LAB", "25", "rISSUER",
    )
    assert result.success is False
    assert info.asset_b_issuer == "rISSUER"


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_name", ["handle_verify_lp_received", "handle_verify_withdrawal"])
async def test_verify_steps_make_no_rpc_without_a_pool(handler_name: str) -> None:
    """F5.3: with no pool (empty LP token), the verify steps fail at once
    instead of querying the ledger with empty currency and issuer."""

    class _NoCalls(DryRunTransport):
        async def get_amm_info(self, *args, **kwargs):
            raise AssertionError("amm_info queried with no pool")

        async def get_lp_token_balance(self, *args, **kwargs):
            raise AssertionError("LP balance queried with no pool")

    console, _ = _console()
    ctx = {"amm_info": AmmInfo(asset_a="XRP", asset_b="LAB")}
    step = ModuleStep(text="verify", action="verify", action_args={})
    handler = getattr(handlers, handler_name)
    ctx = await handler(step, LabState(wallet_address="rLEARNER"), _NoCalls(), "", ctx, console)
    assert any(not v.get("passed", True) for v in ctx.get("verifications", []))


@pytest.mark.asyncio
async def test_amm_info_act_not_found_is_quiet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """F6: rippled's amm_info answers actNotFound when a pair has no pool;
    that's the healthy "create one" answer, not a warning."""
    import xrpl_lab.transport.xrpl_testnet as xt

    class _Resp:
        result = {"error": "actNotFound"}

    class _Client:
        async def request(self, *args, **kwargs):
            return _Resp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(xt, "_rpc_client", lambda url: _Client())
    with caplog.at_level("WARNING", logger="xrpl_lab.transport.xrpl_testnet"):
        info = await xt.XRPLTestnetTransport().get_amm_info("XRP", "", "LAB", "rISSUER")
    assert info is None
    assert "amm_info error" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "label"),
    [("tecUNFUNDED_AMM", "validated failure"), ("terNO_AMM", "not validated")],
)
async def test_a_failed_deposit_prints_its_hash_and_whether_it_validated(
    monkeypatch: pytest.MonkeyPatch, code: str, label: str,
) -> None:
    """F3: a failed AMM submit prints its hash, and says whether it's on the
    ledger (a tec) or never validated (a ter, which can return txnNotFound)."""

    async def _failed_deposit(*args, **kwargs):
        return SubmitResult(success=False, txid=_HASH, result_code=code, error="failed")

    monkeypatch.setattr(handlers, "amm_deposit", _failed_deposit)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    console, buf = _console()
    step = ModuleStep(text="deposit", action="amm_deposit", action_args={
        "a_currency": "XRP", "a_value": "5", "b_currency": "LAB", "b_value": "5"})
    await handlers.handle_amm_deposit(
        step, LabState(wallet_address="rLEARNER"), DryRunTransport(), "", _amm_ctx(), console,
    )
    out = buf.getvalue()
    assert _HASH in out and label in out
