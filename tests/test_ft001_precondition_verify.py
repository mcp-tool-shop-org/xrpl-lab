"""FT-001 LOAD-BEARING: an assertion verify step that COULD NOT RUN must be
honest, not invisible.

Stage C ("verified flag + honest pack") wired every ``handle_verify_*`` handler
to record its REAL pass/fail verdict into ``context["verifications"]`` so a
FAILED on-ledger check flips the module ``verified=False`` and folds into the
proof pack's hashed ``all_verified``. But a hole remained: many assertion
handlers short-circuit on a MISSING PREREQUISITE::

    if not txid:
        console.print("[red]No transaction to verify yet.")
        return context          # <-- records NOTHING

A verify step that could not run — because a PRIOR step never produced its
output (txid / channel_id / wallet / offer / amm_info / nft_id) — was therefore
invisible: the module still completed with ``verified=True`` and the pack's
``all_verified`` stayed vacuously True. That is the exact dishonesty the honest
pack was built to prevent, entering through the "skipped" door instead of the
"failed" door.

FT-001 closes that door: every ASSERTION verify handler records
``passed=False`` on its missing-prerequisite guard BEFORE the early return, so a
step that could not verify is an honest FAILED verification.

SCOPE — the observation/informational handlers are intentionally EXCLUDED and
covered here by an explicit exclusion test:
  * ``verify_reserve_change`` / ``verify_position_delta`` — BC-004 comparison
    handlers; they RAISE on a missing snapshot (never a silent ``return``) and
    record ``passed=True`` by design (they teach observation, not assertion).
  * ``verify_nft_offer`` — an informational reader that records ``passed=True``
    ("never fabricate a failure verdict"); the trade's real assertion lives in
    ``verify_nft_trade``.

These tests are written FIRST and go RED before the fix (the guards currently
record nothing, so ``context["verifications"]`` is empty and the ``[-1]`` index
raises / the verdict is absent), then GREEN after.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from xrpl_lab import handlers
from xrpl_lab.modules import ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport


def _console() -> Console:
    return Console(file=io.StringIO(), no_color=True, markup=True, width=200)


def _step(**action_args) -> ModuleStep:
    return ModuleStep(text="verify", action="verify", action_args=dict(action_args))


async def _run(handler, *, state: LabState, context: dict) -> dict:
    """Invoke a handler through the missing-prerequisite guard path."""
    return await handler(
        _step(), state, DryRunTransport(), "", context, _console()
    )


def _last(context: dict) -> dict:
    return context["verifications"][-1]


# ── The representative sample the FT-001 brief calls out explicitly ──


class TestRepresentativeSampleRecordsFalse:
    @pytest.mark.asyncio
    async def test_verify_tx_without_txid_records_false(self) -> None:
        state = LabState(network="testnet", wallet_address="rTEST")
        ctx = await _run(
            handlers.handle_verify_tx, state=state, context={}  # no txids
        )
        assert _last(ctx)["action"] == "verify_tx"
        assert _last(ctx)["passed"] is False
        assert _last(ctx)["failures"]  # non-empty, explains the missing step

    @pytest.mark.asyncio
    async def test_verify_channel_without_channel_id_records_false(self) -> None:
        # verify_claim_signature is the assertion handler that guards on a
        # missing channel_id (verify_channel itself never early-returns — it
        # passes an empty channel_id straight to the on-ledger check).
        state = LabState(network="testnet", wallet_address="rTEST")
        ctx = await _run(
            handlers.handle_verify_claim_signature,
            state=state,
            context={},  # no channel_id / claim_signature
        )
        assert _last(ctx)["action"] == "verify_claim_signature"
        assert _last(ctx)["passed"] is False
        assert _last(ctx)["failures"]

    @pytest.mark.asyncio
    async def test_verify_trust_line_without_address_records_false(self) -> None:
        state = LabState(network="testnet", wallet_address=None)  # no wallet
        ctx = await _run(
            handlers.handle_verify_trust_line, state=state, context={}
        )
        assert _last(ctx)["action"] == "verify_trust_line"
        assert _last(ctx)["passed"] is False
        assert _last(ctx)["failures"]


# ── Full sweep: every ASSERTION verify handler's missing-prereq guard ──
#
# Each entry drives the handler into its early-return guard and asserts the
# guard now records an honest FAILED verification with the SAME action string
# the handler uses on its success path.


def _no_wallet_state() -> LabState:
    return LabState(network="testnet", wallet_address=None)


def _with_wallet_state() -> LabState:
    return LabState(network="testnet", wallet_address="rTEST")


# (handler, expected action string, state factory, starting context)
_ASSERTION_CASES = [
    (handlers.handle_verify_tx, "verify_tx", _with_wallet_state, {}),
    (handlers.handle_verify_trust_line, "verify_trust_line", _no_wallet_state, {}),
    (
        handlers.handle_verify_trust_line_removed,
        "verify_trust_line_removed",
        _no_wallet_state,
        {},
    ),
    (
        handlers.handle_verify_claim_signature,
        "verify_claim_signature",
        _with_wallet_state,
        {},
    ),
    (
        handlers.handle_verify_offer_present,
        "verify_offer_present",
        _with_wallet_state,
        {},
    ),
    (
        handlers.handle_verify_offer_absent,
        "verify_offer_absent",
        _with_wallet_state,
        {},
    ),
    (handlers.handle_verify_lp_received, "verify_lp_received", _with_wallet_state, {}),
    (handlers.handle_verify_withdrawal, "verify_withdrawal", _with_wallet_state, {}),
    (
        handlers.handle_verify_module_offers,
        "verify_module_offers",
        _with_wallet_state,
        {},
    ),
    (handlers.handle_verify_nft, "verify_nft", _no_wallet_state, {}),
    (handlers.handle_verify_nft_burned, "verify_nft_burned", _no_wallet_state, {}),
    (handlers.handle_verify_escrow, "verify_escrow", _no_wallet_state, {}),
    (
        handlers.handle_verify_escrow_finished,
        "verify_escrow_finished",
        _no_wallet_state,
        {},
    ),
    (handlers.handle_verify_did, "verify_did", _no_wallet_state, {}),
    (handlers.handle_verify_did_deleted, "verify_did_deleted", _no_wallet_state, {}),
    (handlers.handle_verify_mpt_balance, "verify_mpt_balance", _with_wallet_state, {}),
    (handlers.handle_verify_mpt_issuance, "verify_mpt_issuance", _no_wallet_state, {}),
    (handlers.handle_verify_clawback, "verify_clawback", _no_wallet_state, {}),
    (handlers.handle_verify_nft_trade, "verify_nft_trade", _with_wallet_state, {}),
    (
        handlers.handle_verify_nft_modified,
        "verify_nft_modified",
        _no_wallet_state,
        {},
    ),
]


class TestEveryAssertionGuardRecordsFalse:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "handler,action,state_factory,ctx",
        _ASSERTION_CASES,
        ids=[c[1] for c in _ASSERTION_CASES],
    )
    async def test_missing_prerequisite_records_failed_verification(
        self, handler, action, state_factory, ctx
    ) -> None:
        result_ctx = await _run(handler, state=state_factory(), context=dict(ctx))
        entry = _last(result_ctx)
        assert entry["action"] == action, (
            f"{handler.__name__} recorded action {entry['action']!r}, "
            f"expected {action!r} (must match its success-path action string)"
        )
        assert entry["passed"] is False, (
            f"{handler.__name__} did NOT record a FAILED verification on its "
            "missing-prerequisite guard — the step that could not run is invisible"
        )
        assert entry["failures"], (
            f"{handler.__name__} recorded passed=False but no failure reason"
        )


# ── Exclusions: observation / informational handlers stay passed=True ──


class TestObservationHandlersNotFalsified:
    """The comparison / informational handlers must NOT gain a False verdict.

    verify_reserve_change and verify_position_delta RAISE on a missing snapshot
    (BC-004) — they never take the silent-return door FT-001 closes. And
    verify_nft_offer is an informational reader that records passed=True by
    design. FT-001 must leave all three untouched.
    """

    @pytest.mark.asyncio
    async def test_reserve_change_raises_not_records_false(self) -> None:
        from xrpl_lab.errors import LabException

        state = _with_wallet_state()
        with pytest.raises(LabException):
            await _run(
                handlers.handle_verify_reserve_change,
                state=state,
                context={},  # no snapshots
            )

    @pytest.mark.asyncio
    async def test_position_delta_raises_not_records_false(self) -> None:
        from xrpl_lab.errors import LabException

        state = _with_wallet_state()
        with pytest.raises(LabException):
            await _run(
                handlers.handle_verify_position_delta,
                state=state,
                context={},  # no position snapshots
            )

    @pytest.mark.asyncio
    async def test_nft_offer_missing_id_is_not_a_false_verdict(self) -> None:
        # verify_nft_offer is informational: its missing-nft_id guard returns
        # without recording (it is not an assertion handler). FT-001 leaves it
        # as-is, so it must NOT record a passed=False verdict.
        state = _with_wallet_state()
        ctx = await _run(
            handlers.handle_verify_nft_offer, state=state, context={}  # no nft_id
        )
        # Either it recorded nothing (guard returns silently) or, if it recorded,
        # it is NOT a fabricated failure. FT-001's contract is: no False verdict here.
        verifications = ctx.get("verifications", [])
        assert not any(
            v["action"] == "verify_nft_offer" and v["passed"] is False
            for v in verifications
        ), "verify_nft_offer must never record a passed=False verdict (informational)"
