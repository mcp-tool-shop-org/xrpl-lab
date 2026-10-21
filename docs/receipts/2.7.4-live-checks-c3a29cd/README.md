# 2.7.4 live checks on `c3a29cd`

These are the three live testnet checks the Editor asked for on **`c3a29cd`** (PR #29, `feat/2.7.4`), the commit Argon
passed in round 3. `c3a29cd` fixes the two findings of the 2.7.4 full sweep (PR #30):
- `run --force` now updates the module record;
- the trust-line removal now sets `tfSetNoRipple`, so the line is deleted.

No seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>` and `<worktree>`.
Each `state_excerpt.json` holds `module_accounts`, completed modules with `verified`, and `tx_index`, with
`wallet_path` omitted. Each `drift.jsonl` holds addresses, flags and balances only.

Every home passed the preflight: the RPC/faucet env unset (except where check 2 sets the faucet URL on purpose),
`classify_network` = testnet, network guard PASS.

## Verdict

| Check | Expected | Result |
|---|---|---|
| 1. account_hygiene alone, fresh home | exit 0; owner count back to baseline (−2 after cleanup); HYG line gone | **exit 0**, 15 passed / 0 failed, 4 successful txs. Owner count 0 → 2 → **0**. `account_lines` on the learner returns `[]`. Live verify exit 0 (4 PASS). |
| 2. `--force` path | run 1 exit 3 with `verified: false`; `--force` rerun exit 0 with `verified: true` and both runs' txids | **run 1 exit 3**, `verified: false`, 0 txids. The gate passed and no fallback was used. **Run 2 exit 0**, "Steps: 12 passed, 0 failed", `verified: true`, 4 txids, all tesSUCCESS on the ledger. One record, updated in place. |
| 3. Full 32-lesson course sweep, one home | 32 exit 0; live verify exit 0; no flag left on | **32 of 32 exit 0.** Full-pack live verify **exit 0, 123 PASS, 11 SKIPPED**, no FAIL. No flag is left on after any lesson, and the learner ends with Flags `[]`. No Part B ran. Pre-pass: 32/32 offline exit 0. |

### Check 1 detail

- The 4 txs are TrustSet HYG limit 100, OfferCreate, OfferCancel, then TrustSet HYG limit 0 with **Flags 131072
  (`tfSetNoRipple`)**. All are tesSUCCESS.
- The module's own output reads "Owner count: 0", "Owner count: 2", then "✓ Trust line for HYG successfully removed"
  and "Owner count: 0".
- On the ledger after the run, the drift log has owner count 0 and trust lines 0, and `account_lines` is empty.

### Check 2 detail

- **Run 1** had `XRPL_LAB_FAUCET_URL` set to a path that does not exist on the testnet faucet host, so funding fails
  ("Faucet returned 404"). Every later step then fails with `actNotFound`.
  - It ends "Not verified: 7 steps failed" and "'clawback_101' completed with failed steps; exiting with code 3".
  - `state.json` holds one clawback_101 entry with `verified: false` and no txids, since nothing reached the ledger.
    "Txids of both runs" therefore means run 2's 4.
- **Run 2** used the normal faucet: `run --force clawback_101`, "Steps: 12 passed, 0 failed", exit 0.
  - The same entry now reads `verified: true` with 4 txids: AccountSet, TrustSet, Payment, Clawback.
  - `tx_index` also holds the expected-failure Clawback `743BE991…`, which is tecNO_PERMISSION and validated.
- `records.txt` holds the entry after each run, and `gate.txt` the gate result.

### Check 3 detail

- custodial_crediting_101 shows **`+asfRequireDest, -asfRequireDest`** in-lesson.
- deposit_gate_101 shows **`+asfDepositAuth, -asfDepositAuth`**.
- No net flag change after any lesson.
- account_hygiene in the course removes its line: owner count 12 before, 12 after. No HYG line remains on the learner.
- checks_101 ends with 97.0 XRP spendable. No lesson fell below the 40 XRP floor.
- clawback_101 and mpt_distribution_101 pass in the course, at 12/0 and 8/0.

`check3-full-sweep/summary.md` holds the generated one-row-per-lesson table.

## Off the brief

1. **A pack from a home that failed once and then passed with `--force` fails live verify.**
   - This is check 2's home, packed after run 2: `proof verify --live` gives exit 1, 5 PASS, 1 FAIL.
   - The FAIL is txid `"failed"`. Run 1 wrote 4 `tx_index` records with that placeholder, one for each step that failed
     before it reached the network, and the pack carries them.
   - The verifier reports them as "A step failed before its transaction reached the network". Its integrity check
     passes and the module record is `verified: true`.
   - So a learner who recovers with `--force` still cannot get a clean `proof verify --live` for that pack.
   - It is outside the three checks, and nothing in the course sweep hits it. It is a question for the Editor and
     Argon: should the pack drop or skip a run's no-hash records once a forced rerun of that module has passed, or is
     the FAIL the intended history?
   - Files: `check2-force/proof_pack.json` and `verify_live.json`.
2. `proof verify` prints "`proof verify` is deprecated, use `verify-artifact`" on stderr. The harness still calls
   `proof verify`.

## Hashes to check on testnet

| What | Hash | Expected |
|---|---|---|
| Check 1: account_hygiene's HYG removal TrustSet | `A53F02A432409C17E2C9EA7AD5E339629685723D27C35D209B3F57F72DEE3551` | TrustSet HYG limit 0, Flags 131072 (`tfSetNoRipple`), tesSUCCESS. Learner `rDUQE3kt…` has no lines afterwards. |
| Check 3: the same removal in the course | `2A2CDAEADBA46F39616402637BA86EA4CD064781BBFB5418AB1DD6CEEE345AB9` | TrustSet HYG limit 0, Flags 131072, tesSUCCESS |
| Check 2: run 2's Clawback | `597503F1B79C2C23BF41BE91D11BDFDDD3645EA4309927CEF7C9DF81C4D5962C` | Clawback, tesSUCCESS |
| Check 2: run 2's expected rejection | `743BE991609A9C1008E8061C1545B9D3372D8437A964E081AC16D10E2E65AB2E` | Clawback, tecNO_PERMISSION, validated |
| Check 3: custodial_crediting sets RequireDest | `29775845AE814881A3AE441FDF314267DEE4452F3BC59C0D195483C45C15A4A9` | AccountSet SetFlag 1, tesSUCCESS |
| Check 3: custodial_crediting clears it | `01675700AF6E63B4D900D2738374E8C7E14E2A0A3742080852EDDB45A2E61423` | AccountSet ClearFlag 1, tesSUCCESS |
| Check 3: deposit_gate sets DepositAuth | `9E0B9F3AFB9CFE281B407D85E314DDCD498B699BD0605F24B4CAABD4EAC69B6E` | AccountSet SetFlag 9, tesSUCCESS |
| Check 3: deposit_gate clears it | `5FDB28AAD4D16CF669750EE87E39CD89D4A621D5E33BA337EF71C42E9B00050C` | AccountSet ClearFlag 9, tesSUCCESS |

## Files

- `check1-account_hygiene/` is a `course_sweep.py --lessons account_hygiene` run:
  - `A/01-account_hygiene/`;
  - `A/drift.jsonl`, `A/proof_pack.json`, `A/verify_live.json` and `A/state_excerpt.json`;
  - `summary.md`, `summary.json` and `sweep.log`.
- `check2-force/` holds:
  - `1-failing/` and `2-force/`, each with `command.txt` (cmd, env, exit code), `preflight.txt`, and `stdout.txt` /
    `stderr.txt`. `2-force/` also has `module_report.md`;
  - `records.txt` and `gate.txt`;
  - `proof_pack.json` and `verify_live.json` (finding 1), and `state_excerpt.json`.
- `check3-full-sweep/` has the same layout as the 2.7.4 full sweep (PR #30):
  - `prepass/`;
  - `A/<NN>-<lesson>/` with `command.txt`, `stdout.txt` / `stderr.txt`, `module_report.md`, `classify.json` and
    `verify_live.json`;
  - `A/drift.jsonl`, `A/proof_pack.json`, `A/verify_live.json` and `A/state_excerpt.json`;
  - `summary.md`, `summary.json` and `sweep.log`.
