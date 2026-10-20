"""Payment-channel, DEX offer, reserve-snapshot and audit handlers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import xrpl_lab.handlers as handlers
from xrpl_lab.errors import LabException
from xrpl_lab.transport.base import AccountSnapshot, ChannelInfo, FundResult, OfferInfo

from ._h import EXPLORER, TXID, Env, bad, checks_result, ok, secret, verdict

ISSUER = "rISSUERADDRESS123"


# -- create_channel_receiver --


@pytest.mark.asyncio
async def test_create_channel_receiver_makes_and_funds_a_receiver(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="x"))
    env.stub("await_validated_balance", 10)
    out = await env.run("handle_create_channel_receiver")
    assert out["receiver_address"].startswith("r")
    assert out["receiver_seed"].get().startswith("s")
    assert f"Receiver wallet: {out['receiver_address']}" in env.out
    assert "Receiver funded! Balance: 10 XRP" in env.out
    assert "verifications" not in out


@pytest.mark.asyncio
async def test_create_channel_receiver_unfunded_is_a_failed_step(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=False, address="x", message="down"))
    out = await env.run("handle_create_channel_receiver")
    assert "Receiver funding: down" in env.out
    assert verdict(out, "create_channel_receiver")["passed"] is False


# -- open_channel --


@pytest.mark.asyncio
async def test_open_channel_needs_sender_and_receiver(env: Env) -> None:
    calls = env.stub("open_channel", ok(channel_id="CH"))
    await env.run("handle_open_channel", receiver_address="")
    assert "Missing sender wallet or receiver" in env.out
    env.ctx.pop("wallet_seed")
    await env.run("handle_open_channel", receiver_address="rRECV")
    assert calls == []
    assert env.records() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected", "note"),
    [
        ("abc", 86400, "Invalid settle_delay, using default (86400)"),
        ("-5", 0, "settle_delay -5 is invalid"),
        ("3600", 3600, ""),
    ],
)
async def test_open_channel_settle_delay_is_validated(
    env: Env, raw: str, expected: int, note: str,
) -> None:
    calls = env.stub("open_channel", ok(channel_id="CH"))
    await env.run("handle_open_channel", {"settle_delay": raw}, receiver_address="rRECV")
    assert calls[0][0][4] == expected
    if note:
        assert note in env.out
    else:
        assert "Invalid" not in env.out


@pytest.mark.asyncio
async def test_open_channel_success_captures_channel_and_public_key(env: Env) -> None:
    env.stub("open_channel", ok(channel_id="CH1"))
    env.on_transport("get_account_channels", [
        ChannelInfo(channel_id="OTHER", public_key="PKX"),
        ChannelInfo(channel_id="CH1", public_key="PK1"),
    ])
    out = await env.run("handle_open_channel", {"amount": "4"}, receiver_address="rRECV")
    assert out["channel_id"] == "CH1"
    assert out["channel_public_key"] == "PK1"
    assert "Channel ID: CH1" in env.out and EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert env.last().success is True


@pytest.mark.asyncio
async def test_open_channel_unmatched_channel_leaves_an_empty_key(env: Env) -> None:
    env.stub("open_channel", ok(channel_id="CH1"))
    env.on_transport("get_account_channels", [ChannelInfo(channel_id="OTHER", public_key="PKX")])
    out = await env.run("handle_open_channel", receiver_address="rRECV")
    assert out["channel_public_key"] == ""
    assert out["channel_id"] == "CH1"


@pytest.mark.asyncio
async def test_open_channel_still_records_the_tx_when_the_key_readback_raises(env: Env) -> None:
    env.stub("open_channel", ok(channel_id="CH1"))
    env.on_transport("get_account_channels", RuntimeError("rpc blip"))
    out = await env.run("handle_open_channel", receiver_address="rRECV")
    assert out["channel_public_key"] == ""
    assert "could not read back the channel's signing key" in env.out
    # The channel is open on-ledger: the tx must still be recorded.
    assert env.last().success is True and env.last().txid == TXID
    assert out["txids"] == [TXID]


@pytest.mark.asyncio
async def test_open_channel_failure_is_recorded_and_sets_no_channel(env: Env) -> None:
    env.stub("open_channel", bad(error="no funds"))
    out = await env.run("handle_open_channel", receiver_address="rRECV")
    assert "Channel open failed: no funds" in env.out
    assert "channel_id" not in out
    assert env.last().success is False


# -- fund / sign / verify / redeem --


@pytest.mark.asyncio
async def test_fund_channel_without_a_channel(env: Env) -> None:
    calls = env.stub("fund_channel", ok())
    await env.run("handle_fund_channel")
    assert calls == [] and "No channel to fund" in env.out


@pytest.mark.asyncio
async def test_sign_claim_without_a_channel(env: Env) -> None:
    calls = env.stub("sign_claim", "SIG")
    out = await env.run("handle_sign_claim")
    assert calls == [] and "No channel" in env.out
    assert "claim_signature" not in out


@pytest.mark.asyncio
async def test_sign_claim_stores_signature_and_amount(env: Env) -> None:
    calls = env.stub("sign_claim", "AB" * 40)
    out = await env.run("handle_sign_claim", {"amount": "6"}, channel_id="CH1")
    assert calls[0][0][2:] == ("CH1", "6")
    assert out["claim_signature"] == "AB" * 40
    assert out["claim_amount"] == "6"
    assert "no transaction, no fee" in env.out
    assert ("AB" * 40)[:40] in env.out and ("AB" * 40)[:41] not in env.out


@pytest.mark.asyncio
async def test_verify_claim_signature_without_a_claim_fails(env: Env) -> None:
    calls = env.stub("check_claim", True)
    out = await env.run("handle_verify_claim_signature")
    assert calls == []
    assert "No signed claim to verify" in env.out
    assert verdict(out, "verify_claim_signature")["passed"] is False


@pytest.mark.asyncio
async def test_verify_claim_signature_follows_the_checker(env: Env) -> None:
    # The checker is stubbed: this pins how the handler reports its verdict.
    calls = env.stub("check_claim", True)
    out = await env.run(
        "handle_verify_claim_signature",
        channel_id="CH1", claim_signature="SIG", claim_amount="3", channel_public_key="PK",
    )
    assert calls[0][0][1:] == ("CH1", "3", "PK", "SIG")
    assert "Receiver verified the claim for 3 XRP" in env.out
    assert out["last_claim_verify"] is True
    assert verdict(out, "verify_claim_signature") == {
        "action": "verify_claim_signature", "passed": True, "failures": [],
    }


@pytest.mark.asyncio
async def test_verify_claim_signature_rejected_claim_flags_the_module(env: Env) -> None:
    env.stub("check_claim", False)
    out = await env.run(
        "handle_verify_claim_signature", channel_id="CH1", claim_signature="SIG",
    )
    assert "Claim signature did NOT verify" in env.out
    assert out["last_claim_verify"] is False
    v = verdict(out, "verify_claim_signature")
    assert v["passed"] is False and v["failures"] == ["Claim signature did not verify."]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["channel_id", "receiver_seed", "claim_amount"])
async def test_redeem_claim_needs_channel_receiver_and_claim(env: Env, missing: str) -> None:
    calls = env.stub("redeem_claim", ok())
    full = {
        "channel_id": "CH1", "receiver_seed": secret("sREC"), "claim_amount": "3",
        "claim_signature": "SIG", "channel_public_key": "PK",
    }
    full.pop(missing)
    await env.run("handle_redeem_claim", **full)
    assert calls == []
    assert "Missing channel, receiver, or claim" in env.out
    assert env.records() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("close", "expected"), [("yes", True), ("false", False), (True, True)])
async def test_redeem_claim_close_flag_and_plain_string_seed(env: Env, close, expected) -> None:
    calls = env.stub("redeem_claim", ok())
    await env.run(
        "handle_redeem_claim", {"close": close},
        channel_id="CH1", receiver_seed="sPLAIN", claim_amount="3",
        claim_signature="SIG", channel_public_key="PK",
    )
    (args, kwargs), = calls
    assert args[1:4] == ("sPLAIN", "CH1", "3")
    assert kwargs == {"signature": "SIG", "public_key": "PK", "close": expected}


@pytest.mark.asyncio
async def test_verify_channel_reports_the_result(env: Env) -> None:
    res = checks_result(passed=False, checks=["channel exists"], failures=["amount differs"])
    calls = env.stub("verify_channel", res)
    out = await env.run(
        "handle_verify_channel", {"expect_amount": "10", "expect_balance": "3"},
        channel_id="CH1",
    )
    assert calls[0][1] == {
        "channel_id": "CH1", "expect_amount_xrp": "10", "expect_balance_xrp": "3",
    }
    assert "channel exists" in env.out and "amount differs" in env.out
    assert out["last_channel_verify"] is res
    assert verdict(out, "verify_channel")["failures"] == ["amount differs"]
    assert verdict(out, "verify_channel")["passed"] is False


# -- currency / leg helpers --


def test_canon_currency_decodes_hex_codes() -> None:
    hexed = b"HYGIENE".hex().upper().ljust(40, "0")
    assert handlers._canon_currency(hexed) == "HYGIENE"
    assert handlers._canon_currency(" lab ") == "LAB"
    assert handlers._canon_currency(None) == ""


def test_canon_currency_keeps_undecodable_forty_char_codes() -> None:
    assert handlers._canon_currency("z" * 40) == "Z" * 40  # not hex
    assert handlers._canon_currency("00" * 20) == "0" * 40  # decodes to nothing
    assert handlers._canon_currency("FF" * 20) == "F" * 40  # not ASCII


def test_offer_leg_currency() -> None:
    assert handlers._offer_leg_currency("10/LAB/rI") == "LAB"
    assert handlers._offer_leg_currency("1000000") == "XRP"
    assert handlers._offer_leg_currency("") == "XRP"


@pytest.mark.parametrize(
    ("leg", "currency", "value", "expected"),
    [
        ("10/LAB/rI", "LAB", "10", True),
        ("10.0/LAB/rI", "LAB", "10", True),
        ("11/LAB/rI", "LAB", "10", False),
        ("10/USD/rI", "LAB", "10", False),
        ("10", "LAB", "10", False),  # no currency part
        ("x/LAB/rI", "LAB", "10", False),  # unparsable amount
        ("10/LAB/rI", "LAB", "ten", False),  # unparsable wanted value
        ("5", "XRP", "5", True),  # dry-run style raw XRP
        ("5000000", "XRP", "5", True),  # drops
        ("6", "XRP", "5", False),
        ("5/XRP/r", "XRP", "5", False),
        ("abc", "XRP", "5", False),
    ],
)
def test_offer_leg_matches(leg: str, currency: str, value: str, expected: bool) -> None:
    assert handlers._offer_leg_matches(leg, currency, value) is expected


# -- _resolve_created_offer_sequence --


async def _resolve(env: Env, result=None, **kw) -> int | None:
    base = dict(
        taker_pays_currency="LAB", taker_pays_value="50",
        taker_gets_currency="XRP", taker_gets_value="10", console=env.console,
    )
    base.update(kw)
    return await handlers._resolve_created_offer_sequence(
        env.transport, "rLEARNER", result or ok(), **base,
    )


@pytest.mark.asyncio
async def test_resolve_offer_sequence_prefers_the_transport_surfaced_one(env: Env) -> None:
    calls = env.on_transport("get_account_offers", [])
    assert await _resolve(env, ok(offer_sequence=42)) == 42
    assert calls == []  # never read back


@pytest.mark.asyncio
async def test_resolve_offer_sequence_with_no_resting_offers(env: Env) -> None:
    env.on_transport("get_account_offers", [])
    assert await _resolve(env) is None


@pytest.mark.asyncio
async def test_resolve_offer_sequence_picks_the_newest_exact_match(env: Env) -> None:
    env.on_transport("get_account_offers", [
        OfferInfo(sequence=9, taker_pays="50/LAB/rI", taker_gets="10"),
        OfferInfo(sequence=3, taker_pays="50/LAB/rI", taker_gets="10"),
        OfferInfo(sequence=20, taker_pays="1/LAB/rI", taker_gets="1"),  # stale, other amounts
    ])
    assert await _resolve(env) == 9


@pytest.mark.asyncio
async def test_resolve_offer_sequence_falls_back_to_direction(env: Env) -> None:
    env.on_transport("get_account_offers", [
        OfferInfo(sequence=4, taker_pays="30/LAB/rI", taker_gets="6"),  # partially crossed
        OfferInfo(sequence=8, taker_pays="1/USD/rI", taker_gets="1"),
    ])
    assert await _resolve(env) == 4
    assert "matched by direction" in env.out


@pytest.mark.asyncio
async def test_resolve_offer_sequence_captures_nothing_when_it_fully_crossed(env: Env) -> None:
    env.on_transport("get_account_offers", [
        OfferInfo(sequence=8, taker_pays="1/USD/rI", taker_gets="1"),
    ])
    assert await _resolve(env) is None
    assert "sequence not captured" in env.out


# -- create_offer / verify / cancel --


@pytest.mark.asyncio
async def test_create_offer_captures_sequence_and_blanks_xrp_issuer(env: Env) -> None:
    calls = env.stub("create_offer", ok(offer_sequence=12))
    out = await env.run(
        "handle_create_offer",
        {"pays_currency": "LAB", "pays_value": "5", "gets_currency": "XRP", "gets_value": "2"},
        issuer_address=ISSUER,
    )
    args = calls[0][0]
    assert args[2:] == ("LAB", "5", ISSUER, "XRP", "2", "")
    assert out["offer_sequence"] == 12
    assert "Offer sequence: 12" in env.out
    assert "pay 2 XRP to get 5 LAB" in env.out


@pytest.mark.asyncio
async def test_create_offer_that_crossed_leaves_no_sequence(env: Env) -> None:
    env.stub("create_offer", ok())
    env.on_transport("get_account_offers", [])
    out = await env.run("handle_create_offer", issuer_address=ISSUER)
    assert "offer_sequence" not in out
    assert "Offer sequence" not in env.out


@pytest.mark.asyncio
async def test_verify_offer_present_without_a_sequence_fails(env: Env) -> None:
    calls = env.stub("verify_offer_present", checks_result())
    out = await env.run("handle_verify_offer_present")
    assert calls == []
    assert "No offer sequence in context" in env.out
    assert verdict(out, "verify_offer_present")["passed"] is False


@pytest.mark.asyncio
async def test_verify_offer_present_found(env: Env) -> None:
    calls = env.stub("verify_offer_present", checks_result(found=True, checks=["offer 7 rests"]))
    out = await env.run("handle_verify_offer_present", offer_sequence=7)
    assert calls[0][0][1:] == ("rLEARNER", 7)
    assert "offer 7 rests" in env.out
    assert verdict(out, "verify_offer_present")["passed"] is True


@pytest.mark.asyncio
async def test_verify_offer_present_missing(env: Env) -> None:
    env.stub("verify_offer_present", checks_result(found=False, failures=["offer 7 not found"]))
    out = await env.run("handle_verify_offer_present", offer_sequence=7)
    assert "offer 7 not found" in env.out
    v = verdict(out, "verify_offer_present")
    assert v["passed"] is False and v["failures"] == ["offer 7 not found"]


@pytest.mark.asyncio
async def test_verify_offer_present_zero_is_a_real_sequence(env: Env) -> None:
    calls = env.stub("verify_offer_present", checks_result(found=True))
    await env.run("handle_verify_offer_present", offer_sequence=0)
    assert calls[0][0][2] == 0


@pytest.mark.asyncio
async def test_cancel_offer_without_a_sequence(env: Env) -> None:
    calls = env.stub("cancel_offer", ok())
    await env.run("handle_cancel_offer")
    assert calls == [] and "No offer sequence in context" in env.out


@pytest.mark.asyncio
async def test_verify_offer_absent_without_a_sequence_fails(env: Env) -> None:
    out = await env.run("handle_verify_offer_absent")
    assert verdict(out, "verify_offer_absent")["passed"] is False


@pytest.mark.asyncio
async def test_verify_offer_absent_pass_and_fail(env: Env) -> None:
    env.stub("verify_offer_absent", checks_result(passed=True, checks=["offer gone"]))
    out = await env.run("handle_verify_offer_absent", offer_sequence=7)
    assert "offer gone" in env.out
    assert verdict(out, "verify_offer_absent")["passed"] is True

    env2 = Env(env.tmp_path, env.mp)
    env2.stub("verify_offer_absent", checks_result(passed=False, failures=["offer still there"]))
    out2 = await env2.run("handle_verify_offer_absent", offer_sequence=7)
    assert "offer still there" in env2.out
    assert verdict(out2, "verify_offer_absent")["failures"] == ["offer still there"]


# -- snapshots and reserve change --


@pytest.mark.asyncio
async def test_snapshot_account_without_a_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_snapshot_account", {"label": "before"})
    assert "No wallet address found" in env.out
    assert "snapshot_before" not in out


@pytest.mark.asyncio
async def test_snapshot_account_stores_under_its_label(env: Env) -> None:
    env.on_transport(
        "get_account_info",
        AccountSnapshot(address="rLEARNER0123456789", balance_drops="25000000",
                        owner_count=3, sequence=9),
    )
    out = await env.run("handle_snapshot_account", {"label": "mid"})
    snap = out["snapshot_mid"]
    assert snap.owner_count == 3
    assert "Balance: 25.000000 XRP (25000000 drops)" in env.out
    assert "Owner count: 3" in env.out and "Sequence: 9" in env.out


def _snap(balance: int, owners: int) -> AccountSnapshot:
    return AccountSnapshot(address="rA", balance_drops=str(balance), owner_count=owners)


def test_parse_optional_int() -> None:
    failures: list[str] = []
    assert handlers._parse_optional_int(None, "x", failures) is None
    assert handlers._parse_optional_int("", "x", failures) is None
    assert handlers._parse_optional_int("-2", "x", failures) == -2
    assert failures == []
    assert handlers._parse_optional_int("two", "x", failures) is None
    assert failures == ["invalid x: 'two' (expected an integer)"]


@pytest.mark.parametrize(
    ("observed", "direction", "fails"),
    [
        (1, "up", False), (0, "up", True), (-1, "increase", True), (2, "+", False),
        (-1, "down", False), (0, "decreased", True), (1, "-", True),
        (0, "unchanged", False), (1, "flat", True), (-1, "zero", True), (0, "0", False),
        (1, "sideways", True), (5, None, False), (5, "", False),
    ],
)
def test_assert_owner_direction(observed: int, direction, fails: bool) -> None:
    failures: list[str] = []
    handlers._assert_owner_direction(observed, direction, failures)
    assert bool(failures) is fails
    if fails and direction == "sideways":
        assert "unknown expected_direction='sideways'" in failures[0]
    if fails and direction and direction != "sideways":
        assert f"owner_count_delta={observed}" in failures[0]


@pytest.mark.asyncio
async def test_verify_reserve_change_missing_snapshot_raises(env: Env) -> None:
    with pytest.raises(LabException) as ei:
        await env.run("handle_verify_reserve_change", {"before": "a", "after": "b"})
    assert ei.value.error.code == "STATE_MISSING_SNAPSHOT"
    assert "'a'" in ei.value.error.message and "'b'" in ei.value.error.message
    assert "verifications" not in env.ctx


@pytest.mark.asyncio
async def test_verify_reserve_change_observation_only_passes(env: Env) -> None:
    out = await env.run(
        "handle_verify_reserve_change", {},
        snapshot_before=_snap(50_000_000, 1), snapshot_after=_snap(49_000_000, 2),
    )
    assert "Balance decreased by 1.000000 XRP" in env.out
    assert "Owner count increased" in env.out
    assert out["last_reserve_comparison"].owner_count_delta == 1
    assert verdict(out, "verify_reserve_change")["passed"] is True


@pytest.mark.asyncio
async def test_verify_reserve_change_unchanged_balance_is_a_plain_bullet(env: Env) -> None:
    await env.run(
        "handle_verify_reserve_change", {},
        snapshot_before=_snap(5, 1), snapshot_after=_snap(5, 1),
    )
    assert "Balance unchanged" in env.out


@pytest.mark.asyncio
async def test_verify_reserve_change_asserts_opted_in_expectations(env: Env) -> None:
    out = await env.run(
        "handle_verify_reserve_change",
        {"expected_owner_delta": "2", "expected_direction": "down",
         "expected_balance_delta": "-5"},
        snapshot_before=_snap(50_000_000, 1), snapshot_after=_snap(49_000_000, 2),
    )
    v = verdict(out, "verify_reserve_change")
    assert v["passed"] is False
    assert "owner_count_delta mismatch: expected +2, observed +1" in v["failures"]
    assert any("expected_direction='down'" in f for f in v["failures"])
    assert "balance_delta_drops mismatch: expected -5, observed -1000000" in v["failures"]
    assert "owner_count_delta mismatch" in env.out


@pytest.mark.asyncio
async def test_verify_reserve_change_matching_expectations_pass(env: Env) -> None:
    out = await env.run(
        "handle_verify_reserve_change",
        {"expected_owner_delta": "1", "expected_direction": "up",
         "expected_balance_delta": "-1000000", "before": "x", "after": "y"},
        snapshot_x=_snap(50_000_000, 1), snapshot_y=_snap(49_000_000, 2),
    )
    assert verdict(out, "verify_reserve_change")["passed"] is True


@pytest.mark.asyncio
async def test_verify_reserve_change_flags_a_non_integer_expectation(env: Env) -> None:
    out = await env.run(
        "handle_verify_reserve_change", {"expected_owner_delta": "many"},
        snapshot_before=_snap(1, 1), snapshot_after=_snap(1, 1),
    )
    v = verdict(out, "verify_reserve_change")
    assert v["passed"] is False
    assert v["failures"] == ["invalid expected_owner_delta: 'many' (expected an integer)"]


# -- run_audit --


@pytest.mark.asyncio
async def test_run_audit_with_nothing_to_audit(env: Env) -> None:
    calls = env.stub("run_audit", None)
    out = await env.run("handle_run_audit")
    assert calls == []
    assert "No transactions to audit yet" in env.out
    assert "last_audit" not in out


@pytest.mark.asyncio
async def test_run_audit_prints_verdicts_and_writes_report_and_pack(env: Env) -> None:
    report = SimpleNamespace(
        total=2, passed=1, failed=1, not_found=0,
        verdicts=[
            SimpleNamespace(txid="T" * 40, status="pass", checks=["a", "b", "c", "d"], failures=[]),
            SimpleNamespace(txid="U" * 40, status="fail", checks=["z"], failures=["bad result"]),
        ],
    )

    async def _run(transport, txids, on_progress=None):
        for i, t in enumerate(txids, 1):
            on_progress(i, len(txids), t)
        return report

    written: list[Path] = []
    env.mp.setattr(handlers, "run_audit", _run)
    env.mp.setattr(handlers, "ensure_workspace", lambda: None)
    env.mp.setattr(handlers, "write_audit_report_md", lambda r, p: written.append(p))
    env.mp.setattr(handlers, "write_audit_pack", lambda r, p: written.append(p))
    out = await env.run("handle_run_audit", txids=["T" * 40, "U" * 40])

    assert out["last_audit"] is report
    assert "Auditing 2 transaction(s)" in env.out
    assert "Auditing 1/2: " + "T" * 16 in env.out
    assert "Checked: 2" in env.out and "Pass:    1" in env.out and "Fail:    1" in env.out
    assert "bad result" in env.out
    lines = [ln.strip() for ln in env.out.splitlines() if ln.startswith("      ")]
    assert lines[:3] == ["a", "b", "c"]  # only the first three checks are shown
    assert "d" not in lines
    assert [p.suffix for p in written] == [".md", ".json"]
    assert written[0].parent == Path(".xrpl-lab/reports")
    assert written[1].parent == Path(".xrpl-lab/proofs")
    assert f"Report: {written[0]}" in env.out
    assert f"Audit pack: {written[1]}" in env.out
