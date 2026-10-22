# 2.7.5 live checks on `7298174`

These are the three live testnet checks the Editor asked for on **`7298174`** (PR #33, `feat/2.7.5`), the commit Argon
passed with no findings. 2.7.5 fixes #32: a failure older than its module's passing latest run is checked as history
in live verification. It is SKIPPED if it never reached a ledger, and PASS if it is on the ledger as recorded.
`failed` placeholders are keyed per module.

No seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>` and `<worktree>`.
Each `state_excerpt.json` holds `module_accounts`, completed modules with `verified`, and `tx_index`, with
`wallet_path` omitted. Each `drift.jsonl` holds addresses, flags and balances only.

- **Installed version:** the editable install was reinstalled on this head, so it reports 2.7.5 and every pack here
  records `"version": "2.7.5"`.
- **Preflight:** every home passed it. The RPC/faucet env was unset, except where run 1 sets the faucet URL on purpose.
  `classify_network` = testnet, and the network guard passed.

## Verdict

| Check | Expected | Result |
|---|---|---|
| 1. `--force` end to end | run 1 exit 3, `verified: false`; `--force` exit 0, `verified: true`; live verify exit 0, run 1's placeholders SKIPPED | **Run 1:** exit 3, `verified: false`, 0 txids, 4 `failed` placeholders. **Run 2 (`run --force`):** exit 0, "Steps: 12 passed, 0 failed", the same record now `verified: true` with 4 txids. **Live verify: exit 0**, 5 PASS, 1 SKIPPED. The SKIP is the `failed` claim: "An earlier run's step that never reached a ledger; this module's latest run passed." |
| 2. A module left failed | live verify exit 1, the placeholder FAILing as "failed before its transaction reached the network" | **Run 1:** exit 3, `verified: false`, 4 `failed` placeholders, no rerun. **Live verify: exit 1**, 0 PASS, 1 FAIL: "A step failed before its transaction reached the network (no hash was recorded), so there is nothing on the ledger to check." |
| 3. Full 32-lesson course sweep, one home | 32 exit 0; live verify exit 0; no flag left on | **32 of 32 exit 0.** Pre-pass 32/32. Full-pack live verify **exit 0, 123 PASS, 11 SKIPPED**, no FAIL. No flag is left on after any lesson, and the learner ends with Flags `[]`. No Part B ran, and no lesson fell below the 40 XRP floor. |

Notes on checks 1 and 2:
- In both, run 1 used `XRPL_LAB_FAUCET_URL` set to a path that does not exist on the testnet faucet host. Funding
  fails with a 404, and every later step fails with `actNotFound`. The run ends "Not verified: 7 steps failed" and exit
  3.
- The gate (exit 3 and a `verified: false` record) passed both times. These scripts stop on a failed gate rather than
  seeding a record.
- The 4 placeholders collapse into one `failed` claim per module, as 2.7.5 keys them.
- `records.txt` holds the record after each run, and `gate.txt` the gate.

Notes on check 3:
- custodial_crediting_101 shows `+asfRequireDest, -asfRequireDest` in-lesson.
- deposit_gate_101 shows `+asfDepositAuth, -asfDepositAuth` in-lesson.
- account_hygiene's removal TrustSet carries `tfSetNoRipple`.

`check3-full-sweep/summary.md` holds the generated table.

## Off the brief

- **The harness still calls `proof verify --live`.** The Editor asked for `verify-artifact`, but it has no `--live`
  option on this head, so switching would drop the on-ledger check. The Editor filed this as #34, outside 2.7.5. The
  harness README records why. Every `verify_live.err` here holds only the deprecation notice.

## Hashes to check on testnet

| What | Hash | Expected |
|---|---|---|
| Check 1: run 2's Clawback | `DA0A0FEB874E6F17EDA4F6E60F924FC948E1F94FB0EFF6230187A38E3740BECA` | Clawback, tesSUCCESS |
| Check 1: run 2's AccountSet (enables clawback) | `AFDC737FA536D06CECAC81C2C0431A7919206E8DC3EAA55B0B9FE5BCC58B1B0D` | AccountSet, tesSUCCESS |
| Check 1: run 2's expected rejection | `A314F29401D4E1A1B97EA4D9105A28C9BDCC87B4876050BCBC17855FCFFE6552` | Clawback, tecNO_PERMISSION, validated |
| Check 3: account_hygiene's HYG removal TrustSet | `2BC835EC24D898EC0FC3449642E489F068D02229D7D6C2CA1829809BF38A8BCE` | TrustSet HYG limit 0, Flags 131072, tesSUCCESS |
| Check 3: custodial_crediting sets RequireDest | `52638E51D6C0195A4F19A999299B3A080BDFE761BB0757EE677C57A0D816CC44` | AccountSet SetFlag 1, tesSUCCESS |
| Check 3: custodial_crediting clears it | `1F7F391AE28B4379211DFAF1D3AF0F3851F89D35C9D21397DE3A2BE8FA7485C2` | AccountSet ClearFlag 1, tesSUCCESS |
| Check 3: deposit_gate sets DepositAuth | `B86980ACE3E2BD0B72DF3829F54E595E0B9B29E74511375C6BC588AC37BBAAA3` | AccountSet SetFlag 9, tesSUCCESS |
| Check 3: deposit_gate clears it | `F7A8B4B6A8ECCADD90B2EE808A850E70EC70055633FB59FDD53F6C356C64197E` | AccountSet ClearFlag 9, tesSUCCESS |

## Files

- `check1-force/` holds:
  - `1-failing/` and `2-force/`, each with `command.txt` (cmd, env, exit code), `preflight.txt`, and `stdout.txt` /
    `stderr.txt`. `2-force/` also has `module_report.md`;
  - `records.txt`, `gate.txt` and `preflight_verify.txt`;
  - `proof_pack.json`, `verify_live.json`, `verify_live.exit` and `state_excerpt.json`.
- `check2-left-failed/` has the same layout without `2-force/`.
- `check3-full-sweep/` has the same layout as the 2.7.4 sweeps:
  - `prepass/`;
  - `A/<NN>-<lesson>/` with `command.txt`, `stdout.txt` / `stderr.txt`, `module_report.md`, `classify.json` and
    `verify_live.json`;
  - `A/drift.jsonl`, `A/proof_pack.json`, `A/verify_live.json` and `A/state_excerpt.json`;
  - `summary.md`, `summary.json` and `sweep.log`.
