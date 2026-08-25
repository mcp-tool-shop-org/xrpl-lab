"""Wave 6 dashboard Stage C — run-page stalled/reconnect/dry-run humanization.

F-13101734: dead ``txids`` accumulator must become load-bearing (completion
count fallback), not merely deleted as a lint tidy.

SEED-C-run-state: stalled, reconnect, and dry-run vs live must be obvious to
a learner — busy/loading, reconnect feedback, a11y live region, session state
that survives refresh when the server session still exists, and LabException
code/message/hint when the API/WS sends them.

F-cdf586bf (JS executable coverage) stays OPEN — deferred to the feature
pass. These are Python static SOURCE-INSPECTION pins (same convention as
tests/test_w2_dashboard_dryrun_autostart.py and
tests/test_w5_dashboard_dryrun_behavior.py). Do not stand up vitest.

Red-first: helpers reject known-bad fixtures in-process; live tree starts RED
until the run-page / api.ts humanization lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PAGE = REPO_ROOT / "site" / "src" / "pages" / "app" / "run" / "[id].astro"
API_TS = REPO_ROOT / "site" / "src" / "lib" / "api.ts"
DASHBOARD_CSS = REPO_ROOT / "site" / "src" / "styles" / "dashboard.css"

# Known-bad shapes (pre-Stage-C). Used only as fixtures to prove helpers can
# fail — not present after the fix lands.
_BAD_TXIDS_DEAD = """
let txids: string[] = [];
txids = [];
txids.push(msg.txid);
completionBanner.innerHTML = `${msg.txids?.length || 0} transaction(s)`;
"""

_BAD_NO_LAB_ERROR = """
case 'error': {
  termAppend(`[ERROR] ${msg.message || 'Unknown error'}`, 'text-red-400');
  announce(`Error: ${msg.message || 'Unknown error'}`);
  break;
}
"""

_BAD_NO_STALL_ANNOUNCE = """
function handleStalledConnection() {
  setStatus('stalled', 'Connection stalled');
  completionBanner.hidden = false;
}
"""

_BAD_NO_SESSION = """
async function startRun(dryRun: boolean) {
  activeRunId = result.run_id;
  connectWS();
}
loadModuleInfo();
"""

_BAD_START_MODULE_RUN = """
export async function startModuleRun(id: string, dryRun: boolean): Promise<RunResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/run/${id}?dry_run=${dryRun}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Run API returned ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<RunResult>;
}
"""


def _read(path: Path) -> str:
    assert path.exists(), f"expected source file at {path}"
    return path.read_text(encoding="utf-8")


def _script_body(astro_source: str) -> str:
    match = re.search(r"<script>(.*)</script>", astro_source, re.S)
    assert match, "expected a client <script> block"
    return match.group(1)


def _code_lines(script: str) -> list[str]:
    return [ln for ln in script.splitlines() if not ln.strip().startswith("//")]


def _strip_line_comments(script: str) -> str:
    return "\n".join(_code_lines(script))


# ── behavioral helpers ─────────────────────────────────────────────────────


def assert_txids_used_as_completion_fallback(script: str) -> None:
    """F-13101734 — local txids must feed the completion count as fallback."""
    code = _strip_line_comments(script)
    assert re.search(r"\btxids\b", code), "expected a local txids accumulator"
    # Must actually READ the accumulator in a completion-count expression,
    # not only push/reset it.
    fallback = re.search(
        r"msg\.txids\s*\?\.?\s*length\s*\?\?\s*txids\.length"
        r"|txids\.length\s*\?\?\s*msg\.txids"
        r"|\(msg\.txids\s*\?\.?\s*length\s*\|\|\s*txids\.length\)"
        r"|msg\.txids\s*\?\.?\s*length\s*\|\|\s*txids\.length",
        code,
    )
    assert fallback, (
        "txids accumulator is never read for the completion count — wire "
        "`msg.txids?.length ?? txids.length` (or equivalent) so the local "
        "array is a real fallback when the complete frame omits txids"
    )


def assert_dry_run_vs_live_mode_is_obvious(astro_source: str) -> None:
    """SEED-C — learner can see dry-run vs live without reading the terminal."""
    script = _strip_line_comments(_script_body(astro_source))
    html = astro_source.split("<script>")[0]
    has_mode_chip = (
        re.search(r'id=["\']run-mode(?:-chip)?["\']', html)
        or re.search(r'id=["\']run-mode(?:-chip)?["\']', script)
    )
    sets_mode = re.search(
        r"chip--dry|chip--live|setModeChip|run-mode|data-mode|DRY RUN|dry-run",
        script,
    )
    status_names_mode = re.search(
        r"Running.*dry|dry-run|DRY RUN|LIVE RUN|setStatus\([^\)]*(dry|live|DRY|LIVE)",
        script,
        re.I,
    )
    assert has_mode_chip or (sets_mode and status_names_mode), (
        "run page does not keep dry-run vs live obvious after start — need a "
        "visible mode chip and/or status copy that names the mode"
    )
    assert re.search(r"chip--dry", _read(DASHBOARD_CSS)), (
        "dashboard.css missing .chip--dry for dry-run mode affordance"
    )
    assert re.search(r"chip--live", _read(DASHBOARD_CSS)), (
        "dashboard.css missing .chip--live for live-mode affordance"
    )


def assert_busy_loading_affordances(script: str) -> None:
    """SEED-C — busy/loading must be marked for AT and sighted users."""
    code = _strip_line_comments(script)
    assert re.search(r"aria-busy", code), (
        "run page never sets aria-busy during a run — buttons/page must "
        "expose busy/loading state"
    )
    assert re.search(
        r"setAttribute\(\s*['\"]aria-busy['\"]\s*,\s*['\"]true['\"]\s*\)"
        r"|aria-busy\s*=\s*['\"]true['\"]"
        r"|\.setAttribute\(\s*[\"']aria-busy[\"']",
        code,
    ), "aria-busy is mentioned but never set to true"


def assert_stalled_announces_via_live_region(script: str) -> None:
    """SEED-C — stalled path must use the shared #announcer live region."""
    code = _strip_line_comments(script)
    # Find handleStalledConnection body (brace-matched).
    match = re.search(r"function\s+handleStalledConnection\s*\([^)]*\)\s*\{", code)
    assert match, "expected handleStalledConnection"
    start = match.end()
    depth = 1
    i = start
    while i < len(code) and depth:
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
        i += 1
    body = code[start : i - 1]
    assert re.search(r"\bannounce\s*\(", body), (
        "handleStalledConnection does not call announce() — stalled state "
        "must reach the #announcer live region (FEBCD-002)"
    )


def assert_reconnect_feedback_is_visible(script: str) -> None:
    """SEED-C — reconnect attempt updates status + announces + terminal state."""
    code = _strip_line_comments(script)
    assert re.search(
        r"setStatus\(\s*['\"]stalled['\"]\s*,\s*`Reconnecting",
        code,
    ) or re.search(
        r"setStatus\(\s*['\"]stalled['\"]\s*,\s*['\"]Reconnecting",
        code,
    ), "reconnect path must setStatus('stalled', 'Reconnecting…')"
    assert re.search(r"announce\(\s*`Connection dropped", code) or re.search(
        r"announce\(\s*['\"]Connection dropped", code
    ), "reconnect path must announce via the live region"
    assert re.search(
        r"setTermState\(\s*['\"]stalled['\"]\s*,\s*['\"]reconnecting['\"]\s*\)"
        r"|setTermState\(\s*['\"]stalled['\"]\s*,\s*`reconnecting",
        code,
    ), (
        "reconnect path must setTermState('stalled', 'reconnecting') so the "
        "terminal chrome matches the status pill"
    )


def assert_lab_exception_fields_surfaced(script: str, api_ts: str) -> None:
    """SEED-C — show LabException code/message/hint when the API/WS sends them."""
    code = _strip_line_comments(script)
    # WS error frame
    err_case = re.search(
        r"case\s+['\"]error['\"]\s*:\s*\{(.*?)break\s*;",
        code,
        re.S,
    )
    assert err_case, "expected WS case 'error' handler"
    err_body = err_case.group(1)
    assert re.search(r"msg\.code", err_body), (
        "WS error handler ignores msg.code — LabException code must be shown"
    )
    assert re.search(r"msg\.hint", err_body), (
        "WS error handler ignores msg.hint — LabException hint must be shown"
    )
    # HTTP start path must attach structured fields from the envelope
    assert re.search(r"detail\s*\?\.?\s*code|\.code\b", api_ts), (
        "startModuleRun must parse structured detail.code from error bodies"
    )
    assert re.search(r"detail\s*\?\.?\s*hint|\.hint\b", api_ts), (
        "startModuleRun must parse structured detail.hint from error bodies"
    )
    assert re.search(
        r"err\.(?:code|hint|labMessage)|formatLabError|labMessage",
        code,
    ), "startRun catch must surface structured LabException fields from the thrown error"


def assert_session_survives_refresh(script: str) -> None:
    """SEED-C — active run_id persists and reconnects without starting a new run."""
    code = _strip_line_comments(script)
    assert re.search(r"sessionStorage", code), (
        "run page never touches sessionStorage — cannot restore an in-flight "
        "run after refresh"
    )
    assert re.search(r"sessionStorage\.setItem", code), (
        "must persist run session (run_id + dry_run) when a run starts"
    )
    assert re.search(r"sessionStorage\.(?:getItem|removeItem)", code), (
        "must read/clear the persisted run session on load / terminal states"
    )
    # Restore must reconnect, not call startRun / startModuleRun
    assert re.search(r"tryRestore|restoreSession|resumeRun|reconnect.*session", code, re.I) or (
        re.search(r"sessionStorage\.getItem", code) and re.search(r"fetchRun", code)
    ), "expected a restore path that checks the persisted session via fetchRun"
    assert re.search(r"\bfetchRun\b", code), (
        "restore path must call fetchRun to confirm the server session still exists"
    )
    # Ensure restore does not invoke startModuleRun (would mint a new run)
    # Rough: startModuleRun should only appear inside startRun (w5 already pins
    # this); additionally forbid startRun( from restore helper names.
    restore_fn = re.search(
        r"function\s+(tryRestore\w*|restoreSession\w*|resumeRun\w*)\s*\([^)]*\)\s*\{",
        code,
    )
    if restore_fn:
        start = restore_fn.end()
        depth = 1
        i = start
        while i < len(code) and depth:
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
            i += 1
        body = code[start : i - 1]
        assert re.search(r"\bstartRun\s*\(", body) is None, (
            "restore helper must not call startRun — that would mint a new run"
        )
        assert re.search(r"\bstartModuleRun\s*\(", body) is None, (
            "restore helper must not call startModuleRun"
        )
        assert re.search(r"\bconnectWS\s*\(", body), (
            "restore helper must reconnect via connectWS to the existing run_id"
        )


# ── RED proof against known-bad fixtures ───────────────────────────────────


class TestHelpersRejectKnownBadShapes:
    def test_txids_fallback_helper_rejects_dead_accumulator(self) -> None:
        with pytest.raises(AssertionError, match="never read"):
            assert_txids_used_as_completion_fallback(_BAD_TXIDS_DEAD)

    def test_lab_exception_helper_rejects_message_only_error(self) -> None:
        with pytest.raises(AssertionError, match="msg\\.code"):
            assert_lab_exception_fields_surfaced(_BAD_NO_LAB_ERROR, _BAD_START_MODULE_RUN)

    def test_stalled_announce_helper_rejects_silent_stall(self) -> None:
        with pytest.raises(AssertionError, match="announce"):
            assert_stalled_announces_via_live_region(_BAD_NO_STALL_ANNOUNCE)

    def test_session_helper_rejects_no_persist(self) -> None:
        with pytest.raises(AssertionError, match="sessionStorage"):
            assert_session_survives_refresh(_BAD_NO_SESSION)


# ── GREEN against the live tree (RED until Stage C lands) ──────────────────


class TestLiveRunPageStageCHumanization:
    def test_txids_used_as_completion_fallback(self) -> None:
        assert_txids_used_as_completion_fallback(_script_body(_read(RUN_PAGE)))

    def test_dry_run_vs_live_mode_is_obvious(self) -> None:
        assert_dry_run_vs_live_mode_is_obvious(_read(RUN_PAGE))

    def test_busy_loading_affordances(self) -> None:
        assert_busy_loading_affordances(_script_body(_read(RUN_PAGE)))

    def test_stalled_announces_via_live_region(self) -> None:
        assert_stalled_announces_via_live_region(_script_body(_read(RUN_PAGE)))

    def test_reconnect_feedback_is_visible(self) -> None:
        assert_reconnect_feedback_is_visible(_script_body(_read(RUN_PAGE)))

    def test_lab_exception_fields_surfaced(self) -> None:
        assert_lab_exception_fields_surfaced(
            _script_body(_read(RUN_PAGE)), _read(API_TS)
        )

    def test_session_survives_refresh(self) -> None:
        assert_session_survives_refresh(_script_body(_read(RUN_PAGE)))
