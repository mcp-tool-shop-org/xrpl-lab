"""Tests for the WebSocket module runner endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.api.runner_ws import _ALLOWED_ORIGINS
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app

# Default Origin header for WS test fixtures. Browsers always send Origin
# on WS upgrades; Starlette's TestClient does not by default. We pass an
# allow-listed value so existing tests exercise the post-wave-1 Origin
# validation path. Use _ALLOWED_ORIGINS[0] so a future allow-list edit
# automatically updates these tests.
_TEST_ORIGIN = {"origin": _ALLOWED_ORIGINS[0]}

# ── Fixtures ──────────────────────────────────────────────────────────


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


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with state/workspace redirected to tmp_path."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    app = create_app()
    return TestClient(app)


@pytest.fixture()
def client_with_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with a mocked single module available."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
    monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

    app = create_app()
    return TestClient(app)


# ── POST /api/run/{module_id} ─────────────────────────────────────────


class TestStartRun:
    def test_start_run_returns_run_id(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "started"
        assert isinstance(data["run_id"], str)
        assert len(data["run_id"]) > 0

    def test_start_run_invalid_module_returns_404(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/nonexistent_module?dry_run=true")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["code"] == "MODULE_NOT_FOUND"
        assert "not found" in detail["message"].lower()

    def test_start_run_dry_run_false_also_accepted(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/receipt_literacy?dry_run=false")
        assert resp.status_code == 200
        assert "run_id" in resp.json()

    def test_start_run_default_dry_run_is_false(
        self, client_with_module: TestClient
    ) -> None:
        resp = client_with_module.post("/api/run/receipt_literacy")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data

    def test_start_run_each_call_returns_unique_run_id(
        self, client_with_module: TestClient
    ) -> None:
        r1 = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        r2 = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert r1.json()["run_id"] != r2.json()["run_id"]


# ── WS /api/run/{module_id}/ws ────────────────────────────────────────


class TestRunWebSocket:
    def _start_run(self, client: TestClient, module_id: str = "receipt_literacy") -> str:
        resp = client.post(f"/api/run/{module_id}?dry_run=true")
        assert resp.status_code == 200
        return resp.json()["run_id"]

    def test_ws_invalid_run_id_closes_with_error(
        self, client_with_module: TestClient
    ) -> None:
        """Connecting with a bogus run_id should close the WebSocket immediately."""
        from starlette.websockets import WebSocketDisconnect

        try:
            with client_with_module.websocket_connect(
                "/api/run/receipt_literacy/ws?run_id=bogus-run-id",
                headers=_TEST_ORIGIN,
            ) as ws:
                # Server closes immediately for unknown run_id
                ws.receive_json()  # may or may not get a message before close
        except WebSocketDisconnect as exc:
            # Expected: server closed the connection for unknown run_id
            assert exc.code in (1000, 4004)
        except Exception as exc:
            if "disconnect" in str(exc).lower() or "1000" in str(exc):
                pass  # Expected WebSocket close
            else:
                raise  # Re-raise unexpected exceptions

    def test_ws_receives_messages_for_valid_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dry-run should produce at least a 'complete' message."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mod = _make_simple_module("receipt_literacy")
        mods = {"receipt_literacy": mod}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        # Mock run_module to avoid real async execution and just emit done
        async def _fake_run_module(module, transport, dry_run=False, force=False, **kwargs):
            return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", _fake_run_module)

        app = create_app()
        client = TestClient(app)

        start_resp = client.post("/api/run/receipt_literacy?dry_run=true")
        run_id = start_resp.json()["run_id"]

        messages: list[dict] = []
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}",
            headers=_TEST_ORIGIN,
        ) as ws_conn:
            for _ in range(20):  # read up to 20 messages
                try:
                    msg = ws_conn.receive_json()
                    messages.append(msg)
                    if msg.get("type") in ("complete", "error"):
                        break
                except Exception as exc:
                    if "disconnect" in str(exc).lower() or "1000" in str(exc):
                        break  # Expected WebSocket close
                    raise  # Re-raise unexpected exceptions

        msg_types = {m.get("type") for m in messages}
        assert "complete" in msg_types or "error" in msg_types

    def test_ws_complete_message_has_expected_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 'complete' message must have success, txids, and report_path."""
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

        start_resp = client.post("/api/run/receipt_literacy?dry_run=true")
        run_id = start_resp.json()["run_id"]

        complete_msg: dict | None = None
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}",
            headers=_TEST_ORIGIN,
        ) as ws_conn:
            for _ in range(20):
                try:
                    msg = ws_conn.receive_json()
                    if msg.get("type") == "complete":
                        complete_msg = msg
                        break
                    if msg.get("type") == "error":
                        break
                except Exception as exc:
                    if "disconnect" in str(exc).lower() or "1000" in str(exc):
                        break  # Expected WebSocket close
                    raise  # Re-raise unexpected exceptions

        assert complete_msg is not None, "Expected a 'complete' message"
        assert "success" in complete_msg
        assert "txids" in complete_msg
        assert "report_path" in complete_msg

    def test_ws_step_messages_contain_expected_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Step messages from _tracked_execute must have action, index, total."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        # Let the real run_module run (dry-run, no network needed)
        # but intercept _execute_action so it completes immediately
        from xrpl_lab import runner as runner_mod

        async def _fast_execute(step, state, transport, wallet_seed, context):
            return context

        monkeypatch.setattr(runner_mod, "_execute_action", _fast_execute)
        # Also patch console.input to avoid blocking on Enter prompt
        from rich.console import Console
        monkeypatch.setattr(Console, "input", lambda self, prompt="": "")

        app = create_app()
        client = TestClient(app)

        start_resp = client.post("/api/run/receipt_literacy?dry_run=true")
        run_id = start_resp.json()["run_id"]

        messages: list[dict] = []
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}",
            headers=_TEST_ORIGIN,
        ) as ws_conn:
            for _ in range(30):
                try:
                    msg = ws_conn.receive_json()
                    messages.append(msg)
                    if msg.get("type") in ("complete", "error"):
                        break
                except Exception as exc:
                    if "disconnect" in str(exc).lower() or "1000" in str(exc):
                        break  # Expected WebSocket close
                    raise  # Re-raise unexpected exceptions

        step_msgs = [m for m in messages if m.get("type") == "step"]
        assert len(step_msgs) > 0, "Expected at least one step message"
        s = step_msgs[0]
        assert "action" in s
        assert "index" in s
        assert "total" in s


# ── Session store ─────────────────────────────────────────────────────


class TestSessionStore:
    def test_sessions_persisted_in_store(
        self, client_with_module: TestClient
    ) -> None:
        """After POST /api/run, the session appears in _sessions."""
        from xrpl_lab.api import runner_ws

        initial_count = len(runner_ws._sessions)
        client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert len(runner_ws._sessions) > initial_count

    def test_multiple_runs_create_separate_sessions(
        self, client_with_module: TestClient
    ) -> None:
        from xrpl_lab.api import runner_ws

        r1 = client_with_module.post("/api/run/receipt_literacy?dry_run=true").json()
        r2 = client_with_module.post("/api/run/receipt_literacy?dry_run=true").json()

        assert r1["run_id"] in runner_ws._sessions
        assert r2["run_id"] in runner_ws._sessions
        assert r1["run_id"] != r2["run_id"]


# ── Origin allow-list (F-TESTS-003-revised) ──────────────────────────


class TestWebSocketOrigin:
    """WebSocket upgrades are not covered by browser CORS — the WS handler
    must enforce Origin manually to close the CSRF-via-WebSocket vector.

    Wave-1 added the validation but allowed missing Origin so existing
    test fixtures kept passing. Wave-2 (this) adds explicit accept/reject
    coverage; the bridge agent will then drop the None-Origin leniency in
    a follow-up commit without breaking these tests.
    """

    def test_ws_rejects_disallowed_origin(
        self, client_with_module: TestClient
    ) -> None:
        """A WS upgrade with a non-allow-listed Origin must be closed
        with code 4003 (RFC 6455 application policy violation)."""
        from starlette.websockets import WebSocketDisconnect

        # Start a real run so run_id resolves; the rejection must fire on
        # Origin alone before run_id even matters, but this also guards
        # against a future refactor that swaps the order of checks.
        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": "https://evil.com"},
            ) as ws,
        ):
            # Should never reach receive — server closes before accept.
            ws.receive_json()

        assert excinfo.value.code == 4003, (
            f"Expected close code 4003 for disallowed Origin, "
            f"got {excinfo.value.code}"
        )

    @pytest.mark.parametrize("allowed_origin", list(_ALLOWED_ORIGINS))
    def test_ws_accepts_allowed_origin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        allowed_origin: str,
    ) -> None:
        """Each Origin in _ALLOWED_ORIGINS must be accepted (handshake
        completes, server emits at least one message before closing)."""
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

        # If accepted, we should receive at least one message (typically
        # the 'complete' from _fake_run_module). If rejected, the with
        # block raises WebSocketDisconnect synchronously.
        got_message = False
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}",
            headers={"origin": allowed_origin},
        ) as ws_conn:
            for _ in range(5):
                try:
                    msg = ws_conn.receive_json()
                    got_message = True
                    if msg.get("type") in ("complete", "error"):
                        break
                except Exception as exc:
                    if "disconnect" in str(exc).lower() or "1000" in str(exc):
                        break
                    raise

        assert got_message, (
            f"Allowed origin {allowed_origin!r} did not produce any "
            "messages — handshake may have been rejected."
        )

    def test_ws_rejects_missing_origin(
        self, client_with_module: TestClient
    ) -> None:
        """A WS upgrade with no Origin header must be closed with code
        4003. Browsers always send Origin on WS upgrades, so a missing
        Origin means a non-browser client (CLI, integration test,
        server-to-server) — which we treat as the same CSRF risk as a
        disallowed Origin. Wave-2-phase-2 (commit 03e7a5f) tightened the
        check to drop the prior None-leniency; this test guards against
        a refactor accidentally re-introducing it.

        ``headers={}`` suppresses Starlette TestClient's default header
        injection and reaches the server with no ``origin`` key — verified
        empirically (server logs ``origin=None`` on this path).
        """
        from starlette.websockets import WebSocketDisconnect

        # Start a real run so run_id resolves; the rejection must fire on
        # missing Origin alone before run_id even matters.
        run_id = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        ).json()["run_id"]

        with (
            pytest.raises(WebSocketDisconnect) as excinfo,
            client_with_module.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={},  # explicitly no Origin — exercises the `is None` branch
            ) as ws,
        ):
            # Should never reach receive — server closes before accept.
            ws.receive_json()

        assert excinfo.value.code == 4003, (
            f"Expected close code 4003 for missing Origin, "
            f"got {excinfo.value.code}"
        )


# ── WS session lifecycle stress (F-TESTS-B-001) ──────────────────────


@pytest.fixture()
def _clear_sessions():
    """Snapshot and restore ``runner_ws._sessions`` around each lifecycle
    test. The session dict is module-level global state; without this the
    saturation test leaves hanging entries that pollute downstream tests.
    """
    from xrpl_lab.api import runner_ws

    snapshot = dict(runner_ws._sessions)
    runner_ws._sessions.clear()
    yield
    runner_ws._sessions.clear()
    runner_ws._sessions.update(snapshot)


class TestWebSocketLifecycle:
    """Stage B wave 1 — session lifecycle stress coverage.

    Workshop facilitators restarting stuck learners need confidence that
    the next run is not orphaned. These three tests lock in the
    production behavior for client disconnect mid-run, concurrency
    saturation, and idle keepalive — surfacing any silent-hang regression
    as a hard test failure.

    All tests use ``with TestClient(app) as client`` (context-manager
    form) so Starlette's anyio portal stays alive across the WS close.
    Without the ``with``, each TestClient request spins up its own
    portal, and the cleanup task scheduled in the WS handler's
    ``finally`` block is silently cancelled when the portal exits.
    """

    def _build_app(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        fake_run_module=None,
    ):
        """Build a FastAPI app with state redirected and module mocked.

        Inlined helper (rather than a fixture) keeps this lifecycle block
        self-contained per the wave-1 scope-discipline note.
        """
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        if fake_run_module is None:
            async def fake_run_module(  # type: ignore[no-redef]
                module, transport, dry_run=False, force=False, **kwargs
            ):
                return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", fake_run_module)

        return create_app()

    def test_ws_client_disconnect_mid_run_triggers_cleanup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _clear_sessions,
    ) -> None:
        """Client disconnects from WS — once the underlying run completes
        (or errors), the session must be removed from ``_sessions`` within
        ``_CLEANUP_GRACE_SECONDS``. Production default is 60s; we patch
        ``_schedule_session_cleanup`` to force a 0.5s grace so the test
        is deterministic without a real-time wait.

        TestClient is used as a context manager so Starlette's portal
        (and its event loop) stays alive across WS close — required for
        the cleanup task scheduled in the WS handler's ``finally`` block
        to actually execute.
        """
        import time as _time

        from xrpl_lab.api import runner_ws

        # Surgical patch: replace _schedule_session_cleanup with a wrapper
        # that forces a 0.5s grace period. Production behavior preserved
        # (status check + pop), only the delay is shortened.
        original_schedule = runner_ws._schedule_session_cleanup

        def fast_schedule(run_id: str, delay: float = 0.5) -> None:
            return original_schedule(run_id, delay=0.5)

        monkeypatch.setattr(
            runner_ws, "_schedule_session_cleanup", fast_schedule
        )

        app = self._build_app(tmp_path, monkeypatch)

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            # Open WS, read at most one message, then exit the with-block
            # to disconnect. The fake run_module returns True quickly so
            # session.status flips to "complete" → cleanup is eligible.
            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers=_TEST_ORIGIN,
            ) as ws_conn:
                try:
                    ws_conn.receive_json()
                except Exception as exc:
                    if (
                        "disconnect" not in str(exc).lower()
                        and "1000" not in str(exc)
                    ):
                        raise

            # Poll up to 2.0s for cleanup. 0.5s grace + 1.5s slack.
            deadline = _time.monotonic() + 2.0
            while _time.monotonic() < deadline:
                if runner_ws._sessions.get(run_id) is None:
                    break
                _time.sleep(0.05)

            session_after = runner_ws._sessions.get(run_id)
            if session_after is not None:
                pytest.fail(
                    f"Session {run_id} not cleaned up after 2.0s "
                    f"(status={session_after.status!r}). Cleanup task "
                    "did not pop the session — possible regression in "
                    "_schedule_session_cleanup."
                )

    def test_ws_concurrent_runs_over_max_limit_rejects_clearly(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _clear_sessions,
    ) -> None:
        """Saturate ``_MAX_CONCURRENT_RUNS`` with N background runs, then
        verify the (N+1)-th POST /api/run gets a structured 429 with code
        ``RATE_LIMIT_RUNS`` — never a silent hang.

        Production gate is at the HTTP-start endpoint (``start_run``),
        so the rejection lands before WS handshake even begins. Lock that
        in: a future refactor that drops the gate to WS-handshake-only
        would silently break facilitator workflows.
        """
        # Use a fake run_module that hangs (never returns) so the active
        # run count stays at _MAX_CONCURRENT_RUNS for the duration of the
        # test. asyncio.Event().wait() cancels cleanly on app teardown.
        import asyncio as _asyncio

        from xrpl_lab.api import runner_ws

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        app = self._build_app(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )

        max_runs = runner_ws._MAX_CONCURRENT_RUNS
        with TestClient(app) as client:
            for _ in range(max_runs):
                r = client.post("/api/run/receipt_literacy?dry_run=true")
                assert r.status_code == 200, (
                    f"Expected 200 within saturation window, "
                    f"got {r.status_code}"
                )

            # The (max_runs + 1)-th request must be rejected with a
            # structured 429 — not silently queued, not hung, not 500.
            rejected = client.post("/api/run/receipt_literacy?dry_run=true")
            assert rejected.status_code == 429, (
                f"Expected 429 when exceeding _MAX_CONCURRENT_RUNS="
                f"{max_runs}, got {rejected.status_code}"
            )
            detail = rejected.json()["detail"]
            assert detail["code"] == "RATE_LIMIT_RUNS", (
                f"Expected code RATE_LIMIT_RUNS, got {detail.get('code')!r}"
            )
            # The hint must mention waiting — facilitator-actionable copy.
            assert "wait" in detail["hint"].lower(), (
                f"Expected actionable 'wait' hint, "
                f"got {detail.get('hint')!r}"
            )

    def test_ws_idle_timeout_recovers_or_fails_gracefully(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _clear_sessions,
    ) -> None:
        """An idle WS (no messages in queue) must surface either a
        keepalive ping OR a clean close — never a silent hang.

        Production hardcodes the keepalive timeout at 30.0s inside
        ``run_websocket``. We monkey-patch ``asyncio.wait_for`` within
        the runner_ws module to shrink that 30.0s to 0.3s so the test
        deterministically exercises the keepalive branch without a
        real-time wait.
        """
        import asyncio as _asyncio

        from xrpl_lab.api import runner_ws

        # Hanging run_module → queue stays empty → WS read loop hits its
        # timeout branch and emits the keepalive ping.
        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        # Surgical patch: only the 30.0s keepalive timeout is shortened.
        # Other wait_for calls (run timeout = 300s) pass through unchanged.
        real_wait_for = _asyncio.wait_for

        async def short_keepalive_wait_for(coro, timeout):
            if timeout == 30.0:
                timeout = 0.3
            return await real_wait_for(coro, timeout)

        monkeypatch.setattr(
            runner_ws.asyncio, "wait_for", short_keepalive_wait_for
        )

        app = self._build_app(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )

        got_ping = False
        got_clean_close = False
        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers=_TEST_ORIGIN,
            ) as ws_conn:
                # Read up to 5 frames — first should be a ping given the
                # 0.3s shortened keepalive.
                for _ in range(5):
                    try:
                        msg = ws_conn.receive_json(mode="text")
                        if msg.get("type") == "ping":
                            got_ping = True
                            break
                    except Exception as exc:
                        err = str(exc).lower()
                        if "disconnect" in err or "1000" in err:
                            got_clean_close = True
                            break
                        raise

        assert got_ping or got_clean_close, (
            "Idle WS produced neither a keepalive ping nor a clean close "
            "— this is the silent-hang regression the test guards against."
        )


# ── GET /api/runs facilitator endpoints (F-BRIDGE-B-RUNNER-SESSION-OBS) ──


class TestGetRunsEndpoints:
    """Stage B wave 2 phase 1 — facilitator observability over `_sessions`.

    These endpoints expose a safe-to-expose projection of the in-memory
    session store so a facilitator can curl/dashboard "which learners
    are running" without opening a WS per learner.

    All tests use the ``_clear_sessions`` fixture so the module-global
    ``_sessions`` dict starts empty per-test. Without it, sessions from
    earlier tests in the file leak across boundaries.
    """

    def test_get_runs_empty_when_no_sessions(
        self,
        client_with_module: TestClient,
        _clear_sessions,
    ) -> None:
        """No active runs → empty list, max_concurrent reported, active_count 0."""
        from xrpl_lab.api import runner_ws

        resp = client_with_module.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["max_concurrent"] == runner_ws._MAX_CONCURRENT_RUNS
        assert data["active_count"] == 0

    def test_get_runs_lists_active_sessions(
        self,
        client_with_module: TestClient,
        _clear_sessions,
    ) -> None:
        """After two POSTs, GET /api/runs returns 2 entries with the
        expected fields. Does not assert ``status`` strictly because the
        background task may have flipped the session to ``running`` /
        ``completed`` / ``failed`` by the time the GET lands; the field
        presence and field types are what we lock in here."""
        r1 = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        r2 = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert r1.status_code == 200
        assert r2.status_code == 200
        ids = {r1.json()["run_id"], r2.json()["run_id"]}

        resp = client_with_module.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()

        # Our two runs must appear (the test fixture's _clear_sessions
        # ensures no leakage from earlier tests).
        assert len(data["runs"]) == 2
        seen_ids = {r["run_id"] for r in data["runs"]}
        assert seen_ids == ids

        for entry in data["runs"]:
            # Required field presence.
            assert "run_id" in entry
            assert "module_id" in entry
            assert "status" in entry
            assert "created_at" in entry
            assert "elapsed_seconds" in entry
            assert "queue_size" in entry
            assert "dry_run" in entry
            # Field types / values.
            assert entry["module_id"] == "receipt_literacy"
            assert entry["status"] in ("running", "completed", "failed")
            assert isinstance(entry["elapsed_seconds"], (int, float))
            assert entry["elapsed_seconds"] >= 0.0
            assert isinstance(entry["queue_size"], int)
            assert entry["queue_size"] >= 0
            assert entry["dry_run"] is True
            # Forbidden-leak fields stay out.
            assert "error" not in entry
            assert "txids" not in entry
            assert "report_path" not in entry

    def test_get_run_detail_returns_404_for_unknown(
        self,
        client_with_module: TestClient,
        _clear_sessions,
    ) -> None:
        """Unknown run_id → 404 with structured ``RUN_NOT_FOUND`` envelope."""
        resp = client_with_module.get("/api/runs/nonexistent-run-id")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["code"] == "RUN_NOT_FOUND"
        assert "not found" in detail["message"].lower()
        # Actionable hint for facilitators.
        assert "hint" in detail and detail["hint"]

    def test_get_run_detail_returns_correct_fields(
        self,
        client_with_module: TestClient,
        _clear_sessions,
    ) -> None:
        """Known run_id → 200 with the full RunInfo shape."""
        start = client_with_module.post(
            "/api/run/receipt_literacy?dry_run=true"
        )
        assert start.status_code == 200
        run_id = start.json()["run_id"]

        resp = client_with_module.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["run_id"] == run_id
        assert data["module_id"] == "receipt_literacy"
        assert data["status"] in ("running", "completed", "failed")
        # ISO 8601 with timezone — datetime.fromisoformat must parse it.
        from datetime import datetime as _dt
        parsed = _dt.fromisoformat(data["created_at"])
        assert parsed.tzinfo is not None
        assert isinstance(data["elapsed_seconds"], (int, float))
        assert data["elapsed_seconds"] >= 0.0
        assert isinstance(data["queue_size"], int)
        assert data["dry_run"] is True
        # Forbidden-leak fields stay out.
        assert "error" not in data
        assert "txids" not in data
        assert "report_path" not in data


# ── DELETE /api/runs/{run_id} (F-BRIDGE-FT-001) ──────────────────────


class TestDeleteRunEndpoint:
    """Phase 7 v1.6.0 — facilitator-initiated cancellation.

    DELETE /api/runs/{run_id} cancels an in-flight asyncio task,
    frees the concurrency slot, and emits a final ``RUNTIME_CANCELLED``
    envelope to any connected WS client. Idempotent on already-
    terminated runs (returns 200 with ``status="already_terminated"``).
    Unknown run_id → 404 with the structured ``RUN_NOT_FOUND`` envelope.

    Workshop workflow: a learner's run gets stuck (slow testnet, bad
    input, distracted learner). The facilitator clicks "Cancel" on the
    dashboard or curls DELETE /api/runs/{run_id} to free the slot
    without restarting the server.
    """

    def _build_app(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        fake_run_module=None,
    ):
        """Mirror of TestWebSocketLifecycle._build_app — same pattern."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

        if fake_run_module is None:
            async def fake_run_module(  # type: ignore[no-redef]
                module, transport, dry_run=False, force=False, **kwargs
            ):
                return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", fake_run_module)

        return create_app()

    def test_delete_run_cancels_running_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _clear_sessions,
    ) -> None:
        """Start a hanging run, DELETE it, assert 200 + cancelled status.

        Verifies:
          * 200 with ``status="cancelled"`` and a facilitator-friendly
            message.
          * Session status flips to "cancelled" (terminal).
          * Concurrency slot is freed: starting a new run after the
            DELETE succeeds even when we previously held _MAX_CONCURRENT
            saturated by hanging tasks.
        """
        import asyncio as _asyncio

        from xrpl_lab.api import runner_ws

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        app = self._build_app(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )

        max_runs = runner_ws._MAX_CONCURRENT_RUNS
        with TestClient(app) as client:
            # Saturate the concurrency cap with hanging runs.
            run_ids: list[str] = []
            for _ in range(max_runs):
                r = client.post("/api/run/receipt_literacy?dry_run=true")
                assert r.status_code == 200
                run_ids.append(r.json()["run_id"])

            # Pre-condition: any further POST is rate-limited.
            blocked = client.post("/api/run/receipt_literacy?dry_run=true")
            assert blocked.status_code == 429, (
                "Saturation precondition violated — DELETE test is "
                "meaningless if the cap isn't already in force."
            )

            # DELETE the first hanging run.
            target = run_ids[0]
            resp = client.delete(f"/api/runs/{target}")
            assert resp.status_code == 200, (
                f"DELETE expected 200, got {resp.status_code}: {resp.text}"
            )
            body = resp.json()
            assert body["run_id"] == target
            assert body["status"] == "cancelled"
            # Facilitator-actionable copy.
            assert "cancelled" in body["message"].lower()

            # Session is in terminal "cancelled" state (or already evicted
            # by the cleanup grace period — both are valid post-conditions
            # for "no longer holding the slot").
            sess = runner_ws._sessions.get(target)
            assert sess is None or sess.status == "cancelled", (
                f"After DELETE, session should be cancelled or evicted; "
                f"got status={sess.status if sess else None!r}"
            )

            # Concurrency slot freed: a new POST now succeeds.
            freed = client.post("/api/run/receipt_literacy?dry_run=true")
            assert freed.status_code == 200, (
                f"Concurrency slot was not freed after DELETE — "
                f"got {freed.status_code}: {freed.text}"
            )

    def test_delete_run_returns_404_for_unknown(
        self,
        client_with_module: TestClient,
        _clear_sessions,
    ) -> None:
        """Unknown run_id → 404 with the structured ``RUN_NOT_FOUND`` envelope.

        Same shape as GET /api/runs/{run_id} so dashboards can share
        a single error-handling path across the read and write surfaces.
        """
        resp = client_with_module.delete("/api/runs/nonexistent-run-id")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["code"] == "RUN_NOT_FOUND"
        assert "not found" in detail["message"].lower()
        assert "hint" in detail and detail["hint"]
        # The hint must point facilitators at the live-list endpoint
        # so a typo'd run_id has an obvious recovery path.
        assert "/api/runs" in detail["hint"]

    def test_delete_run_idempotent_on_completed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        _clear_sessions,
    ) -> None:
        """A run that already finished → DELETE returns 200 with
        ``status="already_terminated"``. No error, no second cancel.

        A double-DELETE from a flaky network or a confused facilitator
        must be a safe no-op — never a 500 or a 404 (the run still
        exists in the session map until the grace-period cleanup).
        """
        import time as _time

        from xrpl_lab.api import runner_ws

        # Patch grace period to 60s so the completed run stays in
        # _sessions long enough for our DELETE to land.
        original_schedule = runner_ws._schedule_session_cleanup

        def long_schedule(run_id: str, delay: float = 60.0) -> None:
            return original_schedule(run_id, delay=60.0)

        monkeypatch.setattr(
            runner_ws, "_schedule_session_cleanup", long_schedule
        )

        app = self._build_app(tmp_path, monkeypatch)

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            # Wait for the fake run_module (returns True quickly) to
            # flip the session into a terminal state.
            deadline = _time.monotonic() + 2.0
            while _time.monotonic() < deadline:
                sess = runner_ws._sessions.get(run_id)
                if sess and sess.status in ("complete", "error"):
                    break
                _time.sleep(0.05)

            sess = runner_ws._sessions.get(run_id)
            assert sess is not None, "Session disappeared before DELETE"
            assert sess.status in ("complete", "error"), (
                f"Run did not terminate within window; status="
                f"{sess.status!r}"
            )

            # First DELETE on a terminated run.
            resp = client.delete(f"/api/runs/{run_id}")
            assert resp.status_code == 200, (
                f"Idempotent DELETE expected 200, got {resp.status_code}"
            )
            body = resp.json()
            assert body["run_id"] == run_id
            assert body["status"] == "already_terminated"
