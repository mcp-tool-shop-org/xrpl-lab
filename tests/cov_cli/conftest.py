"""Shared isolation for the CLI coverage tests.

Every test runs with home, workspace and cwd inside ``tmp_path`` and with
``Path.home()`` redirected, so nothing touches the real home or workspace.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    home = tmp_path / "labhome"
    work = tmp_path / "work"
    user_home = tmp_path / "userhome"
    for d in (home, work, user_home):
        d.mkdir()
    ws = work / ".xrpl-lab"
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", home)
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(work)
    monkeypatch.setattr(Path, "home", lambda: user_home)
    for var in (
        "XRPL_LAB_HOME",
        "XRPL_LAB_RPC_URL",
        "XRPL_LAB_FAUCET_URL",
        "XRPL_LAB_DASHBOARD_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    return SimpleNamespace(
        tmp=tmp_path, home=home, work=work, ws=ws, user_home=user_home,
    )
