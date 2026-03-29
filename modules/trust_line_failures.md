---
id: trust_line_failures
title: "Debugging Trust Lines"
order: 4
time: 10-15 min
level: beginner
requires:
  - wallet
produces:
  - txid
  - report
checks:
  - "Issued payment fails without trust line"
  - "Error code decoded and understood"
  - "Trust line set and token issued successfully"
  - "Trust line verified on-ledger"
---

Welcome to Debugging Trust Lines. In this module you will intentionally break
a token transfer and learn to read the failure — then fix it.

On the XRPL, most "why won't this token work?" questions come down to one
thing: the trust line. This module teaches you to diagnose the three most
common trust line failures by producing each one on purpose.

## Step 1: Ensure your wallet is ready

You need a funded wallet. If you have one from a previous module, it will
be loaded automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

You need XRP for transaction fees.

<!-- action: ensure_funded -->

## Step 3: Create an issuer

We need a second wallet to act as the token issuer. This issuer will try to
send you tokens — and you will see what happens when the recipient is not
ready.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

The issuer needs XRP to pay fees.

<!-- action: fund_issuer -->

## Step 5: Attempt to receive tokens WITHOUT a trust line

This is the key moment. The issuer will try to send you 100 DBG tokens.
But you have **not** set a trust line for DBG — so the ledger has no
permission to deliver them.

Watch for the error code. On the XRPL, this is `tecPATH_DRY`: the payment
has no valid delivery path because the destination has no trust line for
this currency.

<!-- action: issue_token_expect_fail currency=DBG amount=100 -->

## Step 6: Fix it — set a trust line and try again

Now set a trust line for DBG and have the issuer resend. This time it
will succeed because the ledger knows you are willing to hold DBG from
this issuer.

<!-- action: set_trust_line currency=DBG limit=1000 -->

## Step 7: Issue tokens (this time it works)

With the trust line in place, the same payment that failed before will
now succeed.

<!-- action: issue_token currency=DBG amount=100 -->

## Step 8: Verify the trust line

Confirm the trust line shows the correct currency, issuer, limit, and
balance.

<!-- action: verify_trust_line currency=DBG -->

## Checkpoint: What you proved

You just debugged the most common trust line failure:

1. **No trust line** → `tecPATH_DRY` — the ledger refuses to deliver
   tokens you did not agree to receive
2. **Set trust line** → you opted in to holding DBG from this issuer
3. **Reissue** → same payment, now succeeds
4. **Verified** → the trust line and balance are correct on-ledger

This is the debugging skill that separates operators from tourists:
- When a token transfer fails, **check the trust line first**
- The error code tells you exactly what is missing
- The fix is always the same: set a trust line, then retry

Common trust line failures you will encounter in the wild:
- `tecPATH_DRY` — no delivery path (missing trust line or no liquidity)
- `tecNO_LINE` — destination has no trust line for this currency
- `tecNO_DST` — destination account does not exist
- `tecUNFUNDED_PAYMENT` — sender does not have enough of the token

Run `xrpl-lab feedback` if you need to report an issue.
