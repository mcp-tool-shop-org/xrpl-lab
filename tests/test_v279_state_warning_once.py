"""2.7.9 (#45): the state-version warning prints once per command.

Book Keeper's 2.7.8 parity check: with state written by an older version,
`feedback` and `support-bundle` printed "Warning: state from vX, current is
vY. Some fields may differ." three times, once per load_state() call.
"""

from __future__ import annotations

import json

import pytest

from xrpl_lab import state as state_mod
from xrpl_lab.state import load_state


@pytest.fixture
def old_home(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "_warned_versions", set(), raising=False)
    (tmp_path / "state.json").write_text(
        json.dumps({"version": "2.7.7", "network": "testnet"}), encoding="utf-8",
    )
    return tmp_path


def test_three_loads_warn_once(old_home, capsys):
    for _ in range(3):
        load_state()
    assert capsys.readouterr().err.count("Warning: state from v2.7.7") == 1


def test_a_different_old_version_still_warns(old_home, capsys):
    load_state()
    (old_home / "state.json").write_text(
        json.dumps({"version": "2.7.6", "network": "testnet"}), encoding="utf-8",
    )
    load_state()
    err = capsys.readouterr().err
    assert err.count("Warning: state from v2.7.7") == 1
    assert err.count("Warning: state from v2.7.6") == 1


def test_another_state_file_still_warns(old_home, tmp_path_factory, monkeypatch, capsys):
    load_state()
    other = tmp_path_factory.mktemp("other")
    (other / "state.json").write_text(
        json.dumps({"version": "2.7.7", "network": "testnet"}), encoding="utf-8",
    )
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", other)
    load_state()
    assert capsys.readouterr().err.count("Warning: state from v2.7.7") == 2


def test_the_cli_warns_once_per_command(old_home, monkeypatch):
    """support-bundle loads state three times; the live check saw three warnings."""
    from click.testing import CliRunner

    from xrpl_lab.cli import main

    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: old_home)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: old_home / "ws")
    monkeypatch.setattr("xrpl_lab.workshop.get_workspace_dir", lambda: old_home / "ws")
    result = CliRunner().invoke(main, ["support-bundle"])
    assert result.exit_code == 0, result.output
    assert result.stderr.count("Warning: state from v2.7.7") == 1
