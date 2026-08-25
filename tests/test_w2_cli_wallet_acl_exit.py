"""Coordinator patch regression test — F-5531ceb5 residual.

``save_wallet()`` gained a real failure mode in wave 2: it raises
``LabException(PERM_WALLET_ACL_FAILED)`` when the Windows ACL lockdown cannot be
verified, rather than logging a warning and shipping an unprotected seed. Two CLI
callers never caught it — their only ``except`` is
``(json.JSONDecodeError, KeyError, ValueError)`` — so on a machine without a usable
``icacls`` the learner would get a raw Python traceback.

SHIP_GATE B: no raw stack traces without ``--debug``. These tests pin the structured
rendering (code, message, hint) and the non-zero exit code at both call sites, and
both fail against the unpatched ``cli.py``.

Deliberately no ``skipif`` and no ``pytest.skip`` fallback: the defect class this
whole wave chased was gates that pass without exercising the property, and a test
that quietly skips when it misses its code path is exactly that. Both cases below
drive their call site directly, on every platform.
"""

import json

import pytest
from click.testing import CliRunner

import xrpl_lab.cli as cli_mod
from xrpl_lab.cli import main
from xrpl_lab.errors import LabError, LabException
from xrpl_lab.state import LabState

ACL_ERROR = LabError(
    code="PERM_WALLET_ACL_FAILED",
    message="Could not restrict permissions on wallet.json (Windows ACL lockdown).",
    hint="icacls is required to secure the wallet on Windows.",
)


def _raise_acl(*_a, **_kw):
    raise LabException(ACL_ERROR)


def _assert_structured(output: str, exit_code: int) -> None:
    """Structured failure, not a traceback, and the PERM_ exit code."""
    assert "Traceback (most recent call last)" not in output, (
        f"a raw traceback reached the user (SHIP_GATE B):\n{output}"
    )
    assert exit_code == 2, f"expected the PERM_ exit code 2, got {exit_code}.\n{output}"
    assert "PERM_WALLET_ACL_FAILED" in output, f"error code not surfaced:\n{output}"
    assert "icacls" in output, f"actionable hint not surfaced:\n{output}"


def test_wallet_create_renders_acl_failure_without_traceback(tmp_path, monkeypatch):
    """`xrpl-lab wallet create` must render the failure, not traceback."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", _raise_acl)

    result = CliRunner().invoke(main, ["wallet", "create"])
    _assert_structured(result.output, result.exit_code)


def test_camp_wallet_import_renders_acl_failure_without_traceback(
    tmp_path, monkeypatch, capsys
):
    """The implicit Camp-wallet import must render the failure and exit non-zero.

    It must not degrade to "no camp wallet" either — returning False would hide a
    security failure behind a normal-looking path. Calls the helper directly so the
    assertion cannot be dodged by `start` taking some other branch.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("XRPL_LAB_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    # A real, checksum-valid seed. A hand-written one fails Wallet.from_seed with
    # ValueError, which the pre-existing handler swallows — the helper would then
    # return False and this test would pass for the wrong reason.
    from xrpl.wallet import Wallet as XWallet

    camp = tmp_path / "camp-wallet.json"
    camp.write_text(json.dumps({"seed": XWallet.create().seed}), encoding="utf-8")
    monkeypatch.setattr(cli_mod, "_detect_camp_wallet", lambda: camp)
    monkeypatch.setattr("xrpl_lab.actions.wallet.wallet_exists", lambda *a, **k: False)
    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", _raise_acl)

    with pytest.raises(SystemExit) as exc:
        cli_mod._try_import_camp_wallet(LabState())

    _assert_structured(capsys.readouterr().out, exc.value.code)
