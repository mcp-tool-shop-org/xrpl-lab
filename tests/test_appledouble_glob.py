"""AppleDouble (``._*``) sidecar files are ignored at every glob site.

exFAT/FAT volumes written from macOS get a ``._name`` file beside every real
file. Those carry resource-fork bytes, not text, so reading one as a module or
report breaks the command. Each test puts a ``._`` sidecar beside real files
and proves the site skips it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from xrpl_lab.modules import glob_visible, load_all_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
GARBAGE = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        \x00\x02\xff\xfe"


def _first_real_module() -> Path:
    return sorted((REPO_ROOT / "modules").glob("*.md"))[0]


def _plant(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(GARBAGE)
    return path


def test_glob_visible_skips_appledouble(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    _plant(tmp_path, "._a.md")
    assert [p.name for p in glob_visible(tmp_path, "*.md")] == ["a.md", "b.md"]


def test_load_all_modules_skips_appledouble(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real = _first_real_module()
    (tmp_path / "extra_copy.md").write_text(
        real.read_text(encoding="utf-8").replace(
            "id: " + real.stem, "id: " + real.stem + "_extra", 1
        ),
        encoding="utf-8",
    )
    _plant(tmp_path, "._extra_copy.md")
    before = set(load_all_modules())
    after = load_all_modules(extra_dirs=[tmp_path])
    assert set(after) - before == {real.stem + "_extra"}
    assert "._extra_copy.md" not in capsys.readouterr().err


def test_lint_all_modules_skips_appledouble(tmp_path: Path) -> None:
    from xrpl_lab.linter import lint_all_modules

    real = _first_real_module()
    (tmp_path / real.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    clean = lint_all_modules(tmp_path)
    _plant(tmp_path, "._" + real.name)
    polluted = lint_all_modules(tmp_path)
    assert len(polluted.issues) == len(clean.issues)
    assert not any("._" in i.module for i in polluted.issues)


def test_cli_lint_default_glob_skips_appledouble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from xrpl_lab.cli import main

    mods = tmp_path / "modules"
    mods.mkdir()
    real = _first_real_module()
    (mods / real.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    _plant(mods, "._" + real.name)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["lint", "--json", "--no-curriculum"])
    payload = json.loads(result.output)
    assert not any("._" in i["module"] for i in payload["issues"])


def test_cli_lint_only_sidecars_is_no_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from xrpl_lab.cli import main

    mods = tmp_path / "modules"
    mods.mkdir()
    _plant(mods, "._only.md")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["lint", "--json"])
    assert json.loads(result.output)["issues"] == []


def test_workshop_report_count_skips_appledouble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from xrpl_lab import workshop
    from xrpl_lab.state import LabState

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "wallet_basics.md").write_text("# r", encoding="utf-8")
    _plant(reports, "._wallet_basics.md")
    monkeypatch.setattr(workshop, "get_workspace_dir", lambda: tmp_path)
    assert workshop.get_learner_status(LabState()).report_count == 1


def test_api_reports_listing_skips_appledouble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from xrpl_lab.server import create_app

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "wallet_basics.md").write_text(
        "# Wallet Basics\n\nGenerated: 2026-01-01\n", encoding="utf-8"
    )
    _plant(reports, "._wallet_basics.md")
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: tmp_path)
    data = TestClient(create_app()).get("/api/artifacts/reports").json()
    assert len(data) == 1
