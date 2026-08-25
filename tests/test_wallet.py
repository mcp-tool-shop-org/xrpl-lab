"""Tests for wallet management — create, save, load, exists, info."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from xrpl.wallet import Wallet

from xrpl_lab.actions.wallet import (
    create_wallet,
    load_wallet,
    save_wallet,
    wallet_exists,
    wallet_info,
)


class TestCreateWallet:
    def test_returns_wallet_instance(self):
        wallet = create_wallet()
        assert isinstance(wallet, Wallet)

    def test_has_address(self):
        wallet = create_wallet()
        assert wallet.address
        assert wallet.address.startswith("r")

    def test_has_seed(self):
        wallet = create_wallet()
        assert wallet.seed
        assert len(wallet.seed) > 0

    def test_unique_wallets(self):
        w1 = create_wallet()
        w2 = create_wallet()
        assert w1.address != w2.address
        assert w1.seed != w2.seed


class TestSaveWallet:
    def test_creates_file(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert path.exists()

    def test_file_has_required_keys(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "address" in data
        assert "seed" in data
        assert "public_key" in data

    def test_address_matches(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["address"] == wallet.address

    def test_returns_path(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        result = save_wallet(wallet, path=path)
        assert result == path

    def test_creates_parent_dirs(self, tmp_path):
        wallet = create_wallet()
        nested = tmp_path / "deep" / "nested" / "wallet.json"
        save_wallet(wallet, path=nested)
        assert nested.exists()


class TestLoadWallet:
    def test_roundtrip(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        loaded = load_wallet(path=path)
        assert loaded is not None
        assert loaded.address == wallet.address

    def test_missing_file_returns_none(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_wallet(path=path)
        assert result is None

    def test_corrupted_json_returns_none(self, tmp_path):
        path = tmp_path / "wallet.json"
        path.write_text("{this is not valid json{{", encoding="utf-8")
        result = load_wallet(path=path)
        assert result is None

    def test_missing_seed_key_returns_none(self, tmp_path):
        path = tmp_path / "wallet.json"
        path.write_text(json.dumps({"address": "rFAKE", "public_key": "PUBKEY"}), encoding="utf-8")
        result = load_wallet(path=path)
        assert result is None


class TestWalletExists:
    def test_true_when_file_present(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert wallet_exists(path=path) is True

    def test_false_when_missing(self, tmp_path):
        path = tmp_path / "wallet.json"
        assert wallet_exists(path=path) is False

    def test_reflects_deletion(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert wallet_exists(path=path) is True
        path.unlink()
        assert wallet_exists(path=path) is False


class TestSaveWalletFileMode:
    """Regression tests for the wave-1 TOCTOU fix.

    save_wallet now uses os.open(..., O_WRONLY|O_CREAT|O_TRUNC, 0o600) so
    the seed file is created with restrictive permissions atomically — no
    world-readable window between write_text() and chmod() as before.

    F-5531ceb5 (HIGH, wave 2): this class used to carry a single blanket
    ``skipif(sys.platform == "win32")`` at the CLASS level, which skipped
    all six of its tests on Windows unconditionally — including two
    (``test_os_open_is_called_with_0o600``, ``test_os_open_failure_propagates``)
    that assert on ``os.open`` call arguments / exception propagation and
    have nothing POSIX-specific about them; they pass on win32 today
    unmodified. That blanket skip is exactly how F-5531ceb5 shipped
    undetected: the win32-only gap in ``save_wallet``'s actual ACL
    hardening (see ``_windows_icacls_lockdown`` in wallet.py) had zero
    regression coverage on the one platform it mattered on. The skip is
    now per-test and applied ONLY to the four tests below that assert
    real POSIX mode bits (``st_mode``/``chmod``/umask), which have no
    meaning on an NTFS ACL and are covered on win32 instead by
    ``tests/test_w2_actions_wallet_win32_acl.py`` (real ``icacls``
    assertions on this platform, not skipped).
    """

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX file mode bits — Windows equivalent (icacls ACL) is "
        "asserted in tests/test_w2_actions_wallet_win32_acl.py",
    )
    def test_file_mode_is_0o600_after_save(self, tmp_path: Path) -> None:
        """The file's mode bits MUST be exactly 0o600 after save_wallet."""
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, (
            f"Expected wallet.json mode 0o600 but got 0o{mode:o} — "
            "atomic os.open(..., 0o600) regressed?"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX umask semantics — no equivalent on win32",
    )
    def test_file_mode_is_0o600_even_with_permissive_umask(
        self, tmp_path: Path
    ) -> None:
        """A permissive umask must NOT widen the file mode.

        os.open's mode arg is masked by the active umask, so umask 0o000
        with explicit mode 0o600 still produces 0o600. This test locks in
        that contract — a future refactor that drops the explicit mode
        argument and relies on umask defaults would silently leak the
        seed to other users on the system.
        """
        wallet = create_wallet()
        path = tmp_path / "wallet_umask.json"
        prev = os.umask(0o000)
        try:
            save_wallet(wallet, path=path)
        finally:
            os.umask(prev)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, (
            f"Expected 0o600 under permissive umask 0o000 but got 0o{mode:o}"
        )

    # Not skipped on win32: save_wallet's final content write always goes
    # through atomic_write_json's os.open(..., 0o600) regardless of
    # platform (the win32-only ACL lockdown runs BEFORE this, on an
    # empty file — see wallet.py's save_wallet docstring), so this
    # assertion holds on every platform.
    def test_os_open_is_called_with_0o600(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spy on os.open to capture the mode argument at create time.

        This goes beyond a post-write stat() check — it verifies that the
        atomic create itself uses 0o600, not that some later operation
        chmod'd it down. If save_wallet ever reverts to write_text+chmod
        the spy will record a different (or absent) mode argument.
        """
        captured: list[tuple[object, int, int]] = []
        real_open = os.open

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            # Only record opens for our test path so we don't capture
            # unrelated opens from json/io/etc. (Path objects compare via
            # equality; coerce to str for safety.)
            if str(path).endswith("wallet_spy.json"):
                captured.append((path, flags, mode))
            return real_open(path, flags, mode, *args, **kwargs)

        monkeypatch.setattr("xrpl_lab.actions.wallet.os.open", spy_open)

        wallet = create_wallet()
        path = tmp_path / "wallet_spy.json"
        save_wallet(wallet, path=path)

        assert captured, "save_wallet did not call os.open on the wallet path"
        # Last call wins — that's the create.
        _, flags, mode = captured[-1]
        assert mode == 0o600, f"os.open mode was 0o{mode:o}, expected 0o600"
        assert flags & os.O_CREAT, "expected O_CREAT in flags"
        assert flags & os.O_WRONLY, "expected O_WRONLY in flags"
        assert flags & os.O_TRUNC, "expected O_TRUNC in flags"

    # Not skipped on win32: on this platform save_wallet calls os.open
    # directly (to create the file empty, before the ACL lockdown — see
    # wallet.py) in addition to atomic_write_json's own os.open, so a
    # patched-to-raise os.open still propagates from the very first call
    # save_wallet makes after _ensure_secure_parent.
    def test_os_open_failure_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.open raises (e.g. EACCES), save_wallet must NOT swallow it.

        The wave-1 fix removed the silent OSError suppression that the
        old chmod path had. This test asserts the failure surfaces to the
        caller so misconfigured deployments fail loudly instead of leaving
        a world-readable seed on disk.
        """
        def boom(*args, **kwargs):
            raise PermissionError("simulated EACCES")

        monkeypatch.setattr("xrpl_lab.actions.wallet.os.open", boom)
        wallet = create_wallet()
        path = tmp_path / "wallet_eacces.json"
        with pytest.raises(PermissionError, match="simulated EACCES"):
            save_wallet(wallet, path=path)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX file mode bits — Windows equivalent (icacls ACL) is "
        "asserted in tests/test_w2_actions_wallet_win32_acl.py",
    )
    def test_save_wallet_parent_dir_mode_is_0o700(self, tmp_path: Path) -> None:
        """Parent directory of a freshly-created wallet must be 0o700.

        SECURITY.md promises restricted permissions; the wallet file is
        already 0o600 (wave 1) but the directory it sits in was left at
        0o755 by ``Path.mkdir`` defaults — world-searchable, so a local
        user on a shared system could enumerate the wallet.json filename.
        F-BACKEND-W3-001: parent dir must be 0o700 on creation.
        """
        wallet = create_wallet()
        target = tmp_path / "subdir" / "wallet.json"
        save_wallet(wallet, path=target)
        mode = target.parent.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"Expected parent dir mode 0o700 but got 0o{mode:o} — "
            "_ensure_secure_parent regressed?"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX file mode bits — Windows equivalent (icacls ACL "
        "tightening of a pre-existing loose dir) is asserted in "
        "tests/test_w2_actions_wallet_win32_acl.py",
    )
    def test_save_wallet_tightens_existing_loose_parent_dir(
        self, tmp_path: Path
    ) -> None:
        """Upgrade path: an existing 0o755 parent dir must be tightened to 0o700.

        ``Path.mkdir(mode=0o700)`` only honors ``mode`` on creation, so
        directories left over from earlier xrpl-lab versions stay at the
        looser default unless explicitly chmod'd. This test asserts the
        post-mkdir chmod fixes those existing installs on next save.
        """
        target_parent = tmp_path / "loose"
        target_parent.mkdir(mode=0o755)
        # Confirm setup — guard against umask interference on the test host.
        os.chmod(target_parent, 0o755)
        assert (target_parent.stat().st_mode & 0o777) == 0o755

        wallet = create_wallet()
        save_wallet(wallet, path=target_parent / "wallet.json")
        mode = target_parent.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"Expected loose 0o755 parent to be tightened to 0o700, got 0o{mode:o}"
        )


class TestWalletInfo:
    def test_has_address_and_public_key(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert "address" in info
        assert "public_key" in info

    def test_does_not_include_seed(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert "seed" not in info

    def test_address_matches(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert info["address"] == wallet.address
