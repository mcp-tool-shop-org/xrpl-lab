"""Wave-4 handlers AMEND — F-16917b8d (HIGH).

Stage A closed the WS/runtime FundResult.message leak (F-9f0aa836) but left
CLI stdout in handlers.py. Ten ``fund_from_faucet`` failure branches still
interpolate the raw ``.message`` (which can embed a credential-bearing
``XRPL_LAB_FAUCET_URL``) into ``console.print``.

Contract: every site sanitizes via ``sanitize_endpoint`` (thin wrap
``_sanitize_endpoint_urls`` is fine). Driving only ``handle_fund_issuer``
is a vacuous gate — this suite parametrizes ALL vulnerable print sites and
adds a source enumeration that fails if any remaining site still prints a
credentialed URL / raw ``.message`` without the redactor.

Run in isolation:
    python -m pytest tests/test_w4_handlers_fundresult_message.py -q --tb=short
"""

from __future__ import annotations

import ast
import io
import re
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers_mod
from xrpl_lab.modules import ModuleStep
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult

# Same shape as transport/xrpl_testnet.py CONFIG_NON_TESTNET + w2 runtime test.
CREDENTIAL_FAUCET_URL = (
    "https://facilitator:hunter2@evil-mainnet.example.com:8443"
    "/fund?token=SUPERSECRETTOKEN"
)
CREDENTIAL_MESSAGE = (
    "Refusing to contact faucet: XRPL_LAB_FAUCET_URL points "
    f"at a 'mainnet' endpoint ({CREDENTIAL_FAUCET_URL}). "
    "XRPL Lab is testnet-only. Unset XRPL_LAB_FAUCET_URL to "
    "use the default testnet faucet, or run with --dry-run."
)

HANDLERS_PATH = Path(handlers_mod.__file__).resolve()


class _FailingFundTransport:
    """Always returns a credential-bearing FundResult from fund_from_faucet."""

    async def fund_from_faucet(self, addr: str) -> FundResult:
        return FundResult(
            success=False,
            address=addr,
            balance="0",
            message=CREDENTIAL_MESSAGE,
            code="CONFIG_NON_TESTNET",
        )

    async def submit_trust_set(self, **_kwargs) -> SubmitResult:
        # handle_create_token_recipient continues to TrustSet after funding.
        return SubmitResult(
            success=True,
            txid="DRYRUN_TRUSTSET",
            result_code="tesSUCCESS",
        )


def _assert_no_credential_leak(printed: str, *, handler_name: str) -> None:
    assert "hunter2" not in printed, (
        f"{handler_name}: faucet basic-auth password leaked:\n{printed}"
    )
    assert "facilitator:hunter2" not in printed, (
        f"{handler_name}: faucet basic-auth userinfo leaked:\n{printed}"
    )
    assert "SUPERSECRETTOKEN" not in printed, (
        f"{handler_name}: faucet query-string token leaked:\n{printed}"
    )
    # Sanitization, not silence: host may remain for diagnosability.
    assert "evil-mainnet.example.com" in printed, (
        f"{handler_name}: sanitized output should still name the host:\n{printed}"
    )


# (handler attr, context factory) — every site that prints FundResult.message
# on the generic failure branch. Two other fund_from_faucet sites
# (create_noopt_issuer / create_noclaw_issuer) never print .message.
_VULNERABLE_HANDLERS: list[tuple[str, dict]] = [
    ("handle_fund_issuer", {"issuer_address": "rIssuerAddrForFund"}),
    ("handle_create_channel_receiver", {}),
    (
        "handle_create_token_recipient",
        {"issuer_address": "rIssuerAddrForRecipient"},
    ),
    ("handle_create_subject_wallet", {}),
    ("handle_create_uncredentialed_wallet", {}),
    ("handle_create_sender_wallet", {}),
    ("handle_create_player_wallet", {}),
    ("handle_create_buyer_wallet", {}),
    ("handle_create_recipient_wallet", {}),
    ("handle_create_outsider_wallet", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_name,base_context",
    _VULNERABLE_HANDLERS,
    ids=[h for h, _ in _VULNERABLE_HANDLERS],
)
async def test_fund_failure_message_does_not_leak_credential_url(
    handler_name: str,
    base_context: dict,
) -> None:
    """Each handlers.py FundResult.message print site must scrub credentials."""
    handler = getattr(handlers_mod, handler_name)
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    step = ModuleStep(text="", action=handler_name.removeprefix("handle_"), action_args={})
    state = LabState(network="dry-run", wallet_address="rLearner")
    ctx = dict(base_context)
    ctx.setdefault("wallet_seed", _SecretValue("snoSeedForStubOnly"))

    await handler(step, state, _FailingFundTransport(), "snoSeedForStubOnly", ctx, console)
    _assert_no_credential_leak(buf.getvalue(), handler_name=handler_name)


def test_every_fund_from_faucet_message_print_is_sanitized() -> None:
    """Source enumeration gate: any console.print that interpolates a
    FundResult-like ``.message`` after ``fund_from_faucet`` must route
    through the single redactor (sanitize_endpoint / _sanitize_endpoint_urls).

    Driving only handle_fund_issuer is vacuous — this walks the whole file.
    """
    source = HANDLERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect names assigned from fund_from_faucet awaits: result = await ...fund_from_faucet
    fund_result_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        # await transport.fund_from_faucet(...)
        if isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
            call = value.value
            func = call.func
            if isinstance(func, ast.Attribute) and func.attr == "fund_from_faucet":
                fund_result_names.add(target.id)

    assert fund_result_names, "expected to find fund_from_faucet assignments"

    # Find console.print(f"...{name.message}...") that do NOT wrap with sanitizer.
    unsanitized: list[tuple[int, str]] = []
    sanitize_re = re.compile(
        r"(?:_sanitize_endpoint_urls|sanitize_endpoint)\s*\("
    )
    # Rough but targeted: f-string / format that includes <fundname>.message
    print_msg_re = re.compile(
        r"console\.print\([^)]*\b("
        + "|".join(re.escape(n) for n in sorted(fund_result_names))
        + r")\.message\b[^)]*\)",
        re.MULTILINE,
    )

    for match in print_msg_re.finditer(source):
        snippet = match.group(0)
        line = source.count("\n", 0, match.start()) + 1
        if sanitize_re.search(snippet):
            continue
        unsanitized.append((line, snippet[:160]))

    assert not unsanitized, (
        "handlers.py still prints raw FundResult.message without "
        "sanitize_endpoint / _sanitize_endpoint_urls at:\n"
        + "\n".join(f"  L{ln}: {snip}" for ln, snip in unsanitized)
    )
