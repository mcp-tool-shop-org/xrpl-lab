---
id: payment_channel_101
title: "Payment Channels 101: Sign Many, Settle Once"
track: payments
kb_source: payment-channel-tipping-streaming
summary: Lock XRP once, then sign many cheap OFF-LEDGER claims and let the receiver settle the latest on-ledger — the native rail for tipping, pay-per-action, and streaming rewards.
order: 45
time: 20-25 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Channel opened with XRP locked (PaymentChannelCreate)"
  - "Channel topped up (PaymentChannelFund) — deposit verified on-ledger"
  - "An off-ledger claim signed (no transaction, no fee) and verified by the receiver"
  - "A larger cumulative claim signed — demonstrating sign-many"
  - "Receiver redeemed the latest claim on-ledger (PaymentChannelClaim)"
  - "Channel's claimed balance verified to the exact redeemed amount"
---

A regular `Payment` costs a transaction (and a fee, and a ledger close) every single time.
That's fine for buying a sword. It is **terrible** for tipping a streamer every second,
paying per-action in a game, or streaming a reward as a player progresses — hundreds of
tiny payments would drown in fees and ledger churn.

**Payment channels** solve this. The pattern is "sign many, settle once":

1. The sender **locks XRP** into a channel **once** (one on-ledger transaction).
2. The sender then signs **off-ledger claims** — tiny signed messages saying "you may take
   up to N XRP from this channel." These cost **nothing**: no transaction, no fee, no ledger
   wait. Sign a thousand of them.
3. The receiver **redeems** whichever claim they like, **on-ledger**, whenever they choose
   (one transaction). Claims are **cumulative** — redeeming the latest settles everything.

The receiver always holds a claim they can cash; the sender's locked XRP guarantees it.
That's the trust model: instant, fee-free micropayments backed by on-ledger collateral.

(On XRPL mainnet today, payment channels are **XRP-only** — perfect for streaming native
value. Everything here runs on the testnet.)

## Step 1: Ensure your wallet is ready

You are the **sender** — the one funding the channel and signing claims.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create the receiver

A second wallet is the **receiver** — the merchant / streamer / player being paid.

<!-- action: create_channel_receiver -->

## Step 4: Open the channel

Lock 10 XRP into a channel to the receiver. This is the **one** on-ledger setup. The channel
records the sender's signing key so the receiver can later verify your claims.

<!-- action: open_channel amount=10 -->

## Step 5: Verify the channel exists

<!-- action: verify_channel expect_amount=10 -->

## Step 6: Top the channel up

Channels can be funded again at any time — add 5 more XRP, bringing the deposit to 15.

<!-- action: fund_channel amount=5 -->

## Step 7: Verify the new deposit

<!-- action: verify_channel expect_amount=15 -->

## Step 8: Sign an off-ledger claim for 3 XRP

Here's the magic. The sender signs a claim authorizing the receiver to take up to **3 XRP**.
No transaction. No fee. Instant. In a real app you'd do this hundreds of times a second.

<!-- action: sign_claim amount=3 -->

## Step 9: The receiver verifies the claim

The receiver checks the claim's signature against the channel's key — off-ledger, instantly.
A valid claim is as good as cash they can redeem whenever they want.

<!-- action: verify_claim_signature -->

## Step 10: Sign a larger cumulative claim — 7 XRP

Claims are **cumulative**: a new claim for 7 XRP supersedes the 3 XRP one. The receiver only
ever needs to keep the latest. This is the "sign many" half — imagine these streaming by.

<!-- action: sign_claim amount=7 -->

## Step 11: The receiver verifies the larger claim

<!-- action: verify_claim_signature -->

## Step 12: Redeem the claim on-ledger

Now the "settle once" half. The receiver submits the 7 XRP claim on-ledger with one
`PaymentChannelClaim`. The XRP moves from the channel to the receiver. Dozens of off-ledger
claims, **one** settling transaction.

<!-- action: redeem_claim -->

## Step 13: Verify the settled balance

Read the channel back. Its **claimed** balance must be exactly **7 XRP** — what the receiver
redeemed, out of the 15 deposited.

<!-- action: verify_channel expect_balance=7 -->

## Checkpoint: What you proved

You ran the full micropayment loop:

1. **Locked** XRP into a channel once (`PaymentChannelCreate`) and **topped it up** (`PaymentChannelFund`)
2. **Signed claims off-ledger** for free, and the receiver **verified** them instantly
3. **Signed a larger cumulative claim** — the "sign many" pattern
4. **Settled** the latest claim on-ledger once (`PaymentChannelClaim`)
5. **Verified** the exact claimed amount on-ledger

Key concepts to remember:

- **Sign many, settle once**: off-ledger claims are free and instant; only the final redemption
  touches the ledger. This is what makes per-action / streaming payments viable.
- **Claims are cumulative**: the receiver keeps only the latest; it supersedes all earlier ones.
- **Collateral makes it trustless**: the sender's locked XRP backs every claim, so the receiver
  can always redeem what they were promised.
- **The watchtower pattern**: a receiver (or a service watching for them) redeems before the
  channel's settle-delay lets the sender reclaim unclaimed funds. Design your payout cadence
  around it.
- **XRP-only on mainnet today**: payment channels stream native XRP; token channels are not yet
  live. Use them for native-value tipping, metered play, and streaming rewards.

Run `xrpl-lab proof-pack` when you're ready to export your work.
