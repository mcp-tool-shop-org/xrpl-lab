"""Shared runtime utilities used by both runner and handlers."""

from __future__ import annotations

import asyncio
import re
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
from .errors import LabError, LabException, faucet_rate_limited
from .reporting import sanitize_endpoint
from .state import LabState, save_state
from .transport.base import Transport


def _config_non_testnet_error(message: str = "") -> LabError:
    """Static faucet/RPC misconfiguration — name the env-var fix (F-35d7a78c)."""
    detail = (message or "").strip()
    return LabError(
        code="CONFIG_NON_TESTNET",
        message=(
            detail
            if detail
            else (
                "Faucet/RPC endpoint is not a safe testnet target "
                "(CONFIG_NON_TESTNET)."
            )
        ),
        hint=(
            "Unset XRPL_LAB_FAUCET_URL and/or XRPL_LAB_RPC_URL to restore the "
            "default testnet endpoints, or run with --dry-run offline."
        ),
    )


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
    elif wallet_path is not None:
        # F-1e8c93d7: state.wallet_path WAS set (pointing at a custom or
        # previously-recorded wallet location), but that file is gone
        # (moved/renamed home dir, partial backup restore, manual delete)
        # AND the default location has nothing either. Falling straight
        # through to wallet creation below would silently mint a brand new
        # address and overwrite state.wallet_address/wallet_path with no
        # signal that this differs from the previously recorded identity —
        # any funds already sent to the OLD address become invisible to
        # this tool, and completed_modules history keeps accruing under
        # the new, unrelated address. Name the old path + old address
        # before falling through so the learner has a chance to notice and
        # restore the original file instead.
        old_address = state.wallet_address
        console.print(
            f"  [yellow]Warning: your previously configured wallet at "
            f"{wallet_path} was not found"
            + (f" (previously {old_address})" if old_address else "")
            + ".[/]"
        )
        console.print(
            "  [yellow]If you still have that file, restore it to the "
            "path above before continuing. Otherwise, funds already sent "
            "to the old address will be orphaned from this tool's "
            "perspective — a NEW wallet/address will be created below.[/]"
        )

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

# F-9f0aa836: FundResult.message is operator-influenced prose that can
# embed a raw endpoint URL verbatim. transport/xrpl_testnet.py's
# CONFIG_NON_TESTNET branch (NOT owned by this module — see that file's
# fund_from_faucet(), ~line 785) formats the literal, operator-configured
# XRPL_LAB_FAUCET_URL into .message when it fails the network-safety
# check — and that override can carry basic-auth userinfo or a
# query-string token if the operator pointed it at a credential-protected
# endpoint. Rather than inventing a second redaction scheme, this reuses
# the SAME xrpl_lab.reporting.sanitize_endpoint() already trusted for the
# identical threat class on the proof-pack/doctor/feedback surfaces
# (RA-002/F-60b2df48, CHANGELOG v2.4.0) — per the wave-2 advisor contract.
#
# Unlike the WS output channel's generic, arbitrary-free-text redaction
# pass (api/runner_ws.py:_redact_output_text, which must preserve
# non-credential explorer/faucet CONTENT links byte-for-byte because their
# PATH is the entire point of printing them), THIS message never carries a
# legitimate path/query a learner needs to see — it only ever echoes a
# misconfigured ENDPOINT. So every URL-shaped span found here is reduced
# unconditionally to scheme://host[:port], exactly how audit.py/doctor.py/
# feedback.py already treat endpoint values — no conditional "does this
# look like a credential" heuristic is needed at this specific call site.
_URL_SPAN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"()<>]+")


def _sanitize_endpoint_urls(text: str) -> str:
    """Reduce every URL-shaped span in ``text`` via sanitize_endpoint().

    Used to scrub FundResult.message before it ever reaches console.print()
    — see the F-9f0aa836 note above ``_URL_SPAN_RE``.
    """
    if not text:
        return text
    return _URL_SPAN_RE.sub(lambda m: sanitize_endpoint(m.group(0)), text)


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
        # F-35d7a78c: CONFIG_NON_TESTNET is a pure function of static env
        # (XRPL_LAB_FAUCET_URL / XRPL_LAB_RPC_URL). Retrying burns ~14s for
        # zero chance of a different outcome — name the env-var fix and stop.
        # Sanitize BEFORE building LabError: the transport message can embed
        # a credential-bearing XRPL_LAB_FAUCET_URL (F-9f0aa836), and the
        # LabException flows into WS ``_error_envelope`` as well as console.
        if getattr(result, "code", "") == "CONFIG_NON_TESTNET":
            scrubbed = _sanitize_endpoint_urls(
                getattr(result, "message", "") or ""
            )
            err = _config_non_testnet_error(scrubbed)
            console.print(f"[red]{err.code}:[/] {err.message}")
            if err.hint:
                console.print(f"  [yellow]Hint:[/] {err.hint}")
            raise LabException(err)
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
        # F-9f0aa836: never interpolate the raw message — it may embed a
        # credential-bearing endpoint URL. See _sanitize_endpoint_urls above.
        console.print(f"  Last response: {_sanitize_endpoint_urls(last_result.message)}")
    console.print(
        "Try: [cyan]xrpl-lab fund[/] manually, or wait a few minutes and retry."
    )
    return False
