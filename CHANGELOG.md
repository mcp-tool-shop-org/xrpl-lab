# Changelog

## 1.3.0 — 2026-04-15

Curriculum Spine — module structure, progression, and learner navigation as first-class truth.

### Module Metadata Lock (3A)
- New required frontmatter fields: `track`, `summary`, `mode`
- Five canonical tracks: foundations, dex, reserves, audit, amm
- `mode` field (testnet/dry-run) replaces inferred `dry_run_only` boolean
- `requires` cleaned to reference only module IDs (removed `wallet` as implicit)
- All 12 modules standardized with uniform metadata shape

### Progression Truth (3B)
- `curriculum.py` — directed graph of modules with prerequisite edges
- Topological sort respecting track order and module order
- `next_module(completed)` — deterministic next valid module
- Cycle detection, orphan detection, transitive prerequisite queries
- `CurriculumGraph.validate()` — checks tracks, summaries, prereqs, modes, cycles

### Curriculum-Aware Lint (3C)
- `xrpl-lab lint` now validates curriculum structure (prereqs, cycles, tracks, modes)
- `--no-curriculum` flag to skip cross-module checks
- `lint_curriculum()` function for programmatic use
- Broken prerequisite references, missing tracks, and cycles caught at author time

### Learner Navigation Surfaces (3D)
- `list` command shows track column, curriculum-ordered modules, `▸` next-module indicator
- `start` command uses curriculum graph for next-module selection with summary/track/mode info
- API `/api/modules` returns curriculum-ordered list with `track`, `summary`, `mode`, `is_next`
- `ModuleSummary` schema updated (TS + Python in sync, drift test passing)

### Docs Alignment (3E)
- README modules table updated with track and mode columns
- Tracks and modes sections added to README
- `lint` command added to README commands section
- Handbook modules page reorganized by track with prerequisites
- Handbook getting-started page documents curriculum, tracks, and lint command

### Tests
- 502 → 534 tests (+29 curriculum, +3 curriculum-lint = +32)

## 1.2.0 — 2026-07-24

Authoring Spine — registry-based dispatch, structured payloads, module linter.

### Action Registry (2A)
- Central `registry.py` with `ActionDef`, `PayloadField`, `PayloadSchema`, `register()`, `resolve()`
- All 37 actions registered with metadata (description, wallet_required, payload_fields)
- `handlers.py` — extracted all action handlers from runner.py into standalone async functions
- `runtime.py` — shared utilities (_SecretValue, ensure_wallet, ensure_funded)
- `runner.py` shrunk from ~1750 to ~330 lines: thin `_execute_action()` does registry lookup → wallet gate → validate → dispatch

### Structured Payloads (2B)
- Quote-aware parser: `_parse_action_args()` supports `key="value with spaces"` and `key='value'`
- Typed payload validation (str, int, decimal, bool, enum, list) via `PayloadSchema.validate()`
- Validation wired into dispatch — bad payloads caught before handler runs

### Module Linter (2C)
- `linter.py` — validate frontmatter, action names, payloads, dry_run_only labeling
- `xrpl-lab lint [glob] [--json]` CLI command for author-time and CI validation
- 6 test fixture modules (3 error types + dry-run labeling mismatches + good baseline)
- JSON output for CI integration

### Tests
- 478 → 502 tests (+17 registry, +12 payload, +13 linter = +42 net, minus test renumbering)

## 1.1.0 — 2026-07-23

Truth + Continuity pass — no new modules, tighter semantics.

### Camp Continuity
- `start` imports camp wallet seed for real (reads `~/.xrpl-camp/wallet.json`, validates via `Wallet.from_seed()`, saves to lab wallet path)
- Honest messaging: no "Starting with your existing wallet" unless import succeeds

### Proof Verification CLI
- `proof verify <file>` — verify proof pack integrity (SHA-256 hash check)
- `cert-verify <file>` — verify certificate integrity
- Both support `--json` for machine-readable output
- Exit code 1 on failure

### Dry-Run Semantics
- All `--dry-run` help strings updated from "Run without network" to "Offline sandbox: simulated transactions, real local persistence"
- Start banner explains sandbox behavior clearly

### Dry-Run-Only Modules
- `dry_run_only: true` frontmatter flag for AMM modules (amm_liquidity_101, dex_vs_amm_risk_literacy)
- `list` command shows Mode column (testnet / dry-run)
- `start` command shows `(dry-run only)` tag for labeled modules

### Tests
- 456 → 461 tests (+5 verify command tests)

## 1.0.6 — 2026-04-05

Dogfood Swarm v2 — deep quality hardening, 456 tests.

### Stage A — Bug/Security Fix (65 findings, 4 amend waves)
- Locked API contract: Pydantic response models as single source of truth
- XSS defense: escapeHtml() on all frontend innerHTML injections
- Secret handling: _SecretValue wrapper prevents seed leakage in tracebacks
- Per-address scoping in DryRunTransport (trust lines, offers)
- Float safety: try/except on all numeric conversions from network data
- CORS restricted to localhost dev origins only
- Modules included in pip wheel via hatch force-include

### Stage B — Institutional Hardening (4 waves)
- B1 Contract Law: Pydantic schemas + TypeScript drift detection tests
- B2 Runner Law: console injection, callback isolation, no monkey-patching
- B3 Secret + Numeric Law: Decimal-only financial math, pickle-proof secrets
- B4 Product Proving: 29 end-to-end smoke tests

### Stage C — Humanization
- Structured HTTP errors with code/message/hint (not bare strings)
- CLI help text with quick-start examples
- Runner step failures show exception type + doctor hint

### Feature Pass
- Fixed 2 mismatched module IDs in frontend static paths

### Test Coverage
- 355 → 456 tests (+101)
- New test files: api_contract, schema_drift, runner_isolation, numeric_law, product_smoke

## 1.0.5 — 2026-04-05

Version alignment — bump to match upstream and npm wrapper versions.

- Bump version to 1.0.5 to align with @mcptoolshop/xrpl-lab npm wrapper
- Include module markdown files in wheel via hatch force-include (pip installs now get all 12 modules)
- Fix PyInstaller --add-data separator for cross-platform builds (Windows uses `;`, Linux uses `:`)

## 1.0.4 — 2026-03-29

Translations and documentation update.

- Added 8-language translations for v1.0.3 release notes

## 1.0.3 — 2026-03-29

Dogfood Swarm — comprehensive health pass, web dashboard, and 127 new tests.

### Health Pass (Stage A-C)
- Fixed 9 HIGH-severity logic bugs (trust line, AMM, runner, state, doctor, audit)
- SHA-pinned all CI workflow actions across 4 workflows
- Added defensive guards for all float/int conversions on network data
- Exception boundary around module runner with state preservation
- Graceful faucet failure handling with actionable messages
- Corrupted state backup before reset
- Step-level progress indicators and retry visibility
- Wired XRPL_LAB_HOME env var for state directory override
- Added `network_name` property to Transport ABC

### Web Dashboard
- FastAPI server layer with 9 REST endpoints + WebSocket module runner
- `xrpl-lab serve` command starts API server with --dry-run support
- Astro dashboard: module catalog, interactive runner, artifact viewer, doctor page
- Real-time module execution via WebSocket with terminal-style output
- 36-page site build (landing page + handbook + dashboard)

### Feature Improvements
- Module ordering by explicit order field (not alphabetical)
- AMM modules require --dry-run with clear warning
- Prerequisite enforcement with --force bypass
- Richer module reports with action outcomes
- Certificate includes titles, tx counts, summary line
- `audit --no-pack` option to skip JSON pack
- Fixed dex_market_making_101 step ordering bug

### Test Coverage
- 228 → 355 tests (+127)
- New test files: wallet, verify, send/fund, errors, server, runner_ws, CLI serve
- Fixed dry-run fidelity: per-address balances, instance-level counter, valid base58

## 1.0.2 — 2026-03-25

- SHA-pinned CI actions (checkout, setup-python)
- Version test now uses dynamic `__version__` instead of hardcoded string

## 1.0.1 — 2026-03-03

Binary launcher fix: Windows UTF-8 encoding for Rich console output.

- Fix: `UnicodeEncodeError` on Windows when Rich renders Unicode symbols (○, ✓, ✗)
- `__main__.py` reconfigures stdout/stderr to UTF-8 before any imports
- PyInstaller + npm-launcher: `npx @mcptoolshop/xrpl-lab` now works on Windows

## 1.0.0 — 2026-03-03

Shipcheck + Full Treatment — production-ready release.

- Structured error contract: `LabError` + `LabException` with code/message/hint/cause/retryable
- Exit code mapping: INPUT/CONFIG/STATE → 1, IO/DEP/RUNTIME → 2, PARTIAL → 3
- Verify script: `verify.sh` (lint + test + build in one command)
- README: logo, badges, full 12-module table, trust model paragraph
- SECURITY.md: complete security policy with trust boundaries
- SHIP_GATE.md: all hard gates (A-D) passing
- Landing page: @mcptoolshop/site-theme
- Translations: 8 languages via polyglot-mcp

## 0.10.0 — 2026-03-03

Strategy Track Complete: Inventory Guardrails + DEX vs AMM Capstone.

- New module: DEX Inventory Guardrails — threshold-based quoting, only safe sides placed
- New module: DEX vs AMM Risk Literacy — side-by-side comparison of DEX and AMM strategies
- `check_inventory` — evaluate XRP spendable and token balance against thresholds
- `InventoryCheck` dataclass with `can_bid`, `can_ask`, `sides_allowed`
- Runner: `check_inventory` and `place_safe_sides` action handlers
- New command: `xrpl-lab last-run` — show last module run info + audit command
- Module completion panel now shows audit verification one-liner
- Audit presets: `presets/strategy_inv.json`, `presets/strategy_compare.json`
- 12 modules total — full strategy track (beginner → intermediate → advanced)

## 0.9.0 — 2026-03-02

DEX Market Making 101: Strategy Track Foundations.

- New module: DEX Market Making 101 — bid/ask offers, position snapshots, cleanup hygiene
- Strategy foundations: `PositionSnapshot`, `PositionComparison`, `HygieneSummary`
- `snapshot_position` — extended account state (trust lines, offers, owner count, spendable estimate)
- `compare_positions` — track owner count and offer deltas between snapshots
- `cancel_module_offers` — batch cancel strategy offers by sequence
- `hygiene_summary` — end-of-module cleanup verification (offers cleared, owner count baseline)
- `write_last_run` — outputs `last_run_txids.txt` + `last_run_meta.json` for audit integration
- Strategy memo convention: `XRPLLAB|STRAT|<MODULE>|<ACTION>|<RUNID>`
- Audit preset: `presets/strategy_mm101.json` (OfferCreate/OfferCancel types, memo prefix)
- Runner: 8 new action handlers (snapshot_position, strategy_offer_bid/ask, verify/cancel module offers, verify_position_delta, hygiene_summary)

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
