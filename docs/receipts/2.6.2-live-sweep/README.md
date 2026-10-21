# 2.6.2 live sweep receipts

This is the live acceptance run for 2.6.2, on `8ae1c4e` (PR #22), the commit Argon passed (GO). Thirteen modules
ran once each, live on XRPL Testnet. dex_vs_amm_risk_literacy ran offline, as its frontmatter says.

The run checks the 2.6.2 change from #20 item 8: every judged expected-failure handler records its rejection in
`tx_index` with `expected: true`, and the report and proof pack count it.

**Verdict: PASS.**
- All 14 modules exit 0.
- Every Steps line reads "0 failed".
- Every "Transactions … failed (M expected)" line has M equal to the failed count.
- In every proof pack, `expected_failures` equals M, and each expected failure carries `expected: true` in both
  `transactions` and `receipt_table`.

No seeds and no wallet files are in this directory. Testnet addresses and transaction hashes are public on-ledger.
Local paths are shown as `<scratch>`.

## Setup

- One clean worktree pinned at `8ae1c4e`. Later branch commits (`78e021b`, the support bundle and doctor marking
  expected rejections) are not covered.
- A fresh `XRPL_LAB_HOME` per module, outside every repo.
- Before each module: the RPC/faucet env unset, `classify_network` = testnet, network guard PASS.
- Command: `yes "" | xrpl-lab run <module>`, with the exit code from `PIPESTATUS[1]`.
  - dex_vs_amm_risk_literacy ran with `--dry-run`. `xrpl-lab run` does not read a module's frontmatter `mode`, so
    the flag is required.
- After each run: `xrpl-lab proof-pack` (`proof_pack.json`), then a read-only ledger capture
  (`ledger_evidence.json`).
- Faucet calls spaced 60 s between modules.

**Time:** 2026-10-21 02:55–03:25 UTC. xrpl-lab 2.6.2.

## Results

| Module | Exit | Steps | Transactions | `expected_failures` | Expected failure on the ledger |
|---|---|---|---|---|---|
| dex_vs_amm_risk_literacy (offline) | 0 | 25 passed, 0 failed | 7 successful, 0 failed | 0 | none. Network `dry-run`: its 9 dry-run hashes are not on testnet. Pool 25/25 → 35/35 after the deposit → "All LP tokens returned". |
| failure_literacy | 0 | 5 passed, 0 failed | 1 successful, 1 failed (1 expected) | 1 | Payment tecUNFUNDED_PAYMENT `27FC4790…`, validated |
| token_escrow_101 | 0 | 15 passed, 0 failed | 5 successful, 1 failed (1 expected) | 1 | EscrowCreate tecNO_PERMISSION `4BFFC01E…`, validated |
| deposit_gate_101 | 0 | 18 passed, 0 failed | 8 successful, 5 failed (5 expected) | 5 | Payment tecNO_PERMISSION `9A20E050…` and `30986BB5…`; DepositPreauth tecDUPLICATE `C1A1C5EE…` and tecNO_ENTRY `6ACEDE57…`, all validated. Also `temCANNOT_PREAUTH_SELF` `2EFBD2D4…`, never on a ledger (`txnNotFound`), as a `tem` should be. |
| custodial_crediting_101 | 0 | 8 passed, 0 failed | 2 successful, 1 failed (1 expected) | 1 | Payment tecDST_TAG_NEEDED `BB1D3182…`, validated |
| checks_101 | 0 | 13 passed, 0 failed | 4 successful, 1 failed (1 expected) | 1 | CheckCash tecNO_PERMISSION `047EE14E…`, validated |
| nft_marketplace_101 | 0 | 13 passed, 0 failed | 5 successful, 1 failed (1 expected) | 1 | NFTokenAcceptOffer tecOBJECT_NOT_FOUND `4F6DBC6E…`, validated |
| dnft_evolving_item_101 | 0 | 7 passed, 0 failed | 2 successful, 1 failed (1 expected) | 1 | NFTokenModify tecNO_PERMISSION `E1F8BD07…`, validated |
| multisig_treasury_101 | 0 | 10 passed, 0 failed | 3 successful, 1 failed (1 expected) | 1 | `tefBAD_QUORUM`, never on a ledger, as a `tef` should be. Recorded with txid `"failed"` (see the observation below). |
| clawback_101 | 0 | 12 passed, 0 failed | 4 successful, 1 failed (1 expected) | 1 | Clawback tecNO_PERMISSION `49CF57B4…`, validated |
| credentials_101 | 0 | 10 passed, 0 failed | 3 successful, 3 failed (3 expected) | 3 | CredentialCreate tecNO_TARGET `71CA9F23…` and tecDUPLICATE `BD045E77…`; CredentialAccept tecNO_ENTRY `4C7CB870…`, all validated |
| permissioned_domains_101 | 0 | 15 passed, 0 failed | 6 successful, 2 failed (2 expected) | 2 | OfferCreate tecNO_PERMISSION `79A0B686…`; PermissionedDomainSet tecNO_PERMISSION `CA77FF1D…`, both validated |
| trust_line_failures | 0 | 8 passed, 0 failed | 2 successful, 1 failed (1 expected) | 1 | Payment tecPATH_DRY `8CE6B891…`, validated |
| escrow_101 | 0 | 4 passed, 0 failed | 1 successful, 0 failed | 0 | none. Prints "Escrow found: 10 XRP (10000000 drops)". |

Checked across all 14 modules:
- stderr is empty.
- Every recorded hash that is not an expected failure is `tesSUCCESS` and validated (the live modules).
- No helper funding printed "unknown"; there was no `tefPAST_SEQ` and no "never validated".

## Observation (low; not an acceptance blocker)

The `expected: true` record does not say whether the expected failure **validated on a ledger** (the twelve `tec`s)
or **never reached one** (deposit_gate's `tem`, multisig's `tef`). Two consequences:
- deposit_gate's `tem` record carries a hash and an explorer URL for a transaction that does not exist on any
  ledger.
- multisig_treasury's `tef` record has txid `"failed"` and the explorer URL `…/transactions/failed`, a dead link.

The signed blob's hash was not recorded there, unlike the `tem` case.

## Files

`sweep-8ae1c4e-20261021T0255Z/<module>/` holds:
- `command.txt`, with the exit code;
- `preflight.txt`;
- `stdout.txt`, with the scratch path redacted;
- `stderr.txt`;
- `module_report.md`;
- `proof_pack.json`;
- `ledger_evidence.json`.
