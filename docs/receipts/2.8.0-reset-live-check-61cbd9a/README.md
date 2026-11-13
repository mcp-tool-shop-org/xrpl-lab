# 2.8.0 network-reset check, live on XRPL Testnet, on `61cbd9a`

2.8.0 is the release for the **2026-11-25** Testnet and Devnet wipe. This check ran the release commit against the
real Testnet on 2026-11-13: one fresh lab, real module runs, real proof packs, and then forged packs and a simulated
reset, each verified against the live ledger.

- **Code:** `mcp-tool-shop-org/xrpl-lab` at `61cbd9a`, in the test checkout's editable install, reinstalled after the
  switch. It reports `xrpl-lab, version 2.8.0` (`raw/00_preflight.txt`).
- **Network:** the public Testnet, default endpoint and faucet, no overrides. Network guard PASS. One faucet grant.
- **Lab:** one fresh `XRPL_LAB_HOME` under a scratch folder outside every repo. The wallet file never left it.
- **Redaction:** no seeds or wallet files are here. Paths read `<scratch>`, `<home>` or `<worktree>`.

## Verdict

**PASS.** Every verdict the release adds came out as designed against the real ledger, and none of them was ever
reported as a pass.

## What could not be run live

The **announced** signal depends on the date: it applies from 2026-11-24 10:00 UTC, when the 25th begins anywhere.
It cannot be seen on a live network before then. It is covered by the test suite, which pins the clock
(`tests/test_network_reset.py`, `tests/test_reset_signal.py`). The Testnet has also not actually been reset, so parts
C and D **simulate** one by raising the lab's own recorded ledger index far above the real one. That is exactly what
a reset looks like from the lab's side: the ledger it reads is far below the one it saw before.

## A. A real run, and what the lab recorded

| Step | File | Result |
|---|---|---|
| `run receipt_literacy` | `raw/01_run_receipt_literacy.*` | exit 0 |
| The lab's state afterwards | `raw/02_state_ledger_marks.json` | `ledger_marks.testnet.validated_ledger_index` = **22292456**; no epochs |
| `doctor` | `raw/03_doctor.out` | Network reset: "No reset since your last run" |
| `proof-pack` | `raw/06_pack_real_meta.json` | the pack carries `ledger_marks` inside its hash |
| `verify-artifact --live` | `raw/07_verify_real_live*.out` | **exit 0**, 1 PASS, `reset_signal` "" |

The recorded index matches the network: the endpoint reported ledger 22292457 a few seconds later (`raw/03_doctor.out`).

## B. Forged packs against the real ledger

Each is the real pack with one thing changed and the hash recomputed, so its integrity check passes. The fake
transaction hash is `F00DFACE…`, which is on no ledger.

| Pack | What was forged | Exit | Statuses | `reset_signal` | Flag |
|---|---|---|---|---|---|
| `08` fake txid | one transaction hash | **1** | FAIL | "" | none |
| `09` fake txid + mark | also `ledger_marks` = 99000000 | **4** | UNCONFIRMED | `pack_claim` | suspicious ledger mark |
| `10` fake txid + reset record | also `ledger_resets_seen` | **4** | UNCONFIRMED | `pack_claim` | none |
| `11` real txids + mark | only `ledger_marks` = 99000000 | **0** | PASS | "" | suspicious ledger mark |

- `08` is the baseline: a made-up hash with nothing else fails, as it always did.
- `09` and `10` are the cases the Publisher ruled on: the pack claims a reset that nothing else confirms. The verdict
  reads "UNCONFIRMED: the pack claims a reset that nothing else confirms" and says "anyone can write those fields"
  (`raw/09_verify_fake_mark.out`). `live_passed` is false.
- `11` shows the flag is a flag, not a verdict: the transactions are really there, so they pass, and the false ledger
  mark is still called out.

## C. A simulated reset, seen from this lab

The lab's own ledger mark was set to 99000000 (`raw/12_state_mark_raised.json`).

| Step | File | Result |
|---|---|---|
| `doctor` | `raw/13_doctor_after_raise.out` | Warns: "Testnet was reset since your last run: its ledger is now 22292464, below the 99000000 seen before" |
| `verify-artifact --live` on the fake-txid pack | `raw/14_verify_fake_txid_own_signal*.out` | **exit 4**, RESET, `reset_signal` **`seen_by_this_lab`** |
| `run receipt_literacy` (already complete) | `raw/15_run_sees_reset.out`, `raw/16_state_after_seen.json` | Stops at "already completed"; state unchanged |
| `run receipt_literacy --force` | `raw/19_rerun_force.*`, `raw/23_pack_after_meta.json` | exit 0; the lab closes the epoch **before** the run's own transaction |
| `doctor`, `recovery` | `raw/21_*`, `raw/20_*` | No reset warning; no blockers |
| New pack, `verify-artifact --live` | `raw/24_verify_after_live*.out` | **exit 0**, 2 PASS |

The same fake-txid pack that failed in part B (`08`, exit 1) reads RESET here (exit 4), because this lab's own
state says the network was reset after that transaction was recorded. That is the independent signal: it comes from
the verifying lab, not from the pack.

The new pack records the reset the lab saw (`ledger_resets_seen`: last index 99000000, seen at 12:03:54Z), and the
re-run's transaction is stamped 12:04:03Z, after it.

## D. Two modules, one re-run

`failure_literacy` was run (`raw/30_*`), the mark was raised again (`raw/31_*`), and only `receipt_literacy` was
re-run with `--force` (`raw/32_*`). The lab then holds two epochs (`raw/33_state_two_epochs.json`).

| Step | File | Result |
|---|---|---|
| `doctor` | `raw/34_doctor_one_module_wiped.out` | Warns: "Testnet was reset (seen on 2026-11-13). 1 completed module lost on-ledger results." |
| `recovery` | `raw/35_recovery_one_module_wiped.out` | `xrpl-lab run failure_literacy --force`; "Affected: failure_literacy." No fund step, since a run has happened since |
| `run failure_literacy --force` | `raw/36_*` | exit 0 |
| `doctor`, `recovery` | `raw/37_*`, `raw/38_*` | No reset warning; "No known blockers found." |
| Final pack, `verify-artifact --live` | `raw/40_verify_final_live_json.out` | **exit 0**, 7 PASS, 0 failed, `reset_signal` "" |

## Two things this run showed about the product

Neither is a defect that blocks the release; both are recorded so they are not a surprise.

1. **A plain `run` of a completed module does not notice a reset.** The CLI stops at "already completed" before the
   runner reads the ledger (`raw/15_run_sees_reset.out`, `raw/16_state_after_seen.json`). `run --force`, or running
   any module not yet completed, does read it. `doctor` notices either way, because it reads the ledger itself.
2. **`recovery` is offline.** For a reset that is neither announced nor yet seen by a run, it reports no blockers
   (`raw/18_recovery_after_seen.out`); `doctor` is the command that catches that case (`raw/17_doctor_after_seen.out`)
   and its hint gives the commands. Once the reset is announced or seen, `recovery` lists the steps (part D).

## Layout

`raw/NN_name.out`, `.err` and `.exit` are each command's stdout, stderr and exit code. `raw/*.json` without those
suffixes are summaries written by the check's helper: state and pack fields only, never a wallet file.
`raw/00_snapshot.txt` has the start and end times.
