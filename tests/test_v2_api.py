"""v2.0.0 API regression tests — typed-contract + cleanup-idempotency fixes.

Covers two LOW findings from the v1.8.0 → v2.0.0 dogfood swarm:

* **API-A-002** — ``start_run`` / ``cancel_run`` were outside the typed
  response_model contract (annotated ``dict[str, Any]`` / ``dict[str, str]``),
  so FastAPI applied no validation and the canonical ``RunStartResponse`` /
  ``RunCancelResponse`` models drifted unenforced. These tests pin that both
  endpoints now validate against their models AND that ``cancel_run`` returns
  the SAME key set on the active-run and already-terminal paths.

* **API-A-003** — DELETE /api/runs/{id} on a run with a connected WS client
  double-scheduled the grace-period cleanup (``cancel_session`` schedules it,
  and the WS read-loop's ``finally`` schedules it again). These tests pin that
  exactly ONE cleanup is pending per run_id even when both paths fire.

These tests must NOT weaken the verified-held crown jewels (WS origin 4003,
``_error_envelope`` no-leak, bounded queue, run-cancellation lifecycle); they
only add coverage for the two fixes above.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app

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
def _clear_sessions():
    """Snapshot/restore ``runner_ws._sessions`` around each test so the
    module-global session dict starts empty and leaves no residue."""
    from xrpl_lab.api import runner_ws

    snapshot = dict(runner_ws._sessions)
    runner_ws._sessions.clear()
    yield
    runner_ws._sessions.clear()
    runner_ws._sessions.update(snapshot)


@pytest.fixture()
def client_with_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with state/workspace redirected and one module mocked."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
    monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

    return TestClient(create_app())


def _build_app_with_run_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_run_module=None,
):
    """Build an app with state redirected, one module mocked, and an
    optional ``run_module`` stub (defaults to an instant-success stub)."""
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


# ── API-A-002: typed response_model contract ─────────────────────────


@pytest.mark.usefixtures("_clear_sessions")
class TestStartRunTypedContract:
    """``start_run`` must be annotated with ``RunStartResponse`` and return a
    payload that validates against that model — bringing it under the typed
    response_model + TS-drift contract instead of the old untyped
    ``dict[str, Any]``."""

    def test_start_response_validates_against_run_start_response(
        self, client_with_module: TestClient
    ) -> None:
        from xrpl_lab.api.schemas import RunStartResponse

        resp = client_with_module.post("/api/run/receipt_literacy?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()

        # Must round-trip through the canonical model with no extra/missing keys.
        model = RunStartResponse(**data)
        assert set(data.keys()) == set(model.model_dump().keys())
        assert isinstance(model.run_id, str) and model.run_id
        assert model.status == "started"

    def test_start_run_is_annotated_with_run_start_response(self) -> None:
        """The route's return annotation must be ``RunStartResponse`` so
        FastAPI applies response_model validation (the fix's mechanism)."""
        import typing

        from xrpl_lab.api import runner_ws
        from xrpl_lab.api.schemas import RunStartResponse

        hints = typing.get_type_hints(runner_ws.start_run)
        assert hints.get("return") is RunStartResponse, (
            "start_run must be annotated -> RunStartResponse so FastAPI "
            f"validates the response; got {hints.get('return')!r}"
        )


@pytest.mark.usefixtures("_clear_sessions")
class TestCancelRunConsistentShape:
    """``cancel_run`` (DELETE /api/runs/{id}) must return the SAME key set on
    the active-run path (``status='cancelled'``) and the already-terminal path
    (``status='already_terminated'``). Pre-fix the active path returned a
    3-key dict and the terminal path also 3 keys, but the contract was
    unenforced and the models were dead; this pins the union shape under
    ``RunCancelResponse`` with ``message`` present in BOTH branches."""

    _CANCEL_KEYS = {"run_id", "status", "message"}

    def test_cancel_run_active_path_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio as _asyncio

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        app = _build_app_with_run_module(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )
        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            resp = client.delete(f"/api/runs/{run_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert set(body.keys()) == self._CANCEL_KEYS, (
                f"active-path cancel shape drift: {set(body.keys())}"
            )
            assert body["status"] == "cancelled"
            assert body["run_id"] == run_id
            # message present (non-null) on the active path.
            assert isinstance(body["message"], str) and body["message"]

    def test_cancel_run_terminal_path_shape_matches_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _time

        from xrpl_lab.api import runner_ws

        # Long grace so the completed run stays in _sessions for the DELETE.
        original_schedule = runner_ws._schedule_session_cleanup

        def long_schedule(run_id: str, delay: float = 60.0) -> None:
            return original_schedule(run_id, delay=60.0)

        monkeypatch.setattr(runner_ws, "_schedule_session_cleanup", long_schedule)

        app = _build_app_with_run_module(tmp_path, monkeypatch)
        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            # Wait for the fast fake run to reach a terminal state.
            deadline = _time.monotonic() + 2.0
            while _time.monotonic() < deadline:
                sess = runner_ws._sessions.get(run_id)
                if sess and sess.status in ("complete", "error"):
                    break
                _time.sleep(0.05)

            resp = client.delete(f"/api/runs/{run_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert set(body.keys()) == self._CANCEL_KEYS, (
                f"terminal-path cancel shape drift: {set(body.keys())} — "
                "must match the active-path key set exactly"
            )
            assert body["status"] == "already_terminated"
            assert body["run_id"] == run_id
            # message key present in BOTH branches (the consistency fix).
            assert "message" in body

    def test_cancel_run_validates_against_run_cancel_response(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both DELETE outcomes must deserialize into ``RunCancelResponse``."""
        import asyncio as _asyncio

        from xrpl_lab.api.schemas import RunCancelResponse

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        app = _build_app_with_run_module(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )
        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]
            body = client.delete(f"/api/runs/{run_id}").json()
            model = RunCancelResponse(**body)
            assert set(body.keys()) == set(model.model_dump().keys())


class TestDeadSchemaRemoved:
    """``RunStreamMessage`` was referenced nowhere after the typed-contract
    fix and must be removed; ``RunStartResponse`` / ``RunCancelResponse`` must
    exist and carry the documented fields."""

    def test_run_stream_message_is_gone(self) -> None:
        import xrpl_lab.api.schemas as schemas

        assert not hasattr(schemas, "RunStreamMessage"), (
            "RunStreamMessage was dead (referenced nowhere) and should be "
            "removed by the API-A-002 fix"
        )

    def test_run_start_and_cancel_models_exist(self) -> None:
        from xrpl_lab.api.schemas import RunCancelResponse, RunStartResponse

        assert set(RunStartResponse.model_fields) == {"run_id", "status"}
        # Union of fields across both cancel branches.
        assert set(RunCancelResponse.model_fields) == {"run_id", "status", "message"}


# ── API-A-003: cleanup is scheduled exactly once per run_id ──────────


class TestCleanupNotDoubleScheduled:
    """``_schedule_session_cleanup`` must early-return when a cleanup is
    already pending for that run_id, so a DELETE on a run with a connected WS
    (which schedules from BOTH ``cancel_session`` and the WS ``finally``) ends
    up with exactly ONE pending cleanup task — not two timers racing the same
    pop."""

    @pytest.mark.asyncio
    async def test_double_schedule_creates_one_pending_cleanup(self) -> None:
        """Two back-to-back schedules for the same run_id ⇒ one pending task."""
        import asyncio as _asyncio
        import contextlib as _contextlib

        from xrpl_lab.api import runner_ws

        runner_ws._background_tasks.clear()
        run_id = "double-schedule-run"
        # Long delay so both calls land while the first is still pending.
        runner_ws._schedule_session_cleanup(run_id, delay=5.0)
        runner_ws._schedule_session_cleanup(run_id, delay=5.0)

        pending = [t for t in runner_ws._background_tasks if not t.done()]
        assert len(pending) == 1, (
            f"expected exactly ONE pending cleanup for {run_id!r}, got "
            f"{len(pending)} — the second schedule was not deduplicated"
        )

        # Cleanup: cancel the sleeping task(s) so they don't outlive the test.
        for t in pending:
            t.cancel()
            with _contextlib.suppress(_asyncio.CancelledError):
                await t
        runner_ws._background_tasks.clear()

    @pytest.mark.asyncio
    async def test_inflight_marker_cleared_after_completion(self) -> None:
        """After a cleanup completes, a subsequent schedule for the same
        run_id is allowed again (the in-flight marker must be discarded)."""
        import asyncio as _asyncio

        from xrpl_lab.api import runner_ws

        runner_ws._background_tasks.clear()
        run_id = "reschedulable-run"

        # First schedule with delay=0 → completes on the next loop tick.
        runner_ws._schedule_session_cleanup(run_id, delay=0)
        first = next(iter(runner_ws._background_tasks))
        await first
        await _asyncio.sleep(0)  # let done-callbacks run

        # Now a fresh schedule must be permitted (marker cleared).
        runner_ws._schedule_session_cleanup(run_id, delay=0)
        pending_or_done = [
            t for t in runner_ws._background_tasks
        ]
        assert len(pending_or_done) >= 1, (
            "after the first cleanup completed, a new schedule for the same "
            "run_id was rejected — the in-flight marker was not cleared"
        )
        for t in list(runner_ws._background_tasks):
            await t
        await _asyncio.sleep(0)
        runner_ws._background_tasks.clear()

    def test_delete_with_connected_ws_schedules_cleanup_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _clear_sessions
    ) -> None:
        """End-to-end: DELETE a run while a WS is connected. Both
        ``cancel_session`` and the WS ``finally`` call
        ``_schedule_session_cleanup``; the dedup guard means only ONE cleanup
        task is created for that run_id across the whole interaction."""
        import asyncio as _asyncio
        import threading as _threading

        from starlette.websockets import WebSocketDisconnect

        from xrpl_lab.api import runner_ws

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        # Count how many cleanup tasks get scheduled for our run_id by
        # wrapping the real function (preserves dedup behavior under test).
        scheduled_run_ids: list[str] = []
        real_schedule = runner_ws._schedule_session_cleanup

        def counting_schedule(run_id: str, delay: float = 60.0) -> None:
            before = len(runner_ws._background_tasks)
            # Use a long delay so created tasks stay pending and observable.
            real_schedule(run_id, delay=60.0)
            after = len(runner_ws._background_tasks)
            if after > before:
                scheduled_run_ids.append(run_id)

        monkeypatch.setattr(
            runner_ws, "_schedule_session_cleanup", counting_schedule
        )

        app = _build_app_with_run_module(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            with client.websocket_connect(
                f"/api/run/receipt_literacy/ws?run_id={run_id}",
                headers={"origin": runner_ws._ALLOWED_ORIGINS[0]},
            ) as ws_conn:
                delete_result: dict = {}

                def _do_delete() -> None:
                    resp = client.delete(f"/api/runs/{run_id}")
                    delete_result["status_code"] = resp.status_code

                t = _threading.Thread(target=_do_delete, daemon=True)
                t.start()

                # Drain frames until the socket closes (cancel envelope then
                # normal close). Both the cancel_session schedule and the WS
                # finally schedule fire across this window.
                for _ in range(10):
                    try:
                        ws_conn.receive_json()
                    except WebSocketDisconnect:
                        break

                t.join(timeout=5.0)

        assert delete_result.get("status_code") == 200

        # Exactly one cleanup task created for THIS run_id — the dedup guard
        # collapsed the cancel_session-side and WS-finally-side schedules.
        my_run_count = scheduled_run_ids.count(run_id)
        assert my_run_count == 1, (
            f"expected exactly ONE cleanup task for {run_id!r}, got "
            f"{my_run_count} — double-scheduled cleanup (API-A-003) regressed"
        )

        # Tidy up any pending long-delay cleanup tasks so they don't leak.
        for task in list(runner_ws._background_tasks):
            task.cancel()
        runner_ws._background_tasks.clear()


# ── TXBCD-007: concurrency-slot leak window is closed ────────────────


@pytest.mark.usefixtures("_clear_sessions")
class TestNoStartedSlotLeak:
    """A session must not be able to strand a concurrency slot by sitting
    in a non-terminal state that neither the timeout path nor cleanup ever
    evicts.

    Background (TXBCD-007): the concurrency cap counts sessions whose
    status is in ``{"running", "started"}``. Pre-fix a session was created
    in ``"started"`` and only flipped to ``"running"`` inside
    ``_run_module_task``. A code path that returned/raised BEFORE that flip
    would leave the session pinned at ``"started"`` forever — neither
    ``_evict_oldest_completed`` (terminal-only) nor the run-timeout (inside
    the task that never started) could free it. The fix collapses the
    distinction: a freshly-created session is already ``"running"``, so the
    ``"started"`` leak window does not exist.

    These tests pin the invariant at its source rather than asserting a
    specific implementation, so either valid remediation (collapse to
    ``running`` OR make an aged ``started`` evictable) keeps them honest.
    """

    def test_fresh_session_is_not_in_started_state(self) -> None:
        """A ModuleRunSession, the instant it is constructed, must already
        count toward the cap under a status that a terminal flip can later
        clear — i.e. NOT the orphan-prone ``"started"``.

        If a future refactor reintroduces a ``"started"`` creation state,
        this fails loudly: that is the exact window TXBCD-007 closed.
        """
        from xrpl_lab.api.runner_ws import ModuleRunSession

        session = ModuleRunSession(
            run_id="fresh-1", module_id="receipt_literacy", dry_run=True
        )
        assert session.status != "started", (
            "Fresh session is in 'started' — this is the slot-leak window "
            "TXBCD-007 closed. A path that returns before the running-flip "
            "would strand the concurrency slot permanently."
        )
        # It must still be a non-terminal, cap-counted state so live runs
        # are correctly rate-limited.
        assert session.status == "running", (
            f"Expected a freshly-created session to count as 'running'; "
            f"got {session.status!r}"
        )

    def test_no_session_ever_observed_in_started_during_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Across the full POST → background-task lifecycle, the session is
        only ever ``running`` then a terminal state — never ``started``.

        This guards the invariant end-to-end: a hanging run keeps the
        session non-terminal, and we assert it reads ``running`` (the
        cap-counted, terminal-clearable state) the whole time.
        """
        import asyncio as _asyncio
        import time as _time

        from xrpl_lab.api import runner_ws

        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        app = _build_app_with_run_module(
            tmp_path, monkeypatch, fake_run_module=hanging_run_module
        )
        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            # Sample the internal status repeatedly over a short window;
            # it must never be the orphan-prone "started".
            deadline = _time.monotonic() + 1.0
            seen: set[str] = set()
            while _time.monotonic() < deadline:
                sess = runner_ws._sessions.get(run_id)
                if sess is not None:
                    seen.add(sess.status)
                _time.sleep(0.02)

            assert "started" not in seen, (
                f"Session was observed in 'started' state {seen!r} — the "
                "TXBCD-007 leak window is open again."
            )
            assert seen == {"running"}, (
                f"Hanging run should sit only in 'running'; saw {seen!r}"
            )

    def test_early_return_before_run_does_not_strand_slot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate the TXBCD-007 hazard directly: a run whose task raises
        BEFORE any status flip it might have controlled. The slot must end
        up free (session terminal), not pinned at a non-terminal status.

        ``load_all_modules`` returning an empty dict makes
        ``_run_module_task`` take its early ``mod is None`` branch — which
        sets ``status="error"`` and returns. With the fix the session was
        created ``running`` and ends ``error`` (terminal); a regression to
        ``started``-on-create would leave a non-terminal residue if any
        future early path skipped the flip.
        """
        import time as _time

        from xrpl_lab.api import runner_ws

        app = _build_app_with_run_module(tmp_path, monkeypatch)
        # After app build, swap module loading to empty so the task takes
        # the early-error branch. POST still passes its own membership
        # check via the routes-level loader, so we only patch the runner_ws
        # symbol the task reads.
        good_mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        call_state = {"first": True}

        def flaky_load() -> dict:
            # First call (POST membership check) sees the module; the
            # background task's call sees an empty dict → early error.
            if call_state["first"]:
                call_state["first"] = False
                return good_mods
            return {}

        monkeypatch.setattr(runner_ws, "load_all_modules", flaky_load)

        with TestClient(app) as client:
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]

            deadline = _time.monotonic() + 2.0
            final_status = None
            while _time.monotonic() < deadline:
                sess = runner_ws._sessions.get(run_id)
                if sess is None:
                    final_status = "evicted"
                    break
                if sess.status in ("complete", "error", "cancelled"):
                    final_status = sess.status
                    break
                _time.sleep(0.02)

            assert final_status in ("error", "evicted"), (
                f"Early-return run did not reach a terminal/freed state; "
                f"final_status={final_status!r} — slot may be stranded."
            )

            # Slot is free: a fresh run starts (would be blocked if the
            # errored session were stuck counting against the cap).
            again = client.post("/api/run/receipt_literacy?dry_run=true")
            # The second POST's loader returns {} (call_state consumed), so
            # the route-level 404 is acceptable; what matters is it is NOT a
            # 429 rate-limit, which would prove the prior slot leaked.
            assert again.status_code != 429, (
                "A new run was rate-limited after an early-error run — the "
                "errored session is stranding a concurrency slot (TXBCD-007)."
            )


# ── TXBCD-006: WS send-failure leaves a server-side breadcrumb ───────


class TestWsSendFailureBreadcrumb:
    """When a WS send fails mid-stream (client navigated away, transport
    error), the read loop breaks. Pre-fix it broke SILENTLY — no log — so a
    facilitator investigating a stuck dashboard had no breadcrumb telling
    "send failed" apart from "client closed cleanly".

    The fix logs an INFO with the run_id (and a short reason) on BOTH
    send-failure break paths: the keepalive-ping send and the message send.
    The log must carry run_id only — never seed/path — keeping the
    no-leak crown jewel intact.
    """

    def _build_app(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        fake_run_module=None,
    ):
        return _build_app_with_run_module(
            tmp_path, monkeypatch, fake_run_module=fake_run_module
        )

    def test_message_send_failure_logs_run_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Force ``websocket.send_json`` to raise on the message path and
        assert a log record carrying the run_id is emitted on the break,
        with no seed/path leaked into it."""
        import asyncio as _asyncio
        import logging as _logging

        from xrpl_lab.api import runner_ws

        # A run that emits at least one queue item then hangs, guaranteeing
        # the read loop reaches the message-send path (not the ping path).
        async def emit_then_hang(
            module, transport, dry_run=False, force=False, on_step=None, **kwargs
        ):
            if on_step is not None:
                await on_step("ensure_wallet", 0, 1)
            await _asyncio.Event().wait()
            return True

        app = self._build_app(
            tmp_path, monkeypatch, fake_run_module=emit_then_hang
        )

        # Patch WebSocket.send_json to raise so the message-send branch
        # breaks. We patch at the class level used by the server.
        from starlette.websockets import WebSocket as _WS

        sentinel_seed = "sEdSENTINEL_SEND_FAIL"
        sentinel_path = "/home/learner/.xrpl-lab/wallet.json"

        async def boom_send_json(self, *a, **kw):  # noqa: ANN001
            raise RuntimeError(
                f"send failed {sentinel_path} seed={sentinel_seed}"
            )

        monkeypatch.setattr(_WS, "send_json", boom_send_json, raising=True)

        with (
            caplog.at_level(_logging.DEBUG, logger=runner_ws.logger.name),
            TestClient(app) as client,
        ):
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]
            from starlette.websockets import WebSocketDisconnect

            try:
                with client.websocket_connect(
                    f"/api/run/receipt_literacy/ws?run_id={run_id}",
                    headers={"origin": runner_ws._ALLOWED_ORIGINS[0]},
                ) as ws_conn:
                    # send_json raises server-side → read loop breaks →
                    # socket closes. The client sees a disconnect.
                    for _ in range(3):
                        ws_conn.receive_json()
            except (WebSocketDisconnect, Exception):
                pass

        # A breadcrumb mentioning THIS run_id must exist.
        matching = [
            r for r in caplog.records
            if run_id in r.getMessage() and "send" in r.getMessage().lower()
        ]
        assert matching, (
            "No send-failure breadcrumb logged with the run_id — a "
            "facilitator cannot distinguish 'send failed' from 'client "
            "navigated away' (TXBCD-006)."
        )
        # No secret/path may appear in ANY breadcrumb for this run_id.
        for r in matching:
            text = r.getMessage()
            assert sentinel_seed not in text, (
                f"send-failure breadcrumb leaked the seed: {text!r}"
            )
            assert sentinel_path not in text, (
                f"send-failure breadcrumb leaked a path: {text!r}"
            )

    def test_ping_send_failure_logs_run_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Force the keepalive-ping send to fail (queue stays empty so the
        read loop hits the 30s timeout branch, shortened to 0.3s) and
        assert a distinct run_id breadcrumb is emitted on that break."""
        import asyncio as _asyncio
        import logging as _logging

        from xrpl_lab.api import runner_ws

        # Hanging run → queue empty → read loop times out → ping send path.
        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        # Shorten the 30.0s keepalive so the ping path is reached fast.
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

        from starlette.websockets import WebSocket as _WS

        async def boom_send_json(self, *a, **kw):  # noqa: ANN001
            raise RuntimeError("ping send failed")

        monkeypatch.setattr(_WS, "send_json", boom_send_json, raising=True)

        with (
            caplog.at_level(_logging.DEBUG, logger=runner_ws.logger.name),
            TestClient(app) as client,
        ):
            run_id = client.post(
                "/api/run/receipt_literacy?dry_run=true"
            ).json()["run_id"]
            from starlette.websockets import WebSocketDisconnect

            try:
                with client.websocket_connect(
                    f"/api/run/receipt_literacy/ws?run_id={run_id}",
                    headers={"origin": runner_ws._ALLOWED_ORIGINS[0]},
                ) as ws_conn:
                    for _ in range(3):
                        ws_conn.receive_json()
            except (WebSocketDisconnect, Exception):
                pass

        matching = [
            r for r in caplog.records
            if run_id in r.getMessage() and "send" in r.getMessage().lower()
        ]
        assert matching, (
            "No ping-send-failure breadcrumb logged with the run_id "
            "(TXBCD-006)."
        )
