"""2.6.1: Argon's round-1 review (PASS, three Lows landed before the tag).

- F1: an expected failure that wrote no TxRecord left a "failed" placeholder
  acknowledgement, which could consume a genuine hashless failed record in the
  same step. An acknowledgement is now registered only when the handler
  recorded that failure.
- F2: ``validated`` is opt-in on the testnet transport. Only a validated
  ledger outcome sets it; local, guard and pre-submit failures are not
  validated.
- F3: helper handlers stop when their wallet isn't funded, and
  ``xrpl-lab fund`` exits non-zero when the balance never validates.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console
from xrpl.asyncio.transaction import XRPLReliableSubmissionException

import xrpl_lab.handlers as handlers
import xrpl_lab.transport.xrpl_testnet as xt
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult
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


# ── F1 ─────────────────────────────────────────────────────────────────


async def _hashless_masking_handler(step, state, transport, wallet_seed, ctx, console):
    """An expected hashless failure that records nothing (a local tem), then a
    genuine hashless failure that IS recorded as "failed"."""
    handlers._judge_expected_failure(
        console, ctx, SubmitResult(success=False, result_code="temMALFORMED", validated=False),
        ("temMALFORMED",), "f1", state=state,
    )
    state.record_tx(txid="failed", module_id=ctx.get("module_id", ""),
                    network=state.network, success=False)
    return ctx


async def _recorded_hashless_handler(step, state, transport, wallet_seed, ctx, console):
    """An expected hashless failure that the handler records, then judges."""
    result = SubmitResult(success=False, result_code="temCANNOT_PREAUTH_SELF", validated=False)
    state.record_tx(txid="failed", module_id=ctx.get("module_id", ""),
                    network=state.network, success=False)
    handlers._judge_expected_failure(
        console, ctx, result, ("temCANNOT_PREAUTH_SELF",), "f1b", state=state,
    )
    return ctx


def _module(action: str, handler) -> ModuleDef:
    try:
        resolve(action)
    except Exception:
        register(ActionDef(name=action, handler=handler, description="test-only"))
    return ModuleDef(
        id=f"{action}_mod", title=action, time="1 min", level="beginner",
        requires=[], produces=[], checks=[], raw_body="",
        steps=[ModuleStep(text="## Step 1: Act", action=action, action_args={})],
    )


@pytest.mark.asyncio
async def test_an_unrecorded_expected_failure_cannot_hide_a_hashless_one(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = _module("test_f1_mask", _hashless_masking_handler)
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == mod.id)
    assert cm.verified is False


@pytest.mark.asyncio
async def test_a_recorded_hashless_expected_failure_is_still_acknowledged(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = _module("test_f1_recorded", _recorded_hashless_handler)
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == mod.id)
    assert cm.verified is True


def test_every_judged_handler_passes_its_state() -> None:
    import inspect
    import re

    for name, fn in inspect.getmembers(handlers, inspect.iscoroutinefunction):
        src = inspect.getsource(fn)
        calls = len(re.findall(r"_judge_expected_failure\(", src))
        assert src.count("state=state") >= calls, name


# ── F2 ─────────────────────────────────────────────────────────────────


def test_structured_failures_are_not_validated_unless_said() -> None:
    assert xt._structured_failure("tecNO_PERMISSION").validated is False
    assert xt._structured_failure("tecNO_PERMISSION", validated=True).validated is True


def test_only_the_validated_mapping_is_validated() -> None:
    validated = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("Transaction failed: tecNO_PERMISSION"))
    tem = xt._map_reliable_submission_failure(
        XRPLReliableSubmissionException("temMALFORMED: Malformed transaction."))
    assert validated.validated is True
    assert tem.validated is False


@pytest.mark.asyncio
async def test_a_local_error_is_not_validated() -> None:
    result = await xt.XRPLTestnetTransport().submit_payment(
        wallet_seed="not-a-seed", destination="rDEST", amount="1",
    )
    assert result.success is False
    assert result.validated is False


def test_no_hand_built_testnet_failure_defaults_to_validated() -> None:
    import re

    src = Path(xt.__file__).read_text(encoding="utf-8")
    for m in re.finditer(r"SubmitResult\(\s*success=False,", src):
        call = src[m.start(): src.index(")", m.end()) + 1]
        assert "validated=" in call, src[m.start(): m.start() + 160]


# ── F3 ─────────────────────────────────────────────────────────────────


class _NeverAppears(DryRunTransport):
    async def fund_from_faucet(self, address):
        return FundResult(success=True, address=address, balance="unknown", message="ok")

    async def get_balance(self, address):
        return "0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "follow_up"),
    [
        ("handle_create_token_recipient", "set_trust_line"),
        ("handle_create_noopt_issuer", "set_trust_line"),
        ("handle_create_noclaw_issuer", "set_trust_line"),
    ],
)
async def test_helpers_stop_when_their_wallet_is_not_funded(
    monkeypatch: pytest.MonkeyPatch, handler_name: str, follow_up: str,
) -> None:
    import xrpl_lab.runtime as runtime
    from xrpl_lab.runtime import _SecretValue

    async def _instant(_seconds):
        return None

    async def _must_not_run(*args, **kwargs):
        raise AssertionError(f"{follow_up} ran from an unfunded wallet")

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)
    monkeypatch.setattr(handlers, follow_up, _must_not_run)
    monkeypatch.setattr(handlers, "issue_token", _must_not_run)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    console, _ = _console()
    ctx = {"wallet_seed": _SecretValue("sHOLDER"), "issuer_address": "rISSUER",
           "issuer_seed": _SecretValue("sISSUER"), "module_id": "m"}
    step = ModuleStep(text="helper", action="helper", action_args={"currency": "TOK"})
    ctx = await getattr(handlers, handler_name)(
        step, LabState(wallet_address="rHOLDER"), _NeverAppears(), "", ctx, console,
    )
    assert any(not v["passed"] for v in ctx.get("verifications", []))


def test_cli_fund_exits_non_zero_when_the_balance_never_validates(
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
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run: _NeverAppears())
    result = CliRunner().invoke(cli.main, ["fund"])
    assert result.exit_code == 2, result.output
