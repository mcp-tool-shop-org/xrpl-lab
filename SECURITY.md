# Security Policy

## What XRPL Lab stores locally

| File | Location | Contains |
|------|----------|----------|
| `state.json` | `~/.xrpl-lab/` | Module progress, txids, wallet address, timestamps |
| `wallet.json` | `~/.xrpl-lab/` | Wallet seed (encrypted with file permissions) |
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
