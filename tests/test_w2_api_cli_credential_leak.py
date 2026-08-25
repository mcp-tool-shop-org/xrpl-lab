"""Wave-2 api-cli AMEND regression — F-9f0aa836 (CRITICAL).

``ensure_funded()`` printed ``transport.FundResult.message`` verbatim to
console with zero sanitization (``xrpl_lab/runtime.py:184``, guarded only
by ``if last_result is not None and getattr(last_result, "message", "")``).

``transport/xrpl_testnet.py:785-795`` (NOT owned by this domain — read only
for call-boundary context) builds exactly this message on its
``CONFIG_NON_TESTNET`` branch by embedding the RAW, operator-configured
``XRPL_LAB_FAUCET_URL`` verbatim — including any basic-auth userinfo or
query-string token the operator's override happens to carry. That string
flows straight through ``runtime.ensure_funded`` to ``console.print()``,
and in a WS-driven run that ``console`` is the ``capture_console`` whose
``_QueueFile.write()`` forwards every line to any attached WS client
(``xrpl_lab/api/runner_ws.py``) — so the credential could reach a remote
observer who merely knows a run_id (``GET /api/runs`` lists all of them).

Fixed by routing the message through the SAME
``xrpl_lab.reporting.sanitize_endpoint()`` already trusted for the
identical threat class on the proof-pack/doctor/feedback surfaces
(RA-002/F-60b2df48, CHANGELOG v2.4.0) — per the wave-2 advisor contract,
NOT a second/independent redactor.

Run in isolation:
    python -m pytest tests/test_w2_api_cli_credential_leak.py -q
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from xrpl_lab.runtime import ensure_funded
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult

# Mirrors the shape of transport/xrpl_testnet.py's CONFIG_NON_TESTNET
# message: a raw, operator-configured endpoint URL with BOTH a basic-auth
# userinfo component AND a query-string token, embedded verbatim.
CREDENTIAL_FAUCET_URL = (
    "https://facilitator:hunter2@evil-mainnet.example.com:8443"
    "/fund?token=SUPERSECRETTOKEN"
)


@pytest.mark.asyncio
async def test_ensure_funded_does_not_leak_credential_bearing_faucet_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential-bearing ``FundResult.message`` must never reach
    ``console.print()`` unsanitized. Neither the userinfo
    (``facilitator:hunter2``) nor the query-string token
    (``SUPERSECRETTOKEN``) may appear in the printed output; the bare host
    is allowed to survive (it is diagnostic, not a secret) — this is
    sanitization, not silence, mirroring how sanitize_endpoint() already
    treats every other endpoint value in this codebase.
    """

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

    class StubTransport:
        """Mirrors transport.xrpl_testnet.fund_from_faucet's
        CONFIG_NON_TESTNET branch: FundResult carrying the raw,
        operator-configured faucet URL embedded in .message."""

        async def get_balance(self, addr: str) -> str:
            return "0"

        async def fund_from_faucet(self, addr: str) -> FundResult:
            return FundResult(
                success=False,
                address=addr,
                balance="0",
                message=(
                    "Refusing to contact faucet: XRPL_LAB_FAUCET_URL points "
                    f"at a 'mainnet' endpoint ({CREDENTIAL_FAUCET_URL}). "
                    "XRPL Lab is testnet-only. Unset XRPL_LAB_FAUCET_URL to "
                    "use the default testnet faucet, or run with --dry-run."
                ),
                code="CONFIG_NON_TESTNET",
            )

    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)

    ok = await ensure_funded(LabState(), StubTransport(), "rTestAddr", console)

    assert ok is False
    printed = buf.getvalue()
    assert "hunter2" not in printed, (
        f"faucet basic-auth password leaked into console output:\n{printed}"
    )
    assert "facilitator:hunter2" not in printed, (
        f"faucet basic-auth userinfo leaked into console output:\n{printed}"
    )
    assert "SUPERSECRETTOKEN" not in printed, (
        f"faucet query-string token leaked into console output:\n{printed}"
    )
    # Sanitization, not silence: the host stays for diagnosability.
    assert "evil-mainnet.example.com" in printed, (
        f"sanitized output should still name the misconfigured host:\n{printed}"
    )


@pytest.mark.asyncio
async def test_ensure_funded_leaves_credential_free_message_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic, non-URL failure message (the common case — faucet down,
    timeout) must keep printing normally. The fix must not swallow
    ordinary diagnostic text that never had a URL in it."""

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

    class StubTransport:
        async def get_balance(self, addr: str) -> str:
            return "0"

        async def fund_from_faucet(self, addr: str) -> FundResult:
            return FundResult(
                success=False,
                address=addr,
                balance="0",
                message="faucet timed out after 10s",
            )

    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)

    ok = await ensure_funded(LabState(), StubTransport(), "rTestAddr", console)

    assert ok is False
    assert "faucet timed out after 10s" in buf.getvalue()
