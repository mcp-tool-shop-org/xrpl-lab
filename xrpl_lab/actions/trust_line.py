"""Trust line actions — set trust line, issue tokens, verify trust lines."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import SubmitResult, Transport, TrustLineInfo


async def set_trust_line(
    transport: Transport,
    wallet_seed: str,
    issuer: str,
    currency: str,
    limit: str,
) -> SubmitResult:
    """Set a trust line from the wallet holder to an issuer."""
    return await transport.submit_trust_set(
        wallet_seed=wallet_seed,
        issuer=issuer,
        currency=currency,
        limit=limit,
    )


async def issue_token(
    transport: Transport,
    issuer_seed: str,
    destination: str,
    currency: str,
    issuer_address: str,
    amount: str,
    memo: str = "",
) -> SubmitResult:
    """Issue tokens from an issuer to a destination (issued currency payment)."""
    return await transport.submit_issued_payment(
        wallet_seed=issuer_seed,
        destination=destination,
        currency=currency,
        issuer=issuer_address,
        amount=amount,
        memo=memo,
    )


async def remove_trust_line(
    transport: Transport,
    wallet_seed: str,
    issuer: str,
    currency: str,
) -> SubmitResult:
    """Remove a trust line by setting limit to 0 (balance must be 0)."""
    return await transport.submit_trust_set(
        wallet_seed=wallet_seed,
        issuer=issuer,
        currency=currency,
        limit="0",
    )


async def get_trust_lines(
    transport: Transport,
    address: str,
) -> list[TrustLineInfo]:
    """Get all trust lines for an address."""
    return await transport.get_trust_lines(address)


async def enable_clawback(
    transport: Transport,
    issuer_seed: str,
    issuer_address: str = "",
) -> SubmitResult:
    """Enable clawback on the issuer (AccountSet asfAllowTrustLineClawback).

    MUST be set on a fresh issuer BEFORE any tokens are issued — it cannot be
    enabled retroactively once balances are outstanding. ``issuer_address`` is
    forwarded for the dry-run transport's per-issuer flag state (the testnet
    path ignores it).
    """
    return await transport.submit_account_set_clawback(issuer_seed, issuer_address)


async def clawback_tokens(
    transport: Transport,
    issuer_seed: str,
    holder_address: str,
    currency: str,
    amount: str,
    issuer_address: str = "",
) -> SubmitResult:
    """Forcibly recall ``amount`` of ``currency`` from a holder (Clawback, XLS-39)."""
    return await transport.submit_clawback(
        issuer_seed, holder_address, currency, amount, issuer_address
    )


@dataclass
class TrustLineVerifyResult:
    """Result of verifying trust line state."""

    found: bool
    trust_line: TrustLineInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_trust_line(
    transport: Transport,
    address: str,
    currency: str,
    expected_issuer: str | None = None,
    expected_balance: str | None = None,
) -> TrustLineVerifyResult:
    """Verify a trust line exists and optionally check balance."""
    lines = await transport.get_trust_lines(address)
    checks: list[str] = []
    failures: list[str] = []

    # Find matching trust line
    match = None
    for tl in lines:
        if tl.currency == currency:
            if expected_issuer and tl.peer != expected_issuer:
                continue
            match = tl
            break

    if not match:
        failures.append(f"No trust line found for {currency}")
        return TrustLineVerifyResult(
            found=False, trust_line=None, checks=checks, failures=failures
        )

    checks.append(f"Trust line found: {currency}")
    checks.append(f"Issuer: {match.peer}")
    checks.append(f"Limit: {match.limit}")
    checks.append(f"Balance: {match.balance}")

    if expected_balance and match.balance != expected_balance:
        failures.append(
            f"Balance mismatch: expected {expected_balance}, got {match.balance}"
        )

    return TrustLineVerifyResult(
        found=True, trust_line=match, checks=checks, failures=failures
    )


@dataclass
class ClawbackVerifyResult:
    """Result of verifying a clawback debited the holder's balance exactly."""

    correct: bool
    before: str
    after: str
    expected_after: str
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.correct and len(self.failures) == 0


async def verify_clawback(
    transport: Transport,
    holder_address: str,
    currency: str,
    issuer: str,
    balance_before: str,
    clawed_amount: str,
) -> ClawbackVerifyResult:
    """Verify the holder's balance dropped by EXACTLY ``clawed_amount`` (Decimal-exact).

    Reads the holder's trust-line balance back from the ledger and compares it
    to ``balance_before - clawed_amount``. XRPL clamps a clawback to the
    holder's balance, so the expected floor is 0.
    """
    from decimal import Decimal

    checks: list[str] = []
    failures: list[str] = []

    lines = await transport.get_trust_lines(holder_address)
    match = None
    for tl in lines:
        if tl.currency == currency and (not issuer or tl.peer == issuer):
            match = tl
            break

    after = match.balance if match else "0"
    try:
        before_d = Decimal(balance_before)
        clawed_d = Decimal(clawed_amount)
        after_d = Decimal(after)
    except Exception:
        failures.append("Non-numeric balance — cannot verify clawback math")
        return ClawbackVerifyResult(
            False, balance_before, after, balance_before, checks, failures
        )

    # XRPL clamps a clawback to what the holder actually holds.
    expected_after = before_d - clawed_d
    if expected_after < 0:
        expected_after = Decimal("0")

    checks.append(f"Balance before clawback: {balance_before} {currency}")
    checks.append(f"Clawed back: {clawed_amount} {currency}")
    checks.append(f"Balance after: {after} {currency}")

    if after_d == expected_after:
        checks.append(
            f"Holder balance dropped by exactly {clawed_amount} {currency} — "
            "issuer recall confirmed on-ledger"
        )
        correct = True
    else:
        failures.append(
            f"Clawback math mismatch: expected {expected_after} {currency} "
            f"after, got {after} {currency}"
        )
        correct = False

    return ClawbackVerifyResult(
        correct, balance_before, after, str(expected_after), checks, failures
    )


async def verify_trust_line_removed(
    transport: Transport,
    address: str,
    currency: str,
    expected_issuer: str | None = None,
) -> TrustLineVerifyResult:
    """Verify a trust line has been removed (no longer present)."""
    lines = await transport.get_trust_lines(address)
    checks: list[str] = []
    failures: list[str] = []

    for tl in lines:
        if tl.currency == currency:
            if expected_issuer and tl.peer != expected_issuer:
                continue
            # Trust line still exists
            failures.append(
                f"Trust line for {currency} still present "
                f"(balance: {tl.balance}, limit: {tl.limit})"
            )
            return TrustLineVerifyResult(
                found=True, trust_line=tl, checks=checks, failures=failures
            )

    checks.append(f"Trust line for {currency} successfully removed")
    return TrustLineVerifyResult(
        found=False, trust_line=None, checks=checks, failures=failures
    )
