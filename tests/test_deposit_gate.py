"""Tests for the Deposit Gate — DepositAuth + DepositPreauth (XLS-70 extension).

Completes the XLS-70 arc alongside credentials_101 (attestation) and
permissioned_domains_101 (gates TRADING via DomainID) — this module gates
INBOUND VALUE to a treasury. Coverage (all offline, dry-run transport):

  (a) asfDepositAuth gate parity: an unsolicited Payment to a DepositAuth
      destination fails tecNO_PERMISSION; clearing the flag reopens it.
  (b) DepositPreauth by ADDRESS: Authorize admits the sender; temCANNOT_PREAUTH_SELF,
      tecDUPLICATE, tecNO_ENTRY (revoke); Unauthorize is the compensator.
  (c) DepositPreauth by CREDENTIAL: AuthorizeCredentials admits ANY holder of a
      matching valid credential; a provisional, expired, wrong-subject, or
      non-matching credential does NOT admit; tecDUPLICATE / tecNO_ENTRY /
      UnauthorizeCredentials mirror the address path.
  (d) Payment.credential_ids local validation parity (empty / >8 / duplicates)
      and the "exactly one of four" DepositPreauth field rule.
  (e) The sub-reserve exemption (a destination at/below the base reserve can
      still receive a small XRP Payment from anyone).
  (f) get_credential_id resolves the accepted credential's on-ledger id.
  (g) Handlers: the full module flow end-to-end through the registered
      handlers, including the honest failure/success console paths.
  (h) The module lints clean and pins its confirmed kb_source + prereq.

The mainnet-refusal coverage for submit_deposit_auth / submit_deposit_preauth
is enforced by tests/test_network_safety.py (the _MAINNET_REFUSAL_CALLS row +
the reflection completeness gate) — not duplicated here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.credentials import accept_credential, create_credential
from xrpl_lab.actions.deposit_gate import (
    authorize_deposit_address,
    authorize_deposit_credential,
    enable_deposit_auth,
    get_credential_id,
    send_gated_payment,
    unauthorize_deposit_address,
    unauthorize_deposit_credential,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.modules import parse_module
from xrpl_lab.transport.dry_run import DryRunTransport

_TREASURY = "rTreasuryAAAAAAAAAAAAAAAAAAAAAAA"
_ISSUER = _TREASURY  # dual role, mirroring permissioned_domains_101's owner+issuer
_SENDER = "rSenderBBBBBBBBBBBBBBBBBBBBBBBBB"
_SUBJECT = "rSubjectCCCCCCCCCCCCCCCCCCCCCCCC"
_OUTSIDER = "rOutsiderDDDDDDDDDDDDDDDDDDDDDDD"
_TYPE = "kyc-deposit"
_MODULE_PATH = Path(__file__).parent.parent / "modules" / "deposit_gate_101.md"


@pytest.fixture
def transport() -> DryRunTransport:
    return DryRunTransport()


async def _fund(t: DryRunTransport, address: str) -> None:
    await t.fund_from_faucet(address)


async def _enable_gate(t: DryRunTransport) -> None:
    await _fund(t, _TREASURY)
    res = await enable_deposit_auth(t, "sTREASURY", wallet_address=_TREASURY)
    assert res.success
    assert res.result_code == "tesSUCCESS"
    assert res.txid


async def _accepted_kyc_credential(t: DryRunTransport, subject: str = _SUBJECT) -> None:
    """Issue + accept a kyc-deposit credential so *subject* qualifies for the gate."""
    await _fund(t, subject)
    await create_credential(t, "sISSUER", subject, _TYPE, issuer_address=_ISSUER)
    await accept_credential(t, "sSUBJECT", _ISSUER, _TYPE, subject_address=subject)


# ── (a) asfDepositAuth gate parity ──────────────────────────────────────────


class TestDepositAuthGate:
    @pytest.mark.asyncio
    async def test_unsolicited_payment_blocked(self, transport):
        await _enable_gate(transport)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10", sender_address=_SENDER
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"
        assert not r.txid

    @pytest.mark.asyncio
    async def test_payment_to_open_account_still_succeeds(self, transport):
        # DepositAuth is opt-in per account — an account that never enabled it
        # accepts unsolicited Payments (the pre-gate baseline).
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10", sender_address=_SENDER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_clearing_deposit_auth_reopens_unsolicited_payments(self, transport):
        await _enable_gate(transport)
        # The named compensator: AccountSet ClearFlag asfDepositAuth.
        cleared = await enable_deposit_auth(
            transport, "sTREASURY", wallet_address=_TREASURY, enable=False
        )
        assert cleared.success

        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10", sender_address=_SENDER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_self_payment_is_not_gated_against_itself(self, transport):
        # Guard against a nonsensical self-block: the destination paying
        # itself is out of scope for this gate (XRP self-payment is refused
        # for other reasons entirely, but never tecNO_PERMISSION here).
        await _enable_gate(transport)
        r = await send_gated_payment(
            transport, "sTREASURY", _TREASURY, "10", sender_address=_TREASURY
        )
        assert r.result_code != "tecNO_PERMISSION"


# ── (b) DepositPreauth by ADDRESS ───────────────────────────────────────────


class TestAddressPreauth:
    @pytest.mark.asyncio
    async def test_authorize_admits_the_sender(self, transport):
        await _enable_gate(transport)
        auth = await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert auth.success is True
        assert auth.result_code == "tesSUCCESS"
        assert auth.txid

        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10", sender_address=_SENDER
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_authorize_consumes_owner_reserve(self, transport):
        await _enable_gate(transport)
        assert transport._owner_counts.get(_TREASURY, 0) == 0
        await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert transport._owner_counts.get(_TREASURY, 0) == 1

    @pytest.mark.asyncio
    async def test_self_preauthorization_rejected(self, transport):
        await _enable_gate(transport)
        r = await authorize_deposit_address(
            transport, "sTREASURY", _TREASURY, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "temCANNOT_PREAUTH_SELF"

    @pytest.mark.asyncio
    async def test_duplicate_authorize_rejected(self, transport):
        await _enable_gate(transport)
        await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        r = await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "tecDUPLICATE"

    @pytest.mark.asyncio
    async def test_unauthorize_is_the_compensator(self, transport):
        await _enable_gate(transport)
        await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert transport._owner_counts.get(_TREASURY, 0) == 1

        r = await unauthorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert r.success is True
        assert transport._owner_counts.get(_TREASURY, 0) == 0

        # The sender is blocked again — the exception is gone.
        await _fund(transport, _SENDER)
        blocked = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10", sender_address=_SENDER
        )
        assert blocked.success is False
        assert blocked.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_revoking_nonexistent_preauth_rejected(self, transport):
        await _enable_gate(transport)
        r = await unauthorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_revoking_twice_rejected(self, transport):
        await _enable_gate(transport)
        await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        first = await unauthorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert first.success is True
        second = await unauthorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        assert second.success is False
        assert second.result_code == "tecNO_ENTRY"


# ── (c) DepositPreauth by CREDENTIAL ─────────────────────────────────────────


class TestCredentialPreauth:
    @pytest.mark.asyncio
    async def test_authorize_credentials_admits_a_qualifying_holder(self, transport):
        await _enable_gate(transport)
        await _accepted_kyc_credential(transport)
        auth = await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        assert auth.success is True
        assert auth.result_code == "tesSUCCESS"

        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        assert cred_id

        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_provisional_credential_does_not_admit(self, transport):
        """Issue but do NOT accept — provisional credentials fail the gate."""
        await _enable_gate(transport)
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, _TYPE, issuer_address=_ISSUER
        )
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        assert cred_id  # the credential exists, just isn't accepted yet

        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_credential_belonging_to_a_different_sender_does_not_admit(self, transport):
        """A stolen/borrowed CredentialID must not admit an impersonator —
        the credential's subject must match the ACTUAL sender."""
        await _enable_gate(transport)
        await _accepted_kyc_credential(transport)
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)

        await _fund(transport, _OUTSIDER)
        r = await send_gated_payment(
            transport, "sOUTSIDER", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_OUTSIDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_expired_credential_does_not_admit(self, transport):
        await _enable_gate(transport)
        await _fund(transport, _SUBJECT)
        # Set the sim clock forward, then mint a credential already expired
        # relative to a LATER read — simplest: create with expiration in the
        # future-of-creation but past-of-check by advancing the clock after.
        far_future_create = transport._dry_clock  # avoid temBAD_EXPIRATION at create
        await create_credential(
            transport, "sISSUER", _SUBJECT, _TYPE,
            expiration=far_future_create + 100, issuer_address=_ISSUER,
        )
        await accept_credential(
            transport, "sSUBJECT", _ISSUER, _TYPE, subject_address=_SUBJECT
        )
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)

        # Advance the sim clock PAST the credential's expiration.
        transport._dry_clock = far_future_create + 200

        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_non_matching_credential_type_does_not_admit(self, transport):
        """The credential is valid and belongs to the sender, but the treasury
        never authorized THIS (issuer, type) pair."""
        await _enable_gate(transport)
        await _accepted_kyc_credential(transport)
        # Authorize a DIFFERENT credential type than the one the subject holds.
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, "region-eu", wallet_address=_TREASURY
        )
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)

        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_authorize_credentials_duplicate_rejected(self, transport):
        await _enable_gate(transport)
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        r = await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "tecDUPLICATE"

    @pytest.mark.asyncio
    async def test_unauthorize_credentials_is_the_compensator(self, transport):
        await _enable_gate(transport)
        await _accepted_kyc_credential(transport)
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)

        revoke = await unauthorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        assert revoke.success is True

        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_revoking_nonexistent_credential_preauth_rejected(self, transport):
        await _enable_gate(transport)
        r = await unauthorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_address_and_credential_paths_are_independent(self, transport):
        """Revoking the address preauth must not touch the credential preauth."""
        await _enable_gate(transport)
        await _accepted_kyc_credential(transport)
        await authorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )
        await authorize_deposit_credential(
            transport, "sTREASURY", _ISSUER, _TYPE, wallet_address=_TREASURY
        )
        await unauthorize_deposit_address(
            transport, "sTREASURY", _SENDER, wallet_address=_TREASURY
        )

        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        r = await send_gated_payment(
            transport, "sSUBJECT", _TREASURY, "10",
            credential_ids=[cred_id], sender_address=_SUBJECT,
        )
        assert r.success is True


# ── (d) DepositPreauth "exactly one" + CredentialIDs local validation ──────


class TestLocalValidationParity:
    @pytest.mark.asyncio
    async def test_deposit_preauth_requires_exactly_one_field(self, transport):
        await _fund(transport, _TREASURY)
        none_set = await transport.submit_deposit_preauth("sTREASURY")
        assert none_set.success is False
        assert none_set.result_code == "local_error"

        both_set = await transport.submit_deposit_preauth(
            "sTREASURY", authorize=_SENDER, unauthorize=_SENDER
        )
        assert both_set.success is False
        assert both_set.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_credential_ids_empty_list_rejected(self, transport):
        await _enable_gate(transport)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10",
            credential_ids=[], sender_address=_SENDER,
        )
        assert r.success is False
        assert r.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_credential_ids_over_eight_rejected(self, transport):
        await _enable_gate(transport)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10",
            credential_ids=[f"{'A' * 63}{i}" for i in range(9)],
            sender_address=_SENDER,
        )
        assert r.success is False
        assert r.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_credential_ids_duplicates_rejected(self, transport):
        await _enable_gate(transport)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "10",
            credential_ids=["A" * 64, "A" * 64], sender_address=_SENDER,
        )
        assert r.success is False
        assert r.result_code == "local_error"

    @pytest.mark.asyncio
    async def test_authorize_credentials_over_eight_rejected(self, transport):
        await _enable_gate(transport)
        pairs = [(_ISSUER, f"type-{i}") for i in range(9)]
        r = await transport.submit_deposit_preauth(
            "sTREASURY", authorize_credentials=pairs, wallet_address=_TREASURY
        )
        assert r.success is False
        assert r.result_code == "local_error"


# ── (e) sub-reserve exemption ────────────────────────────────────────────


class TestSubReserveExemption:
    @pytest.mark.asyncio
    async def test_small_payment_admitted_when_destination_is_sub_reserve(self, transport):
        # A destination that never got faucet-funded has NO tracked balance
        # entry -> treated as 0 drops, at/below the base reserve.
        await enable_deposit_auth(transport, "sTREASURY", wallet_address=_TREASURY)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "1", sender_address=_SENDER,
        )
        assert r.success is True

    @pytest.mark.asyncio
    async def test_exemption_does_not_cover_a_funded_destination(self, transport):
        # Once the treasury is funded well above reserve, the same tiny
        # payment from a non-preauthorized sender is blocked again.
        await _enable_gate(transport)  # funds the treasury to 1000 XRP
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "1", sender_address=_SENDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_exemption_does_not_cover_a_payment_above_the_reserve(self, transport):
        await enable_deposit_auth(transport, "sTREASURY", wallet_address=_TREASURY)
        await _fund(transport, _SENDER)
        r = await send_gated_payment(
            transport, "sSENDER", _TREASURY, "5", sender_address=_SENDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"


# ── (f) get_credential_id ────────────────────────────────────────────────


class TestGetCredentialId:
    @pytest.mark.asyncio
    async def test_resolves_after_accept(self, transport):
        await _accepted_kyc_credential(transport)
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        assert cred_id
        assert len(cred_id) == 64

    @pytest.mark.asyncio
    async def test_empty_when_no_credential_exists(self, transport):
        cred_id = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        assert cred_id == ""

    @pytest.mark.asyncio
    async def test_stable_across_repeated_reads(self, transport):
        await _accepted_kyc_credential(transport)
        first = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        second = await get_credential_id(transport, _SUBJECT, _ISSUER, _TYPE)
        assert first == second


# ── (g) handlers: the full module flow end-to-end ───────────────────────


class TestHandlersFullFlow:
    @pytest.mark.asyncio
    async def test_full_flow_through_handlers(self):
        from rich.console import Console

        from xrpl_lab.handlers import (
            handle_accept_credential,
            handle_authorize_kyc_credential,
            handle_authorize_sender_address,
            handle_authorize_sender_address_duplicate,
            handle_create_credential,
            handle_create_sender_wallet,
            handle_create_subject_wallet,
            handle_create_uncredentialed_wallet,
            handle_enable_deposit_auth,
            handle_preauthorize_self_expect_fail,
            handle_send_kyc_payment,
            handle_send_outsider_payment_expect_blocked,
            handle_send_sender_payment,
            handle_send_sender_payment_expect_blocked,
            handle_unauthorize_sender_address,
            handle_unauthorize_sender_address_duplicate,
        )
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.runtime import _SecretValue
        from xrpl_lab.state import LabState

        console = Console(quiet=True)
        t = DryRunTransport()
        state = LabState(network="dry-run")
        state.wallet_address = _TREASURY
        ctx: dict = {
            "module_id": "deposit_gate_101",
            "wallet_seed": _SecretValue("sTREASURY"),
        }
        await t.fund_from_faucet(_TREASURY)

        def step(action: str, **args) -> ModuleStep:
            return ModuleStep(text="", action=action, action_args=args)

        # Step 3: enable Deposit Authorization.
        ctx = await handle_enable_deposit_auth(
            step("enable_deposit_auth"), state, t, "sTREASURY", ctx, console
        )
        assert ctx.get("deposit_auth_enabled") is True

        # Step 4: create the sender.
        ctx = await handle_create_sender_wallet(
            step("create_sender_wallet"), state, t, "sTREASURY", ctx, console
        )
        assert ctx.get("sender_address")

        # Step 5: blocked.
        ctx = await handle_send_sender_payment_expect_blocked(
            step("send_sender_payment_expect_blocked", amount="10"),
            state, t, "sTREASURY", ctx, console,
        )
        assert ctx["failed_txids"][-1]["result_code"] == "tecNO_PERMISSION"

        # Step 6: self-preauth fails.
        ctx = await handle_preauthorize_self_expect_fail(
            step("preauthorize_self_expect_fail"), state, t, "sTREASURY", ctx, console
        )
        assert ctx["failed_txids"][-1]["result_code"] == "temCANNOT_PREAUTH_SELF"

        # Step 7: authorize by address.
        ctx = await handle_authorize_sender_address(
            step("authorize_sender_address"), state, t, "sTREASURY", ctx, console
        )
        assert ctx["txids"]

        # Step 8: duplicate.
        ctx = await handle_authorize_sender_address_duplicate(
            step("authorize_sender_address_duplicate"), state, t, "sTREASURY", ctx, console
        )
        assert ctx["failed_txids"][-1]["result_code"] == "tecDUPLICATE"

        # Step 9: sender's payment now lands.
        txids_before = len(ctx["txids"])
        ctx = await handle_send_sender_payment(
            step("send_sender_payment", amount="10"), state, t, "sTREASURY", ctx, console
        )
        assert len(ctx["txids"]) == txids_before + 1

        # Step 10-12: KYC'd subject wallet + credential create/accept (reused).
        ctx = await handle_create_subject_wallet(
            step("create_subject_wallet"), state, t, "sTREASURY", ctx, console
        )
        ctx = await handle_create_credential(
            step("create_credential", credential_type="kyc-deposit"),
            state, t, "sTREASURY", ctx, console,
        )
        assert ctx["credential_type"] == "kyc-deposit"
        ctx = await handle_accept_credential(
            step("accept_credential"), state, t, "sTREASURY", ctx, console
        )

        # Step 13: authorize by credential.
        ctx = await handle_authorize_kyc_credential(
            step("authorize_kyc_credential"), state, t, "sTREASURY", ctx, console
        )

        # Step 14: KYC'd payment lands.
        txids_before = len(ctx["txids"])
        ctx = await handle_send_kyc_payment(
            step("send_kyc_payment", amount="10"), state, t, "sTREASURY", ctx, console
        )
        assert len(ctx["txids"]) == txids_before + 1

        # Step 15-16: outsider stays blocked.
        ctx = await handle_create_uncredentialed_wallet(
            step("create_uncredentialed_wallet"), state, t, "sTREASURY", ctx, console
        )
        ctx = await handle_send_outsider_payment_expect_blocked(
            step("send_outsider_payment_expect_blocked", amount="10"),
            state, t, "sTREASURY", ctx, console,
        )
        assert ctx["failed_txids"][-1]["result_code"] == "tecNO_PERMISSION"

        # Step 17-18: revoke, then revoke again.
        ctx = await handle_unauthorize_sender_address(
            step("unauthorize_sender_address"), state, t, "sTREASURY", ctx, console
        )
        ctx = await handle_unauthorize_sender_address_duplicate(
            step("unauthorize_sender_address_duplicate"), state, t, "sTREASURY", ctx, console
        )
        assert ctx["failed_txids"][-1]["result_code"] == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_send_kyc_payment_without_credential_is_a_guarded_noop(self):
        """No credential in context -> the handler refuses to guess an id."""
        from rich.console import Console

        from xrpl_lab.handlers import handle_send_kyc_payment
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        console = Console(quiet=True)
        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address=_TREASURY)
        ctx: dict = {"module_id": "deposit_gate_101"}
        step = ModuleStep(text="", action="send_kyc_payment", action_args={})
        result_ctx = await handle_send_kyc_payment(step, state, t, "sTREASURY", ctx, console)
        assert "txids" not in result_ctx


# ── (h) module lints clean + pins its confirmed kb_source ───────────────


class TestDepositGateModule:
    def test_lints_clean(self):
        issues = lint_module_file(_MODULE_PATH)
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"deposit_gate_101 lint errors: {errors}"

    def test_frontmatter_pins_kb_source_and_prereq(self):
        mod = parse_module(_MODULE_PATH.read_text(encoding="utf-8"))
        assert mod.id == "deposit_gate_101"
        assert mod.track == "identity"
        # Confirmed against the xrpl-knowledge KB capabilities table
        # ("Deposit-auth + preauth-by-credential gating").
        assert mod.kb_source == "deposit-auth-credential-preauth"
        assert "credentials_101" in mod.requires
