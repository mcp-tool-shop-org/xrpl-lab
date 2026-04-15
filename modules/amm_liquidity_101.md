---
id: amm_liquidity_101
title: "AMM Liquidity 101: Providing Liquidity and Earning Fees"
order: 9
time: 20-30 min
level: advanced
dry_run_only: true
requires:
  - wallet
  - trust_lines_101
produces:
  - txid
  - report
checks:
  - "AMM pool exists for XRP/LAB"
  - "Deposit succeeded — LP tokens received"
  - "LP token balance increased"
  - "Withdrawal succeeded — LP tokens returned"
  - "Pool balances changed proportionally"
---

Welcome to AMM Liquidity 101. You've already worked with trust lines and
the DEX order book. Now you meet the other side of XRPL trading:
**Automated Market Makers**.

LP is not staking. You are depositing real assets into a shared pool.
Traders swap against your pool, and you earn a slice of every swap fee.
The tradeoff: if the price ratio moves, you may end up with less total
value than if you'd just held the assets — that's **impermanent loss**.

This module walks you through the full lifecycle:
create a pool (if needed) -> deposit -> verify -> withdraw -> verify.

## Step 1: Ensure your wallet is ready

You need a funded wallet with enough XRP for deposits and fees.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create an issuer wallet

We need an issuer for the LAB token. If you completed Trust Lines 101,
this pattern is familiar.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Set trust line for LAB

You need a trust line to the LAB issuer before receiving tokens.

<!-- action: set_trust_line currency=LAB limit=10000 -->

## Step 6: Issue LAB tokens

The issuer sends LAB tokens to your wallet. You need these to deposit
into the AMM pool alongside XRP.

<!-- action: issue_token currency=LAB amount=1000 -->

## Step 7: Snapshot before deposit

Capture your account state before interacting with the AMM. This
baseline helps you measure the reserve impact of LP positions.

<!-- action: snapshot_account label=before_amm -->

## Step 8: Ensure AMM pool exists

XRPL allows one AMM per asset pair. If no XRP/LAB pool exists, we
create one with small initial balances. The creator receives all
initial LP tokens.

Creating an AMM costs a special fee (higher than normal transactions)
and the pool is permanent — it belongs to a special AMM account on
the ledger.

<!-- action: ensure_amm_pair a_currency=XRP a_value=100 b_currency=LAB b_value=100 -->

## Step 9: Query AMM state

Look at the pool before your deposit: how much XRP, how much LAB,
what's the LP token supply, and what's the trading fee.

<!-- action: get_amm_info a_currency=XRP b_currency=LAB -->

## Step 10: Deposit into the AMM

You deposit both XRP and LAB proportionally. In return, you receive
LP tokens — these represent your share of the pool.

Think of LP tokens as a receipt: they prove how much of the pool
belongs to you. The AMM account issues them, and they behave like
any other issued token on XRPL (you can see them as trust lines).

<!-- action: amm_deposit a_currency=XRP a_value=10 b_currency=LAB b_value=10 -->

## Step 11: Verify LP tokens received

Check that your LP token balance increased. The pool balances should
also reflect your deposit.

<!-- action: verify_lp_received -->

## Step 12: Snapshot after deposit

<!-- action: snapshot_account label=after_deposit -->

## Step 13: Check reserve impact

Compare your account state before and after the deposit. Your owner
count may increase (LP trust line / AMM position), and your XRP
balance decreased by the deposit amount plus fees.

<!-- action: verify_reserve_change before=before_amm after=after_deposit -->

## Step 14: Withdraw from the AMM

Return your LP tokens to get your assets back. This is a proportional
withdrawal — you get back XRP and LAB in the current pool ratio,
which may differ from when you deposited (that's impermanent loss
in action, though in this exercise the ratio won't change).

<!-- action: amm_withdraw a_currency=XRP b_currency=LAB -->

## Step 15: Verify withdrawal

Confirm that your LP token balance decreased (or reached zero) and
that assets were returned from the pool.

<!-- action: verify_withdrawal -->

## Step 16: Snapshot after withdrawal

<!-- action: snapshot_account label=after_withdraw -->

## Step 17: Final comparison

Compare before-AMM to after-withdrawal. Your owner count should be
similar, though XRP balance will be slightly lower from transaction
fees. The key insight: you got your assets back, minus fees paid
to the network.

<!-- action: verify_reserve_change before=before_amm after=after_withdraw -->

## Checkpoint: What you proved

You just completed a full AMM liquidity cycle:

1. **Created an AMM pool** (or confirmed one existed) for XRP/LAB
2. **Deposited both assets** and received LP tokens as proof
3. **Verified LP receipt** — your pool share is on-ledger
4. **Withdrew your liquidity** by returning LP tokens
5. **Verified the withdrawal** — assets returned, LP tokens burned

Operator checklist for real AMM usage:
- **LP is not staking**: you earn fees, but take price risk
- **Impermanent loss**: if the price ratio moves significantly, you may
  have less total value than simply holding the assets
- **Fee earnings**: every swap through your pool pays a fee, split
  among all LPs proportionally
- **Reserve impact**: LP positions (trust lines to the AMM account)
  count as owned objects and lock reserve XRP
- **One AMM per pair**: you can't create a competing pool for the
  same asset pair — all liquidity is concentrated

Your report and transaction IDs are saved. Run `xrpl-lab proof-pack` to
export a shareable proof of what you did here.
