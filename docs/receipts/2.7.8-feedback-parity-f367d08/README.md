# 2.7.8 feedback parity check on `f367d08`

This is the check the Editor asked for on **`f367d08`** (PR #43, `chore/2.7.8-drop-generate-feedback`). That commit is
Argon's round-1 pass on `0e60a39`, plus tests only. 2.7.8 removes `feedback.py`'s unused `generate_feedback()` (#42),
which the 2.7.7 live check found had no CLI caller.

- **The two commits:** the tag `v2.7.7` (`3f6f3d6`, reports `xrpl-lab, version 2.7.7`) and `f367d08` (reports
  `xrpl-lab, version 2.7.8`). Each ran in the test checkout's editable install, reinstalled after the switch
  (`*/code.txt`).
- **The same home state for both:** two homes from the 2.7.7 live check (`../2.7.7-live-check-c99bab1/`). Before
  *every* command, the snapshot was restored to one fixed path, so no path can differ between commits.
  - `leftfailed`: clawback_101 recorded `verified: false`, with 4 current `failed` records.
  - `recovered`: the same failing run 1, then a passing `run --force`, so the failures are superseded.
- **Network:** read-only. The doctor checks inside the bundle ask the RPC and faucet hosts; nothing is submitted, and
  no faucet grant is requested.
- **Side effects:** the only file any command changed was the home's `doctor.log`, which the doctor checks append to.
  It changed the same way on both commits.
- **Redaction:** no seeds or wallet files are here (the `wallet*.txt` files are `wallet --help` output). Paths read
  `<scratch>`.

## Verdict

**PASS.** On both snapshots, `feedback`, `support-bundle` and `support-bundle --json` print the same on 2.7.8 as on
2.7.7, apart from the version and the timestamps. Every help page is unchanged, and `xrpl_lab.feedback` is gone.

## Item 1: the outputs, compared (`parity_report.txt`)

`harness/parity_diff.py.txt` compares every captured file. It normalizes only the version (`2.7.7` / `2.7.8`), ISO
timestamps, the live ledger index and the faucet's HTTP status (404 or 429), and counts each substitution per file.
Anything else that differs is listed as a real difference.

| Output | `leftfailed` | `recovered` |
|---|---|---|
| `feedback` stdout | same after normalizing: 2 versions, 2 timestamps, 1 ledger index, 1 faucet status | same, same counts |
| `support-bundle` stdout (markdown) | same after normalizing (2, 2, 1, 1) | same (2, 2, 1, 1) |
| `support-bundle --json` stdout | same after normalizing: 3 versions, 7 timestamps, 1 ledger index, 1 faucet status | same: 3, 12, 1, 1 |
| exit codes | 0 on both commits, all six calls | 0 on both |
| `feedback` stderr | `` `feedback` is deprecated, use `support-bundle`. `` on both commits | the same |

**One stderr difference, and why it is not the change.** On 2.7.8, every call also prints "Warning: state from
v2.7.7, current is v2.7.8. Some fields may differ." three times. The snapshots' `state.json` was written by 2.7.7, so
on 2.7.7 the versions match and nothing prints.

- **The control:** `*/control-state-276/` runs the `leftfailed` snapshot with a copy of its state stamped `2.7.6`.
  Both commits then print the same three warnings (only the "current is" version differs) and the same deprecation
  line.
- **The code:** `xrpl_lab/state.py`, which prints the warning, is identical between the two commits.

## Item 2: the module is gone, the help is not changed

| Check | 2.7.7 | 2.7.8 `f367d08` |
|---|---|---|
| `python -c "import xrpl_lab.feedback"` | exit 0 | **exit 1**, `ModuleNotFoundError: No module named 'xrpl_lab.feedback'` |
| `xrpl-lab --help` | captured | **byte-identical** |
| every other `--help`: 27 commands, the hidden `feedback`, and 5 subcommands of `proof`, `wallet`, `curriculum` and `module` (34 pages with the top level) | captured | **all byte-identical** |

## Off the brief (minor, not from 2.7.8)

**The state-version warning prints three times per command,** on both commits. It looks like each of three
`load_state()` calls along the bundle path warns again.

## Files

- `2.7.7-tag/` and `2.7.8-f367d08/`, each holding:
  - `code.txt`;
  - `leftfailed/` and `recovered/`, with `feedback`, `supportbundle` and `supportbundle_json` as
    `.out`, `.err` and `.exit` each;
  - `control-state-276/`;
  - `help/`, one file per help page;
  - `import_feedback.txt`.
- `parity_report.txt`: the normalized comparison of every file.
- `harness/feedback_parity.sh` (the capture) and `harness/parity_diff.py.txt` (the comparison). The `.txt` keeps the
  script out of the repo's lint.
