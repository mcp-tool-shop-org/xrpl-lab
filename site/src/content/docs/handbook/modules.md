---
title: Modules
description: All 16 modules across nine tracks.
sidebar:
  order: 2
---

XRPL Lab includes 16 modules organized into nine tracks. Each module teaches one skill and produces a verifiable artifact. Prerequisites are explicit and enforced.

## Tracks

| Track | Focus | Mode |
|-------|-------|------|
| **foundations** | Wallet, payments, trust lines, error handling | testnet |
| **nfts** | NFT game assets: minting, collections, royalties (XLS-20) | testnet |
| **tokens** | Multi-Purpose Token (MPT) game-currency issuance (XLS-33) | testnet |
| **payments** | Escrow & time-locked value | testnet |
| **identity** | Decentralized Identifiers (DID, XLS-40) | testnet |
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

## NFTs

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 13 | NFT Minting 101 | — | NFTokenID + on-ledger verify |

## Tokens

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 14 | MPT Issuance 101 | — | issuance id + on-ledger verify |

## Payments

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 15 | Escrow 101 | — | escrow object + FinishAfter |

## Identity

| # | Module | Prerequisites | What you prove |
|---|--------|---------------|----------------|
| 16 | DID 101 | — | DID object + URI |

## Running a module

```bash
xrpl-lab run <module_id>
```

The CLI will warn you if prerequisites aren't met. Use `xrpl-lab list` to see your progress, track, mode, and the next recommended module.
