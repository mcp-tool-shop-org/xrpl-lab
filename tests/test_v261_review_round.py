"""2.6.1: R&D's early review of #21 (M1, L1-L4).

- M1/L1: expected-failure steps pinned to the code each lesson teaches. An
  empty expected set accepted any validated tec or any tem, so an unrelated
  rejection could pass as the lesson.
- L2: the runner matched acknowledgements to failed records by count, so a
  judged failure that writes no TxRecord could hide a genuine failed record in
  the same step. It now matches by txid.
- L3: the first payment to the practice address must carry the base reserve,
  whatever the ledger's reserve is.
- L4: the report separates expected rejections from failures.
"""

from __future__ import annotations

import inspect
import io
import re
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.state import LabState
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


# ── M1 / L1. Each lesson's code is pinned ──────────────────────────────

PINNED = {
    "handle_issue_token_expect_fail": "tecPATH_DRY",
    "handle_create_permissioned_offer_uncredentialed": "tecNO_PERMISSION",
    "handle_modify_domain_nonowner": "tecNO_PERMISSION",
    "handle_clawback_expect_fail": "tecNO_PERMISSION",
    "handle_accept_nft_offer_expect_fail": "tecOBJECT_NOT_FOUND",
    "handle_modify_nft_expect_fail": "tecNO_PERMISSION",
    "handle_accept_credential_wrong_party": "tecNO_ENTRY",
}


def _judged_codes(name: str) -> tuple[str, ...]:
    src = inspect.getsource(getattr(handlers, name))
    m = re.search(r"_judge_expected_failure\(\s*console, context, result,\s*\(([^)]*)\)", src)
    assert m, name
    return tuple(c.strip().strip('"') for c in m.group(1).split(",") if c.strip())


@pytest.mark.parametrize(("name", "code"), sorted(PINNED.items()))
def test_each_lesson_judges_exactly_its_code(name: str, code: str) -> None:
    assert _judged_codes(name) == (code,)


def test_only_submit_payment_fail_keeps_an_open_expectation() -> None:
    open_ones = [
        name for name, fn in inspect.getmembers(handlers, inspect.iscoroutinefunction)
        if name.startswith("handle_") and "_judge_expected_failure(" in inspect.getsource(fn)
        and re.search(r"_judge_expected_failure\(\s*console, context, result,\s*\(\)",
                      inspect.getsource(fn))
    ]
    assert open_ones == []


def test_a_tem_no_longer_passes_as_the_clawback_lesson() -> None:
    console, _ = _console()
    ctx: dict = {}
    ok = handlers._judge_expected_failure(
        console, ctx, SubmitResult(success=False, result_code="temMALFORMED", validated=False),
        ("tecNO_PERMISSION",), "clawback_expect_fail",
    )
    assert not ok
    assert any(not v["passed"] for v in ctx["verifications"])


# ── L2. Acknowledgements match failed records by txid ─────────────────


async def _masked_handler(step, state, transport, wallet_seed, ctx, console):
    """A judged expected failure that records nothing (a local tem), then a
    genuine failed transaction in the same step."""
    handlers._judge_expected_failure(
        console, ctx, SubmitResult(success=False, result_code="temMALFORMED", validated=False),
        ("temMALFORMED",), "masked",
    )
    state.record_tx(txid="B" * 64, module_id=ctx.get("module_id", ""),
                    network=state.network, success=False)
    return ctx


async def _acknowledged_handler(step, state, transport, wallet_seed, ctx, console):
    result = SubmitResult(success=False, txid="C" * 64, result_code="tecDUPLICATE")
    state.record_tx(txid=result.txid, module_id=ctx.get("module_id", ""),
                    network=state.network, success=False)
    handlers._judge_expected_failure(console, ctx, result, ("tecDUPLICATE",), "ack")
    return ctx


def _run_one(action: str, handler) -> Path:
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
async def test_a_judged_failure_without_a_record_cannot_hide_a_real_one(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = _run_one("test_masked", _masked_handler)
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == mod.id)
    assert cm.verified is False


@pytest.mark.asyncio
async def test_an_acknowledged_record_still_passes_and_is_reported_as_expected(_env: Path) -> None:
    from xrpl_lab.runner import run_module
    from xrpl_lab.state import load_state

    mod = _run_one("test_acknowledged", _acknowledged_handler)
    console, _ = _console()
    await run_module(mod, DryRunTransport(), dry_run=True, console=console)
    cm = next(m for m in load_state().completed_modules if m.module_id == mod.id)
    assert cm.verified is True
    report = Path(cm.report_path).read_text(encoding="utf-8")
    assert "1 failed (1 expected)" in report  # L4


# ── L3. The first practice payment carries the base reserve ───────────


@pytest.mark.asyncio
async def test_the_first_practice_payment_carries_the_base_reserve(monkeypatch) -> None:
    sent: list[str] = []

    async def _send(transport, seed, dest, amount, memo=""):
        sent.append(amount)
        return SubmitResult(success=True, txid="A" * 64, result_code="tesSUCCESS")

    class _HighReserve(DryRunTransport):
        async def get_reserves(self):
            return 2_000_000, 200_000  # a 2 XRP base reserve

    monkeypatch.setattr(handlers, "send_payment", _send)
    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    state = LabState(wallet_address="rLEARNER1234567890abcdefghijkLM")
    ctx: dict = {}
    step = ModuleStep(text="pay", action="submit_payment",
                      action_args={"destination": "self", "amount": "1"})
    for _ in range(2):
        console, _ = _console()
        ctx = await handlers.handle_submit_payment(step, state, _HighReserve(), "", ctx, console)
    assert float(sent[0]) >= 2  # creates the account
    assert sent[1] == "1"  # later payments send what the lesson says


# ── The CredentialIDs shim stays wired ────────────────────────────────


def test_the_credential_ids_abbreviation_is_registered() -> None:
    import xrpl.models.base_model as base_model

    import xrpl_lab.transport.xrpl_testnet  # noqa: F401  (installs the shim)

    assert base_model.ABBREVIATIONS.get("ids") == "IDs"
