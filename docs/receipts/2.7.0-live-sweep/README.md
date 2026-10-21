# 2.7.0 live sweep receipts (xrpl-py 5.2)

This is the live acceptance run for 2.7.0 (PR #23, `feat/xrpl-py-5`) on `4deed70`, the commit Argon gave a GO. It
has two parts:
1. One lesson per signing family, live on XRPL Testnet.
2. A wallet file in the xrpl-py 4.x shape: a secp256k1 seed recorded under its ED25519 address.

`0d7c8fb` (Argon round-1 F1/F2) landed after this run and is not covered.

No seeds and no wallet files are in this directory. The 4.x-shape test's seed was generated into a scratch home and
never printed, logged or copied. An exact-match search of the raw folder found no seed. Testnet addresses and hashes
are public on-ledger. Local paths are shown as `<scratch>`.

**Verdict:**
- **Part 1:** 10 of 11 modules pass, unchanged from 2.6.x. **escrow_finish_101 fails** on a pre-existing timing race,
  not a 2.7.0 regression.
- **Part 2:** the 4.x-shape wallet signs as its recorded ED25519 account, and a mismatched file fails closed. Nothing
  was signed and the file was left unchanged. **But the run exits 0, not 1.** Along the way, `run --force` turned out
  not to re-run a completed testnet module.

## Setup

- One clean worktree pinned at `4deed70` (xrpl-lab 2.7.0, xrpl-py 5.2.0).
- A fresh `XRPL_LAB_HOME` per run, outside every repo.
- Before each run: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Command: `yes "" | xrpl-lab run <module>`, with the exit code from `PIPESTATUS[1]`.
- After each module: `xrpl-lab proof-pack`, then a read-only ledger capture.

**Time:** 2026-10-21 04:00–04:40 UTC.

## Part 1: one lesson per signing family (`sweep-4deed70-20261021T0400Z`)

| Module | Family | Exit | Steps | Transactions | stderr | vs 2.6.x |
|---|---|---|---|---|---|---|
| trust_lines_101 | payments, trust lines, issuance | 0 | 7 passed, 0 failed | 2 successful, 0 failed | empty | no earlier live receipt |
| dex_market_making_101 | DEX | 0 | 17 passed, 0 failed | 4 successful, 0 failed | empty | no earlier live receipt (see note 2) |
| amm_liquidity_101 | AMM | 0 | 18 passed, 0 failed | 6 successful, 0 failed | empty | same as 2.6.0 run 4 and the 2.6.1 release sweep |
| escrow_finish_101 | escrow | **3** | 6 passed, **3 failed** | 1 successful, 1 failed | empty | no earlier live receipt (see note 1) |
| payment_channel_101 | channels, incl. the off-ledger claim | 0 | 13 passed, 0 failed | 3 successful, 0 failed | empty | same as 2.6.1 |
| checks_101 | checks | 0 | 13 passed, 0 failed | 4 successful, 1 failed (1 expected) | empty | same as 2.6.2 |
| nft_marketplace_101 | NFTs | 0 | 13 passed, 0 failed | 5 successful, 1 failed (1 expected) | empty | same as 2.6.2 |
| deposit_gate_101 | credentials, credential-gated payment | 0 | 18 passed, 0 failed | 8 successful, 5 failed (5 expected) | empty | same as 2.6.2 |
| multisig_treasury_101 | multisig | 0 | 10 passed, 0 failed | 3 successful, 1 failed (1 expected) | empty | same as 2.6.2 |
| clawback_101 | clawback | 0 | 12 passed, 0 failed | 4 successful, 1 failed (1 expected) | empty | same as 2.6.2 |
| did_101 | DID | 0 | 6 passed, 0 failed | 2 successful, 0 failed | empty | no earlier live receipt |

On the ledger:
- Every hash these modules recorded is either a validated `tesSUCCESS` or a validated expected rejection:
  - checks: tecNO_PERMISSION `75A2CCEA…`;
  - clawback: tecNO_PERMISSION `84DC5FEF…`;
  - nft_marketplace: tecOBJECT_NOT_FOUND `B674982F…`;
  - deposit_gate: tecDUPLICATE `79C7D2EE…`, tecNO_PERMISSION `9FD2C920…` and `42C47B93…`, tecNO_ENTRY `82D53FE0…`.
- deposit_gate's `temCANNOT_PREAUTH_SELF` (`52501B73…`) correctly never reached a ledger.
- The exception is escrow_finish's EscrowFinish, below.

### Note 1: escrow_finish_101, a FinishAfter timing race (pre-existing)

The steps:
- EscrowCreate `1D410489…` validated `tesSUCCESS` in ledger 21700097, with FinishAfter 845870812 (ripple time).
- EscrowFinish `4E18BBE9…` then validated **`tecNO_PERMISSION`** in ledger 21700100.

Why it failed:
- Ledger 21700100's parent close time is **845870812, equal to FinishAfter**. An EscrowFinish succeeds only once the
  parent ledger's close time is *after* FinishAfter.
- `_wait_for_finish_after` (`handlers.py`) waits on **wall-clock time** plus a 2 s margin, not on the ledger's close
  time.
- Here the wall clock already read past FinishAfter when the step began. This machine's clock leads the validated
  ledger's close time by 1–2 s, as measured. So it did not wait at all; stdout has no "Waiting ~" line.

What followed:
- Steps 7 and 9 then fail as a consequence: the escrow is still on the ledger, and the owner count is +1.

Not a 2.7.0 regression: the helper is unchanged since v2.4.0, and this module had not been run live in earlier
receipts.

**Fix:** wait until a validated ledger's `close_time` is past FinishAfter, rather than reading the local clock.

### Note 2: dex_market_making_101 under-reports its OfferCancels (low)

The two OfferCancel transactions (`C128B749…`, `58E9CD5B…`) validated `tesSUCCESS` and are in `tx_index` and the
proof pack. But the module report neither lists nor counts them: "4 successful" against 6 recorded.

## Part 2: a wallet file in the xrpl-py 4.x shape (`legacy-wallet-4deed70-20261021T0424Z`)

**Setup** (`setup.txt`):
- A fresh secp256k1 seed (`generate_seed(algorithm=SECP256K1)`).
- `wallet.json` = `{"seed", "address"}`, with the address from `Wallet.from_seed(seed, algorithm=ED25519)`:
  `rKhWane2oiEpLs391CyoGWetrF7XLGLdAV`.
- xrpl-py 5's prefix-inferred address for the same seed is `rhRRyFDvzrgjApphzbRkCobQkSNRNL9Msg`.
- There was no `state.json` before run A.

| Run | What | Exit | Result |
|---|---|---|---|
| A | `run failure_literacy`, state absent | 0 | **PASS.** It loaded the wallet as `rKhWane2…`, funded it there, and **both transactions were signed by the ED25519 account**: tecUNFUNDED_PAYMENT `0353CD7A…` (the lesson's deliberate failure) and Payment `944D1682…` (tesSUCCESS, to the practice address). The secp256k1 address is `actNotFound`: nothing was ever signed as it. |
| B | the file's address changed to the unrelated `r9s62YbG…` (unfunded); `run --force failure_literacy` | 0 | **Not exercised.** It printed "already completed. Run with --force to redo it" despite `--force`, and nothing ran. See finding 2. The file is byte-identical. |
| B2 | the same file; state from run A (`wallet_address` = `rKhWane2…`); `run receipt_literacy`, a module not yet completed | **0** | It printed **`STATE_WALLET_KEY_MISMATCH`** with "Nothing was signed". The ED25519 account's Sequence is unchanged (21700424 before and after). The unrelated address is `actNotFound`. **The file is byte-identical.** No module completed. **But the exit code is 0, not 1** (finding 1). |

### Findings

1. **`STATE_WALLET_KEY_MISMATCH` exits 0.**
   - `run_module` catches the `LabException` from the wallet load, prints it and returns `False` (`runner.py:258-261`).
   - `_exit_if_unverified` treats `ok == False` as "stopped early, keep the existing exit", which is 0 (`cli.py`).
   - A script cannot tell the refusal from a success. The error carries its own exit code, and it should reach the
     process.
2. **`run --force` does not re-run a completed module on testnet.**
   - `run_module` checks `if state.is_module_completed(module.id) and not dry_run:` and returns `True`
     (`runner.py:210`). The condition should be `not force`.
   - So on testnet, `--force` is ignored and the run exits 0 having done nothing.
   - The guard is present since the initial scaffold (`392c4e0`), so it is not a 2.7.0 regression.
3. The "already completed" path also reports success: exit 0, which `_exit_if_unverified` passes through.

Argon's F1 (a `state.wallet_path` with an empty `wallet_address` skips the check on `4deed70`) was not exercised.
Run A started with no state, as Argon asked.

## Files

- `sweep-4deed70-20261021T0400Z/<module>/`:
  - `command.txt`, with the exit code;
  - `preflight.txt`;
  - `stdout.txt`, with the scratch path redacted;
  - `stderr.txt`;
  - `module_report.md`;
  - `proof_pack.json`;
  - `ledger_evidence.json`.
- `legacy-wallet-4deed70-20261021T0424Z/`:
  - `setup.txt` (addresses only);
  - `preflight.txt`;
  - `ledger_evidence.json` (the three accounts);
  - `A-…/`, `B-…/` and `B2-…/`, each with `command.txt` (exit code, and whether the file stayed byte-identical),
    `stdout.txt` and `stderr.txt`.

  `state.json` is left out because it carries the local home path. The seed's file never leaves the scratch home.
