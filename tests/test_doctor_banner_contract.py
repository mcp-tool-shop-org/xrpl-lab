"""/api/doctor: the "Issues detected" banner agrees with the rows listed.

The dashboard's doctor page shows the banner from ``overall`` and the rows from
``checks`` of one response (site/src/pages/app/doctor.astro, ``doctorHTML``).
``overall == "error"`` can only appear when at least one row is ``"fail"``;
warn rows and passes never raise it. These tests pin that invariant, so a
banner over all-green rows cannot come from the API.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.doctor import Check, DoctorReport
from xrpl_lab.server import create_app


def _get(monkeypatch: pytest.MonkeyPatch, checks: list[Check]) -> dict:
    async def _fake_run_doctor() -> DoctorReport:
        return DoctorReport(checks=checks)

    import xrpl_lab.api.routes as routes_mod

    monkeypatch.setattr(routes_mod, "run_doctor", _fake_run_doctor)
    return TestClient(create_app()).get("/api/doctor").json()


def test_green_rows_and_warns_are_never_error(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _get(monkeypatch, [
        Check("A", True, "ok", ""),
        Check("B", True, "ok", ""),
        Check("Last error", True, "old", "hint", severity="warn"),
        Check("Env overrides", False, "x", "hint", severity="warn"),
    ])
    assert data["overall"] == "warning"
    assert all(c["status"] != "fail" for c in data["checks"])


def test_all_pass_is_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _get(monkeypatch, [Check("A", True, "ok", "")])["overall"] == "healthy"


def test_error_comes_with_a_failing_row_in_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _get(monkeypatch, [
        Check("A", True, "ok", ""),
        Check("B", True, "ok", ""),
        Check("C", True, "ok", ""),
        Check("D", True, "ok", ""),
        Check("Testnet", False, "down", "retry"),
    ])
    assert data["overall"] == "error"
    assert [c["name"] for c in data["checks"] if c["status"] == "fail"] == ["Testnet"]
