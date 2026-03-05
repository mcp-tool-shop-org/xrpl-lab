---
title: Commands
description: Full CLI reference.
sidebar:
  order: 3
---

## Core commands

| Command | Description |
|---------|-------------|
| `xrpl-lab start` | Guided launcher — walks through wallet setup, funding, and first module |
| `xrpl-lab list` | Show all modules with completion status |
| `xrpl-lab run <module_id>` | Run a specific module |
| `xrpl-lab status` | Show progress, wallet info, and recent transactions |
| `xrpl-lab last-run` | Show details of the last module run + suggested audit command |

## Artifact commands

| Command | Description |
|---------|-------------|
| `xrpl-lab proof-pack` | Export a shareable proof pack (JSON with SHA-256 integrity) |
| `xrpl-lab certificate` | Export a slim completion certificate |
| `xrpl-lab audit` | Batch verify transactions against expectations |

## Wallet commands

| Command | Description |
|---------|-------------|
| `xrpl-lab wallet create` | Create a new testnet wallet |
| `xrpl-lab wallet show` | Show wallet info (no secrets displayed) |
| `xrpl-lab fund` | Fund wallet from the testnet faucet |
| `xrpl-lab send` | Send a payment |
| `xrpl-lab verify --tx <id>` | Verify a single transaction on-ledger |

## Utility commands

| Command | Description |
|---------|-------------|
| `xrpl-lab doctor` | Run diagnostic checks |
| `xrpl-lab self-check` | Alias for doctor |
| `xrpl-lab feedback` | Generate issue-ready markdown for bug reports |
| `xrpl-lab reset` | Wipe local state (requires RESET confirmation) |

## Global flags

All commands support `--dry-run` for offline mode where applicable. Dry-run mode simulates transactions without touching the network — useful for learning the workflow or working without an internet connection.
