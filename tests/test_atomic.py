"""Focused unit tests for ``xrpl_lab._atomic.atomic_write_json``.

The helper consolidates the create-with-mode + write + (optional) atomic
rename pattern shared by ``save_wallet`` (atomic=False, O_TRUNC) and
``save_state`` (atomic=True, O_EXCL+rename). The wallet/state suites
already cover the full save flows; these tests pin the helper-level
invariants so future refactors of either caller can't silently drop
TOCTOU-safety, atomic semantics, or the failure-cleanup contract.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from xrpl_lab._atomic import atomic_write_json

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes — Windows uses ACLs, not 0o600",
)


class TestFileMode:
    """The whole point of the helper is TOCTOU-safe permission setting."""

    @POSIX_ONLY
    def test_default_file_mode_is_0o600_atomic(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        atomic_write_json(path, {"k": "v"})
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got 0o{mode:o}"

    @POSIX_ONLY
    def test_default_file_mode_is_0o600_non_atomic(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        atomic_write_json(path, {"k": "v"}, atomic=False)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got 0o{mode:o}"

    @POSIX_ONLY
    def test_file_mode_survives_permissive_umask(self, tmp_path: Path) -> None:
        """umask 0o000 would normally widen permissions; os.open with explicit
        mode must still produce 0o600 regardless of inherited umask."""
        old_umask = os.umask(0o000)
        try:
            path = tmp_path / "umask.json"
            atomic_write_json(path, {"k": "v"})
        finally:
            os.umask(old_umask)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600

    @POSIX_ONLY
    def test_explicit_0o644_honored(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        atomic_write_json(path, {"k": "v"}, file_mode=0o644)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o644

    def test_os_open_called_with_explicit_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spy on os.open to confirm the create itself uses the requested
        mode — not a chmod-after-create that leaves a TOCTOU window."""
        captured: list[tuple[object, int, int]] = []
        real_open = os.open

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            if str(path).endswith(("atomic_spy.json", "atomic_spy.json.tmp")):
                captured.append((path, flags, mode))
            return real_open(path, flags, mode, *args, **kwargs)

        monkeypatch.setattr("xrpl_lab._atomic.os.open", spy_open)

        path = tmp_path / "atomic_spy.json"
        atomic_write_json(path, {"k": "v"}, file_mode=0o600)

        assert captured, "atomic_write_json did not call os.open"
        _, flags, mode = captured[-1]
        assert mode == 0o600, f"os.open mode was 0o{mode:o}, expected 0o600"
        assert flags & os.O_CREAT
        assert flags & os.O_WRONLY


class TestAtomicSemantics:
    """atomic=True writes via tmp + os.replace; atomic=False writes direct."""

    def test_atomic_uses_tmp_then_replace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[str] = []
        replaced: list[tuple[str, str]] = []
        real_open = os.open
        real_replace = os.replace

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, flags, mode, *args, **kwargs)

        def spy_replace(src, dst, *args, **kwargs):
            replaced.append((str(src), str(dst)))
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr("xrpl_lab._atomic.os.open", spy_open)
        monkeypatch.setattr("xrpl_lab._atomic.os.replace", spy_replace)

        path = tmp_path / "data.json"
        atomic_write_json(path, {"k": "v"}, atomic=True)

        tmp_target = str(tmp_path / "data.json.tmp")
        final_target = str(tmp_path / "data.json")
        assert tmp_target in opened, f"tmp not opened: {opened}"
        assert (tmp_target, final_target) in replaced
        assert path.exists()
        assert not (tmp_path / "data.json.tmp").exists()

    def test_non_atomic_writes_direct_with_o_trunc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """atomic=False matches save_wallet's behavior: O_TRUNC, no tmp."""
        opened: list[tuple[str, int]] = []
        replaced: list[tuple[str, str]] = []
        real_open = os.open
        real_replace = os.replace

        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            opened.append((str(path), flags))
            return real_open(path, flags, mode, *args, **kwargs)

        def spy_replace(src, dst, *args, **kwargs):
            replaced.append((str(src), str(dst)))
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr("xrpl_lab._atomic.os.open", spy_open)
        monkeypatch.setattr("xrpl_lab._atomic.os.replace", spy_replace)

        path = tmp_path / "data.json"
        atomic_write_json(path, {"k": "v"}, atomic=False)

        # The final path is opened directly (no .tmp sibling)
        final = str(path)
        target_opens = [(p, f) for p, f in opened if p == final]
        assert target_opens, f"final path not opened: {opened}"
        _, flags = target_opens[-1]
        assert flags & os.O_TRUNC, "atomic=False must use O_TRUNC"
        # No replace ran — direct write
        assert not replaced, f"atomic=False must not call os.replace: {replaced}"

    def test_atomic_no_partial_visible_during_concurrent_read(
        self, tmp_path: Path
    ) -> None:
        """A reader observing the final path during a flurry of writes must
        only ever see complete JSON — never a half-written document. The
        tmp+rename guarantees this; without it a reader could catch the
        write mid-flight."""
        path = tmp_path / "concurrent.json"
        # Establish a known-good baseline file so readers don't FileNotFound.
        atomic_write_json(path, {"version": 0, "items": []})

        stop = threading.Event()
        partial_reads: list[str] = []

        def reader() -> None:
            while not stop.is_set():
                try:
                    text = path.read_text(encoding="utf-8")
                    json.loads(text)  # raises if partial
                except json.JSONDecodeError:
                    partial_reads.append(text)
                except FileNotFoundError:
                    pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        try:
            for i in range(50):
                atomic_write_json(path, {"version": i, "items": list(range(i))})
                time.sleep(0.001)
        finally:
            stop.set()
            t.join(timeout=1.0)

        assert not partial_reads, (
            f"reader observed {len(partial_reads)} partial JSON snapshots — "
            "atomic write-then-rename guarantee broken"
        )


class TestFailureCleanup:
    """A failed atomic write must leave no orphan .tmp and re-raise."""

    def test_serializer_failure_propagates_atomic(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"

        def boom(_data: object) -> str:
            raise RuntimeError("simulated serializer failure")

        with pytest.raises(RuntimeError, match="simulated serializer failure"):
            atomic_write_json(path, {"k": "v"}, atomic=True, serialize=boom)
        # Serializer raises BEFORE we open the tmp, so no orphan.
        assert not (tmp_path / "data.json.tmp").exists()
        # Final path was never created
        assert not path.exists()

    def test_write_failure_cleans_orphan_tmp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the write into the tmp fd fails, the orphan .tmp must be
        unlinked and the original exception must propagate."""
        path = tmp_path / "data.json"

        # Establish a baseline so we can verify it survives the failed write.
        atomic_write_json(path, {"baseline": True})
        original_bytes = path.read_bytes()

        # Patch os.fdopen to return a writer that explodes on write so
        # the tmp fd opens (O_EXCL succeeds) but the write into it fails.
        class BoomFile:
            def __init__(self, fd: int) -> None:
                self._fd = fd

            def __enter__(self) -> BoomFile:
                return self

            def __exit__(self, *exc: object) -> None:
                os.close(self._fd)

            def write(self, _text: str) -> int:
                raise OSError("simulated write failure")

        def patched_fdopen(fd, *args, **kwargs):
            # Only the helper's write path; lambdas elsewhere are unaffected.
            return BoomFile(fd)

        monkeypatch.setattr("xrpl_lab._atomic.os.fdopen", patched_fdopen)

        with pytest.raises(OSError, match="simulated write failure"):
            atomic_write_json(path, {"new": True}, atomic=True)

        # Orphan .tmp cleaned up
        assert not (tmp_path / "data.json.tmp").exists(), (
            "atomic write must unlink the orphan .tmp on failure"
        )
        # Baseline file untouched (no replace ran)
        assert path.read_bytes() == original_bytes, (
            "previous good copy must survive a failed atomic write"
        )

    def test_atomic_recovers_from_stale_tmp(self, tmp_path: Path) -> None:
        """A stale .tmp from a previously-killed process must be pre-cleaned;
        otherwise O_EXCL would block the next save with FileExistsError."""
        path = tmp_path / "data.json"
        atomic_write_json(path, {"baseline": True})

        # Manually create a stale tmp (as if a previous process died after
        # opening it but before os.replace ran).
        stale = tmp_path / "data.json.tmp"
        stale.write_text('{"partial', encoding="utf-8")
        assert stale.exists()

        # Must NOT raise FileExistsError — helper pre-cleans the stale tmp.
        atomic_write_json(path, {"second": True})

        assert not stale.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == {"second": True}


class TestSerializer:
    """Default serialization is json.dumps; callers can override (Pydantic)."""

    def test_default_serializer_is_json_dumps_indent_2(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        atomic_write_json(path, {"a": 1, "b": [2, 3]})
        text = path.read_text(encoding="utf-8")
        assert text == json.dumps({"a": 1, "b": [2, 3]}, indent=2)

    def test_custom_serializer_used(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        atomic_write_json(
            path, {"k": "v"}, serialize=lambda d: json.dumps(d, sort_keys=True)
        )
        text = path.read_text(encoding="utf-8")
        assert text == '{"k": "v"}'

    def test_custom_serializer_can_take_non_dict(self, tmp_path: Path) -> None:
        """state.py passes a Pydantic model, not a dict. The helper must
        not assume dict-shape when a serializer is provided."""

        class Fake:
            def model_dump_json(self) -> str:
                return '{"fake":true}'

        path = tmp_path / "out.json"
        atomic_write_json(
            path, Fake(), serialize=lambda obj: obj.model_dump_json()
        )
        assert path.read_text(encoding="utf-8") == '{"fake":true}'
