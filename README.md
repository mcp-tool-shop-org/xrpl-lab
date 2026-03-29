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
a signed receipt, or a diagnostic report. No accounts, no fluff — just competence and receipts.

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

12 modules across three tracks: Beginner, Intermediate, and Advanced.

| # | Module | Track | What you learn | What you prove |
|---|--------|-------|----------------|----------------|
| 1 | Receipt Literacy | Beginner | Send a payment, read every receipt field | txid + verification report |
| 2 | Failure Literacy | Beginner | Break a tx on purpose, diagnose, fix, resubmit | failed + fixed txid trail |
| 3 | Trust Lines 101 | Beginner | Create issuer, set trust line, issue tokens | trust line + token balance |
| 4 | Debugging Trust Lines | Beginner | Intentional trust line failure, error decode, fix | error → fix txid trail |
| 5 | DEX Literacy | Intermediate | Create offers, read order books, cancel | offer create + cancel txids |
| 6 | Reserves 101 | Intermediate | Account snapshots, owner count, reserve math | before/after snapshot delta |
| 7 | Account Hygiene | Intermediate | Cancel offers, remove trust lines, free reserves | cleanup verification report |
| 8 | Receipt Audit | Intermediate | Batch verify transactions with expectations | audit pack (MD + CSV + JSON) |
| 9 | AMM Liquidity 101 | Advanced | Create pool, deposit, earn LP, withdraw | AMM lifecycle txids |
| 10 | DEX Market Making 101 | Advanced | Bid/ask offers, position snapshots, cleanup | strategy txids + hygiene report |
| 11 | Inventory Guardrails | Advanced | Threshold-based quoting, safe-side-only placement | inventory check + guarded txids |
| 12 | DEX vs AMM Risk Literacy | Advanced | Side-by-side DEX and AMM lifecycle comparison | comparison report + audit trail |

## Commands

```
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status             Progress, wallet, recent txs
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate issue-ready markdown
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab reset              Wipe local state (requires RESET confirmation)

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

All commands support `--dry-run` for offline mode where applicable.

## Artifacts

**Proof pack** (`xrpl_lab_proof_pack.json`): Shareable record of completed modules,
transaction IDs, and explorer links. Includes a SHA-256 integrity hash. No secrets.

**Certificate** (`xrpl_lab_certificate.json`): Slim completion record.

**Reports** (`reports/*.md`): Human-readable summaries of what you did and proved.

**Audit packs** (`audit_pack_*.json`): Batch verification results with SHA-256 integrity hash.

## Security and Trust Model

**Data XRPL Lab touches:**
- Wallet seed (stored locally in `~/.xrpl-lab/wallet.json` with restrictive file permissions)
- Module progress and transaction IDs (stored in `~/.xrpl-lab/state.json`)
- XRPL Testnet RPC (public endpoint, transactions signed locally before submission)
- Testnet faucet (public HTTP, only your address is sent)

**Data XRPL Lab does NOT touch:**
- No mainnet. Testnet only
- No telemetry, analytics, or phone-home of any kind
- No cloud accounts, no registration, no third-party APIs
- No secrets in proof packs, certificates, or reports — ever

**Permissions:**
- Filesystem: reads/writes only `~/.xrpl-lab/` and `./.xrpl-lab/` (local workspace)
- Network: XRPL Testnet RPC + faucet only (both overridable via env vars, both optional with `--dry-run`)
- No elevated permissions required

See [SECURITY.md](SECURITY.md) for the full security policy.

## Requirements

- Python 3.11+
- Internet connection for testnet (or use `--dry-run` for fully offline mode)

## License

MIT

Built by [MCP Tool Shop](https://mcp-tool-shop.github.io/)
