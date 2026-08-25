"""Re-swarm 4 (Wave 2 AMEND) API regression tests.

Covers the HIGH/MEDIUM/LOW findings assigned to the api-domain AMEND agent
(``xrpl_lab/api/**``, ``xrpl_lab/server.py``):

* **F-717654d7 (HIGH)** — the WS ``{"type": "output"}`` channel forwarded
  captured console text verbatim with zero sanitization, unlike the
  ``{"type": "error"}`` channel (always routed through ``_error_envelope``).
  A non-LabException step failure's ``str(exc)`` can embed absolute
  filesystem paths (and, via them, the OS username). ``_QueueFile.write()``
  now redacts path-shaped substrings before queuing.

* **F-6beae9bb (MEDIUM)** — ``list_reports()`` / ``get_report()`` called
  ``read_text()`` with no try/except, and no exception handler was
  registered anywhere in the app, so one bad report file 500'd the WHOLE
  listing with a non-conforming body. Both are now guarded; a global
  catch-all handler was added to ``server.py`` so any future unguarded
  route degrades gracefully too.

* **F-9936b28c (MEDIUM)** — ``start_run``'s "was dry_run explicitly
  passed?" detection substring-searched the raw query string, so e.g.
  ``?note=dry_run_test`` false-positived as "explicitly passed" and
  silently skipped the server-wide ``--dry-run`` safety default. Now
  checks parsed query param KEYS, not raw-string substrings.

* **F-67805cb0 (MEDIUM)** — ``run_websocket()`` had no guard against two
  concurrent WS clients attaching to the same ``run_id``, racing the
  single per-session queue. A second concurrent attach is now rejected
  (close code 4008).

* **F-bddfe64b (LOW)** — ``load_all_modules()`` ran synchronously inside
  ``start_run``, an ``async def`` HTTP route handler, blocking the event
  loop for the duration of the disk I/O + parsing. It now offloads via
  ``asyncio.to_thread``. ``_run_module_task``'s OWN call site is
  deliberately left synchronous: offloading it too was tried and reverted
  after it was found to orphan the fire-and-forget background task under
  ``TestClient(app)`` used WITHOUT the ``with`` context-manager form (a
  convention many pre-existing tests use) — that per-request anyio portal
  tears down before the cross-thread round trip completes, so the run's
  'complete' frame is silently never sent. See the comment on that call
  site in ``runner_ws.py`` for the full root-cause note.

Also RE-VERIFIES (no code change needed — already correct) two properties
called out in the domain guidance:

* The WS Origin allow-list is an exact-match membership check, not
  vulnerable to a missing/empty/case-mismatched/substring bypass.
* The bounded back-pressure queue (``_safe_put`` / ``_QUEUE_MAXSIZE``) is
  already covered exhaustively by ``tests/test_ws_backpressure.py`` — not
  duplicated here.

Run in isolation:

    python -m pytest tests/test_reswarm4_api.py -q
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.api.runner_ws import (
    _ALLOWED_ORIGINS,
    _make_capture_console,
    _redact_output_text,
)
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app

# Default Origin header for WS test fixtures — mirrors test_runner_ws.py.
_TEST_ORIGIN = {"origin": _ALLOWED_ORIGINS[0]}

# Sentinel absolute paths — mirrors the sentinel-channel discipline in
# tests/test_runner_ws.py (_SENTINEL_PATH) / tests/test_reporting.py: pin
# the VALUE channel, not just key/shape, so a leak into an existing field
# is caught rather than vacuously passing.
_SENTINEL_WIN_PATH = r"C:\Users\mikey\.xrpl-lab\state.json"
_SENTINEL_POSIX_PATH = "/home/facilitator/.xrpl-lab/state.json"


def _make_simple_module(mod_id: str = "receipt_literacy") -> ModuleDef:
    """A module with a single ensure_wallet step (no input/submit)."""
    return ModuleDef(
        id=mod_id,
        title="Test Module",
        time="5 min",
        level="beginner",
        requires=[],
        produces=["wallet"],
        checks=["wallet ok"],
        steps=[ModuleStep(text="Intro text", action="ensure_wallet", action_args={})],
        raw_body="",
    )


def _poll_until(predicate, timeout: float = 2.0, interval: float = 0.05) -> bool:
    """Poll ``predicate`` until it is truthy or ``timeout`` elapses.

    Several server-side state transitions here (WS 'finally' blocks
    running after the client-side context manager exits) are eventually
    consistent, not synchronous — mirrors the poll idiom already used by
    tests/test_runner_ws.py::test_ws_client_disconnect_mid_run_triggers_cleanup.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture()
def _clear_sessions():
    """Snapshot and restore ``runner_ws._sessions`` around each test.

    The session dict is module-level global state shared across every test
    file in the process; without this, sessions created here (or leaked
    from another file's tests) pollute lookups keyed by run_id.
    """
    from xrpl_lab.api import runner_ws

    snapshot = dict(runner_ws._sessions)
    runner_ws._sessions.clear()
    yield
    runner_ws._sessions.clear()
    runner_ws._sessions.update(snapshot)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with state/workspace redirected to tmp_path, no modules mocked."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)
    return TestClient(create_app())


@pytest.fixture()
def client_with_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with a mocked single module, dry_run default at the app level."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
    monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

    return TestClient(create_app())


# ── F-717654d7 — output-channel redaction (HIGH) ──────────────────────


class TestOutputChannelRedaction:
    """``_redact_output_text`` / ``_QueueFile.write()`` must strip
    absolute-path substrings from captured console text before it is
    queued as an ``{"type": "output"}`` WS frame — the defense-in-depth
    layer this agent owns (runner.py's console.print() call site is
    tightened separately/independently)."""

    # -- pure string-function unit tests -------------------------------

    def test_redacts_quoted_windows_path(self) -> None:
        text = (
            "Step failed: OSError: [Errno 2] No such file or directory: "
            f"'{_SENTINEL_WIN_PATH}'"
        )
        redacted = _redact_output_text(text)
        assert _SENTINEL_WIN_PATH not in redacted
        assert "<path-redacted>" in redacted
        assert "mikey" not in redacted

    def test_redacts_quoted_path_in_traceback_style_line(self) -> None:
        text = f'File "{_SENTINEL_WIN_PATH}", line 321, in run_module'
        redacted = _redact_output_text(text)
        assert _SENTINEL_WIN_PATH not in redacted

    def test_redacts_bare_posix_path(self) -> None:
        text = f"saved to {_SENTINEL_POSIX_PATH} for user"
        redacted = _redact_output_text(text)
        assert _SENTINEL_POSIX_PATH not in redacted
        assert "facilitator" not in redacted

    def test_redacts_bare_windows_forward_slash_path(self) -> None:
        # This rig's own path convention (E:/AI/xrpl-lab/...) — forward
        # slashes after a drive letter must also be caught.
        text = "state written to E:/AI/xrpl-lab/workspace/state.json"
        redacted = _redact_output_text(text)
        assert "E:/AI/xrpl-lab" not in redacted

    def test_redacts_unc_path(self) -> None:
        text = r"UNC share: \\myserver\share\file.txt unreachable"
        redacted = _redact_output_text(text)
        assert "myserver" not in redacted

    def test_does_not_mangle_urls(self) -> None:
        # Regression guard for the false-positive this redaction must NOT
        # introduce: a testnet explorer/faucet URL is legitimate
        # pedagogical content (the whole point of the console output) and
        # must survive untouched. Without the token-boundary lookbehind,
        # the trailing "p" of "http" followed by ":" and "/" has the same
        # shape as a Windows drive letter ("C:\\") and would be mistaken
        # for one.
        text = (
            "Explorer: https://testnet.xrpl.org/transactions/ABCDEF01 "
            "Faucet: https://faucet.altnet.rippletest.net/accounts"
        )
        assert _redact_output_text(text) == text

    def test_does_not_mangle_url_path_segment_matching_a_redacted_dirname(
        self,
    ) -> None:
        # A URL path segment that happens to be spelled like one of our
        # POSIX top-level directory names ("/etc/") must not be redacted —
        # it is glued onto the preceding hostname/path with no token
        # boundary, unlike a genuine standalone absolute path.
        text = "See https://testnet.xrpl.org/etc/foo for details"
        assert _redact_output_text(text) == text

    def test_does_not_mangle_plain_prose_with_quotes(self) -> None:
        text = "[yellow]Hint: Run 'xrpl-lab doctor' to diagnose the issue.[/]"
        assert _redact_output_text(text) == text

    def test_does_not_mangle_prose_containing_etc_as_a_word(self) -> None:
        text = "module note: etc. and so on, nothing here"
        assert _redact_output_text(text) == text

    def test_does_not_touch_non_path_content_like_a_wallet_seed(self) -> None:
        # Seeds are a SEPARATE concern already handled by runtime._SecretValue
        # (__repr__/__str__ return '***'); this redaction is path-shaped-text
        # only and must not accidentally mangle unrelated sentinel content.
        text = "wallet seed sEdSENTINEL_DO_NOT_LEAK stays untouched"
        assert _redact_output_text(text) == text

    # -- integration: through the actual _QueueFile / Console plumbing --

    def test_queue_file_write_redacts_before_queuing(self) -> None:
        """Drives ``_QueueFile.write()`` directly (the exact method
        ``F-717654d7`` names) and confirms the queued frame is clean."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        async def _drive() -> list[dict]:
            loop = asyncio.get_running_loop()
            console = _make_capture_console(queue, loop, "test-run")
            console.file.write(
                "Step failed: OSError: [Errno 13] Permission denied: "
                f"'{_SENTINEL_WIN_PATH}'\n"
            )
            # call_soon_threadsafe schedules on the next loop iteration;
            # yield once so the scheduled _safe_put actually runs before
            # we drain.
            await asyncio.sleep(0)
            drained = []
            while not queue.empty():
                drained.append(queue.get_nowait())
            return drained

        drained = asyncio.run(_drive())
        output_frames = [d for d in drained if d.get("type") == "output"]
        assert output_frames, "expected at least one output frame"
        for frame in output_frames:
            assert _SENTINEL_WIN_PATH not in frame["text"], (
                f"raw sentinel path leaked into output frame: {frame!r}"
            )

    def test_simulated_non_lab_exception_step_failure_does_not_leak_path(
        self,
    ) -> None:
        """The scenario named in the finding: a step handler raises a bare
        (non-LabException) exception whose ``str(exc)`` embeds a
        filesystem path — mirrors runner.py's per-step exception handler
        printing ``f"{type(exc).__name__}: {exc}"`` for that branch.
        Confirms the WS-frame-side redaction independently defends this
        channel even if the upstream print is not (yet, or ever)
        tightened — this is the defense-in-depth layer this agent owns.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        async def _drive() -> list[dict]:
            loop = asyncio.get_running_loop()
            console = _make_capture_console(queue, loop, "test-run")
            exc = OSError(f"[Errno 13] Permission denied: '{_SENTINEL_WIN_PATH}'")
            # Mirrors runner.py's non-LabException console.print() call
            # verbatim: f"[red]Step failed:[/] {type(exc).__name__}: {exc}"
            console.print(f"[red]Step failed:[/] {type(exc).__name__}: {exc}")
            await asyncio.sleep(0)
            drained = []
            while not queue.empty():
                drained.append(queue.get_nowait())
            return drained

        drained = asyncio.run(_drive())
        output_frames = [d for d in drained if d.get("type") == "output"]
        assert output_frames, "expected at least one output frame"
        for frame in output_frames:
            assert _SENTINEL_WIN_PATH not in frame["text"], (
                f"raw sentinel path leaked into output frame: {frame!r}"
            )
            assert "mikey" not in frame["text"], (
                "OS username embedded in the redacted path must not survive"
            )
            # The exception TYPE name is safe/expected content, not a leak.
            assert "OSError" in frame["text"]


# ── F-6beae9bb — read_text() guards + catch-all exception handler ────


class TestReportsReadGuard:
    """``list_reports()`` / ``get_report()`` must not let a single
    unreadable report file crash the whole endpoint with a non-conforming
    500 body."""

    def test_list_reports_skips_unreadable_file_keeps_others(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        reports_dir = tmp_path / "ws" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "good_one.md").write_text("# Good Report\ncontent", encoding="utf-8")
        # Invalid UTF-8 bytes — read_text(encoding="utf-8") raises UnicodeDecodeError.
        (reports_dir / "bad_encoding.md").write_bytes(b"\xff\xfe\x00bad")
        (reports_dir / "another_good.md").write_text(
            "# Another\nmore content", encoding="utf-8"
        )

        resp = client.get("/api/artifacts/reports")
        assert resp.status_code == 200, (
            "one bad-encoding file must not take down the whole listing"
        )
        data = resp.json()
        titles = {r["title"] for r in data}
        assert "Good One" in titles
        assert "Another Good" in titles
        # The bad file is skipped — not present, and (crucially) does not
        # take down the other two reports.
        assert len(data) == 2

    def test_get_report_unreadable_file_returns_structured_500(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        reports_dir = tmp_path / "ws" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "broken.md").write_bytes(b"\xff\xfe\x00bad")

        resp = client.get("/api/artifacts/reports/broken")
        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert detail["code"] == "REPORT_UNREADABLE"
        assert "message" in detail and detail["message"]
        assert "hint" in detail and detail["hint"]

    def test_get_report_still_404s_for_missing_report(
        self, client: TestClient
    ) -> None:
        # Regression guard: the new try/except must not swallow the
        # pre-existing 404 path for a report that simply doesn't exist.
        resp = client.get("/api/artifacts/reports/does-not-exist")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "REPORT_NOT_FOUND"

    def test_get_report_still_returns_good_content_normally(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        # Regression guard: the guard must not affect the happy path.
        reports_dir = tmp_path / "ws" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "fine.md").write_text("# All good\ncontent here", encoding="utf-8")

        resp = client.get("/api/artifacts/reports/fine")
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == "fine"
        assert "All good" in data["content"]


class TestGlobalExceptionHandler:
    """F-6beae9bb's second half: a catch-all handler in ``server.py`` so
    ANY unguarded route degrades to the structured envelope shape instead
    of Starlette's bare-string default 500 body."""

    def test_unhandled_exception_returns_structured_500_envelope(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        def _boom():
            raise RuntimeError(f"unexpected boom at {_SENTINEL_POSIX_PATH}")

        monkeypatch.setattr("xrpl_lab.api.routes.load_state", _boom)

        app = create_app()
        # raise_server_exceptions=False so the TestClient returns the
        # actual HTTP response instead of re-raising for debug purposes —
        # this is how Starlette's OWN test suite exercises ServerErrorMiddleware.
        boom_client = TestClient(app, raise_server_exceptions=False)

        resp = boom_client.get("/api/status")
        assert resp.status_code == 500
        body = resp.json()
        assert isinstance(body["detail"], dict), (
            "detail must be an OBJECT (matching every HTTPException path "
            "in this API), not Starlette's default bare string — the "
            "dashboard's body?.detail?.message extraction assumes an object"
        )
        assert body["detail"]["code"] == "RUNTIME_INTERNAL"
        assert "message" in body["detail"] and body["detail"]["message"]
        assert "hint" in body["detail"] and body["detail"]["hint"]
        # The raw exception text (which embeds our sentinel path) must
        # never reach the client — only the server log gets full detail.
        assert _SENTINEL_POSIX_PATH not in resp.text

    def test_http_exceptions_are_unaffected_by_catch_all_handler(
        self, client: TestClient
    ) -> None:
        """Registering a bare-Exception handler must not shadow the
        existing structured HTTPException responses raised explicitly
        throughout this API."""
        resp = client.get("/api/modules/nonexistent-module-id")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "MODULE_NOT_FOUND"


# ── F-9936b28c — dry_run substring false-positive ─────────────────────


@pytest.mark.usefixtures("_clear_sessions")
class TestDryRunSubstringFalsePositive:
    """An unrelated query key/value merely CONTAINING the substring
    'dry_run' must NOT be mistaken for the caller explicitly passing
    ``?dry_run=...`` — that used to silently skip the server-wide
    ``--dry-run`` safety default and let the run execute live."""

    def test_unrelated_param_containing_substring_does_not_suppress_default(
        self, client_with_module: TestClient
    ) -> None:
        # App-level default here is dry_run=False (create_app() default);
        # flip the scenario by asserting the OTHER direction is honoured:
        # a substring match must not cause a FALSE "explicitly passed"
        # verdict. We prove this precisely by using an app-level default of
        # True and confirming a query merely containing the substring
        # still resolves to True (the fallback fires because the real key
        # is absent) rather than silently becoming False.
        from xrpl_lab.api import runner_ws

        # Rebuild a client with dry_run=True at the app level for this
        # specific assertion (module fixture already patched load_all_modules).
        app = create_app(dry_run=True)
        true_default_client = TestClient(app)

        resp = true_default_client.post(
            "/api/run/receipt_literacy?note=dry_run_test"
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        session = runner_ws._sessions[run_id]
        assert session.dry_run is True, (
            "a query param merely containing the substring 'dry_run' "
            "(here: '?note=dry_run_test') must not suppress the "
            "app-level --dry-run default — the real 'dry_run' key was "
            "never present"
        )

    def test_explicit_dry_run_true_query_key_overrides_false_default(
        self, client_with_module: TestClient
    ) -> None:
        # App-level default is False (create_app() default in the fixture).
        # An explicit ?dry_run=true must still win — confirms the fix
        # didn't break the legitimate override path.
        resp = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        from xrpl_lab.api import runner_ws

        session = runner_ws._sessions[run_id]
        assert session.dry_run is True

    def test_explicit_dry_run_false_still_overrides_true_default(
        self, client_with_module: TestClient
    ) -> None:
        from xrpl_lab.api import runner_ws

        app = create_app(dry_run=True)
        # Re-patch load_all_modules against the NEW app's module (module
        # patch target is the shared runner_ws module, app instance doesn't
        # matter for this monkeypatch — already applied by the fixture).
        true_default_client = TestClient(app)

        resp = true_default_client.post("/api/run/receipt_literacy?dry_run=false")
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        session = runner_ws._sessions[run_id]
        assert session.dry_run is False, (
            "an explicit ?dry_run=false must override a True app-level default"
        )

    def test_dash_spelled_key_is_treated_as_dry_run_alias(
        self, client_with_module: TestClient
    ) -> None:
        # F-ab18b053 (wave-2 AMEND): this test used to assert the BROKEN
        # terminal behaviour. The FastAPI route parameter is literally
        # named `dry_run` (underscore, no Query alias) — ONLY that exact
        # key ever binds to it. The OLD code treated mere PRESENCE of the
        # unbound "dry-run" (hyphen) key as proof the caller "explicitly
        # specified a value" and used THAT to skip the app.state.dry_run
        # fallback — but the key's VALUE never reached anywhere, so its
        # presence could only ever produce a FALSE "explicit" signal. Net
        # effect: an operator-configured True --dry-run safety default was
        # silently defeated by a caller who spelled the flag the same way
        # the CLI does (--dry-run) — reopening the exact hole F-9936b28c
        # fixed, via key-spelling instead of substring-matching.
        #
        # Fixed: the hyphen key is now read explicitly and folded in as an
        # alias of `dry_run` (or the request is rejected with 400) — see
        # tests/test_w2_api_cli_dry_run.py for the full regression suite,
        # including the dangerous True-default-defeated case this test
        # used to get wrong.
        from xrpl_lab.api import runner_ws

        app = create_app(dry_run=True)
        true_default_client = TestClient(app)

        resp = true_default_client.post("/api/run/receipt_literacy?dry-run=true")

        if resp.status_code == 400:
            return  # fail-closed via rejection also satisfies the contract
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        session = runner_ws._sessions[run_id]
        assert session.dry_run is True, (
            "?dry-run=true (hyphen) must not silently produce a LIVE run "
            "when the app-level --dry-run safety default is True — either "
            "honour it as a dry_run alias, or reject the request outright"
        )


# ── F-67805cb0 — concurrent WS clients on the same run_id ─────────────


@pytest.mark.usefixtures("_clear_sessions")
class TestConcurrentWebSocketGuard:
    """A second WS connection attaching to the SAME run_id while the first
    is still open must be rejected (4008), not allowed to race the first
    connection for items off the single per-session queue."""

    def _build_app(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        # Hanging run keeps the session + first WS connection alive long
        # enough to attempt (and observe the rejection of) a second attach.
        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await asyncio.Event().wait()
            return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", hanging_run_module)

        return create_app()

    def test_second_concurrent_connection_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from starlette.websockets import WebSocketDisconnect

        from xrpl_lab.api import runner_ws

        app = self._build_app(tmp_path, monkeypatch)

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers=_TEST_ORIGIN,
            ):
                # First connection is live — session must be marked attached.
                assert runner_ws._sessions[run_id].ws_attached is True

                # A second connection to the SAME run_id must be rejected.
                with (
                    pytest.raises(WebSocketDisconnect) as excinfo,
                    client.websocket_connect(
                        f"/api/run/receipt_literacy/ws?run_id={run_id}",
                        headers=_TEST_ORIGIN,
                    ) as second_ws,
                ):
                    second_ws.receive_json()

                assert excinfo.value.code == 4008, (
                    f"expected close code 4008 for a concurrent second "
                    f"attach, got {excinfo.value.code}"
                )

                # First connection is unaffected by the rejected second one.
                assert runner_ws._sessions[run_id].ws_attached is True

    def test_reconnect_after_first_closes_is_allowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A clean reconnect (first socket fully closed) must NOT be
        treated as a concurrent attach — only a truly simultaneous second
        connection is rejected."""
        from xrpl_lab.api import runner_ws

        app = self._build_app(tmp_path, monkeypatch)

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers=_TEST_ORIGIN,
            ):
                pass  # connect then immediately close cleanly

            assert _poll_until(
                lambda: runner_ws._sessions[run_id].ws_attached is False
            ), "ws_attached did not reset to False after the first connection closed"

            # Reconnecting now must succeed — entering the context manager
            # must NOT raise WebSocketDisconnect(4008).
            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers=_TEST_ORIGIN,
            ):
                assert runner_ws._sessions[run_id].ws_attached is True


# ── F-bddfe64b — load_all_modules() offload via asyncio.to_thread ─────


@pytest.mark.usefixtures("_clear_sessions")
class TestLoadAllModulesOffload:
    """``load_all_modules()`` is now invoked via ``asyncio.to_thread()``
    inside ``start_run`` (an ``async def`` HTTP route handler) so the
    parsing/disk I/O does not block the event loop. These tests pin that
    the offload is behaviorally transparent — same results, same errors —
    it only changes WHERE the call executes, not what it returns or
    raises.

    ``_run_module_task``'s OWN ``load_all_modules()`` call site is
    deliberately NOT offloaded (see the comment on that call site in
    runner_ws.py): it is a fire-and-forget background task
    (``asyncio.create_task``), and offloading it was found to orphan the
    task under ``TestClient(app)`` used without the ``with`` form — the
    per-request anyio portal for that pattern tears down before the
    cross-thread round trip completes, silently starving the WS queue of
    its terminal frame. The end-to-end test below confirms the run still
    completes correctly with that call site left synchronous."""

    def test_start_run_still_resolves_known_module(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert resp.status_code == 200
        assert "run_id" in resp.json()

    def test_start_run_still_404s_unknown_module(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/nope-not-a-module?dry_run=true")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "MODULE_NOT_FOUND"

    def test_run_module_task_completes_end_to_end_with_start_run_offload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drives an ACTUAL run through the WS to prove the whole flow —
        ``start_run``'s awaited-to-thread ``load_all_modules()`` call,
        followed by ``_run_module_task``'s own (synchronous) call — still
        resolves the module and reaches 'complete'. Also guards against a
        regression that re-introduces the offload in ``_run_module_task``:
        if that ever orphans the task again (see class docstring), THIS
        test would hang/fail rather than only a slower, less obviously
        related test elsewhere."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        async def _fake_run_module(module, transport, dry_run=False, force=False, **kwargs):
            return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", _fake_run_module)

        app = create_app()
        client = TestClient(app)
        run_id = client.post("/api/run/receipt_literacy?dry_run=true").json()["run_id"]

        complete_msg: dict | None = None
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}",
            headers=_TEST_ORIGIN,
        ) as ws_conn:
            for _ in range(20):
                msg = ws_conn.receive_json()
                if msg.get("type") in ("complete", "error"):
                    complete_msg = msg
                    break

        assert complete_msg is not None
        assert complete_msg["type"] == "complete"


# ── Origin allow-list robustness (verification, no code change) ──────


@pytest.mark.usefixtures("_clear_sessions")
class TestOriginAllowListRobustness:
    """Verifies (domain guidance — no code change needed, already
    correct) that the WS Origin allow-list is an EXACT-match membership
    check, not vulnerable to an empty/case/substring bypass.
    ``_ALLOWED_ORIGINS`` is checked via Python ``in`` against a tuple of
    strings, which is per-element exact equality — these tests pin that
    property against regression."""

    def test_empty_origin_header_is_rejected(
        self, client_with_module: TestClient
    ) -> None:
        from starlette.websockets import WebSocketDisconnect

        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": ""},
            ) as ws,
        ):
            ws.receive_json()

        assert excinfo.value.code == 4003

    def test_case_mismatched_origin_is_rejected_not_silently_accepted(
        self, client_with_module: TestClient
    ) -> None:
        """An uppercased variant of an allowed origin must NOT be treated
        as a match — the check is case-sensitive exact-equality. (A false
        NEGATIVE here is just an availability nuisance for a malformed
        client; this test pins that it is not a false POSITIVE / bypass.)
        """
        from starlette.websockets import WebSocketDisconnect

        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        mismatched = _ALLOWED_ORIGINS[0].upper()
        assert mismatched != _ALLOWED_ORIGINS[0]  # sanity: fixture actually differs

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": mismatched},
            ) as ws,
        ):
            ws.receive_json()

        assert excinfo.value.code == 4003

    def test_suffix_origin_is_rejected_not_substring_matched(
        self, client_with_module: TestClient
    ) -> None:
        """An Origin that merely CONTAINS an allowed origin as a substring
        (e.g. an attacker-controlled domain suffixed onto it) must not
        bypass the allow-list — Python ``in`` against the tuple is exact
        per-element equality, not substring containment."""
        from starlette.websockets import WebSocketDisconnect

        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        evil = f"{_ALLOWED_ORIGINS[0]}.evil.com"

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": evil},
            ) as ws,
        ):
            ws.receive_json()

        assert excinfo.value.code == 4003

    def test_prefix_origin_is_rejected_not_substring_matched(
        self, client_with_module: TestClient
    ) -> None:
        """Same as above with the allow-listed origin as a SUFFIX of the
        attacker value instead of a prefix."""
        from starlette.websockets import WebSocketDisconnect

        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        evil = f"https://evil.com#{_ALLOWED_ORIGINS[0]}"

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": evil},
            ) as ws,
        ):
            ws.receive_json()

        assert excinfo.value.code == 4003
