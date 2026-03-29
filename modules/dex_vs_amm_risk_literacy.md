---
id: dex_vs_amm_risk_literacy
title: "DEX vs AMM Risk Literacy: Comparing Trading Strategies"
order: 12
time: 25-35 min
level: advanced
requires:
  - wallet
  - dex_market_making_101
  - amm_liquidity_101
produces:
  - txid
  - report
checks:
  - "DEX offer lifecycle completed"
  - "AMM liquidity lifecycle completed"
  - "Both strategies compared"
  - "All positions cleaned up"
---

You've now used both sides of XRPL trading: the **DEX order book**
(explicit bids and asks) and the **AMM pool** (passive liquidity
provision). This capstone module puts them side by side so you can
compare risks, costs, and behavior.

This is not about which is "better." It's about understanding the
tradeoffs so you can choose the right tool for the situation.

**DEX order book:**
- You control the exact price
- Your offer sits until filled or cancelled
- You pay a fee per transaction (create + cancel)
- You only trade when someone takes your offer

**AMM pool:**
- You deposit both assets and earn swap fees
- The price adjusts automatically (constant product)
- You face impermanent loss if the price ratio changes
- You pay fees to deposit and withdraw

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

Enough tokens for both the DEX and AMM exercises.

<!-- action: issue_token currency=LAB amount=1000 -->

## Step 7: Snapshot baseline

Capture your position before either strategy runs.

<!-- action: snapshot_position label=baseline -->

## Step 8: DEX strategy — place bid

Place a buy order on the DEX order book.

<!-- action: strategy_offer_bid pays_currency=LAB pays_value=10 gets_currency=XRP gets_value=1 memo_action=COMPARE_BID -->

## Step 9: DEX strategy — place ask

Place a sell order on the DEX order book.

<!-- action: strategy_offer_ask pays_currency=LAB pays_value=10 gets_currency=XRP gets_value=2 memo_action=COMPARE_ASK -->

## Step 10: Verify DEX offers

Confirm both offers are live on the ledger.

<!-- action: verify_module_offers -->

## Step 11: Snapshot after DEX

<!-- action: snapshot_position label=after_dex -->

## Step 12: DEX position delta

See the cost of placing DEX offers: owner count +2, reserve locked.

<!-- action: verify_position_delta before=baseline after=after_dex -->

## Step 13: Cancel DEX offers

Clean up the DEX side.

<!-- action: cancel_module_offers -->

## Step 14: Verify DEX offers gone

<!-- action: verify_module_offers_absent -->

## Step 15: Snapshot after DEX cleanup

<!-- action: snapshot_position label=after_dex_cleanup -->

## Step 16: AMM strategy — ensure pool

Create or confirm the XRP/LAB AMM pool.

<!-- action: ensure_amm_pair a_currency=XRP a_value=100 b_currency=LAB b_value=100 -->

## Step 17: AMM strategy — deposit

Deposit into the AMM pool.

<!-- action: amm_deposit a_currency=XRP a_value=10 b_currency=LAB b_value=10 -->

## Step 18: Verify LP tokens received

<!-- action: verify_lp_received -->

## Step 19: Snapshot after AMM deposit

<!-- action: snapshot_position label=after_amm -->

## Step 20: AMM position delta

Compare baseline to after-AMM: owner count may increase (LP trust line),
XRP and LAB balances decreased by deposit amounts.

<!-- action: verify_position_delta before=after_dex_cleanup after=after_amm -->

## Step 21: AMM strategy — withdraw

Return your LP tokens and get your assets back.

<!-- action: amm_withdraw a_currency=XRP b_currency=LAB -->

## Step 22: Verify withdrawal

<!-- action: verify_withdrawal -->

## Step 23: Snapshot final

<!-- action: snapshot_position label=final -->

## Step 24: Final comparison

Compare your baseline to your final position. You should be back
roughly where you started, minus transaction fees.

<!-- action: verify_position_delta before=baseline after=final -->

## Step 25: Hygiene summary

<!-- action: hygiene_summary -->

## Checkpoint: What you proved

You ran both strategies back-to-back and compared the results:

| Dimension | DEX Order Book | AMM Pool |
|-----------|---------------|----------|
| Control | Exact price | Automatic pricing |
| Cost | Fee per tx (create + cancel) | Fee per deposit + withdraw |
| Risk | Offer sits unfilled | Impermanent loss |
| Reserve | +1 owner per offer | +1 owner for LP position |
| Earnings | Only when filled | Continuous swap fees |

Operator rules:
- **DEX for precision**: when you want a specific price and are willing to wait
- **AMM for passive income**: when you want to earn fees without active management
- **Both cost reserve XRP**: owned objects lock reserves
- **Both need cleanup**: leftover offers or LP positions cost you reserves
- **Neither is free**: you always pay transaction fees to enter and exit
- **Know your strategy before you start**: don't mix approaches without understanding why

Your report and transaction IDs are saved. Run `xrpl-lab last-run` to
see the audit command for this session.
