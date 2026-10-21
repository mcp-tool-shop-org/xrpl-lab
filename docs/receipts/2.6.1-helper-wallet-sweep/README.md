# 2.6.1 helper-wallet sweep receipts

This is a live sweep, on XRPL Testnet, of the 10 testnet modules that fund a helper wallet through a handler with
the funding race (#20 item 1). Each module runs once, standalone, on the released code.

No seeds and no wallet files are in this directory. Helper-wallet seeds were held only in memory. Testnet
addresses and transaction hashes are public on-ledger. Local paths are shown as `<scratch>`.

## Sweep 2: `sweep-284fcf7-20261020T2351Z` on `fix/2.6.1-sweep` (`284fcf7`)

**Result:** 9 of 10 modules exit 0. The 10th, credentials_101, exits 3 on a defect the sweep-1 fixes uncovered (see
below).

**Code:** `284fcf7` = `feat/2.6.1` @ `15d6907` (including `b6815f7`'s helper-wallet wait) plus the fixes for sweep 1's
classes A–D. `4becc36` (a `verify_nft_offer` message change) landed after this sweep and is not covered.

**Setup:** the same as sweep 1: one clean worktree, a fresh `XRPL_LAB_HOME` per module, preflight checks, the
`PIPESTATUS` exit code and 60 s faucet spacing.

**Time:** 2026-10-20 23:51 to 2026-10-21 00:40 UTC.

| Module | Exit | Report "Steps" | Report "Transactions" | vs sweep 1 |
|---|---|---|---|---|
| payment_channel_101 | 0 | 13 passed, 0 failed | 3 successful, 0 failed | D fixed: both claims verify (3 and 7 XRP); redeem `3724470D…` lands |
| token_escrow_101 | 0 | 15 passed, 0 failed | 5 successful, 0 failed | still clean |
| credentials_101 | **3** | 9 passed, 1 failed | 4 successful, 2 failed | B fixed (steps 6/7 pass on their validated tecs); **new: step 4** |
| deposit_gate_101 | 0 | 18 passed, 0 failed | 8 successful, 0 failed | A fixed (step 5's tecNO_PERMISSION validates); D fixed (step 14 "Payment landed" with CredentialIDs) |
| permissioned_domains_101 | 0 | 15 passed, 0 failed | 6 successful, 2 failed (the two expected tecs) | A fixed (step 11 OfferCreate tecNO_PERMISSION `2C5E839A…` validated); B fixed (step 12 `0BF1DCAB…` validated) |
| custodial_crediting_101 | 0 | 8 passed, 0 failed | 2 successful, 0 failed | A fixed: the tagged deposit lands |
| clawback_101 | 0 | 12 passed, 0 failed | 4 successful, 1 failed (the expected tec) | B fixed (step 12 tecNO_PERMISSION `3574990D…` validated) |
| checks_101 | 0 | 13 passed, 0 failed | 4 successful, 0 failed | A' fixed: the outsider's CheckCash tecNO_PERMISSION `BA9AEE92…` **validated**, with the fee charged (balance 99,999,990) |
| nft_marketplace_101 | 0 | 13 passed, 0 failed | 5 successful, 0 failed | C fixed: buyer accepts `4284962B…` and buy-back `E5F893FA…` land |
| game_economy_capstone | 0 | 16 passed, 0 failed | 6 successful, 0 failed | C fixed |

Checked across all 10 modules:
- Every helper funding printed a real balance ("Balance: 100.000000 XRP"); none printed "unknown".
- There was no `tefPAST_SEQ` and no "never validated".
- stderr is empty in every module.
- Every non-`tesSUCCESS` transaction the modules recorded is a validated `tec` that the lesson expects.
- The `txnNotFound` entries in `ledger_evidence.json` are object IDs printed in stdout (a channel ID, check IDs and
  a domain ID), not transactions.

### New finding: credentials_101 step 4 attests a funded "unfunded" subject

- **What happened:** step 4 ("Try attesting an UNFUNDED subject", which expects `tecNO_TARGET`) submitted
  CredentialCreate against the fixed default `rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe` (`handlers.py:4383`). It
  validated **tesSUCCESS** (`D5243336…`).
- **Why:** that address is a well-known example address, and it is funded on testnet: 33,108 XRP, Sequence
  17027004, queried 2026-10-21.
- **Now judged honestly:** the step prints "Not the lesson's outcome: expected tecNO_TARGET, the transaction
  succeeded" and fails, so the module exits 3.
- **Sweep 1 had the same tesSUCCESS** (`8EB5E33B…`), but counted it as a pass, so it was a false pass hidden by
  class B.
- **Fix:** attest a freshly generated address that is never funded, instead of a fixed one.

## Sweep 1: `sweep-2.6.0-20261020T2312Z` on v2.6.0 (`036c187`)

**Setup:**
- One clean worktree at `036c187`.
- A fresh `XRPL_LAB_HOME` per module, in a scratch folder outside every repo.
- Before each module: `XRPL_LAB_RPC_URL` and `XRPL_LAB_FAUCET_URL` unset, `classify_network` = testnet, network guard
  PASS (`preflight.txt`).
- Command: `yes "" | xrpl-lab run <module>`, with the exit code read from `PIPESTATUS[1]`.
- Faucet calls spaced 60 s between modules.
- After each run, `ledger_evidence.json` records:
  - `account_info` and `account_tx` for every address printed;
  - a `tx` lookup of every hash recorded in `tx_index` or printed. A `txnNotFound` on a 64-hex value starting
    `0008…` is an NFTokenID picked up by the hash scan, not a transaction.

**Time:** 2026-10-20 23:12–00:00 UTC. xrpl-lab 2.6.0, xrpl-py 4.5.0.

| Module | Exit | Report "Steps" | Report "Transactions" | Finding classes |
|---|---|---|---|---|
| payment_channel_101 | 3 | 9 passed, 4 failed | 2 successful, 0 failed | D |
| token_escrow_101 | 0 | 15 passed, 0 failed | 5 successful, 1 failed (the expected tec) | clean |
| credentials_101 | 3 | 8 passed, 2 failed | 4 successful, 0 failed | B |
| deposit_gate_101 | 3 | 17 passed, 1 failed | 7 successful, 5 failed | A (not counted), D |
| permissioned_domains_101 | 3 | 13 passed, 2 failed | 6 successful, 0 failed | A, B |
| custodial_crediting_101 | 3 | 6 passed, 2 failed | 1 successful, 1 failed | A |
| clawback_101 | 3 | 11 passed, 1 failed | 4 successful, 1 failed | B |
| checks_101 | 0 | 13 passed, 0 failed | 4 successful, 1 failed | A (**false pass**) |
| nft_marketplace_101 | 3 | 8 passed, 5 failed | 2 successful, 1 failed | C |
| game_economy_capstone | 3 | 14 passed, 2 failed | 5 successful, 0 failed | C |

### A. Helper-funding race (#20 item 1): confirmed

Every helper funding printed "Balance: unknown XRP". When a helper's **first** transaction came right after its
funding, the transaction failed and never reached a ledger:

| Module, step | Helper | Expected | Got | Ledger |
|---|---|---|---|---|
| deposit_gate_101, step 5 (sender's Payment into the gated treasury) | `r3VGraPp19yWpxWtHhGTCR35brfD9u6Seu` | tecNO_PERMISSION | **tefPAST_SEQ** (the module printed "The demonstration did not exercise the gate"); stderr 2× "resubmitting after post-broadcast failure" | Not on the ledger; no hash recorded. The sender's only tx is the later Payment `1E8C824A…` (tesSUCCESS). **The step was not counted as failed.** |
| permissioned_domains_101, step 11 (outsider's permissioned OfferCreate) | `rfh6nXzjF7965tdsmW2E6yJY12c1jUwgwV` | tecNO_PERMISSION | **tefPAST_SEQ** | Recorded `B94CAC1C…` and `FDC6EA14…` → `txnNotFound` |
| custodial_crediting_101, step 6 (player's tagged deposit) | `raX5qqSbt7gVPVEZv9qXV4FDqPDUrfhEWd` | tesSUCCESS | **tefPAST_SEQ** ("Sequence number already used") | `F14C43D2…` → `txnNotFound`. Step 7 then fails ("No deposit to credit"). |
| checks_101 (outsider cashes the Check) | `rGdpYFCpxasR2ZnsL8JKC5FVa2o4Com74C` | tecNO_PERMISSION | It printed "Expected failure: tecNO_PERMISSION … it's on the ledger, and its fee was charged" | **False.** `321A304E…` and `FE6D7A51…` → `txnNotFound`. The outsider has no transactions and still holds exactly 100,000,000 drops. The step passed and the module exited 0. |

Helpers whose first transaction came later were not hit: the token_escrow recipient, the credentials subject, the
clawback no-flag issuer, and the deposit_gate subject and outsider.

### B. Expected-failure lessons counted as failed steps

Each of these `tec` results **validated exactly as the lesson expects**, yet the step was listed as failed, so the
module exited 3:
- credentials_101, step 6: `tecDUPLICATE` `72D6F4EC…`
- credentials_101, step 7: `tecNO_ENTRY` `EA70162B…`
- permissioned_domains_101, step 12: `tecNO_PERMISSION` `72CC0448…`
- clawback_101, step 12: `tecNO_PERMISSION` `8C27DE51…`

Other expect-fail steps were counted correctly: token_escrow, checks, custodial step 8, nft step 13, and the
deposit_gate `temCANNOT_PREAUTH_SELF`, `tecDUPLICATE` and outsider steps.

### C. Sizing: a 100 XRP sell offer to a buyer funded once with 100 XRP

- **nft_marketplace_101, step 8:** NFTokenAcceptOffer `tecINSUFFICIENT_FUNDS` `144C25BA…` (validated).
  - Steps 9–12 cascade: the resale offer gets `tecNO_ENTRY` `1F2348F0…`, then the buy-back gets
    `tecCANT_ACCEPT_OWN_NFTOKEN_OFFER` `2544DC53…`.
- **game_economy_capstone, step 10:** `tecINSUFFICIENT_FUNDS` `56869DAE…` (validated). Step 11 cascades.

This is the same class as AMM live-fire run 2: one 100 XRP faucet grant cannot cover a 100 XRP leg plus the
reserve.

### D. Client-side code bugs (nothing was submitted)

- **payment_channel_101:**
  - Steps 9 and 11: `verify_claim_signature` reports "Claim signature did NOT verify" for the sender's own fresh
    claims.
  - Step 12: `redeem_claim` raises "non-hexadecimal number found in fromhex() arg at position 1" before submitting.
  - Step 13 cascades ("expected 7 XRP, got 0").
  - The channel itself is fine: `262D0859…`, 15 XRP deposited.
- **deposit_gate_101, step 14:** `send_kyc_payment` raises `KeyError: 'CredentialIds'` locally ("Rejected by your
  client before reaching the network").

### Files

Each `<module>/` holds:
- `command.txt`, with the exit code;
- `preflight.txt`;
- `stdout.txt`, with the scratch path redacted;
- `stderr.txt`;
- `module_report.md`;
- `ledger_evidence.json`.
