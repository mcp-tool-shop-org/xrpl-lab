"""Re-swarm 4 (dogfood #3, wave 2) backend-core regression tests.

Test-first proofs for the findings assigned to the backend-core domain in
this wave: F-5312c8ba (CRITICAL), F-d6d7f5e8 / F-ae597821 (HIGH),
F-eeddbf7f / F-678304a1 / F-1e8c93d7 / F-0c21577b / F-511dedbd (MEDIUM),
F-99b70cc9 / F-be051e03 (LOW). The fixes live in state.py, _atomic.py,
runner.py, runtime.py, modules.py, linter.py, doctor.py, and cli.py — only
those modules (plus this file) are owned by this domain agent.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading

import pytest
from click.testing import CliRunner
from rich.console import Console

from xrpl_lab.errors import LabException

# ═══════════════════════════════════════════════════════════════════════
# F-5312c8ba (CRITICAL) — state.json cross-process lost-update race
# ═══════════════════════════════════════════════════════════════════════


class TestF5312c8baLostUpdateRace:
    """save_state() must never let one process's write silently discard
    another's completed_modules/tx_index — the core of the CRITICAL fix."""

    def test_two_interleaved_save_cycles_lose_no_history(
        self, tmp_path, monkeypatch,
    ):
        """The literal scenario from the finding: two processes each load
        state.json at roughly the same time (so neither sees the other's
        work yet), then each independently completes a DIFFERENT module
        and saves. Before the fix, whichever saved LAST would silently
        overwrite the file with only its own view — this test is the
        "simulating two save cycles interleaved on the same state file"
        proof the mandate calls for.
        """
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import LabState, load_state, save_state

        # Establish a shared baseline both "processes" load from.
        baseline = LabState(wallet_address="rSHARED")
        baseline.complete_module("mod_zero", txids=["TX0"])
        save_state(baseline)

        # Process A and process B each load their OWN in-memory snapshot.
        proc_a = load_state()
        proc_b = load_state()

        # B completes a module and saves FIRST — unaware of anything A
        # will do later.
        proc_b.complete_module("mod_b", txids=["TXB"])
        proc_b.record_tx("TXB", "mod_b", "testnet", True)
        save_state(proc_b)

        # A completes a DIFFERENT module and saves SECOND, from a snapshot
        # that never saw B's write.
        proc_a.complete_module("mod_a", txids=["TXA"])
        proc_a.record_tx("TXA", "mod_a", "testnet", True)
        save_state(proc_a)

        final = load_state()
        completed_ids = {m.module_id for m in final.completed_modules}
        assert completed_ids == {"mod_zero", "mod_a", "mod_b"}, (
            f"lost update: expected all three modules, got {completed_ids}"
        )
        tx_ids = {t.txid for t in final.tx_index}
        assert tx_ids == {"TXA", "TXB"}, (
            f"lost update in tx_index: got {tx_ids}"
        )

    def test_three_way_interleave_preserves_all_tx_records(
        self, tmp_path, monkeypatch,
    ):
        """Extends the two-way case to three independent snapshots, each
        recording several tx entries, to pin that the merge scales beyond
        a single pair and that tx_index ends up sorted chronologically
        (not just unioned in arbitrary order) so doctor._check_last_error's
        ``failed[-1]`` still means "most recent" after a merge."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import LabState, load_state, save_state

        save_state(LabState(wallet_address="rSHARED"))

        snapshots = [load_state() for _ in range(3)]
        for i, snap in enumerate(snapshots):
            snap.record_tx(f"TX{i}", f"mod_{i}", "testnet", success=(i != 1))

        # Save in a DIFFERENT order than the snapshots were loaded, to
        # prove ordering of saves (not load order) doesn't matter either.
        save_state(snapshots[2])
        save_state(snapshots[0])
        save_state(snapshots[1])

        final = load_state()
        tx_ids = [t.txid for t in final.tx_index]
        assert set(tx_ids) == {"TX0", "TX1", "TX2"}, (
            f"expected all 3 tx records merged, got {tx_ids}"
        )
        # Chronological order preserved (timestamps were assigned in
        # ascending order as each record_tx() call ran earlier in this test).
        timestamps = [t.timestamp for t in final.tx_index]
        assert timestamps == sorted(timestamps), (
            "merged tx_index must stay chronologically sorted"
        )
        # The one recorded failure is still findable as "most recent
        # failure" via the same [-1]-of-filtered pattern doctor.py uses.
        failed = [t for t in final.tx_index if not t.success]
        assert len(failed) == 1
        assert failed[-1].txid == "TX1"

    def test_reset_module_is_not_resurrected_by_a_concurrent_merge(
        self, tmp_path, monkeypatch,
    ):
        """reset_module performs an INTENTIONAL removal. A naive "always
        merge" design would re-fold the just-removed module back in from
        the on-disk copy (which, at save time, still has it — that's
        exactly what's being removed) and silently undo the reset. This
        is why save_state() takes merge=False for this one call site —
        pin that reset_module actually stays reset."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )
        from xrpl_lab.state import LabState, load_state, reset_module, save_state

        s = LabState(wallet_address="rTEST")
        s.complete_module("mod_a", txids=["TXA"])
        s.complete_module("mod_b", txids=["TXB"])
        s.complete_module("mod_c", txids=["TXC"])
        save_state(s)

        reset_module("mod_b")

        final = load_state()
        ids = {m.module_id for m in final.completed_modules}
        assert ids == {"mod_a", "mod_c"}, (
            f"reset_module's removal was resurrected by the save-time "
            f"merge: {ids}"
        )

    def test_caller_state_object_untouched_by_merge_on_success(
        self, tmp_path, monkeypatch,
    ):
        """save_state() merges into a COPY, not the caller's own object —
        a save must never mutate the caller's in-memory LabState with
        entries from a concurrent writer the caller doesn't know about."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import LabState, save_state

        baseline = LabState(wallet_address="rBASE")
        baseline.complete_module("mod_disk_only")
        save_state(baseline)

        caller_state = LabState(wallet_address="rCALLER")
        caller_state.complete_module("mod_caller_only")
        save_state(caller_state)

        # The on-disk file has BOTH (merge worked)...
        from xrpl_lab.state import load_state
        on_disk_ids = {m.module_id for m in load_state().completed_modules}
        assert on_disk_ids == {"mod_disk_only", "mod_caller_only"}

        # ...but the caller's own object was never mutated to include the
        # disk-only entry it didn't know about.
        caller_ids = {m.module_id for m in caller_state.completed_modules}
        assert caller_ids == {"mod_caller_only"}, (
            "save_state must not mutate the caller's object via the merge"
        )

    def test_lock_serializes_real_concurrent_threads(self, tmp_path, monkeypatch):
        """Beyond the deterministic interleave above, prove the lock+merge
        combo holds under GENUINE OS-level concurrency: two threads each
        hammer save_state() with their own distinct module completions.
        Regardless of actual scheduling, the final file must contain
        every module both threads recorded — no lost updates, no torn
        writes (which would show up as a JSONDecodeError from load_state).
        """
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import LabState, load_state, save_state

        save_state(LabState(wallet_address="rSEED"))

        errors: list[BaseException] = []

        def worker(prefix: str, count: int) -> None:
            try:
                for i in range(count):
                    snap = load_state()
                    snap.complete_module(f"{prefix}_{i}")
                    save_state(snap)
            except BaseException as exc:  # noqa: BLE001 — surface in main thread
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=("alpha", 8))
        t2 = threading.Thread(target=worker, args=("beta", 8))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"worker thread(s) raised: {errors}"

        final = load_state()  # must not raise (proves no torn write)
        ids = {m.module_id for m in final.completed_modules}
        expected = {f"alpha_{i}" for i in range(8)} | {f"beta_{i}" for i in range(8)}
        missing = expected - ids
        assert not missing, f"lost update(s) under real concurrency: {missing}"

    def test_lock_timeout_raises_structured_exception_not_silent_clobber(
        self, tmp_path, monkeypatch,
    ):
        """When the advisory lock cannot be acquired within the bounded
        wait, save's critical section raises LabException(state_locked())
        — it must never hang forever and must never silently proceed
        unlocked (that would defeat the whole fix)."""
        import xrpl_lab.state as state_mod

        monkeypatch.setattr(state_mod, "_LOCK_TIMEOUT_S", 0.2)
        monkeypatch.setattr(state_mod, "_LOCK_POLL_INTERVAL_S", 0.02)

        target = tmp_path / "state.json"
        lock_path = state_mod._lock_path_for(target)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Hold the OS lock ourselves (simulating a stuck/very slow
        # concurrent writer) using the exact same primitive, but never
        # release it within the test's window.
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, os.SEEK_SET)
        assert state_mod._try_lock(fd), "test setup must acquire the lock first"

        try:
            with pytest.raises(LabException) as exc_info, state_mod._state_lock(target):
                pytest.fail("must not enter the critical section")
            assert exc_info.value.error.code == "STATE_LOCKED"
            assert exc_info.value.error.retryable is True
        finally:
            state_mod._unlock(fd)
            os.close(fd)

    def test_lock_released_after_write_failure_does_not_wedge_next_save(
        self, tmp_path, monkeypatch,
    ):
        """A save that raises mid-critical-section must still release the
        lock — otherwise every future save would hang/fail forever behind
        a lock nobody will ever release."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import LabState, save_state

        good = LabState(wallet_address="rGOOD")
        save_state(good)

        def boom(self, *a, **kw):
            raise RuntimeError("simulated mid-write failure")

        monkeypatch.setattr(LabState, "model_dump_json", boom)
        bad = LabState(wallet_address="rBAD")
        with pytest.raises(RuntimeError):
            save_state(bad)

        # Undo the monkeypatch and prove a FOLLOWING save still succeeds —
        # the lock from the failed save above must have been released.
        monkeypatch.undo()
        from xrpl_lab.state import load_state
        recovery = LabState(wallet_address="rRECOVER")
        save_state(recovery)  # must not hang or raise STATE_LOCKED
        assert load_state().wallet_address == "rRECOVER"

    def test_reset_state_removes_lock_sidecar(self, tmp_path, monkeypatch):
        """reset_state() should not leave the lock sidecar behind forever
        on a full wipe — best-effort cleanup, removed after release."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )
        from xrpl_lab.state import (
            LabState,
            _lock_path_for,
            reset_state,
            save_state,
            state_path,
        )

        save_state(LabState(wallet_address="rTEST"))
        lock_p = _lock_path_for(state_path())
        assert lock_p.exists(), "save_state should have created the lock sidecar"

        reset_state()
        assert not state_path().exists()
        assert not lock_p.exists()


# ═══════════════════════════════════════════════════════════════════════
# F-d6d7f5e8 (HIGH) — atomic tmp filename collision
# ═══════════════════════════════════════════════════════════════════════


class TestFd6d7f5e8UniqueTmpNames:
    def test_two_concurrent_writers_never_raise_fileexists(
        self, tmp_path, monkeypatch,
    ):
        """Two threads racing atomic_write_json against the SAME final
        path must never raise FileExistsError against each other — the
        unique pid+uuid4 tmp name means their O_EXCL opens can never
        collide."""
        from xrpl_lab._atomic import atomic_write_json

        path = tmp_path / "shared.json"
        errors: list[BaseException] = []

        def writer(tag: str) -> None:
            try:
                for i in range(15):
                    atomic_write_json(path, {"writer": tag, "i": i})
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(f"w{n}",)) for n in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"concurrent writers raised: {errors}"
        # Final file is valid JSON — no torn write.
        json.loads(path.read_text(encoding="utf-8"))
        # No leftover tmp litter from a crash-free run.
        assert not list(tmp_path.glob("shared.json.*.tmp"))

    def test_reset_module_save_state_lock_timeout_surfaces_structured_cli_error(
        self, tmp_path, monkeypatch,
    ):
        """cli.py's ``reset --module`` handler now also catches
        LabException (previously only ValueError) since reset_module's
        save_state() can raise LabException(state_locked()). Must show a
        structured code/message/hint and a non-zero exit — never an
        uncaught traceback."""
        from xrpl_lab.cli import main
        from xrpl_lab.errors import state_locked
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "home",
        )
        monkeypatch.setattr(
            "xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws",
        )

        s = LabState(wallet_address="rTEST")
        s.complete_module("receipt_literacy", txids=["TX1"])
        save_state(s)

        def _raise_locked(_module_id):
            raise LabException(state_locked())

        monkeypatch.setattr("xrpl_lab.state.reset_module", _raise_locked)

        runner = CliRunner()
        result = runner.invoke(main, [
            "reset", "--module", "receipt_literacy", "--confirm",
        ])
        assert result.exit_code != 0
        assert "Traceback (most recent call last)" not in result.output, (
            "must not leak a raw traceback to the CLI"
        )
        assert "STATE_LOCKED" in result.output
        assert "wait" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════
# F-ae597821 (HIGH) — runner.py generic step-failure exception leak
# ═══════════════════════════════════════════════════════════════════════


class TestFae597821StepFailureRedaction:
    @pytest.mark.asyncio
    async def test_generic_exception_does_not_leak_path_to_console(
        self, tmp_path, monkeypatch, caplog,
    ):
        """A GENERIC (non-LabException) exception from an action handler —
        e.g. an OSError whose str() embeds an absolute path + username —
        must never be interpolated into the console. Only the exception
        TYPE name goes to the console; the full detail goes to the logger
        at WARNING, mirroring the sibling recovery-save block's existing
        discipline."""
        from xrpl_lab.modules import ModuleDef, ModuleStep
        from xrpl_lab.runner import run_module
        from xrpl_lab.transport.dry_run import DryRunTransport

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        secret_path = r"C:\Users\SECRETUSER\.xrpl-lab\state.json.55512.abcd1234.tmp"

        async def _boom(*args, **kwargs):
            raise FileExistsError(f"[Errno 17] File exists: {secret_path!r}")

        monkeypatch.setattr("xrpl_lab.runner._execute_action", _boom)

        buf = io.StringIO()
        cap = Console(file=buf, no_color=True, markup=True, width=200)

        mod = ModuleDef(
            id="m1", title="M1", time="1m", level="beginner",
            requires=[], produces=[], checks=[],
            steps=[ModuleStep(text="t", action="send_payment", action_args={})],
            raw_body="",
        )

        with caplog.at_level(logging.WARNING, logger="xrpl_lab.runner"):
            result = await run_module(mod, DryRunTransport(), dry_run=True, console=cap)
        out = buf.getvalue()

        assert result is False
        assert "SECRETUSER" not in out, "OS username leaked to console"
        assert secret_path not in out, "absolute path leaked to console"
        assert "FileExistsError" in out, "safe exception type name must still show"
        assert "xrpl-lab doctor" in out, "doctor hint must still show"

        # Full detail (including the path) must still reach the log, so
        # server-side operators/facilitators aren't left with nothing.
        # Checked via "SECRETUSER" (not the full path) since the exception
        # message embeds the path via repr(), which doubles backslashes —
        # an exact-string match on the raw path would be brittle.
        full_log = "\n".join(r.message for r in caplog.records)
        assert "SECRETUSER" in full_log, (
            "full exception detail must still be logged server-side"
        )
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_lab_exception_path_unaffected(self, tmp_path, monkeypatch):
        """Sanity check: the OTHER branch (structured LabException) keeps
        showing its own code/message/hint exactly as before — this fix
        only changes the GENERIC exception branch."""
        from xrpl_lab.errors import LabError
        from xrpl_lab.modules import ModuleDef, ModuleStep
        from xrpl_lab.runner import run_module
        from xrpl_lab.transport.dry_run import DryRunTransport

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        async def _boom(*args, **kwargs):
            raise LabException(
                LabError(code="RUNTIME_TEST", message="clean failure", hint="try again")
            )

        monkeypatch.setattr("xrpl_lab.runner._execute_action", _boom)

        buf = io.StringIO()
        cap = Console(file=buf, no_color=True, markup=True, width=200)
        mod = ModuleDef(
            id="m1", title="M1", time="1m", level="beginner",
            requires=[], produces=[], checks=[],
            steps=[ModuleStep(text="t", action="send_payment", action_args={})],
            raw_body="",
        )
        result = await run_module(mod, DryRunTransport(), dry_run=True, console=cap)
        out = buf.getvalue()
        assert result is False
        assert "RUNTIME_TEST" in out
        assert "clean failure" in out
        assert "try again" in out


# ═══════════════════════════════════════════════════════════════════════
# F-eeddbf7f (MEDIUM) — Windows ACL doctor awareness
# ═══════════════════════════════════════════════════════════════════════


class TestFeeddbf7fWindowsAclCheck:
    def test_check_is_informational_and_mentions_acl_on_windows(self):
        import sys as _sys

        from xrpl_lab.doctor import _check_windows_dir_permissions

        check = _check_windows_dir_permissions()
        assert check.passed, "must be informational, never a hard failure"
        if _sys.platform == "win32":
            assert check.severity == "warn"
            assert "Windows" in check.detail or "ACL" in check.detail
            assert "icacls" in check.hint
        else:
            # POSIX: dataclass default severity, unused since passed=True
            # and no "warn" — renders as a plain, quiet pass.
            assert check.severity == "fail"
            assert "0o700" in check.detail

    @pytest.mark.asyncio
    async def test_check_is_registered_in_run_doctor(self, tmp_path, monkeypatch):
        from xrpl_lab.doctor import Check, run_doctor

        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        async def _stub_rpc() -> Check:
            return Check("RPC endpoint", True, "stub")

        async def _stub_faucet() -> Check:
            return Check("Faucet", True, "stub")

        monkeypatch.setattr("xrpl_lab.doctor._check_rpc", _stub_rpc)
        monkeypatch.setattr("xrpl_lab.doctor._check_faucet", _stub_faucet)

        report = await run_doctor()
        names = [c.name for c in report.checks]
        assert "Directory permissions" in names


# ═══════════════════════════════════════════════════════════════════════
# F-678304a1 (MEDIUM) — state.version never refreshed on save
# ═══════════════════════════════════════════════════════════════════════


class TestF678304a1VersionStamp:
    def test_save_state_stamps_current_version(self, tmp_path, monkeypatch):
        from xrpl_lab import __version__
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        stale = LabState(wallet_address="rTEST")
        stale.version = "0.0.1-ancient"
        save_state(stale)

        on_disk = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert on_disk["version"] == __version__

    def test_version_warning_fires_once_then_stops(self, tmp_path, monkeypatch, capsys):
        """Load with a stale version prints the warning; the very next
        save refreshes the field so a SUBSEQUENT load stays quiet."""
        from xrpl_lab import __version__
        from xrpl_lab.state import load_state, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)

        (tmp_path / "state.json").write_text(
            json.dumps({"version": "0.0.1-ancient", "network": "testnet"}),
            encoding="utf-8",
        )

        state = load_state()
        capsys.readouterr()  # drain the first (expected) warning
        assert state.version == "0.0.1-ancient"  # not yet refreshed until save

        save_state(state)  # F-678304a1: stamps __version__ before writing

        load_state()
        err = capsys.readouterr().err
        assert "Warning: state from v" not in err, (
            "version warning must not fire again after a save refreshed it"
        )

        on_disk = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert on_disk["version"] == __version__


# ═══════════════════════════════════════════════════════════════════════
# F-1e8c93d7 (MEDIUM) — ensure_wallet silently mints a new identity
# ═══════════════════════════════════════════════════════════════════════


class TestF1e8c93d7OrphanedWalletWarning:
    @pytest.mark.asyncio
    async def test_warns_when_configured_wallet_path_missing(
        self, tmp_path, monkeypatch,
    ):
        from xrpl_lab.runtime import ensure_wallet
        from xrpl_lab.state import LabState
        from xrpl_lab.transport.dry_run import DryRunTransport

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "home")

        missing_path = tmp_path / "old_location" / "wallet.json"
        state = LabState(
            wallet_address="rOLDADDRESS", wallet_path=str(missing_path),
        )

        buf = io.StringIO()
        cap = Console(file=buf, no_color=True, markup=True, width=200)

        new_state, _seed = await ensure_wallet(state, DryRunTransport(), cap)
        out = buf.getvalue()

        assert str(missing_path) in out, "must name the old missing path"
        assert "rOLDADDRESS" in out, "must name the previously known address"
        assert "No wallet found. Creating a new one" in out
        # A new wallet WAS created (falls through as before) — just with a
        # warning first.
        assert new_state.wallet_address != "rOLDADDRESS"

    @pytest.mark.asyncio
    async def test_no_warning_noise_on_fresh_install(self, tmp_path, monkeypatch):
        """Baseline case (wallet_path never set) must NOT gain the new
        warning — it's only for the "was configured, now missing" case."""
        from xrpl_lab.runtime import ensure_wallet
        from xrpl_lab.state import LabState
        from xrpl_lab.transport.dry_run import DryRunTransport

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path / "home")

        state = LabState()  # wallet_path is None — fresh install
        buf = io.StringIO()
        cap = Console(file=buf, no_color=True, markup=True, width=200)

        await ensure_wallet(state, DryRunTransport(), cap)
        out = buf.getvalue()

        assert "previously configured wallet" not in out
        assert "No wallet found. Creating a new one" in out


# ═══════════════════════════════════════════════════════════════════════
# F-0c21577b (MEDIUM) — atomic_write_json missing fsync
# ═══════════════════════════════════════════════════════════════════════


class TestF0c21577bFsyncDurability:
    def test_fsync_called_on_atomic_write(self, tmp_path, monkeypatch):
        from xrpl_lab._atomic import atomic_write_json

        calls: list[int] = []
        real_fsync = os.fsync

        def spy_fsync(fd):
            calls.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr("xrpl_lab._atomic.os.fsync", spy_fsync)

        path = tmp_path / "durable.json"
        atomic_write_json(path, {"k": "v"}, atomic=True)

        assert calls, "atomic_write_json must fsync the tmp file before rename"

    def test_fsync_called_on_non_atomic_write(self, tmp_path, monkeypatch):
        from xrpl_lab._atomic import atomic_write_json

        calls: list[int] = []
        real_fsync = os.fsync

        def spy_fsync(fd):
            calls.append(fd)
            return real_fsync(fd)

        monkeypatch.setattr("xrpl_lab._atomic.os.fsync", spy_fsync)

        path = tmp_path / "durable_direct.json"
        atomic_write_json(path, {"k": "v"}, atomic=False)

        assert calls, "non-atomic write must also fsync before returning"


# ═══════════════════════════════════════════════════════════════════════
# F-511dedbd (MEDIUM) — duplicate module id silently shadows
# ═══════════════════════════════════════════════════════════════════════


class TestF511dedbdDuplicateModuleId:
    _MODULE_TEXT = """\
---
id: {mod_id}
title: {title}
track: foundations
summary: A test module.
time: 1 min
level: beginner
requires: []
produces: []
checks: []
---

Body for {title}.
"""

    def test_duplicate_id_across_extra_dirs_first_wins_with_warning(
        self, tmp_path, capsys,
    ):
        from xrpl_lab.modules import load_all_modules

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "mod.md").write_text(
            self._MODULE_TEXT.format(mod_id="dup_test", title="First"),
            encoding="utf-8",
        )
        (dir_b / "mod.md").write_text(
            self._MODULE_TEXT.format(mod_id="dup_test", title="Second"),
            encoding="utf-8",
        )

        modules = load_all_modules(extra_dirs=[dir_a, dir_b])

        assert modules["dup_test"].title == "First", (
            "first-loaded module for a duplicate id must win"
        )
        err = capsys.readouterr().err
        assert "duplicate" in err.lower()
        assert "dup_test" in err

    def test_builtin_module_protected_from_extra_dir_shadow(self, tmp_path, capsys):
        """The realistic threat: a contributor's custom module in
        extra_dirs accidentally reuses a BUILT-IN id. Built-ins load
        first, so they must never be silently shadowed."""
        from xrpl_lab.modules import load_all_modules

        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "shadow.md").write_text(
            self._MODULE_TEXT.format(
                mod_id="receipt_literacy", title="Malicious Shadow",
            ),
            encoding="utf-8",
        )

        modules = load_all_modules(extra_dirs=[extra])

        assert modules["receipt_literacy"].title != "Malicious Shadow", (
            "a built-in module's content must not be shadowed by extra_dirs"
        )
        err = capsys.readouterr().err
        assert "receipt_literacy" in err
        assert "duplicate" in err.lower()

    def test_no_warning_when_ids_are_distinct(self, tmp_path, capsys):
        from xrpl_lab.modules import load_all_modules

        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "unique.md").write_text(
            self._MODULE_TEXT.format(mod_id="totally_unique_id", title="Unique"),
            encoding="utf-8",
        )

        modules = load_all_modules(extra_dirs=[extra])
        assert "totally_unique_id" in modules
        err = capsys.readouterr().err
        assert "duplicate" not in err.lower()


# ═══════════════════════════════════════════════════════════════════════
# F-99b70cc9 (LOW) — hardcoded personal KB path
# ═══════════════════════════════════════════════════════════════════════


class TestF99b70cc9NoHardcodedKbPath:
    def test_resolve_kb_db_returns_none_when_unset(self, monkeypatch):
        from xrpl_lab.linter import _resolve_kb_db

        monkeypatch.delenv("XRPL_LAB_KB_DB", raising=False)
        assert _resolve_kb_db() is None, (
            "no env var set must yield None — no rig-specific default path"
        )

    def test_resolve_kb_db_honors_explicit_env_var(self, tmp_path, monkeypatch):
        from xrpl_lab.linter import _resolve_kb_db

        target = tmp_path / "custom.db"
        monkeypatch.setenv("XRPL_LAB_KB_DB", str(target))
        assert _resolve_kb_db() == target

    def test_load_kb_capability_slugs_degrades_gracefully_with_no_default(
        self, monkeypatch,
    ):
        from xrpl_lab.linter import load_kb_capability_slugs

        monkeypatch.delenv("XRPL_LAB_KB_DB", raising=False)
        assert load_kb_capability_slugs() is None


# ═══════════════════════════════════════════════════════════════════════
# F-be051e03 (LOW) — doctor.log not written atomically
# ═══════════════════════════════════════════════════════════════════════


class TestFbe051e03DoctorLogAtomicWrite:
    def test_doctor_log_survives_simulated_crash_mid_write(
        self, tmp_path, monkeypatch,
    ):
        """A crash mid-write must leave the PREVIOUS good doctor.log
        intact — the whole point of routing through atomic_write_json
        instead of a plain write_text(). Simulate the crash by making the
        write into the tmp fd explode after O_EXCL already succeeded."""
        from xrpl_lab.doctor import Check, DoctorReport, _append_doctor_log

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: home)

        # Baseline: one real, successful append.
        report1 = DoctorReport()
        report1.checks.append(Check("Wallet", True, "Found: rX123"))
        _append_doctor_log(report1)

        log_path = home / "doctor.log"
        original_bytes = log_path.read_bytes()
        assert original_bytes, "baseline doctor.log must be non-empty"

        # Simulate a crash mid-write on the SECOND append.
        class BoomFile:
            def __init__(self, fd: int) -> None:
                self._fd = fd

            def __enter__(self) -> BoomFile:
                return self

            def __exit__(self, *exc: object) -> None:
                os.close(self._fd)

            def write(self, _text: str) -> int:
                raise OSError("simulated crash mid-write")

        def patched_fdopen(fd, *args, **kwargs):
            return BoomFile(fd)

        monkeypatch.setattr("xrpl_lab._atomic.os.fdopen", patched_fdopen)

        report2 = DoctorReport()
        report2.checks.append(Check("Wallet", False, "Not found"))
        _append_doctor_log(report2)  # must NOT raise (best-effort)

        assert log_path.read_bytes() == original_bytes, (
            "doctor.log must survive a crash mid-write intact (atomic write)"
        )
        # And no orphan tmp litter left behind either.
        assert not list(home.glob("doctor.log.*.tmp"))

    def test_doctor_log_still_appends_normally(self, tmp_path, monkeypatch):
        """Non-regression: the normal (no-crash) path still appends
        correctly through the new atomic-write plumbing."""
        from xrpl_lab.doctor import Check, DoctorReport, _append_doctor_log

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: home)

        for i in range(3):
            report = DoctorReport()
            report.checks.append(Check(f"Check{i}", True, "ok"))
            _append_doctor_log(report)

        log_path = home / "doctor.log"
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # each line still parses as JSON
