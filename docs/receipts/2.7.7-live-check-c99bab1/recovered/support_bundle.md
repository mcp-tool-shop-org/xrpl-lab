
## XRPL Lab Support Bundle

```
xrpl-lab v2.7.7
Python 3.13.13 on Windows
Generated: 2026-10-22T04:11:18.777941+00:00
```

### Curriculum Position

- Current module: receipt_literacy
- Current track: foundations
- Mode: testnet
- Progress: 1/32 modules

### Track Progress

- foundations: 0/5
- nfts: 0/3
- tokens: 1/4
- payments: 0/7
- identity: 0/4
- dex: 0/3
- reserves: 0/2
- audit: 0/1
- amm: 0/2
- capstone: 0/1

### Environment

- Network: testnet
- RPC: `https://s.altnet.rippletest.net:51234`
- Faucet: `https://faucet.altnet.rippletest.net`
- Wallet: `rndd9v87akkzAfWHKmZRJ9ueP5ULdTNyUV`

### Transactions

- Total: 9 (4 ok, 5 failed (1 expected))
- Recent:
  -  6F5DED95D14934051A8AE82C... (clawback_101)
  -  70670718B3434D57849A2CAA... (clawback_101)
  -  D507407A9F40FAFAA29F4914... (clawback_101)
  -  7718FE4D326C45D79221F6CD... (clawback_101)
  - [FAIL (expected)] E3066287BAC8D48D60DA7067... (clawback_101)

### Artifacts

- Proof pack: no
- Certificate: no
- Reports: 1

### Doctor

- [PASS] Wallet: Found: rndd9v87akkzAfWHKmZRJ9ueP5ULdTNyUV
- [PASS] State file: v2.7.7, 1 module(s) completed
- [PASS] Workspace: Writable: 
<scratch>/force-check-c99bab1-20261022T0407Z/cwd/.xrpl-lab
- [PASS] Env overrides: None (using defaults)
- [PASS] Directory permissions: Windows ACLs not tightened by xrpl-lab for 
<scratch>/force-check-c99bab1-20261022T0407Z/home
  - Hint: xrpl-lab tightens directory permissions to owner-only on Linux/macOS (chmod 0o700); on Windows it does not yet tighten the ACL. If this machine is 
shared, consider restricting access yourself, e.g.: icacls "%USERPROFILE%\.xrpl-lab" /inheritance:r /grant:r "%USERNAME%":F
- [PASS] RPC endpoint: Connected to https://s.altnet.rippletest.net:51234 (ledger 21725611)
- [PASS] Faucet: Reachable: https://faucet.altnet.rippletest.net (HTTP 404)
- [PASS] Last error: No failed transactions
- [PASS] Last module state: last completed: clawback_101 (2026-10-22T04:11:13Z) | in-flight: none | drift: none

---
*Attach proof pack if relevant. Run `xrpl-lab proof-pack` to generate.*

