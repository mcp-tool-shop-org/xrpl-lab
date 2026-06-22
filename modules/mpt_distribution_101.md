---
id: mpt_distribution_101
title: "MPT Distribution 101: Getting the Currency to Players"
track: tokens
kb_source: mpt-authorize
summary: Mint a Multi-Purpose Token game currency, have a player opt in (MPTokenAuthorize), then actually pay it to them — the missing half that makes an MPT usable.
order: 32
time: 15-20 min
level: intermediate
mode: testnet
requires:
  - mpt_issuance_101
produces:
  - txid
  - report
checks:
  - "MPT issuance created (issuer side)"
  - "Player authorized the issuance (MPTokenAuthorize) — the opt-in gate"
  - "Issuer paid the MPT to the player (Payment with an MPT amount)"
  - "Player's MPT balance verified on-ledger to the exact amount delivered"
---

`mpt_issuance_101` taught you to **mint** a Multi-Purpose Token game currency. But a
currency you can't move to a player is just a number on the issuer's account. This module
teaches the other half: getting the MPT into a holder's hands.

There are two new ideas, and the order matters:

1. **The holder opts in first.** Just like a trust line for issued currencies, a holder
   must **authorize** an MPT issuance before they can receive it — an `MPTokenAuthorize`
   transaction. This is the opt-in gate: no one can be handed an MPT they didn't agree to
   hold. Try to pay an MPT to an account that hasn't authorized it and the ledger refuses
   with `tecNO_AUTH`.
2. **The MPT amount is its own shape.** An MPT isn't identified by a currency code +
   issuer like an IOU — it's identified by a single **issuance id**. So a payment carries
   an MPT amount of `{ issuance_id, value }`, not `{ currency, issuer, value }`.

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **player** (the holder) in this module — the account that receives the currency.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create the issuer

A second wallet acts as the issuer (your game's treasury).

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Mint the game currency

The issuer creates an MPT issuance with a max supply of 1,000,000 units. The new
**issuance id** is what every later step addresses.

<!-- action: create_mpt_issuance maximum_amount=1000000 -->

## Step 6: Opt in — authorize the issuance

You (the player) send an `MPTokenAuthorize` for this issuance. This is the gate: until you
opt in, the issuer cannot pay you the token.

<!-- action: mpt_authorize -->

## Step 7: Distribute 500 units to the player

The issuer pays you 500 of the MPT. The payment carries an MPT amount addressed by the
issuance id — the currency finally moves from the treasury to a player.

<!-- action: mpt_payment amount=500 -->

## Step 8: Verify your balance on-ledger

Read your MPToken balance back. It must be **exactly 500** — the amount the issuer sent.

<!-- action: verify_mpt_balance expected=500 -->

## Checkpoint: What you proved

You completed the full MPT distribution loop:

1. **Minted** an MPT game currency (issuer side)
2. **Opted in** as a holder (`MPTokenAuthorize`) — the consent gate
3. **Distributed** the currency to a player (Payment with an MPT amount)
4. **Verified** the player holds exactly what was sent

Key concepts to remember:

- **Authorize before pay**: an MPT can only reach a holder who opted in. The opt-in is the
  MPT analog of a trust line — design your onboarding so players authorize before you try
  to airdrop them currency.
- **An MPT is addressed by its issuance id**, not a currency code + issuer. Hold onto that
  id — it's how you reference the token in every payment, query, and balance check.
- **This is what makes the capstone economy real**: issue a currency, then actually move it
  to the players who earn it.

Run `xrpl-lab proof-pack` when you're ready to export your work.
