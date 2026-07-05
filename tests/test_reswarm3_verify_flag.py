"""Re-swarm-3 LOAD-BEARING: verified flag + honest proof pack.

The director's decision ("verified flag + honest pack"): a module run that
FAILS its on-ledger verification must no longer record as a silently-green
"completed" module. Instead:

  * a failed verification surfaces loudly (the handler already prints it) but
    does NOT crash the lesson (no raise, remaining steps still run);
  * the ``CompletedModule`` record carries a ``verified: bool`` (default True
    for back-compat);
  * the proof pack surfaces each module's ``verified`` plus a top-level
    ``all_verified`` folded into the SHA-256 so an honest pack cannot be
    edited to hide a failed verification without breaking its own hash;
  * a step whose verification failed flips its ``on_step_complete`` success to
    False so the dashboard (api/runner_ws.py) forwards the real state
    (PB-001);
  * an OLD state.json without a ``verified`` field still loads via the
    migration seam (PB-004).

These tests are written FIRST and must go RED before the implementation, then
GREEN after. Each proves non-vacuously that the fix is load-bearing.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.handlers import _record_verification
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.registry import ActionDef, register, resolve
from xrpl_lab.reporting import generate_proof_pack, verify_proof_pack
from xrpl_lab.state import CompletedModule, LabState
from xrpl_lab.transport.dry_run import DryRunTransport

# ── Test-only handlers that emit real pass/fail verification signals ──


async def _passing_verify_handler(step, state, transport, wallet_seed, ctx, console):
    """A verify handler that records a PASSING verification (0 failures)."""
    _record_verification(ctx, "test_pass", passed=True, failures=[])
    console.print("  [green]verified ok[/]")
    return ctx


async def _failing_verify_handler(step, state, transport, wallet_seed, ctx, console):
    """A verify handler that records a FAILING verification."""
    _record_verification(
        ctx, "test_fail", passed=False, failures=["on-ledger check did not match"]
    )
    console.print("  [red]verification failed[/]")
    return ctx


# A sentinel that later steps flip so we can prove a failed verification does
# NOT abort the remaining steps of the lesson.
_LATER_STEP_RAN: dict[str, bool] = {}


async def _marker_handler(step, state, transport, wallet_seed, ctx, console):
    _LATER_STEP_RAN["ran"] = True
    return ctx


def _register_test_handlers() -> None:
    for name, handler in (
        ("test_passing_verify", _passing_verify_handler),
        ("test_failing_verify", _failing_verify_handler),
        ("test_marker_step", _marker_handler),
    ):
        try:
            resolve(name)
        except Exception:
            register(ActionDef(name=name, handler=handler, description="test-only"))


@pytest.fixture()
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    _register_test_handlers()
    _LATER_STEP_RAN.clear()


def _module(mid: str, steps: list[ModuleStep]) -> ModuleDef:
    return ModuleDef(
        id=mid,
        title=f"Module {mid}",
        time="1 min",
        level="beginner",
        requires=[],
        produces=[],
        checks=[],
        steps=steps,
        raw_body="",
    )


# ── 1. Failed verify → verified=False in state AND pack; all_verified False ──


class TestFailedVerificationHonestPack:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_failed_verify_records_verified_false(self) -> None:
        from xrpl_lab.runner import run_module
        from xrpl_lab.state import load_state

        mod = _module(
            "vmod_fail",
            [ModuleStep(text="verify", action="test_failing_verify", action_args={})],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        result = await run_module(
            mod, DryRunTransport(), dry_run=True, console=console
        )
        # The lesson still "completes" (it did not crash) ...
        assert result is True
        # ... but the module record is honestly marked NOT verified.
        state = load_state()
        cm = next(m for m in state.completed_modules if m.module_id == "vmod_fail")
        assert cm.verified is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_failed_verify_pack_all_verified_false_and_hash_reflects(
        self,
    ) -> None:
        from xrpl_lab.runner import run_module
        from xrpl_lab.state import load_state

        mod = _module(
            "vmod_fail2",
            [ModuleStep(text="verify", action="test_failing_verify", action_args={})],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        await run_module(mod, DryRunTransport(), dry_run=True, console=console)

        state = load_state()
        pack = generate_proof_pack(state)

        # The module entry surfaces verified=False.
        entry = next(
            m for m in pack["completed_modules"] if m["module_id"] == "vmod_fail2"
        )
        assert entry["verified"] is False
        # Top-level honest flag is False.
        assert pack["all_verified"] is False
        # The self-hash still verifies (all_verified is folded in, not tacked on).
        ok, _msg = verify_proof_pack(pack)
        assert ok is True

    def test_flipping_verified_changes_the_hash(self) -> None:
        """all_verified is INSIDE the hashed dict — flipping it must change the
        SHA-256 (proves it is folded in, not appended after hashing)."""
        state = LabState(network="testnet", wallet_address="rTEST")
        # Two modules, one verified, one not.
        state.complete_module("ok_mod", txids=["TXA"], verified=True)
        state.complete_module("bad_mod", txids=["TXB"], verified=False)
        pack_unverified = generate_proof_pack(state)
        assert pack_unverified["all_verified"] is False
        hash_unverified = pack_unverified["sha256"]

        # Now a state where both are verified → all_verified True → different hash.
        state2 = LabState(network="testnet", wallet_address="rTEST")
        state2.complete_module("ok_mod", txids=["TXA"], verified=True)
        state2.complete_module("bad_mod", txids=["TXB"], verified=True)
        pack_verified = generate_proof_pack(state2)
        assert pack_verified["all_verified"] is True
        assert pack_verified["sha256"] != hash_unverified

    def test_flipping_only_all_verified_breaks_the_seal(self) -> None:
        """Isolate the TOP-LEVEL all_verified's hash contribution: flip ONLY it
        in a sealed pack (leaving per-module `verified` untouched) and the
        integrity check must fail — proving all_verified itself is folded in,
        not merely correlated with the per-module flags that are also hashed."""
        state = LabState(network="testnet", wallet_address="rTEST")
        state.complete_module("ok_mod", txids=["TXA"], verified=True)
        state.complete_module("bad_mod", txids=["TXB"], verified=False)
        pack = generate_proof_pack(state)
        assert pack["all_verified"] is False
        # Tamper: flip only the top-level flag; per-module `verified` stays [T, F].
        pack["all_verified"] = True
        valid, _ = verify_proof_pack(pack)
        assert valid is False


# ── 2. Passing verify → verified=True, all_verified True ─────────────


class TestPassingVerificationHonestPack:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_passing_verify_records_verified_true(self) -> None:
        from xrpl_lab.runner import run_module
        from xrpl_lab.state import load_state

        mod = _module(
            "vmod_ok",
            [ModuleStep(text="verify", action="test_passing_verify", action_args={})],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        result = await run_module(
            mod, DryRunTransport(), dry_run=True, console=console
        )
        assert result is True

        state = load_state()
        cm = next(m for m in state.completed_modules if m.module_id == "vmod_ok")
        assert cm.verified is True

        pack = generate_proof_pack(state)
        entry = next(
            m for m in pack["completed_modules"] if m["module_id"] == "vmod_ok"
        )
        assert entry["verified"] is True
        assert pack["all_verified"] is True

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_module_with_no_verify_steps_defaults_verified_true(self) -> None:
        """Back-compat: a module that never verifies anything is verified=True
        (the default). The honest-pack change must not regress the common
        no-verify module into a false 'unverified' state."""
        from xrpl_lab.runner import run_module
        from xrpl_lab.state import load_state

        mod = _module(
            "vmod_none",
            [ModuleStep(text="just text", action=None, action_args={})],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        await run_module(mod, DryRunTransport(), dry_run=True, console=console)

        state = load_state()
        cm = next(m for m in state.completed_modules if m.module_id == "vmod_none")
        assert cm.verified is True


# ── 3. Failed verification does NOT raise / does NOT abort later steps ──


class TestFailedVerificationDoesNotAbort:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_failed_verify_does_not_abort_remaining_steps(self) -> None:
        from xrpl_lab.runner import run_module
        from xrpl_lab.state import load_state

        mod = _module(
            "vmod_continue",
            [
                ModuleStep(
                    text="verify (fails)",
                    action="test_failing_verify",
                    action_args={},
                ),
                ModuleStep(
                    text="later step",
                    action="test_marker_step",
                    action_args={},
                ),
            ],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        # Skip the interactive between-steps pause (mirrors runner_ws.py's
        # capture_console.input stub used in dashboard mode).
        console.input = lambda _prompt="": ""  # type: ignore[method-assign]
        result = await run_module(
            mod, DryRunTransport(), dry_run=True, console=console
        )
        # Did not crash; the module completed.
        assert result is True
        # The step AFTER the failed verification still ran (no abort).
        assert _LATER_STEP_RAN.get("ran") is True
        # And the module is still honestly marked unverified.
        state = load_state()
        cm = next(
            m for m in state.completed_modules if m.module_id == "vmod_continue"
        )
        assert cm.verified is False

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_failed_verify_flips_on_step_complete_success_false(self) -> None:
        """PB-001: a pure verify step must forward success=False to
        on_step_complete when its verification failed — otherwise the dashboard
        always shows green even for a failed on-ledger check."""
        from xrpl_lab.runner import run_module

        events: list[tuple[str, bool]] = []

        async def _on_step_complete(action: str, success: bool) -> None:
            events.append((action, success))

        mod = _module(
            "vmod_wscheck",
            [
                ModuleStep(
                    text="verify (fails)",
                    action="test_failing_verify",
                    action_args={},
                ),
            ],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        await run_module(
            mod,
            DryRunTransport(),
            dry_run=True,
            console=console,
            on_step_complete=_on_step_complete,
        )
        # The verify step reported success=False to the dashboard callback.
        assert ("test_failing_verify", False) in events

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_env")
    async def test_passing_verify_reports_success_true(self) -> None:
        """A passing verify step must still report success=True (no false red)."""
        from xrpl_lab.runner import run_module

        events: list[tuple[str, bool]] = []

        async def _on_step_complete(action: str, success: bool) -> None:
            events.append((action, success))

        mod = _module(
            "vmod_wsok",
            [
                ModuleStep(
                    text="verify ok",
                    action="test_passing_verify",
                    action_args={},
                ),
            ],
        )
        buf = io.StringIO()
        console = Console(file=buf, no_color=True, markup=True, width=200)
        await run_module(
            mod,
            DryRunTransport(),
            dry_run=True,
            console=console,
            on_step_complete=_on_step_complete,
        )
        assert ("test_passing_verify", True) in events


# ── 4. Old state.json without `verified` loads (migration seam, PB-004) ──


class TestStateMigrationSeam:
    def test_old_state_without_verified_loads_and_defaults_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OLD state.json whose completed_modules have NO ``verified`` field
        must load cleanly (the migration seam / Pydantic default) and default
        verified=True — the learner's history is never silently reset."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        from xrpl_lab.state import load_state

        # A v2.0.0-shaped state.json: completed_modules entries have NO
        # `verified` key at all.
        old_payload = {
            "version": "2.0.0",
            "network": "testnet",
            "wallet_address": "rOLD",
            "completed_modules": [
                {
                    "module_id": "legacy_mod",
                    "completed_at": 1700000000.0,
                    "txids": ["LEGACYTX"],
                    "report_path": "legacy.md",
                }
            ],
            "tx_index": [],
            "created_at": 1700000000.0,
            "updated_at": 1700000000.0,
        }
        (tmp_path / "state.json").write_text(
            json.dumps(old_payload), encoding="utf-8"
        )

        state = load_state()
        # History preserved (NOT reset to fresh).
        assert state.wallet_address == "rOLD"
        assert state.is_module_completed("legacy_mod")
        cm = next(
            m for m in state.completed_modules if m.module_id == "legacy_mod"
        )
        # Additive field defaults True for back-compat.
        assert cm.verified is True

    def test_migrate_is_called_and_is_identity_safe(self) -> None:
        """PB-004: the migration seam function exists and, given already-current
        data, returns it unchanged (identity today, but the seam is present so
        future additive fields upgrade in place instead of failing validation)."""
        from xrpl_lab.state import _migrate

        data = {
            "version": "2.2.0",
            "network": "testnet",
            "completed_modules": [],
            "tx_index": [],
        }
        out = _migrate(dict(data))
        # Must still validate as a LabState afterwards.
        LabState.model_validate(out)


# ── 5. PC-004: verify messages carry an actionable fix-hint ──────────


class TestVerifyMessagesHaveHints:
    def test_missing_marker_message_has_hint(self) -> None:
        ok, msg = verify_proof_pack({"not": "a pack"})
        assert ok is False
        # Actionable: tells the user they may have pasted a certificate.
        assert "cert-verify" in msg or "certificate" in msg.lower()

    def test_hash_mismatch_message_has_regenerate_hint(self) -> None:
        state = LabState(network="testnet", wallet_address="rTEST")
        state.complete_module("m", txids=["TX"], verified=True)
        pack = generate_proof_pack(state)
        # Tamper AFTER hashing so the hash no longer matches.
        pack["address"] = "rTAMPERED"
        ok, msg = verify_proof_pack(pack)
        assert ok is False
        assert "regenerate" in msg.lower() or "proof-pack" in msg.lower()

    def test_certificate_missing_marker_message_has_hint(self) -> None:
        from xrpl_lab.reporting import verify_certificate

        ok, msg = verify_certificate({"not": "a cert"})
        assert ok is False
        assert "proof" in msg.lower() or "cert" in msg.lower()


# ── CompletedModule model direct coverage ────────────────────────────


class TestCompletedModuleModel:
    def test_verified_defaults_true(self) -> None:
        cm = CompletedModule(module_id="m", completed_at=1.0)
        assert cm.verified is True

    def test_verified_can_be_set_false(self) -> None:
        cm = CompletedModule(module_id="m", completed_at=1.0, verified=False)
        assert cm.verified is False

    def test_complete_module_accepts_verified(self) -> None:
        state = LabState()
        state.complete_module("m", txids=["T"], verified=False)
        assert state.completed_modules[0].verified is False


# ── _record_verification helper direct coverage ──────────────────────


class TestRecordVerificationHelper:
    def test_appends_verification_entry(self) -> None:
        ctx: dict = {}
        _record_verification(ctx, "act", passed=True, failures=[])
        assert ctx["verifications"] == [
            {"action": "act", "passed": True, "failures": []}
        ]

    def test_appends_failing_entry(self) -> None:
        ctx: dict = {"verifications": []}
        _record_verification(ctx, "act", passed=False, failures=["boom"])
        assert ctx["verifications"][-1]["passed"] is False
        assert ctx["verifications"][-1]["failures"] == ["boom"]
