# Changelog

## 0.2.0 — 2026-03-02

Clinic & Proof Pack release.

- `xrpl-lab doctor` — checklist diagnostic (wallet, state, RPC, faucet, env, last error)
- XRPL result code reference with categories + actionable hints
- Transport: timeouts, retries (max 2), friendly error messages
- Proof pack upgrade: per-tx detail, endpoint, success/fail counts
- `status` shows env overrides (XRPL_LAB_RPC_URL, XRPL_LAB_FAUCET_URL)
- `reset` requires "RESET" (uppercase), adds `--keep-wallet` flag
- Manual testnet smoke test workflow (workflow_dispatch)

## 0.1.0 — 2026-03-02

Initial release.

- 2 modules: Receipt Literacy, Failure Literacy
- CLI: `start`, `list`, `run`, `status`, `reset`, `proof-pack`, `certificate`
- Standalone commands: `wallet create/show`, `fund`, `send`, `verify`
- XRPL Testnet transport + dry-run (offline) transport
- Proof packs and certificates (no secrets, SHA-256 integrity hash)
- XRPL Camp soft-integration (certificate file detection)
