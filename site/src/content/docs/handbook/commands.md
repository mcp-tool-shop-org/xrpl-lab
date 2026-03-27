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
| `xrpl-lab list` | Show all modules with completion status in a formatted table |
| `xrpl-lab run <module_id>` | Run a specific module (add `--force` to redo a completed module) |
| `xrpl-lab status` | Show progress, wallet info, env overrides, and recent transactions |
| `xrpl-lab last-run` | Show details of the last module run + suggested audit command |
| `xrpl-lab --version` | Print the installed version and exit |

## Artifact commands

| Command | Description |
|---------|-------------|
| `xrpl-lab proof-pack` | Export a shareable proof pack (JSON with SHA-256 integrity) |
| `xrpl-lab certificate` | Export a slim completion certificate |
| `xrpl-lab audit --txids <file>` | Batch verify transactions against expectations |

### Audit flags

| Flag | Description |
|------|-------------|
| `--txids <file>` | Required. File with one transaction ID per line |
| `--expect <file>` | Optional expectations JSON file (type checks, memo prefix, etc.) |
| `--csv <path>` | Write a CSV report to this path |
| `--md <path>` | Write a Markdown report to this path |
| `--dry-run` | Use the dry-run transport for verification |

## Wallet commands

| Command | Description |
|---------|-------------|
| `xrpl-lab wallet create` | Create a new testnet wallet (add `--path <dir>` for custom location) |
| `xrpl-lab wallet show` | Show wallet info (no secrets displayed) |
| `xrpl-lab fund` | Fund wallet from the testnet faucet |
| `xrpl-lab send --to <addr> --amount <xrp>` | Send a payment (optional `--memo <text>`) |
| `xrpl-lab verify --tx <id>` | Verify a single transaction on-ledger |

## Utility commands

| Command | Description |
|---------|-------------|
| `xrpl-lab doctor` | Run diagnostic checks (wallet, state, workspace, env overrides, RPC, faucet, last error) |
| `xrpl-lab self-check` | Alias for doctor |
| `xrpl-lab feedback` | Generate issue-ready markdown for bug reports |
| `xrpl-lab reset` | Wipe local state (requires typing RESET to confirm; add `--keep-wallet` to preserve wallet) |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `XRPL_LAB_RPC_URL` | Override the default XRPL Testnet RPC endpoint |
| `XRPL_LAB_FAUCET_URL` | Override the default testnet faucet URL |

Both overrides are reported by `xrpl-lab status` and `xrpl-lab doctor` when set.

## Global flags

All commands support `--dry-run` for offline mode where applicable. Dry-run mode simulates transactions without touching the network — useful for learning the workflow or working without an internet connection.
