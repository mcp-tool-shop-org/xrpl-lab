"""state.py and _atomic.py edge paths: corruption recovery, locks, durability."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import xrpl_lab._atomic as atomic
import xrpl_lab.state as st
from xrpl_lab.errors import LabException

# ── _atomic._fsync_dir ────────────────────────────────────────────────


def test_fsync_dir_syncs_then_closes_the_directory_fd(monkeypatch, tmp_path):
    calls: list[tuple] = []
    monkeypatch.setattr(atomic.os, "open", lambda p, f: calls.append(("open", str(p))) or 77)
    monkeypatch.setattr(atomic.os, "fsync", lambda fd: calls.append(("fsync", fd)))
    monkeypatch.setattr(atomic.os, "close", lambda fd: calls.append(("close", fd)))
    atomic._fsync_dir(tmp_path)
    assert calls == [("open", str(tmp_path)), ("fsync", 77), ("close", 77)]


def test_fsync_dir_is_silent_when_the_directory_cannot_be_opened(monkeypatch, tmp_path):
    def _deny(*_a):
        raise PermissionError("no dir handles here")

    monkeypatch.setattr(atomic.os, "open", _deny)
    atomic._fsync_dir(tmp_path)  # best effort: must not raise


def test_fsync_dir_swallows_a_failed_fsync_but_still_closes(monkeypatch, tmp_path):
    closed: list[int] = []
    monkeypatch.setattr(atomic.os, "open", lambda p, f: 5)

    def _bad_fsync(_fd):
        raise OSError("not supported")

    monkeypatch.setattr(atomic.os, "fsync", _bad_fsync)
    monkeypatch.setattr(atomic.os, "close", closed.append)
    atomic._fsync_dir(tmp_path)
    assert closed == [5]


# ── _atomic.atomic_write_json ─────────────────────────────────────────


def test_atomic_write_fsyncs_the_parent_directory_on_posix(monkeypatch, tmp_path):
    seen: list[Path] = []
    monkeypatch.setattr(atomic, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(atomic, "_fsync_dir", seen.append)
    dest = tmp_path / "state.json"
    atomic.atomic_write_json(dest, {"k": 1})
    assert json.loads(dest.read_text(encoding="utf-8")) == {"k": 1}
    assert seen == [tmp_path]


def test_atomic_write_never_touches_the_dir_fd_on_windows(monkeypatch, tmp_path):
    seen: list[Path] = []
    monkeypatch.setattr(atomic, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(atomic, "_fsync_dir", seen.append)
    atomic.atomic_write_json(tmp_path / "state.json", {"k": 1})
    assert seen == []


def test_atomic_write_unlinks_a_colliding_tmp_before_writing(monkeypatch, tmp_path):
    box = tmp_path / "box"
    box.mkdir()
    dest = box / "out.json"
    fixed = SimpleNamespace(hex="deadbeefcafe0000")
    monkeypatch.setattr(atomic.uuid, "uuid4", lambda: fixed)
    stale = box / f"out.json.{os.getpid()}.deadbeef.tmp"
    stale.write_text("PARTIAL", encoding="utf-8")
    atomic.atomic_write_json(dest, {"fresh": True})
    assert json.loads(dest.read_text(encoding="utf-8")) == {"fresh": True}
    assert [p.name for p in box.iterdir()] == ["out.json"]


def test_atomic_write_survives_an_unremovable_collision_by_failing_loudly(
    monkeypatch, tmp_path,
):
    box = tmp_path / "box"
    box.mkdir()
    dest = box / "out.json"
    dest.write_text('{"old": 1}', encoding="utf-8")
    monkeypatch.setattr(atomic.uuid, "uuid4", lambda: SimpleNamespace(hex="deadbeefcafe0000"))
    stale = box / f"out.json.{os.getpid()}.deadbeef.tmp"
    stale.write_text("PARTIAL", encoding="utf-8")
    real_unlink = Path.unlink

    def _unlink(self, *a, **k):
        if self == stale:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _unlink)
    with pytest.raises(FileExistsError):
        atomic.atomic_write_json(dest, {"new": 1})
    assert json.loads(dest.read_text(encoding="utf-8")) == {"old": 1}


def test_atomic_write_cleanup_failure_does_not_mask_the_original_error(
    monkeypatch, tmp_path,
):
    box = tmp_path / "box"
    box.mkdir()
    dest = box / "out.json"
    real_unlink = Path.unlink

    def _unlink(self, *a, **k):
        if self.name.endswith(".tmp"):
            raise PermissionError("cannot clean")
        return real_unlink(self, *a, **k)

    def _boom(*_a, **_k):
        raise OSError("replace exploded")

    monkeypatch.setattr(Path, "unlink", _unlink)
    monkeypatch.setattr(atomic.os, "replace", _boom)
    with pytest.raises(OSError, match="replace exploded"):
        atomic.atomic_write_json(dest, {"x": 1})
    assert not dest.exists()


# ── state: directories and locking ────────────────────────────────────


def test_ensure_dir_mode_tightens_an_existing_directory_on_posix(monkeypatch, tmp_path):
    d = tmp_path / "home"
    d.mkdir()
    changed: list[tuple[Path, int]] = []
    monkeypatch.setattr(st, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(st.os, "chmod", lambda p, m: changed.append((Path(p), m)))
    # Windows stat() reports a mode that is never 0o700, so chmod must be requested
    st._ensure_dir_mode(d, 0o700)
    assert changed == [(d, 0o700)]


def test_ensure_dir_mode_leaves_windows_directories_to_acls(monkeypatch, tmp_path):
    d = tmp_path / "ws"
    changed: list = []
    monkeypatch.setattr(st, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(st.os, "chmod", lambda *a: changed.append(a))
    st._ensure_dir_mode(d, 0o755)
    assert d.is_dir() and changed == []


def test_state_lock_times_out_with_a_structured_retryable_error(lab, monkeypatch):
    monkeypatch.setattr(st, "_LOCK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(st, "_LOCK_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(st, "_try_lock", lambda fd: False)
    with pytest.raises(LabException) as exc, st._state_lock(st.state_path()):
        pytest.fail("lock must not be acquired")
    assert exc.value.error.code == "STATE_LOCKED"
    assert exc.value.error.retryable is True
    assert exc.value.exit_code == 1
    assert str(lab.home) not in exc.value.error.message + exc.value.error.hint


def test_state_lock_is_released_after_the_critical_section_raises(lab):
    with pytest.raises(RuntimeError), st._state_lock(st.state_path()):
        raise RuntimeError("boom")
    with st._state_lock(st.state_path()):  # re-acquirable straight away
        pass


# ── state: merge input, migration, loaders ────────────────────────────


def test_save_ignores_a_corrupt_on_disk_file_when_merging(lab):
    p = st.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ this is not json", encoding="utf-8")
    s = st.LabState()
    s.complete_module("alpha", txids=["T"])
    st.save_state(s)
    again = st.load_state()
    assert [m.module_id for m in again.completed_modules] == ["alpha"]


def test_migrate_hands_a_non_dict_payload_back_untouched():
    assert st._migrate([1, 2]) == [1, 2]
    d = {"version": "0", "network": "testnet"}
    assert st._migrate(d) is d


def test_load_state_from_path_error_taxonomy(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError):
        st.load_state_from_path(missing)

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        st.load_state_from_path(broken)

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"completed_modules": "not a list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Schema mismatch"):
        st.load_state_from_path(wrong)

    good = tmp_path / "good.json"
    good.write_text(st.LabState().model_dump_json(), encoding="utf-8")
    assert st.load_state_from_path(good).completed_modules == []


def test_load_state_warns_once_about_version_drift(lab, capsys):
    p = st.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": "0.0.1"}), encoding="utf-8")
    loaded = st.load_state()
    assert loaded.completed_modules == []
    assert "state from v0.0.1" in capsys.readouterr().err
    st.save_state(loaded)  # stamps the current version
    st.load_state()
    assert capsys.readouterr().err == ""


def test_load_state_recovers_from_corruption_with_a_backup_and_a_type_only_warning(
    lab, capsys,
):
    p = st.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("garbage{", encoding="utf-8")
    fresh = st.load_state()
    err = capsys.readouterr().err
    assert fresh.completed_modules == []
    assert "JSONDecodeError" in err and "a backup was saved" in err
    assert str(lab.home) not in err
    backups = list(p.parent.glob("state.json.corrupted.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "garbage{"


def test_load_state_reports_when_the_backup_itself_fails(lab, capsys, monkeypatch):
    p = st.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("garbage{", encoding="utf-8")

    def _no_copy(*_a, **_k):
        raise PermissionError("read-only share")

    monkeypatch.setattr(st.shutil, "copy2", _no_copy)
    fresh = st.load_state()
    err = capsys.readouterr().err
    assert fresh.completed_modules == []
    assert "the backup also failed (PermissionError)" in err
    assert "a fresh state was started" in err
    assert str(lab.home) not in err


# ── state: resets ─────────────────────────────────────────────────────


def test_reset_module_reports_when_the_report_file_cannot_be_removed(lab, monkeypatch):
    s = st.LabState()
    s.complete_module("alpha")
    s.record_tx("T1", "alpha", "testnet", True)
    st.save_state(s)
    report = lab.ws / "reports" / "alpha.md"
    report.parent.mkdir(parents=True)
    report.write_text("# r", encoding="utf-8")
    real_unlink = Path.unlink

    def _unlink(self, *a, **k):
        if self == report:
            raise PermissionError("open in an editor")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _unlink)
    summary = st.reset_module("alpha")
    assert summary == {
        "removed_from_completed": True,
        "tx_records_cleared": 1,
        "report_removed": False,
    }
    assert not st.load_state().is_module_completed("alpha")
    assert report.exists()


def test_reset_module_rejects_a_module_that_was_never_completed(lab):
    st.save_state(st.LabState())
    with pytest.raises(ValueError, match="nothing to reset"):
        st.reset_module("never_done")


def test_reset_state_removes_state_lock_sidecar_and_workspace_only(lab):
    s = st.LabState()
    s.complete_module("alpha")
    st.save_state(s)
    wallet = lab.home / "wallet.json"
    wallet.write_text("{}", encoding="utf-8")
    lab.ws.mkdir()
    (lab.ws / "x.txt").write_text("x", encoding="utf-8")
    sidecar = st._lock_path_for(st.state_path())
    assert sidecar.exists()
    st.reset_state()
    assert not st.state_path().exists()
    assert not sidecar.exists()
    assert not lab.ws.exists()
    assert wallet.exists()
    st.reset_state()  # idempotent on an already-clean install


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_saved_state_is_owner_only(lab):
    st.save_state(st.LabState())
    assert (st.state_path().stat().st_mode & 0o777) == 0o600
