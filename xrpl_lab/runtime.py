"""Shared runtime utilities used by both runner and handlers."""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rich.console import Console

from .actions.wallet import (
    create_wallet,
    default_wallet_path,
    load_wallet,
    save_wallet,
    wallet_exists,
)
from .errors import LabException, faucet_rate_limited
from .state import LabState, save_state
from .transport.base import Transport


class _SecretValue:
    """Wrapper that hides secret values from repr/str to prevent traceback leaks."""

    def __init__(self, value: str):
        self._value = value

    def get(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "***"

    def __str__(self) -> str:
        return "***"

    def __bool__(self) -> bool:
        return bool(self._value)

    def __reduce__(self):
        raise TypeError("Cannot pickle _SecretValue")


async def ensure_wallet(
    state: LabState,
    transport: Transport,
    console: Console,
) -> tuple[LabState, _SecretValue]:
    """Make sure we have a wallet; return (state, wrapped_seed)."""
    wallet_path = Path(state.wallet_path) if state.wallet_path else None

    if wallet_path and wallet_exists(wallet_path):
        wallet = load_wallet(wallet_path)
        if wallet:
            console.print(f"  Wallet loaded: [cyan]{wallet.address}[/]")
            return state, _SecretValue(wallet.seed)
    elif wallet_exists():
        wallet = load_wallet()
        if wallet:
            console.print(f"  Wallet loaded: [cyan]{wallet.address}[/]")
            state.wallet_address = wallet.address
            state.wallet_path = str(default_wallet_path())
            save_state(state)
            return state, _SecretValue(wallet.seed)

    console.print("  No wallet found. Creating a new one...")
    wallet = create_wallet()
    path = save_wallet(wallet)
    console.print(f"  Wallet created: [cyan]{wallet.address}[/]")
    console.print(f"  Saved to: [dim]{path}[/]")
    console.print()
    console.print(
        "[yellow]  Warning: Your wallet seed is stored locally. "
        "Never share it or paste it anywhere.[/]"
    )

    state.wallet_address = wallet.address
    state.wallet_path = str(path)
    save_state(state)
    return state, _SecretValue(wallet.seed)


# F-BACKEND-B-010: testnet faucet is rate-limited (~1 req/sec/IP) and
# routinely flakes under load. The previous one-shot call left learners
# at "ensure_wallet succeeded but I am unfunded" mid-module. Retry the
# fund call with explicit, in-band exponential backoff (no decorator,
# no retry library — keep the shape obvious so this code doesn't grow
# into a generic harness over time).
_FAUCET_RETRY_DELAYS_S: tuple[float, ...] = (2.0, 4.0, 8.0)


async def ensure_funded(
    state: LabState,
    transport: Transport,
    address: str,
    console: Console,
) -> bool:
    """Check balance and fund from faucet if needed. Returns True if funded.

    F-BACKEND-B-010: faucet calls now retry up to 3 times with 2/4/8s
    backoff on failure. The retry covers transient testnet-faucet
    overload; on a truly hard failure (e.g. faucet dead, address
    blocklisted) the same diagnostic message surfaces but only after
    the learner has gotten the benefit of a real retry window.
    """
    balance = await transport.get_balance(address)
    try:
        bal = Decimal(balance) if balance else Decimal("0")
    except (ValueError, TypeError, InvalidOperation):
        bal = Decimal("0")
    if bal > 0:
        console.print(f"  Balance: [green]{balance} XRP[/]")
        return True

    console.print("  Requesting funds from testnet faucet...")
    last_result = None
    for attempt, delay in enumerate(_FAUCET_RETRY_DELAYS_S, start=1):
        result = await transport.fund_from_faucet(address)
        last_result = result
        try:
            funded_bal = Decimal(result.balance) if result.balance else Decimal("0")
        except (ValueError, TypeError, InvalidOperation):
            funded_bal = Decimal("0")
        if result.success and funded_bal > 0:
            console.print(f"  Funded! Balance: [green]{result.balance} XRP[/]")
            return True
        # Final attempt — fall through without further sleeping.
        if attempt >= len(_FAUCET_RETRY_DELAYS_S):
            break
        console.print(
            f"  [yellow]Faucet attempt {attempt}/"
            f"{len(_FAUCET_RETRY_DELAYS_S)} did not fund. "
            f"Retrying in {delay:g}s...[/]"
        )
        await asyncio.sleep(delay)

    # F-BRIDGE-PH8-001: when the faucet's final failure is a 429, the
    # transport tags ``FundResult.code`` with RUNTIME_FAUCET_RATE_LIMITED.
    # Raise a structured LabException so the WS ``_error_envelope``
    # surfaces severity=warning + icon_hint=clock to the dashboard
    # (distinct treatment from generic RUNTIME_NETWORK faults). This wires
    # the producer→consumer path end-to-end: transport sets the code,
    # runtime hands it to the API contract surface, dashboard routes UI.
    # Generic failures (faucet down, timeout, non-429 HTTP error) still
    # return False so existing learner-facing flows keep working.
    if (
        last_result is not None
        and getattr(last_result, "code", "") == "RUNTIME_FAUCET_RATE_LIMITED"
    ):
        raise LabException(faucet_rate_limited())

    console.print(
        "[red]Faucet funding failed after retries.[/] "
        "The testnet faucet may be under load."
    )
    if last_result is not None and getattr(last_result, "message", ""):
        console.print(f"  Last response: {last_result.message}")
    console.print(
        "Try: [cyan]xrpl-lab fund[/] manually, or wait a few minutes and retry."
    )
    return False
