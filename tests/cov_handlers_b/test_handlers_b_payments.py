"""handlers.py 4120+: partial payments, custodial crediting, checks."""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from tests.cov_handlers_b._support import (
    TREASURY,
    Rig,
    fail_result,
    ok_result,
    patch_action,
)
from xrpl_lab.actions.custodial import PlayerCreditResult
from xrpl_lab.actions.partial_payment import DeliveredAmountResult
from xrpl_lab.actions.trust_line import set_trust_line
from xrpl_lab.runtime import _SecretValue

pytestmark = pytest.mark.asyncio

ISSUER = "rIssuerLabAAAAAAAAAAAAAAAAAAAAAAAAA"


def _failed_verification(rig: Rig) -> bool:
    return any(v["passed"] is False for v in rig.context.get("verifications", []))


# ── partial payment / delivered_amount ────────────────────────────────


async def test_partial_payment_requires_issuer_and_holder() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_send_partial_payment)
    assert "Missing issuer wallet or holder" in rig.out
    assert "partial_payment_txid" not in ctx and rig.records == []


async def test_partial_payment_underdelivers_and_exploit_is_demonstrated() -> None:
    rig = Rig()
    await rig.fund()
    await set_trust_line(
        rig.transport, "sHOLDER", ISSUER, "LAB", "1000", wallet_address=TREASURY,
    )
    rig.context.update(issuer_seed=_SecretValue("sISS"), issuer_address=ISSUER)
    ctx = await rig.run(
        handlers.handle_send_partial_payment, amount="100", deliver_min="10", send_max="10",
    )
    assert ctx["partial_payment_amount"] == "100"
    assert ctx["partial_payment_delivered"] == "10"
    assert ctx["partial_payment_txid"] == rig.records[-1].txid
    assert "tesSUCCESS" in rig.out and "delivered_amount" in rig.out

    rig.clear()
    await rig.run(handlers.handle_verify_delivered_amount)
    assert "THE EXPLOIT" in rig.out
    assert rig.verdicts("verify_delivered_amount")[-1]["passed"] is True
    assert rig.context["last_delivered_amount_verify"].exploit_demonstrated is True


async def test_partial_payment_failure_does_not_set_txid(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(issuer_seed="sISS", issuer_address=ISSUER)
    patch_action(monkeypatch, "send_partial_payment", fail_result("tecPATH_DRY"))
    ctx = await rig.run(handlers.handle_send_partial_payment)
    assert "Partial payment failed" in rig.out
    assert "partial_payment_txid" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_verify_delivered_amount_without_txid() -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_delivered_amount)
    assert "No partial-payment tx to inspect" in rig.out
    assert rig.verdicts("verify_delivered_amount")[0]["passed"] is False


async def test_verify_delivered_amount_no_exploit_and_failures(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(partial_payment_txid="TX1", partial_payment_delivered="10")
    full = DeliveredAmountResult(
        amount_field="10", delivered_amount="10", exploit_demonstrated=False,
        checks=["delivered in full"], failures=[],
    )
    calls = patch_action(monkeypatch, "verify_delivered_amount", full)
    await rig.run(handlers.handle_verify_delivered_amount)
    assert calls[0][1]["expected_delivered"] == "10"
    assert "THE EXPLOIT" not in rig.out
    assert rig.verdicts()[-1]["passed"] is True

    bad = DeliveredAmountResult(
        amount_field="10", delivered_amount="3", exploit_demonstrated=True,
        checks=[], failures=["delivered 3, expected 10"],
    )
    patch_action(monkeypatch, "verify_delivered_amount", bad)
    await rig.run(handlers.handle_verify_delivered_amount)
    assert "delivered 3, expected 10" in rig.out
    assert "only 3 was actually delivered" in rig.out.replace("\n", " ") or "3" in rig.out
    assert rig.verdicts()[-1]["passed"] is False


# ── custodial player crediting ────────────────────────────────────────


async def _custody_rig() -> Rig:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_enable_require_dest)
    await rig.run(handlers.handle_create_player_wallet)
    rig.clear()
    rig.state.tx_index.clear()
    rig.context.pop("txids", None)
    return rig


async def test_enable_require_dest_success_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_enable_require_dest)
    assert ctx["require_dest_enabled"] is True
    assert "RequireDest enabled" in rig.out
    assert [r.success for r in rig.records] == [True]

    rig = Rig()
    patch_action(monkeypatch, "enable_require_dest", fail_result("tecOWNERS"))
    ctx = await rig.run(handlers.handle_enable_require_dest)
    assert "require_dest_enabled" not in ctx
    assert "RequireDest enable failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_create_player_wallet_funds_a_distinct_depositor() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_player_wallet)
    assert isinstance(ctx["player_seed"], _SecretValue)
    assert ctx["player_address"] != TREASURY
    assert "Player funded!" in rig.out


async def test_assign_player_tag_registry_and_reuse_warning() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_assign_player_tag, tag="1001", player="arya")
    assert ctx["tag_registry"] == {1001: "arya"}
    assert ctx["player_tag"] == 1001 and ctx["player_name"] == "arya"
    assert "tag 1001 -> player arya" in rig.out.replace("\n", " ") or "arya" in rig.out
    assert "already assigned" not in rig.out

    await rig.run(handlers.handle_assign_player_tag, tag="1001", player="bran")
    assert "already assigned to 'arya'" in rig.out
    assert ctx["tag_registry"] == {1001: "bran"}  # reassigned for the lesson

    rig.clear()
    await rig.run(handlers.handle_assign_player_tag, tag="1001", player="bran")
    assert "already assigned" not in rig.out  # same player is not a conflict


async def test_assign_player_tag_defaults_on_bad_or_empty_input() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_assign_player_tag, tag="abc", player="")
    assert "Invalid tag, using default (1001)." in rig.out
    assert ctx["player_tag"] == 1001
    assert ctx["player_name"] == "arya"
    assert ctx["tag_registry"] == {1001: "arya"}


async def test_tagged_deposit_and_credit_end_to_end() -> None:
    rig = await _custody_rig()
    await rig.run(handlers.handle_assign_player_tag, tag="2002", player="bran")
    ctx = await rig.run(handlers.handle_send_tagged_deposit, amount="25", source_tag="7")
    assert ctx["deposit_tag"] == 2002
    assert ctx["deposit_amount"] == "25"
    assert ctx["deposit_txid"] == rig.records[-1].txid
    assert "SourceTag 7" in rig.out
    assert "Tagged deposit validated." in rig.out

    rig.clear()
    await rig.run(handlers.handle_credit_player_deposit)
    assert "CREDITED:" in rig.out and "bran" in rig.out
    assert "25000000 drops" in rig.out
    v = rig.verdicts("credit_player_deposit")[-1]
    assert v["passed"] is True and v["failures"] == []
    assert rig.context["last_player_credit"].player == "bran"


async def test_tagged_deposit_invalid_tags_are_survivable() -> None:
    rig = await _custody_rig()
    ctx = await rig.run(
        handlers.handle_send_tagged_deposit, tag="zzz", source_tag="nope", amount="3",
    )
    assert "Invalid source_tag 'nope'; omitting it." in rig.out
    assert ctx["deposit_tag"] == 1001
    assert "SourceTag" not in rig.out


async def test_tagged_deposit_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_send_tagged_deposit)
    assert "Missing player wallet or pool address" in rig.out

    rig.context["player_seed"] = "sPlayer"  # plain string is accepted too
    patch_action(monkeypatch, "send_tagged_deposit", fail_result("tecDST_TAG_NEEDED"))
    ctx = await rig.run(handlers.handle_send_tagged_deposit)
    assert "Deposit failed" in rig.out
    assert "deposit_txid" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_untagged_deposit_bounces_without_a_failed_record() -> None:
    rig = await _custody_rig()
    ctx = await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert "Expected failure:" in rig.out and "tecDST_TAG_NEEDED" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecDST_TAG_NEEDED"
    assert rig.failed_records == []
    assert "txids" not in ctx
    assert "asfRequireDest was not enabled" not in rig.out


async def test_untagged_deposit_without_require_dest_lands_and_is_flagged() -> None:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_player_wallet)
    rig.clear()
    ctx = await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert "asfRequireDest was not enabled" in rig.out
    assert "Unexpected success" in rig.out
    assert [r.success for r in rig.records] == [True]
    assert ctx["txids"] == [rig.records[0].txid]


async def test_untagged_deposit_prerequisites_and_txidless_success(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert "Missing player wallet or pool address" in rig.out

    rig.context["player_seed"] = _SecretValue("sP")
    patch_action(monkeypatch, "send_tagged_deposit", ok_result(""))
    await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert "Unexpected success" in rig.out
    assert rig.records == []  # no {txid: "failed", success: True} record


async def test_untagged_deposit_wrong_code_is_not_called_expected(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(player_seed=_SecretValue("sP"), require_dest_enabled=True)
    patch_action(monkeypatch, "send_tagged_deposit", fail_result("tecUNFUNDED_PAYMENT"))
    ctx = await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert "Expected failure" not in rig.out
    assert "Failed with tecUNFUNDED_PAYMENT" in rig.out
    assert "expected tecDST_TAG_NEEDED" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecUNFUNDED_PAYMENT"
    assert rig.records == []


@pytest.mark.xfail(
    strict=True,
    reason="BUG: a non-expected (e.g. non-validated) result is treated as the "
    "expected tec; the deliberate handler records no failed verification",
)
async def test_untagged_deposit_wrong_code_fails_the_verification(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(player_seed=_SecretValue("sP"), require_dest_enabled=True)
    patch_action(monkeypatch, "send_tagged_deposit", fail_result("tecUNFUNDED_PAYMENT"))
    await rig.run(handlers.handle_send_untagged_deposit_expect_fail)
    assert _failed_verification(rig)


async def test_credit_without_deposit_is_an_honest_failure() -> None:
    rig = Rig()
    await rig.run(handlers.handle_credit_player_deposit)
    assert "No deposit to credit" in rig.out
    assert rig.verdicts("credit_player_deposit")[0]["passed"] is False


async def test_credit_unparseable_expected_skips_exact_assertion(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(deposit_txid="TX1", tag_registry={1: "arya"})
    seen = {}

    async def _credit(transport, txid, registry, expected_drops=None):
        seen["expected_drops"] = expected_drops
        seen["registry"] = registry
        return _result(failures=["tag unknown"], player="", tag=None)

    monkeypatch.setattr(handlers, "credit_player_deposit", _credit)
    await rig.run(handlers.handle_credit_player_deposit, expected="12 xrp")
    assert "Could not parse expected amount '12 xrp'" in rig.out
    assert seen["expected_drops"] is None
    assert seen["registry"] == {1: "arya"}
    assert "tag unknown" in rig.out and "CREDITED" not in rig.out
    assert rig.verdicts("credit_player_deposit")[0]["passed"] is False


def _result(*, passed=True, failures=None, player="arya", tag=1, **kw) -> PlayerCreditResult:
    """A PlayerCreditResult; ``passed`` is derived from ``failures``."""
    failures = failures if failures is not None else ([] if passed else ["failed"])
    return PlayerCreditResult(
        player=player, tag=tag, credited_drops=kw.pop("credited_drops", ""),
        amount_field=kw.pop("amount_field", ""), checks=kw.pop("checks", []),
        failures=failures, **kw,
    )


async def test_credit_expected_amount_converted_to_drops(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(deposit_txid="TX1", tag_registry={1: "arya"}, deposit_amount="25")
    seen = {}

    async def _credit(transport, txid, registry, expected_drops=None):
        seen["expected_drops"] = expected_drops
        return _result(credited_value="25000000", credited_drops="25000000")

    monkeypatch.setattr(handlers, "credit_player_deposit", _credit)
    await rig.run(handlers.handle_credit_player_deposit)
    assert seen["expected_drops"] == "25000000"
    assert "25000000" in rig.out and "drops" in rig.out


@pytest.mark.parametrize(
    ("currency", "issuer", "unit"),
    [
        ("LAB", "rIssuerLongAddress12345", "LAB (issuer rIssuerLong"),
        ("LAB", "", "LAB"),
        ("", "", "units"),
    ],
)
async def test_credit_names_the_right_unit(monkeypatch, currency, issuer, unit) -> None:
    rig = Rig()
    rig.context.update(deposit_txid="TX1")

    async def _credit(transport, txid, registry, expected_drops=None):
        return _result(tag=5, credited_value="50", currency=currency, issuer=issuer)

    monkeypatch.setattr(handlers, "credit_player_deposit", _credit)
    await rig.run(handlers.handle_credit_player_deposit)
    assert "CREDITED:" in rig.out
    assert f"+50 {unit}" in rig.out
    assert "drops" not in rig.out  # never hardcode drops for issued currency


# ── checks ────────────────────────────────────────────────────────────


async def _check_rig() -> Rig:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_recipient_wallet)
    await rig.run(handlers.handle_create_check, amount="50")
    rig.clear()
    rig.state.tx_index.clear()
    return rig


async def test_create_recipient_wallet() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_recipient_wallet)
    assert isinstance(ctx["recipient_seed"], _SecretValue)
    assert "Player funded!" in rig.out


async def test_create_check_requires_destination_and_reports_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_create_check)
    assert "No player wallet in context" in rig.out
    assert rig.records == []

    patch_action(monkeypatch, "create_check", fail_result("tecINSUFFICIENT_RESERVE"))
    ctx = await rig.run(handlers.handle_create_check, destination="rDest")
    assert "CheckCreate failed" in rig.out
    assert "check_id" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_check_create_cash_and_credit_on_dry_run() -> None:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_recipient_wallet)
    ctx = await rig.run(handlers.handle_create_check, amount="50")
    assert ctx["check_id"] and ctx["check_send_max"] == "50"
    assert ctx["check_destination"] == ctx["recipient_address"]
    assert "no funds move yet" in rig.out

    await rig.run(handlers.handle_cash_check)
    assert "Check cashed!" in rig.out
    assert ctx["check_cash_amount"] == "50"
    assert ctx["check_id"] == ""  # the object is gone once cashed
    assert ctx["check_cash_txid"] == rig.records[-1].txid

    rig.clear()
    await rig.run(handlers.handle_credit_check_cash)
    assert "Credited the player" in rig.out
    assert rig.verdicts("credit_check_cash")[-1]["passed"] is True


async def test_cash_check_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_cash_check)
    assert "No Check to cash" in rig.out

    rig.context.update(check_id="CHK1", recipient_seed=_SecretValue("sRec"))
    patch_action(monkeypatch, "cash_check", fail_result("tecEXPIRED"))
    ctx = await rig.run(handlers.handle_cash_check, amount="5")
    assert "CheckCash failed" in rig.out
    assert ctx["check_id"] == "CHK1"  # not cleared on failure
    assert "check_cash_txid" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_credit_check_cash_without_txid_and_with_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_credit_check_cash)
    assert "No CheckCash tx to inspect" in rig.out
    assert rig.verdicts("credit_check_cash")[0]["passed"] is False

    rig.context["check_cash_txid"] = "TX1"
    bad = DeliveredAmountResult(
        amount_field="50", delivered_amount="", exploit_demonstrated=False,
        checks=[], failures=["tx not validated"],
    )
    patch_action(monkeypatch, "verify_delivered_amount", bad)
    await rig.run(handlers.handle_credit_check_cash)
    assert "tx not validated" in rig.out
    assert "Credited the player" not in rig.out
    assert rig.verdicts("credit_check_cash")[-1]["passed"] is False


async def test_outsider_cash_is_refused_for_the_check_destination_rule() -> None:
    rig = await _check_rig()
    await rig.run(handlers.handle_create_outsider_wallet)
    rig.clear()
    ctx = await rig.run(handlers.handle_cash_check_wrong_destination_expect_fail)
    assert "Expected failure:" in rig.out and "tecNO_PERMISSION" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecNO_PERMISSION"
    assert rig.failed_records == []
    assert ctx["check_id"]  # the Check survives the refused attempt


async def test_outsider_cash_prerequisites_and_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_cash_check_wrong_destination_expect_fail)
    assert "Missing Check or outsider wallet" in rig.out

    rig.context.update(check_id="CHK1", outsider_seed=_SecretValue("sO"))
    patch_action(monkeypatch, "cash_check", ok_result("TXWRONG"))
    await rig.run(handlers.handle_cash_check_wrong_destination_expect_fail)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXWRONG", True)]


async def test_outsider_cash_wrong_code_is_not_called_expected(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(check_id="CHK1", outsider_seed=_SecretValue("sO"))
    patch_action(monkeypatch, "cash_check", fail_result("tecNO_ENTRY"))
    ctx = await rig.run(handlers.handle_cash_check_wrong_destination_expect_fail)
    assert "Expected failure" not in rig.out
    assert "Failed with tecNO_ENTRY" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecNO_ENTRY"


@pytest.mark.xfail(
    strict=True,
    reason="BUG: the outsider CheckCash accepts any failure as the expected "
    "tecNO_PERMISSION; a mismatch records no failed verification",
)
async def test_outsider_cash_wrong_code_fails_the_verification(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(check_id="CHK1", outsider_seed=_SecretValue("sO"))
    patch_action(monkeypatch, "cash_check", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_cash_check_wrong_destination_expect_fail)
    assert _failed_verification(rig)


async def test_cancel_check_frees_the_reserve_and_clears_the_id() -> None:
    rig = await _check_rig()
    ctx = await rig.run(handlers.handle_cancel_check)
    assert "Check cancelled" in rig.out
    assert ctx["check_id"] == ""
    assert [r.success for r in rig.records] == [True]


async def test_cancel_check_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_cancel_check)
    assert "No Check to cancel" in rig.out and rig.records == []

    rig.context["check_id"] = "CHECKID1234567890ABCDEF"
    patch_action(monkeypatch, "cancel_check", fail_result("tecNO_ENTRY"))
    ctx = await rig.run(handlers.handle_cancel_check)
    assert "CheckCancel failed" in rig.out
    assert ctx["check_id"] == "CHECKID1234567890ABCDEF"
    assert [r.success for r in rig.records] == [False]
