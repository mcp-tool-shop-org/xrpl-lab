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
    _severity_for_code,
)
from xrpl_lab.errors import LabError, LabException
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


# ── F-BRIDGE-D-001: backward-compat for envelope severity + icon_hint ─


class TestErrorEnvelopeBackwardCompat:
    """Pin Stage D wave 1's optional ``severity`` + ``icon_hint`` fields.

    Bridge's commit 557c290 added two optional fields to
    ``_error_envelope``. The contract is *additive* — existing
    consumers reading only ``{code, message, hint}`` keep working.
    These tests pin both halves of that contract:

    * The original three-field surface is preserved (backward compat).
    * The new fields map per the spec — RUNTIME_TIMEOUT/CANCELLED have
      explicit overrides; INPUT_/CONFIG_/STATE_ are warning/alert-circle;
      PARTIAL_ is info/info; IO_/DEP_/RUNTIME_/PERM_ are
      error/alert-triangle. An unmapped prefix falls back to
      error/alert-triangle so a new code never leaks an unmapped value.
    * ``severity`` is bounded to a known enum — a future typo that
      introduces a fifth value fails the test loudly rather than
      silently rendering as an unknown CSS class on the dashboard.

    These complement (not replace) the pedagogy pins in
    ``TestErrorEnvelopePedagogy`` — the pedagogy class pins WHAT the
    hint/message strings teach; this class pins the metadata SHAPE
    Bridge ships for the dashboard's visual treatment.
    """

    _KNOWN_SEVERITIES = {"info", "warning", "error", "critical"}

    def _envelope_for(self, code: str) -> dict[str, str]:
        """Build a synthetic LabException-backed envelope for ``code``."""
        return _error_envelope(
            LabException(LabError(code=code, message="msg", hint="hint"))
        )

    def test_existing_three_field_consumers_still_work(self) -> None:
        """Existing dashboard handlers reading {code, message, hint}
        must continue to work when the new fields are present.

        Asserts both that all 5 keys exist AND that subsetting to the
        original three-field surface (the pre-Stage-D consumer
        pattern) still produces a usable dict.
        """
        envelope = self._envelope_for("RUNTIME_TIMEOUT")

        # All five keys present (new fields additive).
        assert set(envelope) >= {
            "code",
            "message",
            "hint",
            "severity",
            "icon_hint",
        }

        # Backward-compat: a consumer reading only the original three
        # fields (the pre-Stage-D dashboard surface) succeeds.
        legacy_view = {k: envelope[k] for k in ("code", "message", "hint")}
        assert legacy_view["code"] == "RUNTIME_TIMEOUT"
        assert legacy_view["message"] == "msg"
        assert legacy_view["hint"] == "hint"

    @pytest.mark.parametrize(
        ("code", "expected_severity", "expected_icon"),
        [
            # Specific code overrides (precede prefix mapping).
            ("RUNTIME_TIMEOUT", "warning", "clock"),
            ("RUNTIME_CANCELLED", "info", "x-circle"),
            # F-BRIDGE-FT-002 — recoverable rate-limit, distinct from
            # generic RUNTIME_* runtime faults (error/alert-triangle).
            ("RUNTIME_FAUCET_RATE_LIMITED", "warning", "clock"),
            # User-error prefixes → warning/alert-circle.
            ("INPUT_MODULE_NOT_FOUND", "warning", "alert-circle"),
            ("CONFIG_MISSING_KEY", "warning", "alert-circle"),
            ("STATE_CORRUPT", "warning", "alert-circle"),
            # Success-with-degradation → info/info.
            ("PARTIAL_TX_FAILED", "info", "info"),
            # Runtime-fault prefixes → error/alert-triangle.
            ("RUNTIME_INTERNAL", "error", "alert-triangle"),
            ("IO_READ_FAILED", "error", "alert-triangle"),
            ("DEP_MISSING", "error", "alert-triangle"),
            ("PERM_DENIED", "error", "alert-triangle"),
        ],
    )
    def test_severity_mapping_per_code_prefix(
        self, code: str, expected_severity: str, expected_icon: str
    ) -> None:
        """The (severity, icon_hint) mapping matches Bridge's spec.

        Pinning the full table — not just a sample — so a future
        refactor of ``_severity_for_code`` that drops a prefix or
        flips a severity (e.g. STATE_ → error) trips the test rather
        than silently shifting the dashboard's color treatment.
        """
        envelope = self._envelope_for(code)
        assert envelope["severity"] == expected_severity
        assert envelope["icon_hint"] == expected_icon
        # Both helpers agree (the helper is what the envelope calls).
        assert _severity_for_code(code) == (expected_severity, expected_icon)

    def test_unknown_code_prefix_falls_back_to_error_alert_triangle(self) -> None:
        """An unmapped code prefix must NOT leak an unmapped severity.

        Pedagogy: a future ``RUNTIME_FOOBAR`` or a brand-new prefix
        added without updating the mapping renders as the safe default
        (error/alert-triangle) so the dashboard always has *some*
        valid visual treatment to apply.
        """
        envelope = self._envelope_for("ZZZ_UNKNOWN_FUTURE_CODE")
        assert envelope["severity"] == "error"
        assert envelope["icon_hint"] == "alert-triangle"

    def test_severity_is_one_of_known_enum_values(self) -> None:
        """``severity`` must always be one of the four known enum
        values across every envelope path (LabException, TimeoutError,
        CancelledError, generic Exception fallthrough).

        Catches a future regression where a typo (``"warn"`` vs
        ``"warning"``, ``"err"`` vs ``"error"``) introduces a value
        the dashboard's CSS doesn't know how to style.
        """
        import asyncio as _asyncio

        envelopes = [
            # Each branch in _error_envelope.
            _error_envelope(
                LabException(LabError(code="RUNTIME_INTERNAL", message="m", hint="h"))
            ),
            _error_envelope(TimeoutError("deadline")),
            _error_envelope(_asyncio.CancelledError()),
            _error_envelope(RuntimeError("synthetic")),  # generic fallthrough
        ]
        for env in envelopes:
            assert env["severity"] in self._KNOWN_SEVERITIES, (
                f"unknown severity {env['severity']!r} in envelope {env!r}"
            )


# ── F-BRIDGE-C-008: faucet 429 message pedagogy ───────────────────────


class TestFaucetMessagePedagogy:
    """Pin the XRPL testnet faucet 429 humanized message.

    The transport layer surfaces this string when the faucet rate-limits
    a learner's funding request. The copy must teach the WHY (shared
    abuse prevention) and the actionable fallback (--dry-run) so a
    learner hitting the limit isn't stuck refreshing.

    Two-layer pin:
    1. **Source-text pin** — file content contains the load-bearing
       phrases. Catches a future revert of the prose itself.
    2. **Runtime delivery pin** — mock 3 consecutive 429s and assert
       the returned ``FundResult.message`` contains the humanized text.
       Catches the case where prose lives in the file but doesn't
       reach callers (the control-flow defect Stage C P2 surfaced and
       wave-3 hot-fix closed: the gated ``continue`` was previously
       inside the retries-remaining branch, so on the final 429 attempt
       the humanized ``last_error`` was overwritten by the generic
       ``f"Faucet returned {status}: ..."`` fallthrough. Fix: move the
       ``continue`` outside the retries-remaining branch so the 429
       path skips the fallthrough unconditionally).
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

    @pytest.mark.asyncio
    async def test_faucet_429_humanized_message_reaches_callers_runtime(
        self, monkeypatch
    ) -> None:
        """Mock 3 consecutive 429s and assert the FundResult.message
        contains the humanized prose, not the generic fallthrough.

        This is the runtime-delivery pin (counterpart to the source-text
        pin above). It catches the wave-3 control-flow regression class
        where humanized prose lives in the file but doesn't reach the
        caller because a fallthrough overwrites ``last_error`` on the
        final retry attempt.
        """
        from unittest.mock import AsyncMock, MagicMock

        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        # Build a fake httpx response object that looks like a 429.
        fake_429 = MagicMock()
        fake_429.status_code = 429
        fake_429.text = "rate limit exceeded"

        # Build a fake AsyncClient that always returns the 429 response.
        # fund_from_faucet uses `async with httpx.AsyncClient(...) as http`
        # then `await http.post(...)`, so we mock both the context manager
        # and the post call.
        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.post = AsyncMock(return_value=fake_429)

        def _client_factory(*args, **kwargs):
            return fake_client

        # Patch httpx.AsyncClient inside the transport module's namespace.
        # fund_from_faucet imports httpx locally, so patch the actual
        # httpx.AsyncClient symbol it resolves at call time.
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

        # Also short-circuit asyncio.sleep so the test doesn't actually
        # wait through the retry backoff.
        import asyncio as _asyncio

        async def _no_sleep(_seconds):
            return None

        monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

        transport = XRPLTestnetTransport()
        result = await transport.fund_from_faucet("rTEST_ADDRESS")

        assert result.success is False
        # The runtime delivery contract: the humanized prose reaches
        # the caller, not the generic "Faucet returned 429: ..." text.
        assert "rate-limited" in result.message.lower()
        assert "abuse" in result.message
        assert "60" in result.message
        assert "--dry-run" in result.message
        # Negative assertion: the generic fallthrough must NOT win.
        assert "Faucet returned 429:" not in result.message

    @pytest.mark.asyncio
    async def test_faucet_429_populates_structured_code_on_result(
        self, monkeypatch
    ) -> None:
        """F-BRIDGE-FT-002 — 429 path tags ``FundResult.code`` with
        ``RUNTIME_FAUCET_RATE_LIMITED`` so dashboards can route to a
        rate-limit-specific UI distinct from generic network errors.

        Mirrors the runtime-delivery pin above (3 consecutive 429s) and
        adds the code-field assertion. The humanized message contract
        is preserved — both fields ship together.
        """
        from unittest.mock import AsyncMock, MagicMock

        from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

        fake_429 = MagicMock()
        fake_429.status_code = 429
        fake_429.text = "rate limit exceeded"

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.post = AsyncMock(return_value=fake_429)

        def _client_factory(*args, **kwargs):
            return fake_client

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _client_factory)

        import asyncio as _asyncio

        async def _no_sleep(_seconds):
            return None

        monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

        transport = XRPLTestnetTransport()
        result = await transport.fund_from_faucet("rTEST_ADDRESS")

        assert result.success is False
        # Structured-code contract: the dashboard reads result.code to
        # branch into the rate-limit-specific UI (clock icon, retry
        # banner, --dry-run callout).
        assert result.code == "RUNTIME_FAUCET_RATE_LIMITED", (
            f"Expected code=RUNTIME_FAUCET_RATE_LIMITED, "
            f"got code={result.code!r}"
        )
        # Humanized-message contract still upheld — both ship together.
        assert "rate-limited" in result.message.lower()
        assert "--dry-run" in result.message


# ── F-BRIDGE-PH9-001: production emission path for INPUT_MODULE_NOT_FOUND ─


class TestInputModuleNotFoundEmissionPath:
    """Pattern #3 closure: verify INPUT_MODULE_NOT_FOUND envelope reaches the
    WS consumer boundary with all 5 canonical fields (code, message, hint,
    severity, icon_hint).

    The existing parametrized test
    ``TestErrorEnvelopeBackwardCompat.test_severity_mapping_per_code_prefix
    [INPUT_MODULE_NOT_FOUND-warning-alert-circle]`` exercises
    ``_error_envelope`` in isolation — it constructs a synthetic
    ``LabException(LabError(code="INPUT_MODULE_NOT_FOUND"))`` and asserts the
    canonical producer's output. That test passed even while the production
    emission path at ``runner_ws._run_module_task`` (lines 524-529 pre-fix)
    bypassed the canonical producer and emitted a 4-field envelope missing
    ``severity`` and ``icon_hint``.

    Pattern #3 occurred three times in this swarm:
      1. Stage C P2 hot-fix — humanized faucet 429 text overwritten by
         fallthrough.
      2. Phase 8 wave 2 — RUNTIME_FAUCET_RATE_LIMITED transport→runtime gap.
      3. Phase 9 wave 1 — INPUT_MODULE_NOT_FOUND envelope manually constructed
         (this site, fixed by F-BRIDGE-PH9-001 commit 5d89ded).

    Audit-coverage rule (advisor's promoted framing):
        When ANY code path emits a structured contract surface, the test must
        exercise that emission path through the actual canonical producer,
        not the canonical producer in isolation. Tests for any new error
        code or response shape must verify (a) the canonical producer emits
        the right shape, AND (b) the production emission path actually
        invokes the canonical producer.

    This class closes the (b) half for INPUT_MODULE_NOT_FOUND: it triggers
    the production emission path (POST /api/run + background task), captures
    the actual frame at the WS consumer boundary, and asserts the canonical
    5-field shape arrives intact.

    Mirrors the
    ``test_runner_ws.TestDeleteRunEndpoint.test_delete_run_emits_cancelled_to_ws_client``
    pattern — connect WS, trigger a server-side action, drain frames, parse
    envelope, assert canonical shape.
    """

    def test_input_module_not_found_envelope_reaches_ws_with_full_5_field_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the production WS emission path for INPUT_MODULE_NOT_FOUND
        and assert the consumer-boundary frame carries all 5 canonical fields.

        Strategy: use a stateful ``load_all_modules`` patch that returns the
        module on the first call (so ``start_run``'s validation passes and
        POST /api/run/{module_id} returns 200 + run_id) and an empty dict on
        subsequent calls (so the background ``_run_module_task`` hits the
        INPUT_MODULE_NOT_FOUND branch). The WS client then drains the queue
        and we capture the actual frame at the consumer boundary.

        Without this test, a code path bypassing the canonical producer
        (manually constructing ``{type, code, message, hint}`` without
        ``severity``/``icon_hint``) would still pass the existing
        in-isolation ``test_severity_mapping_per_code_prefix`` entry but
        ship a 4-field envelope to the dashboard — the Stage D wave 1
        contract violation that F-BRIDGE-PH9-001 fixed.
        """
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws_dir)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws_dir)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws_dir)

        # Stateful load_all_modules — first call (start_run validation)
        # sees the module so POST returns 200 + a run_id; subsequent calls
        # (background _run_module_task) see an empty registry, driving the
        # INPUT_MODULE_NOT_FOUND branch. This mirrors the real-world race
        # where a module disappears between POST and task pickup, AND lets
        # the test reach the production emission path without depending on
        # POST returning 404 (which short-circuits before the WS path).
        mod = _make_simple_module("vanishing_module")
        call_count = {"n": 0}

        def _stateful_load():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"vanishing_module": mod}
            return {}

        monkeypatch.setattr(
            "xrpl_lab.api.runner_ws.load_all_modules", _stateful_load
        )

        app = create_app()
        client = TestClient(app)

        start_resp = client.post("/api/run/vanishing_module?dry_run=true")
        assert start_resp.status_code == 200, (
            f"start_run validation must pass on first load_all_modules call; "
            f"got {start_resp.status_code}: {start_resp.text}"
        )
        run_id = start_resp.json()["run_id"]

        # Drain the WS queue until we see the error frame.
        error_frame: dict | None = None
        with client.websocket_connect(
            f"/api/run/vanishing_module/ws?run_id={run_id}",
            headers=_TEST_ORIGIN,
        ) as ws_conn:
            for _ in range(20):
                try:
                    msg = ws_conn.receive_json()
                    if msg.get("type") == "error":
                        error_frame = msg
                        break
                    if msg.get("type") == "complete":
                        break
                except Exception as exc:
                    if "disconnect" in str(exc).lower() or "1000" in str(exc):
                        break
                    raise

        assert error_frame is not None, (
            "Expected an 'error' frame on the WS for INPUT_MODULE_NOT_FOUND "
            "production emission path, but none arrived."
        )

        # Contract assertion 1: the code is the one we're testing.
        assert error_frame.get("code") == "INPUT_MODULE_NOT_FOUND", (
            f"Expected code=INPUT_MODULE_NOT_FOUND at consumer boundary, "
            f"got {error_frame.get('code')!r}"
        )

        # Contract assertion 2: ALL 5 canonical envelope fields are present
        # at the consumer boundary. This is the assertion that fails if a
        # future change re-introduces the inline-dict antipattern.
        # (The "type" field is added by the WS layer; the envelope owns the
        # other five.)
        for field in ("code", "message", "hint", "severity", "icon_hint"):
            assert field in error_frame, (
                f"Canonical envelope field {field!r} missing from WS frame "
                f"at consumer boundary. Frame keys: {sorted(error_frame)}. "
                f"This indicates the production emission path bypassed "
                f"_error_envelope() and constructed the envelope inline — "
                f"the Pattern #3 antipattern that F-BRIDGE-PH9-001 fixed."
            )

        # Contract assertion 3: severity + icon_hint match the spec for the
        # INPUT_ prefix — same values asserted by the in-isolation test
        # ``test_severity_mapping_per_code_prefix[INPUT_MODULE_NOT_FOUND-...]``.
        # Pinning them here too proves the production path reaches the
        # canonical producer (not just that some 5-field envelope arrived).
        assert error_frame["severity"] == "warning"
        assert error_frame["icon_hint"] == "alert-circle"

        # Contract assertion 4: the message and hint carry the bug-fix
        # commit's exact pedagogy — the bogus module_id is named (so the
        # learner can spot the typo) and the recovery action (xrpl-lab list)
        # is cited. These come from errors.module_not_found, the canonical
        # constructor F-BRIDGE-PH9-001 routes through.
        assert "vanishing_module" in error_frame["message"]
        assert "xrpl-lab list" in error_frame["hint"]
