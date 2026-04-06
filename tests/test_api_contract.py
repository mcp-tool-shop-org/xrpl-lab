"""API contract tests — enforce canonical response schemas for every endpoint.

These tests validate structural guarantees that the frontend depends on.
If a field is renamed, removed, or changes type, these tests catch it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.doctor import Check, DoctorReport
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app
from xrpl_lab.state import LabState

# ── Helpers ──────────────────────────────────────────────────────────


def _make_module(mod_id: str = "receipt_literacy", order: int = 1) -> ModuleDef:
    return ModuleDef(
        id=mod_id,
        title="Receipt Literacy",
        time="15 min",
        level="beginner",
        requires=["wallet_basics"],
        produces=["wallet"],
        checks=["wallet created"],
        steps=[
            ModuleStep(text="Step one text", action="ensure_wallet", action_args={}),
            ModuleStep(text="Step two text", action="submit_payment", action_args={"amount": "10"}),
        ],
        raw_body="Full module body description.",
        order=order,
    )


def _make_state(completed: list[str] | None = None) -> LabState:
    state = LabState()
    state.wallet_address = "rTestAddress123"
    for mod_id in (completed or []):
        state.complete_module(mod_id)
    return state


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect state and workspace to temp dirs."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)


@pytest.fixture()
def client(
    _env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """TestClient with mocked modules and completed state."""
    mods = {
        "receipt_literacy": _make_module("receipt_literacy", order=1),
        "failure_literacy": _make_module("failure_literacy", order=2),
    }
    state = _make_state(completed=["receipt_literacy"])
    monkeypatch.setattr("xrpl_lab.api.routes.load_all_modules", lambda: mods)
    monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)

    return TestClient(create_app())


# ── GET /api/status — schema contract ────────────────────────────────


class TestStatusSchema:
    """The status endpoint must return: modules_completed (int),
    modules_total (int), wallet_configured (bool), wallet_address (str|None),
    last_run (dict|None), workspace (str)."""

    def test_status_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_status_schema_required_fields(self, client: TestClient) -> None:
        data = client.get("/api/status").json()
        assert isinstance(data["modules_completed"], int)
        assert isinstance(data["modules_total"], int)
        assert isinstance(data["wallet_configured"], bool)
        # wallet_address may be str or None
        assert data["wallet_address"] is None or isinstance(data["wallet_address"], str)
        # last_run may be dict or None
        assert data["last_run"] is None or isinstance(data["last_run"], (dict, str))
        assert isinstance(data["workspace"], str)

    def test_status_counts_are_consistent(self, client: TestClient) -> None:
        data = client.get("/api/status").json()
        assert data["modules_completed"] <= data["modules_total"]
        assert data["modules_total"] >= 0

    def test_status_no_old_field_names(self, client: TestClient) -> None:
        """Old field names completed_modules and total_modules must NOT appear."""
        data = client.get("/api/status").json()
        assert "completed_modules" not in data
        assert "total_modules" not in data
        assert "version" not in data  # moved out of status
        assert "network" not in data  # moved out of status


# ── GET /api/modules — schema contract ───────────────────────────────


class TestModulesListSchema:
    """Each module summary must have: id, title, level, time_estimate,
    completed, checks, requires, produces."""

    REQUIRED_KEYS = {"id", "title", "level", "time_estimate", "completed", "checks"}

    def test_modules_returns_list(self, client: TestClient) -> None:
        data = client.get("/api/modules").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_module_item_has_all_required_keys(self, client: TestClient) -> None:
        data = client.get("/api/modules").json()
        for mod in data:
            missing = self.REQUIRED_KEYS - set(mod.keys())
            assert not missing, f"Module {mod.get('id', '?')} missing keys: {missing}"

    def test_module_item_field_types(self, client: TestClient) -> None:
        data = client.get("/api/modules").json()
        for mod in data:
            assert isinstance(mod["id"], str) and len(mod["id"]) > 0
            assert isinstance(mod["title"], str) and len(mod["title"]) > 0
            assert isinstance(mod["level"], str)
            assert isinstance(mod["time_estimate"], str)
            assert isinstance(mod["completed"], bool)
            assert isinstance(mod["checks"], list)

    def test_module_list_must_not_have_old_time_field(self, client: TestClient) -> None:
        """The old 'time' key must NOT appear in list items."""
        data = client.get("/api/modules").json()
        for mod in data:
            assert "time" not in mod, f"Module {mod['id']} still has old 'time' field"


# ── GET /api/modules/{id} — schema contract ──────────────────────────


class TestModuleDetailSchema:
    """Module detail must have: id, title, level, time_estimate, completed,
    description (non-empty), prerequisites, artifacts, checks,
    steps (list of strings)."""

    def test_module_detail_has_steps_as_strings(self, client: TestClient) -> None:
        data = client.get("/api/modules/receipt_literacy").json()
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0

    def test_module_detail_steps_are_strings(self, client: TestClient) -> None:
        """Each step must be a plain string, NOT a dict."""
        data = client.get("/api/modules/receipt_literacy").json()
        for i, step in enumerate(data["steps"]):
            assert isinstance(step, str), (
                f"Step {i} should be str, got {type(step).__name__}"
            )

    def test_module_detail_has_description(self, client: TestClient) -> None:
        data = client.get("/api/modules/receipt_literacy").json()
        assert "description" in data
        assert isinstance(data["description"], str)
        assert len(data["description"]) > 0

    def test_module_detail_has_canonical_list_fields(self, client: TestClient) -> None:
        data = client.get("/api/modules/receipt_literacy").json()
        assert isinstance(data["prerequisites"], list)
        assert isinstance(data["artifacts"], list)
        assert isinstance(data["checks"], list)

    def test_module_detail_must_not_have_old_field_names(self, client: TestClient) -> None:
        """Old field names 'time', 'requires', 'produces' must NOT appear."""
        data = client.get("/api/modules/receipt_literacy").json()
        assert "time" not in data, "Detail still has old 'time' field"
        assert "requires" not in data, "Detail still has old 'requires' field"
        assert "produces" not in data, "Detail still has old 'produces' field"

    def test_module_detail_404_for_unknown(self, client: TestClient) -> None:
        resp = client.get("/api/modules/nonexistent_xyz_999")
        assert resp.status_code == 404


# ── GET /api/doctor — schema contract ────────────────────────────────


class TestDoctorSchema:
    """Doctor endpoint must return: overall (str: healthy|warning|error),
    checks (list of dicts with name/status/message).
    status must be one of pass|warn|fail."""

    @pytest.fixture()
    def doctor_client(
        self,
        _env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> TestClient:
        fake_report = DoctorReport(
            checks=[
                Check("Wallet", True, "Found: rX123", ""),
                Check("State file", False, "Corrupt", "Recreate it"),
            ]
        )

        async def _fake_run_doctor() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod
        monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)
        return TestClient(create_app())

    def test_doctor_has_overall(self, doctor_client: TestClient) -> None:
        data = doctor_client.get("/api/doctor").json()
        assert "overall" in data
        assert data["overall"] in ("healthy", "warning", "error")

    def test_doctor_checks_structure(self, doctor_client: TestClient) -> None:
        data = doctor_client.get("/api/doctor").json()
        assert isinstance(data["checks"], list)
        for check in data["checks"]:
            assert isinstance(check["name"], str)
            assert check["status"] in ("pass", "warn", "fail")
            assert "message" in check

    def test_doctor_no_old_field_names(self, doctor_client: TestClient) -> None:
        """Old field names must NOT appear in the doctor response."""
        data = doctor_client.get("/api/doctor").json()
        assert "all_passed" not in data
        assert "summary" not in data
        for check in data["checks"]:
            assert "passed" not in check
            assert "detail" not in check
            assert "hint" not in check


# ── GET /api/artifacts — schema contract ─────────────────────────────


class TestArtifactsSchema:
    """Proof-pack and certificate endpoints must match their documented shapes."""

    def test_proof_pack_has_required_keys(self, client: TestClient) -> None:
        data = client.get("/api/artifacts/proof-pack").json()
        assert data["xrpl_lab_proof_pack"] is True
        assert isinstance(data["completed_modules"], list)
        assert isinstance(data["transactions"], list)
        assert "sha256" in data

    def test_certificate_has_required_keys(self, client: TestClient) -> None:
        data = client.get("/api/artifacts/certificate").json()
        assert data["xrpl_lab_certificate"] is True
        assert "sha256" in data
        assert "modules_completed" in data

    def test_reports_returns_list(self, client: TestClient) -> None:
        data = client.get("/api/artifacts/reports").json()
        assert isinstance(data, list)

    def test_report_detail_returns_404_for_missing(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/reports/nonexistent_module_xyz")
        assert resp.status_code == 404
