---
title: Artifacts
description: Proof packs, audit packs, and certificates.
sidebar:
  order: 4
---

Every XRPL Lab module produces a verifiable artifact. These artifacts prove you completed the work and can be independently verified against the XRP Ledger.

## Proof packs

**File:** `xrpl_lab_proof_pack.json`

A shareable record of completed modules containing:

- Module names and completion timestamps
- Transaction IDs with explorer links
- Receipt table with human-readable transaction summaries
- Success/failure counts
- SHA-256 integrity hash

Proof packs never contain secrets (wallet seeds, private keys). They are safe to share publicly.

Generate a proof pack:

```bash
xrpl-lab proof-pack
```

## Audit packs

**Files:** `audit_pack_*.json`, plus Markdown and CSV exports

Batch verification results that compare transactions against expected outcomes. Each audit pack includes:

- Transaction IDs and their on-ledger results
- Expectation configs (type, memo, result code checks)
- Pass/fail status for each transaction
- SHA-256 integrity hash

Run a batch audit:

```bash
xrpl-lab audit --txids .xrpl-lab/last_run_txids.txt \
  --expect presets/strategy_mm101.json
```

## Certificates

**File:** `xrpl_lab_certificate.json`

Slim completion records showing which modules you finished and when. Soft-linked to XRPL Camp for ecosystem integration.

Generate a certificate:

```bash
xrpl-lab certificate
```

## Reports

**Directory:** `reports/*.md`

Human-readable Markdown summaries of what you did and proved in each module. Generated automatically as you complete modules.

## Workspace layout

When you run modules, XRPL Lab creates a `.xrpl-lab/` directory in the current folder with three subdirectories:

- **`proofs/`** — JSON proof packs and audit packs with SHA-256 integrity hashes
- **`reports/`** — Markdown summaries generated after each module
- **`logs/`** — Internal run logs

## Strategy run metadata

After running a strategy module, XRPL Lab writes two files to the workspace:

- **`last_run_meta.json`** — module name, run ID, timestamp, and preset used
- **`last_run_txids.txt`** — one transaction ID per line, ready for audit

Use `xrpl-lab last-run` to view the metadata and get the exact audit command.

## Verification

Any artifact with transaction IDs can be independently verified against the XRP Ledger:

```bash
xrpl-lab verify --tx <transaction_id>
```

This confirms the transaction exists on-ledger and matches the expected result.
