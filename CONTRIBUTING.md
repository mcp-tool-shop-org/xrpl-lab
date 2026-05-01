# Contributing to xrpl-lab

Thanks for considering a contribution. xrpl-lab is a **testnet-only, local-only, no-telemetry** workbook for learning the XRP Ledger. Every contribution must respect those architectural constraints — see [SECURITY.md](./SECURITY.md) for the full threat model.

The most common contribution is a **new module** (a learning step). This guide walks you through it.

---

## Setup

```bash
git clone https://github.com/mcp-tool-shop-org/xrpl-lab.git
cd xrpl-lab
uv sync --all-extras
bash verify.sh
```

If `verify.sh` is green you have a working dev environment. For broader orientation see the handbook's [Getting Started](./site/src/content/docs/handbook/getting-started.md) page.

---

## Authoring a new module

Modules live under `modules/<track>/<id>.md` and are validated by the linter before they reach the curriculum.

### 1. Scaffold

```bash
xrpl-lab module init \
  --id MY_MODULE \
  --track foundations \
  --title "My module title" \
  --time "20 min"
```

This drops a frontmatter-correct skeleton in the right place. (See `xrpl-lab module init --help` for full flags.)

### 2. Frontmatter

Every module file starts with YAML frontmatter. The required keys are:

- `id` — unique identifier, SCREAMING_SNAKE_CASE
- `track` — one of the registered tracks (e.g. `foundations`)
- `title` — human-readable
- `time` — estimated completion (`"20 min"`, `"1 hr"`)
- `requires` — list of module ids this depends on (may be empty)
- `produces` — list of artifact tags this emits (may be empty)
- `checks` — list of check ids the module exercises

The linter enforces these. Run `xrpl-lab lint <new-file>.md` for fast feedback, or `xrpl-lab lint` to validate the whole curriculum.

### 3. Steps

Module body is numbered Markdown sections. Steps that the runner executes carry an action comment:

```markdown
## 1. Make a wallet

<!-- action: ensure_wallet -->

Run `xrpl-lab run MY_MODULE` and a testnet wallet will be created…
```

Available actions and their parameters are documented in the handbook's [modules](./site/src/content/docs/handbook/modules.md) page.

### 4. Mode

Modules declare execution mode. Use `testnet` for live calls against `wss://s.altnet.rippletest.net:51233`; use `dry-run` for steps that should be illustrated without sending real transactions. **Never** target mainnet — the linter rejects it.

---

## Tests

Run the full Python suite:

```bash
UV_PROJECT_ENVIRONMENT=$HOME/.venvs/xrpl-lab uv run pytest tests/ -v
```

Or the gate the CI uses:

```bash
bash verify.sh
```

If your module touches tracked APIs, schemas, or rendered output, regenerate snapshot tests and review the diff before committing.

---

## PR checklist

Before opening a pull request:

- [ ] `xrpl-lab lint` passes against the new/modified module
- [ ] `bash verify.sh` passes (lint + tests + build + security)
- [ ] `CHANGELOG.md` updated with a one-line module description
- [ ] Snapshot tests regenerated and reviewed if APIs/schemas changed
- [ ] No mainnet endpoints, telemetry, or network writes outside testnet

PRs target `main`. CI must be green before merge.

---

## Code of conduct

Be respectful. Focus on the workbook mission: making the XRP Ledger learnable, locally and safely. A formal Code of Conduct may be added in a future release; until then, this paragraph stands.

For architectural and project-shape questions that go beyond a single module, the handbook is the source of truth — start at [docs/handbook](./site/src/content/docs/handbook/index.md).
