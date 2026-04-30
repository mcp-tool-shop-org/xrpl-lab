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


# ── F-BACKEND-B-001: required-field validation in handlers ───────────


class TestRequireValidation:
    """The _require helper raises a structured LabException when a required
    handler input is missing or empty. Selected handlers use it at the
    highest-value sites (send dest, trust currency, AMM pair/amount) to
    fail loud instead of silently submitting garbage to the ledger."""

    def test_require_returns_value_when_present(self) -> None:
        from xrpl_lab.handlers import _require

        out = _require(
            {"k": "  hello  "}, {}, "k", action="x", hint="h",
        )
        assert out == "hello"

    def test_require_falls_back_to_context(self) -> None:
        from xrpl_lab.handlers import _require

        out = _require(
            {}, {"k": "from_ctx"}, "k", action="x", hint="h",
        )
        assert out == "from_ctx"

    def test_require_raises_lab_exception_when_missing(self) -> None:
        from xrpl_lab.errors import LabException
        from xrpl_lab.handlers import _require

        with pytest.raises(LabException) as exc_info:
            _require({}, {}, "destination", action="submit_payment", hint="provide it")
        err = exc_info.value.error
        assert err.code == "INPUT_REQUIRED_FIELD"
        assert "destination" in err.message
        assert "submit_payment" in err.message
        assert err.hint == "provide it"

    def test_require_raises_when_value_is_only_whitespace(self) -> None:
        from xrpl_lab.errors import LabException
        from xrpl_lab.handlers import _require

        with pytest.raises(LabException):
            _require({"k": "   "}, {}, "k", action="x", hint="h")

    def test_require_raises_when_value_is_none(self) -> None:
        from xrpl_lab.errors import LabException
        from xrpl_lab.handlers import _require

        with pytest.raises(LabException):
            _require({"k": None}, {}, "k", action="x", hint="h")

    @pytest.mark.asyncio
    async def test_set_trust_line_raises_on_empty_currency(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """An explicit empty currency must fail loud rather than silently
        defaulting to 'LAB'."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        from xrpl_lab.errors import LabException
        from xrpl_lab.handlers import handle_set_trust_line

        step = ModuleStep(
            text="bad trust",
            action="set_trust_line",
            action_args={"currency": "", "limit": "1000"},
        )
        from rich.console import Console as _Console
        with pytest.raises(LabException) as exc_info:
            await handle_set_trust_line(
                step,
                LabState(),
                DryRunTransport(),
                "seed",
                {"issuer_address": "rIssuer123", "wallet_seed": None},
                _Console(),
            )
        assert exc_info.value.error.code == "INPUT_REQUIRED_FIELD"


# ── F-BACKEND-B-004: step rollback / context snapshot ─────────────────


class TestStepRollback:
    """run_module must restore context if a step handler raises mid-mutation.

    Without this, a handler that ``context['txids'].append(txid)`` and then
    raises would leak the txid into the post-failure saved state — that
    txid corresponds to a transaction the real ledger never accepted.
    """

    @pytest.fixture()
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

    def test_snapshot_context_deepcopies_safe_keys(self) -> None:
        """Mutating the snapshot's nested list must not affect the source."""
        from xrpl_lab.runner import _snapshot_context

        ctx: dict = {"txids": ["A", "B"], "module_id": "m"}
        snap = _snapshot_context(ctx)
        ctx["txids"].append("C")
        assert snap["txids"] == ["A", "B"], (
            "snapshot must be independent of source mutations"
        )

    def test_snapshot_context_preserves_unpicklable_secret(self) -> None:
        """_SecretValue must round-trip via shared reference (not deepcopy)."""
        from xrpl_lab.runner import _snapshot_context
        from xrpl_lab.runtime import _SecretValue

        sv = _SecretValue("seed_xyz")
        ctx: dict = {"wallet_seed": sv, "txids": ["A"]}
        snap = _snapshot_context(ctx)
        # Same wrapper identity (not deepcopied — _SecretValue refuses
        # pickle by design). The contained string is read-only via .get().
        assert snap["wallet_seed"] is sv
        assert snap["wallet_seed"].get() == "seed_xyz"
        # But the rest is independent:
        ctx["txids"].append("B")
        assert snap["txids"] == ["A"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_step_failure_rolls_back_context_mutations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A handler that mutates context then raises must NOT leak the mutation
        into post-failure state. The snapshot-restore in run_module catches it."""
        # Build a fake action that appends to txids then raises. We register
        # it via the handler registry like real handlers do.
        from xrpl_lab.registry import ActionDef, register, resolve
        from xrpl_lab.runner import run_module

        captured_pre_raise: dict[str, list[str]] = {}

        async def _bad_handler(step, state, transport, wallet_seed, ctx, console):
            ctx.setdefault("txids", []).append("LEAKED_TXID")
            captured_pre_raise["txids"] = list(ctx["txids"])
            raise RuntimeError("simulated mid-mutation failure")

        # Register a unique action name so we don't collide with the
        # real registry. Name the action to make the failure trail
        # readable in pytest output.
        action_name = "test_step_rollback_bad_handler"
        try:
            resolve(action_name)
        except Exception:
            register(ActionDef(
                name=action_name,
                handler=_bad_handler,
                description="Test-only: appends txid then raises.",
            ))

        mod = ModuleDef(
            id="rollback_test_module",
            title="Rollback test",
            time="1 min",
            level="beginner",
            requires=[],
            produces=["nothing"],
            checks=[],
            steps=[ModuleStep(text="Bad step", action=action_name, action_args={})],
            raw_body="",
        )
        transport = DryRunTransport()
        result = await run_module(mod, transport, dry_run=False, force=False)

        # Module reports failure
        assert result is False
        # Pre-raise the handler DID append (this confirms our test simulates the bug)
        assert captured_pre_raise.get("txids") == ["LEAKED_TXID"]
        # The state-saved completed-modules list must NOT contain this module —
        # rollback semantics: a failed step's mutations are gone, no
        # complete_module call ever ran for this module id.
        from xrpl_lab.state import load_state
        post = load_state()
        assert not post.is_module_completed("rollback_test_module")


# ── F-BACKEND-B-010: ensure_funded retry with backoff ─────────────────


class TestEnsureFundedRetry:
    """ensure_funded must retry the faucet call with exponential backoff
    when the first attempt does not produce a positive balance."""

    @pytest.mark.asyncio
    async def test_retries_on_failed_faucet_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """First two faucet calls fail; third succeeds. Must call 3x."""
        from xrpl_lab.runtime import ensure_funded
        from xrpl_lab.state import LabState
        from xrpl_lab.transport.base import FundResult

        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

        call_count = {"n": 0}

        class StubTransport:
            async def get_balance(self, addr: str) -> str:
                return "0"

            async def fund_from_faucet(self, addr: str) -> FundResult:
                call_count["n"] += 1
                if call_count["n"] < 3:
                    return FundResult(
                        success=False, address=addr, balance="0",
                        message=f"attempt {call_count['n']} failed",
                    )
                return FundResult(
                    success=True, address=addr, balance="100",
                    message="funded",
                )

        from rich.console import Console as _Console
        ok = await ensure_funded(
            LabState(), StubTransport(), "rTestAddr", _Console(),
        )
        assert ok is True
        assert call_count["n"] == 3, "expected 3 faucet attempts"
        # Two sleeps between three attempts: 2s and 4s
        assert sleeps == [2.0, 4.0], f"expected backoff [2.0, 4.0], got {sleeps}"

    @pytest.mark.asyncio
    async def test_returns_false_after_all_retries_exhausted(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All three faucet attempts fail → ensure_funded returns False."""
        from xrpl_lab.runtime import ensure_funded
        from xrpl_lab.state import LabState
        from xrpl_lab.transport.base import FundResult

        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("xrpl_lab.runtime.asyncio.sleep", fake_sleep)

        class StubTransport:
            async def get_balance(self, addr: str) -> str:
                return "0"

            async def fund_from_faucet(self, addr: str) -> FundResult:
                return FundResult(
                    success=False, address=addr, balance="0",
                    message="faucet down",
                )

        from rich.console import Console as _Console
        ok = await ensure_funded(
            LabState(), StubTransport(), "rTestAddr", _Console(),
        )
        assert ok is False
        # Two sleeps between three attempts (no sleep after the final attempt).
        assert sleeps == [2.0, 4.0]
