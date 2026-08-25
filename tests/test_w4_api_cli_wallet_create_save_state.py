"""Wave-4 api-cli AMEND regression — F-86f2f989 (HIGH).

``wallet_create`` wraps ``save_wallet`` in ``except LabException`` (wave-2 /
88c0a4e) but leaves the trailing ``save_state(state)`` unwrapped.
``save_state`` can raise ``LabException(STATE_LOCKED)`` under lock
contention — SHIP_GATE B forbids a raw traceback.

Same render pattern as ``cli.py`` reset_module (~1650) and the existing
ACL wrap on this function's ``save_wallet`` call.

``_try_import_camp_wallet`` already wraps both ``save_wallet`` and
``save_state`` in one ``except LabException`` — covered here so a future
narrowing of that except cannot silently regress.

Run in isolation:
    python -m pytest tests/test_w4_api_cli_wallet_create_save_state.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import xrpl_lab.cli as cli_mod
from xrpl_lab.cli import main
from xrpl_lab.errors import LabException, state_locked
from xrpl_lab.state import LabState


def _raise_state_locked(*_a, **_kw):
    raise LabException(state_locked())


def _assert_state_locked_structured(output: str, exit_code: int) -> None:
    assert "Traceback (most recent call last)" not in output, (
        f"a raw traceback reached the user (SHIP_GATE B):\n{output}"
    )
    assert exit_code == 1, f"expected STATE_ exit code 1, got {exit_code}.\n{output}"
    assert "STATE_LOCKED" in output, f"error code not surfaced:\n{output}"
    assert "another xrpl-lab process" in output or "Hint:" in output, (
        f"actionable message/hint not surfaced:\n{output}"
    )


def test_wallet_create_renders_save_state_locked_without_traceback(
    tmp_path, monkeypatch
):
    """Trailing save_state(STATE_LOCKED) must render structured, not traceback."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("XRPL_LAB_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from xrpl.wallet import Wallet as XWallet

    w = XWallet.create()

    def fake_create():
        return w

    def fake_save(wallet, path=None):
        return Path(home) / "wallet.json"

    monkeypatch.setattr("xrpl_lab.actions.wallet.wallet_exists", lambda *a, **k: False)
    monkeypatch.setattr("xrpl_lab.actions.wallet.create_wallet", fake_create)
    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", fake_save)
    monkeypatch.setattr(cli_mod, "save_state", _raise_state_locked)
    # load_state is imported into cli_mod; keep a real empty state.
    monkeypatch.setattr(cli_mod, "load_state", lambda: LabState())

    result = CliRunner().invoke(main, ["wallet", "create"], standalone_mode=False)
    # standalone_mode=False re-raises SystemExit from sys.exit inside the cmd.
    if isinstance(result.exception, SystemExit):
        exit_code = result.exception.code
    elif result.exception is not None:
        # Unfixed tree: LabException escapes uncaught → failure path we pin.
        raise result.exception
    else:
        exit_code = result.exit_code

    _assert_state_locked_structured(result.output, exit_code)


def test_camp_import_renders_save_state_locked_without_traceback(
    tmp_path, monkeypatch, capsys
):
    """_try_import_camp_wallet must also structure-render save_state failures."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("XRPL_LAB_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from xrpl.wallet import Wallet as XWallet

    camp = tmp_path / "camp-wallet.json"
    camp.write_text(json.dumps({"seed": XWallet.create().seed}), encoding="utf-8")
    monkeypatch.setattr(cli_mod, "_detect_camp_wallet", lambda: camp)
    monkeypatch.setattr("xrpl_lab.actions.wallet.wallet_exists", lambda *a, **k: False)

    def fake_save(wallet, path=None):
        return Path(home) / "wallet.json"

    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", fake_save)
    # Local import of save_state inside the helper — patch the state module.
    monkeypatch.setattr("xrpl_lab.state.save_state", _raise_state_locked)

    with pytest.raises(SystemExit) as exc:
        cli_mod._try_import_camp_wallet(LabState())

    _assert_state_locked_structured(capsys.readouterr().out, exc.value.code)
