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

## Verify your installation

After installing, confirm everything works:

```bash
xrpl-lab --version
xrpl-lab doctor
```

The `doctor` command checks your wallet, state file, workspace, RPC endpoint, and faucet connectivity. It reports actionable hints for anything that needs attention.

## What happens on first run

1. `xrpl-lab start` launches the guided launcher
2. If an XRPL Camp certificate is detected, you can reuse that wallet
3. You create a wallet (stored locally in `~/.xrpl-lab/wallet.json`)
4. The faucet funds your testnet wallet
5. You choose a module and work through it
6. Each module produces a verifiable artifact (transaction ID, report, etc.)

## Curriculum and tracks

Modules are organized into five tracks with explicit prerequisites:

- **foundations** — wallet, payments, trust lines, error handling
- **dex** — offers, order books, market making, inventory management
- **reserves** — account reserves, owner count, cleanup
- **audit** — batch verification, audit reports
- **amm** — automated market maker liquidity (dry-run only)

Prerequisites are enforced: `xrpl-lab start` always suggests the next valid module
based on what you've completed. Use `xrpl-lab list` to see all modules with track,
mode, and progression status.

Each module has a **mode**: `testnet` (real transactions) or `dry-run` (offline sandbox).
Some modules (AMM) require dry-run because the testnet may not have AMM pairs.

## Validating modules

Authors can lint module files for correctness:

```bash
xrpl-lab lint                     # lint all modules
xrpl-lab lint modules/dex*.md     # lint a subset
xrpl-lab lint --json              # CI-friendly JSON output
```

The linter validates frontmatter, action names, payload schemas, mode labeling,
prerequisite references, and curriculum structure.

## Data storage

All state lives locally:

- **Wallet** — `~/.xrpl-lab/wallet.json` (with restrictive file permissions)
- **Progress** — `~/.xrpl-lab/state.json` (module status, transaction IDs)
- **Workspace** — `./.xrpl-lab/` in the current directory for module outputs

### What survives a browser close, reboot, or migration

- **Browser close** — progress is saved to `~/.xrpl-lab/state.json` after each
  module step via atomic write-then-rename. Closing or refreshing the dashboard
  does not lose progress; reopening picks up where the learner left off.
- **Machine reboot** — state survives the reboot. Resume by reopening the
  dashboard or running `xrpl-lab status` to see what's next.
- **Moving to a new machine** — copy `~/.xrpl-lab/` to the new machine to bring
  both the wallet and progress with you. There is no separate export command;
  the directory itself is the portable bundle. Preserve file permissions on
  `wallet.json` after the copy.

## Network usage

- **XRPL Testnet RPC** — public endpoint, transactions signed locally before submission
- **Testnet faucet** — public HTTP, only your address is sent
- Both endpoints are overridable via environment variables:
  - `XRPL_LAB_RPC_URL` — custom RPC endpoint
  - `XRPL_LAB_FAUCET_URL` — custom faucet endpoint
- Both are optional with `--dry-run`

## Workshop use

XRPL Lab works in real teaching settings — no accounts, no telemetry,
no cloud. Everything runs locally.

### Facilitator view

Check any learner's status in under 10 seconds:

```bash
xrpl-lab status        # where are they, what's blocked, what's next
xrpl-lab tracks        # track-level completion: what was actually practiced
xrpl-lab recovery      # stuck? see exactly what to run
```

### Support handoff

When a learner needs help:

```bash
xrpl-lab support-bundle         # generates a markdown summary
xrpl-lab support-bundle --json  # or machine-parseable JSON
```

The bundle includes curriculum position, blockers, environment, doctor results, and recent transactions. No secrets.

### Common workshop flows

**All-offline sandbox** (no internet):
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Mixed offline + testnet** (most common):
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Camp → Lab progression**:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```
