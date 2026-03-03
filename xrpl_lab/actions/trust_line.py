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


async def get_trust_lines(
    transport: Transport,
    address: str,
) -> list[TrustLineInfo]:
    """Get all trust lines for an address."""
    return await transport.get_trust_lines(address)


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

    if expected_issuer and match.peer != expected_issuer:
        failures.append(
            f"Issuer mismatch: expected {expected_issuer}, got {match.peer}"
        )

    if expected_balance and match.balance != expected_balance:
        failures.append(
            f"Balance mismatch: expected {expected_balance}, got {match.balance}"
        )

    return TrustLineVerifyResult(
        found=True, trust_line=match, checks=checks, failures=failures
    )
