# XRPL DEX — Reference Notes

Quick reference for the DEX Literacy module. These are the concepts you
should understand after completing the module.

## TakerPays vs TakerGets

The naming is from the **taker's** perspective (the person filling your offer):

| Field       | Taker's view          | Your view (maker)     |
| ----------- | --------------------- | --------------------- |
| TakerPays   | What the taker pays   | What you receive      |
| TakerGets   | What the taker gets   | What you give up      |

Example: "I want to buy 50 LAB for 10 XRP"
- TakerPays = 50 LAB (the taker pays LAB to fill your offer → you receive LAB)
- TakerGets = 10 XRP (the taker gets your XRP → you give up XRP)

## Offer Sequence

Every OfferCreate transaction gets a **sequence number** from the account's
transaction sequence. This number is how you reference the offer later — for
cancellation or programmatic tracking.

## OfferCancel

Cancellation is a normal transaction that:
- Costs a fee (like any transaction)
- Releases the owner reserve (currently 0.2 XRP per owned object on mainnet)
- Removes the offer from the order book

You can only cancel your own offers.

## Partial Fills

Offers can be **partially filled**. If someone only wants 5 of your 50 LAB,
the remaining 45 stays on the order book. The offer object is updated in place.

## Reserve Impact

Each open offer increases the account's **owner reserve** by one owner-reserve
increment — currently **0.2 XRP** per owned object on mainnet (lowered from
2 XRP by the 2024-12-02 reserve reduction). This figure is **network-governed**
via validator fee-voting and may drift over time, and **testnet sets its own
reserve**, so do not hard-code it. Cancelling or having the offer filled
releases the reserve.

## Self-Trading

You cannot fill your own offers. The XRPL prevents self-trading at the
protocol level.

## Order Book Matching

The XRPL matches offers automatically at submission time. If your OfferCreate
crosses an existing offer at an equal or better price, it fills immediately
(fully or partially). Any remainder sits on the order book.

## Relevant Result Codes

| Code                | Meaning                                    |
| ------------------- | ------------------------------------------ |
| tesSUCCESS          | Offer placed (or filled) successfully      |
| tecUNFUNDED_OFFER   | Account doesn't have the offered asset     |
| tecEXPIRED          | Offer expired before execution             |
| tecKILLED           | Offer with tfImmediateOrCancel was killed   |
