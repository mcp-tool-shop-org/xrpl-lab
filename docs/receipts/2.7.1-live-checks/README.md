# 2.7.1 live checks

These are the live acceptance checks for 2.7.1 (PR #24, `feat/2.7.1`) on `9aa461b`, the commit Argon passed (GO).
2.7.1 fixes two findings from the 2.6.2 live sweep:
- **#20 item 12:** a `validated` flag on records, and no explorer link for a transaction that never validated. The
  multisigned `tef` keeps its hash.
- **#20 item 13:** a `mode: dry-run` lesson runs offline however it is started.

`25ea23d` (Argon round 1: no stored dead links, among others) landed after this run and is not covered.

**Verdict: PASS, 4 of 4.** One observation follows, on `state.json`'s `explorer_url`.

No seeds and no wallet files are in this directory. `state_tx_index.json` is the `tx_index` excerpt of each
`state.json`; `wallet_path` is left out because it carries the local home path.

## Setup

- One clean worktree pinned at `9aa461b` (xrpl-lab 2.7.1, xrpl-py 5.2).
- A fresh `XRPL_LAB_HOME` per module, outside every repo.
- Before each module: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Command: `yes "" | xrpl-lab run <module>`, with the exit code from `PIPESTATUS[1]`. **No `--dry-run` on any module**,
  including dex_vs_amm_risk_literacy.
- After each module: `xrpl-lab proof-pack`, then a read-only ledger capture.
- 60 s faucet spacing.

**Time:** 2026-10-21 15:18–15:26 UTC.

| # | Check | Exit | Steps | Transactions | Result |
|---|---|---|---|---|---|
| 1 | deposit_gate_101, live: the `temCANNOT_PREAUTH_SELF` record | 0 | 18 passed, 0 failed | 8 successful, 5 failed (5 expected) | **PASS.** txid `512F138B2A4C…` is 64-hex, **`validated: false`**, and `explorer_url` is `""` in `state.json` **and** in the proof pack (`transactions`). The receipt row has `validated: false`. On the ledger it is `txnNotFound`, as a `tem` should be. The four expected `tec`s (`1861E3D4…`, `D930741C…` tecNO_PERMISSION; `B8BF2717…` tecDUPLICATE; `EFEFB636…` tecNO_ENTRY) are `validated: true`, carry proof-pack testnet links, and are validated on the ledger. |
| 2 | multisig_treasury_101, live: the `tefBAD_QUORUM` record | 0 | 10 passed, 0 failed | 3 successful, 1 failed (1 expected) | **PASS.** txid `98307BEA3788…` is **64-hex (not "failed")**, **`validated: false`**, and `explorer_url` is `""` in `state.json` and the proof pack. A ledger lookup finds the signed Payment as known to the server but **not validated**, as a `tef` should be (never applied). |
| 3 | failure_literacy, live: the `tecUNFUNDED_PAYMENT` record | 0 | 5 passed, 0 failed | 1 successful, 1 failed (1 expected) | **PASS.** `1E784AD72619…` has **`validated: true`**. The proof pack carries `https://testnet.xrpl.org/transactions/1E784AD7…`. On the ledger it is a Payment, `tecUNFUNDED_PAYMENT`, validated. |
| 4 | `xrpl-lab run dex_vs_amm_risk_literacy`, **without `--dry-run`** | 0 | 25 passed, 0 failed | 9 successful, 0 failed | **PASS.** stdout line 1 reads "'dex_vs_amm_risk_literacy' is an offline lesson (mode: dry-run); running it in the dry-run sandbox, not on the network." `state.json` and the proof pack say network `dry-run`. None of its 9 hashes exists on testnet. (9 matches its `tx_index`; 2.6.2's report said 7 because it did not count every recorded tx, fixed in 2.7.0's `c67cdf8`.) |

stderr is empty in all four.

## Observation: `state.json`'s `explorer_url` for expected failures (pre-existing; for Argon's F2)

Argon's F2 concern was an unvalidated record holding a URL in `state.json`. **That did not occur on `9aa461b`.** Both
unvalidated records (`512F138B…`, `98307BEA…`) have `explorer_url: ""` in `state.json`.

What does happen is the reverse:
- **Every expected-failure record** has `explorer_url: ""` in `state.json`, **including the validated `tec`s**
  (deposit_gate ×4, failure_literacy ×1).
- **Every ordinary success record** has a URL.
- The proof pack adds the link for validated records, so the shared artifact is right.

2.6.2's `state.json` behaved the same, so this is not a 2.7.1 change. If `state.json` should match the proof pack, a
validated expected `tec` needs its URL there too.

## Live proof verification on `da63f40` (`sweep-da63f40-20261021T1545Z`)

**The defect `da63f40` addresses** (released in 2.6.2 and 2.7.0): `proof verify --live` checked every claim for
`tesSUCCESS`. So a rejection lesson's honest pack failed live verification: each expected `tec` as "not
tesSUCCESS", and each `tem` as "not found". `da63f40` checks an expected rejection as one. `ca8e968` (Argon round 3,
F1) landed after this run and is not covered.

**What was run:**
- deposit_gate_101 and multisig_treasury_101 live on `da63f40`, each with a fresh `XRPL_LAB_HOME` and the same setup
  as above. deposit_gate: exit 0, 18/0, "8 successful, 5 failed (5 expected)". multisig: exit 0, 10/0, "3 successful,
  1 failed (1 expected)". stderr empty.
- Then `xrpl-lab proof verify --live proof_pack.json` on each pack (`verify_live.txt`; deposit_gate also with `--json`,
  `verify_live.json`).

| Pack | Verifier | Exit | Overall | Per-tx verdicts |
|---|---|---|---|---|
| multisig_treasury_101 (2.7.1) | `da63f40` | **0** | **PASS**: 3 verified, 1 skipped | 3 successes PASS. The `tefBAD_QUORUM` `DAFCE065…` is SKIP: "Expected rejection that never reaches a ledger (by design)." |
| deposit_gate_101 (2.7.1) | `da63f40` | **1** | **FAIL**: 3 failed, 9 verified, 1 skipped | **The 4 expected `tec`s PASS** as "Expected rejection, validated on-ledger: tecNO_PERMISSION / tecDUPLICATE / tecNO_PERMISSION / tecNO_ENTRY" (`F5C418AB…`, `6E1F0490…`, `3ADF073E…`, `36D4CB22…`). The `temCANNOT_PREAUTH_SELF` `12D008E7…` is SKIP ("never reaches a ledger (by design)"). The learner's 6 successes PASS. **3 successes FAIL**: "On-ledger account does not match the pack's claimed address". These are the sender's preauthorized Payment `213B629D…` (signed by helper `r422taaU…`), and the subject's CredentialAccept `8A52D055…` and KYC Payment `0842B07B…` (signed by helper `rJi5XTfL…`). |
| deposit_gate_101 from the **2.6.2** sweep (`8ae1c4e`) | **old v2.6.2** (`d075b96`) | **1** | FAIL | The released defect: **the 4 `tec`s FAIL** "On-ledger result is tec…, not tesSUCCESS"; **the `tem` FAILs** "Transaction not found on the public ledger". Plus the same 3 helper-signed successes FAIL the address check. |
| the same 2.6.2 pack | `da63f40` | **1** | FAIL | The 4 `tec`s now PASS ("Expected rejection, validated on-ledger"), and the `tem` is SKIPPED ("a tem or tef never is"). **The 3 helper-signed successes still FAIL the address check.** |

**Result:**
- **`da63f40` fixes the released rejection defect.** On both the 2.7.1 and the 2.6.2 deposit_gate packs, every
  expected `tec` now PASSes as an expected rejection, and every `tem`/`tef` is SKIPPED. multisig's pack passes overall.
- **A second, pre-existing defect still fails deposit_gate's honest pack** on every release tested. Live verify
  requires each success to be signed by the pack's single `address` (the learner). A module whose helper wallets sign
  successful transactions recorded in the learner's pack can never pass `--live`.
- The check is inconsistent: helper-signed expected `tec`s pass (`F5C418AB…` by `r422taaU…`, `3ADF073E…` by the
  outsider `rPEjTQ98…`), but helper-signed successes fail.
- Every other existing pack was then verified the same way, read-only, to map the defect. See "Map" below.

## Map: `proof verify --live` (`da63f40`) on every existing pack (`verify-live-map-da63f40/`)

The scope is the 2.6.2 live sweep (`8ae1c4e`, 14 packs) and the 2.7.0 live sweep (`4deed70`, 11 packs). Each pack was
verified once with the `da63f40` verifier, read-only, with no new testnet transactions. The 2.6.1 sweeps have no
proof packs: the harness only started writing them with 2.6.2.

**Result:**
- **18 of 25 packs FAIL (exit 1).**
- **17 of them fail only on "On-ledger account does not match the pack's claimed address"**, 32 transactions in all.
- **Every one of the 32 is a successful transaction signed by a non-learner account:** an issuer, recipient, subject,
  buyer, payment-channel receiver or player wallet that the module creates.
- The 18th, escrow_finish_101 on `4deed70`, fails on its genuine `tecNO_PERMISSION` (the FinishAfter race, fixed in
  2.7.0). That is a correct FAIL.

| Sweep | Module | Exit | Account-mismatch FAILs (all successes; signer) | Other FAIL | Helper-signed expected `tec`s that PASS |
|---|---|---|---|---|---|
| 2.6.2 | checks_101 | 1 | 1: CheckCash (recipient) | none | 1 (outsider's CheckCash) |
| 2.6.2 | clawback_101 | 1 | 3: AccountSet, Payment, Clawback (issuer) | none | 1 (no-flag issuer's Clawback) |
| 2.6.2 | credentials_101 | 1 | 2: CredentialAccept, CredentialDelete (subject) | none | none |
| 2.6.2 | custodial_crediting_101 | 1 | 1: Payment (player) | none | 1 (player's untagged Payment) |
| 2.6.2 | deposit_gate_101 | 1 | 3: Payment (sender); CredentialAccept, Payment (subject) | none | 2 (sender's and outsider's Payments) |
| 2.6.2 | nft_marketplace_101 | 1 | 2: NFTokenAcceptOffer, NFTokenCreateOffer (buyer) | none | none |
| 2.6.2 | permissioned_domains_101 | 1 | 2: CredentialAccept, OfferCreate (subject) | none | 2 (outsider's OfferCreate and PermissionedDomainSet) |
| 2.6.2 | token_escrow_101 | 1 | 3: AccountSet, Payment (issuer); EscrowFinish (recipient) | none | none |
| 2.6.2 | trust_line_failures | 1 | 1: Payment (issuer) | none | 1 (Payment tecPATH_DRY) |
| 2.6.2 | dex_vs_amm_risk_literacy | 0 | none | none | none (all 9 SKIPPED: dry-run) |
| 2.6.2 | dnft_evolving_item_101, escrow_101, failure_literacy, multisig_treasury_101 | 0 | none | none | none |
| 2.7.0 | amm_liquidity_101 | 1 | 2: AccountSet, Payment (issuer) | none | none |
| 2.7.0 | checks_101 | 1 | 1: CheckCash (recipient) | none | 1 |
| 2.7.0 | clawback_101 | 1 | 3: AccountSet, Payment, Clawback (issuer) | none | 1 |
| 2.7.0 | deposit_gate_101 | 1 | 3: Payment (sender); CredentialAccept, Payment (subject) | none | 2 |
| 2.7.0 | dex_market_making_101 | 1 | 1: Payment (issuer) | none | none |
| 2.7.0 | escrow_finish_101 | 1 | none | 1: EscrowFinish "tecNO_PERMISSION, not tesSUCCESS" (the real race failure) | none |
| 2.7.0 | nft_marketplace_101 | 1 | 2: NFTokenAcceptOffer, NFTokenCreateOffer (buyer) | none | none |
| 2.7.0 | payment_channel_101 | 1 | 1: PaymentChannelClaim (receiver) | none | none |
| 2.7.0 | trust_lines_101 | 1 | 1: Payment (issuer) | none | none |
| 2.7.0 | did_101, multisig_treasury_101 | 0 | none | none | none |

**What this means:**
- Every honest pack from a module that creates its own issuer or counterparty fails `--live` today. That includes
  module #30, amm_liquidity_101, the 2.6.0 acceptance module (its issuer's AccountSet and LAB issue).
- The only packs that pass are those where the learner signs every success: dnft, escrow_101, failure_literacy,
  multisig, did, plus dex_vs_amm, which has nothing to check.
- The verifier is inconsistent: helper-signed expected rejections pass in 7 packs (11 txs), while helper-signed
  successes fail.

`verify-live-map-da63f40/` holds each pack's `--json` verdict, and `summary.json` (module, exit, status counts,
mismatch count, other FAIL reasons). The packs themselves are in this directory's and `2.6.2-live-sweep/` /
`2.7.0-live-sweep/`'s run folders.

`before-after-2.6.2-pack/` holds the 2.6.2 pack and both verifiers' JSON output. The old-release run used a temporary
worktree at the `v2.6.2` tag, since removed.

## The helper-account fix, live on `e32d090` (`accounts-check-e32d090-20261021T1639Z/`)

`e32d090` (Argon round 6 GO) records each lesson's accounts (the learner plus the helpers it binds) in
`state.module_accounts`, and carries them in the pack's `module_accounts`. Live verification accepts a transaction
signed by any of a lesson's recorded accounts. Older records keep the learner-only check, and `reset --module`
clears a lesson's entry. `e5da712` landed after this run and is not covered.

**Verdict:**
- **The fix works.** Every helper-signed transaction whose result is the lesson's own now PASSes, and every helper is
  listed in its lesson's `module_accounts`.
- Neither pack below reaches exit 0, though. The cause is **two curriculum and ledger-state defects that the fix
  uncovered**, not the verifier.

### A: three lessons in one fresh home

The lessons, in order: deposit_gate_101, amm_liquidity_101, nft_marketplace_101, live, one learner wallet
`rMZpZ5Hu…`.

| Module | Exit | Note |
|---|---|---|
| deposit_gate_101 | 0 | all steps passed |
| amm_liquidity_101 | **3** | 6 steps failed. See defect 1. |
| nft_marketplace_101 | 0 | all steps passed |

**`proof verify --live`: exit 1**, "2 failed, 20 verified, 1 skipped".
- **Every helper-signed transaction PASSes:**
  - deposit_gate: the sender's Payment `A1B91AA4…`, the subject's CredentialAccept `45A8EE00…` and KYC Payment
    `8F7189D5…`, plus the expected `tec`s `0F191B34…` (sender) and `EEBB5710…` (outsider);
  - amm: the issuer's AccountSet `6D78F44B…`;
  - nft: the buyer's NFTokenAcceptOffer `339AADEC…` and NFTokenCreateOffer `EEE5B7FA…`.

  The PASS reason reads "Verified on-ledger." (successes) or "Expected rejection, validated on-ledger: tec…", not
  "Account matches: r…".
- `module_accounts`: deposit_gate has 4 accounts (the learner, sender, subject, outsider), amm has 2 (the learner,
  issuer), nft has 2 (the learner, buyer).
- **The 2 FAILs are both amm_liquidity_101's,** and both are genuine:
  - the issuer's LAB issue Payment `0333220B…` is **`tecNO_PERMISSION`**;
  - the AMMCreate `5EF97240…` is **`tecUNFUNDED_AMM`**.

### B: the da63f40 deposit_gate home (a record from before e32d090)

1. **`proof verify --live` on its pack: exit 1, as expected.** "5 failed, 7 verified, 1 skipped". `module_accounts`
   is `{}`. The 3 helper-signed successes FAIL on the address check, as before. Now the 2 helper-signed expected `tec`s
   (`F5C418AB…`, `3ADF073E…`) also FAIL, as "is not the learner or one of this module's recorded helper wallets".
   (Under `da63f40` they passed. The old-record path is now learner-only throughout, which is consistent.)
2. `xrpl-lab reset --module deposit_gate_101 --confirm`: exit 0, "Cleared 13 tx record(s); report removed: True".
3. **The re-run: exit 3**, 1 step failed. See defect 2.
4. **`proof verify --live`: exit 1**, "1 failed, 11 verified, 1 skipped". **All 5 helper-signed txs PASS** (3
   successes, 2 expected `tec`s), and `module_accounts` lists 4 accounts. The one FAIL is defect 2's genuine
   `tecDUPLICATE` (`B2AA5569…`).

### Defect 1: deposit_gate_101 leaves Deposit Authorization on the learner's wallet

deposit_gate turns on `asfDepositAuth` for the learner (the "treasury") and never turns it off. After the run, the
learner's account `Flags` read `0x01000000` (`lsfDepositAuth`) on the validated ledger.

Any later lesson in the same home that pays the learner is then refused. Here, amm_liquidity's issuer could not issue
LAB to the learner (`tecNO_PERMISSION`), so the AMMCreate had no LAB (`tecUNFUNDED_AMM`), and amm failed 6 steps.

A workshop runs lessons in sequence in one home, so this breaks every later lesson that receives a payment.
Possible fixes: deposit_gate clears the flag at its end, or lessons that receive payments check for it.

### Defect 2: deposit_gate_101 can't be re-run on the same wallet after `reset --module`

`reset --module` clears only local state. The first run's credential-based preauthorization (DepositPreauth
`AuthorizeCredentials` for the learner's own `kyc-deposit` credential type) is still on the ledger. So the re-run's
DepositPreauth validates **`tecDUPLICATE`** (`B2AA5569…`), which is not one of the lesson's expected rejections.

The lesson needs to tolerate or clean up its own ledger objects from an earlier attempt.

The run folder holds A and B with each module's `command.txt` (exit code), `stdout.txt` / `stderr.txt` (stderr
empty throughout), each pack's `proof_pack.json`, and `verify_live.json` / `verify_live.txt` / `verify_exit.txt`.
`state_excerpt.json` holds `module_accounts`, the completed modules and `tx_index`, with `wallet_path` omitted. There
is also `B/reset.txt`.

## Files

`sweep-9aa461b-20261021T1517Z/<module>/` holds:
- `command.txt`, with the exit code;
- `preflight.txt`;
- `stdout.txt`, with the scratch path redacted;
- `stderr.txt`;
- `module_report.md`;
- `proof_pack.json`;
- `state_tx_index.json`;
- `ledger_evidence.json`.
