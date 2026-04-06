"""Tests for the FastAPI server layer."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.doctor import Check, DoctorReport
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app
from xrpl_lab.state import LabState

# ── Fixtures ──────────────────────────────────────────────────────────


def _make_module(mod_id: str = "receipt_literacy") -> ModuleDef:
    return ModuleDef(
        id=mod_id,
        title="Receipt Literacy",
        time="15 min",
        level="beginner",
        requires=[],
        produces=["wallet"],
        checks=["wallet created"],
        steps=[ModuleStep(text="Intro text", action="ensure_wallet", action_args={})],
        raw_body="",
    )


def _make_state(completed: list[str] | None = None) -> LabState:
    state = LabState()
    state.wallet_address = "rTestAddress123"
    for mod_id in (completed or []):
        state.complete_module(mod_id)
    return state


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with state/workspace redirected to tmp_path."""
    # Redirect state home to a temp dir
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    # Redirect workspace to a temp subdir
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    app = create_app()
    return TestClient(app)


@pytest.fixture()
def client_with_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with mocked modules and completed state."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {
        "receipt_literacy": _make_module("receipt_literacy"),
        "failure_literacy": _make_module("failure_literacy"),
    }
    state = _make_state(completed=["receipt_literacy"])

    monkeypatch.setattr("xrpl_lab.api.routes.load_all_modules", lambda: mods)
    monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)

    app = create_app()
    return TestClient(app)


# ── GET /api/modules ──────────────────────────────────────────────────


class TestListModules:
    def test_returns_list(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_module_has_expected_fields(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules")
        mod = next(m for m in resp.json() if m["id"] == "receipt_literacy")
        assert mod["title"] == "Receipt Literacy"
        assert mod["level"] == "beginner"
        assert mod["time_estimate"] == "15 min"
        assert isinstance(mod["requires"], list)
        assert isinstance(mod["completed"], bool)

    def test_completion_status_reflects_state(
        self, client_with_modules: TestClient
    ) -> None:
        resp = client_with_modules.get("/api/modules")
        mods = {m["id"]: m for m in resp.json()}
        assert mods["receipt_literacy"]["completed"] is True
        assert mods["failure_literacy"]["completed"] is False

    def test_empty_state_returns_empty_completed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a fresh real state and real modules the list still comes back as a list."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        monkeypatch.setattr("xrpl_lab.api.routes.load_all_modules", lambda: {})
        monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: LabState())

        app = create_app()
        resp = TestClient(app).get("/api/modules")
        assert resp.status_code == 200
        assert resp.json() == []


# ── GET /api/status ───────────────────────────────────────────────────


class TestStatus:
    def test_returns_canonical_status_fields(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "modules_completed" in data
        assert "modules_total" in data
        assert "wallet_configured" in data
        assert "workspace" in data

    def test_returns_module_counts(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/status")
        data = resp.json()
        assert data["modules_total"] == 2
        assert data["modules_completed"] == 1

    def test_returns_wallet_address(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/status")
        data = resp.json()
        assert data["wallet_address"] == "rTestAddress123"

    def test_fresh_state_has_null_last_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.load_all_modules", lambda: {})
        monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: LabState())

        app = create_app()
        resp = TestClient(app).get("/api/status")
        assert resp.status_code == 200
        assert resp.json()["last_run"] is None


# ── GET /api/modules/{module_id} ──────────────────────────────────────


class TestGetModule:
    def test_valid_id_returns_detail(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules/receipt_literacy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "receipt_literacy"
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) == 1

    def test_steps_are_strings(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules/receipt_literacy")
        steps = resp.json()["steps"]
        assert len(steps) == 1
        assert isinstance(steps[0], str)
        assert steps[0] == "Intro text"

    def test_completed_flag_on_detail(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules/receipt_literacy")
        assert resp.json()["completed"] is True

        resp2 = client_with_modules.get("/api/modules/failure_literacy")
        assert resp2.json()["completed"] is False

    def test_invalid_id_returns_404(self, client_with_modules: TestClient) -> None:
        resp = client_with_modules.get("/api/modules/nonexistent_module_xyz")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ── GET /api/artifacts/proof-pack ─────────────────────────────────────


class TestProofPack:
    def test_empty_state_returns_proof_pack_shape(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/artifacts/proof-pack")
        assert resp.status_code == 200
        data = resp.json()
        assert data["xrpl_lab_proof_pack"] is True
        assert isinstance(data["version"], str)
        assert data["completed_modules"] == []
        assert data["transactions"] == []
        assert "sha256" in data

    def test_proof_pack_with_completed_modules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        state = _make_state(completed=["receipt_literacy"])
        monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)

        app = create_app()
        resp = TestClient(app).get("/api/artifacts/proof-pack")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["completed_modules"]) == 1
        assert data["completed_modules"][0]["module_id"] == "receipt_literacy"


# ── GET /api/artifacts/certificate ────────────────────────────────────


class TestCertificate:
    def test_returns_certificate_shape(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/certificate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["xrpl_lab_certificate"] is True
        assert isinstance(data["version"], str)
        assert "sha256" in data
        assert "modules_completed" in data

    def test_certificate_lists_completed_modules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        state = _make_state(completed=["receipt_literacy", "failure_literacy"])
        monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)

        app = create_app()
        resp = TestClient(app).get("/api/artifacts/certificate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] == 2
        assert set(data["modules_completed"]) == {
            "receipt_literacy",
            "failure_literacy",
        }


# ── GET /api/artifacts/reports ────────────────────────────────────────


class TestReports:
    def test_no_reports_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_existing_reports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        reports_dir = ws / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "receipt_literacy.md").write_text("# Report", encoding="utf-8")
        (reports_dir / "failure_literacy.md").write_text("# Report 2", encoding="utf-8")
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        app = create_app()
        resp = TestClient(app).get("/api/artifacts/reports")
        assert resp.status_code == 200
        reports = resp.json()
        assert isinstance(reports, list)
        assert len(reports) == 2
        titles = [r["title"] for r in reports]
        assert "Receipt Literacy" in titles
        assert "Failure Literacy" in titles
        for r in reports:
            assert "title" in r
            assert "generated" in r
            assert "content" in r

    def test_get_report_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        reports_dir = ws / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "receipt_literacy.md").write_text(
            "# Receipt Literacy Report\n\nSome content", encoding="utf-8"
        )
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        app = create_app()
        resp = TestClient(app).get("/api/artifacts/reports/receipt_literacy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == "receipt_literacy"
        assert "Receipt Literacy Report" in data["content"]

    def test_get_report_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/reports/nonexistent_module")
        assert resp.status_code == 404

    def test_get_report_path_traversal_rejected(self, client: TestClient) -> None:
        resp = client.get("/api/artifacts/reports/..%2Fsecret")
        # FastAPI will URL-decode before routing; either 400 or 404 is acceptable
        assert resp.status_code in (400, 404)


# ── GET /api/doctor ───────────────────────────────────────────────────


class TestDoctor:
    def test_returns_checks_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        # Mock run_doctor to avoid real network calls
        fake_report = DoctorReport(
            checks=[
                Check("Wallet", False, "Not found", "Run: xrpl-lab wallet create"),
                Check("State file", True, "No state yet (fresh install)"),
                Check("Workspace", True, f"Writable: {ws}"),
                Check("RPC endpoint", True, "Connected"),
            ]
        )

        async def _fake_run_doctor() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod
        monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)

        app = create_app()
        resp = TestClient(app).get("/api/doctor")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) == 4
        assert "overall" in data
        assert data["overall"] in ("healthy", "warning", "error")

    def test_checks_have_expected_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        fake_report = DoctorReport(
            checks=[Check("Wallet", True, "Found: rX123", "")]
        )

        async def _fake_run_doctor() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod  # noqa: PLC0415
        monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)

        app = create_app()
        resp = TestClient(app).get("/api/doctor")
        check = resp.json()["checks"][0]
        assert "name" in check
        assert "status" in check
        assert "message" in check
        assert check["name"] == "Wallet"
        assert check["status"] == "pass"

    def test_overall_reflects_check_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

        fake_report = DoctorReport(
            checks=[
                Check("A", True),
                Check("B", False, "failed", "fix it"),
            ]
        )

        async def _fake_run_doctor() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod  # noqa: PLC0415
        monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)

        app = create_app()
        resp = TestClient(app).get("/api/doctor")
        data = resp.json()
        assert data["overall"] == "error"
        checks = data["checks"]
        statuses = [c["status"] for c in checks]
        assert "pass" in statuses
        assert "fail" in statuses


# ── create_app dry_run state ──────────────────────────────────────────


class TestCreateAppDryRun:
    def test_dry_run_stored_in_app_state(self) -> None:
        """create_app(dry_run=True) should store dry_run=True in app.state."""
        app = create_app(dry_run=True)
        assert app.state.dry_run is True

    def test_default_dry_run_is_false(self) -> None:
        """create_app() without arguments should default dry_run to False."""
        app = create_app()
        assert app.state.dry_run is False

    def test_dry_run_false_explicit(self) -> None:
        """create_app(dry_run=False) explicitly stores False."""
        app = create_app(dry_run=False)
        assert app.state.dry_run is False
