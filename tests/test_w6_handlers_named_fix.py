"""Wave-6 handlers Stage C — SEED-C-named-fix.

Where handlers.py prints a structured LabError / LabException failure, the
learner must see **code + what to do next** (hint), not a yellow/red blob of
message-only prose.

Stage A/B already raise ``STATE_MISSING_NOOPT_ISSUER`` (and siblings) with
hints; the runner renders those on the raise path. This seed targets the
sites handlers.py itself **prints**: every ``faucet_rate_limited()`` branch
must surface ``RUNTIME_FAUCET_RATE_LIMITED`` plus the wait/--dry-run hint.

Call-site enumeration covers raise LabException sites (justified: runner
renders) and every faucet print site (fixed).
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers_mod
from xrpl_lab.errors import LabException, faucet_rate_limited
from xrpl_lab.modules import ModuleStep
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult

HANDLERS_PATH = Path(handlers_mod.__file__).resolve()

# Every handler that prints faucet_rate_limited() on the 429 path.
_RATE_LIMIT_HANDLERS: list[tuple[str, dict]] = [
    ("handle_fund_issuer", {"issuer_address": "rIssuerAddrForFund"}),
    ("handle_create_channel_receiver", {}),
    (
        "handle_create_token_recipient",
        {"issuer_address": "rIssuerAddrForRecipient"},
    ),
    ("handle_create_noopt_issuer", {}),
    ("handle_create_subject_wallet", {}),
    ("handle_create_uncredentialed_wallet", {}),
    ("handle_create_sender_wallet", {}),
    ("handle_create_player_wallet", {}),
    ("handle_create_noclaw_issuer", {}),
    ("handle_create_buyer_wallet", {}),
    ("handle_create_recipient_wallet", {}),
    ("handle_create_outsider_wallet", {}),
]


class _RateLimitedFundTransport:
    """fund_from_faucet always returns RUNTIME_FAUCET_RATE_LIMITED."""

    async def fund_from_faucet(self, addr: str) -> FundResult:
        return FundResult(
            success=False,
            address=addr,
            balance="0",
            message="Faucet rate-limited (HTTP 429).",
            code="RUNTIME_FAUCET_RATE_LIMITED",
        )

    async def submit_trust_set(self, **_kwargs) -> SubmitResult:
        return SubmitResult(
            success=True,
            txid="DRYRUN_TRUSTSET",
            result_code="tesSUCCESS",
        )

    async def submit_payment(self, **_kwargs) -> SubmitResult:
        return SubmitResult(
            success=True,
            txid="DRYRUN_PAY",
            result_code="tesSUCCESS",
        )

    async def submit_issued_payment(self, **_kwargs) -> SubmitResult:
        # create_noopt_issuer / create_noclaw_issuer continue past a 429.
        return SubmitResult(
            success=True,
            txid="DRYRUN_ISSUE",
            result_code="tesSUCCESS",
        )


def _assert_named_fix(printed: str, *, handler_name: str) -> None:
    """Code + actionable next step — not message-only yellow prose."""
    assert "RUNTIME_FAUCET_RATE_LIMITED" in printed, (
        f"{handler_name}: LabError code missing from console "
        f"(SEED-C-named-fix — learner must see the code):\n{printed}"
    )
    lower = printed.lower()
    assert "dry-run" in lower or "--dry-run" in lower, (
        f"{handler_name}: actionable hint missing (--dry-run / wait):\n{printed}"
    )
    assert "60" in printed or "wait" in lower, (
        f"{handler_name}: wait guidance missing from hint:\n{printed}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_name,base_context",
    _RATE_LIMIT_HANDLERS,
    ids=[h for h, _ in _RATE_LIMIT_HANDLERS],
)
async def test_faucet_rate_limit_print_names_code_and_fix(
    handler_name: str,
    base_context: dict,
) -> None:
    """Each faucet_rate_limited print site must show code + what to do next."""
    handler = getattr(handlers_mod, handler_name)
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    step = ModuleStep(
        text="",
        action=handler_name.removeprefix("handle_"),
        action_args={},
    )
    state = LabState(network="dry-run", wallet_address="rLearner")
    context = {"wallet_seed": _SecretValue("sSEED"), **base_context}

    await handler(step, state, _RateLimitedFundTransport(), "sSEED", context, console)
    _assert_named_fix(buf.getvalue(), handler_name=handler_name)


def test_source_gate_faucet_prints_use_named_fix_helper() -> None:
    """AST gate: every faucet_rate_limited() site must print via helper that
    includes the code — bare ``err.message``-only prints fail this gate."""
    src = HANDLERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    helper_names = {"_print_lab_error", "_print_lab_exception"}

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.sites: list[int] = []

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "faucet_rate_limited":
                self.sites.append(node.lineno)
            self.generic_visit(node)

    v = _Visitor()
    v.visit(tree)
    assert v.sites, "expected faucet_rate_limited() call sites in handlers.py"

    offenders: list[str] = []
    for ln in v.sites:
        window = "\n".join(lines[ln - 1 : ln + 12])
        uses_helper = any(h in window for h in helper_names)
        if not uses_helper:
            offenders.append(
                f"L{ln}: faucet_rate_limited() without _print_lab_error in nearby lines:\n"
                f"{window}"
            )

    assert not offenders, (
        "SEED-C-named-fix: faucet LabError prints must go through "
        "_print_lab_error (code + message + hint):\n\n" + "\n---\n".join(offenders)
    )


def test_raise_labexception_sites_carry_actionable_hint() -> None:
    """Every raise LabException(LabError(...)) in handlers.py has a non-empty hint
    that names a next step. Raise-only sites are rendered by runner.py."""
    src = HANDLERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    class _RaiseVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.problems: list[str] = []
            self.codes: list[tuple[int, str]] = []

        def visit_Raise(self, node: ast.Raise) -> None:
            exc = node.exc
            if not isinstance(exc, ast.Call):
                return
            func = exc.func
            if not (isinstance(func, ast.Name) and func.id == "LabException"):
                return
            if not exc.args:
                self.problems.append(f"L{node.lineno}: LabException() with no LabError")
                return
            lab_err = exc.args[0]
            if not isinstance(lab_err, ast.Call):
                self.problems.append(
                    f"L{node.lineno}: LabException arg is not LabError(...)"
                )
                return
            kwargs = {
                kw.arg: kw.value
                for kw in lab_err.keywords
                if kw.arg is not None
            }
            code_node = kwargs.get("code")
            hint_node = kwargs.get("hint")
            code = ""
            if isinstance(code_node, ast.Constant) and isinstance(code_node.value, str):
                code = code_node.value
            self.codes.append((node.lineno, code or "?"))

            hint_ok = False
            if isinstance(hint_node, ast.Constant) and isinstance(hint_node.value, str):
                hint_ok = bool(hint_node.value.strip())
            elif isinstance(hint_node, (ast.JoinedStr, ast.Name)):
                hint_ok = True
            if not hint_ok:
                self.problems.append(
                    f"L{node.lineno} code={code!r}: LabException missing actionable hint"
                )
            self.generic_visit(node)

    visitor = _RaiseVisitor()
    visitor.visit(tree)
    assert visitor.codes, "expected raise LabException sites in handlers.py"
    assert not visitor.problems, "\n".join(visitor.problems)
    raised_codes = {c for _, c in visitor.codes}
    assert "STATE_MISSING_NOOPT_ISSUER" in raised_codes, (
        f"STATE_MISSING_NOOPT_ISSUER raise missing; found {sorted(raised_codes)}"
    )


@pytest.mark.asyncio
async def test_state_missing_noopt_issuer_names_the_fix() -> None:
    """STATE_MISSING_NOOPT_ISSUER LabError must name create_noopt_issuer in hint."""
    from xrpl_lab.transport.dry_run import DryRunTransport

    console = Console(file=io.StringIO(), no_color=True, width=200)
    state = LabState(network="dry-run", wallet_address="rLearner")
    step = ModuleStep(
        text="",
        action="create_token_escrow_expect_fail",
        action_args={"currency": "NOP"},
    )
    context = {"issuer_address": "rMainIssuerOptedIn"}
    with pytest.raises(LabException) as exc_info:
        await handlers_mod.handle_create_token_escrow_expect_fail(
            step,
            state,
            DryRunTransport(),
            "sSEED",
            context,
            console,
        )
    err = exc_info.value.error
    assert err.code == "STATE_MISSING_NOOPT_ISSUER"
    assert err.hint.strip(), "hint must name the fix"
    assert "create_noopt_issuer" in err.hint
    ref = faucet_rate_limited()
    assert ref.code and ref.hint
