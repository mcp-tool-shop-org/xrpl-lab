"""Tests for state management."""

import os
import sys

import pytest

from xrpl_lab import __version__
from xrpl_lab.state import LabState


class TestLabState:
    def test_version_matches_package(self):
        """LabState.version must stay in sync with the package __version__."""
        assert LabState().version == __version__

    def test_fresh_state(self):
        state = LabState()
        assert state.version == __version__
        assert state.network == "testnet"
        assert state.wallet_address is None
        assert state.completed_modules == []
        assert state.tx_index == []

    def test_complete_module(self):
        state = LabState()
        state.complete_module("receipt_literacy", txids=["ABC123"], report_path="r.md")
        assert state.is_module_completed("receipt_literacy")
        assert not state.is_module_completed("failure_literacy")
        assert len(state.completed_modules) == 1
        assert state.completed_modules[0].txids == ["ABC123"]

    def test_complete_module_idempotent(self):
        state = LabState()
        state.complete_module("receipt_literacy")
        state.complete_module("receipt_literacy")  # Should not duplicate
        assert len(state.completed_modules) == 1

    def test_record_tx(self):
        state = LabState()
        state.record_tx(
            txid="TX001",
            module_id="receipt_literacy",
            network="testnet",
            success=True,
            explorer_url="https://example.com/tx/TX001",
        )
        assert len(state.tx_index) == 1
        assert state.tx_index[0].txid == "TX001"
        assert state.tx_index[0].success is True

    def test_record_failed_tx(self):
        state = LabState()
        state.record_tx(
            txid="FAIL01",
            module_id="failure_literacy",
            network="testnet",
            success=False,
        )
        assert state.tx_index[0].success is False

    def test_roundtrip_json(self):
        state = LabState(
            network="testnet",
            wallet_address="rFAKE123",
        )
        state.complete_module("receipt_literacy", txids=["TX1"])
        state.record_tx("TX1", "receipt_literacy", "testnet", True)

        json_str = state.model_dump_json()
        restored = LabState.model_validate_json(json_str)

        assert restored.wallet_address == "rFAKE123"
        assert len(restored.completed_modules) == 1
        assert len(restored.tx_index) == 1


class TestStatePersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        # Redirect home dir to temp
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import load_state, save_state

        state = LabState(wallet_address="rTEST")
        state.complete_module("receipt_literacy")
        save_state(state)

        loaded = load_state()
        assert loaded.wallet_address == "rTEST"
        assert loaded.is_module_completed("receipt_literacy")

    def test_load_missing_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import load_state

        state = load_state()
        assert state.completed_modules == []

    def test_load_corrupted_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        # Write invalid JSON
        (tmp_path / "state.json").write_text("{invalid json", encoding="utf-8")

        from xrpl_lab.state import load_state

        state = load_state()
        assert state.completed_modules == []  # Falls back to fresh

    def test_reset(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws")

        from xrpl_lab.state import ensure_workspace, reset_state, save_state

        state = LabState(wallet_address="rTEST")
        save_state(state)
        ensure_workspace()

        assert (tmp_path / "state.json").exists()
        assert (tmp_path / "ws" / "reports").exists()

        reset_state()

        assert not (tmp_path / "state.json").exists()
        assert not (tmp_path / "ws").exists()


class TestStateAtomicWrite:
    """Verify save_state uses write-to-temp + atomic rename (F-BACKEND-B-005).

    Same class of bug as the wallet TOCTOU fix in wave 1: process death
    mid-write must not corrupt the destination file.
    """

    def test_save_state_creates_intermediate_tmp_file(self, tmp_path, monkeypatch):
        """save_state opens state.json.tmp before atomically replacing state.json."""
        import os as _os

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import save_state

        opened_paths: list[str] = []
        replaced: list[tuple[str, str]] = []

        real_open = _os.open
        real_replace = _os.replace

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            opened_paths.append(str(path))
            return real_open(path, flags, mode, *args, **kwargs)

        def spy_replace(src, dst, *args, **kwargs):
            replaced.append((str(src), str(dst)))
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr("xrpl_lab.state.os.open", spy_open)
        monkeypatch.setattr("xrpl_lab.state.os.replace", spy_replace)

        save_state(LabState(wallet_address="rTEST"))

        # The tmp path must be opened
        tmp_target = str(tmp_path / "state.json.tmp")
        final_target = str(tmp_path / "state.json")
        assert any(p == tmp_target for p in opened_paths), (
            f"expected os.open of {tmp_target}, saw {opened_paths}"
        )
        # And os.replace must have moved tmp -> final
        assert (tmp_target, final_target) in replaced, (
            f"expected os.replace({tmp_target!r}, {final_target!r}), saw {replaced}"
        )
        # Final file exists, tmp is gone
        assert (tmp_path / "state.json").exists()
        assert not (tmp_path / "state.json.tmp").exists()

    def test_save_state_recovers_from_partial_write_via_replace(
        self, tmp_path, monkeypatch
    ):
        """Mid-write failure: previous state.json intact, no orphan .tmp, exception propagates."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import save_state

        # First save: establish a known-good state.json on disk
        good = LabState(wallet_address="rGOOD")
        good.complete_module("receipt_literacy", txids=["GOOD_TX"])
        save_state(good)

        original_bytes = (tmp_path / "state.json").read_bytes()

        # Now monkeypatch model_dump_json to raise mid-write so the .tmp
        # file gets opened (O_EXCL succeeds) but the write into it fails.
        def boom(self, *a, **kw):
            raise RuntimeError("simulated mid-write failure")

        monkeypatch.setattr(LabState, "model_dump_json", boom)

        bad = LabState(wallet_address="rBAD")
        try:
            save_state(bad)
        except RuntimeError as e:
            assert "simulated mid-write failure" in str(e)
        else:
            raise AssertionError("save_state must re-raise the write failure")

        # The previous good state.json must be untouched (no atomic replace ran)
        assert (tmp_path / "state.json").read_bytes() == original_bytes
        # The orphan .tmp must be cleaned up
        assert not (tmp_path / "state.json.tmp").exists()


class TestStatePartialWriteRecovery:
    """F-TESTS-B-002: partial-write recovery scenarios for the wave-1 atomic-write fix.

    The wave-1 fix (commit 138ef95) made save_state survive process death
    mid-write by using O_EXCL temp + os.replace. These tests pin the
    recovery behavior so a future refactor that drops the pre-clean of a
    stale .tmp, or the versioned corrupt-backup naming, breaks loud.
    """

    def test_save_state_recovers_from_stale_tmp_orphan(
        self, tmp_path, monkeypatch,
    ):
        """A stale state.json.tmp from a previously-killed process is pre-cleaned.

        Simulates the kill-before-rename failure mode: previous process
        opened state.json.tmp via O_EXCL, wrote partial bytes, then died
        before os.replace ran. The next save must succeed (not block on
        O_EXCL "file exists"), produce a valid state.json, and leave no
        orphan .tmp behind.
        """
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import load_state, save_state

        # Establish a valid baseline state.json on disk.
        baseline = LabState(wallet_address="rBASELINE")
        baseline.complete_module("receipt_literacy")
        save_state(baseline)
        assert (tmp_path / "state.json").exists()

        # Manually create a stale tmp (as if a previous process died after
        # os.open / O_EXCL + before os.replace). Contents are partial /
        # garbage by definition.
        stale_tmp = tmp_path / "state.json.tmp"
        stale_tmp.write_text('{"version":"1.5.0","partial', encoding="utf-8")
        assert stale_tmp.exists()

        # Save again — this must NOT block on O_EXCL (would raise FileExistsError).
        new_state = LabState(wallet_address="rNEW")
        new_state.complete_module("receipt_literacy")
        new_state.complete_module("failure_literacy")
        save_state(new_state)  # must not raise

        # The previously-stale tmp file must be gone (atomically replaced).
        assert not (tmp_path / "state.json.tmp").exists()

        # The new state.json contains the new content.
        loaded = load_state()
        assert loaded.wallet_address == "rNEW"
        assert loaded.is_module_completed("failure_literacy")

    def test_concurrent_save_load_no_partial_read(
        self, tmp_path, monkeypatch,
    ):
        """Concurrent save_state + load_state never observe a partial JSON read.

        The atomic write-then-rename guarantees readers either see the
        previous full state or the new full state, never a half-written
        document. We exercise that invariant by interleaving a small
        number of save/load cycles in async tasks and asserting load_state
        never raises JSONDecodeError.

        This is intentionally NOT a stress test — small iteration count
        keeps it deterministic in CI.
        """
        import asyncio

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import load_state, save_state

        # Seed an initial valid state so load_state always has a target.
        save_state(LabState(wallet_address="rSEED"))

        loads_seen: list[LabState] = []
        load_errors: list[Exception] = []

        async def saver() -> None:
            for i in range(20):
                state = LabState(wallet_address=f"rSAVE_{i:03d}")
                state.complete_module("receipt_literacy")
                save_state(state)
                # Yield to the loop so loader gets interleaved scheduling.
                await asyncio.sleep(0)

        async def loader() -> None:
            for _ in range(20):
                try:
                    s = load_state()
                    loads_seen.append(s)
                except Exception as e:  # noqa: BLE001 — explicit capture
                    load_errors.append(e)
                await asyncio.sleep(0)

        async def run_both() -> None:
            await asyncio.gather(saver(), loader())

        asyncio.run(run_both())

        # No load ever raised — partial-read collisions impossible by design.
        assert not load_errors, (
            f"unexpected load errors during concurrent save/load: {load_errors}"
        )
        # And every load returned a wallet_address that was either the
        # seed or a saver iteration — never a half-empty default that
        # could only happen on a partial-write fall-through.
        for s in loads_seen:
            assert s.wallet_address is not None
            assert s.wallet_address.startswith("rSAVE_") or s.wallet_address == "rSEED"

    def test_corrupt_state_writes_versioned_backup_preserves_existing_bak(
        self, tmp_path, monkeypatch,
    ):
        """Corrupt recovery uses state.json.corrupted.<ts>, never overwrites .bak.

        Wave-1 changed corrupt-recovery to write a timestamped
        ``state.json.corrupted.<ts>`` rather than clobbering a sibling
        ``.bak``. This test seeds a pre-existing .bak (e.g. from a
        previous unrelated tool or a manual snapshot) and asserts:

          1. load_state on a corrupt state.json creates a .corrupted.<ts>
             snapshot of the corrupt data.
          2. Any pre-existing .bak file is left untouched.
          3. load_state still returns a fresh fallback LabState.
        """
        import time as _time

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        from xrpl_lab.state import load_state

        # Pre-existing sibling .bak — represents a previous good snapshot.
        bak_path = tmp_path / "state.json.bak"
        bak_content = (
            '{"version":"1.5.0","network":"testnet","wallet_address":"rPREVGOOD"}'
        )
        bak_path.write_text(bak_content, encoding="utf-8")
        bak_mtime_before = bak_path.stat().st_mtime

        # Now corrupt the active state.json.
        corrupt_payload = "{this is not json"
        (tmp_path / "state.json").write_text(corrupt_payload, encoding="utf-8")

        # Capture timestamps before / after to bound the .corrupted.<ts> filename range.
        ts_before = int(_time.time())
        loaded = load_state()
        ts_after = int(_time.time())

        # Fallback is a fresh LabState (no modules completed).
        assert loaded.completed_modules == []

        # A .corrupted.<ts> file was created with the corrupt payload.
        # The atomic-write helper appends the suffix via with_suffix,
        # which replaces the trailing ".json" — so the filename pattern
        # is ``state.json.corrupted.<ts>`` (parent dir, not nested).
        corrupted_files = list(tmp_path.glob("state.json.corrupted.*"))
        assert len(corrupted_files) == 1, (
            f"expected exactly one corrupted backup, got {corrupted_files}"
        )
        corrupted = corrupted_files[0]
        # The numeric ts suffix is bracketed by the wall-clock window.
        ts_part = corrupted.name.rsplit(".", 1)[-1]
        assert ts_part.isdigit(), f"corrupted backup name not ts-suffixed: {corrupted.name}"
        ts_val = int(ts_part)
        assert ts_before <= ts_val <= ts_after, (
            f"corrupted backup ts {ts_val} outside [{ts_before}, {ts_after}]"
        )
        # And the corrupted backup contains the corrupt payload (proves
        # we copied state.json, not garbage).
        assert corrupted.read_text(encoding="utf-8") == corrupt_payload

        # Pre-existing .bak is untouched (content + mtime).
        assert bak_path.exists(), ".bak must not be deleted on corrupt recovery"
        assert bak_path.read_text(encoding="utf-8") == bak_content
        assert bak_path.stat().st_mtime == bak_mtime_before, (
            ".bak mtime must not change — corrupt recovery must not overwrite it"
        )


# ── DD-1: workspace/home dir mode policy ─────────────────────────────


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes — Windows uses ACLs, not 0o700/0o755",
)
class TestEnsureDirModeHelper:
    """The state._ensure_dir_mode helper centralizes the wave-1 wallet
    upgrade-tighten pattern (mkdir(mode=) + post-mkdir os.chmod) so the
    other 8 mkdir sites in the package can apply the per-dir threat-model
    classification without copy-pasting the discipline."""

    def test_creates_dir_with_requested_mode(self, tmp_path):
        from xrpl_lab.state import _ensure_dir_mode

        target = tmp_path / "fresh"
        _ensure_dir_mode(target, 0o700)
        mode = target.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"expected 0o700 on creation, got 0o{mode:o}"
        )

    def test_tightens_existing_loose_dir(self, tmp_path):
        from xrpl_lab.state import _ensure_dir_mode

        target = tmp_path / "loose"
        target.mkdir(mode=0o755)
        os.chmod(target, 0o755)  # guard against umask interference
        assert (target.stat().st_mode & 0o777) == 0o755

        _ensure_dir_mode(target, 0o700)
        mode = target.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"expected loose 0o755 to be tightened to 0o700, got 0o{mode:o}"
        )

    def test_loosens_existing_tight_dir_to_match_classification(self, tmp_path):
        """If a workspace dir was previously 0o700 (e.g. left over from
        an earlier run that ran issuer-wallet save), DD-1 says workspace
        is 0o755. The helper must converge to whatever mode is requested."""
        from xrpl_lab.state import _ensure_dir_mode

        target = tmp_path / "tight"
        target.mkdir(mode=0o700)
        os.chmod(target, 0o700)
        assert (target.stat().st_mode & 0o777) == 0o700

        _ensure_dir_mode(target, 0o755)
        mode = target.stat().st_mode & 0o777
        assert mode == 0o755


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes — Windows uses ACLs",
)
class TestHomeDirModePrivate:
    """DD-1: ~/.xrpl-lab/ holds the wallet seed + state — single-user
    private. Must be 0o700 on creation AND tightened on existing loose
    installs (upgrade path matches the wave-1 wallet pattern)."""

    def test_ensure_home_dir_creates_at_0o700(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "h")

        from xrpl_lab.state import ensure_home_dir

        home = ensure_home_dir()
        mode = home.stat().st_mode & 0o777
        assert mode == 0o700

    def test_save_state_parent_dir_is_0o700(self, tmp_path, monkeypatch):
        """save_state's parent dir creation must classify private."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "h")

        from xrpl_lab.state import save_state, state_path

        save_state(LabState(wallet_address="rTEST"))
        parent = state_path().parent
        mode = parent.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"home dir holding state.json must be 0o700, got 0o{mode:o}"
        )

    def test_save_state_tightens_existing_loose_home(self, tmp_path, monkeypatch):
        """Upgrade path: an earlier xrpl-lab version left ~/.xrpl-lab at 0o755."""
        home = tmp_path / "h"
        home.mkdir(mode=0o755)
        os.chmod(home, 0o755)
        assert (home.stat().st_mode & 0o777) == 0o755

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", home)

        from xrpl_lab.state import save_state

        save_state(LabState())
        mode = home.stat().st_mode & 0o777
        assert mode == 0o700, (
            f"loose home dir must be tightened to 0o700, got 0o{mode:o}"
        )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes — Windows uses ACLs",
)
class TestWorkspaceDirModeShareable:
    """DD-1: ./.xrpl-lab/{proofs,reports,logs,audit_packs}/ is workshop-
    shareable (facilitator handoff at session end, no secrets per the
    threat model). Default 0o755.

    These are regression tests: 0o755 stays 0o755 so any future tightening
    must be intentional (e.g. updating the threat model first)."""

    def test_ensure_workspace_subdirs_are_0o755(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )

        from xrpl_lab.state import ensure_workspace

        ws = ensure_workspace()
        for sub in ("proofs", "reports", "logs", "audit_packs"):
            mode = (ws / sub).stat().st_mode & 0o777
            assert mode == 0o755, (
                f"workspace subdir {sub!r} expected 0o755 (workshop-"
                f"shareable per DD-1), got 0o{mode:o}"
            )

    def test_workspace_root_is_0o755(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )

        from xrpl_lab.state import ensure_workspace

        ws = ensure_workspace()
        mode = ws.stat().st_mode & 0o777
        assert mode == 0o755

    def test_proof_pack_writes_to_0o755_dir(self, tmp_path, monkeypatch):
        """write_proof_pack creates the proofs/ dir; must land at 0o755."""
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )

        from xrpl_lab.reporting import write_proof_pack

        path = write_proof_pack(LabState(wallet_address="rTEST"))
        mode = path.parent.stat().st_mode & 0o777
        assert mode == 0o755

    def test_audit_pack_writes_to_0o755_dir(self, tmp_path):
        """write_audit_pack creates the audit_packs/ dir at 0o755."""
        from xrpl_lab.audit import (
            AuditConfig,
            AuditReport,
            write_audit_pack,
        )

        report = AuditReport(
            verdicts=[],
            config=AuditConfig(),
            endpoint="https://test",
            tool_version=__version__,
            timestamp="2026-04-30T00:00:00Z",
        )
        target = tmp_path / "ws" / "audit_packs" / "audit.json"
        write_audit_pack(report, target)
        mode = target.parent.stat().st_mode & 0o777
        assert mode == 0o755
