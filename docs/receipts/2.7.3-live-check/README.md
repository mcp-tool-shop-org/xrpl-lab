# 2.7.3 live check: a validated failure keeps its explorer link in state

This is the live acceptance check for 2.7.3 (PR #26, `feat/2.7.3`) on `46aa2f6`, the commit Argon passed (GO). It
fixes #20 item 14: `state.json` stored `explorer_url: ""` for every expected failure, even a validated `tec`, while
the proof pack linked it.

**Verdict: PASS** (run 2). Run 1 was spoiled by a testnet faucet rate limit, not by 2.7.3, and is kept as the record.

No seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>` and `<worktree>`.
`state_excerpt.json` holds `tx_index` (with `explorer_url`) and `module_accounts`, with `wallet_path` omitted.

## Setup

- One clean worktree pinned at `46aa2f6` (xrpl-lab 2.7.3).
- A fresh `XRPL_LAB_HOME` per run, outside every repo.
- Preflight: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Command: `yes "" | xrpl-lab run deposit_gate_101`, with the exit code from `PIPESTATUS[1]`.
- Then `xrpl-lab proof-pack`, and `proof verify --live --json proof_pack.json` run from inside the run folder.

**Time:** 2026-10-21 18:18–18:27 UTC.

## Run 2: `sweep-46aa2f6-20261021T1824Z`, PASS

**Exit 0**; "Steps: 20 passed, 0 failed"; "Transactions: 10 successful, 5 failed (5 expected)"; stderr empty.

| Record | Ledger | `validated` | `explorer_url` in `state.json` | Proof pack |
|---|---|---|---|---|
| Payment tecNO_PERMISSION `4CF3967F…` | validated | `true` | `https://testnet.xrpl.org/transactions/4CF3967F…` (its own hash) | same link |
| DepositPreauth tecDUPLICATE `87451931…` | validated | `true` | `https://testnet.xrpl.org/transactions/87451931…` | same link |
| Payment tecNO_PERMISSION `85CC7212…` | validated | `true` | `https://testnet.xrpl.org/transactions/85CC7212…` | same link |
| DepositPreauth tecNO_ENTRY `A124FAA9…` | validated | `true` | `https://testnet.xrpl.org/transactions/A124FAA9…` | same link |
| temCANNOT_PREAUTH_SELF `0C62895C…` | `txnNotFound` (never on a ledger) | `false` | `""` | `""` |

Each `explorer_url` is exactly `https://testnet.xrpl.org/transactions/` plus the record's full 64-hex hash.

**`proof verify --live`: exit 0.** 14 PASS, 1 SKIPPED (the `tem`). `file` is `proof_pack.json`.

## Run 1: `sweep-46aa2f6-20261021T1818Z`, spoiled by a faucet rate limit

**Exit 3**; 17 passed, 3 failed (steps 10–12); "7 successful, 7 failed (5 expected)". `proof verify --live`: exit 1.

The cause was environmental:
- When step 10 funded the KYC subject helper, the faucet answered **`RUNTIME_FAUCET_RATE_LIMITED` (HTTP 429)**.
- With the subject unfunded, CredentialCreate validated `tecNO_TARGET` (`B5B3AAC5…`).
- CredentialAccept then failed locally with `actNotFound`; its sequence pre-fetch logged a traceback to stderr.
- The module reported the steps as failed, honestly.

The 2.7.3 change already showed in this run's `state.json`:
- the 4 validated expected `tec`s carry their testnet links with `validated: true`;
- the `tem` has `""` with `validated: false`;
- the unexpected but validated `tecNO_TARGET` also carries its link;
- the local `actNotFound` record (txid `"failed"`) has `""`.

Run 2 was started in a fresh home after a 3-minute pause for the faucet.

## Files

`<run>/deposit_gate_101/` holds:
- `command.txt`, with the exit code and the verify exit code;
- `preflight.txt`;
- `stdout.txt` and `stderr.txt`;
- `module_report.md`;
- `proof_pack.json`;
- `verify_live.json`;
- `state_excerpt.json`;
- `ledger_evidence.json`.
