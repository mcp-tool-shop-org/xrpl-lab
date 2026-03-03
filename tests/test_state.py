"""Tests for state management."""



from xrpl_lab.state import LabState


class TestLabState:
    def test_fresh_state(self):
        state = LabState()
        assert state.version == "0.7.0"
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
