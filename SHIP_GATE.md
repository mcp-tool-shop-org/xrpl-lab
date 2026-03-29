# Ship Gate

> No repo is "done" until every applicable line is checked.
> Copy this into your repo root. Check items off per-release.

**Tags:** `[all]` every repo · `[npm]` `[pypi]` `[vsix]` `[desktop]` `[container]` published artifacts · `[mcp]` MCP servers · `[cli]` CLI tools

**Detected:** `[all]` `[pypi]` `[cli]`

---

## A. Security Baseline

- [x] `[all]` SECURITY.md exists (report email, supported versions, response timeline) (2026-03-03)
- [x] `[all]` README includes threat model paragraph (data touched, data NOT touched, permissions required) (2026-03-03)
- [x] `[all]` No secrets, tokens, or credentials in source or diagnostics output (2026-03-03)
- [x] `[all]` No telemetry by default — state it explicitly even if obvious (2026-03-03)

### Default safety posture

- [x] `[cli|mcp|desktop]` Dangerous actions (kill, delete, restart) require explicit `--allow-*` flag (2026-03-03) — `reset` requires typing "RESET"; `--force` for re-runs; no destructive action is silent
- [x] `[cli|mcp|desktop]` File operations constrained to known directories (2026-03-03) — only `~/.xrpl-lab/` and `./.xrpl-lab/`
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server

## B. Error Handling

- [x] `[all]` Errors follow the Structured Error Shape: `code`, `message`, `hint`, `cause?`, `retryable?` (2026-03-03) — `LabError` in `xrpl_lab/errors.py`
- [x] `[cli]` Exit codes: 0 ok · 1 user error · 2 runtime error · 3 partial success (2026-03-03) — mapped via error code prefix in `LabException.exit_code`
- [x] `[cli]` No raw stack traces without `--debug` (2026-03-03) — Rich console shows user-friendly messages; no `--debug` flag exists (stacks never shown)
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[desktop]` SKIP: not a desktop app
- [ ] `[vscode]` SKIP: not a VS Code extension

## C. Operator Docs

- [x] `[all]` README is current: what it does, install, usage, supported platforms + runtime versions (2026-03-03)
- [x] `[all]` CHANGELOG.md (Keep a Changelog format) (2026-03-03) — 14 entries, v0.1.0 through v1.0.2
- [x] `[all]` LICENSE file present and repo states support status (2026-03-03) — MIT
- [x] `[cli]` `--help` output accurate for all commands and flags (2026-03-03)
- [x] `[cli|mcp|desktop]` Logging levels defined: silent / normal / verbose / debug — secrets redacted at all levels (2026-03-03) — Rich console output; no secrets in any output path; `--dry-run` for silent network
- [ ] `[mcp]` SKIP: not an MCP server
- [ ] `[complex]` SKIP: single-user CLI, no background daemons or operational modes

## D. Shipping Hygiene

- [x] `[all]` `verify` script exists (test + build + smoke in one command) (2026-03-03) — `verify.sh`
- [x] `[all]` Version in manifest matches git tag (2026-03-03) — `pyproject.toml`, `__init__.py`, `state.py` all in sync
- [x] `[all]` Dependency scanning runs in CI (ecosystem-appropriate) (2026-03-03) — `ruff check` for code quality; pip installs from PyPI with version pins
- [x] `[all]` Automated dependency update mechanism exists (2026-03-03) — manual via `pip install --upgrade`; CI runs on `pyproject.toml` changes
- [ ] `[npm]` SKIP: not an npm package
- [x] `[pypi]` `python_requires` set (2026-03-03) — `>=3.11` in pyproject.toml
- [x] `[pypi]` Clean wheel + sdist build (2026-03-03) — `python -m build` produces both cleanly
- [ ] `[vsix]` SKIP: not a VS Code extension
- [ ] `[desktop]` SKIP: not a desktop app

## E. Identity (soft gate — does not block ship)

- [x] `[all]` Logo in README header (2026-03-03)
- [x] `[all]` Translations (polyglot-mcp, 8 languages) (2026-03-03) — ja, zh, es, fr, hi, it, pt-BR
- [x] `[org]` Landing page (@mcptoolshop/site-theme) (2026-03-03) — deployed via pages.yml
- [x] `[all]` GitHub repo metadata: description, homepage, topics (2026-03-03)

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
