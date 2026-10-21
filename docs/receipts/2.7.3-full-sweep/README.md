# 2.7.3 full live sweep: all 32 lessons on testnet

This is a measurement only, with no code changes. The Director asked for it. It runs the whole course live on XRPL
Testnet against the released **v2.7.3** (main `8723e95`, which is the `v2.7.3` tag), under the new live verifier
(2.7.1–2.7.3: expected rejections, helper accounts, links).

- **Part A, the workshop shape:** all 32 lessons in curriculum order, in **one fresh home**, then
  `proof verify --live` over the full pack.
- **Part B:** each lesson that failed in Part A, re-run alone in its own fresh home, with `proof verify --live` on its
  pack. That separates a lesson's own defect from interference by an earlier lesson.

No seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>` and `<worktree>`.
Each `state_excerpt.json` holds `module_accounts`, completed modules with `verified`, and `tx_index`, with
`wallet_path` omitted.

## Setup

- One clean worktree at `8723e95` (xrpl-lab 2.7.3, xrpl-py 5.2).
- Preflight: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Every lesson: `yes "" | xrpl-lab run <m>` with `PYTHONIOENCODING=utf-8`. Enter is fed to every prompt; stdin is
  never closed.
- The exit code is read from `PIPESTATUS[1]`.
- No log contains "Module interrupted".
- 60 s between lessons. On a faucet 429 the lesson would have been retried once after 150 s; **no retry was needed**
  (no 429 in Part A or Part B).
- dex_vs_amm_risk_literacy is `mode: dry-run`, and the runner forces it offline, as designed.

**Time:** 2026-10-21. Part A 18:55–19:55 UTC; Part B 20:00–20:20 UTC.

## Results

**Part A's overall live verdict: FAIL** (`proof verify --live` exit 1): **104 PASS, 14 FAIL, 11 SKIPPED**.
- Every FAIL is one of the failing lessons' own genuine failures, an unexpected on-ledger `tec`.
- The one exception is account_hygiene's local failure, a txid `"failed"` reported as "Transaction not found".
- **There is no helper-account mismatch anywhere.** The 2.7.1 `module_accounts` fix holds across the whole course.

**Part A:** 22 of 32 lessons exit 0. **Part B:** 7 of the 9 re-run lessons pass alone, so their Part A failures were
**interference**. **2 fail alone** (mpt_distribution_101, account_hygiene) and are **their own defects**.

| # | Lesson | Exit (A) | Steps (A) | Transactions (A) | Live verify (A), this lesson's claims | Wall (s) | Part B (alone) |
|---|---|---|---|---|---|---|---|
| 01 | receipt_literacy | 0 | 4 passed, 0 failed | 1 successful, 0 failed | PASS (1) | 19 | |
| 02 | failure_literacy | 0 | 5 passed, 0 failed | 1 successful, 1 failed (1 expected) | PASS (2) | 20 | |
| 03 | trust_lines_101 | 0 | 7 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 24 | |
| 04 | trust_line_failures | 0 | 8 passed, 0 failed | 2 successful, 1 failed (1 expected) | PASS (3) | 29 | |
| 05 | multisig_treasury_101 | 0 | 10 passed, 0 failed | 3 successful, 1 failed (1 expected) | PASS (3, 1 SKIP) | 94 | |
| 06 | nft_minting_101 | 0 | 6 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 18 | |
| 07 | nft_marketplace_101 | 0 | 13 passed, 0 failed | 5 successful, 1 failed (1 expected) | PASS (6) | 69 | |
| 08 | dnft_evolving_item_101 | 0 | 7 passed, 0 failed | 2 successful, 1 failed (1 expected) | PASS (3) | 33 | |
| 09 | mpt_issuance_101 | 0 | 4 passed, 0 failed | 1 successful, 0 failed | PASS (1) | 13 | |
| 10 | **mpt_distribution_101** | **3** | 5 passed, 3 failed | 1 successful, 2 failed | **FAIL** (2 FAIL, 1 PASS) | 26 | **exit 3, 5 passed / 3 failed, verify 1: own defect** |
| 11 | token_freeze_101 | 0 | 14 passed, 0 failed | 6 successful, 0 failed | PASS (6) | 57 | |
| 12 | **clawback_101** | **3** | 9 passed, 3 failed | 2 successful, 3 failed (1 expected) | **FAIL** (2 FAIL, 3 PASS) | 59 | exit 0, 12/0, verify 0: interference |
| 13 | escrow_101 | 0 | 4 passed, 0 failed | 1 successful, 0 failed | PASS (1) | 16 | |
| 14 | escrow_finish_101 | 0 | 9 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 26 | |
| 15 | token_escrow_101 | 0 | 15 passed, 0 failed | 5 successful, 1 failed (1 expected) | PASS (6) | 100 | |
| 16 | **checks_101** | **3** | 11 passed, 2 failed | 3 successful, 2 failed (1 expected) | **FAIL** (1 FAIL, 4 PASS) | 55 | exit 0, 13/0, verify 0: interference |
| 17 | payment_channel_101 | 0 | 13 passed, 0 failed | 3 successful, 0 failed | PASS (3) | 36 | |
| 18 | delivered_amount_101 | 0 | 7 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 24 | |
| 19 | custodial_crediting_101 | 0 | 8 passed, 0 failed | 2 successful, 1 failed (1 expected) | PASS (3) | 30 | (the source of the RequireDest interference) |
| 20 | did_101 | 0 | 6 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 18 | |
| 21 | credentials_101 | 0 | 10 passed, 0 failed | 3 successful, 3 failed (3 expected) | PASS (6) | 62 | |
| 22 | permissioned_domains_101 | 0 | 15 passed, 0 failed | 6 successful, 2 failed (2 expected) | PASS (8) | 76 | |
| 23 | **deposit_gate_101** | **3** | 16 passed, 4 failed | 8 successful, 7 failed (3 expected) | **FAIL** (4 FAIL, 10 PASS, 1 SKIP) | 133 | exit 0, 20/0, verify 0: interference |
| 24 | dex_literacy | 0 | 8 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 21 | |
| 25 | **dex_market_making_101** | **3** | 16 passed, 1 failed | 5 successful, 1 failed | **FAIL** (1 FAIL, 5 PASS) | 53 | exit 0, 17/0, verify 0: interference |
| 26 | **dex_inventory_guardrails** | **3** | 15 passed, 1 failed | 5 successful, 1 failed | **FAIL** (1 FAIL, 5 PASS) | 58 | exit 0, 16/0, verify 0: interference |
| 27 | reserves_101 | 0 | 8 passed, 0 failed | 1 successful, 0 failed | PASS (1) | 11 | |
| 28 | **account_hygiene** | **3** | 10 passed, 5 failed | 0 successful, 3 failed | **FAIL** (3 FAIL) | 5 | **exit 3, 10 passed / 5 failed, verify 1: own defect** |
| 29 | receipt_audit | 0 | 5 passed, 0 failed | 2 successful, 0 failed | PASS (2) | 22 | |
| 30 | **amm_liquidity_101** | **3** | 17 passed, 1 failed | 5 successful, 1 failed | **FAIL** (1 FAIL, 5 PASS) | 59 | exit 0, 18/0, verify 0: interference |
| 31 | dex_vs_amm_risk_literacy | 0 | 25 passed, 0 failed | 9 successful, 0 failed | PASS (9 SKIP: offline lesson) | 1 | |
| 32 | **game_economy_capstone** | **3** | 14 passed, 2 failed | 4 successful, 1 failed | **FAIL** (1 FAIL, 4 PASS) | 60 | exit 0, 16/0, verify 0: interference |

`table_rows.json` holds the same rows, machine-readable.

## Failures and their causes

### Interference: an earlier lesson's ledger state (7 lessons; each passes alone)

1. **custodial_crediting_101 leaves `asfRequireDest` on the learner.** It sets the flag (AccountSet SetFlag 1,
   `44B89718…`) and never clears it. The learner ends the course with `Flags 0x20000` (`lsfRequireDestTag`). Every
   later lesson that pays the learner without a destination tag then fails `tecDST_TAG_NEEDED`:
   - deposit_gate_101 steps 5, 9, 14, 16 (4 txs);
   - dex_market_making_101 step 6 (LAB issue `B5B02C9F…`);
   - dex_inventory_guardrails step 6;
   - amm_liquidity_101 step 7 (LAB issue);
   - game_economy_capstone step 12 (the reward escrow) and step 15.

   This is the same class as #20 item 15 (deposit_gate's DepositAuth, fixed in 2.7.2; its cleanup works here: SetFlag
   9, then ClearFlag 9).
2. **clawback_101 reuses the workspace's issuer wallet.** That issuer already owns objects from earlier lessons, so
   "Enable clawback on the issuer (BEFORE issuing)" fails **`tecOWNERS`**. asfAllowTrustLineClawback needs an
   issuer with no owned objects. The later Clawback then fails `tecNO_PERMISSION`.
3. **checks_101 runs out of XRP.** The learner's single faucet grant had fallen to **49.99967 XRP** by lesson 16. The
   lesson's 50 XRP Check could not be cashed: **`tecPATH_PARTIAL`**. Nothing in the course tops the learner up again,
   and alone it passes.

### Own defects (2 lessons; each fails alone too)

4. **mpt_distribution_101 signs the issuance with the wrong account.** The lesson creates an issuer wallet, but
   **MPTokenIssuanceCreate is signed by the learner** (`98930C4D…`). The learner's opt-in MPTokenAuthorize
   (`C6EED576…`) is then **`tecNO_PERMISSION`**: an issuer cannot hold its own MPT. The issuer wallet's Payment is
   **`tecNO_AUTH`**: it is not the issuer of that issuance. The same happened in Part A and Part B.
5. **account_hygiene uses an invalid currency code.** It uses the currency code `HYGIENE`. XRPL currency codes are 3
   characters or 40 hex digits, so xrpl-py rejects it before signing ("Invalid currency HYGIENE"). Its TrustSet,
   OfferCreate and removal never reach the network, and 5 steps fail. Not a 2.7.0 regression: **xrpl-py 4.5.0 rejects
   it too** (checked in an isolated environment).
   - In live verify, its local failure is recorded with txid `"failed"`, which the verifier reports as "Transaction not
     found on the public ledger". It's a genuine failure either way. A clearer reason for a local, never-submitted
     failure would help.

## Hashes to check on testnet

| What | Hash | Expected on testnet |
|---|---|---|
| An expected tec (failure_literacy) | `C63913E7FF2524DBF893209670FE53E1436C0BBFC3B29356A7736EC29B8EC020` | Payment, `tecUNFUNDED_PAYMENT`, validated |
| A helper-signed success (nft_marketplace_101 buyer `rhvFFExP…`) | `4DF565050E0CACD3000FBF6516DBDD616EA1506BE424FCFD68AD113FFC35AD31` | NFTokenAcceptOffer, `tesSUCCESS`, Account ≠ learner `r9vWv5PL…` |
| The RequireDest left on (custodial_crediting_101) | `44B89718D5C2788D60DF38443FCAADD00B78BCE8B45F5305D7BAEC7C133E37BF` | AccountSet SetFlag 1, `tesSUCCESS`, learner `r9vWv5PLZiT3hHsgUUkEr4TVn6KP1bPKqq` (Flags still `0x20000`) |
| An interference failure (dex_market_making_101 LAB issue) | `B5B02C9FBEA48F876D2441DD561032940582DF4B74788458C4329944A00FA5A3` | Payment, `tecDST_TAG_NEEDED` |
| The own defect (mpt_distribution_101, Part B) | `98930C4DF24612A07FA4F9667A170546961240E07C77C281F01F7786CCCEE4F8` and `C6EED5760B69E18F789BDABCD5FE6EC1A015871226558BF543E2C61DDE314F28` | MPTokenIssuanceCreate signed by the learner, then MPTokenAuthorize `tecNO_PERMISSION` by the same learner |

## Files

- `A/<NN>-<lesson>/` holds `command.txt` (exit code, wall seconds, "Module interrupted" count), `stdout.txt`,
  `stderr.txt` and `module_report.md`.
- `A/` also holds `preflight.txt`, `proof_pack.json` (the full course), `verify_live.json` / `.txt` /
  `verify_exit.txt` and `state_excerpt.json`.
- `B/<lesson>/` holds `command.txt` (exit code, verify exit code), `preflight.txt`, `stdout.txt`, `stderr.txt`,
  `module_report.md`, `proof_pack.json`, `verify_live.json`, `state_excerpt.json` and `ledger_evidence.json`.
