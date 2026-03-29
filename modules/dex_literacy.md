---
id: dex_literacy
title: "DEX Literacy: Offers, Order Books, and Cancellations"
order: 5
time: 10-15 min
level: intermediate
requires:
  - wallet
  - trust_lines_101
produces:
  - txid
  - report
checks:
  - "Offer created on the DEX"
  - "Offer verified as active"
  - "Offer cancelled successfully"
  - "Offer verified as absent"
---

Welcome to DEX Literacy. The XRPL has a built-in decentralized exchange — no
smart contracts, no AMM (for this module), just native order book matching.

In this module you will create an offer to trade XRP for LAB tokens, verify it
is live on the order book, cancel it, and confirm it is gone.

**Prerequisite**: You must have completed **Trust Lines 101** first. This module
uses the LAB token and issuer from that module. If you have not completed it,
run `xrpl-lab run trust_lines_101` first.

## Step 1: Ensure your wallet is ready

You need the same funded wallet from Trust Lines 101. Your LAB trust line must
already exist.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Offers require XRP for fees and the owner reserve (each open offer increases
the reserve by 2 XRP on mainnet, free on testnet).

<!-- action: ensure_funded -->

## Step 3: Prepare the issuer

We need the issuer address from your Trust Lines 101 session. This step loads
or re-creates the issuer wallet so the offer references a valid LAB issuer.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

The issuer needs XRP to exist on the ledger (the offer references this address).

<!-- action: fund_issuer -->

## Step 5: Create a DEX offer

Now you will submit an **OfferCreate** transaction. This places an order on the
XRPL's built-in order book.

Your offer says: "I will pay 10 XRP to get 50 LAB."

This means someone who has LAB tokens and wants XRP can fill your offer. On
testnet, it will likely sit in the order book unfilled — which is exactly what
we want, because the next step is to verify it is there.

Key concepts:
- **TakerPays**: what the taker of your offer pays (the asset you want to receive)
- **TakerGets**: what the taker of your offer gets (the asset you are offering)
- From your perspective: you GET TakerPays and you PAY TakerGets

<!-- action: create_offer pays_currency=LAB pays_value=50 gets_currency=XRP gets_value=10 -->

## Step 6: Verify the offer is active

Let's check that your offer exists in your account's active offers. The offer
should show the sequence number, what it pays, and what it gets.

If the offer was immediately filled (unlikely on testnet with no counterparty),
the verification will report it as absent — that is also a valid DEX outcome.

<!-- action: verify_offer_present -->

## Step 7: Cancel the offer

Open offers tie up reserves and can be filled at any time. When you no longer
want to trade at that price, you cancel. This is an **OfferCancel** transaction
referencing the offer's sequence number.

Cancelling is a normal transaction that costs a fee but releases the reserve.

<!-- action: cancel_offer -->

## Step 8: Verify the offer is gone

After cancellation, the offer should no longer appear in your active offers.
This confirms the cancellation was processed by the ledger.

<!-- action: verify_offer_absent -->

## Checkpoint: What you proved

You just completed the DEX offer lifecycle:

1. **Created an offer** — placed an order on the XRPL's native order book
2. **Verified it was active** — confirmed the offer existed on-ledger
3. **Cancelled the offer** — removed it from the order book
4. **Confirmed cancellation** — verified the offer is gone

Key concepts to remember:
- **Native DEX**: the XRPL order book is built into the protocol, not a smart contract
- **TakerPays / TakerGets**: confusing at first, but remember — from the taker's perspective
- **Offer sequence**: every offer gets a sequence number you use to cancel it
- **Reserve impact**: each open offer costs 2 XRP reserve (released on cancel/fill)
- **Partial fills**: offers can be partially filled — the remaining amount stays on the book
- **Self-trading**: you cannot fill your own offers

Your report and transaction IDs are saved. Run `xrpl-lab proof-pack` to
export a shareable proof of what you did here.
