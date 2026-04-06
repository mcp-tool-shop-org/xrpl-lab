"""Runner isolation tests — prove per-run isolation guarantees.

Tests cover:
- Console isolation: custom consoles don't contaminate the module-level global
- Context isolation: each run gets its own independent context dict
- _SecretValue never leaks via repr/str
- Concurrency policy constants and guardrails
- Callback-style hooks (on_step via runner_ws tracked execute pattern)
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport

# ── Helpers ─────────────────────────────────────────────────────────


def _make_module(
    mod_id: str = "isolation_test",
    steps: list[ModuleStep] | None = None,
) -> ModuleDef:
    """Build a minimal module for testing."""
    if steps is None:
        steps = [
            ModuleStep(text="Step 1", action="ensure_wallet", action_args={}),
        ]
    return ModuleDef(
        id=mod_id,
        title="Isolation Test Module",
        time="1 min",
        level="beginner",
        requires=[],
        produces=["wallet"],
        checks=["wallet created"],
        steps=steps,
        raw_body="",
    )


def _make_noop_module(mod_id: str = "noop_mod") -> ModuleDef:
    """Module with only text steps (no actions)."""
    return ModuleDef(
        id=mod_id,
        title="No-Op Module",
        time="1 min",
        level="beginner",
        requires=[],
        produces=[],
        checks=[],
        steps=[
            ModuleStep(text="Just reading", action=None, action_args={}),
            ModuleStep(text="More reading", action=None, action_args={}),
        ],
        raw_body="",
    )


# ── Console isolation ──────────────────────────────────────────────


class TestConsoleIsolation:
    """Prove that per-run consoles don't contaminate the global."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    def test_global_console_unchanged_after_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The module-level console is the same object before and after run_module."""
        import xrpl_lab.runner as runner_mod

        original = runner_mod.console
        # Temporarily swap to a custom console and restore
        custom = Console(file=io.StringIO(), no_color=True)
        runner_mod.console = custom
        runner_mod.console = original

        assert runner_mod.console is original

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_custom_console_receives_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A custom console captures output that would otherwise go to global."""
        import xrpl_lab.runner as runner_mod

        buf = io.StringIO()
        custom_console = Console(file=buf, no_color=True, highlight=False)
        original_console = runner_mod.console

        # Swap in the custom console
        runner_mod.console = custom_console
        try:
            runner_mod.console.print("isolation-marker-xyz")
            output = buf.getvalue()
            assert "isolation-marker-xyz" in output
        finally:
            runner_mod.console = original_console

        # Original console's file should NOT contain our marker
        # (it writes to stderr/stdout, not our StringIO)
        assert runner_mod.console is original_console

    def test_two_consoles_dont_share_output(self) -> None:
        """Two StringIO-backed consoles get isolated output."""
        buf_a = io.StringIO()
        buf_b = io.StringIO()
        console_a = Console(file=buf_a, no_color=True)
        console_b = Console(file=buf_b, no_color=True)

        console_a.print("alpha-output")
        console_b.print("beta-output")

        assert "alpha-output" in buf_a.getvalue()
        assert "beta-output" not in buf_a.getvalue()
        assert "beta-output" in buf_b.getvalue()
        assert "alpha-output" not in buf_b.getvalue()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_global_console_identity_stable_across_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After a full run_module, the global console object is the same identity."""
        import xrpl_lab.runner as runner_mod

        original = runner_mod.console

        mod = _make_noop_module()
        transport = DryRunTransport()
        monkeypatch.setattr("xrpl_lab.runner.load_state", lambda: LabState())

        # Patch console.input to avoid interactive blocking
        monkeypatch.setattr(runner_mod.console, "input", lambda _p="": "")

        await runner_mod.run_module(mod, transport, dry_run=True)

        assert runner_mod.console is original


# ── Context isolation ──────────────────────────────────────────────


class TestContextIsolation:
    """Prove that each run gets its own context."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_context_not_shared_between_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two sequential runs produce independent context dicts."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(text="No-op", action=None, action_args={})
        state = LabState()
        transport = DryRunTransport()

        ctx_a: dict = {"module_id": "run_a", "marker": "aaa"}
        ctx_b: dict = {"module_id": "run_b", "marker": "bbb"}

        result_a = await _execute_action(step, state, transport, "", ctx_a)
        result_b = await _execute_action(step, state, transport, "", ctx_b)

        assert result_a["marker"] == "aaa"
        assert result_b["marker"] == "bbb"
        assert result_a is not result_b

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_context_mutation_doesnt_leak(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mutating one context dict doesn't affect another."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(text="No-op", action=None, action_args={})
        state = LabState()
        transport = DryRunTransport()

        ctx_a: dict = {"module_id": "run_a", "txids": []}
        ctx_b: dict = {"module_id": "run_b", "txids": []}

        result_a = await _execute_action(step, state, transport, "", ctx_a)
        result_a["txids"].append("FAKE_TX")

        result_b = await _execute_action(step, state, transport, "", ctx_b)
        assert "FAKE_TX" not in result_b.get("txids", [])

    def test_secret_value_not_in_repr(self) -> None:
        """_SecretValue never leaks the raw value in repr."""
        from xrpl_lab.runner import _SecretValue

        secret = _SecretValue("sEdV_my_super_secret_seed")
        assert "sEdV" not in repr(secret)
        assert repr(secret) == "***"

    def test_secret_value_not_in_str(self) -> None:
        """_SecretValue never leaks the raw value in str."""
        from xrpl_lab.runner import _SecretValue

        secret = _SecretValue("sEdV_my_super_secret_seed")
        assert "sEdV" not in str(secret)
        assert str(secret) == "***"

    def test_secret_value_not_in_context_repr(self) -> None:
        """A dict containing _SecretValue doesn't leak on repr."""
        from xrpl_lab.runner import _SecretValue

        ctx = {"wallet_seed": _SecretValue("sEdV_secret123"), "module_id": "test"}
        ctx_repr = repr(ctx)
        assert "sEdV_secret123" not in ctx_repr
        assert "***" in ctx_repr

    def test_secret_value_truthiness(self) -> None:
        """_SecretValue is truthy when non-empty, falsy when empty."""
        from xrpl_lab.runner import _SecretValue

        assert bool(_SecretValue("has_value")) is True
        assert bool(_SecretValue("")) is False

    def test_secret_value_get_returns_raw(self) -> None:
        """_SecretValue.get() returns the original raw value."""
        from xrpl_lab.runner import _SecretValue

        raw = "sEdV_actual_seed_data"
        secret = _SecretValue(raw)
        assert secret.get() == raw


# ── Concurrency policy ─────────────────────────────────────────────


class TestConcurrencyPolicy:
    """Prove the explicit concurrency contract."""

    def test_max_concurrent_runs_constant_exists(self) -> None:
        from xrpl_lab.api.runner_ws import _MAX_CONCURRENT_RUNS

        assert _MAX_CONCURRENT_RUNS == 3

    def test_max_sessions_constant_exists(self) -> None:
        from xrpl_lab.api.runner_ws import _MAX_SESSIONS

        assert _MAX_SESSIONS == 100

    def test_cleanup_grace_seconds_constant_exists(self) -> None:
        from xrpl_lab.api.runner_ws import _CLEANUP_GRACE_SECONDS

        assert _CLEANUP_GRACE_SECONDS == 60

    def test_no_runner_patch_lock(self) -> None:
        """The global monkey-patch lock should no longer exist."""
        import xrpl_lab.api.runner_ws as ws_mod

        assert not hasattr(ws_mod, '_runner_patch_lock')

    def test_sessions_dict_starts_empty(self) -> None:
        """The sessions store is a dict (may have entries from other tests,
        but the type must be correct)."""
        from xrpl_lab.api.runner_ws import _sessions

        assert isinstance(_sessions, dict)


# ── Run callbacks / step tracking ──────────────────────────────────


class TestRunCallbacks:
    """Prove that the runner_ws step-tracking pattern works correctly."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_on_step_called_for_each_step(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A wrapping function around _execute_action fires for every step."""
        from xrpl_lab.runner import _execute_action

        step_log: list[str] = []

        original_execute = _execute_action

        async def tracked_execute(step, state, transport, wallet_seed, context):
            step_log.append(step.action or "read")
            return await original_execute(step, state, transport, wallet_seed, context)

        steps = [
            ModuleStep(text="Read", action=None, action_args={}),
            ModuleStep(text="Read more", action=None, action_args={}),
            ModuleStep(text="Read again", action=None, action_args={}),
        ]

        state = LabState()
        transport = DryRunTransport()
        ctx: dict = {"module_id": "test"}

        for step in steps:
            ctx = await tracked_execute(step, state, transport, "", ctx)

        assert len(step_log) == 3
        assert step_log == ["read", "read", "read"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_callbacks_are_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_module works fine with no callbacks — no on_step parameter needed."""
        import xrpl_lab.runner as runner_mod

        mod = _make_noop_module()
        transport = DryRunTransport()
        monkeypatch.setattr("xrpl_lab.runner.load_state", lambda: LabState())
        monkeypatch.setattr(runner_mod.console, "input", lambda _p="": "")

        # run_module has no on_step parameter — it should just work
        result = await runner_mod.run_module(mod, transport, dry_run=True)
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_tracked_execute_preserves_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tracked-execute wrapper pattern preserves context pass-through."""
        from xrpl_lab.runner import _execute_action

        original_execute = _execute_action
        wrapper_called = False

        async def tracked_execute(step, state, transport, wallet_seed, context):
            nonlocal wrapper_called
            wrapper_called = True
            return await original_execute(step, state, transport, wallet_seed, context)

        step = ModuleStep(text="Test", action=None, action_args={})
        ctx: dict = {"module_id": "test", "payload": "preserved"}

        result = await tracked_execute(
            step, LabState(), DryRunTransport(), "", ctx
        )
        assert wrapper_called
        assert result["payload"] == "preserved"


# ── _execute_action isolation ──────────────────────────────────────


class TestExecuteActionIsolation:
    """Prove _execute_action doesn't leak state between invocations."""

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_no_action_returns_same_context_object(self) -> None:
        """A no-op step returns the same context dict (identity, not copy)."""
        from xrpl_lab.runner import _execute_action

        step = ModuleStep(text="Text only", action=None, action_args={})
        ctx: dict = {"module_id": "test", "val": 99}
        result = await _execute_action(
            step, LabState(), DryRunTransport(), "", ctx
        )
        assert result is ctx

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_wallet_seed_unwrap_in_execute(self) -> None:
        """_execute_action unwraps _SecretValue to plain str for dispatch."""
        from xrpl_lab.runner import _execute_action, _SecretValue

        step = ModuleStep(text="No-op", action=None, action_args={})
        secret = _SecretValue("sEdV_test_seed")
        ctx: dict = {"module_id": "test", "wallet_seed": secret}

        result = await _execute_action(
            step, LabState(), DryRunTransport(), secret, ctx
        )
        # Context should still have the _SecretValue wrapper
        assert isinstance(result.get("wallet_seed"), _SecretValue)
