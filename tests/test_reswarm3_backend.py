"""Re-swarm 3 (Stage A) backend regression tests — BC-001 … BC-007.

Test-first proofs for the seven findings assigned to this agent. Each test
probes the real defect; the fix lives in handlers.py / runner.py /
curriculum.py. Only this file plus those three modules are owned here.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from xrpl_lab import handlers
from xrpl_lab.errors import LabException
from xrpl_lab.modules import ModuleStep
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> Console:
    return Console(file=io.StringIO(), width=200)


def _secret(value: str) -> _SecretValue:
    return _SecretValue(value)


# ── BC-001 ──────────────────────────────────────────────────────────────────
# After a SUCCESSFUL open_channel, the get_account_channels read-back is a
# network round-trip sitting BEFORE record_tx. If it raises, the tx is never
# recorded even though the channel is real and XRP is locked on-ledger.


@pytest.mark.asyncio
async def test_bc001_open_channel_records_tx_when_readback_raises():
    """A transient failure in the channel read-back must NOT lose the recorded tx."""

    class _ReadbackRaisesTransport(DryRunTransport):
        async def get_account_channels(self, *args, **kwargs):  # noqa: ARG002
            raise RuntimeError("transient RPC error during read-back")

    transport = _ReadbackRaisesTransport()
    state = LabState(network="dry-run", wallet_address="rSENDER")
    step = ModuleStep(
        text="open a channel",
        action="open_channel",
        action_args={"amount": "10"},
    )
    context: dict = {
        "module_id": "paychan_basics",
        "wallet_seed": _secret("sSENDER"),
        "receiver_address": "rRECEIVER",
    }

    # Must not propagate the read-back error.
    result_ctx = await handlers.handle_open_channel(
        step, state, transport, "sSENDER", context, _console()
    )

    # The on-ledger success MUST be recorded despite the read-back failure.
    assert len(state.tx_index) == 1, "successful channel open was not recorded"
    assert state.tx_index[0].success is True
    # The channel_id must be retained; empty channel_public_key is tolerated.
    assert result_ctx.get("channel_id"), "channel_id was lost after read-back failure"
    assert result_ctx.get("channel_public_key", "") == ""
    assert result_ctx.get("txids"), "txid was not appended to context"


# ── BC-003 ──────────────────────────────────────────────────────────────────
# The on_tx callback iterates ALL of context['txids'] each step, passing the
# CURRENT step's result_code for every historical txid (O(steps*txids), and
# stale result codes). Should fire once per NEW txid only.


@pytest.mark.asyncio
async def test_bc003_on_tx_fires_once_per_new_txid(tmp_path, monkeypatch):
    """on_tx must fire once per newly-added txid with that txid's own result_code.

    Uses a transport whose payments always succeed with a UNIQUE txid and a
    distinct result_code per submission, so the buggy "iterate all txids each
    step with the current step's result_code" behavior is unambiguous:
    - buggy: step1 fires [tx1], step2 fires [tx1, tx2] → tx1 re-fired, and its
      result_code is the STALE current step's code.
    - fixed: step1 fires [tx1], step2 fires [tx2] → each txid once, own code.
    """
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    from xrpl_lab import runner as runner_mod
    from xrpl_lab.modules import ModuleDef
    from xrpl_lab.transport.base import SubmitResult

    class _UniqueTxTransport(DryRunTransport):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        async def submit_payment(self, wallet_seed, destination, amount, memo=""):  # noqa: ANN001, ARG002
            self._n += 1
            return SubmitResult(
                success=True,
                txid=str(self._n).rjust(64, "0"),  # unique 64-char txid per call
                result_code=f"tesSUCCESS_{self._n}",
                fee="12",
            )

    calls: list[tuple[str, str]] = []

    def _on_tx(txid: str, result_code: str) -> None:
        calls.append((txid, result_code))

    module = ModuleDef(
        id="bc003_mod",
        title="BC003",
        time="1 min",
        level="beginner",
        requires=[],
        produces=["txid"],
        checks=[],
        steps=[
            ModuleStep(text="wallet", action="ensure_wallet", action_args={}),
            ModuleStep(
                text="pay 1", action="submit_payment",
                action_args={"destination": "rD1", "amount": "5"},
            ),
            ModuleStep(
                text="pay 2", action="submit_payment",
                action_args={"destination": "rD2", "amount": "7"},
            ),
        ],
        order=1,
        track="payments",
        summary="two payments",
        mode="dry-run",
    )

    # Patch console.input so the between-step pause doesn't read stdin.
    console = _console()
    console.input = lambda _p="": ""  # type: ignore[assignment]

    ok = await runner_mod.run_module(
        module, _UniqueTxTransport(), dry_run=True, console=console, on_tx=_on_tx,
    )
    assert ok is True

    # Exactly one call per NEW txid → 2 calls, 2 distinct txids.
    assert len(calls) == 2, (
        f"on_tx fired {len(calls)} times; expected 2 (once per NEW txid). "
        f"calls={calls}"
    )
    fired_txids = [c[0] for c in calls]
    assert len(set(fired_txids)) == 2, (
        f"on_tx fired duplicate txids (historical re-fire): {fired_txids}"
    )
    # Each txid must carry ITS OWN result_code, not a later step's stale code.
    by_txid = dict(calls)
    assert by_txid[fired_txids[0]].endswith("_1")
    assert by_txid[fired_txids[1]].endswith("_2")


# ── BC-002 ──────────────────────────────────────────────────────────────────
# Documents the ACTUAL durability contract after the comment correction: the
# runner snapshots/restores in-memory CONTEXT on a mid-step raise, but does NOT
# roll back state.tx_index. A tx recorded via state.record_tx before a raise is
# intentionally retained (ledger is source of truth; orphan records tolerated).


@pytest.mark.asyncio
async def test_bc002_durability_contract_context_rolled_back_state_retained(tmp_path, monkeypatch):
    """On a mid-step raise: context is restored; a pre-raise TxRecord is kept."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    from xrpl_lab import runner as runner_mod
    from xrpl_lab.modules import ModuleDef

    # Simulate a handler that records a REAL on-ledger tx, mutates context, then
    # raises mid-step. Patch _execute_action (what run_module dispatches to) so
    # we don't have to permanently register a throwaway action in the registry.
    async def _record_then_raise(step, state, transport, wallet_seed, context, console=None):  # noqa: ANN001, ARG001
        state.record_tx(
            txid="BC002TX", module_id=context.get("module_id", ""),
            network=state.network, success=True,
        )
        context.setdefault("txids", []).append("BC002TX")
        context["leaked_flag"] = "should_be_rolled_back"
        raise RuntimeError("boom after recording a real on-ledger tx")

    monkeypatch.setattr(runner_mod, "_execute_action", _record_then_raise)

    module = ModuleDef(
        id="bc002_mod",
        title="BC002",
        time="1 min",
        level="beginner",
        requires=[],
        produces=["txid"],
        checks=[],
        steps=[ModuleStep(text="record then raise", action="submit_payment", action_args={})],
        order=1,
        track="payments",
        summary="durability contract",
        mode="dry-run",
    )

    console = _console()
    console.input = lambda _p="": ""  # type: ignore[assignment]

    # We assert against the persisted state, so run through the real load/save
    # path. run_module loads state from disk; seed it via save_state.
    from xrpl_lab.state import ensure_workspace, load_state, save_state

    ensure_workspace()
    seed_state = load_state()
    seed_state.network = "dry-run"
    save_state(seed_state)
    txids_before = len(load_state().tx_index)

    ok = await runner_mod.run_module(
        module, DryRunTransport(), dry_run=True, console=console,
    )
    # The step raised → the module did not complete.
    assert ok is False

    # DURABILITY CONTRACT: the pre-raise TxRecord is RETAINED in persisted state
    # (ledger is source of truth; orphan records are tolerated, never discarded).
    persisted = load_state()
    assert len(persisted.tx_index) == txids_before + 1, (
        "a tx recorded before the raise must be retained in state.tx_index"
    )
    assert any(t.txid == "BC002TX" for t in persisted.tx_index)


# ── BC-004 ──────────────────────────────────────────────────────────────────
# verify_reserve_change / verify_position_delta silently `return context` on a
# missing snapshot — a mislabeled snapshot lets a verify step pass without
# verifying. Must raise (or record failure) instead.


@pytest.mark.asyncio
async def test_bc004_verify_reserve_change_raises_on_missing_snapshot():
    transport = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rW")
    step = ModuleStep(
        text="verify reserve",
        action="verify_reserve_change",
        action_args={"before": "before", "after": "after"},
    )
    context: dict = {"module_id": "reserves"}  # no snapshots present

    with pytest.raises(LabException):
        await handlers.handle_verify_reserve_change(
            step, state, transport, "s", context, _console()
        )


@pytest.mark.asyncio
async def test_bc004_verify_position_delta_raises_on_missing_snapshot():
    transport = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rW")
    step = ModuleStep(
        text="verify position",
        action="verify_position_delta",
        action_args={"before": "before", "after": "after"},
    )
    context: dict = {"module_id": "dex"}  # no position snapshots present

    with pytest.raises(LabException):
        await handlers.handle_verify_position_delta(
            step, state, transport, "s", context, _console()
        )


# ── BC-005 ──────────────────────────────────────────────────────────────────
# Numeric arg parses sit in a bare `except ValueError`, so a valid-but-
# out-of-range int (e.g. transfer_fee=999999, finish_seconds=-100) flows to the
# tx builder. Load-bearing ones must be range-validated (reject or clamp).


@pytest.mark.asyncio
async def test_bc005_mint_nft_rejects_out_of_range_transfer_fee(monkeypatch):
    """transfer_fee=999999 (> 50000) must not be forwarded to mint_nft."""
    captured: dict = {}

    async def _spy_mint_nft(transport, seed, uri, taxon, transfer_fee, transferable, mutable):  # noqa: ANN001
        captured["transfer_fee"] = transfer_fee
        from xrpl_lab.transport.base import SubmitResult

        return SubmitResult(success=True, txid="TX", result_code="tesSUCCESS", fee="12")

    monkeypatch.setattr(handlers, "mint_nft", _spy_mint_nft)

    transport = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rW")
    step = ModuleStep(
        text="mint",
        action="mint_nft",
        action_args={"uri": "ipfs://x", "transfer_fee": "999999"},
    )
    context: dict = {"module_id": "nfts", "wallet_seed": _secret("sSeed")}

    await handlers.handle_mint_nft(step, state, transport, "sSeed", context, _console())

    assert "transfer_fee" in captured, "mint_nft was never called"
    assert captured["transfer_fee"] <= 50000, (
        f"out-of-range transfer_fee forwarded to builder: {captured['transfer_fee']}"
    )


@pytest.mark.asyncio
async def test_bc005_create_escrow_rejects_negative_finish_seconds(monkeypatch):
    """finish_seconds=-100 (< 1) must not be forwarded as-is to create_escrow."""
    captured: dict = {}

    async def _spy_create_escrow(  # noqa: ANN001
        transport, seed, amount, destination, finish_after, cancel_after=None,
    ):
        captured["finish_after"] = finish_after
        from xrpl_lab.transport.base import SubmitResult

        return SubmitResult(success=True, txid="TX", result_code="tesSUCCESS", fee="12")

    monkeypatch.setattr(handlers, "create_escrow", _spy_create_escrow)

    import time as _time

    transport = DryRunTransport()
    state = LabState(network="dry-run", wallet_address="rOWNER")
    step = ModuleStep(
        text="escrow",
        action="create_escrow",
        action_args={"amount": "10", "finish_seconds": "-100"},
    )
    context: dict = {"module_id": "escrow", "wallet_seed": _secret("sSeed")}

    before = int(_time.time())
    await handlers.handle_create_escrow(step, state, transport, "sSeed", context, _console())

    assert "finish_after" in captured, "create_escrow was never called"
    # finish_after = now - RIPPLE_EPOCH + delay. With delay clamped to >= 1,
    # finish_after must be in the future (> the equivalent 'now' ripple time),
    # never in the past as -100 would make it.
    from xrpl_lab.handlers import _RIPPLE_EPOCH

    now_ripple = before - _RIPPLE_EPOCH
    assert captured["finish_after"] > now_ripple, (
        f"negative finish_seconds produced a past finish_after "
        f"({captured['finish_after']} <= {now_ripple})"
    )


# ── BC-006 ──────────────────────────────────────────────────────────────────
# handle_accept_nft_offer writes context['nft_seller_address'] but the verify
# reads 'nft_prev_owner' — the key is dead. The fix removes the dead write.


def _strip_comments(src: str) -> str:
    """Drop full-line and inline ``#`` comments so source probes ignore prose."""
    out = []
    for line in src.splitlines():
        code = line.split("#", 1)[0]
        out.append(code)
    return "\n".join(out)


def test_bc006_no_dead_nft_seller_address_write():
    """The dead nft_seller_address write must be gone from handle_accept_nft_offer."""
    import inspect

    code = _strip_comments(inspect.getsource(handlers.handle_accept_nft_offer))
    assert "nft_seller_address" not in code, (
        "dead context key 'nft_seller_address' is still assigned in "
        "handle_accept_nft_offer (verify reads 'nft_prev_owner')"
    )


# ── BC-007 ──────────────────────────────────────────────────────────────────
# curriculum.is_reachable has an unreachable `except RecursionError` around
# all_prerequisites, which is an iterative stack-walk. Drop it.


def test_bc007_is_reachable_has_no_recursionerror_handler():
    """The unreachable RecursionError handler in is_reachable must be removed."""
    import inspect

    from xrpl_lab.curriculum import CurriculumGraph

    code = _strip_comments(inspect.getsource(CurriculumGraph.is_reachable))
    assert "except RecursionError" not in code, (
        "is_reachable still has an unreachable `except RecursionError` handler; "
        "all_prerequisites is an iterative stack-walk"
    )
