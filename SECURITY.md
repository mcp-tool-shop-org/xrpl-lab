# Security Policy

## What XRPL Lab stores locally

| File | Location | Contains |
|------|----------|----------|
| `state.json` | `~/.xrpl-lab/` | Module progress, txids, wallet address, timestamps |
| `wallet.json` | `~/.xrpl-lab/` | Wallet seed (plaintext, protected by file permissions) |
| Reports | `./.xrpl-lab/reports/` | Human-readable markdown summaries |
| Proofs | `./.xrpl-lab/proofs/` | Shareable JSON (no secrets) |

## Secrets hygiene

- **Wallet seeds** are stored in `wallet.json` with restrictive file permissions (owner-only read/write)
- **Proof packs and certificates never contain seeds** — they only include public addresses and txids
- **Reports never contain seeds** — only public transaction data
- The CLI warns users not to share wallet files or paste seeds

## Trust boundaries

- **XRPL Testnet RPC**: Public endpoint, no authentication. Transactions are signed locally before submission
- **Testnet Faucet**: Public HTTP endpoint. Only your address is sent (no secrets)
- **Local filesystem**: State and wallet files are local-only. No telemetry, no phone-home
- **Module content**: Modules are bundled markdown files parsed locally
- **Dashboard / `serve` API**: Optional in-process HTTP + WebSocket server (see [Dashboard / serve surface](#dashboard--serve-surface)). Loopback-bound by default, no authentication, Origin allow-listed

## Testnet-only is code-enforced, not a convention

XRPL Lab will not sign or submit a transaction against mainnet or an unrecognized endpoint — and this is **enforced in code**, not merely documented. `classify_network` (in `xrpl_lab/transport/xrpl_testnet.py`) is the single source of truth: it classifies the effective RPC/faucet URL as `testnet`/`devnet`/`local` (allowed) or `mainnet`/`unknown` (refused, fail-closed).

- **Write path:** `submit_payment` (and every other signing method) refuses any endpoint not in `SAFE_NETWORKS` **before** the wallet seed is loaded or the network is touched — a mainnet `XRPL_LAB_RPC_URL` override returns a failed result, it does not sign.
- **Faucet:** the faucet path applies the same `classify_network` guard, so a mainnet/attacker `XRPL_LAB_FAUCET_URL` override is refused rather than sent your address.
- **Doctor:** `xrpl-lab doctor` **FAILS** the env-overrides check (not a passing informational note) when either override resolves to a non-testnet network, matching the transport's refusal.
- **Honest labels:** network names reported by the CLI, the dashboard, and exported artifacts reflect the *actual* classified network, never a hard-coded "testnet."

The `--dry-run` mode bypasses the network entirely and is the recommended path for offline practice.

## Workshop Setup

XRPL Lab uses a two-tier directory model designed for workshop facilitator handoff:

### Single-user private (`~/.xrpl-lab/`)
Created at mode `0o700` (owner-only). Contains:
- `wallet.json` — wallet seed (mode `0o600`)
- `state.json` — module progress, txid history (mode `0o600`)
- `doctor.log` — diagnostic log (mode `0o600`)

These files are personal to the learner and never intended to be shared.

### Workshop-shareable (`./.xrpl-lab/` in your working directory)
Created at mode `0o755`. Contains:
- `proofs/` — proof packs (no secrets, public txids only)
- `reports/` — markdown summaries
- `audit_packs/` — batch verification results
- `logs/` — runner logs

These are designed for facilitator inspection during workshop handoff. A facilitator can `ls` and `cat` files in this directory to review a learner's work without needing access to the learner's home directory or wallet.

### Per-learner isolation in shared lab environments

For workshops on a shared machine where each learner has a distinct OS user:
- Default behavior is correct: `~/<learner>/.xrpl-lab/` is owner-private; `./<learner>/.xrpl-lab/` (relative to learner's working dir) is shareable.

For workshops on a shared machine where multiple learners share an OS user (e.g., training labs with kiosk users):
- Set `XRPL_LAB_HOME` to a per-learner path: `XRPL_LAB_HOME=/tmp/learner-N xrpl-lab start`. The home dir's `0o700` mode prevents cross-learner reads even on the shared user.

### Threat model summary
- Local private files (`~/.xrpl-lab/`) protect learner secrets from other OS users.
- Workspace files (`./.xrpl-lab/`) are designed-readable for workshop handoff.

The two-tier design solves the shared-machine problem: learners keep secrets in their private home directory while sharing evidence (proofs, reports, audit packs) through the workspace directory, so a facilitator giving feedback only needs `cat` permissions on the workspace — never SSH or password access to a learner's account.

- See [the DD-1 implementation in xrpl_lab/state.py](xrpl_lab/state.py) for the per-directory mode policy.

## Network risks

- RPC endpoint can be overridden via `XRPL_LAB_RPC_URL` — must resolve to a testnet/devnet/local network or it is refused (see [Testnet-only is code-enforced](#testnet-only-is-code-enforced-not-a-convention))
- Faucet endpoint can be overridden via `XRPL_LAB_FAUCET_URL` — same refusal applies
- All network operations are optional (`--dry-run` mode works fully offline)

## Dashboard / serve surface

`xrpl-lab serve` starts an optional in-process HTTP API plus a WebSocket runner (and, when a built dashboard is present, mounts it at `/xrpl-lab/app/`). It exists for facilitator workshop use — a projector-friendly cohort view and live module runs — and its security posture is deliberately scoped to that.

- **Loopback by default.** The server binds `127.0.0.1` unless `--host` is passed. On a loopback bind it is reachable only from the host machine.
- **Non-loopback is warned, not blocked.** Passing a non-loopback `--host` (e.g. `0.0.0.0`) prints an explicit warning: there is no authentication, so binding off-loopback exposes the API and facilitator endpoints to the network. **Only do this on a trusted LAN.**
- **No authentication.** There is no login, cookie, or session auth. `allow_credentials` is explicitly `False` in the CORS config. Access control is the bind address plus the Origin allow-list — not identity.
- **WebSocket Origin allow-list.** Browser CORS does not cover WebSocket upgrades, so the WS handshake is gated manually: a missing or non-allow-listed `Origin` is rejected with RFC 6455 code `4003`. This closes the CSRF-via-WebSocket vector. The allow-list (`xrpl_lab/api/runner_ws.py:_ALLOWED_ORIGINS`) is the single source of truth shared by both the HTTP CORS middleware and the WS gate; `serve` extends it with the in-process dashboard's own origin when the dashboard is mounted.
- **No-leak error envelope.** Errors surfaced to the browser use a structured `{code, message, hint, severity, icon_hint}` envelope (`_error_envelope`). It never carries raw paths, stack traces, or internals — full detail goes only to the server log and `~/.xrpl-lab/doctor.log` on the host. A learner's browser sees a generic `RUNTIME_INTERNAL` message and a `run_id` to give the facilitator, nothing more.
- **Safe-to-expose facilitator endpoints.** The `GET /api/runs` observability endpoints project each run to a non-secret subset (run_id, module_id, status, timing) — queue contents, error detail, txids, and report paths are omitted from the public projection.
- **Concurrency cap.** Concurrent runs are capped (HTTP `429` over the cap) so a full room can't exhaust server memory.

## Common user mistakes

- Sharing `wallet.json` — this contains your seed. Treat it like a password file
- Overriding RPC/faucet to mainnet — XRPL Lab is testnet-only and **refuses** non-testnet endpoints in code (write path, faucet, and doctor); the override simply won't sign, so use `--dry-run` for offline practice instead
- Running in shared directories — workspace files are world-readable by default
- Binding `xrpl-lab serve` off-loopback on an untrusted network — the API has no auth; keep it on `127.0.0.1` or a trusted LAN only

## How to reset

```bash
xrpl-lab reset
```

This deletes `state.json` and the workspace directory. Your wallet file is preserved.

To fully remove all XRPL Lab data:

```bash
rm -rf ~/.xrpl-lab/
rm -rf ./.xrpl-lab/
```

## Reporting vulnerabilities

Report security issues at: https://github.com/mcp-tool-shop-org/xrpl-lab/security/advisories/new

We will respond within 48 hours.
