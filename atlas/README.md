# xrpl-lab: how it works

Mapped at 2026-09-25 from commit 0b2dd2f.

## What this is

11 parts, mostly Python (173 files), TypeScript (8) and JavaScript (2). Work enters through 8 doors; the busiest is CI, which reaches 4 parts. It publishes to npm and PyPI. People run xrpl-lab.

## What changed since the last map

This is the first map.

## What comes in

1. **CI.** On a pull request touching 10 paths; on a push touching 10 paths; or by hand. Runs tests/, site/src/lib/artifacts-panels.test.ts and site/src/lib/dashboard-ui.test.ts; checks xrpl_lab/.
2. **Deploy site to GitHub Pages.** On a push to main touching 2 paths; or by hand. Runs site/astro.config.mjs and site/src/.
3. **Release Binaries.** When a release is published; when the workflow Release completes; or by hand. Builds xrpl_lab/__main__.py.
4. **Publish to PyPI.** When a release is published; when the workflow Release completes; or by hand. Checks xrpl_lab/.
5. **Release.** When a tag matching `v*` is pushed; or by hand. Runs no file this map can see.
6. **Smoke Test (Testnet).** By hand. Runs no file this map can see.
7. **xrpl-lab** (a command people run, from package.json). Runs bin/xrpl-lab.js.
8. **xrpl-lab** (a command people run, from pyproject.toml). Runs xrpl_lab/cli.py.

## What happens through CI

1. The workflow runs site/src/lib/artifacts-panels.test.ts and site/src/lib/dashboard-ui.test.ts in the site and tests/ in tests; it checks xrpl_lab/ in xrpl_lab.
2. That reaches scripts (1 file).

## Who reads the results

CI writes nothing this map can see.

## The other doors

**Deploy site to GitHub Pages** runs site/astro.config.mjs and site/src/, and deploys the site.

**Release Binaries** creates a GitHub release and builds xrpl_lab/__main__.py into binaries for linux-x64 and win-x64 and uploads them to the release.

**Publish to PyPI** checks xrpl_lab/ and publishes to PyPI.

**Release** runs no file this map can see, publishes to npm, and creates a GitHub release.

**Smoke Test (Testnet)** runs no file this map can see.

**xrpl-lab** (a command people run, from package.json) runs bin/xrpl-lab.js.

**xrpl-lab** (a command people run, from pyproject.toml) runs xrpl_lab/cli.py.

## What breaks what

- **xrpl_lab** is imported by 1 part (scripts), and by 1 more only from tests; it sits on the path of 4 doors.
- **the site** is imported by no other part and sits on the path of 2 doors.
- **scripts** is imported only from tests, by 1 part (tests), and sits on the path of 1 door.

## What tends to change together

No two source files, other than a file and its own test, changed together often enough to name.

1 file changed together with its own test, as expected.

Window: 180 days; a pair counts from 3 shared commits, since 13 source files reach 10 revisions; the floor rises to 10 when 25 do.

## What no test touches

- **bin** is imported by no test.

## Written but never read

No place this map can see is written, so none goes unread.

## Helpers that look duplicated

No two parts export a helper that looks alike.

## Generated, never hand-edited

Nothing in this repository writes to a tracked place this map can see.

## Hand-authored

People write .github/, design/, docs/, modules/, presets/, the repository root and site/; 7 writes with paths built at run time may land here.

## Where to start

xrpl_lab/cli.py

Read those in order to follow one run of xrpl-lab end to end. This path follows xrpl-lab (a command people run, from pyproject.toml) from its entry, since CI runs only tests.

## What this map cannot see

- 1 import site could not be resolved.
- 7 writes and 20 reads use paths built at run time and are not named here.
- 5 reads go to the home directory (.xrpl-lab/) or a path their caller passes, not to this repository.
- 2 reads go to the directory the command is run in, not to this repository.
- Statistics confidence is low: fewer than 20 source files reach 10 revisions in the window.

Regenerate with `npx --yes @dogfood-lab/atlas map`.
