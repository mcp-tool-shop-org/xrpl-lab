---
id: reserves_101
title: "Reserves 101: Where Your XRP 'Went'"
track: reserves
summary: See how trust lines and offers lock reserves, and reclaim them.
order: 6
time: 10-15 min
level: intermediate
mode: testnet
requires:
  - trust_lines_101
produces:
  - txid
  - report
checks:
  - "Account snapshot captured before and after"
  - "Owner count increased after creating objects"
  - "Owner count decreased after removing objects"
  - "Reserve impact explained"
---

Welcome to Reserves 101. This is the module that answers the #1 beginner
question: "Where did my XRP go?"

The XRPL has two types of reserves:

- **Base reserve**: the minimum XRP every account must hold to exist on the
  ledger (currently 1 XRP on mainnet testnet values may differ).
- **Owner reserve**: additional XRP locked per "owned object" — each trust
  line, open offer, escrow, or other ledger entry you create.

Your **spendable XRP** is your balance minus all reserves. When you create
objects, spendable XRP shrinks. When you remove them, it comes back.

Reserve values may vary by network and settings. What matters is the
concept: owned objects reduce spendable XRP.

## Step 1: Ensure your wallet is ready

You need a funded wallet with an existing LAB trust line from Trust Lines 101.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Make sure you have enough XRP for the operations ahead.

<!-- action: ensure_funded -->

## Step 3: Snapshot — before

Let's capture your account state right now. This is your "before" picture:
balance in drops, owner count, and estimated spendable XRP.

<!-- action: snapshot_account label=before -->

## Step 4: Create an owned object (OfferCreate)

Now we'll create a DEX offer. This adds one owned object to your account,
which should increase the owner count and lock more reserve.

We need an issuer wallet to reference LAB tokens in the offer.

<!-- action: create_issuer_wallet -->

## Step 5: Fund the issuer and create the offer

<!-- action: fund_issuer -->

## Step 6: Set a trust line and place the offer

First, set a trust line for a second currency (RSV) to create another
owned object. Then place a tiny XRP/RSV offer on the DEX.

<!-- action: set_trust_line currency=RSV limit=1000 -->

## Step 7: Snapshot — after creating objects

Let's capture your account state again. You should see:

- **Owner count increased** — each trust line and offer is an owned object
- **Balance may have decreased** slightly (transaction fees)

<!-- action: snapshot_account label=after_create -->

## Step 8: Compare and explain

Here's what changed between your "before" and "after" snapshots. The
owner count delta shows how many objects you added, and the balance
delta reflects fees paid.

<!-- action: verify_reserve_change before=before after=after_create -->

## Checkpoint: What you proved

You just observed the reserve mechanism in action:

1. **Captured a baseline** — your account's balance and owner count
2. **Created owned objects** — trust line + offer increased owner count
3. **Measured the impact** — each object locks additional reserve XRP
4. **Understood the concept** — "missing" XRP is locked in reserves

Operator takeaway:
- **Keep enough XRP for reserves** — if you create many trust lines or
  offers, your spendable balance shrinks
- **Objects cost reserve** — every trust line, offer, escrow, or check
  locks additional XRP
- **Cancel offers to free reserve** — removing objects releases the
  locked XRP back to spendable
- **Trust lines are sticky** — you can only remove a trust line if the
  balance is zero AND the limit is set to zero

Your report and transaction IDs are saved. Run `xrpl-lab proof-pack` to
export a shareable proof of what you did here.
