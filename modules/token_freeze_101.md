---
id: token_freeze_101
title: "Token Freeze 101: The Issuer's Pause Button"
track: tokens
kb_source: freeze-tiers-sanctions
summary: Freeze a single holder's token line, then freeze your whole currency at once — the issuer's two non-destructive sanction levers below clawback.
order: 35
time: 15-20 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Token issued to a holder"
  - "Individual Freeze set on the holder's trust line (TrustSet tfSetFreeze), verified on-ledger"
  - "Individual Freeze cleared, verified OFF"
  - "Global Freeze enabled on the issuer (AccountSet asfGlobalFreeze), verified on-ledger"
  - "Global Freeze cleared, verified OFF"
---

Clawback (the previous module) is the issuer's *destructive* lever — it pulls tokens
back. But most of the time you want something gentler first: **stop** the money moving
without taking it. On the XRPL that lever is **Freeze**, and it comes in two tiers.

- **Individual Freeze** — the issuer freezes **one holder's** trust line. That holder
  can no longer send the token (they can only send it *back to the issuer*). Everyone
  else keeps trading. This is your targeted sanction: a single exploited or banned
  account, paused, with their balance intact and recoverable.
- **Global Freeze** — the issuer freezes **the whole currency** at once. Every holder
  is paused. This is your economy-wide circuit breaker: an exploit is draining the
  market and you need to stop *all* movement while you investigate.

Both are core, mainnet-live features and both are **reversible** — you set the flag, and
you clear it. (There is a third tier, *Deep Freeze* / XLS-77d, that blocks a holder from
even returning the token to the issuer. It is not yet enabled on XRPL mainnet, so this
module deliberately does not teach it as live — Individual and Global are the two you can
rely on today.)

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **holder** in this module — the account whose token gets frozen.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create the issuer

A second wallet acts as the issuer of a game currency called **GLD**.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Set a trust line for GLD

Before you can hold GLD you opt in by trusting the issuer for up to 1000 GLD.

<!-- action: set_trust_line currency=GLD limit=1000 -->

## Step 6: Receive 100 GLD

The issuer sends you 100 GLD. You now hold a real balance — the thing freeze will pause.

<!-- action: issue_token currency=GLD amount=100 -->

## Step 7: Individual Freeze — pause this one holder

The issuer freezes **your** GLD trust line with a `TrustSet` carrying the `tfSetFreeze`
flag. The freeze is set on the *issuer's* side of the line: your balance is untouched,
but you can no longer move that GLD to anyone except the issuer.

<!-- action: set_freeze currency=GLD freeze=true -->

## Step 8: Verify the freeze is on

Read the issuer's view of the line back. The `freeze` flag must be **on**.

<!-- action: verify_freeze currency=GLD expect_individual=true -->

## Step 9: Unfreeze — lift the pause

Individual Freeze is reversible. The issuer clears it with a `TrustSet` carrying
`tfClearFreeze`, and your GLD is liquid again.

<!-- action: set_freeze currency=GLD freeze=false -->

## Step 10: Verify the freeze is off

<!-- action: verify_freeze currency=GLD expect_individual=false -->

## Step 11: Global Freeze — pause the whole currency

Now the bigger hammer. The issuer sets `asfGlobalFreeze` (an `AccountSet` flag) on its
**account**. Every holder of every token this account issues is now paused at once — the
economy-wide circuit breaker.

<!-- action: set_global_freeze enable=true -->

## Step 12: Verify Global Freeze is on

Read the issuer's account flags back. Global Freeze must be **on**.

<!-- action: verify_freeze expect_global=true -->

## Step 13: Clear Global Freeze — resume trading

<!-- action: set_global_freeze enable=false -->

## Step 14: Verify Global Freeze is off

<!-- action: verify_freeze expect_global=false -->

## Checkpoint: What you proved

You exercised both non-destructive issuer sanction levers end to end:

1. **Individual Freeze** — paused one holder's line (`tfSetFreeze`) and confirmed it
   on-ledger, then lifted it (`tfClearFreeze`)
2. **Global Freeze** — paused the entire currency (`asfGlobalFreeze`) and confirmed it,
   then cleared it
3. **Reversible** — both flags went on AND off; freeze stops movement, it never destroys
   a balance

Key concepts to remember:

- **Freeze is the rung below clawback**: stop the money before you take it. Reach for
  Individual Freeze first (targeted), Global Freeze when the whole market is at risk, and
  Clawback only when you actually need to recall tokens.
- **A frozen holder can still pay the issuer back**: Individual Freeze blocks holder→holder
  transfers, not holder→issuer — the off-ramp stays open.
- **`asfNoFreeze` is a one-way promise**: an issuer can permanently *relinquish* its freeze
  power with the NoFreeze flag — a credibility signal to holders that their balances can
  never be paused. (We don't set it here; it can't be undone.)
- **Deep Freeze (XLS-77d) is not mainnet-live** — don't design a live economy around it yet.

Run `xrpl-lab proof-pack` when you're ready to export your work.
