# Changelog

## 0.8.0 — 2026-03-02

AMM Liquidity 101: Providing Liquidity and Earning Fees.

- New module: AMM Liquidity 101 — create pool, deposit, verify LP, withdraw, verify
- Transport: `get_amm_info`, `submit_amm_create`, `submit_amm_deposit`, `submit_amm_withdraw`, `get_lp_token_balance`
- `AmmInfo` dataclass: pool balances, LP token, trading fee
- Dry-run transport: full AMM simulation (pool registry, LP minting/burning, proportional math)
- Actions: `ensure_amm_pair`, `amm_deposit`, `amm_withdraw`, `verify_lp_received`, `verify_withdrawal`
- Runner: 7 new AMM action handlers
- Testnet transport: AMM stubs (dry-run only for now, pending AMM amendment availability)

## 0.7.0 — 2026-03-02

Audit Mode: Verify Receipts at Scale.

- New command: `xrpl-lab audit --txids txids.txt` — batch verify transactions
- Expectation configs: JSON with defaults + per-tx overrides (require_validated, require_success, memo_prefix, types_allowed, expected_engine_result)
- Failure vocabulary: NOT_FOUND, NOT_VALIDATED, ENGINE_RESULT_MISMATCH, TYPE_DISALLOWED, MEMO_MISSING
- Reports: Markdown table, CSV, JSON audit pack with SHA-256 integrity hash
- New module: Receipt Audit — hands-on audit mode walkthrough
- Dry-run transport: tx fixture support for deterministic audit testing
- Runner: `run_audit` action handler for module-driven audits

## 0.6.0 — 2026-03-03

Account Hygiene: Freeing Reserves and Cleaning Up Objects.

- New module: Account Hygiene — create objects, cancel offers, remove trust lines, verify cleanup
- Trust line removal: `submit_trust_set` with `limit=0` removes trust lines (balance must be 0)
- Dry-run transport: smart trust line handling — no duplicates, limit updates, owner count decrement on removal
- Actions: `remove_trust_line`, `verify_trust_line_removed`
- Runner: `remove_trust_line` and `verify_trust_line_removed` action handlers
- Non-zero balance guard: removal fails with `tecNO_PERMISSION` if tokens still held

## 0.5.0 — 2026-03-02

Reserves 101: Where Your XRP "Went" — account snapshots and owner count tracking.

- New module: Reserves 101 — snapshot before/after, owner count delta, reserve explanation
- Transport: `get_account_info` returns `AccountSnapshot` (balance, owner count, sequence)
- `AccountSnapshot` dataclass for point-in-time account state
- Actions: `snapshot_account`, `compare_snapshots` with `ReserveComparison` result
- Runner: `snapshot_account` and `verify_reserve_change` action handlers
- Dry-run transport tracks `_owner_count` across trust lines and offers
- Helper: `_drops_to_xrp` for human-readable balance display

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
