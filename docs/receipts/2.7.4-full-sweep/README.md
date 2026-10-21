# 2.7.4 full live sweep: all 32 lessons, one home

This is the live acceptance run for 2.7.4 (PR #29, `feat/2.7.4`) on **`7e71c67`**, the commit Argon passed in round 1.
2.7.4 fixes #28, the five findings of the 2.7.3 full sweep.

It ran with the harness's `course_sweep.py` (items 1–7): an offline pre-pass, all 32 lessons in curriculum order in
**one** fresh home with a per-lesson drift log, tx classification, per-lesson live verify, automatic Part B on any
failure, then the full-pack `proof verify --live`. `6df7b7e` (Argon round 1's three findings) landed after this run
and is not covered.

No seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>` and `<worktree>`.
`A/state_excerpt.json` holds `module_accounts`, completed modules with `verified`, and `tx_index`, with `wallet_path`
omitted. `A/drift.jsonl` holds addresses, flags and balances only.

## Verdict

- **Full-pack `proof verify --live`: exit 0, 127 PASS, 11 SKIPPED** (the expected tem/tef records and the offline
  lesson). No FAIL.
- **Lessons: 30 of 32 exit 0.** The 2 that exit 3:
  - clawback_101, a CLI defect on the faucet-retry path (finding 1);
  - account_hygiene, its own new defect (finding 2).
- **The interference is gone.** The drift log shows **no flag left on after any lesson**, and the learner ends with
  Flags `[]`.
  - custodial_crediting_101 shows **`+asfRequireDest, -asfRequireDest`** in-lesson.
  - deposit_gate_101 shows **`+asfDepositAuth, -asfDepositAuth`**.
  - The five lessons that 2.7.3's RequireDest broke (deposit_gate, dex_market_making, dex_inventory_guardrails,
    amm_liquidity, game_economy_capstone) all exit 0.
- **checks_101 tops up once.** "Balance: 49.999670 XRP … needs at least 60 … Topped up! Balance: 149.999670 XRP". Its
  spendable after the lesson is **96.8 XRP** (drift log). No lesson fell below the 40 XRP floor.
- **mpt_distribution_101 passes** (8/0, 3 successful): the issuer signs the issuance.
- **clawback_101's lesson logic passes:** "Steps: 12 passed, 0 failed" with a fresh issuer. Its Part B (alone) gives
  exit 0, 12/0, verify 0.
- **Pre-pass:** 32/32 offline exit 0.

`summary.md` / `summary.json` hold the generated one-row-per-lesson table; `sweep.log` holds the run log.

## Findings

1. **`run --force` that passes still exits 3** (CLI defect, pre-existing since 2.7.0's `--force` fix).
   - clawback_101's first attempt hit a faucet 429 (`RUNTIME_FAUCET_RATE_LIMITED`) and completed with 1 failed step,
     recorded `verified: false`. The harness retried once with `run --force` after 150 s.
   - The retry passed: the module report reads "Steps: 12 passed, 0 failed", and the panel is the plain "Complete".
     **But the process exited 3**, and `state.json` still holds `verified: false` for clawback_101.
   - Cause: `LabState.complete_module` returns early when the module is already completed (`state.py:303`). A
     `--force` re-run therefore never updates the record's `verified`, `txids` or `completed_at`, and
     `_exit_if_unverified` reads the stale record.
   - This is the first exercise of the harness's 429-retry branch.
2. **account_hygiene's trust-line removal leaves the line on the ledger** (own defect, newly visible: 2.7.4 fixed the
   currency code, so its transactions now land).
   - It runs TrustSet HYG limit 100 (`C7E3AE4B…`), OfferCreate, OfferCancel, then TrustSet limit 0 (`79DAD508…`). All
     4 are tesSUCCESS.
   - But the HYG line remains with balance 0 and limit 0 on both sides. The learner's side has **NoRipple off**, while
     its default (an account without DefaultRipple) is on, so the line is not in its default state and is not deleted.
   - Steps 12, 14 and 15 then fail ("Trust line for HYG still present", owner count −1 instead of −2).
   - It fails the same way alone (Part B: exit 3, 12/3, verify 0).
   - Likely fix: the removal TrustSet also sets `tfSetNoRipple`, the standard remove-a-trust-line recipe.
3. **Harness note: dex_vs_amm_risk_literacy is not a defect.** The harness's per-lesson classification flagged its
   offline (dry-run) hashes as `not_validated` and triggered a Part B (exit 0, 25/0, verify 0). Offline records are
   now classified `offline_dry_run` (harness fix after this run). The full-pack verify SKIPs them correctly.

## Hashes to check on testnet

| What | Hash | Expected |
|---|---|---|
| custodial_crediting's in-lesson flag pair | see `A/19-custodial_crediting_101/classify.json` (AccountSet SetFlag asfRequireDest, then ClearFlag asfRequireDest) | both tesSUCCESS by the learner |
| account_hygiene's removal TrustSet (finding 2) | `79DAD508…` (Part B; full hash in `B/account_hygiene/proof_pack.json`) | TrustSet HYG limit 0, tesSUCCESS, with the line still present |

## Files

- `prepass/<lesson>/command.txt`: the offline pre-pass exit codes.
- `A/<NN>-<lesson>/` holds:
  - `command.txt` (exit code, wall time, "Module interrupted" count);
  - `stdout.txt` / `stderr.txt` (plus `*.attempt1.txt` where a 429 was retried);
  - `module_report.md`;
  - `classify.json`, the lesson's txs classified on the ledger;
  - `verify_live.json`, the per-lesson live verify.
- `A/` also holds `drift.jsonl`, `preflight.txt`, `proof_pack.json` and `verify_live.json` (the full-pack verify),
  and `state_excerpt.json`.
- `B/<lesson>/` holds Part B: `command.txt`, `stdout.txt` / `stderr.txt`, `module_report.md`, `proof_pack.json`,
  `verify_live.json` and `result.json`.
