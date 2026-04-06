"""B4 Product Proving — end-to-end smoke tests for the full user lifecycle.

These tests prove the product works as a user would experience it:
1. App boots and serves responses
2. Status endpoint returns consistent data
3. Module list → module detail → steps are walkable
4. Doctor returns actionable diagnostics
5. Artifacts (proof-pack, certificate, reports) render
6. Dry-run POST starts a run and returns a run_id
7. Packaging: all expected modules are importable
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.server import create_app
from xrpl_lab.state import LabState

# ── Helpers ─────────────────────────────────────────────────────────


def _make_module(mod_id: str, order: int = 1) -> ModuleDef:
    return ModuleDef(
        id=mod_id,
        title=f"Module {mod_id}",
        time="10 min",
        level="beginner",
        requires=[],
        produces=["wallet"],
        checks=["wallet ok"],
        steps=[
            ModuleStep(text="Step one", action="ensure_wallet", action_args={}),
            ModuleStep(text="Step two", action=None, action_args={}),
        ],
        raw_body="Full body text for this module.",
        order=order,
    )


def _make_state(completed: list[str] | None = None) -> LabState:
    state = LabState()
    state.wallet_address = "rSmokeTestAddr"
    for mod_id in completed or []:
        state.complete_module(mod_id)
    return state


@pytest.fixture()
def smoke_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Full-featured test client with 3 modules, 1 completed."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)

    mods = {
        "wallet_basics": _make_module("wallet_basics", 1),
        "send_xrp": _make_module("send_xrp", 2),
        "trust_lines": _make_module("trust_lines", 3),
    }
    state = _make_state(completed=["wallet_basics"])

    monkeypatch.setattr("xrpl_lab.api.routes.load_all_modules", lambda: mods)
    monkeypatch.setattr("xrpl_lab.api.routes.load_state", lambda: state)
    monkeypatch.setattr(
        "xrpl_lab.api.runner_ws.load_all_modules", lambda: mods,
    )

    # Create a report file so artifacts/reports has data
    reports_dir = ws / "reports"
    reports_dir.mkdir()
    (reports_dir / "wallet_basics.md").write_text(
        "# Wallet Basics Report\nCompleted successfully.",
        encoding="utf-8",
    )

    return TestClient(create_app())


# ── 1. App boots ────────────────────────────────────────────────────


class TestAppBoots:
    """The app must start and serve basic responses."""

    def test_openapi_schema_loads(self, smoke_client: TestClient) -> None:
        resp = smoke_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "XRPL Lab"

    def test_status_endpoint_responds(self, smoke_client: TestClient) -> None:
        assert smoke_client.get("/api/status").status_code == 200


# ── 2. Status consistency ──────────────────────────────────────────


class TestStatusConsistency:
    """Status must reflect actual state accurately."""

    def test_completed_count_matches(self, smoke_client: TestClient) -> None:
        data = smoke_client.get("/api/status").json()
        assert data["modules_completed"] == 1
        assert data["modules_total"] == 3

    def test_wallet_configured(self, smoke_client: TestClient) -> None:
        data = smoke_client.get("/api/status").json()
        assert data["wallet_configured"] is True
        assert data["wallet_address"] == "rSmokeTestAddr"

    def test_last_run_present(self, smoke_client: TestClient) -> None:
        data = smoke_client.get("/api/status").json()
        assert data["last_run"] is not None
        assert data["last_run"]["module"] == "wallet_basics"
        assert data["last_run"]["success"] is True


# ── 3. Module list → detail walkthrough ────────────────────────────


class TestModuleWalkthrough:
    """A user can list modules, pick one, and see its steps."""

    def test_module_list_has_all_modules(
        self, smoke_client: TestClient,
    ) -> None:
        data = smoke_client.get("/api/modules").json()
        ids = {m["id"] for m in data}
        assert ids == {"wallet_basics", "send_xrp", "trust_lines"}

    def test_module_detail_has_steps(
        self, smoke_client: TestClient,
    ) -> None:
        data = smoke_client.get("/api/modules/send_xrp").json()
        assert data["id"] == "send_xrp"
        assert len(data["steps"]) == 2
        assert all(isinstance(s, str) for s in data["steps"])

    def test_completed_module_marked(
        self, smoke_client: TestClient,
    ) -> None:
        data = smoke_client.get("/api/modules").json()
        completed = {m["id"]: m["completed"] for m in data}
        assert completed["wallet_basics"] is True
        assert completed["send_xrp"] is False


# ── 4. Doctor diagnostics ──────────────────────────────────────────


class TestDoctorSmoke:
    """Doctor endpoint must return actionable diagnostics."""

    @pytest.fixture()
    def doctor_client(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> TestClient:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        from xrpl_lab.doctor import Check, DoctorReport

        fake_report = DoctorReport(
            checks=[Check("Wallet", True, "Found", "")],
        )

        async def _fake() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod

        monkeypatch.setattr(routes_mod, "run_doctor", _fake)
        return TestClient(create_app())

    def test_doctor_returns_overall_and_checks(
        self, doctor_client: TestClient,
    ) -> None:
        data = doctor_client.get("/api/doctor").json()
        assert data["overall"] in ("healthy", "warning", "error")
        assert len(data["checks"]) >= 1
        assert data["checks"][0]["status"] in ("pass", "warn", "fail")


# ── 5. Artifacts render ────────────────────────────────────────────


class TestArtifactsSmoke:
    """Proof pack, certificate, and reports must render."""

    def test_proof_pack_shape(self, smoke_client: TestClient) -> None:
        data = smoke_client.get("/api/artifacts/proof-pack").json()
        assert data["xrpl_lab_proof_pack"] is True
        assert "sha256" in data

    def test_certificate_shape(self, smoke_client: TestClient) -> None:
        data = smoke_client.get("/api/artifacts/certificate").json()
        assert data["xrpl_lab_certificate"] is True
        assert "sha256" in data

    def test_reports_list_has_content(
        self, smoke_client: TestClient,
    ) -> None:
        data = smoke_client.get("/api/artifacts/reports").json()
        assert len(data) >= 1
        assert data[0]["title"]
        assert data[0]["content"]

    def test_report_detail_renders(
        self, smoke_client: TestClient,
    ) -> None:
        data = smoke_client.get(
            "/api/artifacts/reports/wallet_basics",
        ).json()
        assert data["module_id"] == "wallet_basics"
        assert "Wallet Basics" in data["content"]


# ── 6. Dry-run start ───────────────────────────────────────────────


class TestDryRunStart:
    """POST /api/run/{id}?dry_run=true must return a run_id."""

    def test_start_run_returns_run_id(
        self, smoke_client: TestClient,
    ) -> None:
        resp = smoke_client.post(
            "/api/run/wallet_basics?dry_run=true",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "started"

    def test_start_run_unknown_module_404(
        self, smoke_client: TestClient,
    ) -> None:
        resp = smoke_client.post("/api/run/nonexistent?dry_run=true")
        assert resp.status_code == 404


# ── 7. Packaging — importability ────────────────────────────────────


class TestPackagingSmoke:
    """All expected top-level modules must be importable."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "xrpl_lab",
            "xrpl_lab.server",
            "xrpl_lab.runner",
            "xrpl_lab.state",
            "xrpl_lab.doctor",
            "xrpl_lab.modules",
            "xrpl_lab.reporting",
            "xrpl_lab.cli",
            "xrpl_lab.api.routes",
            "xrpl_lab.api.schemas",
            "xrpl_lab.api.runner_ws",
            "xrpl_lab.transport.base",
            "xrpl_lab.transport.dry_run",
            "xrpl_lab.transport.xrpl_testnet",
        ],
    )
    def test_module_importable(self, module_path: str) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        assert mod is not None
