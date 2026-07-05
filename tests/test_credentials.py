"""Tests for the Credentials (XLS-70) vertical slice — transport, actions,
handlers, and the credentials_101 module.

FC-002 — the two-party credential lifecycle: an issuer creates a PROVISIONAL
credential about a subject; only the subject can accept it (which moves the
owner reserve to the subject); a verify reads it back as VALID only AFTER
accept; either party can delete it to reclaim the reserve. The dry-run transport
models all of this offline, keyed by the explicit (subject, issuer, type_hex).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.credentials import (
    _type_to_hex,
    accept_credential,
    create_credential,
    delete_credential,
    verify_credential,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport

# Distinct dry-run addresses for the two parties. The dry-run transport keys
# credentials by the EXPLICIT subject/issuer passed in (every seed collapses to
# one synthetic address), so these must be different to model two parties.
_ISSUER = "rIssuerAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_SUBJECT = "rSubjectBBBBBBBBBBBBBBBBBBBBBBBBBB"
_UNFUNDED = "rUnfundedCCCCCCCCCCCCCCCCCCCCCCCCC"


@pytest.fixture
def transport():
    return DryRunTransport()


async def _fund(transport, address):
    await transport.fund_from_faucet(address)


# ── (a) create against an unfunded subject → tecNO_TARGET ─────────────────


class TestUnfundedSubject:
    @pytest.mark.asyncio
    async def test_create_unfunded_subject_no_target(self, transport):
        # Subject was never funded → tecNO_TARGET.
        r = await create_credential(
            transport, "sISSUER", _UNFUNDED, "over21", issuer_address=_ISSUER
        )
        assert r.success is False
        assert r.result_code == "tecNO_TARGET"

    @pytest.mark.asyncio
    async def test_create_funded_subject_succeeds(self, transport):
        await _fund(transport, _SUBJECT)
        r = await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        assert r.success is True
        assert r.txid != ""


# ── (b) duplicate → tecDUPLICATE ──────────────────────────────────────────


class TestDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_credential_rejected(self, transport):
        await _fund(transport, _SUBJECT)
        r1 = await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        assert r1.success is True
        r2 = await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        assert r2.success is False
        assert r2.result_code == "tecDUPLICATE"


# ── (c) only the subject can accept ───────────────────────────────────────


class TestSubjectOnlyAccept:
    @pytest.mark.asyncio
    async def test_issuer_cannot_accept(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        # Issuer tries to accept naming ITSELF as the acting subject → no
        # matching provisional credential under the issuer → rejected.
        r = await accept_credential(
            transport, "sISSUER", _ISSUER, "over21", subject_address=_ISSUER
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_other_party_cannot_accept(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        other = "rOtherDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
        r = await accept_credential(
            transport, "sOTHER", _ISSUER, "over21", subject_address=other
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_subject_can_accept(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        r = await accept_credential(
            transport, "sSUBJECT", _ISSUER, "over21", subject_address=_SUBJECT
        )
        assert r.success is True


# ── (d) accept transfers the reserve to the subject ───────────────────────


class TestReserveMovesOnAccept:
    @pytest.mark.asyncio
    async def test_reserve_moves_issuer_to_subject(self, transport):
        await _fund(transport, _SUBJECT)
        # Provisional: the ISSUER holds the owner reserve.
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        assert transport._owner_counts.get(_ISSUER, 0) == 1
        assert transport._owner_counts.get(_SUBJECT, 0) == 0
        # Accept: the reserve moves from the issuer to the subject.
        r = await accept_credential(
            transport, "sSUBJECT", _ISSUER, "over21", subject_address=_SUBJECT
        )
        assert r.success is True
        assert transport._owner_counts.get(_ISSUER, 0) == 0
        assert transport._owner_counts.get(_SUBJECT, 0) == 1


# ── (e) verify records valid only AFTER accept (not while provisional) ────


class TestVerifyValidOnlyAfterAccept:
    @pytest.mark.asyncio
    async def test_provisional_not_valid(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        v = await verify_credential(transport, _SUBJECT, _ISSUER, "over21")
        # Found on-ledger, but NOT valid — it's provisional.
        assert v.found is True
        assert v.passed is False
        assert any("PROVISIONAL" in f for f in v.failures)

    @pytest.mark.asyncio
    async def test_accepted_is_valid(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        await accept_credential(
            transport, "sSUBJECT", _ISSUER, "over21", subject_address=_SUBJECT
        )
        v = await verify_credential(transport, _SUBJECT, _ISSUER, "over21")
        assert v.found is True
        assert v.passed is True
        assert v.credential is not None and v.credential.accepted is True

    @pytest.mark.asyncio
    async def test_missing_credential_not_found(self, transport):
        v = await verify_credential(transport, _SUBJECT, _ISSUER, "over21")
        assert v.found is False
        assert v.passed is False


# ── delete reclaims the reserve (revocation) ──────────────────────────────


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_after_accept_frees_subject_reserve(self, transport):
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        await accept_credential(
            transport, "sSUBJECT", _ISSUER, "over21", subject_address=_SUBJECT
        )
        assert transport._owner_counts.get(_SUBJECT, 0) == 1
        r = await delete_credential(
            transport, "sSUBJECT", _ISSUER, _SUBJECT, "over21",
            wallet_address=_SUBJECT,
        )
        assert r.success is True
        assert transport._owner_counts.get(_SUBJECT, 0) == 0
        # Gone — a subsequent verify no longer finds it.
        v = await verify_credential(transport, _SUBJECT, _ISSUER, "over21")
        assert v.found is False


# ── type hex-encoding helper ──────────────────────────────────────────────


class TestTypeToHex:
    def test_plaintext_is_hex_encoded(self):
        assert _type_to_hex("over21") == "6F7665723231"
        assert _type_to_hex("kyc") == "6B7963"

    def test_existing_hex_passes_through(self):
        assert _type_to_hex("6F7665723231") == "6F7665723231"


# ── (f) linter accepts the module ─────────────────────────────────────────


class TestCredentialsModule:
    def test_lints_clean(self):
        issues = lint_module_file(
            Path(__file__).parent.parent / "modules" / "credentials_101.md"
        )
        assert not [i for i in issues if i.level == "error"], (
            f"credentials_101 has lint errors: "
            f"{[str(i) for i in issues if i.level == 'error']}"
        )


# ── (g) verify handler records via _record_verification on both paths ─────


class TestVerifyHandlerRecords:
    @pytest.mark.asyncio
    async def test_records_failure_when_prereqs_missing(self, transport):
        """Missing subject/issuer → the verify handler records a FAILED
        verification (honest unverified), not an invisible skip."""
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_credential
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        state = LabState(network="dry-run", wallet_address="")
        context: dict = {}  # no credential_subject / subject_address
        step = ModuleStep(text="", action="verify_credential", action_args={})
        await handle_verify_credential(
            step, state, transport, "", context, Console()
        )
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_credential"
        assert recs[0]["passed"] is False
        assert recs[0]["failures"]

    @pytest.mark.asyncio
    async def test_records_success_after_accept(self, transport):
        """A valid accepted credential → the verify handler records passed=True."""
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_credential
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, "over21", issuer_address=_ISSUER
        )
        await accept_credential(
            transport, "sSUBJECT", _ISSUER, "over21", subject_address=_SUBJECT
        )

        state = LabState(network="dry-run", wallet_address=_ISSUER)
        context = {
            "credential_type": "over21",
            "credential_issuer": _ISSUER,
            "subject_address": _SUBJECT,
        }
        step = ModuleStep(text="", action="verify_credential", action_args={})
        await handle_verify_credential(
            step, state, transport, "", context, Console()
        )
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_credential"
        assert recs[0]["passed"] is True
        assert recs[0]["failures"] == []
