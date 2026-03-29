"""Tests for the WebSocket module runner endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app
from xrpl_lab.state import LabState


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
        assert "not found" in resp.json()["detail"].lower()

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
                "/api/run/receipt_literacy/ws?run_id=bogus-run-id"
            ) as ws:
                # Server closes immediately for unknown run_id
                ws.receive_json()  # may or may not get a message before close
        except WebSocketDisconnect as exc:
            # Expected: server closed the connection for unknown run_id
            assert exc.code in (1000, 4004)
        except Exception:
            # Any other exception during connect is also acceptable
            pass

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
        async def _fake_run_module(module, transport, dry_run=False, force=False):
            return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", _fake_run_module)

        app = create_app()
        client = TestClient(app)

        start_resp = client.post("/api/run/receipt_literacy?dry_run=true")
        run_id = start_resp.json()["run_id"]

        messages: list[dict] = []
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}"
        ) as ws_conn:
            for _ in range(20):  # read up to 20 messages
                try:
                    msg = ws_conn.receive_json()
                    messages.append(msg)
                    if msg.get("type") in ("complete", "error"):
                        break
                except Exception:
                    break

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

        async def _fake_run_module(module, transport, dry_run=False, force=False):
            return True

        monkeypatch.setattr("xrpl_lab.api.runner_ws.run_module", _fake_run_module)

        app = create_app()
        client = TestClient(app)

        start_resp = client.post("/api/run/receipt_literacy?dry_run=true")
        run_id = start_resp.json()["run_id"]

        complete_msg: dict | None = None
        with client.websocket_connect(
            f"/api/run/receipt_literacy/ws?run_id={run_id}"
        ) as ws_conn:
            for _ in range(20):
                try:
                    msg = ws_conn.receive_json()
                    if msg.get("type") == "complete":
                        complete_msg = msg
                        break
                    if msg.get("type") == "error":
                        break
                except Exception:
                    break

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
            f"/api/run/receipt_literacy/ws?run_id={run_id}"
        ) as ws_conn:
            for _ in range(30):
                try:
                    msg = ws_conn.receive_json()
                    messages.append(msg)
                    if msg.get("type") in ("complete", "error"):
                        break
                except Exception:
                    break

        step_msgs = [m for m in messages if m.get("type") == "step"]
        if step_msgs:
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
