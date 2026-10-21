"""handlers.py 4120+: deposit gate (DepositAuth/Preauth) and MPT handlers."""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from tests.cov_handlers_b._support import (
    SEED,
    TREASURY,
    Rig,
    fail_result,
    ok_result,
    patch_action,
)
from xrpl_lab.actions.mpt import MPTBalanceResult, MPTVerifyResult
from xrpl_lab.runtime import _SecretValue

pytestmark = pytest.mark.asyncio

ISSUER_SEED = "sMPTISSUERSEED"
ISSUER = "rMptIssuerAAAAAAAAAAAAAAAAAAAAAAAA"


def _failed_verification(rig: Rig) -> bool:
    return any(v["passed"] is False for v in rig.context.get("verifications", []))


# ── deposit gate on the dry-run transport ─────────────────────────────


async def _gate_rig() -> Rig:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_enable_deposit_auth)
    await rig.run(handlers.handle_create_sender_wallet)
    rig.clear()
    rig.state.tx_index.clear()  # the setup tx is not what the tests count
    rig.context.pop("txids", None)
    return rig


async def test_enable_deposit_auth_success_and_failure() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_enable_deposit_auth)
    assert ctx["deposit_auth_enabled"] is True
    assert "Deposit Authorization enabled" in rig.out
    assert [r.success for r in rig.records] == [True]

    rig = Rig()
    await rig.fund()
    rig.transport.set_fail_next()
    ctx = await rig.run(handlers.handle_enable_deposit_auth)
    assert "deposit_auth_enabled" not in ctx
    assert "Enabling Deposit Authorization failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_create_sender_wallet_funds_a_distinct_account() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_sender_wallet)
    assert isinstance(ctx["sender_seed"], _SecretValue)
    assert ctx["sender_address"] != TREASURY
    assert "Sender funded!" in rig.out


async def test_sender_payment_blocked_then_preauthorized_lands() -> None:
    rig = await _gate_rig()
    ctx = await rig.run(handlers.handle_send_sender_payment_expect_blocked)
    assert "Expected failure:" in rig.out and "tecNO_PERMISSION" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecNO_PERMISSION"
    assert [r.success for r in rig.records] == [False]  # 2.6.2: the rejection is recorded
    assert rig.acknowledged == [rig.records[0].txid]  # ...and acknowledged as the lesson
    assert "txids" not in ctx

    await rig.run(handlers.handle_authorize_sender_address)
    assert "Sender preauthorized" in rig.out
    await rig.run(handlers.handle_send_sender_payment, amount="5")
    assert "address preauthorization admitted it" in rig.out
    assert [r.success for r in rig.records] == [False, True, True]
    assert len(ctx["txids"]) == 2


async def test_blocked_handlers_require_wallets() -> None:
    rig = Rig()
    for handler in (
        handlers.handle_send_sender_payment_expect_blocked,
        handlers.handle_send_sender_payment,
    ):
        rig.clear()
        await rig.run(handler)
        assert "Missing sender wallet or treasury address" in rig.out
    rig.clear()
    await rig.run(handlers.handle_send_outsider_payment_expect_blocked)
    assert "No outsider wallet in context" in rig.out
    assert rig.records == []


async def test_blocked_payment_unexpected_success_records_real_txid(monkeypatch) -> None:
    rig = Rig()
    rig.context["sender_seed"] = _SecretValue("sS")
    patch_action(monkeypatch, "send_gated_payment", ok_result("TXLAND"))
    ctx = await rig.run(handlers.handle_send_sender_payment_expect_blocked)
    assert "Unexpected success" in rig.out
    assert ctx["txids"] == ["TXLAND"]
    assert [(r.txid, r.success) for r in rig.records] == [("TXLAND", True)]


async def test_blocked_payment_unexpected_success_without_txid_records_nothing(
    monkeypatch,
) -> None:
    rig = Rig()
    rig.context["sender_seed"] = _SecretValue("sS")
    rig.context["outsider_seed"] = _SecretValue("sO")
    patch_action(monkeypatch, "send_gated_payment", ok_result(""))
    for handler in (
        handlers.handle_send_sender_payment_expect_blocked,
        handlers.handle_send_outsider_payment_expect_blocked,
    ):
        await rig.run(handler)
    assert rig.out.count("Unexpected success") == 2
    assert rig.records == []
    assert "txids" not in rig.context


async def test_outsider_unexpected_success_records_real_txid(monkeypatch) -> None:
    rig = Rig()
    rig.context["outsider_seed"] = _SecretValue("sO")
    patch_action(monkeypatch, "send_gated_payment", ok_result("TXOUT"))
    ctx = await rig.run(handlers.handle_send_outsider_payment_expect_blocked)
    assert ctx["txids"] == ["TXOUT"]
    assert [r.success for r in rig.records] == [True]


@pytest.mark.parametrize(
    "handler",
    [
        handlers.handle_send_sender_payment_expect_blocked,
        handlers.handle_send_outsider_payment_expect_blocked,
    ],
)
async def test_blocked_payment_wrong_code_is_not_called_expected(
    monkeypatch, handler,
) -> None:
    rig = Rig()
    rig.context["sender_seed"] = _SecretValue("sS")
    rig.context["outsider_seed"] = _SecretValue("sO")
    patch_action(monkeypatch, "send_gated_payment", fail_result("tecINSUFFICIENT_RESERVE"))
    ctx = await rig.run(handler)
    assert "Expected failure" not in rig.out
    assert "Failed with tecINSUFFICIENT_RESERVE" in rig.out
    assert "expected tecNO_PERMISSION" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "tecINSUFFICIENT_RESERVE"
    assert [r.success for r in rig.records] == [False]
    assert rig.acknowledged == []  # a wrong code is recorded, not acknowledged


@pytest.mark.parametrize(
    "handler",
    [
        handlers.handle_send_sender_payment_expect_blocked,
        handlers.handle_send_outsider_payment_expect_blocked,
    ],
)
async def test_blocked_payment_wrong_code_fails_the_verification(
    monkeypatch, handler,
) -> None:
    rig = Rig()
    rig.context["sender_seed"] = _SecretValue("sS")
    rig.context["outsider_seed"] = _SecretValue("sO")
    patch_action(monkeypatch, "send_gated_payment", fail_result("tecINSUFFICIENT_RESERVE"))
    await rig.run(handler)
    assert _failed_verification(rig)


async def test_preauthorize_self_expect_fail_on_dry_run() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_preauthorize_self_expect_fail)
    assert "Expected failure:" in rig.out and "temCANNOT_PREAUTH_SELF" in rig.out
    assert ctx["failed_txids"][0]["result_code"] == "temCANNOT_PREAUTH_SELF"


async def test_preauthorize_self_wrong_code_and_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "authorize_deposit_address", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_preauthorize_self_expect_fail)
    assert "Failed with tecNO_ENTRY" in rig.out
    assert "Expected failure" not in rig.out

    rig = Rig()
    patch_action(monkeypatch, "authorize_deposit_address", ok_result("TXSELF"))
    await rig.run(handlers.handle_preauthorize_self_expect_fail)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXSELF", True)]


async def test_authorize_sender_address_needs_a_sender_and_reports_failure(
    monkeypatch,
) -> None:
    rig = Rig()
    await rig.run(handlers.handle_authorize_sender_address)
    assert "No sender wallet in context" in rig.out
    assert rig.records == []

    rig.context["sender_address"] = "rSenderAAAAAAAAAAAAAAAAAAAAAAAAA"
    patch_action(monkeypatch, "authorize_deposit_address", fail_result("tecINSUFFICIENT_RESERVE"))
    await rig.run(handlers.handle_authorize_sender_address)
    assert "Preauthorization failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_authorize_duplicate_expected_on_dry_run() -> None:
    rig = await _gate_rig()
    await rig.run(handlers.handle_authorize_sender_address)
    rig.clear()
    ctx = await rig.run(handlers.handle_authorize_sender_address_duplicate)
    assert "Expected failure:" in rig.out and "tecDUPLICATE" in rig.out
    assert ctx["failed_txids"][-1]["result_code"] == "tecDUPLICATE"
    # The real authorize, then the duplicate's recorded, acknowledged rejection.
    assert [r.success for r in rig.records] == [True, False]
    assert rig.acknowledged == [rig.records[-1].txid]


async def test_authorize_duplicate_wrong_code_and_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "authorize_deposit_address", fail_result("tecNO_TARGET"))
    await rig.run(handlers.handle_authorize_sender_address_duplicate)
    assert "Failed with tecNO_TARGET" in rig.out and "Expected failure" not in rig.out

    rig = Rig()
    patch_action(monkeypatch, "authorize_deposit_address", ok_result("TXDUP"))
    await rig.run(handlers.handle_authorize_sender_address_duplicate)
    assert "Unexpected success" in rig.out
    assert [r.success for r in rig.records] == [True]


async def test_unauthorize_then_duplicate_revocation() -> None:
    rig = await _gate_rig()
    await rig.run(handlers.handle_authorize_sender_address)
    ctx = await rig.run(handlers.handle_unauthorize_sender_address)
    assert "Preauthorization revoked" in rig.out
    assert [r.success for r in rig.records] == [True, True]
    rig.clear()
    await rig.run(handlers.handle_unauthorize_sender_address_duplicate)
    assert "Expected failure:" in rig.out and "tecNO_ENTRY" in rig.out
    assert ctx["failed_txids"][-1]["result_code"] == "tecNO_ENTRY"
    assert [r.success for r in rig.records] == [True, True, False]
    assert rig.acknowledged == [rig.records[-1].txid]


async def test_unauthorize_variants_on_unexpected_results(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "unauthorize_deposit_address", fail_result("tecINTERNAL"))
    await rig.run(handlers.handle_unauthorize_sender_address)
    assert "Revocation failed" in rig.out
    assert [r.success for r in rig.records] == [False]

    rig = Rig()
    await rig.run(handlers.handle_unauthorize_sender_address_duplicate)
    assert "Failed with tecINTERNAL" in rig.out and "Expected failure" not in rig.out

    rig = Rig()
    patch_action(monkeypatch, "unauthorize_deposit_address", ok_result("TXREV"))
    await rig.run(handlers.handle_unauthorize_sender_address_duplicate)
    assert "Unexpected success" in rig.out
    assert [r.success for r in rig.records] == [True]


async def test_sender_payment_failure_is_recorded(monkeypatch) -> None:
    rig = Rig()
    rig.context["sender_seed"] = _SecretValue("sS")
    patch_action(monkeypatch, "send_gated_payment", fail_result("tecNO_PERMISSION"))
    await rig.run(handlers.handle_send_sender_payment)
    assert "Payment failed" in rig.out
    assert [r.success for r in rig.records] == [False]


# ── credential-based preauthorization ─────────────────────────────────


async def _kyc_rig() -> Rig:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_subject_wallet)
    await rig.run(handlers.handle_create_credential, credential_type="kyc-deposit")
    await rig.run(handlers.handle_accept_credential)
    await rig.run(handlers.handle_enable_deposit_auth)
    await rig.run(handlers.handle_authorize_kyc_credential)
    rig.clear()
    return rig


async def test_kyc_credential_gates_deposits_end_to_end() -> None:
    rig = await _kyc_rig()
    before = len(rig.records)
    await rig.run(handlers.handle_send_kyc_payment, amount="7")
    assert "credential satisfied" in rig.out
    assert "CredentialIDs=" in rig.out
    assert len(rig.records) == before + 1 and rig.records[-1].success is True

    # An outsider without the credential stays blocked.
    await rig.run(handlers.handle_create_outsider_wallet)
    rig.clear()
    ctx = await rig.run(handlers.handle_send_outsider_payment_expect_blocked)
    assert "Expected failure:" in rig.out
    assert ctx["failed_txids"][-1]["result_code"] == "tecNO_PERMISSION"


async def test_authorize_kyc_credential_failure(monkeypatch) -> None:
    rig = Rig()
    calls = patch_action(
        monkeypatch, "authorize_deposit_credential", fail_result("tecINSUFFICIENT_RESERVE"),
    )
    await rig.run(handlers.handle_authorize_kyc_credential)
    assert "Credential preauthorization failed" in rig.out
    assert calls[0][0][1:4] == (SEED, TREASURY, "kyc-deposit")  # defaults
    assert [r.success for r in rig.records] == [False]


async def test_send_kyc_payment_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_send_kyc_payment)
    assert "No KYC'd player wallet" in rig.out

    rig = Rig()
    rig.context.update(subject_seed=_SecretValue("sSub"), subject_address="rSub")
    await rig.run(handlers.handle_send_kyc_payment)
    assert "Could not resolve the accepted credential" in rig.out
    assert rig.records == []


async def test_send_kyc_payment_failure_and_credential_ids(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(subject_seed=_SecretValue("sSub"), subject_address="rSub")

    async def _cred_id(*a, **k):
        return "ABCDEF0123456789ABCDEF0123456789"

    monkeypatch.setattr(handlers, "get_credential_id", _cred_id)
    calls = patch_action(monkeypatch, "send_gated_payment", fail_result("tecNO_PERMISSION"))
    await rig.run(handlers.handle_send_kyc_payment)
    assert "Payment failed" in rig.out
    assert calls[0][1]["credential_ids"] == ["ABCDEF0123456789ABCDEF0123456789"]
    assert [r.success for r in rig.records] == [False]


async def test_create_outsider_wallet_funds_account() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_outsider_wallet)
    assert ctx["outsider_address"].startswith("r")
    assert "Outsider funded!" in rig.out


# ── MPT ───────────────────────────────────────────────────────────────


async def test_mpt_issue_authorize_pay_verify_on_dry_run() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(
        handlers.handle_create_mpt_issuance, maximum_amount="5000", asset_scale="2",
        transfer_fee="10", transferable="true",
    )
    assert ctx["mpt_max"] == "5000"
    assert ctx["mpt_issuance_id"]
    assert "Issuance ID:" in rig.out

    await rig.run(handlers.handle_verify_mpt_issuance)
    assert rig.verdicts("verify_mpt_issuance")[-1]["passed"] is True
    assert "MPT issuance verified on-ledger." in rig.out
    assert rig.verdicts("verify_mpt_issuance")[-1]["failures"] == []


async def test_mpt_authorize_then_issuer_payment_to_holder() -> None:
    rig = Rig()
    holder = "rMptHolderAAAAAAAAAAAAAAAAAAAAAAAAA"
    await rig.fund(TREASURY, holder)
    await rig.run(handlers.handle_create_mpt_issuance, maximum_amount="1000")
    issuance_id = rig.context["mpt_issuance_id"]

    # Switch to the holder's seat: authorize, then the issuer pays it.
    rig.state.wallet_address = holder
    rig.context["issuer_seed"] = _SecretValue(SEED)
    await rig.run(handlers.handle_mpt_authorize)
    assert "Authorized" in rig.out
    await rig.run(handlers.handle_mpt_payment, amount="40")
    assert "40 MPT delivered" in rig.out
    assert all(r.success for r in rig.records) and len(rig.records) == 3

    await rig.run(handlers.handle_verify_mpt_balance, expected="40")
    assert rig.verdicts("verify_mpt_balance")[-1]["passed"] is True
    assert await rig.transport.get_mpt_balance(holder, issuance_id) == "40"


async def test_create_mpt_issuance_bad_numbers_fall_back_with_notes() -> None:
    rig = Rig()
    await rig.fund()
    await rig.run(
        handlers.handle_create_mpt_issuance, asset_scale="two", transfer_fee="lots",
        transferable="false",
    )
    assert "Invalid asset_scale, using default (0)." in rig.out
    assert "Invalid transfer_fee, using default (0)." in rig.out
    assert "transferable False" in rig.out


async def test_create_mpt_issuance_requires_wallet_and_reports_failure(monkeypatch) -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_create_mpt_issuance)
    assert "No wallet in context" in rig.out

    rig = Rig()
    patch_action(monkeypatch, "create_mpt_issuance", fail_result("temDISABLED"))
    ctx = await rig.run(handlers.handle_create_mpt_issuance)
    assert "MPT issuance failed" in rig.out
    assert "mpt_issuance_id" not in ctx and "mpt_max" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_create_mpt_issuance_without_id_still_succeeds(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "create_mpt_issuance", ok_result("TXMPT"))
    ctx = await rig.run(handlers.handle_create_mpt_issuance, maximum_amount=77)
    assert ctx["mpt_max"] == "77"
    assert "mpt_issuance_id" not in ctx
    assert "Issuance ID:" not in rig.out


async def test_mpt_authorize_prerequisites_and_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_mpt_authorize)
    assert "No MPT issuance id" in rig.out

    rig.context["mpt_issuance_id"] = "ISS1"
    del rig.context["wallet_seed"]
    rig.clear()
    await rig.run(handlers.handle_mpt_authorize)
    assert "No holder wallet in context" in rig.out

    rig.context["wallet_seed"] = _SecretValue(SEED)
    patch_action(monkeypatch, "authorize_mpt", fail_result("tecNO_AUTH"))
    await rig.run(handlers.handle_mpt_authorize)
    assert "MPTokenAuthorize failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_mpt_payment_prerequisites_success_failure(monkeypatch) -> None:
    rig = Rig()
    await rig.run(handlers.handle_mpt_payment)
    assert "Missing issuance id, issuer wallet, or holder" in rig.out

    rig.context.update(mpt_issuance_id="ISS1", issuer_seed=_SecretValue("sIss"))
    calls = patch_action(monkeypatch, "send_mpt", ok_result("TXPAY"))
    await rig.run(handlers.handle_mpt_payment, amount="42")
    assert "42 MPT delivered" in rig.out
    assert calls[0][0][1:] == ("sIss", TREASURY, "ISS1", "42")
    assert [r.success for r in rig.records] == [True]

    patch_action(monkeypatch, "send_mpt", fail_result("tecNO_AUTH"))
    await rig.run(handlers.handle_mpt_payment)
    assert "MPT payment failed" in rig.out
    assert [r.success for r in rig.records] == [True, False]


async def test_mpt_payment_accepts_plain_string_issuer_seed(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(mpt_issuance_id="ISS1", issuer_seed="sPlain")
    calls = patch_action(monkeypatch, "send_mpt", ok_result("TXP2"))
    await rig.run(handlers.handle_mpt_payment)
    assert calls[0][0][1] == "sPlain"


async def test_verify_mpt_balance_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_mpt_balance)
    assert "Missing issuance id or holder" in rig.out
    assert rig.verdicts("verify_mpt_balance")[0]["passed"] is False


async def test_verify_mpt_balance_pass_and_fail(monkeypatch) -> None:
    rig = Rig()
    rig.context["mpt_issuance_id"] = "ISS1"
    good = MPTBalanceResult(balance="100", checks=["balance is 100"], failures=[])
    calls = patch_action(monkeypatch, "verify_mpt_balance", good)
    await rig.run(handlers.handle_verify_mpt_balance, expected="100")
    assert calls[0][1]["expected"] == "100"
    assert "balance is 100" in rig.out
    assert rig.verdicts()[-1]["passed"] is True

    bad = MPTBalanceResult(balance="1", checks=[], failures=["expected 100, got 1"])
    patch_action(monkeypatch, "verify_mpt_balance", bad)
    await rig.run(handlers.handle_verify_mpt_balance, expected="100")
    assert "expected 100, got 1" in rig.out
    assert rig.verdicts()[-1] == {
        "action": "verify_mpt_balance", "passed": False,
        "failures": ["expected 100, got 1"],
    }
    assert rig.context["last_mpt_balance_verify"] is bad


async def test_verify_mpt_issuance_variants(monkeypatch) -> None:
    rig = Rig()
    rig.state.wallet_address = None
    await rig.run(handlers.handle_verify_mpt_issuance)
    assert "No wallet address" in rig.out
    assert rig.verdicts("verify_mpt_issuance")[0]["passed"] is False

    rig = Rig()
    missing = MPTVerifyResult(found=False, issuance=None, checks=[], failures=[])
    patch_action(monkeypatch, "verify_mpt_issuance", missing)
    await rig.run(handlers.handle_verify_mpt_issuance)
    assert rig.verdicts()[0]["passed"] is False  # not found is never green
    assert "MPT issuance verified" not in rig.out

    rig = Rig()
    rig.context["mpt_max"] = "1000"
    wrong = MPTVerifyResult(found=True, issuance=None, checks=[], failures=["max differs"])
    calls = patch_action(monkeypatch, "verify_mpt_issuance", wrong)
    await rig.run(handlers.handle_verify_mpt_issuance)
    assert calls[0][1]["expected_maximum"] == "1000"
    assert "max differs" in rig.out
    assert rig.verdicts()[0]["passed"] is False
