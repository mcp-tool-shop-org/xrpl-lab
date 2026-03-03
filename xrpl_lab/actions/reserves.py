"""Reserve actions — snapshot account state, compare reserve changes."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import AccountSnapshot, Transport

# XRP has 6 decimal places; 1 XRP = 1,000,000 drops
_DROPS_PER_XRP = 1_000_000


def _drops_to_xrp(drops: str) -> str:
    """Convert drops to XRP string with 6 decimal places."""
    try:
        return f"{int(drops) / _DROPS_PER_XRP:.6f}"
    except (ValueError, TypeError):
        return "0.000000"


async def snapshot_account(
    transport: Transport,
    address: str,
) -> AccountSnapshot:
    """Take a snapshot of account state."""
    return await transport.get_account_info(address)


@dataclass
class ReserveComparison:
    """Result of comparing two account snapshots."""

    before: AccountSnapshot
    after: AccountSnapshot
    balance_delta_drops: int
    owner_count_delta: int
    checks: list[str]
    explanation: str

    @property
    def owner_count_changed(self) -> bool:
        return self.owner_count_delta != 0


def compare_snapshots(
    before: AccountSnapshot,
    after: AccountSnapshot,
    label: str = "",
) -> ReserveComparison:
    """Compare two snapshots and explain what changed."""
    balance_delta = int(after.balance_drops) - int(before.balance_drops)
    owner_delta = after.owner_count - before.owner_count

    checks: list[str] = []
    parts: list[str] = []

    # Balance change
    if balance_delta != 0:
        direction = "decreased" if balance_delta < 0 else "increased"
        xrp_delta = abs(balance_delta) / _DROPS_PER_XRP
        checks.append(
            f"Balance {direction} by {xrp_delta:.6f} XRP "
            f"({abs(balance_delta)} drops)"
        )
        parts.append(
            f"balance {direction} by {xrp_delta:.6f} XRP"
        )
    else:
        checks.append("Balance unchanged")

    # Owner count change
    if owner_delta > 0:
        checks.append(
            f"Owner count increased: {before.owner_count} -> "
            f"{after.owner_count} (+{owner_delta})"
        )
        parts.append(
            f"owner count went from {before.owner_count} to "
            f"{after.owner_count} — each owned object (trust line, "
            f"offer, etc.) reserves additional XRP"
        )
    elif owner_delta < 0:
        checks.append(
            f"Owner count decreased: {before.owner_count} -> "
            f"{after.owner_count} ({owner_delta})"
        )
        parts.append(
            f"owner count dropped from {before.owner_count} to "
            f"{after.owner_count} — removing objects releases "
            f"reserve XRP back to spendable"
        )
    else:
        checks.append(
            f"Owner count unchanged: {after.owner_count}"
        )

    # Build explanation
    prefix = f"After {label}: " if label else ""

    if parts:
        explanation = prefix + "; ".join(parts) + "."
    else:
        explanation = prefix + "no significant changes detected."

    return ReserveComparison(
        before=before,
        after=after,
        balance_delta_drops=balance_delta,
        owner_count_delta=owner_delta,
        checks=checks,
        explanation=explanation,
    )
