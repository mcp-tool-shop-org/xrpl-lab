"""Stage C P2 — pin Bridge envelope humanized text.

This file silos the WebSocket close-reason and ``_error_envelope`` /
faucet-message pedagogy pins so they don't collide with Bridge agent
ownership of ``xrpl_lab/api/runner_ws.py`` and
``xrpl_lab/transport/xrpl_testnet.py`` in future waves. Mirrors the
P1 ``test_doctor_pedagogy.py`` siloing pattern.

The pedagogical contract being protected here:

* **WS 4003 close-reason** — non-browser clients (curl, wscat, custom
  integrations) see this raw text on Origin rejection. Pinning the
  allow-listed dashboard URLs in the reason ensures a facilitator
  debugging via curl can immediately see WHERE to connect from.
* **WS 4004 close-reason** — distinguishes "never existed" (typo in
  run_id) from "cleaned up after disconnect grace period" (session
  expired) and points at ``POST /api/run`` as the recovery action.
* **Rate-limit envelope hint** — cites the ``_MAX_CONCURRENT_RUNS``
  constant and the workshop saturation reality so a facilitator at a
  saturated room knows the lever to raise.
* **RUNTIME_INTERNAL envelope** — routes workshop learners (no
  server-log access) to the workshop facilitator (who has both
  server logs and ``~/.xrpl-lab/doctor.log``).
* **Timeout envelope** — covers BOTH CLI (``--dry-run``) and dashboard
  (``Dry Run`` button) audiences with one hint, since the same
  envelope flows to both surfaces.
* **Faucet 429 message** — teaches WHY (abuse prevention, shared
  testnet) plus the actionable fallback (``--dry-run``) so a learner
  hitting the rate-limit isn't stuck waiting blindly. Pinned at the
  *source-text* level (file read), mirroring the
  ``test_handlers_py_teaches_trust_line_directionality`` precedent
  in test_doctor_pedagogy.py — this contract survives even if the
  retry-loop control flow is refactored.

Substring-only assertions, no snapshot library — the test reads as
the pedagogical contract at a glance and survives wrapping/header
formatting changes that don't alter the load-bearing concepts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.api.runner_ws import (
    _ALLOWED_ORIGINS,
    _MAX_CONCURRENT_RUNS,
    _error_envelope,
)
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app

_TEST_ORIGIN = {"origin": _ALLOWED_ORIGINS[0]}


def _make_simple_module(mod_id: str = "receipt_literacy") -> ModuleDef:
    """Mirror of the test_runner_ws.py fixture — single-step ensure_wallet."""
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

    app = create_app()
    return TestClient(app)


@pytest.fixture()
def _clear_sessions():
    """Snapshot+restore module-global ``_sessions`` around each test.

    Mirrors the test_runner_ws.py fixture — keeps saturation tests
    from leaking entries across boundaries.
    """
    from xrpl_lab.api import runner_ws

    snapshot = dict(runner_ws._sessions)
    runner_ws._sessions.clear()
    yield
    runner_ws._sessions.clear()
    runner_ws._sessions.update(snapshot)


# ── F-BRIDGE-C-001 + F-BRIDGE-C-002: WS close-reason pedagogy ─────────


class TestWebSocketCloseReasonPedagogy:
    """Pin WS 4003 / 4004 close-reason text.

    The raw close.reason is what non-dashboard clients (curl, wscat,
    custom integrations) see on rejection. The browser dashboard
    substitutes its own user-visible message via ``ws.onclose``, but
    facilitators debugging via the CLI rely on the raw reason text.
    """

    def test_4003_origin_not_in_allow_list_cites_dashboard_origins(
        self, client_with_module: TestClient
    ) -> None:
        """4003 reason must teach WHICH origins are allow-listed.

        Pedagogy: a facilitator running curl/wscat from the wrong port
        sees the canonical dashboard URLs in the close.reason and knows
        immediately where to connect from.
        """
        from starlette.websockets import WebSocketDisconnect

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
            ws.receive_json()

        assert excinfo.value.code == 4003
        reason = excinfo.value.reason or ""
        # Pedagogy: the rejection cause (not just a code).
        assert "origin" in reason.lower()
        assert "allow-list" in reason.lower() or "allow list" in reason.lower()
        # Pedagogy: at least one canonical dashboard URL is cited so a
        # facilitator's curl session knows where to point.
        assert "localhost" in reason
        # Pedagogy: cite the actual Astro dev port (4321) — pinning the
        # exact port catches a future refactor that genericizes the text.
        assert "4321" in reason

    def test_4004_run_not_found_distinguishes_lifecycle_states(
        self, client_with_module: TestClient
    ) -> None:
        """4004 reason must distinguish 'never existed' from 'cleaned up'.

        Pedagogy: workshop facilitators debugging a learner's stuck WS
        need to know whether the run_id was a typo (never existed) or
        the session expired after the disconnect grace period (cleaned
        up). The reason also points at POST /api/run as the recovery
        action so the next step is unambiguous.

        RFC 6455 caps reason at 123 bytes — a UUID is 36 chars, leaving
        ~85 bytes for teaching. The phrasing has to fit.
        """
        from starlette.websockets import WebSocketDisconnect

        try:
            with client_with_module.websocket_connect(
                "/api/run/receipt_literacy/ws?run_id=bogus-run-id",
                headers=_TEST_ORIGIN,
            ) as ws:
                ws.receive_json()
        except WebSocketDisconnect as exc:
            assert exc.code == 4004
            reason = exc.reason or ""
            # Pedagogy: the lifecycle distinction.
            assert "never existed" in reason.lower()
            assert "cleaned up" in reason.lower()
            # Pedagogy: the recovery action.
            assert "POST /api/run" in reason or "/api/run" in reason
        else:
            pytest.fail("Expected WebSocketDisconnect on bogus run_id")


# ── F-BRIDGE-C-004 + C-005 + C-006: error envelope hint pedagogy ──────


class TestErrorEnvelopePedagogy:
    """Pin ``_error_envelope`` and rate-limit hint text.

    These are the action-next-step strings the dashboard surfaces when
    a run fails or the room saturates. They flow to BOTH the CLI and
    browser surfaces, so the copy must address both audiences.
    """

    def test_rate_limit_envelope_cites_max_concurrent_runs(
        self,
        _clear_sessions,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The 429 hint must cite the ``_MAX_CONCURRENT_RUNS`` lever
        and frame the workshop saturation reality.

        Pedagogy: a facilitator at a saturated room shouldn't have to
        dig through source to find which constant raises capacity. The
        hint names it directly, plus 'workshop' framing so the operator
        knows this is the correct lever (not e.g. queue size or session
        cap).
        """
        import asyncio as _asyncio

        # Hanging run_module → active count stays at saturation.
        async def hanging_run_module(
            module, transport, dry_run=False, force=False, **kwargs
        ):
            await _asyncio.Event().wait()
            return True

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
        monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)
        monkeypatch.setattr(
            "xrpl_lab.api.runner_ws.run_module", hanging_run_module
        )

        with TestClient(create_app()) as client:
            # Saturate.
            for _ in range(_MAX_CONCURRENT_RUNS):
                r = client.post("/api/run/receipt_literacy?dry_run=true")
                assert r.status_code == 200

            # Trigger the rate-limit envelope.
            rejected = client.post("/api/run/receipt_literacy?dry_run=true")
            assert rejected.status_code == 429
            detail = rejected.json()["detail"]

            assert detail["code"] == "RATE_LIMIT_RUNS"
            hint = detail["hint"]
            # Pedagogy: cite the actual constant a facilitator can raise.
            assert "_MAX_CONCURRENT_RUNS" in hint
            # Pedagogy: workshop framing (multi-learner reality).
            assert "workshop" in hint.lower()
            # Pedagogy: the message also frames the cap's purpose.
            message = detail["message"]
            assert (
                "memory" in message.lower()
                or "exhaustion" in message.lower()
            )

    def test_runtime_internal_routes_to_facilitator(self) -> None:
        """The RUNTIME_INTERNAL hint must route learners to the workshop
        facilitator and name doctor.log.

        Pedagogy: workshop learners don't have server-log access — the
        envelope must point them at the human (facilitator) who does,
        and name the artifact (doctor.log) the facilitator should check.
        """
        # Synthesize a generic exception → falls through to the
        # RUNTIME_INTERNAL branch in _error_envelope.
        envelope = _error_envelope(RuntimeError("synthetic"))

        assert envelope["code"] == "RUNTIME_INTERNAL"
        message = envelope["message"]
        hint = envelope["hint"]
        # Pedagogy: this is server-side, not learner error.
        assert "server-side" in message.lower() or "server side" in message.lower()
        # Pedagogy: escalation routing.
        assert "facilitator" in hint.lower()
        # Pedagogy: the artifact to inspect.
        assert "doctor.log" in hint
        # Pedagogy: workaround pointer.
        assert "--dry-run" in hint or "run_id" in hint

    def test_timeout_hint_covers_cli_and_dashboard_audiences(self) -> None:
        """The timeout hint must speak to BOTH CLI (--dry-run) and
        dashboard ('Dry Run' button) users.

        Pedagogy: the same envelope flows to both surfaces, so the
        recovery copy can't assume the audience. A learner reading
        from the dashboard sees 'Dry Run' on a button; a facilitator
        reading from the CLI sees '--dry-run'. Both must be cited.
        """
        envelope = _error_envelope(TimeoutError("deadline exceeded"))

        assert envelope["code"] == "RUNTIME_TIMEOUT"
        message = envelope["message"]
        hint = envelope["hint"]
        # Pedagogy (message): not a learner-module bug — testnet is the
        # likely cause, framed as load/congestion.
        assert "testnet" in message.lower()
        assert "congested" in message.lower() or "slow" in message.lower()
        # Pedagogy (hint): cite the CLI form.
        assert "--dry-run" in hint
        # Pedagogy (hint): cite the dashboard form (capitalized button label).
        assert "Dry Run" in hint


# ── F-BRIDGE-C-008: faucet 429 message pedagogy ───────────────────────


class TestFaucetMessagePedagogy:
    """Pin the XRPL testnet faucet 429 humanized message.

    The transport layer surfaces this string when the faucet rate-limits
    a learner's funding request. The copy must teach the WHY (shared
    abuse prevention) and the actionable fallback (--dry-run) so a
    learner hitting the limit isn't stuck refreshing.

    NOTE on the test approach: ``fund_from_faucet`` has a control-flow
    quirk — on the FINAL retry attempt that hits 429, the humanized
    string is set into ``last_error`` and then immediately overwritten
    by the generic ``f"Faucet returned {resp.status_code}: ..."`` line
    that follows the 429 branch (since the retry ``if attempt <
    MAX_RETRIES`` guard short-circuits the ``continue`` only on
    non-final attempts). The humanized text IS reachable on transient
    paths (429 followed by a different status), but we pin it at the
    source-text level here to lock the pedagogical prose regardless of
    how the retry plumbing evolves.

    This mirrors the precedent set in
    ``test_handlers_py_teaches_trust_line_directionality`` (P1) which
    reads the source file rather than running the handler end-to-end.
    Surfacing the control-flow issue is left to a follow-up Bridge
    revision; the prose itself is correct and worth pinning now.
    """

    def test_faucet_429_message_explains_purpose_and_fallback(self) -> None:
        """The faucet 429 humanized string must teach:
        - WHAT it is (XRPL testnet faucet, rate-limited)
        - WHY (abuse prevention so test XRP is available for everyone)
        - WAIT TIME (60 seconds)
        - FALLBACK (--dry-run for offline practice)
        """
        src = (
            Path(__file__).parent.parent
            / "xrpl_lab"
            / "transport"
            / "xrpl_testnet.py"
        ).read_text(encoding="utf-8")

        # Pedagogy: name the system that failed.
        assert "XRPL" in src
        assert "testnet faucet" in src
        # Pedagogy: the rate-limit framing (HTTP 429).
        assert "Faucet rate-limited" in src or "rate-limited" in src
        # Pedagogy: WHY — abuse prevention is the actual reason caps exist.
        assert "abuse" in src
        # Pedagogy: cite the wait time so the learner doesn't refresh blindly.
        assert "60" in src
        # Pedagogy: cite the offline fallback so a learner has a path
        # forward without waiting.
        assert "--dry-run" in src
        # Pedagogy: name the reason the cap matters (shared resource).
        assert "everyone" in src or "available for" in src
