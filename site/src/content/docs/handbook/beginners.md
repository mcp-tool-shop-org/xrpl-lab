---
title: For Beginners
description: New to XRPL Lab? Start here for a gentle introduction.
sidebar:
  order: 99
---

## What is this tool?

XRPL Lab is a hands-on training workbook for the XRP Ledger. Instead of reading documentation and hoping you understand it, you work through 12 structured modules that each teach one skill and produce a verifiable artifact -- a transaction ID, a signed receipt, or a diagnostic report.

Everything runs on the XRPL Testnet, a free sandbox that behaves like the real ledger but uses worthless test XRP. Nothing you do costs real money. The tool stores your wallet and progress locally on your machine, connects only to public testnet endpoints, and sends no telemetry.

## Who is this for?

- **Developers** learning XRPL fundamentals before building production applications
- **Students** studying blockchain technology who want hands-on practice with a real ledger
- **Analysts and auditors** who need to understand XRPL transaction receipts and verification
- **Anyone curious about the XRP Ledger** who prefers learning by doing over reading specs

No prior blockchain experience is required. The earliest modules start from zero and build up.

## Prerequisites

Before you begin, make sure you have:

- **Python 3.11 or newer** -- check with `python --version` or `python3 --version`
- **pip or pipx** -- pipx is recommended for CLI tools (`pip install pipx` if you do not have it)
- **Basic terminal skills** -- you should be comfortable running commands and reading output
- **An internet connection** -- needed to talk to the XRPL Testnet (or use `--dry-run` for fully offline mode)

You do not need:

- An XRPL mainnet account or real XRP
- Any cloud accounts, API keys, or registrations
- Prior experience with blockchain, the XRPL, or cryptography

## Your first 5 minutes

**1. Install XRPL Lab:**

```bash
pipx install xrpl-lab
```

**2. Verify the installation:**

```bash
xrpl-lab --version
```

You should see the version number printed.

**3. Launch the guided starter:**

```bash
xrpl-lab start
```

The launcher walks you through creating a wallet, funding it from the testnet faucet, and starting your first module (Receipt Literacy).

**4. Complete the first module:**

Follow the on-screen prompts. You will send a payment, read every field of the receipt, and verify the transaction on-ledger. When the module finishes, you get a transaction ID and verification report as proof.

**5. Check your progress:**

```bash
xrpl-lab status
```

This shows your wallet address, completed modules, and recent transactions.

## Common mistakes

**Forgetting to fund your wallet.** Before you can send transactions, your testnet wallet needs XRP. If you see `tecUNFUNDED_PAYMENT`, run `xrpl-lab fund` to request free test XRP from the faucet.

**Running without a wallet.** Commands that submit transactions require a wallet. If you see a "No wallet found" error, run `xrpl-lab wallet create` first.

**Confusing testnet with mainnet.** XRPL Lab only works on the Testnet. Your testnet XRP has no real value, and testnet addresses are not valid on mainnet. This is by design -- it keeps you safe while learning.

**Skipping module prerequisites.** Some modules build on earlier ones. Module 4 (Debugging Trust Lines) expects you to have completed Module 3 (Trust Lines 101). The guided launcher suggests the next module in order.

**Not checking doctor when something fails.** If a command produces unexpected errors, run `xrpl-lab doctor` before anything else. It checks your wallet, state file, workspace, network connectivity, and reports actionable hints for each problem it finds.

## Next steps

Once you have completed your first module:

- Read the [Getting Started](/xrpl-lab/handbook/getting-started/) guide for details on data storage and network usage
- Browse the [Modules](/xrpl-lab/handbook/modules/) page to see all 12 modules across the Foundations, DEX, Reserves, Audit, and AMM tracks
- Check the [Commands](/xrpl-lab/handbook/commands/) reference for every CLI command and flag
- Learn about [Artifacts](/xrpl-lab/handbook/artifacts/) -- proof packs, audit packs, and certificates that prove your work

## Glossary

| Term | Definition |
|------|------------|
| **XRPL** | XRP Ledger -- the decentralized public blockchain that XRPL Lab teaches you to use |
| **Testnet** | A free sandbox copy of the XRPL that uses worthless test XRP, safe for experimentation |
| **Wallet** | Your identity on the ledger, consisting of a public address and a secret seed (private key) |
| **Seed** | The secret key that signs your transactions. Never share it. Stored locally in `~/.xrpl-lab/wallet.json` |
| **Faucet** | A public service that gives out free testnet XRP for development and learning |
| **Transaction (tx)** | Any action on the ledger: a payment, trust line change, DEX offer, or AMM deposit |
| **Transaction ID (txid)** | A unique hash that identifies a transaction on the ledger permanently |
| **Result code** | The outcome of a transaction. `tesSUCCESS` means it worked; prefixes `tec`, `tef`, `tel`, `tem` indicate different failure categories |
| **Trust line** | A declaration that you trust an issuer to hold up to a specified amount of an issued currency |
| **DEX** | Decentralized Exchange -- the XRPL has a built-in order book for trading currency pairs |
| **AMM** | Automated Market Maker -- liquidity pools on the XRPL that trade algorithmically |
| **Reserves** | XRP the ledger locks for each object you own (offers, trust lines). Removing objects frees reserves |
| **Proof pack** | A shareable JSON record of your completed modules, transaction IDs, and explorer links with a SHA-256 integrity hash |
| **Dry-run mode** | Offline mode that simulates transactions locally without touching the network |
