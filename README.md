<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL training workbook — learn by doing, prove by artifact.

Each module teaches one XRPL skill and produces a verifiable artifact: a transaction ID,
a signed receipt, or a diagnostic report. No accounts, no fluff, no cloud — just
competence and receipts.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
</p>

## Install

```bash
pipx install xrpl-lab
```

Or with pip:

```bash
pip install xrpl-lab
```

Requires Python 3.11+.

## Quickstart

```bash
xrpl-lab start
```

The guided launcher walks you through wallet setup, funding, and your first module.

### Offline mode

```bash
xrpl-lab start --dry-run
```

No network required. Simulated transactions for learning the workflow.

## Modules

12 modules across five tracks: Foundations, DEX, Reserves, Audit, and AMM.
Prerequisites are explicit — the CLI and linter enforce them.

| # | Module | Track | Mode | What you learn | What you prove |
|---|--------|-------|------|----------------|----------------|
| 1 | Receipt Literacy | foundations | testnet | Finality is a receipt, not a "sent" status — send a payment, read every receipt field | txid + verification report |
| 2 | Failure Literacy | foundations | testnet | XRPL errors have semantics (tec/tef/tem/ter) — break a tx on purpose, diagnose, fix, resubmit | failed + fixed txid trail |
| 3 | Trust Lines 101 | foundations | testnet | Tokens are opt-in and directional — create issuer, set trust line, issue tokens | trust line + token balance |
| 4 | Debugging Trust Lines | foundations | testnet | Decode trust line error codes — intentional failure, error decode, fix | error → fix txid trail |
| 5 | DEX Literacy | dex | testnet | Order books pair makers with takers — create offers, read order books, cancel | offer create + cancel txids |
| 6 | Reserves 101 | reserves | testnet | Every owned object locks XRP — snapshots, owner count, reserve math | before/after snapshot delta |
| 7 | Account Hygiene | reserves | testnet | Cleanup is a first-class skill — cancel offers, remove trust lines, free reserves | cleanup verification report |
| 8 | Receipt Audit | audit | testnet | Audits encode intent (txid + expectation + verdict) — batch verify with expectations | audit pack (MD + CSV + JSON) |
| 9 | AMM Liquidity 101 | amm | dry-run | Constant product (`x*y=k`) prices passively — create pool, deposit, earn LP, withdraw | AMM lifecycle txids |
| 10 | DEX Market Making 101 | dex | testnet | Bid/ask spreads track inventory — quote both sides, snapshot positions, clean up | strategy txids + hygiene report |
| 11 | Inventory Guardrails | dex | testnet | Quote only the safe side when inventory tilts — threshold-based, guarded placement | inventory check + guarded txids |
| 12 | DEX vs AMM Risk Literacy | amm | dry-run | Impermanent loss is a property of the AMM model — DEX and AMM lifecycle side by side | comparison report + audit trail |

### Tracks

- **foundations** — wallet, payments, trust lines, error handling
- **dex** — offers, order books, market making, inventory management
- **reserves** — account reserves, owner count, cleanup
- **audit** — batch verification, audit reports
- **amm** — automated market maker liquidity, DEX vs AMM comparison

### Modes

- **testnet** — real transactions on the XRPL Testnet
- **dry-run** — offline sandbox with simulated transactions (no network required)

## Commands

```text
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status and progression
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status [--json]    Progress, curriculum position, blockers, track progress
xrpl-lab cohort-status [--dir DIR] [--format FORMAT]  Aggregate per-learner status across a cohort directory (facilitator)
xrpl-lab session-export [--dir DIR] [--format FORMAT] [--outfile FILE]  Archive all learner artifacts with a SHA-256 manifest
xrpl-lab tracks             Track-level completion summaries
xrpl-lab recovery           Diagnose stuck states, show recovery commands
xrpl-lab lint [glob] [--json] [--no-curriculum]  Validate module files and curriculum
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate support bundle (markdown)
xrpl-lab support-bundle [--json] [--verify FILE]  Generate or verify support bundles
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab serve [--port N] [--host H] [--dry-run]  Start web dashboard and API server
xrpl-lab reset [--module MODULE_ID]  Wipe local state OR reset a single module (requires confirmation)
xrpl-lab module init --id ID --track TRACK --title TITLE --time TIME  Scaffold a lint-passing module skeleton

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

All commands support `--dry-run` for offline mode where applicable.

## Workshop Use

XRPL Lab is designed for real teaching settings. No accounts, no telemetry, no cloud.
Everything runs locally.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Facilitator status

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Support handoff

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

A facilitator can diagnose any learner's issue from a support bundle without
reproducing the whole session. No secrets are included.

### Workshop flows

**All-offline sandbox** — no network required:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Mixed offline + testnet** — real transactions for basics, sandbox for advanced:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Camp → Lab progression** — continue from xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artifacts

**Proof pack** (`xrpl_lab_proof_pack.json`): Shareable record of completed modules,
transaction IDs, and explorer links. Includes a SHA-256 integrity hash. No secrets.

**Certificate** (`xrpl_lab_certificate.json`): Slim completion record.

**Reports** (`reports/*.md`): Human-readable summaries of what you did and proved.

**Audit packs** (`audit_pack_*.json`): Batch verification results with SHA-256 integrity hash.

## Security and Trust Model

**Data XRPL Lab touches:**
- Wallet seed (stored locally in `~/.xrpl-lab/wallet.json` as plaintext JSON, protected by 0o600 file permissions and a 0o700 parent directory — not encrypted)
- Module progress and transaction IDs (stored in `~/.xrpl-lab/state.json`, atomic writes via tmp + rename)
- XRPL Testnet RPC (public endpoint, transactions signed locally before submission)
- Testnet faucet (public HTTP, only your address is sent)

**Data XRPL Lab does NOT touch:**
- No mainnet. Testnet only
- No telemetry, analytics, or phone-home of any kind
- No cloud accounts, no registration, no third-party APIs
- No secrets in proof packs, certificates, reports, or support bundles — ever

**Permissions and storage tiers:**
- Home `~/.xrpl-lab/` — private secrets tier, 0o700 directory + 0o600 wallet file. Stores wallet seed, doctor log, audit packs.
- Workspace `./.xrpl-lab/` — designed-shareable tier, 0o755 directory. Stores module reports, proof packs, certificates. Facilitators can review without permission elevation.
- Filesystem: reads/writes only the two locations above
- Network: XRPL Testnet RPC + faucet only (both overridable via env vars, both optional with `--dry-run`)
- No elevated permissions required

**Dashboard surface (when `xrpl-lab serve` is running):**
- WebSocket runner endpoint enforces an Origin allow-list (closes non-allow-listed connections with code 4003)
- All error frames emit a structured envelope (`code`, `message`, `hint`, `severity`, `icon_hint`) — no path leakage, no internal-state leakage
- Bounded per-connection message queue with documented back-pressure behavior

See [SECURITY.md](SECURITY.md) for the full security policy and workshop-setup guidance.

## Requirements

- Python 3.11+
- Internet connection for testnet (or use `--dry-run` for fully offline mode)

## License

MIT

Built by [MCP Tool Shop](https://mcp-tool-shop.github.io/)
