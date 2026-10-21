"""handlers.py 4120+: signer-list delete, DID, credentials, permissioned domains."""

from __future__ import annotations

import pytest

import xrpl_lab.handlers as handlers
from tests.cov_handlers_b._support import (
    SEED,
    TREASURY,
    FaucetTransport,
    Rig,
    fail_result,
    ok_result,
    patch_action,
)
from xrpl_lab.actions.credentials import CredentialVerifyResult
from xrpl_lab.actions.did import DIDGoneResult, DIDVerifyResult
from xrpl_lab.actions.multisig import SignerListVerifyResult
from xrpl_lab.actions.permissioned_domains import (
    DomainVerifyResult,
    PermissionedOfferVerifyResult,
)
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.transport.base import FundResult

pytestmark = pytest.mark.asyncio


# ── signer list delete / verify ───────────────────────────────────────


async def test_delete_signer_list_requires_wallet() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    ctx = await rig.run(handlers.handle_delete_signer_list)
    assert "No wallet in context" in rig.out
    assert "signer_list_deleted" not in ctx
    assert rig.records == []


async def test_delete_signer_list_success_records_and_flags(monkeypatch) -> None:
    rig = Rig()
    calls = patch_action(monkeypatch, "delete_signer_list", ok_result("TXDEL"))
    ctx = await rig.run(handlers.handle_delete_signer_list)
    assert ctx["signer_list_deleted"] is True
    assert ctx["txids"] == ["TXDEL"]
    assert calls[0][0][1:] == (SEED, TREASURY)
    assert "Signer list deleted" in rig.out
    assert "tecNO_ALTERNATIVE_KEY" in rig.out
    assert "https://explorer.test/TXDEL" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXDEL", True)]


async def test_delete_signer_list_failure_is_a_failed_record(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "delete_signer_list", fail_result("tecNO_ALTERNATIVE_KEY"))
    ctx = await rig.run(handlers.handle_delete_signer_list)
    assert "Delete failed" in rig.out
    assert "Category:" in rig.out  # _explain_failure taught the code
    assert "signer_list_deleted" not in ctx
    assert [(r.txid, r.success) for r in rig.records] == [("TXBAD1", False)]


async def test_delete_signer_list_real_transport_roundtrip() -> None:
    rig = Rig()
    await rig.fund()
    await rig.transport.submit_signer_list_set(
        SEED, 1, [("rSignerAAAAAAAAAAAAAAAAAAAAAAAAAAA", 1)], owner_address=TREASURY,
    )
    ctx = await rig.run(handlers.handle_delete_signer_list)
    assert ctx.get("signer_list_deleted") is True
    await rig.run(handlers.handle_verify_signer_list_deleted)
    assert rig.verdicts("verify_signer_list_deleted")[-1]["passed"] is True
    assert "single-key control" in rig.out


async def test_verify_signer_list_deleted_without_treasury_fails_verification() -> None:
    rig = Rig()
    rig.state.wallet_address = None
    ctx = await rig.run(handlers.handle_verify_signer_list_deleted)
    assert "No treasury wallet" in rig.out
    assert ctx["verifications"] == [
        {
            "action": "verify_signer_list_deleted", "passed": False,
            "failures": ["treasury address missing — the wallet step did not run"],
        }
    ]


async def test_verify_signer_list_deleted_reports_failures(monkeypatch) -> None:
    rig = Rig()
    res = SignerListVerifyResult(
        found=True, quorum=2, entries=[], checks=["looked"], failures=["list still there"],
    )
    patch_action(monkeypatch, "verify_signer_list", res)
    await rig.run(handlers.handle_verify_signer_list_deleted)
    assert "looked" in rig.out and "list still there" in rig.out
    assert "single-key control" not in rig.out
    v = rig.verdicts()[0]
    assert v["passed"] is False and v["failures"] == ["list still there"]


# ── DID ───────────────────────────────────────────────────────────────


async def test_set_did_requires_wallet() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    ctx = await rig.run(handlers.handle_set_did)
    assert "No wallet in context" in rig.out
    assert "did_uri" not in ctx and rig.records == []


async def test_did_lifecycle_on_dry_run() -> None:
    rig = Rig()
    await rig.fund()
    ctx = await rig.run(handlers.handle_set_did, uri="did:xrpl:test", data="abc")
    assert ctx["did_uri"] == "did:xrpl:test"
    assert "DID set!" in rig.out
    assert rig.records[-1].success is True

    await rig.run(handlers.handle_verify_did)
    assert rig.verdicts("verify_did")[-1]["passed"] is True
    assert "DID verified on-ledger." in rig.out

    await rig.run(handlers.handle_delete_did)
    assert "DID deleted" in rig.out
    assert rig.records[-1].success is True

    await rig.run(handlers.handle_verify_did_deleted)
    assert rig.verdicts("verify_did_deleted")[-1]["passed"] is True
    assert "Identity hygiene complete" in rig.out


async def test_set_did_failure_records_failed_tx_and_no_uri() -> None:
    rig = Rig()
    await rig.fund()
    rig.transport.set_fail_next()
    ctx = await rig.run(handlers.handle_set_did, uri="did:xrpl:x")
    assert "DIDSet failed" in rig.out
    assert "did_uri" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_verify_did_without_wallet_fails_verification() -> None:
    rig = Rig()
    rig.state.wallet_address = ""
    await rig.run(handlers.handle_verify_did)
    assert "No wallet address" in rig.out
    assert rig.verdicts("verify_did")[0]["passed"] is False


async def test_verify_did_found_but_failing_is_not_green(monkeypatch) -> None:
    rig = Rig()
    res = DIDVerifyResult(found=True, did=None, checks=[], failures=["URI mismatch"])
    patch_action(monkeypatch, "verify_did", res)
    ctx = await rig.run(handlers.handle_verify_did)
    assert "URI mismatch" in rig.out
    assert "DID verified on-ledger." not in rig.out
    assert ctx["last_did_verify"] is res
    assert rig.verdicts()[0]["passed"] is False


async def test_verify_did_not_found_is_failed(monkeypatch) -> None:
    rig = Rig()
    res = DIDVerifyResult(found=False, did=None, checks=[], failures=[])
    patch_action(monkeypatch, "verify_did", res)
    await rig.run(handlers.handle_verify_did)
    assert rig.verdicts()[0]["passed"] is False


async def test_delete_did_requires_wallet() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_delete_did)
    assert "No wallet in context" in rig.out
    assert rig.records == []


async def test_delete_did_failure(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "delete_did", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_delete_did)
    assert "DIDDelete failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_verify_did_deleted_without_wallet() -> None:
    rig = Rig()
    rig.state.wallet_address = None
    await rig.run(handlers.handle_verify_did_deleted)
    assert rig.verdicts("verify_did_deleted")[0]["passed"] is False


async def test_verify_did_deleted_still_present(monkeypatch) -> None:
    rig = Rig()
    res = DIDGoneResult(gone=False, checks=[], failures=["DID still on ledger"])
    patch_action(monkeypatch, "verify_did_deleted", res)
    await rig.run(handlers.handle_verify_did_deleted)
    assert "DID still on ledger" in rig.out
    assert "Identity hygiene complete" not in rig.out
    assert rig.verdicts()[0]["passed"] is False


# ── subject wallet and the faucet seam (_fund_new_wallet) ─────────────


async def test_create_subject_wallet_funds_and_exposes_secret() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_subject_wallet)
    assert isinstance(ctx["subject_seed"], _SecretValue)
    assert ctx["subject_address"].startswith("r")
    assert "Subject funded!" in rig.out
    assert "verifications" not in ctx
    assert await rig.transport.get_balance(ctx["subject_address"]) != "0"
    assert ctx["subject_seed"].get() not in rig.out


async def test_create_subject_wallet_faucet_rate_limited() -> None:
    fund = FundResult(
        success=False, address="x", message="slow down",
        code="RUNTIME_FAUCET_RATE_LIMITED",
    )
    rig = Rig(FaucetTransport(fund))
    ctx = await rig.run(handlers.handle_create_subject_wallet)
    assert "RUNTIME_FAUCET_RATE_LIMITED" in rig.out
    assert "Hint:" in rig.out
    v = rig.verdicts("create_subject_wallet")[0]
    assert v["passed"] is False
    assert v["failures"] == ["subject wallet not funded on a validated ledger"]
    assert "subject_address" in ctx  # the wallet exists; only funding failed


async def test_create_subject_wallet_faucet_generic_failure_sanitizes_url() -> None:
    fund = FundResult(
        success=False, address="x",
        message="bad https://user:secret@faucet.example.com/path?token=abc",
    )
    rig = Rig(FaucetTransport(fund))
    await rig.run(handlers.handle_create_subject_wallet)
    assert "Subject funding:" in rig.out
    assert "secret" not in rig.out and "token=abc" not in rig.out
    assert rig.verdicts("create_subject_wallet")[0]["passed"] is False


async def test_create_subject_wallet_never_validates() -> None:
    fund = FundResult(success=True, address="x", balance="1000")
    rig = Rig(FaucetTransport(fund, settle=False))
    await rig.run(handlers.handle_create_subject_wallet)
    assert "appeared on a validated ledger" in rig.out
    assert "Subject funded!" not in rig.out
    assert rig.verdicts("create_subject_wallet")[0]["passed"] is False


# ── credentials ───────────────────────────────────────────────────────


async def _credential_rig() -> Rig:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_subject_wallet)
    rig.clear()
    return rig


async def test_credential_happy_path_through_delete() -> None:
    rig = await _credential_rig()
    ctx = await rig.run(handlers.handle_create_credential, credential_type="kyc")
    assert ctx["credential_type"] == "kyc"
    assert ctx["credential_issuer"] == TREASURY
    assert ctx["credential_subject"] == ctx["subject_address"]
    assert "PROVISIONAL" in rig.out

    # Not valid until accepted.
    await rig.run(handlers.handle_verify_credential)
    assert rig.verdicts("verify_credential")[-1]["passed"] is False

    await rig.run(handlers.handle_accept_credential)
    assert "now VALID on-ledger" in rig.out
    await rig.run(handlers.handle_verify_credential)
    assert rig.verdicts("verify_credential")[-1]["passed"] is True
    assert "gate would pass this player" in rig.out

    await rig.run(handlers.handle_delete_credential)
    assert "Credential deleted" in rig.out
    assert all(r.success for r in rig.records)
    assert len(rig.records) == 3  # create, accept, delete

    await rig.run(handlers.handle_verify_credential)
    assert rig.verdicts("verify_credential")[-1]["passed"] is False


async def test_create_credential_prerequisites() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_create_credential)
    assert "No issuer wallet in context" in rig.out

    rig = Rig()
    await rig.run(handlers.handle_create_credential)
    assert "No subject wallet" in rig.out
    assert rig.records == []


async def test_create_credential_failure_not_threaded_forward() -> None:
    rig = await _credential_rig()
    rig.transport.set_fail_next()
    ctx = await rig.run(handlers.handle_create_credential, credential_type="kyc")
    assert "CredentialCreate failed" in rig.out
    assert "credential_type" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_create_credential_unfunded_prints_expected_failure() -> None:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_credential_unfunded)
    assert "Expected failure:" in rig.out
    assert "tecNO_TARGET" in rig.out


async def test_create_credential_unfunded_requires_wallet() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_create_credential_unfunded)
    assert "No issuer wallet in context" in rig.out


async def test_create_credential_unfunded_unexpected_success_is_recorded() -> None:
    rig = Rig()
    await rig.fund()
    await rig.fund("rFundedSubjectAAAAAAAAAAAAAAAAAAAA")
    await rig.run(
        handlers.handle_create_credential_unfunded,
        subject="rFundedSubjectAAAAAAAAAAAAAAAAAAAA",
    )
    assert "Unexpected success" in rig.out
    assert "Expected failure" not in rig.out
    assert [r.success for r in rig.records] == [True]


async def test_create_credential_duplicate_prints_expected_failure() -> None:
    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential, credential_type="kyc")
    rig.clear()
    await rig.run(handlers.handle_create_credential_duplicate)
    assert "Expected failure:" in rig.out and "tecDUPLICATE" in rig.out


async def test_create_credential_duplicate_prerequisites() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_create_credential_duplicate)
    assert "No issuer wallet in context" in rig.out
    rig = Rig()
    await rig.run(handlers.handle_create_credential_duplicate)
    assert "No subject wallet" in rig.out


async def test_create_credential_duplicate_unexpected_success() -> None:
    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential_duplicate, credential_type="fresh")
    assert "Unexpected success" in rig.out
    assert [r.success for r in rig.records] == [True]


async def test_accept_wrong_party_prints_expected_rejection(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "accept_credential", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_accept_credential_wrong_party)
    assert "Expected rejection:" in rig.out and "tecNO_ENTRY" in rig.out
    assert "hold your own passport" in rig.out


async def test_accept_wrong_party_requires_wallet() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    await rig.run(handlers.handle_accept_credential_wrong_party)
    assert "No issuer wallet in context" in rig.out


async def test_accept_wrong_party_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "accept_credential", ok_result("TXACC"))
    await rig.run(handlers.handle_accept_credential_wrong_party)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXACC", True)]


async def test_accept_credential_failure_and_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_accept_credential)
    assert "No subject wallet" in rig.out and rig.records == []

    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential, credential_type="kyc")
    rig.transport.set_fail_next()
    await rig.run(handlers.handle_accept_credential)
    assert "CredentialAccept failed" in rig.out
    assert [r.success for r in rig.records][-1] is False


async def test_accept_credential_accepts_plain_string_seed() -> None:
    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential, credential_type="kyc")
    rig.context["subject_seed"] = rig.context["subject_seed"].get()  # plain str
    await rig.run(handlers.handle_accept_credential)
    assert "now VALID on-ledger" in rig.out


async def test_verify_credential_without_context_fails_verification() -> None:
    rig = Rig()
    rig.state.wallet_address = ""
    await rig.run(handlers.handle_verify_credential)
    assert "No credential in context" in rig.out
    assert rig.verdicts("verify_credential")[0]["passed"] is False


async def test_verify_credential_prints_failures(monkeypatch) -> None:
    rig = Rig()
    rig.context["subject_address"] = "rSub"
    res = CredentialVerifyResult(
        found=True, credential=None, checks=["found"], failures=["not accepted"],
    )
    patch_action(monkeypatch, "verify_credential", res)
    await rig.run(handlers.handle_verify_credential)
    assert "not accepted" in rig.out
    assert "gate would pass" not in rig.out
    assert rig.verdicts()[0] == {
        "action": "verify_credential", "passed": False, "failures": ["not accepted"],
    }


async def test_delete_credential_failure_and_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_delete_credential)
    assert "No subject wallet" in rig.out

    rig = await _credential_rig()
    rig.transport.set_fail_next()
    await rig.run(handlers.handle_delete_credential)
    assert "CredentialDelete failed" in rig.out
    assert [r.success for r in rig.records] == [False]


# ── permissioned domains ──────────────────────────────────────────────


async def _domain_rig() -> Rig:
    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential, credential_type="kyc")
    await rig.run(handlers.handle_accept_credential)
    rig.clear()
    return rig


async def test_domain_lifecycle_on_dry_run() -> None:
    rig = await _domain_rig()
    ctx = await rig.run(handlers.handle_create_permissioned_domain)
    assert ctx["domain_id"]
    assert ctx["domain_issuer"] == TREASURY
    assert ctx["domain_credential_type"] == "kyc"
    assert "Permissioned Domain created!" in rig.out

    await rig.run(handlers.handle_verify_domain)
    assert rig.verdicts("verify_domain")[-1]["passed"] is True

    await rig.run(handlers.handle_create_permissioned_offer)
    assert ctx["permissioned_offer_seq"] is not None
    assert "Permissioned offer placed" in rig.out
    await rig.run(handlers.handle_verify_permissioned_offer)
    assert rig.verdicts("verify_permissioned_offer")[-1]["passed"] is True

    await rig.run(handlers.handle_delete_permissioned_domain)
    assert "Domain deleted" in rig.out
    assert "domain_id" not in rig.context
    assert all(r.success for r in rig.records)


async def test_hybrid_offer_flag_is_passed_through(monkeypatch) -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    calls = patch_action(
        monkeypatch, "create_permissioned_offer", ok_result("TXOFF", offer_sequence=7),
    )
    await rig.run(
        handlers.handle_create_permissioned_offer, hybrid="true",
        pays_currency="XRP", gets_currency="LAB",
    )
    assert calls[0][1]["hybrid"] is True
    assert "hybrid" in rig.out
    # XRP leg carries no issuer; the issued leg carries the domain issuer.
    assert calls[0][0][4] == "" and calls[0][0][7] == TREASURY
    assert rig.context["permissioned_offer_seq"] == 7


async def test_domain_handlers_need_their_prerequisites() -> None:
    rig = Rig()
    del rig.context["wallet_seed"]
    for handler in (
        handlers.handle_create_permissioned_domain,
        handlers.handle_modify_domain_drop_credential,
        handlers.handle_delete_permissioned_domain,
    ):
        rig.clear()
        await rig.run(handler)
        assert "No owner wallet in context" in rig.out

    rig = Rig()
    for handler in (
        handlers.handle_create_permissioned_offer,
        handlers.handle_create_permissioned_offer_uncredentialed,
        handlers.handle_modify_domain_drop_credential,
        handlers.handle_modify_domain_nonowner,
        handlers.handle_delete_permissioned_domain,
    ):
        rig.clear()
        await rig.run(handler)
        assert "No domain in context" in rig.out
    assert rig.records == []

    rig.context["domain_id"] = "DOM1"
    rig.clear()
    await rig.run(handlers.handle_create_permissioned_offer)
    assert "No credentialed (subject) wallet" in rig.out
    for handler in (
        handlers.handle_create_permissioned_offer_uncredentialed,
        handlers.handle_modify_domain_nonowner,
    ):
        rig.clear()
        await rig.run(handler)
        assert "No outsider wallet" in rig.out
    assert rig.records == []


async def test_create_domain_failure_does_not_set_domain_id(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "set_permissioned_domain", fail_result("temDISABLED"))
    ctx = await rig.run(handlers.handle_create_permissioned_domain)
    assert "PermissionedDomainSet failed" in rig.out
    assert "domain_id" not in ctx
    assert [r.success for r in rig.records] == [False]


async def test_permissioned_offer_failure(monkeypatch) -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    patch_action(monkeypatch, "create_permissioned_offer", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_create_permissioned_offer)
    assert "Permissioned offer failed" in rig.out
    assert "permissioned_offer_seq" not in ctx
    assert [r.success for r in rig.records][-1] is False


async def test_create_uncredentialed_wallet_funds_outsider() -> None:
    rig = Rig()
    ctx = await rig.run(handlers.handle_create_uncredentialed_wallet)
    assert isinstance(ctx["outsider_seed"], _SecretValue)
    assert "Outsider funded!" in rig.out


async def test_uncredentialed_offer_rejected_by_gate() -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    await rig.run(handlers.handle_create_uncredentialed_wallet)
    rig.clear()
    await rig.run(handlers.handle_create_permissioned_offer_uncredentialed)
    assert "Expected rejection:" in rig.out
    assert "NOT by CredentialIDs" in rig.out


async def test_uncredentialed_offer_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(
        domain_id="DOM1", outsider_seed=_SecretValue("sOut"), outsider_address="rOut",
    )
    patch_action(
        monkeypatch, "create_permissioned_offer", ok_result("TXU", offer_sequence=9),
    )
    ctx = await rig.run(handlers.handle_create_permissioned_offer_uncredentialed)
    assert "Unexpected success" in rig.out
    assert ctx["uncredentialed_offer_seq"] == 9
    assert [(r.txid, r.success) for r in rig.records] == [("TXU", True)]


async def test_modify_domain_drop_credential_swaps_accepted_set(monkeypatch) -> None:
    rig = Rig()
    rig.context["domain_id"] = "DOM1"
    rig.context["domain_issuer"] = "rIss"
    calls = patch_action(monkeypatch, "set_permissioned_domain", ok_result("TXM"))
    await rig.run(handlers.handle_modify_domain_drop_credential, replacement_type="decoy")
    assert calls[0][0][2] == [("rIss", "decoy")]
    assert calls[0][1]["domain_id"] == "DOM1"
    assert "accepted set fully replaced" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXM", True)]


async def test_modify_domain_drop_credential_failure(monkeypatch) -> None:
    rig = Rig()
    rig.context["domain_id"] = "DOM1"
    patch_action(monkeypatch, "set_permissioned_domain", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_modify_domain_drop_credential)
    assert "PermissionedDomainSet (modify) failed" in rig.out
    assert [r.success for r in rig.records] == [False]


async def test_modify_domain_nonowner_rejected_on_dry_run() -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    await rig.run(handlers.handle_create_uncredentialed_wallet)
    rig.clear()
    await rig.run(handlers.handle_modify_domain_nonowner)
    assert "Expected rejection:" in rig.out
    assert "key custody matters" in rig.out


async def test_modify_domain_nonowner_unexpected_success(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(
        domain_id="DOM1", outsider_seed=_SecretValue("sOut"), outsider_address="rOut",
        domain_issuer="rIss",
    )
    patch_action(monkeypatch, "set_permissioned_domain", ok_result("TXN"))
    await rig.run(handlers.handle_modify_domain_nonowner)
    assert "Unexpected success" in rig.out
    assert [(r.txid, r.success) for r in rig.records] == [("TXN", True)]


async def test_delete_domain_failure_keeps_domain_id(monkeypatch) -> None:
    rig = Rig()
    rig.context["domain_id"] = "DOM1"
    patch_action(monkeypatch, "delete_permissioned_domain", fail_result("tecNO_PERMISSION"))
    ctx = await rig.run(handlers.handle_delete_permissioned_domain)
    assert "PermissionedDomainDelete failed" in rig.out
    assert ctx["domain_id"] == "DOM1"
    assert [r.success for r in rig.records] == [False]


async def test_verify_domain_missing_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_domain)
    assert "No domain in context" in rig.out
    assert rig.verdicts("verify_domain")[0]["passed"] is False


async def test_verify_domain_expect_absent_after_drop(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(
        domain_id="DOM1", domain_issuer="rIss", domain_credential_type="kyc",
    )
    res = DomainVerifyResult(found=True, domain=None, checks=["gone"], failures=[])
    calls = patch_action(monkeypatch, "verify_domain", res)
    await rig.run(handlers.handle_verify_domain, expect_absent="true")
    assert calls[0][1]["expect_absent"] is True
    assert calls[0][1]["expect_issuer"] == "rIss"
    assert rig.verdicts()[0]["passed"] is True


async def test_verify_domain_failures_are_recorded(monkeypatch) -> None:
    rig = Rig()
    rig.context["domain_id"] = "DOM1"
    res = DomainVerifyResult(found=False, domain=None, checks=[], failures=["no such domain"])
    patch_action(monkeypatch, "verify_domain", res)
    await rig.run(handlers.handle_verify_domain)
    assert "no such domain" in rig.out
    assert rig.verdicts()[0]["failures"] == ["no such domain"]


async def test_verify_permissioned_offer_missing_prerequisites() -> None:
    rig = Rig()
    await rig.run(handlers.handle_verify_permissioned_offer)
    assert "No permissioned offer in context" in rig.out
    assert rig.verdicts("verify_permissioned_offer")[0]["passed"] is False


async def test_verify_permissioned_offer_failure(monkeypatch) -> None:
    rig = Rig()
    rig.context.update(subject_address="rSub", permissioned_offer_seq=0)
    res = PermissionedOfferVerifyResult(
        placed=False, offer=None, checks=[], failures=["offer missing"],
    )
    patch_action(monkeypatch, "verify_permissioned_offer", res)
    await rig.run(handlers.handle_verify_permissioned_offer)
    assert "offer missing" in rig.out
    assert rig.verdicts()[0]["passed"] is False


# ── expected-failure lessons are acknowledged ────────────────────────
# The runner counts a failed TxRecord as a failed step unless the lesson
# acknowledged it as its expected outcome (fixed in 2.6.1).

async def test_unfunded_credential_lesson_is_acknowledged() -> None:
    rig = Rig()
    await rig.fund()
    await rig.run(handlers.handle_create_credential_unfunded)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]


async def test_duplicate_credential_lesson_is_acknowledged() -> None:
    rig = await _credential_rig()
    await rig.run(handlers.handle_create_credential, credential_type="kyc")
    await rig.run(handlers.handle_create_credential_duplicate)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]


async def test_wrong_party_accept_lesson_is_acknowledged(monkeypatch) -> None:
    rig = Rig()
    patch_action(monkeypatch, "accept_credential", fail_result("tecNO_ENTRY"))
    await rig.run(handlers.handle_accept_credential_wrong_party)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]


async def test_uncredentialed_offer_lesson_is_acknowledged() -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    await rig.run(handlers.handle_create_uncredentialed_wallet)
    await rig.run(handlers.handle_create_permissioned_offer_uncredentialed)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]


async def test_nonowner_modify_lesson_is_acknowledged() -> None:
    rig = await _domain_rig()
    await rig.run(handlers.handle_create_permissioned_domain)
    await rig.run(handlers.handle_create_uncredentialed_wallet)
    await rig.run(handlers.handle_modify_domain_nonowner)
    # The tec IS on the ledger, so it stays a failed TxRecord; the lesson
    # acknowledges it as its expected outcome (handlers._judge_expected_failure).
    assert len(rig.failed_records) <= rig.context.get("expected_failures", 0)
    assert rig.context.get("expected_failures", 0) >= 1
    assert not [v for v in rig.verdicts() if not v["passed"]]
