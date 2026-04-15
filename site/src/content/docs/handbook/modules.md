---
title: Modules
description: All 12 modules across five tracks.
sidebar:
  order: 2
---

XRPL Lab includes 12 modules organized into five tracks. Each module teaches one skill and produces a verifiable artifact. Prerequisites are explicit and enforced.

## Tracks

| Track | Focus | Mode |
|-------|-------|------|
| **foundations** | Wallet, payments, trust lines, error handling | testnet |
| **dex** | Offers, order books, market making, inventory | testnet |
| **reserves** | Account reserves, owner count, cleanup | testnet |
| **audit** | Batch verification, audit reports | testnet |
| **amm** | AMM liquidity, DEX vs AMM comparison | dry-run |

## Foundations

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 1 | Receipt Literacy | — | txid + verification report |
| 2 | Failure Literacy | Receipt Literacy | failed + fixed txid trail |
| 3 | Trust Lines 101 | — | trust line + token balance |
| 4 | Debugging Trust Lines | Trust Lines 101 | error → fix txid trail |

## DEX

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 5 | DEX Literacy | Trust Lines 101 | offer create + cancel txids |
| 10 | DEX Market Making 101 | DEX Literacy | strategy txids + hygiene report |
| 11 | Inventory Guardrails | DEX Market Making 101 | inventory check + guarded txids |

## Reserves

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 6 | Reserves 101 | Trust Lines 101 | before/after snapshot delta |
| 7 | Account Hygiene | Reserves 101 | cleanup verification report |

## Audit

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 8 | Receipt Audit | Receipt Literacy | audit pack (MD + CSV + JSON) |

## AMM (dry-run only)

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 9 | AMM Liquidity 101 | Trust Lines 101 | AMM lifecycle txids |
| 12 | DEX vs AMM Risk Literacy | DEX Market Making 101, AMM Liquidity 101 | comparison report |

## Running a module

```bash
xrpl-lab run <module_id>
```

The CLI will warn you if prerequisites aren't met. Use `xrpl-lab list` to see your progress, track, mode, and the next recommended module.
