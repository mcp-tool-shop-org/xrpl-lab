---
id: dex_market_making_101
title: "DEX Market Making 101: Earning Spread on the Order Book"
track: dex
summary: Place bid and ask offers, verify spread, and clean up — your first strategy.
order: 10
time: 20-30 min
level: advanced
mode: testnet
requires:
  - dex_literacy
produces:
  - txid
  - report
checks:
  - "Baseline position captured"
  - "Bid offer placed on DEX"
  - "Ask offer placed on DEX"
  - "Both offers verified active"
  - "Both offers cancelled"
  - "Owner count returned to baseline"
---

You've already built and torn down DEX offers in DEX Literacy. Now you
use them with **intent**: to capture spread.

Market making means placing a buy (bid) and a sell (ask) on the same
pair, with a gap between them. If both fill, you profit the gap. If
only one fills, you're exposed to price risk — that's **inventory
risk**. If the price moves through your order, you bought high or
sold low — that's **adverse selection**.

This module is not financial advice. It's a controlled exercise in
placing, verifying, and cleaning up orders with a strategic frame.
Everything runs on the testnet — no real value at stake.

## Step 1: Ensure your wallet is ready

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create the issuer wallet

We need an issuer to provide LAB tokens for the sell side.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Set trust line for LAB

You need a LAB trust line to trade LAB/XRP. The issuer must exist
before the trust line can reference it.

<!-- action: set_trust_line currency=LAB limit=10000 -->

## Step 6: Issue LAB tokens to your wallet

You need LAB in hand to sell on the order book.

<!-- action: issue_token currency=LAB amount=500 -->

## Step 7: Snapshot baseline position

Capture your full position before placing any orders. This is your
clean starting point — we'll compare back to it at the end.

<!-- action: snapshot_position label=baseline -->

## Step 8: Place the bid (buy LAB with XRP)

Your bid offers to buy LAB by paying XRP. You're saying:
"I'll pay 1 XRP to get 10 LAB."

This is the lower side of your spread — you want to buy cheap.

<!-- action: strategy_offer_bid pays_currency=LAB pays_value=10 gets_currency=XRP gets_value=1 memo_action=OFFER_BID -->

## Step 9: Place the ask (sell LAB for XRP)

Your ask offers to sell LAB to get XRP. You're saying:
"I'll give 10 LAB if you pay me 2 XRP."

This is the upper side of your spread — you want to sell dear.
The spread between bid (1 XRP) and ask (2 XRP) is your profit
if both fill.

<!-- action: strategy_offer_ask pays_currency=LAB pays_value=10 gets_currency=XRP gets_value=2 memo_action=OFFER_ASK -->

## Step 10: Verify both offers are active

Check that both your bid and ask appear in your account's open offers.
Each offer is a live commitment on the ledger.

<!-- action: verify_module_offers -->

## Step 11: Snapshot after placing offers

Two new owned objects: one bid, one ask. Your owner count should
have increased by 2. Each locks 2 XRP in reserve.

<!-- action: snapshot_position label=after_offers -->

## Step 12: Compare baseline to after-offers

See the reserve impact of your open orders. Owner count should be
+2, and your XRP spendable decreased by the reserve lock.

<!-- action: verify_position_delta before=baseline after=after_offers -->

## Step 13: Cancel both offers

Clean up. Cancel both the bid and ask. In real market making,
you'd leave them live and manage fills. Here, we're practicing
the full lifecycle: place -> verify -> cancel -> verify.

<!-- action: cancel_module_offers -->

## Step 14: Verify offers are gone

Confirm both offers are absent from your active offer list.

<!-- action: verify_module_offers_absent -->

## Step 15: Snapshot final position

<!-- action: snapshot_position label=final -->

## Step 16: Verify cleanup

Compare baseline to final. Owner count should be back to baseline.
Balance will be slightly lower from transaction fees — that's the
cost of doing business on-ledger.

<!-- action: verify_position_delta before=baseline after=final -->

## Step 17: Hygiene summary

Final check: no leftover offers, no unexpected owner count growth.

<!-- action: hygiene_summary -->

## Checkpoint: What you proved

You just executed a complete market-making lifecycle:

1. **Captured baseline** — clean starting position
2. **Placed a bid and ask** — symmetric orders with a spread
3. **Verified active** — both offers live on the order book
4. **Measured reserve impact** — owner count +2, reserve locked
5. **Cancelled both** — cleaned up the orders
6. **Verified cleanup** — owner count back to baseline

Operator checklist for real market making:
- **Spread = profit margin**: wider spread = safer but less likely to fill
- **Inventory risk**: if only one side fills, you're exposed to direction
- **Adverse selection**: informed traders fill your stale orders
- **Reserve cost**: every open offer locks 2 XRP — dozens of offers
  locks significant reserve
- **Monitor and cancel stale orders**: never leave orders unattended

Run `xrpl-lab last-run` to see the audit command for this session.
