"""Shared runtime utilities used by both runner and handlers."""

from __future__ import annotations

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


async def ensure_funded(
    state: LabState,
    transport: Transport,
    address: str,
    console: Console,
) -> bool:
    """Check balance and fund from faucet if needed. Returns True if funded."""
    balance = await transport.get_balance(address)
    try:
        bal = Decimal(balance) if balance else Decimal("0")
    except (ValueError, TypeError, InvalidOperation):
        bal = Decimal("0")
    if bal > 0:
        console.print(f"  Balance: [green]{balance} XRP[/]")
        return True

    console.print("  Requesting funds from testnet faucet...")
    result = await transport.fund_from_faucet(address)
    try:
        funded_bal = Decimal(result.balance) if result.balance else Decimal("0")
    except (ValueError, TypeError, InvalidOperation):
        funded_bal = Decimal("0")
    if result.success and funded_bal > 0:
        console.print(f"  Funded! Balance: [green]{result.balance} XRP[/]")
        return True
    else:
        console.print(
            "[red]Faucet funding failed.[/] The testnet faucet may be under load."
        )
        console.print(
            "Try: [cyan]xrpl-lab fund[/] manually, or wait a few minutes and retry."
        )
        return False
