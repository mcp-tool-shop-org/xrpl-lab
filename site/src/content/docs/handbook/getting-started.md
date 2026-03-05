---
title: Getting Started
description: Install, configure, and start learning.
sidebar:
  order: 1
---

## Install

With pipx (recommended):

```bash
pipx install xrpl-lab
```

Or with pip:

```bash
pip install xrpl-lab
```

Requires Python 3.11+.

## Start learning

The guided launcher walks you through wallet setup, funding, and your first module:

```bash
xrpl-lab start
```

## Offline mode

No internet required. Use dry-run for simulated transactions:

```bash
xrpl-lab start --dry-run
```

All commands support `--dry-run` where applicable, letting you learn the workflow without touching the network.

## What happens on first run

1. `xrpl-lab start` launches the guided launcher
2. You create a wallet (stored locally in `~/.xrpl-lab/wallet.json`)
3. The faucet funds your testnet wallet
4. You choose a module and work through it
5. Each module produces a verifiable artifact (transaction ID, report, etc.)

## Data storage

All state lives locally:

- **Wallet** — `~/.xrpl-lab/wallet.json` (with restrictive file permissions)
- **Progress** — `~/.xrpl-lab/state.json` (module status, transaction IDs)
- **Workspace** — `./.xrpl-lab/` in the current directory for module outputs

## Network usage

- **XRPL Testnet RPC** — public endpoint, transactions signed locally before submission
- **Testnet faucet** — public HTTP, only your address is sent
- Both endpoints are overridable via environment variables
- Both are optional with `--dry-run`
