---
id: failure_literacy
title: Failure Literacy
track: foundations
summary: Submit intentionally broken transactions and learn to decode error codes.
order: 2
time: 10-15 min
level: beginner
mode: testnet
requires:
  - receipt_literacy
produces:
  - txid
  - report
checks:
  - "Intentional failure submitted"
  - "Error code identified"
  - "Fix applied and resubmitted successfully"
---

Transactions fail. The difference between a beginner and a competent
operator is knowing *why* they fail and *how* to fix them.

In this module you intentionally break a transaction, read the error,
then fix and resubmit it. Everything here is safe — failed transactions
on the testnet cost nothing.

## Step 1: Ensure your wallet is ready

<!-- action: ensure_wallet -->

## Step 2: Ensure you have funds

<!-- action: ensure_funded -->

## Step 3: Submit a failing transaction

We are going to submit a transaction that we *know* will fail. This is safe —
a failed transaction on the XRPL Testnet costs nothing and harms nothing.

Common failure modes on XRPL:
- `tecUNFUNDED_PAYMENT` — not enough XRP
- `tecNO_DST` — destination account doesn't exist
- `tefBAD_AUTH` — wrong signing key
- `tecPATH_DRY` — no liquidity path (for issued currencies)

Let's trigger one now.

<!-- action: submit_payment_fail reason=underfunded -->

## Step 4: Read the error

Look at the result code above. Every XRPL result code has a prefix that tells
you the category:

| Prefix | Meaning |
|--------|---------|
| `tes`  | Success |
| `tec`  | Claimed — tx applied but failed (fee charged on mainnet) |
| `tef`  | Failed — tx not applied |
| `tel`  | Local — client-side rejection |
| `tem`  | Malformed — invalid tx format |
| `ter`  | Retry — might work later |

The result code tells you *what* happened. The category tells you *how bad*.

## Step 5: Fix and resubmit

Now let's submit the same payment correctly. The fix depends on what failed:
- Underfunded? Fund the wallet or reduce the amount.
- Bad destination? Use a valid address.
- Auth error? Check the signing wallet.

We will send a corrected payment now.

<!-- action: submit_payment destination=self amount=10 memo=XRPLLAB|L2|FIXED|{timestamp} -->

## Step 6: Verify the fix

Let's confirm the corrected transaction landed.

<!-- action: verify_tx -->

## Checkpoint: What you proved

You just completed the debugging workflow:

1. You submitted a transaction that failed (on purpose)
2. You read and understood the error code
3. You identified the fix
4. You resubmitted successfully

Every production system has failures. The question is never "will it
fail?" — it's "can you diagnose and recover?" Now you can.

Both the failed and successful transactions are in your trail. Run
`xrpl-lab proof-pack` when you're ready to export.
