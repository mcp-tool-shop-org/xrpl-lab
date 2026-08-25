"""Wave 5 dashboard Stage B — pin no-auto-start + fail-closed dry_run BEHAVIOR.

F-cdf586bf (JS executable coverage) stays OPEN this wave — deferred to the
feature pass; this file is NOT that coverage. It only tightens the existing
Python static gate so it pins *behavior* (a run starts only from an explicit
click; LIVE is never the default of a URL boolean parse) rather than a bare
source substring that a differently-shaped auto-start could sail past.

Contract (wave-2 / wave-5 advisor locks, still in force):
- No auto-start on page load. A run begins because a human clicked.
- dry_run=false may mean live from an explicit click, never from URL auto-start.
- Fail-closed: a `startRun(x === 'true')` URL parse must never return — that
  shape fails OPEN to LIVE for every non-'true' value.

Helpers below operate on source strings so the known-bad F-d1deca46 shape can
be proven RED in-process (fixture) without mutating the live tree, while the
live pages are asserted green against the same helpers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PAGE = REPO_ROOT / "site" / "src" / "pages" / "app" / "run" / "[id].astro"
MODULE_PAGE = REPO_ROOT / "site" / "src" / "pages" / "app" / "modules" / "[id].astro"

# Known-bad shape from F-d1deca46 (pre-fix). Used only as a fixture to prove
# the helpers go RED — not present in the live tree.
_BAD_AUTOSTART_SCRIPT = """
const urlParams = new URLSearchParams(window.location.search);
const autoDryRun = urlParams.get('dry_run');
async function startRun(dryRun) {
  await startModuleRun(moduleId, dryRun);
}
btnRun.addEventListener('click', () => startRun(false));
btnDry.addEventListener('click', () => startRun(true));
if (autoDryRun !== null) {
  setTimeout(() => startRun(autoDryRun === 'true'), 300);
}
"""

_BAD_MODULE_HREF = (
    '<a class="btn btn--primary" '
    'href="/xrpl-lab/app/run/${esc(mod.id)}/?dry_run=false">Run Module</a>'
)


def _read(path: Path) -> str:
    assert path.exists(), f"expected source file at {path}"
    return path.read_text(encoding="utf-8")


def _script_body(astro_source: str) -> str:
    match = re.search(r"<script>(.*)</script>", astro_source, re.S)
    assert match, "expected a client <script> block"
    return match.group(1)


def _code_lines(script: str) -> list[str]:
    """Drop full-line // comments so prose about the old bug cannot trip pins."""
    return [ln for ln in script.splitlines() if not ln.strip().startswith("//")]


def _strip_line_comments(script: str) -> str:
    return "\n".join(_code_lines(script))


# ── behavioral helpers (assert_* raise AssertionError on the bad shape) ─────


def assert_no_url_driven_run_start(script: str) -> None:
    """A run must not be keyed off the page URL / query string.

    Pins the *behavior* (URL → start), not the old identifier `autoDryRun`.
    Catches URLSearchParams, location.search, and searchParams.get('dry_run')
    even if renamed.
    """
    code = _strip_line_comments(script)
    offenders: list[str] = []
    if re.search(r"new\s+URLSearchParams\s*\(", code):
        offenders.append("URLSearchParams construction")
    if re.search(r"\blocation\.search\b", code):
        offenders.append("location.search read")
    if re.search(r"searchParams\.get\s*\(\s*['\"]dry_run['\"]\s*\)", code):
        offenders.append("searchParams.get('dry_run')")
    if re.search(r"\.get\s*\(\s*['\"]dry_run['\"]\s*\)", code) and re.search(
        r"URLSearchParams|location\.search|searchParams", code
    ):
        offenders.append("query get('dry_run') paired with URL parsing")
    assert not offenders, (
        "run page still has a URL-driven run-start path: "
        + ", ".join(offenders)
        + ". Contract: a run begins from an explicit click, never from a URL."
    )


def assert_fail_closed_dry_run_parse_absent(script: str) -> None:
    """The fail-OPEN shape `startRun(x === 'true')` must never appear.

    That comparison makes every non-'true' value (including 'false', '', typo)
    a LIVE run — the F-d1deca46 hazard. Pin the absence of that boolean shape
    regardless of the left-hand identifier name.
    """
    code = _strip_line_comments(script)
    bad = re.search(
        r"startRun\s*\(\s*\w+\s*===\s*['\"]true['\"]\s*\)",
        code,
    )
    assert bad is None, (
        "found fail-open dry_run parse feeding startRun: "
        f"{bad.group(0)!r}. LIVE must never be the default of a URL boolean."
    )


def assert_no_deferred_or_lifecycle_startrun(script: str) -> None:
    """startRun must not be reached from timers or page-load lifecycle hooks."""
    code = _strip_line_comments(script)
    deferred = r"\s*\(\s*\(?\s*(?:async\s*)?\(?\s*\)?\s*=>\s*startRun"
    patterns = [
        (rf"setTimeout{deferred}", "setTimeout → startRun"),
        (rf"setInterval{deferred}", "setInterval → startRun"),
        (
            r"addEventListener\s*\(\s*['\"](?:DOMContentLoaded|load|astro:page-load)['\"]"
            r"[^)]*startRun",
            "page-load listener → startRun",
        ),
        (rf"requestAnimationFrame{deferred}", "rAF → startRun"),
    ]
    hits = [label for pat, label in patterns if re.search(pat, code, re.S)]
    assert not hits, (
        "startRun reachable without an explicit button click via: "
        + ", ".join(hits)
    )


def assert_startrun_invocations_are_click_wired(script: str) -> None:
    """Every startRun(...) call site (not the definition) is a click wire.

    Requires BOTH an addEventListener('click') context on the same statement
    AND an explicit boolean literal (true/false) — so a renamed auto-start
    that calls startRun(someVar) from a click handler still fails the pin
    unless it is one of the two intentional Run / Dry Run buttons.
    """
    code_lines = _code_lines(script)
    invocations = [
        ln
        for ln in code_lines
        if re.search(r"\bstartRun\s*\(", ln) and "function startRun" not in ln
    ]
    assert invocations, "expected btnRun/btnDry startRun(...) call sites"
    for line in invocations:
        assert "addEventListener" in line and "'click'" in line, (
            f"startRun(...) not on an explicit click handler: {line!r}"
        )
        assert re.search(r"startRun\s*\(\s*(true|false)\s*\)", line), (
            f"startRun(...) must pass an explicit boolean literal from a "
            f"click handler (fail-closed at the call site): {line!r}"
        )


def assert_startmodulerun_only_inside_startrun(script: str) -> None:
    """startModuleRun (the API call that actually starts a run) lives only
    inside startRun — so a future page-load path cannot bypass the click gate
    by calling the API directly.
    """
    code = _strip_line_comments(script)
    # Rough function-body window: from `async function startRun` / `function startRun`
    # to the next top-level `function` / end.
    match = re.search(
        r"(?:async\s+)?function\s+startRun\s*\([^)]*\)\s*\{",
        code,
    )
    assert match, "expected a startRun function definition"
    start = match.end()
    # Brace match from the opening `{` of startRun.
    depth = 1
    i = start
    while i < len(code) and depth:
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
        i += 1
    body = code[start : i - 1]
    outside = code[: match.start()] + code[i:]
    assert re.search(r"\bstartModuleRun\s*\(", body), (
        "startRun must call startModuleRun (the API entry that starts a run)"
    )
    assert re.search(r"\bstartModuleRun\s*\(", outside) is None, (
        "startModuleRun called outside startRun — a page-load path could "
        "bypass the click-only gate"
    )


def assert_module_primary_cta_has_no_dry_run_query(module_source: str) -> None:
    """Module detail primary CTA must navigate to the run page with no dry_run=."""
    # Live construction shape (template literal href).
    assert re.search(r"run/\$\{esc\(mod\.id\)\}/\?dry_run=", module_source) is None, (
        "modules/[id].astro still builds a dry_run= query on the run link"
    )
    # Also reject any primary-button href that carries dry_run= of either value.
    for m in re.finditer(
        r'class="btn btn--primary"[^>]*href="([^"]+)"',
        module_source,
    ):
        href = m.group(1)
        assert "dry_run=" not in href, (
            f"primary CTA still carries dry_run in href: {href!r}"
        )


# ── RED proof against the known-bad fixture (helpers must be able to fail) ──


class TestHelpersRejectKnownBadAutostartShape:
    """Red-first: the same helpers that gate the live tree must reject the
    historical F-d1deca46 shape. If a helper goes green on this fixture, the
    pin is vacuous."""

    def test_url_driven_start_helper_rejects_bad_script(self) -> None:
        with pytest.raises(AssertionError, match="URL-driven"):
            assert_no_url_driven_run_start(_BAD_AUTOSTART_SCRIPT)

    def test_fail_open_parse_helper_rejects_bad_script(self) -> None:
        with pytest.raises(AssertionError, match="fail-open"):
            assert_fail_closed_dry_run_parse_absent(_BAD_AUTOSTART_SCRIPT)

    def test_deferred_start_helper_rejects_bad_script(self) -> None:
        with pytest.raises(AssertionError, match="setTimeout"):
            assert_no_deferred_or_lifecycle_startrun(_BAD_AUTOSTART_SCRIPT)

    def test_click_wire_helper_rejects_autostart_invocation(self) -> None:
        with pytest.raises(AssertionError, match="explicit click handler"):
            assert_startrun_invocations_are_click_wired(_BAD_AUTOSTART_SCRIPT)

    def test_module_cta_helper_rejects_dry_run_false_href(self) -> None:
        with pytest.raises(AssertionError, match="dry_run"):
            assert_module_primary_cta_has_no_dry_run_query(_BAD_MODULE_HREF)


# ── GREEN against the live fixed pages ─────────────────────────────────────


class TestLiveRunPagePinsBehavior:
    def test_no_url_driven_run_start(self) -> None:
        assert_no_url_driven_run_start(_script_body(_read(RUN_PAGE)))

    def test_fail_closed_dry_run_parse_absent(self) -> None:
        assert_fail_closed_dry_run_parse_absent(_script_body(_read(RUN_PAGE)))

    def test_no_deferred_or_lifecycle_startrun(self) -> None:
        assert_no_deferred_or_lifecycle_startrun(_script_body(_read(RUN_PAGE)))

    def test_startrun_invocations_are_click_wired_with_explicit_bools(self) -> None:
        assert_startrun_invocations_are_click_wired(_script_body(_read(RUN_PAGE)))

    def test_startmodulerun_only_inside_startrun(self) -> None:
        assert_startmodulerun_only_inside_startrun(_script_body(_read(RUN_PAGE)))

    def test_both_live_and_dry_click_paths_exist(self) -> None:
        """Behavior pin: the page exposes BOTH an explicit LIVE click and an
        explicit DRY click — dry_run=false live is allowed from a human click,
        never from URL auto-start."""
        script = _strip_line_comments(_script_body(_read(RUN_PAGE)))
        assert re.search(
            r"addEventListener\s*\(\s*'click'\s*,\s*\(\)\s*=>\s*startRun\s*\(\s*false\s*\)",
            script,
        ), "missing explicit LIVE click → startRun(false)"
        assert re.search(
            r"addEventListener\s*\(\s*'click'\s*,\s*\(\)\s*=>\s*startRun\s*\(\s*true\s*\)",
            script,
        ), "missing explicit DRY click → startRun(true)"


class TestLiveModulePagePinsBehavior:
    def test_primary_cta_has_no_dry_run_query(self) -> None:
        assert_module_primary_cta_has_no_dry_run_query(_read(MODULE_PAGE))
