"""F-BRIDGE-A-007 — pin ``_safe_put``'s drop-oldest back-pressure policy.

``_safe_put`` is the single choke point through which every WS frame
(output, step, tx, complete, error) is enqueued onto a learner's
``ModuleRunSession.queue``. The queue is bounded (``_QUEUE_MAXSIZE``)
precisely so a stalled or slow WS consumer cannot drive unbounded
memory growth — that bound is the DoS / unbounded-growth defense
named in the threat model. When the queue is full, ``_safe_put`` drops
the OLDEST item and retries (the dashboard values freshness over
completeness) and logs a WARNING so a facilitator can see the policy
firing in the server logs.

These tests pin three load-bearing properties of that policy:

* **The bound holds** — ``qsize()`` never exceeds ``_QUEUE_MAXSIZE``,
  no matter how many items are pushed past capacity. This is the
  memory-safety invariant the whole mechanism exists for.
* **Drop-OLDEST, not drop-newest** — on overflow the eldest enqueued
  item is the one evicted, and the WARNING fires. A regression that
  flipped this to drop-newest would silently throw away the freshest
  dashboard state.
* **The terminal frame is never the victim** — critically, a
  ``{"type": "complete"}`` frame enqueued LAST survives an overflow.
  Because it is the newest item, drop-oldest must never evict it. This
  is the invariant that keeps the WS read loop's "stop on complete/
  error" contract intact under back-pressure: if overflow could swallow
  the terminal frame, a learner whose console spammed output would see
  the socket stall at 30s-ping keepalives forever instead of closing
  cleanly. The dashboard MUST always receive its terminal frame.

Mirrors the siloing discipline of the other Bridge-owned test modules:
this file owns the ``_safe_put`` back-pressure contract so it doesn't
collide with ``test_runner_ws.py`` / ``test_envelope_pedagogy.py``
ownership in future waves.
"""

from __future__ import annotations

import logging

import pytest

from xrpl_lab.api.runner_ws import (
    _QUEUE_MAXSIZE,
    ModuleRunSession,
    _safe_put,
)


def _make_session() -> ModuleRunSession:
    """Build a bare ModuleRunSession with a real bounded ``asyncio.Queue``.

    No task / transport — these tests exercise the synchronous
    ``_safe_put`` choke point against the session's default-factory
    queue (``asyncio.Queue(maxsize=_QUEUE_MAXSIZE)``) only.
    """
    return ModuleRunSession(
        run_id="bp-test-run",
        module_id="receipt_literacy",
        dry_run=True,
    )


@pytest.mark.asyncio
async def test_safe_put_drop_oldest_bounds_queue_and_preserves_terminal_frame(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fill the queue to capacity, push past it, and assert the policy.

    Asserts, in one cohesive scenario (the queue's lifetime is shared):

      1. ``qsize()`` stays ``<= _QUEUE_MAXSIZE`` after overflow — the
         memory-safety bound holds.
      2. The OLDEST item was evicted (drop-oldest, not drop-newest).
      3. The WARNING fired (caplog) so the policy is observable in
         server logs.
      4. CRITICALLY — a terminal ``{"type": "complete"}`` frame
         enqueued LAST survives the overflow, because drop-oldest never
         targets the newest item. This is the "overflow never drops the
         terminal frame" invariant.
    """
    session = _make_session()
    queue = session.queue

    # The asyncio.Queue is constructed with the module's bound; this is
    # the value the whole mechanism is protecting.
    assert queue.maxsize == _QUEUE_MAXSIZE

    # Fill EXACTLY to capacity with tagged, ordered items so we can prove
    # which one gets evicted. Item 0 is the oldest.
    for i in range(_QUEUE_MAXSIZE):
        _safe_put(queue, {"type": "output", "text": f"line-{i}"}, "bp-test-run")

    assert queue.qsize() == _QUEUE_MAXSIZE, "queue should be exactly full"

    # ── Overflow #1: a normal output frame. ───────────────────────────
    # This must evict the oldest item (line-0) and fire a WARNING.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="xrpl_lab.api.runner_ws"):
        _safe_put(queue, {"type": "output", "text": "line-overflow"}, "bp-test-run")

    # The bound holds — never exceeds maxsize.
    assert queue.qsize() <= _QUEUE_MAXSIZE
    assert queue.qsize() == _QUEUE_MAXSIZE

    # The WARNING fired and names the drop-oldest policy + run_id.
    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert warning_records, "drop-oldest overflow must log a WARNING"
    assert any(
        "dropped oldest" in r.getMessage() for r in warning_records
    ), "the WARNING must name the drop-oldest policy"
    assert any(
        "bp-test-run" in r.getMessage() for r in warning_records
    ), "the WARNING must carry the run_id for facilitator triage"

    # ── Overflow #2: the TERMINAL frame, enqueued LAST. ───────────────
    # This is the load-bearing case: a complete frame pushed when the
    # queue is full must itself survive (it is the newest) — drop-oldest
    # evicts the next-oldest item instead.
    _safe_put(queue, {"type": "complete", "success": True}, "bp-test-run")
    assert queue.qsize() <= _QUEUE_MAXSIZE

    # Drain the queue and inspect what survived.
    drained: list[dict] = []
    while not queue.empty():
        drained.append(queue.get_nowait())

    texts = [d.get("text") for d in drained if d.get("type") == "output"]

    # Drop-oldest: line-0 (the very first item) must be gone — it was the
    # eldest when the first overflow fired.
    assert "line-0" not in texts, (
        "drop-oldest must evict the OLDEST item (line-0), not a newer one"
    )

    # The most recent output frame pushed before the terminal frame
    # survived — proving we drop the OLD end, not the new end.
    assert "line-overflow" in texts, (
        "drop-newest regression: the freshest output frame was evicted"
    )

    # THE invariant: the terminal complete frame — enqueued LAST into a
    # full queue — is still present. Overflow must never swallow it.
    terminal = [d for d in drained if d.get("type") == "complete"]
    assert len(terminal) == 1, (
        "the terminal {'type': 'complete'} frame must survive overflow — "
        "it is the newest item, so drop-oldest must never evict it. If this "
        "fails, a learner whose console spammed output past _QUEUE_MAXSIZE "
        "would never receive the terminal frame and the WS read loop would "
        "stall on keepalive pings instead of closing cleanly."
    )
    assert terminal[0]["success"] is True
