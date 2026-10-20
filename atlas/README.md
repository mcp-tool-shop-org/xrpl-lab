# xrpl-lab: how it works

Mapped at 2026-10-20 from commit fa2370c by Atlas 1.24.0.

## What this is

10 parts, mostly Python (175 files), Astro (13), TypeScript (8), CSS (4), JavaScript (2), HTML (1) and shell (1). Work enters through 8 doors; the busiest is CI, which reaches 4 parts. It publishes to npm and PyPI. It deploys a site to GitHub Pages. People run xrpl-lab.

## What changed since 2026-10-15 (c73deb4)

- modules/amm_liquidity_101.md is now read by tests/test_amm.py.
- design is no longer a part.
- 2 files added, 2 moved and 25 changed content, across 8 parts.

## What comes in

1. **CI.** On a pull request; on a push touching 11 paths; or by hand. Runs tests/, site/src/lib/artifacts-panels.test.ts and site/src/lib/dashboard-ui.test.ts; checks xrpl_lab/.
2. **Deploy site to GitHub Pages.** On a push to main touching 2 paths; or by hand. Runs site/astro.config.mjs and site/src/.
3. **Release Binaries.** When a release is published; when the workflow Release completes; or by hand. Builds xrpl_lab/__main__.py.
4. **Smoke Test (Testnet).** By hand. Runs xrpl_lab/transport/xrpl_testnet.py.
5. **Publish to PyPI.** When a release is published; when the workflow Release completes; or by hand. Checks xrpl_lab/.
6. **Release.** When a tag matching `v*` is pushed; or by hand. Runs no file this map can see.
7. **xrpl-lab** (a command people run, from package.json). Runs bin/xrpl-lab.js.
8. **xrpl-lab** (a command people run, from pyproject.toml). Runs xrpl_lab/cli.py.

## What happens through CI

1. The workflow runs site/src/lib/artifacts-panels.test.ts and site/src/lib/dashboard-ui.test.ts in the site and tests/ in tests; it checks xrpl_lab/ in xrpl_lab.
2. That reaches scripts (1 file).
3. It uploads coverage to Codecov.

## Who reads the results

CI writes nothing this map can see.

## The other doors

**Deploy site to GitHub Pages** runs site/astro.config.mjs and site/src/, and deploys the site.

**Release Binaries** creates a GitHub release and builds xrpl_lab/__main__.py into binaries for linux-x64 and win-x64 and uploads them to the release.

**Smoke Test (Testnet)** runs xrpl_lab/transport/xrpl_testnet.py.

**Publish to PyPI** checks xrpl_lab/ and publishes to PyPI.

**Release** runs no file this map can see, publishes to npm, and creates a GitHub release.

**xrpl-lab** (a command people run, from package.json) runs bin/xrpl-lab.js.

**xrpl-lab** (a command people run, from pyproject.toml) runs xrpl_lab/cli.py.

## What breaks what

- **xrpl_lab** is imported by 1 part (scripts), and by 1 more only from tests; it sits on the path of 5 doors.
- **the site** is imported by no other part and sits on the path of 2 doors.
- **scripts** is imported only from tests, by 1 part (tests), and sits on the path of 1 door.

## What tends to change together

No two source files, other than a file and its own test, changed together often enough to name.

1 file changed together with its own test, as expected.

Window: 180 days; a pair counts from 3 shared commits, since 5 source files reach 10 revisions; the floor rises to 10 when 25 do.

## What no test touches

- **bin** is imported by no test.

verify.sh runs in no workflow.

## Written but never read

No place this map can see is written, so none goes unread.

## Helpers that look duplicated

No two parts export a helper that looks alike.

## Generated, never hand-edited

Nothing in this repository writes to a tracked place this map can see.

## Hand-authored

People write .github/, docs/, modules/, presets/, the repository root and site/; 3 writes with paths built at run time may land here.

## Where to start

xrpl_lab/cli.py → xrpl_lab/curriculum.py → xrpl_lab/modules.py

Read those in order to follow one run of xrpl-lab end to end. This path follows xrpl-lab (a command people run, from pyproject.toml) from its entry, since CI runs only tests and checks.

## What this map cannot see

- 1 import could not be resolved: `tests/test_product_smoke.py` imports a path built at run time.
- 3 writes and 7 reads use paths built at run time and are not named here.
- 6 writes and 52 reads go to a path their caller passes, not to this repository.
- 1 write and 6 reads go to the home directory (.xrpl-lab/) or a path their caller passes, not to this repository.
- 4 reads go to the directory the command is run in, not to this repository.
- Statistics confidence is low: fewer than 25 source files reach 10 revisions in the window.

Regenerate with `npx --yes @dogfood-lab/atlas map`.
