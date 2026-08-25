"""Wave 2 dashboard AMEND — F-d1deca46 (HIGH).

The run page auto-started a module run straight from a URL query param, and
its boolean parse failed OPEN to LIVE: line 119 was

    if (autoDryRun !== null) { setTimeout(() => startRun(autoDryRun === 'true'), 300); }

Since the live/dry choice was `autoDryRun === 'true'`, ANY value other than
the exact string 'true' — including 'false', an empty string, or a typo —
resolved to `startRun(false)`, i.e. a LIVE run. This was not hypothetical:
the module detail page's own PRIMARY "Run Module" button
(modules/[id].astro) constructed exactly that URL, `?dry_run=false`, so
clicking the app's main CTA — or reloading, sharing, or restoring that URL
from history — silently fired a live run with zero clicks and zero
confirmation.

The fix (contract in swarms/.../wave-2/dashboard.md, ADVISOR CONTRACTS):
"No auto-start on page load. A run begins because a human clicked — never
because a URL was opened, reloaded, restored from history, or shared." The
run page no longer reads the query string at all; a run only ever starts
from the two on-page buttons (Run / Dry Run), and the module page's primary
CTA no longer constructs a `?dry_run=` link.

These are static SOURCE-INSPECTION tests, not executed-browser tests: this
package ships no JS/TS test runner (no vitest/jest/playwright anywhere in
the repo — confirmed by search before writing this file), and `npm install`
is out of scope for a domain worktree (it can rewrite package-lock.json).
tests/test_schema_drift.py already establishes the precedent of asserting
invariants on site/src/**/*.ts|astro source from Python — this file follows
that same convention.

Each assertion below targets the actual CODE SHAPE of the hazard (a real
declaration, call, or href construction) rather than a bare substring —
otherwise this file's own explanatory comments, which necessarily quote the
old identifiers/URLs by name, would trip the checks they're supposed to
gate. Full-line `//` comments are additionally filtered out of the
call-site scan in TestRunPageNeverAutoStarts for the same reason.

Confirmed RED against the genuinely unfixed tree — reproduced with THIS
exact test file by temporarily stashing only the two fix files
(`git stash push -- site/src/pages/app/modules/[id].astro
site/src/pages/app/run/[id].astro`), running, then `git stash pop` to
restore the fix. Real output (`--tb=line`), all 4 failing as predicted:

    tests\\test_w2_dashboard_dryrun_autostart.py FFFF                         [100%]

    AssertionError: run/[id].astro constructs a URLSearchParams from the page URL [...]
      assert <re.Match object; span=(5709, 5729), match='new URLSearchParams('> is None

    AssertionError: run/[id].astro still declares `const autoDryRun = ...` [...]
      assert <re.Match object; span=(5758, 5776), match='const autoDryRun ='> is None

    AssertionError: startRun(...) invoked outside an explicit click handler:
    "      setTimeout(() => startRun(autoDryRun === 'true'), 300);". [...]

    AssertionError: modules/[id].astro still builds a `.../run/${esc(mod.id)}/?dry_run=...` link. [...]
      assert <re.Match object; span=(5485, 5513), match='run/${esc(mod.id)}/?dry_run='> is None

    4 failed in 0.02s

After restoring the fix (`git stash pop`), all 4 pass: `4 passed in 0.03s`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PAGE = REPO_ROOT / "site" / "src" / "pages" / "app" / "run" / "[id].astro"
MODULE_PAGE = REPO_ROOT / "site" / "src" / "pages" / "app" / "modules" / "[id].astro"


def _read(path: Path) -> str:
    assert path.exists(), f"expected source file at {path}"
    return path.read_text(encoding="utf-8")


class TestRunPageNeverAutoStarts:
    """F-d1deca46 — a run may only ever begin from an explicit button click."""

    def test_no_url_search_params_are_read_on_the_run_page(self) -> None:
        """The run page must not construct a URLSearchParams from the
        location at all. Before the fix it did — `new
        URLSearchParams(window.location.search)` — purely to auto-start a
        run 300ms after load. Once that's the only reason the page ever
        reads the query string, the strongest regression is simply: it
        doesn't construct one any more."""
        source = _read(RUN_PAGE)
        assert re.search(r"new\s+URLSearchParams\s*\(", source) is None, (
            "run/[id].astro constructs a URLSearchParams from the page URL — "
            "re-introducing a URL-driven code path risks re-introducing the "
            "F-d1deca46 auto-start-to-live bug. On the unfixed tree this "
            "failed because the script read `new URLSearchParams(window."
            "location.search)` to seed `autoDryRun`, consumed 300ms later "
            "by an un-gated setTimeout that called startRun()."
        )

    def test_no_fail_open_boolean_parse_survives(self) -> None:
        """Belt-and-suspenders: even if URL parsing is ever reintroduced for
        some other reason, the `autoDryRun` identifier and the fail-open
        `startRun(x === 'true')` comparison shape must never come back —
        per contract, anything not an explicit 'true' must resolve to dry,
        not live. Matches on real declarations/calls, not prose: this
        module's own docstring/comments quote the old identifier by name
        and must not trip this check."""
        source = _read(RUN_PAGE)
        assert re.search(r"\bconst\s+autoDryRun\s*=", source) is None, (
            "run/[id].astro still declares `const autoDryRun = ...` — the "
            "variable that fed the F-d1deca46 fail-open auto-start."
        )
        assert re.search(r"startRun\s*\(\s*autoDryRun\b", source) is None, (
            "run/[id].astro still passes autoDryRun into startRun(...)."
        )
        assert re.search(r"startRun\s*\(\s*\w+\s*===\s*['\"]true['\"]\s*\)", source) is None, (
            "found a startRun(x === 'true') style comparison — this is the "
            "exact fail-open shape of F-d1deca46: any value other than the "
            "literal string 'true' (including 'false', '', or a typo) "
            "resolves to a LIVE run."
        )

    def test_startrun_is_only_ever_invoked_from_an_explicit_click(self) -> None:
        """Every call to startRun( in the client script must sit on a line
        wiring a literal button click event — never inside a setTimeout or
        any other page-load-reachable path. This is the structural version
        of the contract: 'a run begins because a human clicked — never
        because a URL was opened, reloaded, restored from history, or
        shared.' Full-line `//` comments are excluded from the scan (this
        very file's fix comments say "startRun()" in prose)."""
        source = _read(RUN_PAGE)
        script_match = re.search(r"<script>(.*)</script>", source, re.S)
        assert script_match, "expected a client <script> block in run/[id].astro"
        script = script_match.group(1)

        code_lines = [line for line in script.splitlines() if not line.strip().startswith("//")]
        call_lines = [line for line in code_lines if re.search(r"\bstartRun\s*\(", line)]
        invocation_lines = [line for line in call_lines if "function startRun" not in line]
        assert invocation_lines, "expected at least the two button-wired startRun(...) calls"
        for line in invocation_lines:
            assert "addEventListener" in line and "'click'" in line, (
                f"startRun(...) invoked outside an explicit click handler: {line!r}. "
                "F-d1deca46 was exactly this shape: "
                "setTimeout(() => startRun(autoDryRun === 'true'), 300) fired "
                "on every page load/reload/history-restore with zero clicks."
            )

        # The precise original shape must never reappear anywhere in the
        # (comment-stripped) script.
        assert re.search(r"setTimeout\s*\(\s*\(\)\s*=>\s*startRun", "\n".join(code_lines)) is None, (
            "found a setTimeout(...) wrapping a startRun(...) call — this is "
            "the literal F-d1deca46 auto-start pattern."
        )


class TestModulePageStopsConstructingLiveAutostartUrl:
    """F-d1deca46 (module-detail side) — the module page's own PRIMARY CTA
    built the ?dry_run=false URL that, combined with the run page's
    auto-start, fired an unconfirmed live run on every click. Even with the
    run page fixed, the module page must not keep constructing this URL: a
    query param the destination page ignores is a stale, misleading
    contract, and a future edit could resurrect the auto-start behavior
    around it."""

    def test_primary_run_link_no_longer_carries_a_dry_run_query_param(self) -> None:
        source = _read(MODULE_PAGE)
        # Targets the actual href-construction code shape (not a bare
        # substring) so this module's own fix comment — which quotes the old
        # "(?dry_run=false)" URL by name for context — can't trip it.
        assert re.search(r"run/\$\{esc\(mod\.id\)\}/\?dry_run=", source) is None, (
            "modules/[id].astro still builds a `.../run/${esc(mod.id)}/"
            "?dry_run=...` link. On the unfixed tree this failed because the "
            "PRIMARY ('Run Module') button built exactly "
            "`.../run/${esc(mod.id)}/?dry_run=false` — the URL that, "
            "combined with the run page's auto-start, fired an unconfirmed "
            "LIVE run on every click."
        )
