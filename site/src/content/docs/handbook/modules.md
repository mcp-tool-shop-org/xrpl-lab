---
title: Modules
description: All 12 modules across three tracks.
sidebar:
  order: 2
---

XRPL Lab includes 12 modules organized into three tracks: Beginner, Intermediate, and Advanced. Each module teaches one skill and produces a verifiable artifact.

## Beginner track

| # | Module | What you learn | What you prove |
|---|--------|----------------|----------------|
| 1 | Receipt Literacy | Send a payment, read every receipt field | txid + verification report |
| 2 | Failure Literacy | Break a tx on purpose, diagnose, fix, resubmit | failed + fixed txid trail |
| 3 | Trust Lines 101 | Create issuer, set trust line, issue tokens | trust line + token balance |
| 4 | Debugging Trust Lines | Intentional trust line failure, error decode, fix | error → fix txid trail |

The beginner track focuses on fundamental XRPL operations: sending payments, reading receipts, creating trust lines, and learning how to diagnose and fix failures.

## Intermediate track

| # | Module | What you learn | What you prove |
|---|--------|----------------|----------------|
| 5 | DEX Literacy | Create offers, read order books, cancel | offer create + cancel txids |
| 6 | Reserves 101 | Account snapshots, owner count, reserve math | before/after snapshot delta |
| 7 | Account Hygiene | Cancel offers, remove trust lines, free reserves | cleanup verification report |
| 8 | Receipt Audit | Batch verify transactions with expectations | audit pack (MD + CSV + JSON) |

The intermediate track teaches DEX operations, reserve management, account cleanup, and batch verification.

## Advanced track

| # | Module | What you learn | What you prove |
|---|--------|----------------|----------------|
| 9 | AMM Liquidity 101 | Create pool, deposit, earn LP, withdraw | AMM lifecycle txids |
| 10 | DEX Market Making 101 | Bid/ask offers, position snapshots, cleanup | strategy txids + hygiene report |
| 11 | Inventory Guardrails | Threshold-based quoting, safe-side-only placement | inventory check + guarded txids |
| 12 | DEX vs AMM Risk Literacy | Side-by-side DEX and AMM lifecycle comparison | comparison report + audit trail |

The advanced track covers AMM liquidity, market making strategies, inventory management, and comparative risk analysis.

## Running a module

```bash
xrpl-lab run <module_id>
```

For example, to run the Receipt Literacy module:

```bash
xrpl-lab run receipt_literacy
```

Check your progress at any time:

```bash
xrpl-lab list
```
