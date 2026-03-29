---
id: dex_inventory_guardrails
title: "DEX Inventory Guardrails: Don't Get Lopsided"
time: 15-20 min
level: advanced
requires:
  - wallet
  - dex_market_making_101
produces:
  - txid
  - report
checks:
  - "Inventory check evaluated"
  - "Only safe sides were quoted"
  - "Offers cancelled and cleaned up"
  - "Owner count returned to baseline"
---

You learned to place both sides of a market in DEX Market Making 101.
Now the hard question: **should you always quote both sides?**

If your XRP balance is low, placing a bid means locking reserve XRP you
can't afford. If your LAB balance is low, placing an ask means selling
tokens you don't have enough of to deliver.

Inventory guardrails prevent lopsided exposure. Before placing offers,
you check your balances against minimum thresholds and only quote the
sides you can safely cover.

## Step 1: Ensure your wallet is ready

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create an issuer wallet

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Set trust line for LAB

<!-- action: set_trust_line currency=LAB limit=10000 -->

## Step 6: Issue LAB tokens

We issue a moderate amount so the guardrail has something to check.

<!-- action: issue_token currency=LAB amount=500 -->

## Step 7: Snapshot baseline position

Capture your position before any strategy activity.

<!-- action: snapshot_position label=baseline -->

## Step 8: Check inventory thresholds

The guardrail evaluates your XRP and LAB balances against minimum
thresholds. If XRP is too low, it blocks bids. If LAB is too low,
it blocks asks. If both are healthy, both sides are allowed.

<!-- action: check_inventory currency=LAB min_xrp_drops=20000000 min_token=10 -->

## Step 9: Place only safe sides

Based on the inventory check, we place only the offers that are safe.
If both sides are allowed, you get a two-sided quote. If only one
side is safe, you get a one-sided quote. If neither is safe, nothing
is placed.

<!-- action: place_safe_sides pays_currency=LAB gets_currency=XRP bid_value=10 ask_value=10 bid_price=1 ask_price=2 -->

## Step 10: Verify placed offers

Confirm that only the allowed offers actually exist on the ledger.

<!-- action: verify_module_offers -->

## Step 11: Snapshot after offers

<!-- action: snapshot_position label=after_offers -->

## Step 12: Verify position delta

<!-- action: verify_position_delta before=baseline after=after_offers -->

## Step 13: Cancel all strategy offers

Clean up: cancel everything from this module.

<!-- action: cancel_module_offers -->

## Step 14: Verify offers are gone

<!-- action: verify_module_offers_absent -->

## Step 15: Snapshot final position

<!-- action: snapshot_position label=final -->

## Step 16: Hygiene summary

<!-- action: hygiene_summary -->

## Checkpoint: What you proved

You just ran a guarded market-making cycle:

1. **Checked inventory** before placing any offers
2. **Quoted only safe sides** — no blind two-sided exposure
3. **Verified** that only allowed offers were on the ledger
4. **Cleaned up** all offers and verified owner count

Operator rules for inventory management:
- **Never quote a side you can't cover** — the guardrail prevents this
- **XRP reserve matters** — placing a bid locks reserve; check spendable first
- **Token balance matters** — selling tokens you barely have creates delivery risk
- **Re-check before every cycle** — balances change after every trade
- **One-sided is fine** — a single-sided quote is safer than a reckless two-sided one

Your report and transaction IDs are saved. Run `xrpl-lab last-run` to
see the audit command for this session.
