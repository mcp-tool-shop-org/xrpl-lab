"""Wave-2 api-cli AMEND regression — F-ab18b053 (HIGH).

``start_run()``'s "was dry_run explicitly passed?" detection treated MERE
PRESENCE of either query key — ``dry_run`` (underscore, the one FastAPI
actually binds) or ``dry-run`` (hyphen) — as proof the caller "explicitly
specified a value" and, on that basis alone, skipped the fallback to
``request.app.state.dry_run`` (the server-wide safety default set by
``xrpl-lab serve --dry-run``).

But the FastAPI route parameter is literally named ``dry_run`` with no
``Query(alias=...)`` — ONLY the underscore key ever binds to it. Posting
``?dry-run=true`` (a natural mistake: the CLI's own flag is spelled
``--dry-run``) leaves the bound ``dry_run`` parameter at its literal
default (``False``) AND, because the hyphen key is merely PRESENT in the
parsed query params, skips the app.state fallback that would otherwise
have caught the omission. The hyphenated key's value never binds to
anything, so its presence could ONLY ever produce a false "explicit"
signal — reopening the exact hole F-9936b28c fixed (a True
``--dry-run`` safety default silently defeated, and the run executes LIVE
against testnet), via key-spelling instead of substring-matching.

Fixed per the wave-2 advisor contract: the hyphen key is now read
explicitly and folded in as an alias of ``dry_run`` when the canonical key
is absent; an unparseable value fails closed with 400 rather than being
silently guessed at or silently ignored. The three required behaviours
(unchanged): missing key -> app.state.dry_run fallback; ``dry_run=true``
-> dry; ``dry_run=false`` -> live. The new, closed-here behaviour:
``dry-run`` (hyphen) -> alias of ``dry_run``, or 400 — but NEVER a route
where the key's presence alone defeats the safety fallback while its
value silently fails to bind.

This file also repairs
``tests/test_reswarm4_api.py::TestDryRunSubstringFalsePositive::
test_dash_spelled_key_is_checked_as_exact_key_not_substring``, which
asserted the BROKEN terminal behaviour (``session.dry_run is False``
even against a True app-level default) as if it were merely an
incidental, harmless detail.

Run in isolation:
    python -m pytest tests/test_w2_api_cli_dry_run.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app


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
    """Snapshot/restore runner_ws._sessions — module-level global state
    shared across every test file in the process (mirrors the identical
    fixture in tests/test_reswarm4_api.py, kept local/self-contained here
    since tests/ is a shared surface this wave)."""
    from xrpl_lab.api import runner_ws

    snapshot = dict(runner_ws._sessions)
    runner_ws._sessions.clear()
    yield
    runner_ws._sessions.clear()
    runner_ws._sessions.update(snapshot)


@pytest.fixture()
def _client_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Returns a factory building a TestClient for a given app-level
    dry_run default, with a single mocked module and state/workspace
    redirected to tmp_path — mirrors test_reswarm4_api.py's
    client_with_module fixture."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {"receipt_literacy": _make_simple_module("receipt_literacy")}
    monkeypatch.setattr("xrpl_lab.api.runner_ws.load_all_modules", lambda: mods)

    def _build(app_dry_run_default: bool) -> TestClient:
        return TestClient(create_app(dry_run=app_dry_run_default))

    return _build


@pytest.mark.usefixtures("_clear_sessions")
class TestDryRunHyphenKeyFailsClosed:
    def test_hyphenated_key_does_not_defeat_true_safety_default(
        self, _client_factory
    ) -> None:
        """The dangerous case: operator runs with a True app-level
        --dry-run safety default. A caller spells the query flag the same
        way the CLI does (``?dry-run=true``), which does not bind to the
        FastAPI ``dry_run`` parameter. The run must still resolve to
        dry_run=True (aliasing) or be rejected outright (400) — it must
        NEVER silently fall through to a LIVE run.
        """
        from xrpl_lab.api import runner_ws

        client = _client_factory(True)
        resp = client.post("/api/run/receipt_literacy?dry-run=true")

        if resp.status_code == 400:
            return  # fail-closed via rejection also satisfies the contract
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        session = runner_ws._sessions[run_id]
        assert session.dry_run is True, (
            "?dry-run=true silently produced a LIVE run (session.dry_run "
            "is False) despite a True app-level --dry-run safety default "
            "-- the hyphenated key's mere presence defeated the fallback "
            "while its value never bound to anything."
        )

    def test_hyphenated_key_true_overrides_false_default(
        self, _client_factory
    ) -> None:
        """Mirrors test_explicit_dry_run_true_query_key_overrides_false_default
        for the hyphen spelling: if honoured as an alias, it must actually
        flip a False app-level default to a dry run — not merely fail to
        defeat a True one."""
        from xrpl_lab.api import runner_ws

        client = _client_factory(False)
        resp = client.post("/api/run/receipt_literacy?dry-run=true")

        if resp.status_code == 400:
            pytest.skip("dry-run alias rejected with 400 (accepted contract outcome)")
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        session = runner_ws._sessions[run_id]
        assert session.dry_run is True

    def test_unparseable_hyphenated_value_fails_closed(
        self, _client_factory
    ) -> None:
        """A garbage value for the alias must never be silently coerced
        into a truthy/falsy guess -- fail closed (400/422) rather than
        risk a live run from a typo."""
        client = _client_factory(True)
        resp = client.post("/api/run/receipt_literacy?dry-run=maybe")

        assert resp.status_code in (400, 422), (
            f"expected fail-closed 400/422 for an unparseable 'dry-run' "
            f"value, got {resp.status_code}: {resp.text}"
        )

    def test_canonical_key_wins_when_both_spellings_present(
        self, _client_factory
    ) -> None:
        """When both spellings are present with conflicting values, the
        canonical (FastAPI-bound) ``dry_run`` key must win — the alias
        must never override an explicit canonical value."""
        from xrpl_lab.api import runner_ws

        client = _client_factory(True)
        resp = client.post(
            "/api/run/receipt_literacy?dry_run=false&dry-run=true"
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        session = runner_ws._sessions[run_id]
        assert session.dry_run is False, (
            "explicit canonical ?dry_run=false must win over the "
            "?dry-run=true alias, not be overridden by it"
        )

    def test_missing_both_keys_still_falls_back_to_app_state(
        self, _client_factory
    ) -> None:
        """Unchanged baseline behaviour: neither key present -> fall back
        to request.app.state.dry_run."""
        from xrpl_lab.api import runner_ws

        client = _client_factory(True)
        resp = client.post("/api/run/receipt_literacy")
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        session = runner_ws._sessions[run_id]
        assert session.dry_run is True
