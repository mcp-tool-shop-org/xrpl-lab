---
id: escrow_101
title: "Escrow 101: Time-Locked XRP"
track: payments
kb_source: escrow-xrp
summary: Lock XRP in a time-based escrow and verify it on-ledger.
order: 40
time: 15-20 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Escrow created (txid produced)"
  - "Escrow verified on-ledger: amount, destination, FinishAfter"
---

**Escrow** locks XRP on-ledger so it can only be released when a condition is met. The simplest
form is **time-based**: set a `FinishAfter` time, and the funds can be finished (released) only
after it. Escrow is the building block for vesting, delayed payouts, and conditional rewards.

This runs on testnet — free and disposable. You'll escrow XRP to yourself, finishable shortly.

## Step 1: Ensure your wallet is ready

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Escrow locks real XRP plus an owner reserve for the escrow object (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Create a time-based escrow

Lock some XRP with a `FinishAfter` a couple of minutes out. (Defaults escrow to your own
account — escrow-to-self is the simplest way to learn the mechanics.)

<!-- action: create_escrow amount=10 finish_seconds=120 -->

## Step 4: Verify the escrow

Read it back via `account_objects`. You should see the locked amount, destination, and the
FinishAfter time.

<!-- action: verify_escrow -->

## Checkpoint: What you proved

You locked XRP in a time-based escrow and verified it on-ledger:

1. **EscrowCreate** — locked funds with a `FinishAfter` release time
2. **On-ledger custody** — no third party holds the funds; the ledger enforces the condition
3. **Verified** — `account_objects` shows your escrow

Key concepts to remember:

- **FinishAfter or a crypto-condition** — every escrow needs at least one; `CancelAfter` (if set) must be **later** than `FinishAfter`.
- **Finishing is a second step** — `EscrowFinish` can only succeed **after** `FinishAfter`; this module creates + verifies, you finish later.
- **Reserve cost** — each open escrow object costs owner reserve until finished or cancelled.
- **Token escrow** — as of XLS-85 (2026), escrow also supports IOUs/MPTs (issuer opt-in); this lesson uses XRP.

Run `xrpl-lab proof-pack` when you're ready to export your work.
