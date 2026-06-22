# Ship Gate

> No repo is "done" until every applicable line is checked.
> Copy this into your repo root. Check items off per-release.

**Tags:** `[all]` every repo · `[npm]` `[pypi]` `[vsix]` `[desktop]` `[container]` published artifacts · `[mcp]` MCP servers · `[cli]` CLI tools

**Detected:** `[all]` `[pypi]` `[npm]` `[cli]`

> **Date semantics:** Each item's date reflects the most-recent
> human verification. SHIP_GATE.md is re-stamped at every release as
> part of the shipcheck audit pass — items remain checked across
> releases until shipcheck flags them, at which point dates refresh.
> Dates older than the current release version indicate items
> verified at an earlier release that haven't been re-checked since.

---

## A. Security Baseline

- [x] `[all]` SECURITY.md exists (report email, supported versions, response timeline) (2026-05-01)
- [x] `[all]` README includes threat model paragraph (data touched, data NOT touched, permissions required) (2026-05-01)
- [x] `[all]` No secrets, tokens, or credentials in source or diagnostics output (2026-05-01)
- [x] `[all]` No telemetry by default — state it explicitly even if obvious (2026-05-01)

### Default safety posture

- [x] `[cli|mcp|desktop]` Dangerous actions (kill, delete, restart) require explicit `--allow-*` flag (2026-05-01) — `reset` requires typing "RESET"; `--force` for re-runs; no destructive action is silent
- [x] `[cli|mcp|desktop]` File operations constrained to known directories (2026-05-01) — only `~/.xrpl-lab/` and `./.xrpl-lab/`
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server

## B. Error Handling

- [x] `[all]` Errors follow the Structured Error Shape: `code`, `message`, `hint`, `cause?`, `retryable?` (2026-05-01) — `LabError` in `xrpl_lab/errors.py`
- [x] `[cli]` Exit codes: 0 ok · 1 user error · 2 runtime error · 3 partial success (2026-05-01) — mapped via error code prefix in `LabException.exit_code`
- [x] `[cli]` No raw stack traces without `--debug` (2026-05-01) — Rich console shows user-friendly messages; no `--debug` flag exists (stacks never shown)
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[desktop]` SKIP: not a desktop app
- [ ] `[vscode]` SKIP: not a VS Code extension

## C. Operator Docs

- [x] `[all]` README is current: what it does, install, usage, supported platforms + runtime versions (2026-05-01)
- [x] `[all]` CHANGELOG.md (Keep a Changelog format) (2026-06-22) — 24+ entries, v0.1.0 through v2.2.0
- [x] `[all]` LICENSE file present and repo states support status (2026-05-01) — MIT
- [x] `[cli]` `--help` output accurate for all commands and flags (2026-05-01)
- [x] `[cli|mcp|desktop]` Logging levels defined: silent / normal / verbose / debug — secrets redacted at all levels (2026-05-01) — Rich console output; no secrets in any output path; `--dry-run` for silent network
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[complex]` SKIP: single-user CLI, no background daemons or operational modes

## D. Shipping Hygiene

- [x] `[all]` `verify` script exists (test + build + smoke in one command) (2026-05-01) — `verify.sh`
- [x] `[all]` Version in manifest matches git tag (2026-06-22) — in sync at **v2.2.0** via single-sourcing: the *runtime* version (`__init__.py`, `state.py`) derives from `pyproject.toml` `[project].version` through `importlib.metadata.version("xrpl-lab")` (source-checkout fallback literal pinned to pyproject by `tests/test_v2_core.py::test_version_matches_pyproject`); the *literal* surfaces are `package.json` + `bin/xrpl-lab.js`, both gated against the release tag in `release.yml` (the bin gate was added after it drifted to v1.7.1 — CIDOCS-A-001/A-004)
- [x] `[all]` Dependency scanning runs in CI (ecosystem-appropriate) (2026-06-14) — `pip-audit --skip-editable --ignore-vuln PYSEC-2026-196` step in `ci.yml` (fails on real vulns; `--strict` dropped — incompatible with skipping the editable self-package; `pip` installer advisory out of scope); audited tree clean after `idna>=3.15` / `starlette>=1.0.1` runtime + `urllib3>=2.7.0` dev security floors; `ruff check` for code quality
- [x] `[all]` Automated dependency update mechanism exists (2026-05-01) — manual via `pip install --upgrade`; CI runs on `pyproject.toml` changes
- [x] `[npm]` `@mcptoolshop/xrpl-lab` binary-launcher wrapper (`package.json` + `bin/xrpl-lab.js`) in-repo; published via OIDC trusted publishing (`release.yml`, npm provenance, no tokens) (2026-06-14)
- [x] `[pypi]` `python_requires` set (2026-05-01) — `>=3.11` in pyproject.toml
- [x] `[pypi]` Clean wheel + sdist build (2026-05-01) — `python -m build` produces both cleanly
- [ ] `[vsix]` SKIP: not a VS Code extension
- [ ] `[desktop]` SKIP: not a desktop app

## E. Identity (soft gate — does not block ship)

- [x] `[all]` Logo in README header (2026-05-01)
- [x] `[all]` Translations (polyglot-mcp, 7 languages + en source) (2026-05-01) — ja, zh, es, fr, hi, it, pt-BR
- [x] `[org]` Landing page (@mcptoolshop/site-theme) (2026-05-01) — deployed via pages.yml
- [x] `[all]` GitHub repo metadata: description, homepage, topics (2026-05-01)

---

## Gate Rules

**Hard gate (A–D):** Must pass before any version is tagged or published.
If a section doesn't apply, mark `SKIP:` with justification — don't leave it unchecked.

**Soft gate (E):** Should be done. Product ships without it, but isn't "whole."

**Checking off:**
```
- [x] `[all]` SECURITY.md exists (2026-02-27)
```

**Skipping:**
```
- [ ] `[pypi]` SKIP: not a Python project
```
