# 2.7.6 live check on `ad456c0`

This is the live check the Editor asked for on **`ad456c0`** (PR #36, `feat/2.7.6`), the commit Argon passed. 2.7.6
fixes #34: `verify-artifact` now takes `--live`. `e53b72f`, the hint-string fix on top, landed after this run and
changes no behaviour.

- **Install:** the test checkout's editable install was reinstalled on `ad456c0`, so it reports `xrpl-lab, version
  2.7.6`. Every artifact here records `"version": "2.7.6"`.
- **Redaction:** no seeds and no wallet files are in this directory. Local paths are shown as `<scratch>`, `<home>`
  and `<worktree>`.
- **Integrity after redaction:** redaction touched only text output and the support bundle, which has no hash.
  Every artifact in `matrix/` still verifies.

## How it ran

1. **Two real testnet packs, each made in a fresh home** with the faucet-URL method (`XRPL_LAB_FAUCET_URL` set to a
   missing path on the testnet faucet host):
   - `pack-pass-force/`: clawback_101 run 1 fails (exit 3, `verified: false`, 4 `failed` placeholders). Then
     `run --force` passes (exit 0, `verified: true`, 4 txids).
   - `pack-left-failed/`: the same failing run 1 (exit 3), with no rerun.
2. **From the pass-force home:** a certificate (`xrpl-lab certificate`), an audit pack (`xrpl-lab audit` over the home's
   5 real txids) and a support bundle (`xrpl-lab support-bundle --json`).
3. **`verify_matrix.py` (harness) ran on each artifact:**
   - which commands: `verify-artifact`, and for packs and certificates the native command too (`proof verify` /
     `cert-verify`);
   - which modes: each with and without `--live` and with and without `--json`;
   - how: each call in its own process, from inside `matrix/` with a relative path.
   - `trace_cli.py` logs every network lookup and connect a call makes (`<label>.<n>.net`). Loopback connects are
     asyncio's own socketpair on Windows and are not counted.

## Verdict

| # | Artifact | Command | `--live` | `--live --json` | no `--live` | Network calls with / without `--live` |
|---|---|---|---|---|---|---|
| 1 | Passing pack | `verify-artifact` | exit 0 | exit 0 | exit 0 / exit 0 (`--json`) | 5 lookups of the testnet RPC host / **0** |
| 1 | Passing pack | `proof verify` | exit 0 | exit 0 | exit 0 / exit 0 | 5 / **0** |
| 2 | Left-failed pack | `verify-artifact` | **exit 1** | **exit 1** | exit 0 / exit 0 | 0 / 0 (its only claim has no hash) |
| 2 | Left-failed pack | `proof verify` | **exit 1** | **exit 1** | exit 0 / exit 0 | 0 / 0 |
| 3 | Certificate | `verify-artifact` | exit 0 | exit 0 | exit 0 / exit 0 | 0 / 0 |
| 3 | Certificate | `cert-verify` | exit 0 | exit 0 | exit 0 / exit 0 | 0 / 0 |
| 3 | Audit pack | `verify-artifact` | exit 0 | exit 0 | exit 0 / exit 0 | 0 / 0 |
| 3 | Support bundle | `verify-artifact` | exit 0 | exit 0 | exit 0 / exit 0 | 0 / 0 |

- **Item 1, the passing pack:** 5 PASS, 1 SKIPPED. The SKIP is the `failed` claim: "An earlier run's step that never
  reached a ledger; this module's latest run passed."
- **Item 2, the left-failed pack:** 0 PASS, 1 FAIL. Both commands give the same reason, in text and JSON: "A step
  failed before its transaction reached the network (no hash was recorded), so there is nothing on the ledger to
  check."
- **JSON for packs and certificates:** `verify-artifact` and the native command match exactly apart from
  `artifact_kind`, both with and without `--live` (`<label>.matrix.json`, `json_identical_except_artifact_kind`).
- **Text for packs and certificates:** the outputs differ only by `verify-artifact`'s "Artifact: proof pack" /
  "Artifact: certificate" line. The deprecated commands also print their deprecation line on stderr.
- **Item 3, the certificate:** with `--live`, "Certificates record no individual txids — there is nothing to anchor
  on-ledger…". In JSON, `live.overall_passed: true` with 0 / 0 / 0.
- **Item 3, the audit pack and support bundle:** with `--live`, "On-ledger verification doesn't apply to <kind>; only
  its integrity hash is checked." In `--json` it appears as `live.skipped` holding that note, and no other output
  changes.
- **Item 4, without `--live`:** no network lookup or connect on any artifact, for either command.

## Off the brief

1. **The support-bundle `--live` note is inaccurate** (sent to the Editor during the run).
   - A support bundle has no integrity hash, and `verify_support_bundle` (workshop.py:441) checks only structure.
     It returns "Support bundle is well-formed."
   - The note says "only its integrity hash is checked". The audit-pack note is accurate.
   - `verify-artifact --help` has the same wording ("embedded integrity hash"), from before this release.
2. **The certificate's `--live` note still names `proof verify`.** This is Argon's NB-1, fixed in `e53b72f` after
   this run.
3. **A stale support-bundle hint after a `--force` recovery** (minor, outside 2.7.6).
   - The pass-force home's support bundle has a "Last error" doctor check: "Last failure in 'clawback_101': tx
     failed".
   - Its hint is "Run: xrpl-lab verify --tx failed for details". That uses the placeholder as a txid, for a module
     whose latest run passed.
4. **The support bundle carries home-relative paths** (`~/…/.xrpl-lab`) in its doctor checks. That may be intended
   for a facilitator handoff. Here it is redacted to `<scratch>`, and `redact_tree.py` was widened to catch the `~/`
   form.

## The harness has switched

`course_sweep.py` and `sweep.sh` now call `verify-artifact <pack> --live --json`. They fall back to
`proof verify --live` when `verify-artifact --help` lists no `--live`, which is xrpl-lab before 2.7.6, since the
harness also runs older commits.

## Hashes to check on testnet

| What | Hash | Expected |
|---|---|---|
| Passing pack: run 2's Clawback | `8D4434B1FF8BB69C59022AD89823BAC85ECA6C094DEA66486D9989B8F80A8E81` | Clawback, tesSUCCESS |
| Passing pack: run 2's learner TrustSet | `C84A293E706DBB942C279CC223D6F7B162D8D70DDADD74AF24C00DAE368A4078` | TrustSet by learner `rKpJ5XRN…`, tesSUCCESS |
| Passing pack: the expected rejection | `D8DAB3F166928AEF5A2EF04E96663B38E3086A30AD2E3A1C97D72D6EDF9458AF` | Clawback, tecNO_PERMISSION, validated |

## Files

- `pack-pass-force/` and `pack-left-failed/` each hold:
  - `1-failing/` (and `2-force/` for the pass-force pack);
  - `records.txt`, `gate.txt`, `preflight_verify.txt`;
  - `proof_pack.json`, `verify_live.json` and `verify_live.exit` (that run's own `proof verify --live`);
  - `state_excerpt.json`.
- `matrix/` holds:
  - the five artifacts: `pack_pass.json`, `pack_fail.json`, `certificate.json`, `audit_pack.json`,
    `support_bundle.json`;
  - per call: `<label>.<n>.out`, `.err` and `.net`;
  - per artifact: `<label>.matrix.json`, with each call's command, exit code, network calls, parsed JSON, and the
    JSON comparison.
