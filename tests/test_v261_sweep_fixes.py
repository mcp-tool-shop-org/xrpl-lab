"""2.6.1: the defects the helper-wallet sweep on 2.6.0 found.

Sweep 1 (docs/receipts/2.6.1-helper-wallet-sweep/) ran the 10 testnet modules
that fund a helper wallet. Beyond the funding race (fixed in b6815f7), it
found:

- **B. Correct lessons counted as failed.** 2.6.0 counts a step failed when it
  records a failed transaction. Lessons whose point is a rejected transaction
  (tecDUPLICATE, tecNO_PERMISSION, ...) record that expected tec too, so they
  read as failed (credentials, permissioned_domains, clawback).
- **A'. A false pass.** checks_101's outsider CheckCash "got" its expected
  tecNO_PERMISSION, but the transaction never validated: its window closed on
  a preliminary result. A lesson expecting a tec now needs it on the ledger.
- **C. Sizing.** nft_marketplace and the capstone list an NFT at 100 XRP to a
  buyer funded once with 100 XRP (tecINSUFFICIENT_FUNDS).
- **D. Code bugs.** payment_channel stored the channel's base58 public key
  (account_channels' ``public_key``), so claim checks and redemption failed;
  xrpl-py 4.5 serialises ``credential_ids`` as "CredentialIds", which the
  binary codec rejects, so deposit_gate's KYC payment couldn't be signed.
"""

from __future__ import annotations

import inspect
import io
import re
from pathlib import Path

import pytest
from rich.console import Console
from xrpl.asyncio.transaction import XRPLReliableSubmissionException

import xrpl_lab.handlers as handlers
import xrpl_lab.transport.xrpl_testnet as xt
from xrpl_lab.modules import ModuleDef, ModuleStep, load_all_modules
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda *args, **kwargs: ""
    return console, buf


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── A'. A result says whether it validated ─────────────────────────────


def test_an_expired_window_is_not_a_validated_result() -> None:
    msg = (
        "The latest validated ledger sequence 105 is greater than "
        "LastLedgerSequence 100 in the transaction. Prelim result: tecNO_PERMISSION"
    )
    result = xt._map_reliable_submission_failure(XRPLReliableSubmissionException(msg))
    assert result is not None
    assert result.result_code == "tecNO_PERMISSION"
    assert result.validated is False
    assert "never validated" in result.error.lower()


def test_a_validated_tec_is_validated() -> None:
    result = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("Transaction failed: tecNO_PERMISSION")
    )
    assert result is not None and result.validated is True


def test_a_tem_rejection_is_not_validated() -> None:
    result = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("temMALFORMED: Malformed transaction.")
    )
    assert result is not None and result.validated is False


# ── B. An expected failure is acknowledged, not counted ───────────────


def test_judge_accepts_only_the_validated_expected_code() -> None:
    from xrpl_lab.handlers import _judge_expected_failure

    def judge(result: SubmitResult) -> tuple[bool, dict]:
        ctx: dict = {}
        console, _ = _console()
        ok = _judge_expected_failure(
            console, ctx, result, ("tecNO_PERMISSION",), "cash_check_outsider",
        )
        return ok, ctx

    ok, ctx = judge(SubmitResult(success=False, result_code="tecNO_PERMISSION"))
    assert ok and ctx["expected_failures"] == 1
    assert not ctx.get("verifications")

    for wrong in (
        SubmitResult(success=False, result_code="tecNO_PERMISSION", validated=False),
        SubmitResult(success=False, result_code="tefPAST_SEQ", validated=False),
        SubmitResult(success=True, result_code="tesSUCCESS"),
    ):
        ok, ctx = judge(wrong)
        assert not ok
        assert not ctx.get("expected_failures")
        assert any(not v["passed"] for v in ctx["verifications"])


def test_a_tem_expectation_does_not_need_validation() -> None:
    from xrpl_lab.handlers import _judge_expected_failure

    console, _ = _console()
    ctx: dict = {}
    ok = _judge_expected_failure(
        console, ctx,
        SubmitResult(success=False, result_code="temMALFORMED", validated=False),
        ("temMALFORMED",), "preauthorize_self",
    )
    assert ok and ctx["expected_failures"] == 1


async def _expected_tec_handler(step, state, transport, wallet_seed, ctx, console):
    """Like create_credential_duplicate: a lesson whose point is a tec. It
    records the failed tx (it IS on the ledger) and acknowledges it."""
    from xrpl_lab.handlers import _judge_expected_failure

    result = SubmitResult(success=False, txid="D" * 64, result_code="tecDUPLICATE")
    state.record_tx(txid=result.txid, module_id=ctx.get("module_id", ""),
                    network=state.network, success=False)
    _judge_expected_failure(console, ctx, result, ("tecDUPLICATE",), "dup")
    return ctx


@pytest.mark.asyncio
async def test_an_acknowledged_expected_failure_keeps_the_module_verified(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    try:
        resolve("test_expected_tec")
    except Exception:
        register(ActionDef(name="test_expected_tec", handler=_expected_tec_handler,
                           description="test-only"))
    mod = ModuleDef(
        id="lesson_mod", title="lesson", time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: Dup", action="test_expected_tec", action_args={})],
    )
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == "lesson_mod")
    assert cm.verified is True


# ── C. The NFT lessons fit one faucet grant ───────────────────────────


@pytest.mark.parametrize("module_id", ["nft_marketplace_101", "game_economy_capstone"])
def test_nft_sale_prices_fit_one_faucet_grant(module_id: str) -> None:
    """A buyer funded once gets 100 XRP and must keep 1 XRP base reserve plus
    0.2 XRP per object; every listing must be affordable with room to spare."""
    module = load_all_modules()[module_id]
    prices = [
        float(s.action_args.get("amount", "0"))
        for s in module.steps if s.action == "list_nft_sell_offer"
    ]
    assert prices
    assert max(prices) <= 50, f"{module_id} lists at {prices} XRP"


# ── D1. The channel's key is the hex one ──────────────────────────────


@pytest.mark.asyncio
async def test_channel_public_key_is_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        result = {"channels": [{
            "channel_id": "AB" * 32, "amount": "15000000", "balance": "0",
            "destination_account": "rDEST", "settle_delay": 86400,
            "public_key": "aKGgKDHGtHfwHkte8EjdtYdvg5rj3DuxjqACxvm5hzLdXLBwWgf9",
            "public_key_hex": "ED" + "FB" * 32,
        }]}

    class _Client:
        async def request(self, *args, **kwargs):
            return _Resp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(xt, "_rpc_client", lambda url: _Client())
    channels = await xt.XRPLTestnetTransport().get_account_channels("rSENDER")
    assert channels[0].public_key == "ED" + "FB" * 32


# ── D2. credential_ids serialises as CredentialIDs ────────────────────


def test_a_payment_with_credentials_can_be_signed() -> None:
    from xrpl.models.transactions import Payment
    from xrpl.transaction import sign
    from xrpl.wallet import Wallet

    sender, dest = Wallet.create(), Wallet.create()
    tx = Payment(
        account=sender.address, destination=dest.address, amount="10000000",
        credential_ids=["F2C81CF9EC208A95" + "0" * 48],
        fee="12", sequence=5, last_ledger_sequence=100,
    )
    assert "CredentialIDs" in tx.to_xrpl()
    assert len(sign(tx, sender).get_hash()) == 64


# ── B (cont.). Every expected-failure handler is judged ───────────────

_EXPECTED_FAILURE_NAME = re.compile(
    r"_expect_fail$|_expect_blocked$|_duplicate$|_wrong_party$|_unfunded$|"
    r"_nonowner$|_uncredentialed$|^handle_submit_payment_fail$"
)


def _expected_failure_handlers() -> list[str]:
    return sorted(
        name for name, fn in inspect.getmembers(handlers, inspect.iscoroutinefunction)
        if name.startswith("handle_") and _EXPECTED_FAILURE_NAME.search(name)
    )


def test_there_are_expected_failure_handlers() -> None:
    assert len(_expected_failure_handlers()) >= 19


@pytest.mark.parametrize("name", _expected_failure_handlers())
def test_every_expected_failure_handler_is_judged(name: str) -> None:
    source = inspect.getsource(getattr(handlers, name))
    assert "_judge_expected_failure(" in source, (
        f"{name} teaches a rejected transaction but never judges the outcome, "
        "so a tec that never validated (or the wrong code) would read as the lesson"
    )


def _check_ctx() -> dict:
    from xrpl_lab.runtime import _SecretValue

    return {
        "module_id": "checks_101", "check_id": "CC" * 32,
        "outsider_seed": _SecretValue("sOUTSIDER"), "outsider_address": "rOUTSIDER",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "acknowledged"),
    [
        (SubmitResult(success=False, txid="E" * 64, result_code="tecNO_PERMISSION"), True),
        # The sweep's false pass: the window closed on a preliminary tec.
        (SubmitResult(success=False, txid="E" * 64, result_code="tecNO_PERMISSION",
                      validated=False), False),
        (SubmitResult(success=False, result_code="tefPAST_SEQ", validated=False), False),
    ],
)
async def test_the_checks_outsider_needs_a_validated_rejection(
    monkeypatch: pytest.MonkeyPatch, result: SubmitResult, acknowledged: bool,
) -> None:
    from xrpl_lab.state import LabState

    async def _cash(*args, **kwargs):
        return result

    monkeypatch.setattr(handlers, "cash_check", _cash)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    console, _ = _console()
    step = ModuleStep(text="cash", action="cash_check_wrong_destination_expect_fail",
                      action_args={})
    ctx = await handlers.handle_cash_check_wrong_destination_expect_fail(
        step, LabState(), DryRunTransport(), "", _check_ctx(), console,
    )
    assert bool(ctx.get("expected_failures")) is acknowledged
    failed = any(not v["passed"] for v in ctx.get("verifications", []))
    assert failed is (not acknowledged)


def test_a_non_numeric_amm_leg_is_kept_as_is() -> None:
    """Found by the 2.6.1 coverage work: drops_to_xrp raises XRPRangeException,
    which _parse_amm_amount didn't catch, so get_amm_info crashed."""
    assert xt.XRPLTestnetTransport._parse_amm_amount("not-drops") == "not-drops"
    assert xt.XRPLTestnetTransport._parse_amm_amount("25000000") == "25"


@pytest.mark.asyncio
async def test_a_malformed_nft_offer_bound_is_explained() -> None:
    """Found by the 2.6.1 coverage work: a malformed expected_min failed the
    verification without printing why."""
    from xrpl_lab.state import LabState

    console, buf = _console()
    step = ModuleStep(text="verify", action="verify_nft_offer",
                      action_args={"expected_min": "two"})
    ctx = await handlers.handle_verify_nft_offer(
        step, LabState(), DryRunTransport(), "", {"nft_id": "00" * 32}, console,
    )
    assert any(not v["passed"] for v in ctx["verifications"])
    assert "expected_min" in buf.getvalue()


@pytest.mark.asyncio
async def test_the_unfunded_subject_is_a_fresh_address_each_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sweep 2: the lesson's 'unfunded' subject was a fixed example address
    that is funded on testnet, so CredentialCreate succeeded (tesSUCCESS)
    instead of teaching tecNO_TARGET. Each run now attests a fresh address
    that has never been funded."""
    from xrpl_lab.runtime import _SecretValue
    from xrpl_lab.state import LabState

    subjects: list[str] = []

    async def _capture(transport, seed, subject, credential_type, **kwargs):
        subjects.append(subject)
        return SubmitResult(success=False, txid="F" * 64, result_code="tecNO_TARGET")

    monkeypatch.setattr(handlers, "create_credential", _capture)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    for _ in range(2):
        console, _ = _console()
        ctx = await handlers.handle_create_credential_unfunded(
            ModuleStep(text="unfunded", action="create_credential_unfunded", action_args={}),
            LabState(wallet_address="rISSUER"), DryRunTransport(), "",
            {"wallet_seed": _SecretValue("sISSUER")}, console,
        )
        assert ctx.get("expected_failures") == 1
    assert "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe" not in subjects
    assert len(set(subjects)) == 2
