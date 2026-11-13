"""Known resets of the public test networks.

A reset deletes every account, transaction and ledger object on a test network.
A proof pack issued before a reset still has an intact SHA-256, but its txids
no longer exist on any ledger. Live verification must not read that as a fake
txid, so it asks this module whether the network was reset after the pack's
transaction was recorded.

Two signals, either of which is enough:

1. **A known, announced reset** (``KNOWN_RESETS``). The announcement gives a
   date but no time or timezone, so a reset covers any transaction recorded
   before the reset day has ended everywhere (UTC-12), and is treated as
   having happened only once the day has begun everywhere (UTC+14). Until
   then a missing transaction is checked as before.
2. **The ledger went backwards.** Each run records the highest validated ledger
   index it saw (``LabState.ledger_marks``); the proof pack carries it. Ledger
   indexes only grow on a live network, so a current index well below the
   recorded one (more than server lag explains) means the network was reset
   after issuance, announced or not.

Neither signal is a pass. The verdict is "can't be checked on-ledger any more";
the offline hash is the remaining evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class KnownReset:
    """An announced reset of one network, on one day."""

    network: str
    day: date
    source: str

    @property
    def starts(self) -> datetime:
        """The earliest instant the reset day exists anywhere (UTC+14)."""
        return datetime.combine(self.day, time.min, tzinfo=UTC) - timedelta(hours=14)

    @property
    def ends(self) -> datetime:
        """The last instant the reset day exists anywhere (UTC-12)."""
        return datetime.combine(self.day + timedelta(days=1), time.min, tzinfo=UTC) + timedelta(
            hours=12
        )

    def label(self) -> str:
        return f"{self.network.capitalize()} was reset on {self.day.isoformat()}"


# The public networks whose transactions live verification re-checks, and so
# the ones whose ledger index a run records.
LIVE_CHECKED_NETWORKS = frozenset({"testnet", "devnet"})

_RESET_2026_11_25 ="https://xrpl.org/blog/2026/testnet-devnet-reset"

KNOWN_RESETS: tuple[KnownReset, ...] = (
    KnownReset("testnet", date(2026, 11, 25), _RESET_2026_11_25),
    KnownReset("devnet", date(2026, 11, 25), _RESET_2026_11_25),
)


def _now() -> datetime:
    """The current time. A seam: the test suite pins it, so results don't
    change on the day a listed reset happens."""
    return datetime.now(tz=UTC)


def known_reset_after(
    network: str,
    recorded_at: datetime | None,
    *,
    now: datetime | None = None,
    resets: tuple[KnownReset, ...] = KNOWN_RESETS,
) -> KnownReset | None:
    """The first announced reset of ``network`` after ``recorded_at``.

    Only a reset that has (possibly) already happened counts: before its day
    begins anywhere, a missing transaction is still a real failure. A
    transaction with no recorded time is covered by any reset that has
    happened, since nothing says it came later.
    """
    now = now or _now()
    for reset in sorted(resets, key=lambda r: r.day):
        if reset.network != network or now < reset.starts:
            continue
        if recorded_at is None or recorded_at < reset.ends:
            return reset
    return None


# Servers of one network can sit a few ledgers apart, so a slightly lower
# index is lag, not a reset. A ledger closes every 3 to 5 seconds: 1,000
# ledgers is about an hour, far more than any lag, and far less than the drop
# a reset causes (the index restarts near 1).
LEDGER_LAG_TOLERANCE = 1_000


def ledger_went_backwards(recorded_index: int | None, current_index: int | None) -> bool:
    """True when the network's validated ledger is well below an index seen before."""
    if not recorded_index or not current_index:
        return False
    return current_index < recorded_index - LEDGER_LAG_TOLERANCE


@dataclass(frozen=True)
class WipedWork:
    """Completed modules whose on-ledger results a reset of ``network`` erased."""

    network: str
    label: str          # "Testnet was reset on 2026-11-25" / "... was reset (seen ...)"
    source: str         # the announcement URL, or "" for a reset the lab saw itself
    since: datetime     # records before this instant are gone
    modules: tuple[str, ...]
    # True when nothing at all has been recorded on the network since the
    # reset: the wallet itself has not been funded again.
    nothing_since: bool


def _reset_point(network: str, state, now: datetime) -> tuple[datetime, str, str] | None:
    """When ``network`` was last reset, as far as this state can tell.

    A reset the lab saw itself (a ledger epoch) gives the moment it was seen.
    An announced reset gives only its day, so its last possible instant is
    used unless the lab also saw it, which is more precise.
    """
    epochs = sorted(state.ledger_epochs.get(network, []), key=lambda e: e.reset_seen_at)
    seen = [datetime.fromtimestamp(e.reset_seen_at, tz=UTC) for e in epochs]
    announced = [r for r in KNOWN_RESETS if r.network == network and now >= r.starts]
    latest = max(announced, key=lambda r: r.day, default=None)
    # A reset seen after the announced day is a later one, and the latest.
    if seen and (latest is None or seen[-1] > latest.ends):
        day = seen[-1].date().isoformat()
        return seen[-1], f"{network.capitalize()} was reset (seen on {day})", ""
    if latest is not None:
        on_the_day = [s for s in seen if s >= latest.starts]
        return (on_the_day[-1] if on_the_day else latest.ends), latest.label(), latest.source
    return None


def wiped_by_reset(state, *, now: datetime | None = None) -> list[WipedWork]:
    """The completed modules whose on-ledger results a network reset erased.

    A module counts as wiped when every transaction it has on the network was
    recorded before the reset. Re-running it (``run --force``) records new
    ones and clears it.
    """
    now = now or _now()
    completed = {m.module_id for m in state.completed_modules}
    found: list[WipedWork] = []
    for network in sorted(LIVE_CHECKED_NETWORKS):
        point = _reset_point(network, state, now)
        if point is None:
            continue
        since, label, source = point
        cutoff = since.timestamp()
        before: set[str] = set()
        after: set[str] = set()
        for tx in state.tx_index:
            if tx.network != network or tx.txid == "failed" or tx.validated is False:
                continue
            (before if tx.timestamp < cutoff else after).add(tx.module_id)
        wiped = tuple(sorted((before - after) & completed))
        if wiped:
            found.append(WipedWork(
                network=network, label=label, source=source, since=since,
                modules=wiped, nothing_since=not after,
            ))
    return found
