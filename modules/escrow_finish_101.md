---
id: escrow_finish_101
title: "Escrow Finish 101: Releasing Locked XRP"
track: payments
kb_source: escrow-finish-permission-reserve
summary: Finish a time-based escrow to release the locked XRP and free your reserve — the other half of the escrow story.
order: 41
time: 15-20 min
level: intermediate
mode: testnet
requires:
  - escrow_101
produces:
  - txid
  - report
checks:
  - "Escrow created with a short FinishAfter (txid produced)"
  - "EscrowFinish submitted after FinishAfter (txid produced)"
  - "Escrow object gone from the ledger — funds released, owner reserve freed"
---

In **Escrow 101** you *locked* XRP with an `EscrowCreate`. That is only half the story: a created
escrow sits on the ledger holding your XRP **and your owner reserve** until someone releases it.
This module teaches the release path — `EscrowFinish` — so the lifecycle actually completes
instead of leaving funds locked forever.

A time-based escrow has two clocks:

- **`FinishAfter`** — the earliest time `EscrowFinish` can succeed (the release becomes possible).
- **`CancelAfter`** (optional, must be **later** than `FinishAfter`) — after this, anyone can
  `EscrowCancel` and the XRP returns to the **owner**. That is the reclaim path.

You'll create a short-`FinishAfter` escrow to yourself, wait for it to mature, finish it, and
verify the escrow object is gone (funds released, reserve freed). This runs on testnet — free and
disposable — and works identically in `--dry-run`, where the release time is simulated
deterministically so you never have to wait on a wall clock.

## Step 1: Ensure your wallet is ready

If you completed Escrow 101 your wallet loads automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

EscrowFinish costs a small fee. Creating the escrow also locks XRP plus an owner reserve for the
escrow object — both are returned when you finish it (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Snapshot A — before the escrow

Capture your account state so you can prove the reserve was freed at the end. Watch `owner_count`:
it goes up by 1 when the escrow exists, and back down when you finish it.

<!-- action: snapshot_account label=before_escrow -->

## Step 4: Create a short-FinishAfter escrow

Lock XRP to yourself with a `FinishAfter` only a few seconds out. (Escrow-to-self keeps the lesson
simple: you are both the owner and the destination, so the released funds land back in your own
balance.) The create step captures the escrow's **create-sequence** — the `OfferSequence` that
`EscrowFinish` needs to identify which escrow to release.

<!-- action: create_escrow amount=10 finish_seconds=10 -->

## Step 5: Verify the escrow is locked

Read it back via `account_objects`. You should see the locked amount, destination, and the
`FinishAfter` time — and your owner count is now one higher than the baseline.

<!-- action: verify_escrow -->

## Step 6: Finish the escrow

Submit `EscrowFinish`, naming the escrow by its owner + create-sequence. On testnet this only
succeeds **after** `FinishAfter` has elapsed (a few seconds — if you see a `tecNO_PERMISSION`,
the release time has not passed yet; re-run this step). In `--dry-run` the release time is
simulated as already elapsed, so it succeeds immediately and deterministically.

A time-based escrow needs **no condition or fulfillment** — the clock is the only gate.

<!-- action: finish_escrow -->

## Step 7: Verify the funds released and the reserve is freed

Confirm the escrow object is **gone** from `account_objects`. With the object removed, the locked
XRP has moved to the destination and the owner reserve it held is freed back to spendable.

<!-- action: verify_escrow_finished -->

## Step 8: Snapshot B — after the finish, and compare

Capture your account state again and compare it to the baseline. The escrow's owner-reserve slot
is gone, so `owner_count` returns to where it started.

<!-- action: snapshot_account label=after_finish -->

## Step 9: Confirm the reserve returned to baseline

Compare snapshot A (before the escrow) to snapshot B (after the finish). Owner count should match;
balance is only lower by the transaction fees.

<!-- action: verify_reserve_change before=before_escrow after=after_finish -->

## Checkpoint: What you proved

You completed a full escrow lifecycle — not just the lock, but the release:

1. **EscrowCreate** — locked XRP with a `FinishAfter` and recorded its create-sequence
2. **EscrowFinish** — released the funds once the clock matured, naming the escrow by
   owner + `OfferSequence`
3. **Reserve freed** — the escrow object was deleted, returning its owner-reserve slot

Key concepts to remember:

- **`OfferSequence` is the create sequence** — `EscrowFinish`/`EscrowCancel` identify an escrow by
  its **owner address + the EscrowCreate's sequence number**, not by a hash. Capture it at create
  time (or read it back from the escrow before finishing).
- **Time-based vs conditional** — a pure time-based escrow finishes with no condition/fulfillment;
  a crypto-conditional escrow (XLS) additionally requires the matching fulfillment.
- **`EscrowFinish` is gated by `FinishAfter`; `EscrowCancel` by `CancelAfter`** — finishing before
  `FinishAfter` (or cancelling before `CancelAfter`) fails with `tecNO_PERMISSION`.
- **Cancel is the reclaim path** — if a destination never finishes, the **owner** can
  `EscrowCancel` after `CancelAfter` and the XRP comes back. That is why escrows are not "locked
  forever": there is always a way out once the clocks elapse.
- **Either party can finish** — for a time-based escrow, anyone (commonly the destination) may
  submit `EscrowFinish` after `FinishAfter`; the funds always go to the destination regardless of
  who submits.

Run `xrpl-lab proof-pack` when you're ready to export your work.
