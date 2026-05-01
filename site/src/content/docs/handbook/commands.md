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
| `xrpl-lab status [--json]` | Progress, curriculum position, blockers, track progress |
| `xrpl-lab tracks` | Track-level completion summaries — what was actually practiced |
| `xrpl-lab recovery` | Diagnose stuck states and show recovery commands |
| `xrpl-lab last-run` | Show details of the last module run + suggested audit command |
| `xrpl-lab --version` | Print the installed version and exit |

## Workshop commands

| Command | Description |
|---------|-------------|
| `xrpl-lab support-bundle` | Generate a support bundle (markdown) for facilitator handoff |
| `xrpl-lab support-bundle --json` | Machine-parseable JSON support bundle |
| `xrpl-lab support-bundle --verify <file>` | Verify a received support bundle |
| `xrpl-lab feedback` | Alias for support-bundle (markdown output) |

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
| `xrpl-lab reset` | Wipe local state (requires typing RESET to confirm; add `--keep-wallet` to preserve wallet) |
| `xrpl-lab reset --module <module_id>` | Granular per-module reset — clear one module's state and workspace artifacts only, keep everything else |

### Granular reset flags

| Flag | Description |
|------|-------------|
| `--module <module_id>` | Reset only the named module (removes it from `completed_modules`, clears its tx records and workspace report). Wallet, other modules, and audit packs are preserved |
| `--confirm` | Skip the confirmation prompt (granular `--module` mode only) |
| `--keep-wallet` | Whole-state reset, but keep the wallet file |

## `xrpl-lab serve` — web dashboard

`xrpl-lab serve` starts the FastAPI backend that drives the bundled web dashboard. Facilitators use it during workshops for at-a-glance cohort monitoring, kill-switch control of in-flight runs, and a click-through artifact viewer; integration users hit the same surface programmatically via REST + WebSocket.

```bash
# Start the API on the default port
xrpl-lab serve

# Custom port + offline sandbox for a demo cohort
xrpl-lab serve --port 9000 --dry-run
```

API docs are auto-published at `http://<host>:<port>/docs` once the server is running.

### Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--port <N>` | `8321` | API server port. The dashboard's frontend hardcodes `http://localhost:8321` for `fetch` calls, so non-default ports require you to drive the API directly (curl, custom client) rather than the bundled UI |
| `--host <H>` | `127.0.0.1` | Bind address. Stays on loopback by default — workshop threat-model line. Override only when you understand the exposure (e.g., a trusted LAN-only facilitator station) |
| `--dry-run` | off | Run the entire dashboard surface in offline-sandbox mode. Useful for projector demos with no internet, or for facilitators rehearsing the workshop flow without funding wallets |

### Dev vs production

In **development**, the Astro site runs separately on port 4321:

```bash
# Terminal 1 — API
xrpl-lab serve

# Terminal 2 — Astro dev server (hot reload)
cd site && npm run dev
```

Open `http://localhost:4321/xrpl-lab/app/` to use the dashboard.

In **production** (after `cd site && npm run build`), the FastAPI app serves both the API surface and the built dashboard from one process — `xrpl-lab serve` is the only command you need.

### Why this matters for facilitators

The dashboard is the surface most workshop facilitators run on a second monitor while the cohort works in their own terminals. It is the live cohort view: per-run module ID, status, queue depth, kill button on stuck runs, capacity badge. See the [facilitator dashboard](/xrpl-lab/handbook/facilitator-dashboard/) page for what each piece of that surface tells you and how the kill-switch semantics work.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `XRPL_LAB_RPC_URL` | Override the default XRPL Testnet RPC endpoint |
| `XRPL_LAB_FAUCET_URL` | Override the default testnet faucet URL |

Both overrides are reported by `xrpl-lab status` and `xrpl-lab doctor` when set.

## Global flags

All commands support `--dry-run` for offline mode where applicable. Dry-run mode simulates transactions without touching the network — useful for learning the workflow or working without an internet connection.
