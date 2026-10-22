"""2.7.8 (#42): two feedback.py tests re-homed onto the support bundle.

`generate_feedback()` was removed because nothing but its tests called it.
These are the two of its contracts that no other test held for the bundle,
which is what `feedback` and `support-bundle` actually print (Argon, 2.7.8
round 1, F1).
"""

from __future__ import annotations

import os
import stat

from xrpl_lab.state import LabState
from xrpl_lab.workshop import generate_support_bundle


def _home(tmp_path, monkeypatch, ws):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.workshop.get_workspace_dir", lambda: ws)


def _state() -> LabState:
    return LabState(wallet_address="rTestAddr123", completed_modules=[], tx_index=[])


def test_the_bundle_network_follows_an_rpc_override(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, tmp_path / "ws")
    monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s.devnet.rippletest.net:51234")
    md = generate_support_bundle(_state()).to_markdown()
    assert "- Network: devnet" in md
    assert "- Network: testnet" not in md


def test_the_bundle_survives_a_read_only_workspace(tmp_path, monkeypatch):
    """F-TESTS-B-003: a read-only workspace must not crash the shareable report.

    The bundle only reads the workspace. If a future change writes into it
    from here, this fails and forces that write to handle the error.
    Windows ignores the mode; the no-crash contract still runs.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    _home(tmp_path, monkeypatch, ws)
    original = ws.stat().st_mode
    try:
        os.chmod(ws, stat.S_IRUSR | stat.S_IXUSR)  # r-x------
        md = generate_support_bundle(_state()).to_markdown()
    finally:
        os.chmod(ws, original)
    assert "## XRPL Lab Support Bundle" in md
    assert "### Environment" in md
