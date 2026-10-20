# 2.6.0 AMM live-fire receipts (module #30, `amm_liquidity_101`)

The release acceptance test for PR #19 (2.6.0) is one live run of module #30 against XRPL Testnet. The question it
answers: does every step of `amm_liquidity_101` reach `tesSUCCESS` on the real network?

No seeds and no wallet files are in this directory. Testnet addresses and transaction hashes are public on-ledger.
Local paths are shown as `<scratch>`.

| Run | Date (UTC) | Code | Verdict |
|---|---|---|---|
| [run-1](run-1-f9-20261020T2056Z/) | 2026-10-20 20:56–21:01 | `7acc67c` (feat/2.6.0) | **FAIL**: no AMM was created; 4 submissions never validated |

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

`run-1-f9-20261020T2056Z/`:
- `command.txt`, `env.txt`, `preflight.txt`
- `stdout.txt` (the scratch path redacted), `stderr.txt`
- `module_report.md` (xrpl-lab's own report, unedited)
- `ledger_evidence.json` (`account_tx`, `account_info`, `server_state` reserves, `amm_info` and `simulate` results,
  all queried after the run)

The full raw folder (the unredacted ledger JSON and `state.json`) is kept locally, outside the repo.
