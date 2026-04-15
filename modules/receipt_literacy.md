---
id: receipt_literacy
title: Receipt Literacy
track: foundations
summary: Send a real payment and learn to read every field in the receipt.
order: 1
time: 10-15 min
level: beginner
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Payment submitted successfully"
  - "Tx verified: amount, destination, fee, result"
---

Welcome to Receipt Literacy. In this module you will send a real payment on the
XRPL Testnet and learn to read every field in the receipt.

By the end you will be able to verify: who sent what, to whom, for how much,
what it cost, and whether it actually worked.

## Step 1: Ensure your wallet is ready

First we need a funded wallet. If you already have one from XRPL Camp or a
previous session, it will be loaded automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Your wallet needs XRP to pay for transactions. We will request test XRP from
the faucet — this is free and only works on the testnet.

<!-- action: ensure_funded -->

## Step 3: Send a payment

Now send a small payment. We will attach a memo so you can find this
transaction later. The memo format is: `XRPLLAB|L1|<timestamp>`

This payment goes to your own address (a self-payment) so nothing is lost.
On a real network you would send to someone else.

<!-- action: submit_payment destination=self amount=10 memo=XRPLLAB|L1|{timestamp} -->

## Step 4: Verify the receipt

Now let's look up your transaction on the ledger and verify every field.

A proper receipt check covers:
- **Result code**: `tesSUCCESS` means the ledger accepted it
- **Amount**: matches what you sent
- **Destination**: matches where you sent it
- **Fee**: the network fee in drops (1 XRP = 1,000,000 drops)
- **Ledger index**: which ledger version recorded your tx
- **Validated**: whether the consensus process has confirmed it

<!-- action: verify_tx -->

## Checkpoint: What you proved

You just completed the fundamental workflow of any blockchain interaction:

1. You had a funded wallet (identity + resources)
2. You submitted a transaction (intent → ledger)
3. You verified the receipt (ledger → proof)

This is the skill that everything else builds on: trust lines, DEX offers,
escrows, multi-sig — they all start with "send, receive, verify."

Your report and transaction ID are saved. Run `xrpl-lab proof-pack` to
export a shareable proof of what you did here.
