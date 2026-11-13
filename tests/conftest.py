"""Suite-wide fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# Before every reset listed in xrpl_lab.resets.KNOWN_RESETS.
BEFORE_ANY_KNOWN_RESET = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _pin_reset_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the clock the known-reset check reads.

    Live verification treats a missing transaction differently once a listed
    network reset has happened. Without a pinned clock, tests that expect
    "not found" to fail would change their result on the reset day. Tests of
    the reset behaviour set their own time over this one.
    """
    monkeypatch.setattr("xrpl_lab.resets._now", lambda: BEFORE_ANY_KNOWN_RESET)
