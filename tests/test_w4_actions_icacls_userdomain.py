"""F-e4d178f0: icacls self-lockout when USERDOMAIN is unset.

When USERDOMAIN is missing but USERNAME is set, the unfixed
``_windows_icacls_lockdown`` grants the bare username, then strips every
ACE whose display string does not exactly match that bare name. icacls
always echoes grants back as DOMAIN\\user, so the just-granted entry is
removed and the path is left with zero working ACEs — silent self-lockout
that returns normally instead of raising PERM_WALLET_ACL_FAILED.

Existing ``tests/test_w2_actions_wallet_win32_acl.py`` never unsets
USERDOMAIN, so that suite staying green is not evidence. These tests use
a throwaway temp path only — never the live home dir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from xrpl_lab.actions import wallet as wallet_mod
from xrpl_lab.errors import LabException

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows icacls lockdown only runs on win32",
)


def _restore_acl(path: Path) -> None:
    """Owner always retains WRITE_DAC — re-grant so tmp cleanup can succeed."""
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME", "")
    grant = f"{domain}\\{user}" if domain and user else user
    if not grant:
        return
    subprocess.run(
        ["icacls", str(path), "/grant", f"{grant}:(OI)(CI)F"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.fixture
def acl_dir(tmp_path):
    d = tmp_path / "lockdown_target"
    d.mkdir()
    yield d
    _restore_acl(d)


def _can_write(path: Path) -> bool:
    probe = path / "_write_probe.txt"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _icacls_stdout(path: Path) -> str:
    result = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestIcaclsUserdomainRoundTrip:
    def test_lockdown_retains_access_when_userdomain_unset(self, acl_dir, monkeypatch):
        """The audit reproduction: USERDOMAIN popped, USERNAME still set."""
        assert os.environ.get("USERNAME"), "USERNAME must be set"
        monkeypatch.delenv("USERDOMAIN", raising=False)

        wallet_mod._windows_icacls_lockdown(acl_dir, is_dir=True)

        assert _can_write(acl_dir), (
            "self-lockout: current user lost write access after lockdown "
            "with USERDOMAIN unset — icacls echoed a qualified ACE that "
            "failed the bare-username exact-string self-check and was "
            f"/remove:g'd. icacls:\n{_icacls_stdout(acl_dir)}"
        )
        user = os.environ["USERNAME"]
        listing = _icacls_stdout(acl_dir)
        assert user.lower() in listing.lower(), (
            f"current user {user!r} missing from ACL after lockdown:\n{listing}"
        )

    def test_lockdown_retains_access_when_userdomain_set(self, acl_dir, monkeypatch):
        """Qualified-name happy path must still leave the user able to write."""
        user = os.environ.get("USERNAME", "")
        domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME", "")
        assert user and domain, "USERNAME and a domain/computer name required"
        monkeypatch.setenv("USERDOMAIN", domain)
        monkeypatch.setenv("USERNAME", user)

        wallet_mod._windows_icacls_lockdown(acl_dir, is_dir=True)

        assert _can_write(acl_dir), (
            "lockdown with USERDOMAIN set left path unwritable:\n"
            f"{_icacls_stdout(acl_dir)}"
        )
        listing = _icacls_stdout(acl_dir)
        assert user.lower() in listing.lower(), (
            f"current user {user!r} missing from ACL after lockdown:\n{listing}"
        )


class TestIcaclsLastGranteeGuard:
    def test_raises_perm_instead_of_stripping_when_self_absent_from_listing(
        self, acl_dir, monkeypatch
    ):
        """Failure path: if the post-grant listing has no recognizable self
        ACE, do not ``/remove:g`` every listed principal into an empty
        grantee set — raise PERM_WALLET_ACL_FAILED and leave ACEs intact.

        Uses a real grant (so inheritance:r + grant succeed on pytest's
        inherited-only temp ACLs) but forces the parsed grantee list to
        contain only a non-self principal.
        """
        real_run = wallet_mod.subprocess.run
        remove_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            if len(cmd) >= 2 and cmd[0] == "icacls" and "/remove:g" in cmd:
                remove_cmds.append(list(cmd))
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(wallet_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(
            wallet_mod,
            "_icacls_grantee_names",
            lambda _stdout, _path: ["BUILTIN\\Administrators"],
        )

        with pytest.raises(LabException) as excinfo:
            wallet_mod._windows_icacls_lockdown(acl_dir, is_dir=True)

        assert excinfo.value.error.code == "PERM_WALLET_ACL_FAILED"
        assert remove_cmds == [], (
            "last-grantee guard failed: /remove:g ran when stripping would "
            f"leave an empty self-grantee set: {remove_cmds!r}"
        )
        assert _can_write(acl_dir), (
            "raised PERM_WALLET_ACL_FAILED but still locked out the path:\n"
            f"{_icacls_stdout(acl_dir)}"
        )
