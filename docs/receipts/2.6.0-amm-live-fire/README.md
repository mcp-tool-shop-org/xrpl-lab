# 2.6.0 AMM live-fire receipts (module #30, `amm_liquidity_101`)

The release acceptance test for PR #19 (2.6.0) is one live run of module #30 against XRPL Testnet. The question it
answers: does every step of `amm_liquidity_101` reach `tesSUCCESS` on the real network?

No seeds and no wallet files are in this directory. Testnet addresses and transaction hashes are public on-ledger.
Local paths are shown as `<scratch>`.

| Run | Date (UTC) | Code | Verdict |
|---|---|---|---|
| [run-1](run-1-f9-20261020T2056Z/) | 2026-10-20 20:56–21:01 | `7acc67c` (feat/2.6.0) | **FAIL**: no AMM was created; 4 submissions never validated |
| [run-2](run-2-f9-20261020T2124Z/) | 2026-10-20 21:24–21:27 | `f803a49` (feat/2.6.0) | **FAIL**: run 1's defects fixed; AMMCreate validated `tecUNFUNDED_AMM` (pool sized past one 100 XRP faucet grant) |
| [run-3](run-3-f9-20261020T2148Z/) | 2026-10-20 21:48–21:49 | `453d361` (feat/2.6.0) | **PASS**: all 18 steps; all 9 transactions `tesSUCCESS`; the pool was deleted after the full withdraw |

**Acceptance verdict: PASS on run 3 (`453d361`).** Runs 1 and 2 are kept as the failure record that led to the
fixes.

`35de678` (Argon's run-2 review fixes) landed on `feat/2.6.0` during run 3, so it is not covered by this run. It
changes code (`xrpl_lab/actions/amm.py`, `handlers.py`, `transport/xrpl_testnet.py`). Under the studio rule it goes to
Argon for a second review first, and then gets its own live run (run 4) so the receipt covers the PR head.

## Run 3: f9-20261020T2148Z, PASS

**Setup:** the same as runs 1 and 2, on `453d361`, which is run 2's receipt plus the fixes for sizing, failure
accounting, AMM hashes and the exit code.

**Preflight:**
- `classify_network` reported `testnet`.
- The network guard passed.
- Connected at ledger 21693271.

**Exit code:** xrpl-lab exited **0**, read from `PIPESTATUS[1]`.

**Status:**
- The panel reads "Complete".
- The report says "Steps: 18 passed, 0 failed" and "Transactions: 6 successful, 0 failed".
- `state.json` has the module `verified: true`.

**Accounts:**
- Learner: `rEfzCXENKBBTQbs6TzVFBH4GAjXyjX61FS`
- Issuer: `r9hxLvtS9daHa57h2GTnqHWHCSz2opCrU3`

**Ledger at the time:** `reserve_base` 1000000, `reserve_inc` 200000.

| # | Step | Tx type | Hash | Ledger | Engine result | Fee (drops) | Flags | Outcome |
|---|---|---|---|---|---|---|---|---|
| 1 | ensure_wallet | none | none | n/a | n/a | n/a | n/a | PASS |
| 2 | ensure_funded | Payment (faucet, 100 XRP) ×1 | `71497BEE…E145` | 21693273 | tesSUCCESS | 12 | 0 | PASS |
| 3 | create_issuer_wallet | none | none | n/a | n/a | n/a | n/a | PASS |
| 4 | fund_issuer | Payment (faucet, 100 XRP) | `D8B77F0F…B2FA` | 21693275 | tesSUCCESS | 12 | 0 | PASS |
| 5 | enable_default_ripple | AccountSet asfDefaultRipple | `A6917DA5…2BB7` | 21693277 | tesSUCCESS | 10 | SetFlag 8 | PASS: issuer `Flags` 0x800000 |
| 6 | set_trust_line | TrustSet LAB | `7E4BC208…EF0D` | 21693279 | tesSUCCESS | 10 | n/a | PASS |
| 7 | issue_token | Payment 1000 LAB | `EDC401FC…E370` | 21693281 | tesSUCCESS | 10 | n/a | PASS |
| 8 | snapshot_account | none | none | n/a | n/a | n/a | n/a | 99.999990 XRP, owner count 1 |
| 9 | ensure_amm_pair | AMMCreate 25 XRP / 25 LAB | `020B4543…1104` | 21693284 | **tesSUCCESS** | **200000 = reserve_inc** | n/a | PASS: pool 25/25 |
| 10 | get_amm_info | amm_info | n/a | n/a | ok | n/a | n/a | PASS: pool XRP 25, LAB 25, LP supply 25000 |
| 11 | amm_deposit 5/5 | AMMDeposit | `2105787A…203F` | 21693287 | **tesSUCCESS** | 10 | **0x00100000 tfTwoAsset** | PASS |
| 12 | verify_lp_received | none | none | n/a | n/a | n/a | n/a | PASS: LP balance 30000; pool 30/30; LP supply 30000 |
| 13 | snapshot_account | none | none | n/a | n/a | n/a | n/a | 69.799980 XRP, owner count 2 |
| 14 | verify_reserve_change | none | none | n/a | n/a | n/a | n/a | PASS: −30.200010 XRP (30 XRP into the pool + the 0.2 create fee + 10 drops); owner count 1 → 2 (the LP-token line) |
| 15 | amm_withdraw (all) | AMMWithdraw | `27CADA3F…84B5` | 21693290 | **tesSUCCESS** | 10 | **0x00020000 tfWithdrawAll** | PASS |
| 16 | verify_withdrawal | none | none | n/a | n/a | n/a | n/a | PASS: "LP tokens decreased: 30000 -> 0", "All LP tokens returned"; no contradictory line |
| 17 | snapshot_account | none | none | n/a | n/a | n/a | n/a | 99.799970 XRP, owner count 1 |
| 18 | verify_reserve_change | none | none | n/a | n/a | n/a | n/a | PASS: −0.200020 XRP net (the create fee + 2 × 10 drops); owner count back to 1 |

Pool and reserve before and after:
- **Pool:** 25/25 after the create, 30/30 after the deposit, deleted after the full withdraw.
- **Learner:**
  - 99,999,990 drops and owner count 1 before the AMM steps;
  - 69,799,980 drops and owner count 2 after the deposit;
  - 99,799,970 drops and owner count 1 after the withdraw.
- **LAB:** the learner's balance is back to 1000 on its single trust line, and the LP-token line is gone.

### The F9 watch-items (Argon): all three settled

| Risk | Status |
|---|---|
| AMMCreate fee (`max_fee` cap, `telINSUF_FEE_P`) | **Cleared on the ledger.** A `tesSUCCESS` AMMCreate (`020B4543…`) paid exactly `reserve_inc` = 200000 drops. Run 2's validated `tec` paid the same. |
| Deposit/withdraw mode flags (`temINVALID_FLAG`) | **Cleared on the ledger.** AMMDeposit with `tfTwoAsset` (0x00100000) and AMMWithdraw with `tfWithdrawAll` (0x00020000) both validated `tesSUCCESS`. |
| `amm_info` → `actNotFound` after a full withdraw | **Confirmed.** The creator was the sole LP and withdrew with `tfWithdrawAll`. The AMM was deleted, and `amm_info` XRP/LAB returned `actNotFound` ("Account not found") on the validated ledger after the run. |

### Notes from run 3

- **`issueMalformed` did not recur.** It comes only from the failed-create path, where the fallback `AmmInfo` has
  empty issuers (Argon F4.1, open but low).
- **stderr has two `amm_info error for XRP/LAB: actNotFound` lines.** These are the healthy "no pool yet" answer,
  logged as a warning because `get_amm_info` checks `entryNotFound` (Argon F6, open but low).
- **The AMMCreate preflight is silent when the wallet can cover the pool.** It prints "needs N XRP, has M XRP" only
  on a shortfall (`handlers.py:1780-1787`), so this run shows that it didn't block, not the line itself. By its own
  formula the create needed 26.6 XRP (25 XRP leg + 0.2 XRP fee + 1 XRP base reserve + 2 × 0.2 XRP owner reserve)
  against 99.99999 XRP held.

---

## Run 2: f9-20261020T2124Z, FAIL

**Setup:** the same as run 1, on `f803a49`, which is run 1's receipt plus the fixes for funding, held results and
honest status.

**Preflight:**
- `classify_network` reported `testnet`.
- The network guard passed.
- Connected at ledger 21692849.

**Exit code:** xrpl-lab exited **0**, read from `PIPESTATUS[1]`, even though the run ended "Completed with failures".

**Accounts:**
- Learner: `rQ3mdmTCHGHsVzSnfoSYqktePZeHu7CJCy`
- Issuer: `rGaJTbCz2i9ccNoJ9XZmZrVcrtzRLD2Ew5`

**Ledger at the time:** `reserve_base` 1000000, `reserve_inc` 200000.

| # | Step | Tx type | Hash | Engine result | Fee (drops) | Flags | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | ensure_wallet | none | none | n/a | n/a | n/a | PASS |
| 2 | ensure_funded | Payment (faucet, 100 XRP) ×1 | `CA029368…68CB0` (ledger 21692852) | tesSUCCESS | 12 | 0 | PASS: one call, "Funded! Balance: 100.000000 XRP" |
| 3 | create_issuer_wallet | none | none | n/a | n/a | n/a | PASS |
| 4 | fund_issuer | Payment (faucet, 100 XRP) | `4244473F…438F8` (21692854) | tesSUCCESS | 12 | 0 | PASS: balance read back as 100 XRP |
| 5 | enable_default_ripple | AccountSet asfDefaultRipple | `FE8679A4…DBE4E` (21692857) | tesSUCCESS | 10 | SetFlag 8 | PASS: issuer `Flags` 0x800000 |
| 6 | set_trust_line | TrustSet | `21B056C7…CE0F` (21692859) | tesSUCCESS | 10 | n/a | PASS |
| 7 | issue_token | Payment 1000 LAB | `6521535C…1888` (21692861) | tesSUCCESS | 10 | n/a | PASS |
| 8 | snapshot_account | none | none | n/a | n/a | n/a | 99.999990 XRP, owner count 1 |
| 9 | ensure_amm_pair | AMMCreate 100 XRP / 100 LAB | `1C14C1C3…08A1F5` (21692864) | **tecUNFUNDED_AMM** | **200000 = reserve_inc** | n/a | **FAIL**: hash never printed or recorded |
| 10 | get_amm_info | amm_info | n/a | actNotFound | n/a | n/a | FAIL (follows from step 9); printed nothing for "no pool" |
| 11 | amm_deposit 10/10 | AMMDeposit | `A55B97F2…BA31B` (recorded in `tx_index`) | not found on the network (`txnNotFound`) | n/a | tfTwoAsset | **FAIL**: "There is no AMM pool" |
| 12 | verify_lp_received | none | none | n/a | n/a | n/a | FAIL |
| 13 | snapshot_account | none | none | n/a | n/a | n/a | 99.799990 XRP: the 0.2 XRP AMMCreate fee |
| 14 | verify_reserve_change | none | none | n/a | n/a | n/a | "decreased by 0.200000 XRP" (the failed AMMCreate's fee) |
| 15 | amm_withdraw | AMMWithdraw | `A91F3B02…B7B98` (recorded) | known but not validated; LastLedgerSequence 21692905 passed | n/a | tfWithdrawAll | **FAIL**: "There is no AMM pool"; stderr `issueMalformed` |
| 16 | verify_withdrawal | none | none | n/a | n/a | n/a | FAIL: still prints both a ✓ and a ✗ |
| 17 | snapshot_account | none | none | n/a | n/a | n/a | unchanged |
| 18 | verify_reserve_change | none | none | n/a | n/a | n/a | "decreased by 0.200000 XRP" |

Pool and reserve before and after:
- **Pool:** never created. `amm_info` XRP/LAB returned `actNotFound` after the run.
- **Learner:** 99,999,990 drops before the AMM steps and 99,799,990 after, owner count 1 throughout.

### What run 2 fixed (verified against the ledger)

- **Funding:** one faucet call per account, no triple funding. Each account appeared on a validated ledger before
  its next step. The issuer was funded at ledger 21692854, and its AccountSet validated at 21692857.
- **DefaultRipple** is set (issuer `Flags` 0x800000), so the run-1 chain (`terNO_RIPPLE` → `terNO_AMM`) is gone.
- **Panel and report:**
  - The panel reads "Completed with failures" and lists failed steps.
  - The report's step numbers match the module.
  - The report has a "Steps: N passed, M failed" line.

### What run 2 found

1. **Blocking: the pool is sized past one faucet grant.**
   - The faucet now funds 100 XRP once.
   - The module's AMMCreate asks for 100 XRP into the pool. Before the AMM steps the learner held 99.99999 XRP, and
     the account reserve alone is 1 XRP plus 0.2 XRP per owned object, with 1 already owned (the LAB trust line).
   - So the AMMCreate can never be funded: `tecUNFUNDED_AMM`.
   - In run 1 this was hidden: the false-negative faucet loop funded 300 XRP.
2. **Failed AMM steps don't count as failures.**
   - The runner marks a step failed on a failed verification, or on a new unsuccessful `context["last_submit"]`.
   - The AMM handlers never set `last_submit`. So steps 9, 11 and 15 count as passed.
   - The report says "Steps: 16 passed, 2 failed" and "Transactions: 3 successful, 0 failed". The panel lists only
     steps 12 and 16.
   - The process exits 0.
3. **A validated hash goes missing.**
   - `handle_ensure_amm_pair`'s failure branch neither prints nor records the AMMCreate hash. `1C14C1C3…` is
     only in the ledger.
   - The deposit and withdraw hashes are recorded in `tx_index` but not printed.
   - The recorded deposit hash `A55B97F2…` is unknown to the network.
4. **The `tec` failure message says "fee charged on mainnet"** on a testnet run.
5. **Still open from run 1:** `verify_withdrawal` prints both a pass and a fail line, and an `amm_info` call logs
   `issueMalformed`.

### The F9 watch-items (Argon) after run 2

| Risk | Status |
|---|---|
| AMMCreate fee | **Cleared on the ledger.** The validated AMMCreate `1C14C1C3…` paid exactly `reserve_inc` = 200000 drops. No `telINSUF_FEE_P`, no `max_fee` cap. |
| Deposit/withdraw mode flags | Cleared at preflight (run 1). Not yet seen on a validated deposit or withdraw. |
| `amm_info` → `actNotFound` after a full withdraw | **Not tested.** No pool was created. |

---

## Run 1: f9-20261020T2056Z, FAIL

**Setup.**
- Clean worktree at `7acc67c`.
- `XRPL_LAB_HOME` pointed at a scratch folder outside every repo.
- `XRPL_LAB_RPC_URL` and `XRPL_LAB_FAUCET_URL` were unset.

**Preflight** (see `preflight.txt`):
- `classify_network` reported `testnet`.
- The network guard passed.
- `get_network_info` connected at ledger 21692354.

**Command:** `yes "" | xrpl-lab run amm_liquidity_101`, with xrpl-lab 2.6.0, xrpl-py 4.5.0 and Python 3.13.13.

**Accounts:**
- Learner wallet: `rNgrA8eo8Bdee3hYEJ4euJoke4DhKJ1APy`
- Issuer: `rfsraes2gh6h26SgtaxR2Cf3UNVWHJJekH`

**Ledger at the time:** `reserve_base` 1000000 drops, `reserve_inc` 200000 drops.

### Per step

"Engine result" is the validated result where the transaction reached a ledger. Where the client timed out before
recording a hash, the result shown comes from a read-only `simulate` call made after the run against the same
accounts. Those rows are marked *(sim)*, and `ledger_evidence.json` holds the data behind them. `simulate` applies
nothing to the ledger.

| # | Step | Tx type | Hash | Engine result | Fee (drops) | Flags | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | ensure_wallet | none | none | n/a | n/a | n/a | PASS |
| 2 | ensure_funded | Payment (faucet) ×3 | `EA526DDB…DAAF2`, `9B1F231D…3F2E`, `415322A7…EDC4` | tesSUCCESS ×3 | 12 each | 0 | **FAIL**: funded 3 times (300 XRP), but each attempt was reported as "did not fund" |
| 3 | create_issuer_wallet | none | none | n/a | n/a | n/a | PASS |
| 4 | fund_issuer | Payment (faucet) | `9CFFD320…FF17` | tesSUCCESS | 12 | 0 | PASS, printed "Balance: unknown XRP" |
| 5 | enable_default_ripple | AccountSet (asfDefaultRipple) | none (60s client timeout) | never validated; tesSUCCESS *(sim, after the run)* | n/a | SetFlag 8 | **FAIL**: issuer `Flags` = 0x0; no sequence consumed |
| 6 | set_trust_line | TrustSet | `41A618B2…8C94` | tesSUCCESS | 10 | n/a | PASS |
| 7 | issue_token | Payment (1000 LAB) | `C6EF15D0…AE98` | tesSUCCESS | 10 | n/a | PASS |
| 8 | snapshot_account | none | none | n/a | n/a | n/a | 299.999990 XRP, owner count 1 |
| 9 | ensure_amm_pair | AMMCreate XRP/LAB 100/100 | none (60s client timeout) | **terNO_RIPPLE** *(sim)* | pinned to `reserve_inc` = 200000 *(not on ledger)* | n/a | **FAIL** |
| 10 | get_amm_info | amm_info | n/a | actNotFound | n/a | n/a | FAIL (follows from step 9) |
| 11 | amm_deposit 10/10 | AMMDeposit | none (60s client timeout) | **terNO_AMM** *(sim)* | n/a | tfTwoAsset 0x00100000 | **FAIL** |
| 12 | verify_lp_received | none | none | n/a | n/a | n/a | FAIL, "No LP tokens received" |
| 13 | snapshot_account | none | none | n/a | n/a | n/a | unchanged |
| 14 | verify_reserve_change | none | none | n/a | n/a | n/a | "no significant changes" (passes only because nothing happened) |
| 15 | amm_withdraw | AMMWithdraw | none (60s client timeout) | **terNO_AMM** *(sim)* | n/a | tfWithdrawAll 0x00020000 | **FAIL**; stderr also shows `amm_info … issueMalformed` |
| 16 | verify_withdrawal | none | none | n/a | n/a | n/a | FAIL; printed both "✓ All LP tokens returned" and "✗ no withdrawal detected" |
| 17 | snapshot_account | none | none | n/a | n/a | n/a | unchanged |
| 18 | verify_reserve_change | none | none | n/a | n/a | n/a | "no significant changes" (passes only because nothing happened) |

Pool and reserve before and after:
- **Pool:** no pool existed at any point. `amm_info` for XRP/LAB returned `actNotFound` after the run.
- **Wallet:** balance 299999990 drops, owner count 1, before and after. No AMM transaction consumed a sequence: the
  wallet `Sequence` was 21692362 when the run ended.

### Why it failed

1. **Step 5 never landed, so every AMM step after it failed.**
   - AMMCreate requires `lsfDefaultRipple` on the token issuer. Without it, rippled returns `terNO_RIPPLE`.
   - A `ter` code is provisional: rippled holds the transaction instead of validating it. xrpl-py's `submit_and_wait`
     therefore keeps polling until `LastLedgerSequence` passes, about 20 ledgers. The transport's 60s
     `SUBMIT_TIMEOUT` fires first, so the client reports a timeout with no hash and no engine result.
   - AMMDeposit and AMMWithdraw then hit `terNO_AMM` and time out the same way.
   - `simulate` after the run confirms all three codes.
2. **Why step 5's AccountSet didn't land: not proven.** This is a hypothesis, labelled as one:
   - The faucet answered for the issuer, but `fund_issuer` printed `Balance: unknown`, and the AccountSet was
     submitted right after.
   - The account had only just been funded (ledger 21692363), so the submit probably got a provisional `ter*` (for
     example `terNO_ACCOUNT` on a node behind the load balancer that hadn't seen it yet). It then timed out like the
     others.
   - The same AccountSet simulates to `tesSUCCESS` now.
   - The client timeout throws away the provisional result, so the run cannot show which code it was.
3. **The faucet funding was reported as failed even though it succeeded:**
   - `runtime.py` counts a funding as successful only when `FundResult.balance` parses as a number greater than 0.
   - The faucet's answer had no usable `balance`, so the transport returned `"unknown"`, which parses to 0.
   - Each successful funding was therefore treated as "did not fund", and the loop funded the wallet three times.
   - The issuer path (`handlers.py:477`) doesn't check the balance, so it printed "unknown" and went straight on to
     step 5.

### Other defects this run exposed

- **The module was recorded as completed** (`state.json`: `completed_modules`, `verified: false`) and printed the
  "Complete" panel and "What you proved", although 4 submissions and 3 verifications failed.
- **The module report is wrong.** Its summary says "2 successful, 0 failed". Each step section lists every txid
  accumulated so far, not just the step's own. Its step numbers are one higher than the module's.
- **Only 3 of the 4 failed submissions appear in `tx_index`** (as `"txid": "failed"`).
- **`verify_withdrawal` printed a pass and a fail line** for the same state.
- **The timeout message is self-contradictory.** It says the transaction was "handed to the network", then
  classifies it as Category `local`, "Rejected by your client before reaching the network".
- **The xrpl-lab exit code was not captured.** Under `pipefail`, `yes` exits 141 (SIGPIPE) and masks it. Run 2 will
  read `PIPESTATUS`.

### The F9 watch-items (Argon)

| Risk | Status after run 1 |
|---|---|
| AMMCreate fee: `max_fee` caps the fee, or the fee is below `reserve_inc` (`telINSUF_FEE_P`) | **Partly cleared.** The fee is pinned to `reserve_inc` (200000), there was no local fee rejection, and `simulate` at that fee passed preflight (`terNO_RIPPLE`, not `telINSUF_FEE_P`). Not yet proven on a validated AMMCreate. |
| Deposit/withdraw mode flags (`temINVALID_FLAG`) | **Cleared at preflight.** `tfTwoAsset` with both amounts and `tfWithdrawAll` with no amounts reached `terNO_AMM`; `temINVALID_FLAG` is a preflight check and would have come first. Not yet proven on a validated deposit or withdraw. |
| `amm_info` → `actNotFound` after a full withdraw | **Not tested.** No pool was ever created. |

### Files

Each `run-N-<run-id>/` holds the same set (run 2's `ledger_evidence.json` also has a ledger lookup of each hash xrpl-lab
recorded):
- `command.txt`, `env.txt`, `preflight.txt`
- `stdout.txt` (the scratch path redacted), `stderr.txt`
- `module_report.md` (xrpl-lab's own report, unedited)
- `ledger_evidence.json` (`account_tx`, `account_info`, `server_state` reserves, `amm_info` and `simulate` results,
  all queried after the run)

The full raw folder (the unredacted ledger JSON and `state.json`) is kept locally, outside the repo.
