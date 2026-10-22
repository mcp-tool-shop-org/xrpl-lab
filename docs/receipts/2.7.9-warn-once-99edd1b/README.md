# 2.7.9 state-version warning check on `99edd1b`

This is the check the Editor asked for on **`99edd1b`** (PR #46, `fix/2.7.9-warn-once`). 2.7.9 fixes #45, which the
2.7.8 parity check found: a command that loads state several times printed "Warning: state from v<old>, current is
v<new>…" once per load, so three times for `feedback` and `support-bundle`. 2.7.9 prints it once per state file and
version in a process.

- **The two commits:** `f367d08` (reports `xrpl-lab, version 2.7.8`) and `99edd1b` (reports
  `xrpl-lab, version 2.7.9`). Each ran in the test checkout's editable install, reinstalled after the switch
  (`*/code.txt`).
- **Three homes, the same for both commits.** Before *every* command, the home was restored to one fixed path, so no
  path can differ between commits (`build-saved278/README.txt` says how each home was made):
  - `saved278`: a home **saved by 2.7.8**. It is the 2.7.7 `leftfailed` snapshot from `../2.7.7-live-check-c99bab1/`,
    after one `run receipt_literacy --dry-run` on 2.7.8, so its `state.json` reads `2.7.8`.
  - `leftfailed277`: the 2.7.7 `leftfailed` snapshot as it is (`state.json` reads `2.7.7`).
  - `stamp276`: a copy of the same snapshot with only `state.json`'s version set to `2.7.6`.
- **Network:** read-only. The doctor checks inside the bundle ask the RPC and faucet hosts. The item 2 module run is a
  dry run, so nothing is submitted and no faucet grant is requested.
- **Redaction:** no seeds or wallet files are here. Paths read `<scratch>`.

## Verdict

**PASS.** On 2.7.9, every command prints the warning exactly once on stderr, on all three homes. Once a command saves
state, the next `status` prints none. Apart from the warning, stdout is the same as on 2.7.8 after normalizing the
version and timestamps.

## Item 1: one warning per command (`*/<home>/*.exit` holds each count)

Warnings on stderr per call (none on stdout, in any call):

| Command | `saved278` 2.7.8 → 2.7.9 | `leftfailed277` 2.7.8 → 2.7.9 | `stamp276` 2.7.8 → 2.7.9 |
|---|---|---|---|
| `feedback` | 0 → **1** | 3 → **1** | 3 → **1** |
| `support-bundle` | 0 → **1** | 3 → **1** | 3 → **1** |
| `support-bundle --json` | 0 → **1** | 3 → **1** | 3 → **1** |
| `status` | 0 → **1** | 1 → **1** | 1 → **1** |

- **The text on 2.7.9:** `Warning: state from v2.7.8, current is v2.7.9. Some fields may differ.` on `saved278`, and
  the same with `v2.7.7` and `v2.7.6` on the other two homes. `feedback` also prints its deprecation line, as before.
- **Why `saved278` shows 0 on 2.7.8:** that home was saved by 2.7.8, so on 2.7.8 the versions match and nothing
  prints.
- **Exit codes:** 0 for every call on both commits.
- **stdout (`parity_report.txt`):** `feedback`, `support-bundle` and `support-bundle --json` are the same on both
  commits for all three homes after normalizing the version, ISO timestamps, the live ledger index and the faucet's HTTP
  status. `status` is byte-identical. Among the item 1 files, the only ones that differ are the `.err` and `.exit`
  files, which hold the warnings and their counts.

## Item 2: no warning after a save

On each home: restore, `run receipt_literacy --dry-run --force`, then `status`, then `feedback`, with no restore
between them.

| Step | `saved278` 2.7.8 → 2.7.9 | `leftfailed277` 2.7.8 → 2.7.9 | `stamp276` 2.7.8 → 2.7.9 |
|---|---|---|---|
| `run … --dry-run --force`: warnings | 0 → **1** | 2 → **1** | 2 → **1** |
| `state.json` version after the run | 2.7.8 → **2.7.9** | 2.7.8 → **2.7.9** | 2.7.8 → **2.7.9** |
| `status` next: warnings | 0 → **0** | 0 → **0** | 0 → **0** |
| `feedback` next: warnings | 0 → **0** | 0 → **0** | 0 → **0** |

The dry-run `run` output differs between commits only in values made fresh on every run: the practice destination
address and the simulated hashes. It is the same once those, the version and the timestamps are normalized.

## Item 3: a different old version still warns once

`leftfailed277` (stamped 2.7.7) and `stamp276` (stamped 2.7.6) are the control. On 2.7.9, each warns once per
command with its own version (`state from v2.7.7`, `state from v2.7.6`), as the tables above show.

## Off the brief

**On 2.7.8, `run` printed the warning twice** on the two homes from older versions. That is the same #45 cause on
another path (two loads), and 2.7.9 prints it once there as well.

## Files

- `2.7.8-f367d08/` and `2.7.9-99edd1b/`, each holding:
  - `code.txt`;
  - `saved278/`, `leftfailed277/` and `stamp276/`, with `snapshot.txt` (the home's version), then `feedback`,
    `supportbundle`, `supportbundle_json`, `status` and the three `item2_*` steps as `.out`, `.err` and `.exit` each.
    The `.exit` file also holds the warning counts and `state.json`'s version after the call.
- `build-saved278/`: how the `saved278` home was made on 2.7.8.
- `parity_report.txt`: the normalized comparison of every file.
- `harness/warn_once.sh` (the capture) and `harness/parity_diff.py.txt` (the comparison, now normalizing 2.7.9 too). The
  `.txt` keeps the script out of the repo's lint.
