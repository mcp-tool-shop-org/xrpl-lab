---
title: Facilitator Guide
description: Running XRPL Lab in a workshop — setup, day-of workflow, recovery, and live-room tips.
sidebar:
  order: 5
---

This guide is for facilitators running learners through XRPL Lab in a teaching setting — a one-day workshop, a multi-session course, a cohort lab, or any room where you are responsible for getting a group of people from `pipx install` to a verified XRPL transaction.

The CLI was built workshop-first: every facilitator-facing command answers a question you actually have to answer in the room ("who is stuck?", "is everyone online?", "what is on this learner's screen?"), and the threat model assumes a shared physical space rather than a hardened production deployment.

## 1. Setup

### Workspace layout — the two-tier policy

XRPL Lab splits storage into two tiers on purpose. Both you and your learners need to understand which is which before the workshop starts.

- **Home-private** — `~/.xrpl-lab/` holds the wallet seed and the private state file. Restrictive permissions; never archived; never inspected as part of facilitator handoff.
- **Workspace-shareable** — `./.xrpl-lab/` in the current directory holds proofs, reports, audit packs, certificates. These are the artifacts you and the learner are allowed to look at together.

`xrpl-lab session-export` honours that line — wallet files and state files are deliberately never archived. The full threat model and the rationale for this split are in the canonical [SECURITY.md](https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/SECURITY.md), which is the single source of truth — read that before your first workshop, especially the **Workshop Setup** section.

**Why this matters in the room:** during handoff or "show me your screen" debugging, you can `cat` files in `./.xrpl-lab/` without risk. You should not be browsing `~/.xrpl-lab/` at all. Train your TAs on the same line.

### One-time setup on the facilitator's machine

Before the workshop:

```bash
pipx install xrpl-lab
xrpl-lab --version       # verify install
xrpl-lab doctor          # verify env, RPC, faucet
```

If your cohort is on a shared network, point everyone at the same testnet RPC override so a public outage doesn't take you down mid-workshop:

```bash
export XRPL_LAB_RPC_URL="https://your-preferred-testnet.example/"
```

Both `XRPL_LAB_RPC_URL` and `XRPL_LAB_FAUCET_URL` are surfaced by `xrpl-lab status` and `xrpl-lab doctor`, so you can always confirm what a learner's machine is actually pointed at.

For the cohort directory layout (one subdirectory per learner, each containing a `.xrpl-lab/state.json`), see the canonical workshop-setup section linked above.

## 2. Day-of workflow

These five commands carry you through the live workshop. Each one is designed to answer a specific facilitator question in under 10 seconds.

### `xrpl-lab status` — "where is this one learner?"

Run on a learner's machine (or copy them through it). Reports the wallet address, completed modules, current module, blockers, and any environment overrides. Add `--json` for scripting.

**When to use it:** any time a learner says "I'm stuck" or "what's next?". This is the first command, before doctor, before recovery — it tells you where they actually are in the curriculum.

**What it teaches:** the curriculum is linear with explicit prerequisites. The next module is never ambiguous. Status surfaces the same prerequisite math the guided launcher uses.

### `xrpl-lab cohort-status` — "where is the whole room?"

Aggregates per-learner status across a cohort directory. One row per learner showing progress, current module, blockers, and last activity. Subdirectories without a `state.json` are skipped silently; corrupt state files yield a warning row instead of an abort, so partial views never block on one learner's bad day.

```bash
# Per-learner subdirectories under ./cohort-2026-04/
xrpl-lab cohort-status --dir ./cohort-2026-04

# Single shared workspace (one machine, one state file)
xrpl-lab cohort-status --dir .

# JSON for scripting / dashboard ingestion
xrpl-lab cohort-status --dir ./cohort-2026-04 --format json
```

**When to use it:** every 15 minutes during the workshop. Eyes-on the laggers; eyes-on whoever is two modules ahead of everyone else.

**What it teaches:** workshop pacing is a real thing. Cohort-status is your pacing instrument.

### `xrpl-lab session-export` — "give me the artifacts to grade later"

Walks the cohort directory and packs every learner's `proofs/`, `reports/`, `audit_packs/`, and `certificates/` into a single archive with a `MANIFEST.json` SHA-256 of every included file. Wallets, state files, and doctor logs are **never** archived — that's the threat-model line, enforced in the exporter.

```bash
xrpl-lab session-export --dir ./cohort-2026-04 --format tar.gz
xrpl-lab session-export --dir ./cohort-2026-04 --format zip --outfile workshop-week1.zip
```

**When to use it:** end-of-day, or end-of-workshop. The archive is the deliverable you take home to grade or to feed back to whoever sponsored the workshop.

**What it teaches:** XRPL receipts are independently verifiable. A learner's proof pack carries enough information for any third party (you, an auditor, a sponsor) to re-check the work against the ledger without trusting the learner's machine.

### `xrpl-lab recovery` — "diagnose this stuck state and tell me what to run"

Looks at the current state file and prints the exact recovery commands for whatever it finds wrong (uncompleted module marker, missing wallet, dirty workspace). It does not fix anything itself — facilitator decides whether to run the suggested commands.

**When to use it:** when status says a learner is stuck on a specific module, recovery says *why* and *which command unsticks them*.

**What it teaches:** the lab favours explicit recovery over auto-magic. Every stuck state has a documented exit. Learners shadowing your terminal during recovery learn the recovery vocabulary too.

### `xrpl-lab doctor` — "is this machine actually online?"

Diagnostic checks: wallet present and well-formed, state file readable, workspace writable, env overrides surfaced, RPC reachable, faucet reachable, last error replayed. Each check has its own structured pass/warn/fail status with an actionable hint.

**When to use it:** when a command failed in a way that doesn't smell like curriculum state — network errors, signature errors, faucet rejections. Doctor catches the environmental layer before you waste time on the application layer.

**What it teaches:** XRPL applications have several failure layers (env, network, account, signature, ledger). Doctor maps cleanly to those layers. Learners who watch you read doctor output start reading their own.

## 3. Stuck-learner playbook

Most stuck states are one of two shapes. Match the shape, then run the playbook.

### Shape A — one module is wedged, everything else is fine

Use granular reset:

```bash
xrpl-lab reset --module trust-lines-101
```

This removes that one module from `completed_modules`, clears its tx records and its workspace report, and leaves everything else (wallet, other modules, audit packs, certificates) untouched. The learner can re-run the module from scratch without losing any of their other work.

Add `--confirm` to skip the typed-confirmation prompt — useful for workshop-day flow when you're walking the learner through it side-by-side.

**The recover-then-rerun pattern:** `xrpl-lab recovery` → if it points at one module, `xrpl-lab reset --module <id>` → `xrpl-lab run <id>`. Three commands; learner is unstuck without losing their morning's work.

### Shape B — the whole environment is wrong, blow it away

Full wipe (interactive, requires typing `RESET` to confirm):

```bash
xrpl-lab reset
```

Add `--keep-wallet` to preserve the wallet file (and the funded testnet balance) while wiping all module progress. Useful when the wallet is fine but the state file is corrupt or the workspace is in a weird half-finished state.

**Decision rule:** prefer granular `--module` reset. Only fall back to the full wipe when the recovery hint explicitly tells you the state file is unreadable, or when you've already tried the granular path and the learner is still stuck. A workshop-day full reset is almost always overkill and erases the rest of their progress.

## 4. Live-workshop tips

### Color-independence for projector demos

The CLI is designed so every status signal carries an icon **and** a text label, not just color. That means you can:

- Run on a projector where the green/red distinction washes out — learners can still read DONE/ACTIVE/TODO from the labels
- Set the standard `NO_COLOR=1` environment variable before any demo command to suppress ANSI sequences entirely (Rich respects the convention)
- Trust that color-blind learners get the same information as everyone else without asking

```bash
NO_COLOR=1 xrpl-lab status
NO_COLOR=1 xrpl-lab tracks
```

**What this teaches you to teach:** never describe a status only by hue ("the green one"). Say "the row that says ACTIVE" or "the entry with the checkmark." Your color-blind learners will thank you, and the rest of the room will too.

### Terminal + dashboard split-screen

The most legible workshop layout we've seen:

- **Left half of projector** — your terminal, running `xrpl-lab status` / `xrpl-lab cohort-status` live
- **Right half of projector** — the bundled web dashboard at `http://localhost:4321/xrpl-lab/app/` (dev) or wherever `xrpl-lab serve` is bound (production)

Learners get the CLI vocabulary (left) and the visual cohort overview (right) side-by-side. The [facilitator dashboard](/xrpl-lab/handbook/facilitator-dashboard/) page covers what each piece of the dashboard tells you and how the kill-switch works.

Run `xrpl-lab serve` once at the start of the workshop and leave it running.

### Support-bundle workflow for after-session diagnostics

When a learner hits something that you can't diagnose in the room — a stack trace you've never seen, a faucet rejection that doesn't reproduce, a signature error that smells like something deeper — capture a support bundle on their machine:

```bash
xrpl-lab support-bundle              # markdown, human-readable
xrpl-lab support-bundle --json       # machine-parseable
```

The bundle includes curriculum position, blockers, environment, doctor results, and recent transactions. **No secrets** — designed to be safe to email or paste into a ticket.

**When to use it:** end-of-session, or anytime you want to escalate a learner's issue to whoever is on call for the lab. Far better than asking the learner to copy-paste fragments of terminal output.

**What it teaches:** good debugging is reproducible debugging. The support bundle is what reproducibility looks like for a CLI workbook — the same shape every time, the same fields, the same threat-model boundary on what gets included.

---

For the full CLI reference, see [Commands](/xrpl-lab/handbook/commands/). For a deeper threat-model walkthrough, the canonical source is [SECURITY.md](https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/SECURITY.md).
