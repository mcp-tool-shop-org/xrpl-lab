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
| `xrpl-lab feedback` | Alias for support-bundle (markdown output) |

## Facilitator commands

| Command | Description |
|---------|-------------|
| `xrpl-lab cohort-status [--dir DIR] [--format FORMAT]` | Aggregate per-learner status across a cohort directory (one subdirectory per learner). JSON includes `all_verified` / `unverified` / `has_proof` / `has_cert` |
| `xrpl-lab session-export [--dir DIR] [--format FORMAT] [--outfile FILE]` | Archive every learner's shareable artifacts (proofs, reports, audit packs, certificates) with a SHA-256 manifest — never includes wallet or state files |

## Module authoring

| Command | Description |
|---------|-------------|
| `xrpl-lab lint [glob] [--json] [--no-curriculum]` | Validate module files and curriculum (default glob `modules/*.md`) |
| `xrpl-lab module init --id ID --track TRACK --title TITLE --time TIME` | Scaffold a lint-passing module skeleton at `modules/<id>.md` |
| `xrpl-lab curriculum manifest` | Print the canonical curriculum manifest, the single source the README and handbook track lists are generated from |

## Artifact commands

| Command | Description |
|---------|-------------|
| `xrpl-lab proof-pack` | Export a shareable proof pack (JSON with SHA-256 integrity) |
| `xrpl-lab certificate` | Export a slim completion certificate |
| `xrpl-lab audit --txids <file>` | Batch verify transactions against expectations |
| `xrpl-lab verify-artifact <file> [--json] [--live]` | Verify any artifact: it detects proof packs, certificates, audit packs and support bundles from their own JSON and runs the same check as that kind's own command |

### Ledger-anchored verification (`--live`)

The offline SHA-256 check always runs. With `--live`, `verify-artifact` also re-fetch every transaction a proof pack or certificate claims from the public XRPL and confirm each one is there as claimed. Audit packs and support bundles have nothing on the ledger to check, so `--live` says so and changes nothing.

#### After a test network reset

Testnet and Devnet are sometimes reset, which deletes every account and transaction on them. Both are reset on **2026-11-25** ([xrpl.org notice](https://xrpl.org/blog/2026/testnet-devnet-reset)). A proof pack issued before a reset keeps its hash, but its transactions are on no ledger any more.

`--live` reports each such transaction as `RESET`, with the verdict **can't be checked (ledger reset after issuance)**, and exits with code **4**:

| Exit code | Meaning |
|-----------|---------|
| `0` | The hash is intact and, with `--live`, every transaction was confirmed on the ledger |
| `1` | The hash check failed, or a transaction is missing or not as claimed |
| `4` | The hash is intact and nothing was found false, but the network was reset after issuance, so the transactions can't be checked |

`RESET` is not a pass. A pack listing made-up transactions dated before the reset reads the same way, so a reset pack is never reported as verified: only its offline hash remains, and a hash shows the file is unedited, not that the transactions happened. To get a pack that verifies on-ledger again, re-run the modules after the reset and export a new pack.

The notice gives the reset's day but not its hour, so the announced reset covers every transaction recorded before the 25th has ended everywhere: **2026-11-26 12:00 UTC**. A transaction recorded after the wipe but before that time, and missing from the ledger, reads `RESET` where it would otherwise read `FAIL`. Neither is a pass.

#### Getting going again after a reset

A reset deletes your account from the network. Your wallet file, its address, your progress and your reports are untouched.

1. `xrpl-lab doctor` shows a **Network reset** warning when completed modules lost their on-ledger results.
2. `xrpl-lab recovery` lists the commands for your case.
3. `xrpl-lab fund` funds the same address again from the faucet.
4. `xrpl-lab run <module> --force` re-runs a module, so it is proven on the new ledger.
5. `xrpl-lab proof-pack` exports a new pack. Its re-run modules verify with `--live`; modules you did not re-run still read `RESET`.

#### Who says there was a reset

Exit code 4 always comes with the signal the verdict rests on, in the output and in `--json` (`reset_signal`):

| Signal | What it means | Verdict |
|--------|---------------|---------|
| `announced` | A listed, announced reset covers the time the transaction was recorded | `RESET`: can't be checked |
| `seen_by_this_lab` | The lab running the check saw the reset itself, in its own state (`ledger_epochs`, or its own ledger mark now above the network's) | `RESET`: can't be checked |
| `pack_claim` | Only the pack says so: its `ledger_marks` or its `ledger_resets_seen`. Anyone can write those fields | `UNCONFIRMED`: the pack claims a reset that nothing else confirms |

The first two do not depend on the pack. The third is a claim, not evidence. When transactions rest on different signals, the weakest one names the result. None of the three is ever a pass.

A pack that records a ledger index above the network's current one, when no reset is known, is flagged as a **suspicious ledger mark** (`suspicious_ledger_marks` in `--json`).

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
| `xrpl-lab reset` | Wipe local state + workspace (requires typing RESET to confirm). Your wallet is always preserved — reset never touches `~/.xrpl-lab/wallet.json` |
| `xrpl-lab reset --module <module_id>` | Granular per-module reset — clear one module's state and workspace artifacts only, keep everything else |

### Granular reset flags

| Flag | Description |
|------|-------------|
| `--module <module_id>` | Reset only the named module (removes it from `completed_modules`, clears its tx records and workspace report). Wallet, other modules, and audit packs are preserved |
| `--confirm` | Skip the confirmation prompt (granular `--module` mode only) |
| `--keep-wallet` | Deprecated no-op — `reset` always preserves the wallet; kept (hidden) for backward compatibility |

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

In **production**, build the site once (`cd site && npm run build`) and then `xrpl-lab serve` hosts **both** the API and the built dashboard from one process: on start-up it looks for a built dashboard at `$XRPL_LAB_DASHBOARD_DIR` or `./site/dist`, and when it finds one it mounts it in-process at `/xrpl-lab/app/`. If no built dashboard is found, `serve` hosts the API only and prints how to start the dashboard separately. The bundled dashboard calls the API at `localhost:8321`, so keep the default port when using the in-process dashboard.

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
