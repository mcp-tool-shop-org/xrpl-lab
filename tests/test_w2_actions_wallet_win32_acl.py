"""Windows ACL regression tests for wallet.py (F-5531ceb5).

SECURITY.md unconditionally promises the wallet seed is protected by file
permissions (0o600 inside a 0o700 home dir). The wave-2 audit found that
on win32 (``sys.platform == "win32"``), ``save_wallet()`` only logged a
warning and took no hardening action at all, and
``_ensure_secure_parent()``'s ``os.chmod`` tightening was skipped
entirely on win32 -- no Windows-equivalent (ACL) protection ever ran, so
the documented guarantee was simply false on every Windows install. All 7
regression tests that verified the POSIX side of this property
(``test_wallet.py::TestSaveWalletFileMode``) were blanket
``skipif``-ed on win32, so the gap shipped with a fully green test suite.

These tests run FOR REAL on win32 -- this platform -- instead of being
skipped. They shell out to the actual ``icacls`` binary (built into every
Windows install; no extra dependency) and assert on its real output, the
direct Windows equivalent of the POSIX suite's ``path.stat().st_mode``
checks. Skipped (not run) on POSIX, where ``test_wallet.py``'s existing
mode-bit suite already covers the equivalent guarantee.

What the fixed code guarantees on win32, verified here:

  1. The wallet file's ACL carries NO inherited entries (icacls's ``(I)``
     flag) and grants access to the current user ONLY -- no SYSTEM,
     Administrators, Users, or Everyone survive the lockdown.
  2. The wallet's parent directory gets the identical treatment, so a
     freshly-created OR a pre-existing (looser) home dir both end up
     owner-only, and new files created under it inherit that lockdown.
  3. The seed is never written to disk before the file's ACL is locked
     down -- the file is created empty, hardened, THEN the seed is
     written -- so a reader racing the tiny window before hardening can
     observe at most an empty file, never the seed.
  4. If ``icacls`` cannot be run or reports failure, ``save_wallet()``
     raises a structured, catchable ``LabException`` (code ``PERM_*``)
     instead of silently logging a warning and continuing with an
     unprotected file -- the exact defect this fixes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from xrpl_lab.actions import wallet as wallet_mod
from xrpl_lab.actions.wallet import create_wallet, save_wallet
from xrpl_lab.errors import LabException

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows ACL hardening only runs on win32 -- see "
    "test_wallet.py::TestSaveWalletFileMode for the POSIX mode-bit "
    "equivalent of these checks",
)


def _icacls(path: Path) -> str:
    result = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, f"icacls itself failed: {result.stderr}"
    return result.stdout


def _non_boilerplate_lines(icacls_output: str) -> list[str]:
    """Strip icacls's summary/footer lines, keep only ACE lines."""
    keep = []
    for line in icacls_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Successfully processed") or "Failed processing" in line:
            continue
        keep.append(line)
    return keep


class TestSaveWalletWindowsACL:
    """Real, on-platform assertions on the file's actual ACL after save."""

    def test_wallet_file_acl_has_no_inherited_entries(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)

        output = _icacls(path)
        assert "(I)" not in output, (
            f"wallet.json still carries inherited ACEs after save_wallet -- "
            f"its real exposure is whatever the parent's ACL template "
            f"happens to grant, exactly the ambient-default reliance "
            f"F-5531ceb5 flagged:\n{output}"
        )

    def test_wallet_file_acl_grants_only_current_user(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)

        user = os.environ.get("USERNAME", "")
        assert user, "USERNAME env var must be set to run this test"
        output = _icacls(path)
        for line in _non_boilerplate_lines(output):
            assert user.lower() in line.lower(), (
                f"Unexpected grantee survives wallet.json ACL lockdown: "
                f"{line!r}\nFull output:\n{output}"
            )

    def test_wallet_parent_dir_acl_has_no_inherited_entries(self, tmp_path):
        wallet = create_wallet()
        target = tmp_path / "subdir" / "wallet.json"
        save_wallet(wallet, path=target)

        output = _icacls(target.parent)
        assert "(I)" not in output, (
            f"wallet parent dir still carries inherited ACEs after save:\n{output}"
        )

    def test_wallet_parent_dir_acl_grants_only_current_user(self, tmp_path):
        wallet = create_wallet()
        target = tmp_path / "subdir" / "wallet.json"
        save_wallet(wallet, path=target)

        user = os.environ.get("USERNAME", "")
        output = _icacls(target.parent)
        for line in _non_boilerplate_lines(output):
            assert user.lower() in line.lower(), (
                f"Unexpected grantee survives wallet dir ACL lockdown: "
                f"{line!r}\nFull output:\n{output}"
            )

    def test_save_wallet_tightens_existing_loose_parent_dir_acl(self, tmp_path):
        """Upgrade path (mirrors the POSIX 0o755->0o700 test): a parent
        dir left over from an earlier xrpl-lab version, with a wide-open
        ACL, must be tightened on the NEXT save -- not just at first
        creation."""
        parent = tmp_path / "loose"
        parent.mkdir()
        subprocess.run(
            ["icacls", str(parent), "/grant:r", "Everyone:(OI)(CI)F"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        assert "Everyone" in _icacls(parent)

        wallet = create_wallet()
        save_wallet(wallet, path=parent / "wallet.json")

        output = _icacls(parent)
        assert "Everyone" not in output, (
            f"pre-existing loose parent dir ACL was not tightened on save:\n{output}"
        )


class TestSaveWalletNeverExposesSeedBeforeLockdown:
    def test_file_is_empty_when_acl_lockdown_runs(self, tmp_path, monkeypatch):
        """The seed must never be written to disk before its ACL is
        locked down -- otherwise a racing reader in that instant could
        read the seed itself instead of merely observing an empty file."""
        seen_sizes: list[int] = []
        real_lockdown = wallet_mod._windows_icacls_lockdown

        def spy_lockdown(path, *, is_dir):
            if not is_dir:
                seen_sizes.append(Path(path).stat().st_size)
            return real_lockdown(path, is_dir=is_dir)

        monkeypatch.setattr(wallet_mod, "_windows_icacls_lockdown", spy_lockdown)

        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)

        assert seen_sizes == [0], (
            f"Expected the wallet file to be empty (size 0) at ACL-lockdown "
            f"time, got sizes {seen_sizes} -- the seed may be exposed "
            "before its ACL is restricted"
        )
        # Sanity: the seed IS on disk after save_wallet returns.
        assert path.stat().st_size > 0


class TestWindowsACLFailureSurfaces:
    """The 'or make the failure explicit' half of the contract: if icacls
    cannot be run or reports failure, save_wallet must raise a
    structured, catchable error -- never silently log a warning and
    continue with an unprotected file (the exact defect being fixed)."""

    def test_icacls_nonzero_exit_raises_lab_exception(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="access denied (simulated)"
            )

        monkeypatch.setattr(wallet_mod.subprocess, "run", fake_run)

        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        with pytest.raises(LabException) as excinfo:
            save_wallet(wallet, path=path)
        assert excinfo.value.error.code.startswith("PERM_")
        assert "simulated" in (excinfo.value.error.cause or "")

    def test_icacls_missing_binary_raises_lab_exception(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("[WinError 2] simulated: icacls not found")

        monkeypatch.setattr(wallet_mod.subprocess, "run", fake_run)

        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        with pytest.raises(LabException) as excinfo:
            save_wallet(wallet, path=path)
        assert excinfo.value.error.code.startswith("PERM_")
        assert "simulated" in (excinfo.value.error.cause or "")

    def test_acl_failure_is_not_logged_and_swallowed(self, tmp_path, monkeypatch, caplog):
        """Regression guard for the exact pre-fix shape: a log.warning()
        call that lets execution continue. Failure must propagate as an
        exception, full stop -- a caplog capture of a warning is not
        enough to satisfy this test if save_wallet also returns
        normally."""
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="simulated failure"
            )

        monkeypatch.setattr(wallet_mod.subprocess, "run", fake_run)

        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        raised = False
        try:
            save_wallet(wallet, path=path)
        except LabException:
            raised = True
        assert raised, (
            "save_wallet() returned normally after a simulated icacls "
            "failure -- the failure must be surfaced as a raised "
            "exception, not swallowed into a log line"
        )
