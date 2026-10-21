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
