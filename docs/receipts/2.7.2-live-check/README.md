# 2.7.2 live check: deposit_gate cleans up after itself

This is the live acceptance check for 2.7.2 (PR #25, `feat/2.7.2`) on `9da6231`, the commit Argon passed (GO). 2.7.2
fixes #20 items 15 and 16, both found in the 2.7.1 live check:
- deposit_gate_101 left `lsfDepositAuth` on the learner, which broke later lessons that pay the learner.
- It could not be re-run on the same wallet after `reset --module` (`tecDUPLICATE`).

`c883565` (a failed ClearFlag fails the step; the checks list names the cleanup) landed after this run and is not
covered.

**Verdict: PASS, all four steps.** Everything ran in **one fresh home** (learner `rNqAHBdAypisqfogzYnKw65uXXiV68FNTF`).

No seeds and no wallet files are in this directory. Run folders are written as `<scratch>`. `state_excerpt.json` holds
`module_accounts`, the completed modules and `tx_index`, with `wallet_path` omitted.

## Setup

- One clean worktree pinned at `9da6231` (xrpl-lab 2.7.2).
- One fresh `XRPL_LAB_HOME`, outside every repo.
- Preflight: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Command: `yes "" | xrpl-lab run <module>`, with the exit code from `PIPESTATUS[1]`.
- After each deposit_gate run, the learner's `Flags` were read from the validated ledger (`flags.txt`).
- `proof verify --live` ran from inside the run folder, so its output names `proof_pack.json` only.
- 60 s faucet spacing.

**Time:** 2026-10-21 17:35–17:50 UTC.

| # | Step | Exit | Steps | Transactions | Result |
|---|---|---|---|---|---|
| 1 | `run deposit_gate_101` | 0 | **20 passed, 0 failed** | 10 successful, 5 failed (5 expected) | **PASS.** The two new closing steps validated tesSUCCESS: DepositPreauth **`UnauthorizeCredentials`** (`D2731A54…`, the learner's own `kyc-deposit` credential type), then AccountSet **`ClearFlag` 9** (asfDepositAuth, `B98BCD82…`), with the read-back "Checked: payments to your wallet are accepted again." Afterwards the learner's **Flags are `0x0`** (lsfDepositAuth not set) on validated ledger 21714385. All 10 printed TXIDs are validated tesSUCCESS. |
| 2 | `run amm_liquidity_101` (same home) | 0 | **18 passed, 0 failed** | 6 successful, 0 failed | **PASS.** The issuer's LAB issue Payment **lands** (all 6 printed TXIDs validated tesSUCCESS). **AMM pool created** (`83B45C01…`): 25/25, then 30/30 after the deposit, then the withdraw. |
| 3 | `reset --module deposit_gate_101 --confirm`, then `run deposit_gate_101` again | 0 / 0 | **20 passed, 0 failed** | 10 successful, 5 failed (5 expected) | **PASS.** The reset gave exit 0 ("Cleared 15 tx record(s); report removed: True"). On the re-run, **no unexpected `tecDUPLICATE`**: the only tecDUPLICATE is the lesson's own expected one (re-authorizing the same address). Its closing pair validated again: `UnauthorizeCredentials` `742BE3C2…`, `ClearFlag` 9 `8ED67661…`. Flags `0x0` afterwards (ledger 21714485). All 10 printed TXIDs are validated tesSUCCESS. |
| 4 | `proof verify --live` (`4-verify_live.*`) | **0** | n/a | n/a | **PASS.** "On-ledger verdict: PASS — 20 verified, 1 skipped". The skip is the `temCANNOT_PREAUTH_SELF` (`454EF7FC…`): "never reaches a ledger (by design)". The pack covers amm_liquidity_101 and the re-run deposit_gate_101; the reset cleared the first run's records. `module_accounts`: amm_liquidity 2, deposit_gate 4. |

Checked across the run:
- stderr is empty in all three lesson runs.
- No transaction recorded in `tx_index` is a non-`tesSUCCESS` result other than the lessons' expected rejections.

## Files

- `1-deposit_gate_101/`, `2-amm_liquidity_101/` and `3-deposit_gate_101-rerun/` each hold `command.txt` (exit code),
  `stdout.txt`, `stderr.txt` and `module_report.md`.
- `3-reset.txt`, `flags.txt` and `preflight.txt`.
- `proof_pack.json`, `4-proof_pack.log`, and `4-verify_live.json` / `.txt` / `4-verify_exit.txt`.
- `state_excerpt.json`.
