"""Tests for state management."""



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
