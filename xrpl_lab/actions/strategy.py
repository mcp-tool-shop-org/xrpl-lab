"""Strategy actions — position snapshots, offer management, run tracking."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ..transport.base import AccountSnapshot, OfferInfo, Transport, TrustLineInfo

# ── Memo convention ──────────────────────────────────────────────────

MEMO_PREFIX = "XRPLLAB|STRAT|"


def strategy_memo(module: str, action: str, run_id: str = "") -> str:
    """Build a strategy memo string."""
    rid = run_id or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return f"{MEMO_PREFIX}{module}|{action}|{rid}"


# ── Position snapshot ────────────────────────────────────────────────


@dataclass
class PositionSnapshot:
    """Extended account snapshot including trust lines and offers."""

    timestamp: float
    account: AccountSnapshot
    trust_lines: list[TrustLineInfo]
    offers: list[OfferInfo]
    xrp_balance: str = "0"
    owner_count: int = 0
    offer_count: int = 0

    @property
    def spendable_estimate_drops(self) -> int:
        """Estimate spendable XRP (balance - reserves)."""
        base_reserve = 10_000_000  # 10 XRP in drops
        owner_reserve = 2_000_000  # 2 XRP per object
        balance = int(self.account.balance_drops)
        reserved = base_reserve + (self.owner_count * owner_reserve)
        return max(0, balance - reserved)


async def snapshot_position(
    transport: Transport,
    address: str,
) -> PositionSnapshot:
    """Take an extended position snapshot."""
    account = await transport.get_account_info(address)
    trust_lines = await transport.get_trust_lines(address)
    offers = await transport.get_account_offers(address)

    return PositionSnapshot(
        timestamp=time.time(),
        account=account,
        trust_lines=trust_lines,
        offers=offers,
        xrp_balance=account.balance_drops,
        owner_count=account.owner_count,
        offer_count=len(offers),
    )


@dataclass
class PositionComparison:
    """Result of comparing two position snapshots."""

    before: PositionSnapshot
    after: PositionSnapshot
    owner_count_delta: int
    offer_count_delta: int
    checks: list[str]
    explanation: str

    @property
    def clean(self) -> bool:
        """True if no leftover objects from the strategy."""
        return self.owner_count_delta == 0


def compare_positions(
    before: PositionSnapshot,
    after: PositionSnapshot,
    label: str = "",
) -> PositionComparison:
    """Compare two position snapshots."""
    owner_delta = after.owner_count - before.owner_count
    offer_delta = after.offer_count - before.offer_count

    checks: list[str] = []
    parts: list[str] = []

    # Owner count
    if owner_delta > 0:
        checks.append(
            f"Owner count increased: {before.owner_count} -> "
            f"{after.owner_count} (+{owner_delta})"
        )
        parts.append(f"owner count +{owner_delta}")
    elif owner_delta < 0:
        checks.append(
            f"Owner count decreased: {before.owner_count} -> "
            f"{after.owner_count} ({owner_delta})"
        )
        parts.append(f"owner count {owner_delta}")
    else:
        checks.append(f"Owner count unchanged: {after.owner_count}")

    # Offers
    if offer_delta > 0:
        checks.append(f"Open offers increased: +{offer_delta}")
    elif offer_delta < 0:
        checks.append(f"Open offers decreased: {offer_delta}")
    else:
        checks.append(f"Open offers unchanged: {after.offer_count}")

    prefix = f"After {label}: " if label else ""
    explanation = (
        prefix + "; ".join(parts) + "." if parts
        else prefix + "no significant changes."
    )

    return PositionComparison(
        before=before,
        after=after,
        owner_count_delta=owner_delta,
        offer_count_delta=offer_delta,
        checks=checks,
        explanation=explanation,
    )


# ── Strategy cleanup ─────────────────────────────────────────────────


async def cancel_module_offers(
    transport: Transport,
    wallet_seed: str,
    offer_sequences: list[int],
) -> list[tuple[int, bool]]:
    """Cancel all offers by sequence. Returns [(seq, success), ...]."""
    results = []
    for seq in offer_sequences:
        result = await transport.submit_offer_cancel(wallet_seed, seq)
        results.append((seq, result.success))
    return results


@dataclass
class HygieneSummary:
    """End-of-module hygiene report."""

    offers_remaining: int
    trust_lines_created: int
    owner_count_delta: int
    checks: list[str]

    @property
    def clean(self) -> bool:
        return self.offers_remaining == 0 and self.owner_count_delta <= 0


def hygiene_summary(
    baseline: PositionSnapshot,
    final: PositionSnapshot,
    offers_cancelled: int = 0,
) -> HygieneSummary:
    """Generate end-of-module hygiene summary."""
    owner_delta = final.owner_count - baseline.owner_count
    checks: list[str] = []

    if final.offer_count == 0:
        checks.append("No open offers remaining")
    else:
        checks.append(f"Warning: {final.offer_count} offers still open")

    if owner_delta == 0:
        checks.append("Owner count returned to baseline")
    elif owner_delta > 0:
        checks.append(
            f"Owner count +{owner_delta} vs baseline "
            f"(trust lines or positions still active)"
        )
    else:
        checks.append(f"Owner count {owner_delta} vs baseline")

    if offers_cancelled > 0:
        checks.append(f"Offers cancelled during cleanup: {offers_cancelled}")

    return HygieneSummary(
        offers_remaining=final.offer_count,
        trust_lines_created=max(
            0, len(final.trust_lines) - len(baseline.trust_lines)
        ),
        owner_count_delta=owner_delta,
        checks=checks,
    )


# ── Last run tracking ────────────────────────────────────────────────


def write_last_run(
    txids: list[str],
    module_id: str,
    run_id: str = "",
    preset: str = "",
    endpoint: str = "",
    workspace: Path | None = None,
) -> Path:
    """Write last_run_txids.txt and last_run_meta.json."""
    ws = workspace or Path(".xrpl-lab")
    ws.mkdir(parents=True, exist_ok=True)

    # txids file
    txids_path = ws / "last_run_txids.txt"
    txids_path.write_text(
        "\n".join(txids) + "\n", encoding="utf-8"
    )

    # meta file
    meta = {
        "module": module_id,
        "run_id": run_id or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        ),
        "preset": preset,
        "endpoint": endpoint,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "txid_count": len(txids),
    }
    meta_path = ws / "last_run_meta.json"
    meta_path.write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    return txids_path
