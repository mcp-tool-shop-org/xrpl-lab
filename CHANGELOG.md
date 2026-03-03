# Changelog

## 0.4.0 — 2026-03-02

DEX Literacy module — offers, order books, and cancellations.

- New module: DEX Literacy — create offer, verify active, cancel, verify absent
- Transport: `submit_offer_create`, `submit_offer_cancel`, `get_account_offers`
- `OfferInfo` dataclass for DEX offer representation
- Actions: `create_offer`, `cancel_offer`, `verify_offer_present`, `verify_offer_absent`
- Runner: handles DEX action types (create_offer, cancel_offer, verify_offer_*)
- Dry-run transport tracks offers with sequence numbers and supports cancellation
- DEX notes: `docs/dex_notes.md` — taker pays/gets, partial fills, why cancel matters

## 0.3.1 — 2026-03-03

Debugging Reality: trust line failure module + ecosystem alignment.

- New module: Debugging Trust Lines — intentional failure, error decode, fix, verify
- Dry-run transport validates trust lines realistically (no trust line = tecPATH_DRY)
- `xrpl-lab self-check` — alias for `doctor` (ecosystem verb alignment)
- Proof pack receipt table: human-readable per-tx summary (txid, module, status, timestamp)
- Runner: `issue_token_expect_fail` action with result code explanation

## 0.3.0 — 2026-03-02

Trust Lines module + feedback command.

- New module: Trust Lines 101 — create issuer, set trust line, issue tokens, verify
- Transport: `submit_trust_set`, `submit_issued_payment`, `get_trust_lines`
- Trust line actions: `set_trust_line`, `issue_token`, `verify_trust_line`
- `xrpl-lab feedback` — generates issue-ready markdown (doctor + env + proof pack)
- Runner handles trust line action types (create_issuer_wallet, fund_issuer, etc.)

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
