---
id: clawback_101
title: "Clawback 101: The Issuer Recall Lever"
track: tokens
kb_source: clawback-economy-recall
summary: Enable clawback on an issuer, issue a game token, then forcibly recall part of it from a holder — the #1 anti-exploit lever for a live economy.
order: 40
time: 15-20 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Clawback enabled on the issuer BEFORE issuance (AccountSet asfAllowTrustLineClawback)"
  - "Tokens issued to a holder"
  - "Holder balance snapshotted before the clawback"
  - "Clawback recalled an exact amount (txid produced)"
  - "Holder balance dropped by EXACTLY the clawed amount"
  - "Clawback without the flag is refused (tec error, explained)"
---

A live game economy needs an undo button. If an exploit mints a holder a pile of
your currency, or a banned account is sitting on ill-gotten gold, you need a way to
**recall** it. On the XRPL that lever is **Clawback** (XLS-39): an issuer who opted in
*before issuing* can forcibly pull issued tokens back from any holder with a single
`Clawback` transaction.

The opt-in is deliberate and one-way. You set the `asfAllowTrustLineClawback`
AccountSet flag on a **fresh issuer, before any tokens exist**. You cannot enable it
retroactively once balances are outstanding — that is the consent contract: holders can
see, at the issuer level, whether their balances are clawable.

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **holder** in this module. You need a funded wallet to hold the token.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Trust lines and payments cost a small fee plus owner reserve (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Create the issuer

We create a second wallet to act as the issuer of a game currency called **GLD**.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

The issuer needs XRP for transaction fees.

<!-- action: fund_issuer -->

## Step 5: Enable clawback on the issuer (BEFORE issuing)

This is the load-bearing ordering rule. The issuer sets `asfAllowTrustLineClawback`
**now**, while it has issued nothing. Try to enable it after issuance and the ledger
refuses — the flag is a promise made up front, not a power grabbed later.

<!-- action: enable_clawback -->

## Step 6: Set a trust line for GLD

Before you can receive GLD you must opt in by trusting the issuer for up to 1000 GLD.

<!-- action: set_trust_line currency=GLD limit=1000 -->

## Step 7: Receive 100 GLD

The issuer sends you 100 GLD. Because the issuer enabled clawback before issuing, your
GLD balance is clawable.

<!-- action: issue_token currency=GLD amount=100 -->

## Step 8: Snapshot your balance

Capture your GLD balance *before* the recall so we can prove the exact-amount debit.

<!-- action: snapshot_token_balance currency=GLD label=before -->

## Step 9: Claw back 30 GLD

The issuer recalls 30 of your 100 GLD. Note the XRPL quirk taught inline: the
`Clawback` transaction's `Amount.issuer` sub-field carries the **holder** address (you),
not the issuer — the token is identified by currency plus the clawing account.

<!-- action: clawback currency=GLD amount=30 -->

## Step 10: Verify the exact-amount debit

Read your GLD trust line back. Your balance must have dropped by **exactly 30** — from
100 to 70. The verifier does the Decimal math and confirms the before/after delta.

<!-- action: verify_clawback currency=GLD -->

## Step 11: Set up the failure case

Now the other half of the lesson. We spin up a *second* issuer that issues you a token
(**NOC**) but **never** sets the clawback flag — a fresh issuer with no recall power.

<!-- action: create_noclaw_issuer currency=NOC amount=50 -->

## Step 12: The failure case — clawback without the flag

When that no-flag issuer tries to claw NOC back, the ledger refuses with a `tec` error —
the recall power was never granted, and it cannot be granted retroactively.

<!-- action: clawback_expect_fail currency=NOC amount=10 -->

## Checkpoint: What you proved

You exercised the issuer recall lever end to end:

1. **Opt-in first** — `asfAllowTrustLineClawback` is set on a fresh issuer before any issuance; it cannot be enabled retroactively
2. **Clawback** — the issuer recalled an exact amount from a holder
3. **Exact accounting** — the holder's balance dropped by precisely the clawed amount
4. **No flag, no power** — a clawback against an issuer that never opted in is refused at the protocol level

Key concepts to remember:

- **Clawback is consensual by design**: the holder can see the issuer's flag; you can't be silently exposed to recall after the fact
- **The Amount.issuer quirk**: in a `Clawback`, the holder rides in `Amount.issuer` — get this wrong and the tx is malformed
- **Clamped to balance**: you can't claw back more than the holder actually holds
- **It is a governance tool, not a backdoor**: use it for exploit recovery and compliance, and document it in your game's economy rules

Run `xrpl-lab proof-pack` when you're ready to export your work.
