"""Runner tests — validate highest-risk flows using DryRunTransport.

Tests cover:
- Wallet-required action guard (no wallet_seed -> early return)
- Context propagation through _execute_action
- run_module prerequisite/completion checks
- DryRunTransport deterministic behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport

# ── DryRunTransport deterministic behavior ───────────────────────────


class TestDryRunTransport:
    """DryRunTransport must produce deterministic, unique transaction IDs."""

    def test_unique_txids(self) -> None:
        """Each call to _next_txid returns a different value."""
        t = DryRunTransport()
        ids = {t._next_txid() for _ in range(20)}
        assert len(ids) == 20, "DryRunTransport produced duplicate txids"

    def test_txid_is_hex_string(self) -> None:
        t = DryRunTransport()
        txid = t._next_txid()
        assert isinstance(txid, str)
        assert len(txid) == 64
        # Must be valid uppercase hex
        int(txid, 16)

    def test_network_name_is_dry_run(self) -> None:
        t = DryRunTransport()
        assert t.network_name == "dry-run"

    @pytest.mark.asyncio
    async def test_get_network_info_connected(self) -> None:
        t = DryRunTransport()
        info = await t.get_network_info()
        assert info.connected is True
        assert info.network == "dry-run"

    @pytest.mark.asyncio
    async def test_fund_from_faucet_succeeds(self) -> None:
        t = DryRunTransport()
        result = await t.fund_from_faucet("rTestAddr123")
        assert result.success is True
        assert float(result.balance) > 0


# ── _execute_action wallet guard ─────────────────────────────────────


class TestExecuteActionWalletGuard:
    """Actions in _WALLET_REQUIRED_ACTIONS must early-return when wallet_seed
    is empty, without raising exceptions."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_submit_payment_without_wallet_returns_context(self) -> None:
        """submit_payment with empty wallet_seed returns context unchanged."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(
            text="Pay something",
            action="submit_payment",
            action_args={"destination": "rFake", "amount": "10"},
        )
        state = LabState()
        transport = DryRunTransport()
        context: dict = {"module_id": "test"}

        result = await _execute_action(
            step, state, transport, wallet_seed="", context=context
        )
        # Should return context without crashing — no txids added
        assert "txids" not in result or len(result.get("txids", [])) == 0

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_set_trust_line_without_wallet_returns_context(self) -> None:
        """set_trust_line with empty wallet_seed returns context unchanged."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(
            text="Set trust",
            action="set_trust_line",
            action_args={"currency": "LAB", "limit": "1000"},
        )
        state = LabState()
        transport = DryRunTransport()
        context: dict = {"module_id": "test"}

        result = await _execute_action(
            step, state, transport, wallet_seed="", context=context
        )
        assert "txids" not in result or len(result.get("txids", [])) == 0

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_cancel_offer_without_wallet_returns_context(self) -> None:
        """cancel_offer with empty wallet_seed returns context unchanged."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(
            text="Cancel offer",
            action="cancel_offer",
            action_args={},
        )
        state = LabState()
        transport = DryRunTransport()
        context: dict = {"module_id": "test"}

        result = await _execute_action(
            step, state, transport, wallet_seed="", context=context
        )
        assert "txids" not in result or len(result.get("txids", [])) == 0


# ── _execute_action no-op for empty action ───────────────────────────


class TestExecuteActionNoOp:
    """Steps with no action should pass through without side-effects."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_no_action_returns_context_unchanged(self) -> None:
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(text="Just some text", action=None, action_args={})
        state = LabState()
        transport = DryRunTransport()
        context = {"module_id": "test", "marker": 42}

        result = await _execute_action(
            step, state, transport, wallet_seed="seed123", context=context
        )
        assert result["marker"] == 42


# ── run_module already-completed guard ───────────────────────────────


class TestRunModuleCompletionGuard:
    """run_module should return True immediately for already-completed modules
    (when not in dry_run or force mode)."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_already_completed_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from xrpl_lab.runner import run_module

        state = LabState()
        state.complete_module("receipt_literacy")
        monkeypatch.setattr("xrpl_lab.runner.load_state", lambda: state)

        mod = ModuleDef(
            id="receipt_literacy",
            title="Receipt Literacy",
            time="15 min",
            level="beginner",
            requires=[],
            produces=["wallet"],
            checks=["wallet created"],
            steps=[ModuleStep(text="Step 1", action="ensure_wallet", action_args={})],
            raw_body="",
        )
        transport = DryRunTransport()
        result = await run_module(mod, transport, dry_run=False, force=False)
        assert result is True
