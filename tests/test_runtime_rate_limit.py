"""F-BRIDGE-PH8-001 — runtime-delivery pin for FAUCET_RATE_LIMITED.

Pattern #3 (sharpened): when a wave introduces a structured field, error
code, or response envelope element, the test must exercise the
end-to-end producer→consumer path — not just verify the field exists at
one layer.

This module pins the `RUNTIME_FAUCET_RATE_LIMITED` runtime path:

    transport.fund_from_faucet (sets FundResult.code)
        → runtime.ensure_funded (raises LabException(faucet_rate_limited()))
            → api.runner_ws._error_envelope (formats {code, message,
              hint, severity=warning, icon_hint=clock})

The Stage C P2 hot-fix proved that humanized prose only ships if BOTH
the source-pin (transport) and runtime-pin (caller) are in place. The
sibling test in `test_envelope_pedagogy.py` covers the source-pin
(transport tags FundResult.code on 429). This file covers the
runtime-pin: ensure_funded actually raises a LabException so the
envelope surface receives the structured code rather than just discarding
it.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ensure_funded_raises_lab_exception_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ensure_funded must raise LabException(faucet_rate_limited()) when
    the transport's final FundResult is tagged with the rate-limit code.

    Generic failures (no code set) still return False — preserved by
    the existing test_runner.py:test_returns_false_after_all_retries_exhausted
    pin. This test covers the new structured-code branch.
    """
    from xrpl_lab.errors import LabException
    from xrpl_lab.runtime import ensure_funded
    from xrpl_lab.state import LabState
    from xrpl_lab.transport.base import FundResult

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
                message="Faucet rate-limited (HTTP 429). ...",
                code="RUNTIME_FAUCET_RATE_LIMITED",
            )

    from rich.console import Console as _Console

    with pytest.raises(LabException) as excinfo:
        await ensure_funded(
            LabState(), StubTransport(), "rTestAddr", _Console(),
        )
    assert excinfo.value.error.code == "RUNTIME_FAUCET_RATE_LIMITED"
    assert excinfo.value.error.retryable is True


@pytest.mark.asyncio
async def test_envelope_routing_end_to_end_from_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end producer→consumer pin: faucet 429 propagates through
    runtime → API contract surface with the right severity/icon_hint.

    This is the sharpened pattern #3 contract: NOT just "FundResult.code
    contains the right string" (the source-pin), and NOT just "envelope
    maps the code to severity=warning" (the consumer-pin). It chains
    them together: the runtime layer in between must hand the code over
    to the consumer instead of swallowing it.
    """
    from xrpl_lab.api.runner_ws import _error_envelope
    from xrpl_lab.errors import LabException
    from xrpl_lab.runtime import ensure_funded
    from xrpl_lab.state import LabState
    from xrpl_lab.transport.base import FundResult

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

    class StubTransport:
        """Mirrors what xrpl_testnet.fund_from_faucet does on a real 429:
        returns FundResult(success=False, code='RUNTIME_FAUCET_RATE_LIMITED').
        """

        async def get_balance(self, addr: str) -> str:
            return "0"

        async def fund_from_faucet(self, addr: str) -> FundResult:
            return FundResult(
                success=False,
                address=addr,
                balance="0",
                message=(
                    "Faucet rate-limited (HTTP 429). The XRPL testnet "
                    "faucet caps funding requests per client to prevent "
                    "abuse and keep test XRP available for everyone. "
                    "Wait at least 60 seconds before retrying, or use "
                    "--dry-run to practice this module offline without "
                    "needing a funded testnet wallet."
                ),
                code="RUNTIME_FAUCET_RATE_LIMITED",
            )

    from rich.console import Console as _Console

    # Step 1: trigger the producer→runtime hand-off.
    captured: LabException | None = None
    try:
        await ensure_funded(
            LabState(), StubTransport(), "rTestAddr", _Console(),
        )
    except LabException as exc:
        captured = exc

    assert captured is not None, (
        "ensure_funded must raise LabException on faucet rate-limit "
        "instead of returning False — otherwise the structured code "
        "never reaches the API contract surface."
    )

    # Step 2: route the captured exception through _error_envelope and
    # assert the consumer-side contract. This is the leg that closes
    # the loop: not just that the code string survives, but that the
    # dashboard receives the right severity + icon_hint mapping derived
    # from it.
    envelope = _error_envelope(captured)
    assert envelope["code"] == "RUNTIME_FAUCET_RATE_LIMITED"
    assert envelope["severity"] == "warning"
    assert envelope["icon_hint"] == "clock"
    # Humanized hint stays — the rate-limit message must teach WHY
    # (abuse prevention) and the fallback (--dry-run).
    assert "--dry-run" in envelope["hint"]
    assert "60 seconds" in envelope["hint"]


@pytest.mark.asyncio
async def test_ensure_funded_returns_false_for_non_rate_limit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-rate-limit faucet failures (timeout, faucet down, generic HTTP
    error — any FundResult without code='RUNTIME_FAUCET_RATE_LIMITED')
    keep returning False. Preserves the existing learner-facing fallback
    flow and the test_runner.py:TestEnsureFundedRetry contract.
    """
    from xrpl_lab.runtime import ensure_funded
    from xrpl_lab.state import LabState
    from xrpl_lab.transport.base import FundResult

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
                message="faucet timed out",
                # No code — generic failure, not a rate-limit.
            )

    from rich.console import Console as _Console

    ok = await ensure_funded(
        LabState(), StubTransport(), "rTestAddr", _Console(),
    )
    assert ok is False
