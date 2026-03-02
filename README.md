# XRPL Lab

XRPL training workbook — learn by doing, prove by artifact.

Each module teaches one skill and produces a verifiable artifact: a transaction ID,
a signed receipt, or a diagnostic report. No accounts, no fluff.

## Install

```bash
pipx install xrpl-lab
```

Or with pip:

```bash
pip install xrpl-lab
```

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

| Module | What you learn | What you prove |
|--------|---------------|----------------|
| Receipt Literacy | Send a payment, read every receipt field | txid + verification report |
| Failure Literacy | Break a tx on purpose, diagnose, fix, resubmit | failed + fixed txid trail |

## Commands

```
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status             Progress, wallet, recent txs
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab reset              Wipe local state (confirmation required)

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send               Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

## Artifacts

**Proof pack** (`xrpl_lab_proof_pack.json`): Shareable record of completed modules,
transaction IDs, and explorer links. Includes a SHA-256 integrity hash. No secrets.

**Certificate** (`xrpl_lab_certificate.json`): Slim completion record.

**Reports** (`reports/*.md`): Human-readable summaries of what you did and proved.

## Security

- Wallet seeds are stored locally with restricted file permissions
- Proof packs and certificates never contain secrets
- All network operations are optional (use `--dry-run` for offline mode)
- See [SECURITY.md](SECURITY.md) for the full threat model

## Requirements

- Python 3.11+
- Internet connection for testnet (or use `--dry-run`)

## License

MIT

Built by [MCP Tool Shop](https://mcp-tool-shop.github.io/)
