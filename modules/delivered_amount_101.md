---
id: delivered_amount_101
title: "Delivered Amount: The Partial-Payment Exploit"
track: payments
kb_source: partial-payment-exploit
summary: The #1 XRPL integration bug — a sender sets tfPartialPayment, the tx returns tesSUCCESS, but far less arrives than the Amount field claims. Learn to read delivered_amount, never Amount.
order: 46
time: 15-20 min
level: intermediate
mode: testnet
requires:
  - trust_lines_101
produces:
  - txid
  - report
checks:
  - "Trust line set so the holder can receive an issued currency"
  - "Issuer sent an issued-currency Payment WITH tfPartialPayment that under-delivered"
  - "The tx returned tesSUCCESS even though delivery was reduced"
  - "delivered_amount read from the validated tx metadata — the ACTUAL amount delivered"
  - "delivered_amount contrasted with the Amount field, proving the exploit"
---

This is the single most expensive bug in XRPL integrations, and it is a
**one-line mistake**: crediting a user from a transaction's `Amount` field
instead of its `delivered_amount`.

Here is how the exploit works. XRPL Payments support a flag,
**`tfPartialPayment`** (value `0x00020000` / `131072`). When it is set, the
ledger is allowed to **reduce delivery** instead of failing the transaction:
the only constraint is `DeliverMin <= delivered <= DeliverMax`, and the total
source spent must stay `<= SendMax`. So a sender can craft a Payment whose
`Amount` field says "100" but whose `SendMax` only allows a fraction to move —
the transaction returns **`tesSUCCESS`**, and only a sliver is actually
delivered.

- The tx's **`Amount`** field (renamed **`DeliverMax`** in API v2) is only the
  requested **cap**. It is NOT what arrived.
- **`delivered_amount`** is a **metadata field on a validated transaction** — the
  **actual** amount delivered. For XRP it is drops (a string); for tokens it is
  an object `{currency, issuer, value}`. (Legacy pre-2014 partial payments can
  show the literal string `"unavailable"`.)

A naive backend that reads `Amount` and credits the user that number pays out
money it never received. That is the partial-payment exploit.

(One guardrail worth knowing: **XRP-to-XRP partial payments are forbidden** —
the ledger rejects them with `temBAD_SEND_XRP_PARTIAL`. So we demonstrate the
exploit with an **issued currency**, which is exactly where real integrations
get burned.)

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **receiver** (the holder) — the account a naive backend would be
crediting.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create the issuer

A second wallet acts as the issuer — and, in this lesson, the attacker who
crafts the under-delivering payment.

**Issuer reuse:** this step loads `.xrpl-lab/issuer_wallet.json` when present
and reuses that issuer — it does not mint a fresh wallet on resume or re-run.
Minting a new issuer would orphan trust lines (and their owner reserve) against
the previous address. Leftover lines from earlier currencies still lock reserve
until balance is 0 and you remove them; run **Account Hygiene**
(`account_hygiene`) for the taught cleanup loop.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Set a trust line

Before you can receive an issued currency you must trust the issuer for it —
the same opt-in you learned in Trust Lines 101. Trust the issuer for up to 1000
**LAB**.

<!-- action: set_trust_line currency=LAB limit=1000 -->

## Step 6: The issuer sends a partial payment that under-delivers

Here is the trap. The issuer sends a Payment whose **`Amount` claims 100 LAB**,
but with **`tfPartialPayment` set** and a **`SendMax` of only 10** — so the
ledger delivers just **10 LAB** and still returns **`tesSUCCESS`**.

The `Amount` field will say 100. Only 10 will arrive. The transaction succeeds.

<!-- action: send_partial_payment currency=LAB amount=100 deliver_min=10 send_max=10 -->

## Step 7: Read delivered_amount — the field you must trust

Now the payoff. We fetch the **validated** transaction and read its
**`delivered_amount`** metadata, then contrast it with the `Amount` field. The
`Amount` field claims 100; `delivered_amount` reveals the truth: **10**.

A backend that credited the `Amount` field just gave away 90 LAB it never got.

<!-- action: verify_delivered_amount -->

## Checkpoint: What you proved

You reproduced the partial-payment exploit end-to-end and saw the exact field
that defends against it:

1. **Set a trust line** so an issued currency could be received
2. **Sent a Payment with `tfPartialPayment`** that delivered far less than its
   `Amount` field claimed — and still returned `tesSUCCESS`
3. **Read `delivered_amount`** from the validated transaction's metadata — the
   ACTUAL amount delivered
4. **Contrasted `delivered_amount` with `Amount`**, proving that crediting the
   `Amount` field would over-credit

Two lessons to carry into every integration you build:

- **RECEIVING**: always read **`delivered_amount`**, never `Amount` /
  `DeliverMax`, and only after confirming **`tesSUCCESS`** AND **`validated:true`**.
  `delivered_amount` is only authoritative on a successful, validated tx.
- **SENDING**: only set **`tfPartialPayment`** when you genuinely accept
  under-delivery — refunds, dust-sweeping, path-limited transfers. For a normal
  payout, leave it **OFF** so the transaction fails full-or-fail rather than
  silently delivering less than you promised.

Run `xrpl-lab proof-pack` when you're ready to export your work.
