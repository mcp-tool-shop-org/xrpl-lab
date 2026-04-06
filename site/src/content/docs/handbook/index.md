---
title: Handbook
description: Everything you need to know about XRPL Lab.
sidebar:
  order: 0
---

Welcome to the XRPL Lab handbook.

XRPL Lab is a CLI training workbook for the XRP Ledger. Each module teaches one XRPL skill and produces a verifiable artifact — a transaction ID, a signed receipt, or a diagnostic report. No accounts, no fluff — just competence and receipts.

## Quick start

```bash
# Install
pipx install xrpl-lab

# Start interactive mode
xrpl-lab start

# Or run offline (no network required)
xrpl-lab start --dry-run

# Launch the web dashboard
xrpl-lab serve
# Then open http://localhost:4321/xrpl-lab/app/
```

## What's in the handbook

| Section | What you'll find |
|---------|-----------------|
| **[Getting Started](/xrpl-lab/handbook/getting-started/)** | Install, configure, wallet setup, and first run |
| **[Modules](/xrpl-lab/handbook/modules/)** | All 12 modules across Beginner, Intermediate, and Advanced tracks |
| **[Commands](/xrpl-lab/handbook/commands/)** | Full CLI reference — every flag, every subcommand |
| **[Artifacts](/xrpl-lab/handbook/artifacts/)** | Proof packs, audit packs, and certificates explained |
| **[Beginners](/xrpl-lab/handbook/beginners/)** | New to the XRP Ledger? Start here before running modules |

## Web dashboard

XRPL Lab ships a browser-based dashboard alongside the CLI. Run `xrpl-lab serve` and open [/xrpl-lab/app/](/xrpl-lab/app/) to get:

> **Note:** The dashboard requires the API server to be running (`xrpl-lab serve` on port 8321). It degrades gracefully when offline, but live data and module execution need an active server.

- Real-time module progress and status cards
- Interactive module runner
- Artifact viewer for proof packs and audit packs
- Health diagnostics (Doctor view)

The dashboard connects to a local API server on port 8321.

## What you walk away with

Every completed module produces at least one artifact:

- **Proof pack** — shareable JSON with transaction IDs, module results, and SHA-256 integrity hash
- **Audit pack** — batch verification results in Markdown, CSV, and JSON
- **Certificate** — slim completion record, soft-linked to XRPL Camp

---

[Back to landing page](/xrpl-lab/)
