---
id: checks_101
title: "Checks 101: Deferred Pull-Payments (CheckCreate / CheckCash / CheckCancel)"
track: payments
kb_source: checks-deferred-pull-payment
summary: Write a Check authorizing a player to pull up to an amount whenever they choose, prove the funds are NOT locked (unlike Escrow), cash it, credit from delivered_amount, and cancel an unredeemed one.
order: 43
time: 20-25 min
level: intermediate
mode: testnet
requires:
  - receipt_literacy
produces:
  - txid
  - report
checks:
  - "Check written (CheckCreate, SendMax authorizes up to the reward amount, txid + CheckID produced)"
  - "Reserve delta observed after CheckCreate — contrast with Escrow's locking behavior (funds not reserved beyond the Check object)"
  - "Player cashed the Check for the exact amount (CheckCash Amount, tesSUCCESS)"
  - "Credited from delivered_amount — never the Check's own Amount/SendMax fields"
  - "A second Check written and later cancelled (CheckCancel, reserve freed, nothing refunded)"
  - "A non-Destination's cash attempt was rejected — tecNO_PERMISSION"
---

A **Check** is a deferred, PULL-style payment: the sender writes an
authorization — a maximum amount (**`SendMax`**) and the one account allowed
to claim it — and the recipient decides whether, and when, to actually pull
the money, by submitting **`CheckCash`** themselves. Nothing changes hands at
write time. This is the **claimable-reward pattern**: a studio writes a Check
for a battle-pass payout or a tournament prize, and the player cashes it on
their own schedule — no payout job to run, no funds sitting in escrow waiting
for a timer.

The rule that separates Checks from Escrow — read this twice: **`CheckCreate`
does not lock or set aside any XRP.** `SendMax` is a CEILING, not a
reservation. The writer's spendable balance is untouched the moment the Check
is written; the only new cost is a small owner reserve for the Check object
itself. This means a Check that succeeded at creation can still FAIL at cash
time if the writer's balance has since dropped below what's being asked —
**`CheckCreate` returning `tesSUCCESS` is never a guaranteed payout.** Contrast
this hard with Escrow: `EscrowCreate` debits and holds the funds the instant
it validates; a Check debits NOTHING until `CheckCash` actually executes.

Three transactions make up the lifecycle, all mainnet-live since 2018:

1. **`CheckCreate`** — write the authorization: `Destination`, `SendMax`, and
   optionally `Expiration`, `DestinationTag`, `InvoiceID`. Creates a `Check`
   ledger object (owner reserve charged to the writer).
2. **`CheckCash`** — only the named **Destination** may redeem it, for
   exactly one of an exact **`Amount`** or a flexible **`DeliverMin`** (at
   least this much, up to `SendMax`).
3. **`CheckCancel`** — voids an unredeemed Check. Either the writer or the
   Destination may cancel a LIVE Check; once it expires, ANY address may
   clean it up. Unlike `EscrowCancel`, nothing is credited back — a Check
   never moved anything, so there is nothing to refund.

This runs on testnet — free and disposable. Your wallet plays the **studio**
(the writer); a second wallet plays the **player** who claims the reward.

## Step 1: Ensure your wallet is ready

Your wallet is the **studio** — the account writing the claimable reward.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Writing a Check costs a normal transaction fee plus a small owner reserve for
the Check object (free on testnet). Cashing it later is the player's own
transaction, on the player's own wallet.

<!-- action: ensure_funded -->

## Step 3: Create the player wallet

A fresh, funded wallet plays the player — the ONLY account this Check will
ever let cash it.

<!-- action: create_recipient_wallet -->

## Step 4: Snapshot your balance before writing the Check

Before proving the "no lock" claim, capture a baseline: your current balance
and owner count.

<!-- action: snapshot_account label=before_check -->

## Step 5: Write the Check — a claimable reward

`CheckCreate` authorizes the player to pull up to 50 XRP (`SendMax`) whenever
they choose. Read that again: it AUTHORIZES, it does not SEND. Nothing has
moved yet.

<!-- action: create_check amount=50 -->

## Step 6: Snapshot your balance again

<!-- action: snapshot_account label=after_check -->

## Step 7: Prove the funds were never locked

Compare the two snapshots. Your owner count went up by one — the Check object
itself now costs a reserve slot — but your SPENDABLE BALANCE did not move.
Escrow would have debited the full 50 XRP right here; a Check debits nothing
until `CheckCash` actually runs.

<!-- action: verify_reserve_change before=before_check after=after_check -->

## Step 8: The player cashes the Check

The player submits `CheckCash` for the exact amount (`Amount`). Only the
Destination named on the Check can do this — the studio's own key plays no
role in this transaction at all.

<!-- action: cash_check amount=50 -->

## Step 9: Credit the player from delivered_amount

Same receiving discipline as Delivered Amount 101 and Custodial Crediting:
read **`delivered_amount`** from the validated `CheckCash`, never the Check's
own `Amount`/`SendMax` fields. xrpl.org names `CheckCash` explicitly as a
transaction type whose own amount field is not the one to trust — this is
why. For a plain XRP exact-cash the two numbers happen to match; a correct
backend reads `delivered_amount` every time anyway, because token checks
(with a transfer fee in play) are exactly where they diverge.

<!-- action: credit_check_cash -->

## Step 10: Write a second reward — then change your mind

The studio writes another Check, this time deciding to withdraw the offer
before the player claims it.

<!-- action: create_check amount=20 -->

## Step 11: Create an outsider wallet

A third wallet — someone who is NOT this Check's Destination — to test the
boundary.

<!-- action: create_outsider_wallet -->

## Step 12: See the failure — only the Destination may cash

The outsider tries to cash the still-live Check. It fails: `CheckCash` checks
the SIGNING account against the Check's `Destination` field, and this signer
is not it.

<!-- action: cash_check_wrong_destination_expect_fail amount=20 -->

## Step 13: Cancel the unredeemed Check

The studio voids it with `CheckCancel`. Notice what does NOT happen: no XRP
moves back to the studio, because none was ever taken. Only the owner reserve
is freed.

<!-- action: cancel_check -->

## Checkpoint: What you proved

You ran the full Check lifecycle — write, prove no lock, cash, credit, and
cancel — with receipts for every claim:

1. **`CheckCreate` moves nothing** — verified on-ledger: your balance was
   unchanged after writing a 50 XRP authorization; only your owner count rose
2. **`CheckCash` (exact `Amount`)** — the player redeemed the Check;
   `tesSUCCESS`
3. **Credited `delivered_amount`** — never the Check's `Amount`/`SendMax`,
   reusing the Delivered Amount 101 discipline unchanged
4. **`CheckCancel` refunds nothing** — a second Check was written and voided;
   the reserve was freed, but no XRP moved, because none was ever taken
5. **`tecNO_PERMISSION`** — an outsider's cash attempt was rejected; only the
   named Destination may ever cash a Check

Key concepts to remember:

- **Check vs Escrow — the one distinction that matters.** `EscrowCreate`
  locks and reserves funds immediately; `CheckCreate` only authorizes a
  ceiling. Never treat `CheckCreate` success as a guaranteed payout — the
  writer's balance can drop below `SendMax` before the destination cashes it,
  and `CheckCash` will then fail honestly rather than pay out money that
  isn't there.
- **`SendMax` is a ceiling, not the delivered amount.** For token Checks
  especially, always reconcile against **`delivered_amount`** from the
  `CheckCash` metadata — never `SendMax`, never the `CheckCash`'s own
  `Amount`/`DeliverMin`.
- **Only the Destination cashes; either party (or anyone, once expired)
  cancels.** `CheckCash` from any other account fails `tecNO_PERMISSION`.
  `CheckCancel` is open to the writer or the Destination while the Check is
  live, and to ANY address once its `Expiration` has passed — a past-expiry
  Check can only be cancelled, never cashed (`tecEXPIRED`).
- **A missing or already-consumed CheckID fails `tecNO_ENTRY`** — cashing or
  cancelling a wrong id, or one already cashed/cancelled by someone else,
  fails honestly rather than silently.
- **Token checks exist too.** `SendMax`/`Amount`/`DeliverMin` can carry an
  issued currency instead of XRP (the destination needs a trust line first,
  same as any issued-currency payment) — the reconciliation discipline is
  identical: read `delivered_amount`, not the face values on the transactions
  themselves.

Run `xrpl-lab proof-pack` when you're ready to export your work.
