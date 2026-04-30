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


# ── F-TESTS-B-005: snapshot tests for downstream xrpl-camp consumers ─


class TestApiContractSnapshots:
    """Pin response shapes for the downstream xrpl-camp consumer.

    These tests use INLINE expected key sets (no third-party snapshot lib,
    no fixture file). A future reader can see the full contract at a
    glance, and a refactor that adds/removes/renames a field must update
    the inline expected dict in the same diff — making the contract
    change explicit and reviewable.

    If a future test surfaces a real production bug, xfail-strict mark
    it and flag for wave-3 — these tests do NOT modify production code.
    """

    def test_status_response_schema_locked(self, client: TestClient) -> None:
        """GET /api/status must expose exactly the documented top-level keys.

        Adding, removing, or renaming a key without updating the expected
        set fails this test loud. xrpl-camp's TS types mirror this shape.
        """
        data = client.get("/api/status").json()

        expected_keys = {
            "modules_completed",
            "modules_total",
            "wallet_configured",
            "wallet_address",
            "last_run",
            "workspace",
            "current_module",
            "current_track",
            "current_mode",
            "blockers",
            "is_blocked",
            "track_progress",
            "has_proof_pack",
            "has_certificate",
            "report_count",
        }

        actual_keys = set(data.keys())
        assert actual_keys == expected_keys, (
            f"status response key drift:\n"
            f"  added (in response, not expected): {actual_keys - expected_keys}\n"
            f"  removed (in expected, not response): {expected_keys - actual_keys}\n"
            f"  full response: {data!r}"
        )

        # Type contract — the integers are integers, the bools are bools,
        # the lists are lists. xrpl-camp's TS types depend on these.
        assert isinstance(data["modules_completed"], int)
        assert isinstance(data["modules_total"], int)
        assert isinstance(data["wallet_configured"], bool)
        assert data["wallet_address"] is None or isinstance(data["wallet_address"], str)
        assert isinstance(data["workspace"], str)
        assert isinstance(data["blockers"], list)
        assert isinstance(data["is_blocked"], bool)
        assert isinstance(data["track_progress"], list)
        assert isinstance(data["has_proof_pack"], bool)
        assert isinstance(data["has_certificate"], bool)
        assert isinstance(data["report_count"], int)

    def test_doctor_response_schema_locked(
        self, _env: None, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/doctor must expose exactly {overall, checks[]}.

        Each check item must have exactly {name, status, message}. The
        wave-1 schema migration removed legacy passed/detail/hint keys
        from the response — this test pins that removal.
        """
        # Build a deterministic doctor report for stable assertion.
        fake_report = DoctorReport(
            checks=[
                Check("Wallet", True, "Found: rZ123", ""),
                Check("State file", True, "v1.5.0, 0 modules", ""),
                Check("Workspace", False, "Cannot create", "Check perms"),
            ]
        )

        async def _fake_run_doctor() -> DoctorReport:
            return fake_report

        import xrpl_lab.api.routes as routes_mod
        monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)

        data = TestClient(create_app()).get("/api/doctor").json()

        # Top-level keys frozen at exactly these two.
        assert set(data.keys()) == {"overall", "checks"}, (
            f"doctor response top-level keys drift: {set(data.keys())}"
        )
        # overall is one of the canonical strings.
        assert data["overall"] in {"healthy", "warning", "error"}
        # Each check has exactly the canonical 3-key shape.
        for check in data["checks"]:
            assert set(check.keys()) == {"name", "status", "message"}, (
                f"doctor check key drift: {set(check.keys())}"
            )
            assert check["status"] in {"pass", "warn", "fail"}
            assert isinstance(check["name"], str)
            assert isinstance(check["message"], str)

        # Old field names must be gone (catch a partial revert).
        assert "all_passed" not in data
        assert "summary" not in data
        for check in data["checks"]:
            assert "passed" not in check
            assert "detail" not in check
            assert "hint" not in check

    def test_runs_list_response_schema_locked(self, client: TestClient) -> None:
        """GET /api/runs (added wave-2 P1, commit d18f137) — locked schema.

        Top-level: ``runs`` (list), ``max_concurrent`` (int), ``active_count`` (int).
        Each run dict: ``run_id``, ``module_id``, ``status``, ``created_at``,
        ``elapsed_seconds``, ``queue_size``, ``dry_run``.

        Schema must hold even when no runs are active (the empty-list case
        is the most common state for a fresh facilitator query).
        """
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()

        # Top-level shape locked.
        assert set(data.keys()) == {"runs", "max_concurrent", "active_count"}, (
            f"/api/runs top-level keys drift: {set(data.keys())}"
        )
        assert isinstance(data["runs"], list)
        assert isinstance(data["max_concurrent"], int)
        assert isinstance(data["active_count"], int)
        assert data["max_concurrent"] >= 1
        assert data["active_count"] >= 0
        assert data["active_count"] <= data["max_concurrent"]

        # Per-run-item schema (validate any items present, and seed one
        # via runner_ws to guarantee at least one run-info dict gets
        # exercised in this test).
        # Inject a synthetic session into the in-memory store. Use the
        # internal Session dataclass to ensure the dict shape matches.
        from xrpl_lab.api import runner_ws

        synthetic_run_id = "test_runs_schema_lock"
        sess = runner_ws.ModuleRunSession(
            run_id=synthetic_run_id,
            module_id="receipt_literacy",
            dry_run=False,
            status="running",
        )
        runner_ws._sessions[synthetic_run_id] = sess
        try:
            data2 = client.get("/api/runs").json()
            assert len(data2["runs"]) >= 1
            expected_run_keys = {
                "run_id",
                "module_id",
                "status",
                "created_at",
                "elapsed_seconds",
                "queue_size",
                "dry_run",
            }
            for run in data2["runs"]:
                assert set(run.keys()) == expected_run_keys, (
                    f"run-info key drift: "
                    f"added {set(run.keys()) - expected_run_keys}, "
                    f"removed {expected_run_keys - set(run.keys())}"
                )
                assert isinstance(run["run_id"], str)
                assert isinstance(run["module_id"], str)
                assert isinstance(run["status"], str)
                assert isinstance(run["created_at"], str)
                assert isinstance(run["elapsed_seconds"], (int, float))
                assert isinstance(run["queue_size"], int)
                assert isinstance(run["dry_run"], bool)
        finally:
            runner_ws._sessions.pop(synthetic_run_id, None)

    def test_no_secret_field_in_any_response(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No API response may include a key matching a secret-like name.

        Belt-and-suspenders for the threat-model promise that wallet
        secrets never leave the local machine. Iterates a representative
        set of GET endpoints and recursively scans the JSON for any key
        in the forbidden set. Catches:

          - accidental serialisation of the wallet seed
          - leaking ``password`` / ``private_key`` from a future endpoint
          - inclusion of full wallet.json content in a status response
        """
        forbidden_keys = {
            "seed",
            "secret",
            "private_key",
            "privatekey",
            "private-key",
            "password",
            "passphrase",
            "mnemonic",
            "wallet_json",
            "wallet.json",
            "encryption_key",
        }

        def _scan(obj: object, path: str = "$") -> list[str]:
            """Recursively yield (key-path) for any forbidden key found."""
            hits: list[str] = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    k_norm = str(k).lower().replace("-", "_").replace(".", "_")
                    if k_norm in {fk.replace("-", "_").replace(".", "_") for fk in forbidden_keys}:
                        hits.append(f"{path}.{k}")
                    hits.extend(_scan(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    hits.extend(_scan(item, f"{path}[{i}]"))
            return hits

        # Set up reports to exercise the artifacts/reports list path.
        ws = tmp_path / "ws"
        reports_dir = ws / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "test_secrets.md").write_text(
            "Some content.", encoding="utf-8",
        )

        endpoints_to_scan = [
            "/api/status",
            "/api/modules",
            "/api/modules/receipt_literacy",
            "/api/artifacts/proof-pack",
            "/api/artifacts/certificate",
            "/api/artifacts/reports",
            "/api/runs",
        ]

        all_hits: list[tuple[str, str]] = []
        for endpoint in endpoints_to_scan:
            resp = client.get(endpoint)
            # Some endpoints may legitimately 404 in the test env; skip those.
            if resp.status_code == 404:
                continue
            assert resp.status_code == 200, (
                f"unexpected status {resp.status_code} from {endpoint}"
            )
            payload = resp.json()
            hits = _scan(payload)
            for h in hits:
                all_hits.append((endpoint, h))

        assert not all_hits, (
            f"forbidden secret-like keys found in API responses: {all_hits}"
        )
