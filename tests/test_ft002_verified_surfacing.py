"""FT-002 — surface verified status where humans look.

Stage C added ``CompletedModule.verified: bool`` (state.py) plus per-module
``verified`` and top-level ``all_verified`` to the sealed proof pack. But that
status was INVISIBLE in ``xrpl-lab status`` / ``list`` / ``tracks`` and in
``/api/status`` / ``/api/modules`` — a learner could complete every module with
a FAILED on-ledger verification and see all-green "✓ done" everywhere except
``proof verify``. This feature makes it visible.

Contract pinned here:

* **workshop** — ``get_learner_status`` exposes per-completed-module ``verified``
  (via ``LearnerStatus.unverified_modules``) and a learner-level
  ``all_verified: bool`` (True iff every completed module is verified).
* **/api/status** — ``StatusResponse.all_verified`` mirrors the workshop value.
* **/api/modules** — ``ModuleSummary.verified`` mirrors the completed module's
  flag (a not-completed module is ``verified=True`` — irrelevant/default).
* **CLI status** — surfaces an "UNVERIFIED" indicator (glyph + label, not
  hue-only) when ``all_verified`` is False; silent when all verified.

Run in isolation:

    python -m pytest tests/test_ft002_verified_surfacing.py -q
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from xrpl_lab.cli import main
from xrpl_lab.server import create_app
from xrpl_lab.state import CompletedModule, LabState
from xrpl_lab.workshop import get_learner_status

# A real module id from the curriculum — keeps the completed-module projection
# consistent with load_all_modules() so track/next math is realistic.
_MOD = "receipt_literacy"


def _state(*, verified: bool, wallet: str | None = "rTestAddr123") -> LabState:
    """A LabState with one completed module whose ``verified`` flag is set."""
    return LabState(
        wallet_address=wallet,
        completed_modules=[
            CompletedModule(
                module_id=_MOD,
                completed_at=time.time(),
                verified=verified,
            )
        ],
    )


# ── workshop: get_learner_status exposes verified + all_verified ──────


class TestWorkshopVerifiedProjection:
    def test_unverified_completed_module_sets_all_verified_false(self) -> None:
        ls = get_learner_status(_state(verified=False))
        assert ls.all_verified is False
        assert _MOD in ls.unverified_modules
        # to_dict carries the fields for the JSON/status --json consumers.
        d = ls.to_dict()
        assert d["all_verified"] is False
        assert _MOD in d["unverified_modules"]

    def test_all_verified_completed_module_sets_all_verified_true(self) -> None:
        ls = get_learner_status(_state(verified=True))
        assert ls.all_verified is True
        assert ls.unverified_modules == []
        assert ls.to_dict()["all_verified"] is True

    def test_empty_state_is_all_verified_true(self) -> None:
        # No completed modules → vacuously all-verified (no warning surface).
        ls = get_learner_status(LabState(wallet_address="rTestAddr123"))
        assert ls.all_verified is True
        assert ls.unverified_modules == []


# ── /api/status + /api/modules ────────────────────────────────────────


def _api_client(
    state: LabState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """TestClient whose load_state returns the given in-memory state.

    Mirrors test_server.py's ``client_with_modules`` injection pattern — the
    real curriculum modules are used, but state is a fixed in-memory object so
    the verified flags are controlled by the test.
    """
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)
    # workshop.get_learner_status calls load_state() when state is None; here
    # get_status passes state explicitly, so patching routes.load_state suffices.
    return TestClient(create_app())


class TestApiStatusAllVerified:
    def test_unverified_module_makes_status_all_verified_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _api_client(_state(verified=False), tmp_path, monkeypatch)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["all_verified"] is False

    def test_all_verified_state_makes_status_all_verified_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _api_client(_state(verified=True), tmp_path, monkeypatch)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["all_verified"] is True


class TestApiModulesVerified:
    def test_unverified_completed_module_has_verified_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _api_client(_state(verified=False), tmp_path, monkeypatch)
        resp = client.get("/api/modules")
        assert resp.status_code == 200
        by_id = {m["id"]: m for m in resp.json()}
        # The completed-but-unverified module reports verified False.
        assert by_id[_MOD]["completed"] is True
        assert by_id[_MOD]["verified"] is False
        # A NOT-completed module defaults verified True (irrelevant/back-compat).
        other = next(m for mid, m in by_id.items() if not m["completed"])
        assert other["verified"] is True

    def test_verified_completed_module_has_verified_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _api_client(_state(verified=True), tmp_path, monkeypatch)
        resp = client.get("/api/modules")
        assert resp.status_code == 200
        by_id = {m["id"]: m for m in resp.json()}
        assert by_id[_MOD]["completed"] is True
        assert by_id[_MOD]["verified"] is True


# ── CLI: xrpl-lab status surfaces the unverified indicator ────────────


class TestCliStatusUnverifiedIndicator:
    def test_unverified_module_surfaces_indicator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "xrpl_lab.workshop.load_state", lambda: _state(verified=False)
        )
        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        # Honest, glyph + label (not hue-only). Word "UNVERIFIED" is the anchor.
        assert "UNVERIFIED" in result.output

    def test_all_verified_state_shows_no_unverified_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "xrpl_lab.workshop.load_state", lambda: _state(verified=True)
        )
        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "UNVERIFIED" not in result.output

    def test_status_json_carries_all_verified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as _json

        monkeypatch.setattr(
            "xrpl_lab.workshop.load_state", lambda: _state(verified=False)
        )
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["all_verified"] is False
        assert _MOD in data["unverified_modules"]
