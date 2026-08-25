"""Wave-6 api-cli Stage C — F-35d7a78c.

CONFIG_NON_TESTNET is a static env-config refusal (XRPL_LAB_FAUCET_URL /
XRPL_LAB_RPC_URL). ensure_funded must NOT sleep through the 2/4/8s backoff
(~14s) when the faucet returns that code — name the env-var fix and stop.

Run in isolation:
    python -m pytest tests/test_w6_api_cli_config_non_testnet_no_retry.py -q
"""

from __future__ import annotations

import pytest
from rich.console import Console

from xrpl_lab.errors import LabException
from xrpl_lab.runtime import ensure_funded
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult


@pytest.mark.asyncio
async def test_ensure_funded_stops_immediately_on_config_non_testnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One CONFIG_NON_TESTNET attempt — zero sleeps, zero further faucet calls."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    class StubTransport:
        async def get_balance(self, addr: str) -> str:
            return "0"

        async def fund_from_faucet(self, addr: str) -> FundResult:
            calls["n"] += 1
            return FundResult(
                success=False,
                address=addr,
                balance="0",
                message=(
                    "Refusing to contact faucet: XRPL_LAB_FAUCET_URL points at "
                    "a 'mainnet' endpoint (https://evil.example/faucet). "
                    "Unset XRPL_LAB_FAUCET_URL to use the default testnet faucet."
                ),
                code="CONFIG_NON_TESTNET",
            )

    with pytest.raises(LabException) as excinfo:
        await ensure_funded(LabState(), StubTransport(), "rTestAddr", Console())

    assert calls["n"] == 1, (
        f"CONFIG_NON_TESTNET must not retry; expected 1 faucet call, got {calls['n']}"
    )
    assert sleeps == [], (
        f"CONFIG_NON_TESTNET must not sleep the 2/4/8s backoff; slept {sleeps}"
    )
    err = excinfo.value.error
    assert err.code == "CONFIG_NON_TESTNET"
    # Name the fix — at least one of the operator-overridable env vars.
    named = "XRPL_LAB_FAUCET_URL" in err.message or "XRPL_LAB_FAUCET_URL" in err.hint
    named = named or (
        "XRPL_LAB_RPC_URL" in err.message or "XRPL_LAB_RPC_URL" in err.hint
    )
    assert named, (
        f"CONFIG_NON_TESTNET must name XRPL_LAB_FAUCET_URL / XRPL_LAB_RPC_URL:\n"
        f"message={err.message!r}\nhint={err.hint!r}"
    )


@pytest.mark.asyncio
async def test_config_non_testnet_routes_through_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Producer→consumer: CONFIG_NON_TESTNET reaches _error_envelope with hint."""
    from xrpl_lab.api.runner_ws import _error_envelope

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
                message="Refusing: XRPL_LAB_RPC_URL points at mainnet.",
                code="CONFIG_NON_TESTNET",
            )

    with pytest.raises(LabException) as excinfo:
        await ensure_funded(LabState(), StubTransport(), "rTestAddr", Console())

    envelope = _error_envelope(excinfo.value)
    assert envelope["code"] == "CONFIG_NON_TESTNET"
    assert envelope["severity"] == "warning"
    assert envelope["message"]
    assert envelope["hint"]
    assert (
        "XRPL_LAB_FAUCET_URL" in envelope["message"]
        or "XRPL_LAB_FAUCET_URL" in envelope["hint"]
        or "XRPL_LAB_RPC_URL" in envelope["message"]
        or "XRPL_LAB_RPC_URL" in envelope["hint"]
    )
