---
id: account_hygiene
title: "Account Hygiene: Freeing Reserves and Cleaning Up Objects"
track: reserves
summary: Clean up ledger objects and free locked reserves on your account.
order: 7
time: 15-25 min
level: intermediate
mode: testnet
requires:
  - reserves_101
produces:
  - txid
  - report
checks:
  - "Baseline snapshot captured (A)"
  - "Owner count increased after creating objects (B)"
  - "Offer cancelled successfully"
  - "Trust line removed (limit 0, balance 0)"
  - "Owner count returned to baseline (C)"
---

You learned in Reserves 101 that owned objects lock reserve XRP.
Now you learn how to **reclaim** it.

This module walks you through creating objects, then systematically
removing them — cancelling offers and deleting trust lines — and
verifying that your owner count drops back to baseline.

This is routine maintenance, not surgery. Every step is reversible.

The rule is simple:
- **Cancel stale offers** to free their reserve
- **Remove unused trust lines** by setting limit to 0 (only works if
  balance is also 0 — you can't delete a trust line while holding tokens)
- **Re-snapshot** to confirm reserve was released

## Step 1: Ensure your wallet is ready

You need a funded wallet. If you've completed earlier modules, your
existing wallet will be reused.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Make sure you have enough XRP for the operations ahead.

<!-- action: ensure_funded -->

## Step 3: Snapshot A — baseline

Capture your current account state. This is your clean starting point:
owner count, balance, and sequence number.

<!-- action: snapshot_account label=baseline -->

## Step 4: Create an issuer wallet

We need an issuer to create objects against. This issuer creates a currency
called HYGIENE — chosen specifically because we won't issue any tokens,
which means the trust line can be cleanly removed later.

<!-- action: create_issuer_wallet -->

## Step 5: Fund the issuer

<!-- action: fund_issuer -->

## Step 6: Create two owned objects

First, set a trust line for HYGIENE with a small limit. No tokens will be
issued — we're keeping the balance at 0 so removal works cleanly.

Then place a tiny DEX offer (XRP for HYGIENE) to create a second owned
object.

<!-- action: set_trust_line currency=HYGIENE limit=100 -->

## Step 7: Place the offer

<!-- action: create_offer pays_currency=HYGIENE pays_value=10 gets_currency=XRP gets_value=1 -->

## Step 8: Snapshot B — dirty state

Two new objects: one trust line + one offer. Your owner count should be
higher than baseline.

<!-- action: snapshot_account label=dirty -->

## Step 9: Verify the increase

Compare baseline (A) to dirty state (B). You should see owner count
increased by 2 (one trust line + one offer).

<!-- action: verify_reserve_change before=baseline after=dirty -->

## Step 10: Cancel the offer

Remove the first object. This should decrement owner count by 1 and
release that offer's reserve back to spendable.

<!-- action: cancel_offer -->

## Step 11: Remove the trust line

Set the HYGIENE trust line limit to 0. Because we never issued any
HYGIENE tokens, the balance is 0 — so the ledger will delete the trust
line object entirely.

If you had a non-zero balance, this would fail. That's the rule: you
must return or burn all tokens before you can remove a trust line.

<!-- action: remove_trust_line currency=HYGIENE -->

## Step 12: Verify removal

Confirm the HYGIENE trust line no longer appears in your account's
trust line list.

<!-- action: verify_trust_line_removed currency=HYGIENE -->

## Step 13: Snapshot C — clean state

Capture your account state one final time. Owner count should be back
to where it was at baseline.

<!-- action: snapshot_account label=clean -->

## Step 14: Verify the cleanup

Compare dirty state (B) to clean state (C). Owner count should have
decreased by 2 — one for the cancelled offer, one for the removed
trust line.

<!-- action: verify_reserve_change before=dirty after=clean -->

## Step 15: Full comparison — baseline to clean

Compare your original baseline (A) to your final clean state (C).
Owner count should be the same. Balance will be slightly lower due
to transaction fees, but all reserve XRP is freed.

<!-- action: verify_reserve_change before=baseline after=clean -->

## Checkpoint: What you proved

You just performed a complete hygiene cycle:

1. **Captured a baseline** — clean starting state (A)
2. **Created 2 owned objects** — trust line + offer (B)
3. **Cancelled the offer** — freed one reserve slot
4. **Removed the trust line** — freed another reserve slot (limit=0, balance=0)
5. **Verified cleanup** — owner count returned to baseline (C)

Operator checklist for real accounts:
- **Audit owned objects**: `account_info` shows your `OwnerCount`
- **Cancel stale offers**: any offer you no longer want is locking reserve
- **Remove unused trust lines**: set limit to 0, but only after balance
  reaches 0 (send tokens back to issuer or let them expire)
- **Re-check after cleanup**: snapshot before and after to confirm
  reserve was actually released

Run `xrpl-lab proof-pack` when you're ready to export your work.
