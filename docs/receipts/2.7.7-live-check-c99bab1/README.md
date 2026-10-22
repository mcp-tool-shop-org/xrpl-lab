# 2.7.7 live check on `c99bab1`

This is the live check the Editor asked for on **`c99bab1`** (PR #40, `feat/2.7.7`), the commit Argon passed. 2.7.7
fixes #39: after a `run --force` recovery, doctor's "Last error" still reported the failed first run, with the hint
`verify --tx failed`.

- **Install:** the test checkout's editable install was reinstalled on `c99bab1`, so it reports `xrpl-lab, version
  2.7.7`. The state files and packs record `v2.7.7`.
- **Redaction:** no seeds and no wallet files are in this directory. Local paths are shown as `<scratch>` and
  `<home>`. The packs still verify after redaction (`verify-artifact`, `valid: true`).
- **Faucet use:** one grant, for the recovered case's `run --force`. Both first runs fail by design and draw nothing.

## How it ran

Each case ran in its own fresh home, with the faucet-URL method for run 1 (`XRPL_LAB_FAUCET_URL` set to a missing
path on the testnet faucet host). A gate required exit 3 and a `verified: false` record before going on.

- `recovered/`: clawback_101 run 1 fails (exit 3, 4 `failed` placeholders). Then `run --force` with the normal
  faucet passes (exit 0, `verified: true`, 4 txids).
- `left-failed/`: the same failing run 1, with no rerun.

Then, from each home, with the faucet override unset:

- `xrpl-lab doctor`;
- `support-bundle --json`, and `support-bundle` (markdown);
- `feedback`, the deprecated markdown alias;
- `proof-pack` and `verify-artifact proof_pack.json --live --json`;
- `current_failures.txt`, which is `LabState.current_failures()` read from the home's state.

## Verdict

| # | Check | Result |
|---|---|---|
| 1 | Recovered: `doctor` Last error | **PASS.** `✓ Last error — No failed transactions` |
| 1 | Recovered: `support-bundle --json` | **PASS.** `doctor_checks` "Last error": `No failed transactions`, no hint |
| 1 | Recovered: markdown | **PASS.** No `### Last Error` in `support-bundle` or `feedback`; the Doctor list has `[PASS] Last error: No failed transactions` |
| 1 | Recovered: `current_failures()` | 0 of 4 `failed` records; the module's latest run passed after them |
| 2 | Left failed: `doctor` Last error | **PASS.** `! Last error — Last failure in 'clawback_101': a step failed before its transaction reached the network`, hint `Run: xrpl-lab run clawback_101 --force to retry the module` |
| 2 | Left failed: `support-bundle --json` | **PASS.** The same detail and hint, `severity: warn` |
| 2 | Left failed: `verify --tx failed` anywhere | **PASS.** In no file of either case |
| 2 | Left failed: `current_failures()` | 4 of 4 `failed` records |
| 3 | A current failure with a hash | **SKIPPED**, as the brief allows. See below. |

- **Live verify, unchanged from 2.7.6:**
  - recovered: exit 0, with 5 PASS and 1 SKIPPED (the `failed` claim, "An earlier run's step that never reached a
    ledger; this module's latest run passed");
  - left failed: exit 1, 1 FAIL ("A step failed before its transaction reached the network…").
- **`doctor` exits 0 in both cases** and prints "9/9 checks passed — all good". The Last error check is
  informational (`passed: true`, `severity: warn`), so the left-failed case shows `!` beside a green summary, as
  designed.

### Why item 3 was skipped

`xrpl-lab send` does not write to `tx_index`, so a failed payment never becomes a "Last error". The only way to
get a current failure with a hash is a lesson step that lands an unexpected `tec`, which needs new setup. The unit
tests cover it (`tests/test_v277_last_error.py`).

## Off the brief

1. **The markdown "### Last Error" block is not reachable from the CLI** (minor; 2.7.7 is not wrong).
   - 2.7.7 changes `feedback.py` `generate_feedback()` to use `current_failures()`. Only tests call that
     function.
   - `xrpl-lab feedback` (deprecated) and `xrpl-lab support-bundle` both render `workshop.py`'s
     `SupportBundle.to_markdown()`. That has no `### Last Error` section in either case, including the left-failed
     one. The failure shows only in its Doctor list, as the Last error line.
   - So item 1's "no `### Last Error`" holds, but it would hold without the fix too. Live, the change shows in
     `doctor` and the support bundle; in `generate_feedback()` only the unit tests see it.
   - The Editor may want to remove `generate_feedback()` or point the alias at it. That call is not mine.
2. **The markdown labels a warn check `[PASS]`.** For example, `[PASS] Last error: Last failure in 'clawback_101':
   a step failed…`. The terminal shows `!`. This is by design (`public_check_icon(passed=True, severity="warn") ==
   "PASS"`, in `tests/test_w7_core_state_support_bundle_warn_icons.py`), and the hint line follows it.
3. **The left-failed support bundle's markdown faucet check got HTTP 429** ("Reachable: … (HTTP 429)"). That is the
   faucet rate-limiting a bare GET of its host, a few seconds after the JSON bundle's check got 404. The check still
   counts it as reachable, which is right.

## Hashes to check on testnet

The recovered case's `run --force`, each looked up with `tx` after the run. All validated.

| Hash | Type | Account | Result |
|---|---|---|---|
| `6F5DED95D14934051A8AE82C0B566B64BFE5D505BEACE018D7FE4E0A1857A27A` | AccountSet | issuer `rwsUATTh…` | tesSUCCESS |
| `70670718B3434D57849A2CAAABE12C1B748F09EF64AD90B9FCEE242F63AD295D` | TrustSet | learner `rndd9v87…` | tesSUCCESS |
| `D507407A9F40FAFAA29F49141781C8E858C8550EA7C4F219B3CDF61652173BFB` | Payment | issuer `rwsUATTh…` | tesSUCCESS |
| `7718FE4D326C45D79221F6CDFFD6723BAE30852EC4DF5FFC639E6FEB761CD626` | Clawback | issuer `rwsUATTh…` | tesSUCCESS |
| `E3066287BAC8D48D60DA7067D5731AAE5AEB0C099D501D08E94078277E815902` | Clawback | `rnaWTtTb…` | tecNO_PERMISSION (the expected rejection) |

## Files

`recovered/` and `left-failed/` each hold:

- `1-failing/` (and `2-force/` for the recovered case): the command, preflight, stdout and stderr;
- `gate.txt`, `records.txt`, `preflight_verify.txt`, `current_failures.txt`;
- `doctor.txt`;
- `support_bundle.json`, `support_bundle.md` and `feedback.md`, with their `.err` files;
- `proof_pack.json`, plus `verify_live.json` and `verify_live.exit`.
