"""Tests for custodial player crediting — destination tags on a pooled treasury.

Proves (all offline, dry-run transport — no live network):
  (a) asfRequireDest state: enabling it makes the dry-run reject an UNTAGGED
      payment to the pool with tecDST_TAG_NEEDED (identical to testnet), a
      TAGGED payment passes, clearing the flag reopens untagged traffic, and
      out-of-range tags are rejected locally (parity with xrpl-py's model
      ceiling).
  (b) a tagged deposit reads back with its DestinationTag / SourceTag and a
      delivered_amount, and credit_player_deposit attributes it to the right
      player via the registry and credits delivered_amount — never Amount.
  (c) the tag-is-not-authentication rule: an unregistered tag is an honest
      failed credit (hold for review), never a guessed player.
  (d) the handlers record honest verifications (FT-001) and the expect-fail
      handler names tecDST_TAG_NEEDED.
  (e) the custodial_crediting_101 module lints clean and pins its confirmed
      kb_source slug.

The mainnet-refusal coverage for the new submit_require_dest signing method is
enforced by tests/test_network_safety.py (the _MAINNET_REFUSAL_CALLS row + the
reflection completeness gate) — not duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.custodial import (
    MAX_TAG,
    credit_player_deposit,
    enable_require_dest,
    send_tagged_deposit,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.modules import parse_module
from xrpl_lab.transport.dry_run import DryRunTransport

_POOL = "rPOOLTREASURY00000000000000"
_MODULE_PATH = Path(__file__).parent.parent / "modules" / "custodial_crediting_101.md"


async def _enable_pool(t: DryRunTransport) -> None:
    res = await enable_require_dest(t, "sPOOL", wallet_address=_POOL)
    assert res.success
    assert res.result_code == "tesSUCCESS"
    assert res.txid


# ── (a) RequireDest enforcement parity ──────────────────────────────────────


@pytest.mark.asyncio
async def test_untagged_payment_to_require_dest_pool_fails_dst_tag_needed():
    t = DryRunTransport()
    await _enable_pool(t)

    res = await t.submit_payment("sPLAYER", _POOL, "10")
    assert not res.success
    assert res.result_code == "tecDST_TAG_NEEDED"
    assert not res.txid


@pytest.mark.asyncio
async def test_tagged_payment_to_require_dest_pool_succeeds():
    t = DryRunTransport()
    await _enable_pool(t)

    res = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "25", destination_tag=1001, source_tag=9001
    )
    assert res.success
    assert res.result_code == "tesSUCCESS"
    assert res.txid


@pytest.mark.asyncio
async def test_untagged_payment_to_open_account_still_succeeds():
    # The flag is opt-in per account: a pool that never set asfRequireDest
    # accepts untagged payments (and eats the unattributable-deposit risk —
    # the operational lesson, not a ledger rule).
    t = DryRunTransport()
    res = await t.submit_payment("sPLAYER", _POOL, "10")
    assert res.success


@pytest.mark.asyncio
async def test_clearing_require_dest_reopens_untagged_payments():
    t = DryRunTransport()
    await _enable_pool(t)
    # The named compensator: AccountSet ClearFlag asfRequireDest.
    res = await enable_require_dest(t, "sPOOL", wallet_address=_POOL, enable=False)
    assert res.success

    res = await t.submit_payment("sPLAYER", _POOL, "10")
    assert res.success


@pytest.mark.asyncio
async def test_out_of_range_tags_are_rejected_locally():
    # Tags are 32-bit unsigned. xrpl-py's Payment model refuses to construct
    # an out-of-range tag (testnet surfaces local_error); the action layer
    # rejects the same set with a teaching message BEFORE either transport.
    t = DryRunTransport()
    for bad in (MAX_TAG + 1, -1):
        res = await send_tagged_deposit(
            t, "sPLAYER", _POOL, "10", destination_tag=bad
        )
        assert not res.success
        assert res.result_code == "local_error"
        assert "32-bit" in res.error
    # SourceTag gets the identical ceiling.
    res = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "10", destination_tag=1001, source_tag=MAX_TAG + 1
    )
    assert not res.success
    assert res.result_code == "local_error"


@pytest.mark.asyncio
async def test_transport_backstop_rejects_out_of_range_tag():
    # A direct transport caller (skipping the action layer) hits the same
    # ceiling inside the dry-run — the backstop that keeps dry-run/testnet
    # parity even without the action preflight.
    t = DryRunTransport()
    res = await t.submit_payment(
        "sPLAYER", _POOL, "10", destination_tag=MAX_TAG + 1
    )
    assert not res.success
    assert res.result_code == "local_error"


@pytest.mark.asyncio
async def test_boundary_tags_are_valid():
    # 0 and 2^32-1 are both legal tag values — the range check must not
    # off-by-one either edge. (Fresh transport per tag: the dry-run debits
    # the sender's tracked balance on each send, so back-to-back sends from
    # one unfunded sender would trip the reserve floor, not the tag check.)
    for tag in (0, MAX_TAG):
        t = DryRunTransport()
        res = await send_tagged_deposit(
            t, "sPLAYER", _POOL, "1", destination_tag=tag
        )
        assert res.success, f"tag {tag} should be valid"
        tx = await t.fetch_tx(res.txid)
        assert tx.destination_tag == tag


# ── (b) read-back + attribution + delivered_amount credit ──────────────────


@pytest.mark.asyncio
async def test_tagged_deposit_reads_back_tags_and_delivered_amount():
    t = DryRunTransport()
    await _enable_pool(t)
    sent = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "25", destination_tag=1001, source_tag=9001
    )
    assert sent.success

    tx = await t.fetch_tx(sent.txid)
    assert tx.validated is True
    assert tx.result_code == "tesSUCCESS"
    assert tx.destination_tag == 1001
    assert tx.source_tag == 9001
    # 25 XRP = 25_000_000 drops; delivered_amount is the metadata figure.
    assert tx.delivered_amount == "25000000"
    assert tx.destination == _POOL


@pytest.mark.asyncio
async def test_credit_player_deposit_attributes_and_credits():
    t = DryRunTransport()
    await _enable_pool(t)
    sent = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "25", destination_tag=1001, source_tag=9001
    )

    result = await credit_player_deposit(
        t, sent.txid, {1001: "arya", 1002: "bran"}, expected_drops="25000000"
    )
    assert result.passed, result.failures
    assert result.player == "arya"
    assert result.tag == 1001
    assert result.credited_drops == "25000000"
    # The credit MUST come from delivered_amount (and say so), with the
    # Amount field kept only for the contrast.
    assert any("delivered_amount" in c for c in result.checks)
    # SourceTag surfaces as the refund-routing hint.
    assert any("SourceTag 9001" in c for c in result.checks)


@pytest.mark.asyncio
async def test_credit_expected_drops_mismatch_is_honest_failure():
    t = DryRunTransport()
    await _enable_pool(t)
    sent = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "25", destination_tag=1001
    )
    bad = await credit_player_deposit(
        t, sent.txid, {1001: "arya"}, expected_drops="999"
    )
    assert not bad.passed
    assert any("mismatch" in f for f in bad.failures)


@pytest.mark.asyncio
async def test_credit_unknown_txid_fails_before_any_attribution():
    t = DryRunTransport()
    result = await credit_player_deposit(t, "NOTATRANSACTION", {1001: "arya"})
    assert not result.passed
    assert result.player == ""


# ── (c) a tag is a routing hint, NOT authentication ────────────────────────


@pytest.mark.asyncio
async def test_credit_unregistered_tag_is_held_never_guessed():
    # Anyone can send any tag — the deposit's value is real, the claimed
    # player is not. An unknown tag must be an honest failed credit that says
    # so, never a guess.
    t = DryRunTransport()
    await _enable_pool(t)
    sent = await send_tagged_deposit(
        t, "sPLAYER", _POOL, "25", destination_tag=4242
    )

    result = await credit_player_deposit(t, sent.txid, {1001: "arya"})
    assert not result.passed
    assert result.player == ""
    assert result.tag == 4242
    assert any("not authentication" in f.lower() for f in result.failures)


@pytest.mark.asyncio
async def test_credit_untagged_deposit_is_unattributable():
    # An untagged deposit that LANDED (pool without RequireDest) cannot be
    # attributed — the failure names the missing tag and points at the flag.
    t = DryRunTransport()
    sent = await t.submit_payment("sPLAYER", _POOL, "10")  # open pool, no tag
    assert sent.success

    result = await credit_player_deposit(t, sent.txid, {1001: "arya"})
    assert not result.passed
    assert result.tag is None
    assert any("No DestinationTag" in f for f in result.failures)
    assert any("asfRequireDest" in f for f in result.failures)


# ── (d) handlers: honest verifications + the expect-fail wall ───────────────


@pytest.mark.asyncio
async def test_handlers_full_flow_records_verification_and_hits_the_wall():
    """End-to-end through the handlers: enable → player → tag → deposit →
    credit (verification passed=True) → untagged wall (tecDST_TAG_NEEDED)."""
    from rich.console import Console

    from xrpl_lab.handlers import (
        handle_assign_player_tag,
        handle_create_player_wallet,
        handle_credit_player_deposit,
        handle_enable_require_dest,
        handle_send_tagged_deposit,
        handle_send_untagged_deposit_expect_fail,
    )
    from xrpl_lab.modules import ModuleStep
    from xrpl_lab.state import LabState

    console = Console(quiet=True)
    t = DryRunTransport()
    state = LabState(network="dry-run")
    state.wallet_address = _POOL
    ctx: dict = {"module_id": "custodial_crediting_101"}

    step = ModuleStep(text="", action="enable_require_dest", action_args={})
    ctx = await handle_enable_require_dest(step, state, t, "sPOOL", ctx, console)
    assert ctx.get("require_dest_enabled") is True

    step = ModuleStep(text="", action="create_player_wallet", action_args={})
    ctx = await handle_create_player_wallet(step, state, t, "sPOOL", ctx, console)
    assert ctx.get("player_seed") and ctx.get("player_address")

    step = ModuleStep(
        text="", action="assign_player_tag",
        action_args={"tag": "1001", "player": "arya"},
    )
    ctx = await handle_assign_player_tag(step, state, t, "sPOOL", ctx, console)
    assert ctx["tag_registry"] == {1001: "arya"}
    assert ctx["player_tag"] == 1001

    step = ModuleStep(
        text="", action="send_tagged_deposit",
        action_args={"amount": "25", "source_tag": "9001"},
    )
    ctx = await handle_send_tagged_deposit(step, state, t, "sPOOL", ctx, console)
    assert ctx.get("deposit_txid")
    assert ctx.get("deposit_tag") == 1001

    step = ModuleStep(
        text="", action="credit_player_deposit", action_args={"expected": "25"},
    )
    ctx = await handle_credit_player_deposit(step, state, t, "sPOOL", ctx, console)
    recs = ctx.get("verifications", [])
    assert recs and recs[-1]["action"] == "credit_player_deposit"
    assert recs[-1]["passed"] is True
    assert recs[-1]["failures"] == []
    assert ctx["last_player_credit"].player == "arya"

    step = ModuleStep(
        text="", action="send_untagged_deposit_expect_fail",
        action_args={"amount": "10"},
    )
    ctx = await handle_send_untagged_deposit_expect_fail(
        step, state, t, "sPOOL", ctx, console
    )
    fails = ctx.get("failed_txids", [])
    assert fails and fails[-1]["result_code"] == "tecDST_TAG_NEEDED"


@pytest.mark.asyncio
async def test_handle_credit_without_deposit_records_honest_failure():
    """FT-001: the verify step's prerequisite never ran → an honest FAILED
    verification, not an invisible skip."""
    from rich.console import Console

    from xrpl_lab.handlers import handle_credit_player_deposit
    from xrpl_lab.modules import ModuleStep
    from xrpl_lab.state import LabState

    console = Console(quiet=True)
    t = DryRunTransport()
    state = LabState(network="dry-run")
    state.wallet_address = _POOL
    ctx: dict = {"module_id": "custodial_crediting_101"}

    step = ModuleStep(text="", action="credit_player_deposit", action_args={})
    ctx = await handle_credit_player_deposit(step, state, t, "sPOOL", ctx, console)
    recs = ctx.get("verifications", [])
    assert recs and recs[-1]["action"] == "credit_player_deposit"
    assert recs[-1]["passed"] is False
    assert any("deposit_txid missing" in f for f in recs[-1]["failures"])


# ── (e) the module lints clean + pins its confirmed kb_source ───────────────


def test_custodial_module_lints_clean():
    issues = lint_module_file(_MODULE_PATH)
    errors = [i for i in issues if i.level == "error"]
    assert not errors, f"custodial_crediting_101 lint errors: {errors}"


def test_custodial_module_frontmatter_pins_kb_source_and_prereq():
    mod = parse_module(_MODULE_PATH.read_text(encoding="utf-8"))
    assert mod.id == "custodial_crediting_101"
    assert mod.track == "payments"
    # Confirmed against the xrpl-knowledge KB capabilities table
    # ("Destination tags for custodial player sub-accounts").
    assert mod.kb_source == "destination-tag-subaccounts"
    # The module COMPOSES the delivered_amount discipline — the prereq is
    # load-bearing, not decorative.
    assert "delivered_amount_101" in mod.requires
