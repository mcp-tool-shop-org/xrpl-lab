"""API contract tests — enforce response schemas using Pydantic models.

These tests prove that every API response can be deserialized into
the canonical Pydantic model without error. Field drift is caught
at test time, not at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.api.schemas import (
    DoctorCheck,
    DoctorResponse,
    ModuleDetail,
    ModuleSummary,
    ReportDetail,
    ReportSummary,
    StatusResponse,
)
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
    for mod_id in completed or []:
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


# ── GET /api/status — Pydantic model validation ───────────────────────


class TestStatusSchema:
    """Every status response must deserialize into StatusResponse."""

    def test_status_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_status_validates_against_pydantic_model(self, client: TestClient) -> None:
        data = client.get("/api/status").json()
        model = StatusResponse(**data)
        # Round-trip: model fields match response keys
        assert set(data.keys()) == set(model.model_dump().keys())

    def test_status_counts_are_consistent(self, client: TestClient) -> None:
        data = client.get("/api/status").json()
        model = StatusResponse(**data)
        assert model.modules_completed <= model.modules_total
        assert model.modules_total >= 0

    def test_status_no_old_field_names(self, client: TestClient) -> None:
        """Old field names completed_modules and total_modules must NOT appear."""
        data = client.get("/api/status").json()
        assert "completed_modules" not in data
        assert "total_modules" not in data
        assert "version" not in data
        assert "network" not in data


# ── GET /api/modules — Pydantic model validation ──────────────────────


class TestModulesListSchema:
    """Every module summary must deserialize into ModuleSummary."""

    def test_modules_returns_list(self, client: TestClient) -> None:
        data = client.get("/api/modules").json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_each_module_validates_against_pydantic_model(self, client: TestClient) -> None:
        data = client.get("/api/modules").json()
        for item in data:
            model = ModuleSummary(**item)
            assert model.id and model.title

    def test_module_list_must_not_have_old_time_field(self, client: TestClient) -> None:
        """The old 'time' key must NOT appear in list items."""
        data = client.get("/api/modules").json()
        for mod in data:
            assert "time" not in mod, f"Module {mod['id']} still has old 'time' field"


# ── GET /api/modules/{id} — Pydantic model validation ─────────────────


class TestModuleDetailSchema:
    """Module detail must deserialize into ModuleDetail."""

    def test_module_detail_validates_against_pydantic_model(self, client: TestClient) -> None:
        data = client.get("/api/modules/receipt_literacy").json()
        model = ModuleDetail(**data)
        assert model.id == "receipt_literacy"
        assert model.description
        assert isinstance(model.steps, list) and len(model.steps) > 0

    def test_module_detail_steps_are_strings(self, client: TestClient) -> None:
        """Each step must be a plain string, NOT a dict."""
        data = client.get("/api/modules/receipt_literacy").json()
        model = ModuleDetail(**data)
        for step in model.steps:
            assert isinstance(step, str)

    def test_module_detail_has_canonical_list_fields(self, client: TestClient) -> None:
        data = client.get("/api/modules/receipt_literacy").json()
        model = ModuleDetail(**data)
        assert isinstance(model.prerequisites, list)
        assert isinstance(model.artifacts, list)
        assert isinstance(model.checks, list)

    def test_module_detail_must_not_have_old_field_names(self, client: TestClient) -> None:
        """Old field names 'time', 'requires', 'produces' must NOT appear."""
        data = client.get("/api/modules/receipt_literacy").json()
        assert "time" not in data
        assert "requires" not in data
        assert "produces" not in data

    def test_module_detail_404_for_unknown(self, client: TestClient) -> None:
        resp = client.get("/api/modules/nonexistent_xyz_999")
        assert resp.status_code == 404


# ── GET /api/doctor — Pydantic model validation ──────────────────────


class TestDoctorSchema:
    """Doctor response must deserialize into DoctorResponse."""

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

    def test_doctor_validates_against_pydantic_model(self, doctor_client: TestClient) -> None:
        data = doctor_client.get("/api/doctor").json()
        model = DoctorResponse(**data)
        assert model.overall in ("healthy", "warning", "error")

    def test_doctor_checks_validate_against_pydantic_model(self, doctor_client: TestClient) -> None:
        data = doctor_client.get("/api/doctor").json()
        model = DoctorResponse(**data)
        assert isinstance(model.checks, list)
        for check in model.checks:
            assert isinstance(check, DoctorCheck)
            assert check.status in ("pass", "warn", "fail")
            assert isinstance(check.name, str)
            assert isinstance(check.message, str)

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

    def test_reports_validate_against_pydantic_model(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """If reports exist, each must deserialize into ReportSummary."""
        # Create a fake report so we have data to validate
        ws = tmp_path / "ws"
        reports_dir = ws / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "test_module.md").write_text(
            "# Test Report\nSome content.", encoding="utf-8",
        )

        data = client.get("/api/artifacts/reports").json()
        assert len(data) >= 1
        for item in data:
            model = ReportSummary(**item)
            assert model.title
            assert model.content

    def test_report_detail_returns_404_for_missing(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/reports/nonexistent_module_xyz")
        assert resp.status_code == 404

    def test_report_detail_validates_against_pydantic_model(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """An existing report must deserialize into ReportDetail."""
        ws = tmp_path / "ws"
        reports_dir = ws / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "my_module.md").write_text("Report body.", encoding="utf-8")

        data = client.get("/api/artifacts/reports/my_module").json()
        model = ReportDetail(**data)
        assert model.module_id == "my_module"
        assert model.content == "Report body."
