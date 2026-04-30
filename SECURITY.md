# Security Policy

## What XRPL Lab stores locally

| File | Location | Contains |
|------|----------|----------|
| `state.json` | `~/.xrpl-lab/` | Module progress, txids, wallet address, timestamps |
| `wallet.json` | `~/.xrpl-lab/` | Wallet seed (plaintext, protected by file permissions) |
| Reports | `./.xrpl-lab/reports/` | Human-readable markdown summaries |
| Proofs | `./.xrpl-lab/proofs/` | Shareable JSON (no secrets) |

## Secrets hygiene

- **Wallet seeds** are stored in `wallet.json` with restrictive file permissions (owner-only read/write)
- **Proof packs and certificates never contain seeds** — they only include public addresses and txids
- **Reports never contain seeds** — only public transaction data
- The CLI warns users not to share wallet files or paste seeds

## Trust boundaries

- **XRPL Testnet RPC**: Public endpoint, no authentication. Transactions are signed locally before submission
- **Testnet Faucet**: Public HTTP endpoint. Only your address is sent (no secrets)
- **Local filesystem**: State and wallet files are local-only. No telemetry, no phone-home
- **Module content**: Modules are bundled markdown files parsed locally

## Workshop Setup

XRPL Lab uses a two-tier directory model designed for workshop facilitator handoff:

### Single-user private (`~/.xrpl-lab/`)
Created at mode `0o700` (owner-only). Contains:
- `wallet.json` — wallet seed (mode `0o600`)
- `state.json` — module progress, txid history (mode `0o600`)
- `doctor.log` — diagnostic log (mode `0o600`)

These files are personal to the learner and never intended to be shared.

### Workshop-shareable (`./.xrpl-lab/` in your working directory)
Created at mode `0o755`. Contains:
- `proofs/` — proof packs (no secrets, public txids only)
- `reports/` — markdown summaries
- `audit_packs/` — batch verification results
- `logs/` — runner logs

These are designed for facilitator inspection during workshop handoff. A facilitator can `ls` and `cat` files in this directory to review a learner's work without needing access to the learner's home directory or wallet.

### Per-learner isolation in shared lab environments

For workshops on a shared machine where each learner has a distinct OS user:
- Default behavior is correct: `~/<learner>/.xrpl-lab/` is owner-private; `./<learner>/.xrpl-lab/` (relative to learner's working dir) is shareable.

For workshops on a shared machine where multiple learners share an OS user (e.g., training labs with kiosk users):
- Set `XRPL_LAB_HOME` to a per-learner path: `XRPL_LAB_HOME=/tmp/learner-N xrpl-lab start`. The home dir's `0o700` mode prevents cross-learner reads even on the shared user.

### Threat model summary
- Local private files (`~/.xrpl-lab/`) protect learner secrets from other OS users.
- Workspace files (`./.xrpl-lab/`) are designed-readable for workshop handoff.

The two-tier design solves the shared-machine problem: learners keep secrets in their private home directory while sharing evidence (proofs, reports, audit packs) through the workspace directory, so a facilitator giving feedback only needs `cat` permissions on the workspace — never SSH or password access to a learner's account.

- See [the DD-1 implementation in xrpl_lab/state.py](xrpl_lab/state.py) for the per-directory mode policy.

## Network risks

- RPC endpoint can be overridden via `XRPL_LAB_RPC_URL` — use only trusted endpoints
- Faucet endpoint can be overridden via `XRPL_LAB_FAUCET_URL`
- All network operations are optional (`--dry-run` mode works fully offline)

## Common user mistakes

- Sharing `wallet.json` — this contains your seed. Treat it like a password file
- Using mainnet RPC URLs — XRPL Lab is designed for testnet only
- Running in shared directories — workspace files are world-readable by default

## How to reset

```bash
xrpl-lab reset
```

This deletes `state.json` and the workspace directory. Your wallet file is preserved.

To fully remove all XRPL Lab data:

```bash
rm -rf ~/.xrpl-lab/
rm -rf ./.xrpl-lab/
```

## Reporting vulnerabilities

Report security issues at: https://github.com/mcp-tool-shop-org/xrpl-lab/security/advisories/new

We will respond within 48 hours.
