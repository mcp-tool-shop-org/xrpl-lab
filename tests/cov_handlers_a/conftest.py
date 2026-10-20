from __future__ import annotations

from pathlib import Path

import pytest

from ._h import Env


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    # Isolate every state/workspace write (and the relative ``.xrpl-lab``
    # paths some handlers use) under tmp; no network is ever reached.
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.chdir(tmp_path)
    return Env(tmp_path, monkeypatch)
