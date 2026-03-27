---
title: Beginners
description: New to the XRP Ledger? Start here.
sidebar:
  order: 99
---

New to the XRP Ledger? This page covers the core concepts you need before starting the modules.

## What is the XRP Ledger?

The XRP Ledger (XRPL) is a decentralized public blockchain. It processes transactions in seconds, has a built-in decentralized exchange (DEX), and supports issued currencies and automated market makers (AMMs) natively. XRPL Lab works exclusively on the **Testnet** -- a free sandbox that behaves like the real ledger but uses worthless test XRP. Nothing you do in XRPL Lab costs real money or touches real funds.

## Wallets and addresses

A wallet is your identity on the ledger. It consists of:

- **Address** (public) -- a string like `rHb9CJA...` that others use to send you XRP. Safe to share.
- **Seed** (secret) -- the private key that signs your transactions. Never share this.

XRPL Lab stores your wallet locally in `~/.xrpl-lab/wallet.json` with restrictive file permissions. Create one with:

```bash
xrpl-lab wallet create
```

View your address (no secrets shown) with:

```bash
xrpl-lab wallet show
```

## Funding and the testnet faucet

Before you can send transactions, your account needs XRP. On testnet, you get free XRP from the **faucet** -- a public service that deposits test XRP into your wallet.

```bash
xrpl-lab fund
```

The faucet typically grants enough XRP to complete all 12 modules. If you run low, call `fund` again.

## Transactions and receipts

Every action on the ledger is a **transaction**: a payment, a trust line change, a DEX offer, or an AMM deposit. Each transaction produces a **receipt** with:

- **Transaction ID (txid)** -- a unique hash that identifies it on the ledger forever
- **Result code** -- `tesSUCCESS` means it worked; codes starting with `tec`, `tef`, `tel`, or `tem` indicate different failure types
- **Ledger index** -- which ledger version included your transaction
- **Explorer URL** -- a link to view the transaction on testnet.xrpl.org

XRPL Lab records every transaction you submit. View your history with `xrpl-lab status`, or verify any single transaction:

```bash
xrpl-lab verify --tx <transaction_id>
```

## Trust lines and issued currencies

XRP is the native currency, but the ledger also supports **issued currencies** -- tokens created by any account. To hold an issued currency, you must first create a **trust line** to the issuer. A trust line says: "I trust this issuer to hold up to X units of this currency."

Module 3 (Trust Lines 101) walks you through the full lifecycle: creating an issuer account, setting a trust line, and issuing tokens. Module 4 teaches you what happens when trust lines fail and how to fix them.

## The DEX and order books

The XRPL has a built-in decentralized exchange. You trade by placing **offers** -- orders to buy or sell a currency pair. The ledger matches offers automatically.

Key concepts:

- **OfferCreate** -- place a new offer on the order book
- **OfferCancel** -- remove an offer you no longer want
- **Order book** -- the list of all open offers for a currency pair
- **Reserves** -- XRP that the ledger locks up for each object you own (offers, trust lines). Cancelling offers and removing trust lines frees reserves.

Modules 5 through 8 cover DEX operations, reserve math, account cleanup, and batch verification of your trading history.

## Dry-run mode

If you want to learn the workflow without a network connection, use dry-run mode:

```bash
xrpl-lab start --dry-run
```

Dry-run mode simulates every transaction locally. You get the same step-by-step flow, the same receipts, and the same artifacts -- but nothing touches the real testnet. This is useful for:

- Learning on a plane or in a restricted network
- Testing the CLI without waiting for network responses
- Understanding the module structure before committing real testnet resources

All commands that submit transactions accept `--dry-run`. When you are ready for the real thing, drop the flag and run against testnet.
