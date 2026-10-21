# 2.6.1 release acceptance sweep

This is the release acceptance test for 2.6.1. Fourteen modules were run once each, live on XRPL Testnet, against
the exact release head `ff7314f` (`feat/2.6.1`, version 2.6.1), which Argon passed in round 2 (no findings).

**Verdict: PASS. All 14 modules exit 0, every Steps line is honest, and every non-`tesSUCCESS` transaction is a
validated `tec` that its lesson expects.**

No seeds and no wallet files are in this directory. Testnet addresses and transaction hashes are public on-ledger.
Local paths are shown as `<scratch>`.

## Setup

- One clean worktree at `ff7314f`.
- A fresh `XRPL_LAB_HOME` per module, in a scratch folder outside every repo.
- Before each module: `XRPL_LAB_RPC_URL` and `XRPL_LAB_FAUCET_URL` unset, `classify_network` = testnet, network guard
  PASS (`preflight.txt`).
- Command: `yes "" | xrpl-lab run <module>`, with the exit code read from `PIPESTATUS[1]`.
- Faucet calls spaced 60 s between modules.
- After each run, `ledger_evidence.json` records:
  - `account_info` and `account_tx` for every address printed, and for every `Destination` of a recorded
    transaction (this covers the per-run practice recipient);
  - a `tx` lookup of every hash recorded or printed. A `txnNotFound` on a 64-hex value that stdout labels as a
    channel, check, domain or NFToken ID is an object ID, not a transaction.

**Time:** 2026-10-21 01:15–01:44 UTC. xrpl-lab 2.6.1, xrpl-py 4.5.0, Python 3.13.13.

## Results

| Module | Exit | Report "Steps" | Report "Transactions" | Validated non-`tes` on the ledger (all expected by the lesson) |
|---|---|---|---|---|
| receipt_literacy | 0 | 4 passed, 0 failed | 1 successful, 0 failed | none |
| failure_literacy | 0 | 5 passed, 0 failed | 1 successful, 0 failed | Payment **tecUNFUNDED_PAYMENT** `10ABC0CB…` |
| receipt_audit | 0 | 5 passed, 0 failed | 2 successful, 0 failed | none |
| amm_liquidity_101 (#30) | 0 | 18 passed, 0 failed | 6 successful, 0 failed | none: AMMCreate, AMMDeposit and AMMWithdraw all `tesSUCCESS` |
| payment_channel_101 | 0 | 13 passed, 0 failed | 3 successful, 0 failed | none |
| token_escrow_101 | 0 | 15 passed, 0 failed | 5 successful, 0 failed | EscrowCreate tecNO_PERMISSION `1B0A38A8…` |
| credentials_101 | 0 | 10 passed, 0 failed | 3 successful, 3 failed (3 expected) | CredentialCreate tecNO_TARGET `86804D66…`, tecDUPLICATE `4FDC7995…`; CredentialAccept tecNO_ENTRY `693D0419…` |
| deposit_gate_101 | 0 | 18 passed, 0 failed | 8 successful, 0 failed | DepositPreauth tecDUPLICATE `E812A132…`, tecNO_ENTRY `65622152…`; Payment tecNO_PERMISSION `BF21B199…`, `B1B8ADC0…` (plus `temCANNOT_PREAUTH_SELF`, which is never on a ledger) |
| permissioned_domains_101 | 0 | 15 passed, 0 failed | 6 successful, 2 failed (2 expected) | OfferCreate tecNO_PERMISSION `6B4B6431…`; PermissionedDomainSet tecNO_PERMISSION `1AC9182D…` |
| custodial_crediting_101 | 0 | 8 passed, 0 failed | 2 successful, 0 failed | Payment tecDST_TAG_NEEDED `A7CC6E24…` |
| clawback_101 | 0 | 12 passed, 0 failed | 4 successful, 1 failed (1 expected) | Clawback tecNO_PERMISSION `77F0C8FC…` |
| checks_101 | 0 | 13 passed, 0 failed | 4 successful, 0 failed | CheckCash tecNO_PERMISSION `FCA027F3…` |
| nft_marketplace_101 | 0 | 13 passed, 0 failed | 5 successful, 0 failed | NFTokenAcceptOffer tecOBJECT_NOT_FOUND `5A0787DC…` |
| game_economy_capstone | 0 | 16 passed, 0 failed | 6 successful, 0 failed | none |

Checked across all 14 modules:
- Every module is `verified: true` in `state.json`.
- stderr is empty in every module.
- No helper funding printed "unknown"; there was no `tefPAST_SEQ` and no "never validated".
- No hash that xrpl-lab recorded is missing from the ledger.

### The first lessons' practice recipient

The practice payments now go to a fresh per-run address, and the first payment creates that account. Each address
exists on the validated ledger after its run:

| Module | Practice address | Payments | `account_info` after the run |
|---|---|---|---|
| receipt_literacy | `rM7dp23jPq3nwcv9CF5vsTMfTtZWRjTuK9` | `E32C8106…` tesSUCCESS | Balance 10,000,000 drops, Sequence 21696986 |
| failure_literacy | `rsHWecqbkBkbG2jn2eDGqzYe8VcSf8Dprn` | `772E824C…` tesSUCCESS | Balance 10,000,000 drops, Sequence 21697013 |
| receipt_audit | `rDi4wJQdacXd8TWKDUnUurS27R5dVrafzq` | `EA9B0130…`, `F1B57C5B…` tesSUCCESS | Balance 2,000,000 drops, Sequence 21697037 |

failure_literacy's deliberate failure validated **tecUNFUNDED_PAYMENT** (`10ABC0CB…`), not a self-payment.

### Observation (low; not an acceptance blocker)

The "N failed (M expected)" form of the Transactions line appears only where the expected `tec` is recorded in
`tx_index`: credentials_101, permissioned_domains_101 and clawback_101.

In six modules the expected `tec` validated on the ledger but is not in `tx_index`, so the report's Transactions
line and the proof pack leave it out:
- failure_literacy;
- token_escrow_101;
- deposit_gate_101 (4);
- custodial_crediting_101;
- checks_101;
- nft_marketplace_101.

The Steps lines in those modules are still honest.

## Files

`release-sweep-ff7314f-20261021T0115Z/<module>/` holds:
- `command.txt`, with the exit code;
- `preflight.txt`;
- `stdout.txt`, with the scratch path redacted;
- `stderr.txt`;
- `module_report.md`;
- `ledger_evidence.json`.
