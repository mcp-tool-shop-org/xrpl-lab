"""Tests for the Permissioned Domains & Gated DEX (XLS-80 / XLS-81) vertical slice.

FC-004 — the compliance / gated-trading primitive, composed on top of credentials
(FC-002). Coverage:

  (a) create a domain → a DomainID is produced (and distinct per create);
  (b) a NON-owner modify is rejected (owner-only);
  (c) a full-replace modify that DROPS a credential excludes a previously-eligible
      account (the silent-revocation gotcha);
  (d) a CREDENTIALED account's permissioned offer succeeds;
  (e) an UN-credentialed account's permissioned offer fails (eligibility gate);
  (f) the CredentialIDs-vs-DomainID rail distinction — a held credential alone,
      referenced by DomainID, is what admits the offer (no CredentialIDs channel);
  (g) delete frees the domain (compensator);
  (h) the linter accepts the module;
  (i) the verify handlers record via _record_verification on BOTH paths.

The dry-run transport models all of this offline, keyed by the EXPLICIT
subject/issuer/owner addresses passed in (every seed collapses to one synthetic
address), so the two-plus parties are distinguishable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.actions.credentials import accept_credential, create_credential
from xrpl_lab.actions.permissioned_domains import (
    create_permissioned_offer,
    delete_permissioned_domain,
    set_permissioned_domain,
    verify_domain,
    verify_permissioned_offer,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport

_OWNER = "rOwnerAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_ISSUER = "rIssuerBBBBBBBBBBBBBBBBBBBBBBBBBB"
_SUBJECT = "rSubjectCCCCCCCCCCCCCCCCCCCCCCCCC"
_OUTSIDER = "rOutsiderDDDDDDDDDDDDDDDDDDDDDDDD"
_TYPE = "region-EU"


@pytest.fixture
def transport():
    return DryRunTransport()


async def _fund(transport, address):
    await transport.fund_from_faucet(address)


async def _accepted_credential(transport, subject=_SUBJECT, ctype=_TYPE):
    """Issue + accept a credential so *subject* is eligible for a domain listing it."""
    await _fund(transport, subject)
    await create_credential(
        transport, "sISSUER", subject, ctype, issuer_address=_ISSUER
    )
    await accept_credential(
        transport, "sSUBJECT", _ISSUER, ctype, subject_address=subject
    )


# ── (a) create a domain → DomainID ────────────────────────────────────────


class TestCreateDomain:
    @pytest.mark.asyncio
    async def test_create_yields_domain_id(self, transport):
        r = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        assert r.success is True
        assert r.domain_id != ""
        # The domain is readable back under the owner.
        domains = await transport.get_permissioned_domains(_OWNER)
        assert len(domains) == 1
        assert domains[0].domain_id == r.domain_id
        # The accepted set carries the hex-encoded credential type.
        assert domains[0].accepted_credentials == [(_ISSUER, "726567696F6E2D4555")]

    @pytest.mark.asyncio
    async def test_create_is_not_idempotent(self, transport):
        """Each (owner, sequence) yields a DISTINCT DomainID — re-running create
        makes a NEW domain, never idempotently the old one."""
        r1 = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        r2 = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        assert r1.domain_id != r2.domain_id
        assert len(await transport.get_permissioned_domains(_OWNER)) == 2

    @pytest.mark.asyncio
    async def test_create_consumes_owner_reserve(self, transport):
        assert transport._owner_counts.get(_OWNER, 0) == 0
        await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        assert transport._owner_counts.get(_OWNER, 0) == 1

    @pytest.mark.asyncio
    async def test_empty_accepted_set_rejected(self, transport):
        r = await set_permissioned_domain(
            transport, "sOWNER", [], owner_address=_OWNER
        )
        assert r.success is False
        assert r.result_code == "temMALFORMED"

    @pytest.mark.asyncio
    async def test_duplicate_accepted_entry_rejected(self, transport):
        r = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE), (_ISSUER, _TYPE)],
            owner_address=_OWNER,
        )
        assert r.success is False
        assert r.result_code == "temMALFORMED"


# ── (b) non-owner modify → rejected ───────────────────────────────────────


class TestOwnerOnlyModify:
    @pytest.mark.asyncio
    async def test_nonowner_modify_rejected(self, transport):
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        # A different account tries to modify the owner's domain.
        r = await set_permissioned_domain(
            transport, "sOUTSIDER", [(_ISSUER, "hijack")],
            domain_id=created.domain_id, owner_address=_OUTSIDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"
        # The accepted set is untouched.
        domains = await transport.get_permissioned_domains(_OWNER)
        assert domains[0].accepted_credentials == [(_ISSUER, "726567696F6E2D4555")]

    @pytest.mark.asyncio
    async def test_owner_modify_succeeds(self, transport):
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        r = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE), (_ISSUER, "kyc")],
            domain_id=created.domain_id, owner_address=_OWNER,
        )
        assert r.success is True
        domains = await transport.get_permissioned_domains(_OWNER)
        assert len(domains[0].accepted_credentials) == 2


# ── (c) full-replace drops a credential → previously-eligible excluded ─────


class TestFullReplaceRevocation:
    @pytest.mark.asyncio
    async def test_dropping_credential_excludes_eligible_account(self, transport):
        """The full-replace gotcha: a modify that drops the credential silently
        revokes access for its holders."""
        await _accepted_credential(transport)
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        did = created.domain_id

        # Before: the credentialed subject can place a permissioned offer.
        ok = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=did, wallet_address=_SUBJECT,
        )
        assert ok.success is True

        # Full-replace modify: swap to a decoy, DROPPING region-EU.
        mod = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, "region-XX")],
            domain_id=did, owner_address=_OWNER,
        )
        assert mod.success is True

        # After: the SAME subject's permissioned offer now FAILS — silently
        # revoked by the accepted-set change.
        after = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=did, wallet_address=_SUBJECT,
        )
        assert after.success is False
        assert after.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_verify_domain_flags_dropped_credential(self, transport):
        await _accepted_credential(transport)
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        did = created.domain_id
        v_before = await verify_domain(
            transport, _OWNER, did, expect_issuer=_ISSUER, expect_credential_type=_TYPE
        )
        assert v_before.passed is True

        await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, "region-XX")],
            domain_id=did, owner_address=_OWNER,
        )
        v_after = await verify_domain(
            transport, _OWNER, did, expect_issuer=_ISSUER, expect_credential_type=_TYPE
        )
        assert v_after.passed is False
        assert any("does NOT accept" in f for f in v_after.failures)


# ── (d) credentialed account's permissioned offer succeeds ────────────────


class TestCredentialedOfferSucceeds:
    @pytest.mark.asyncio
    async def test_offer_rests_when_credentialed(self, transport):
        await _accepted_credential(transport)
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        r = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, wallet_address=_SUBJECT,
        )
        assert r.success is True
        assert r.offer_sequence is not None
        # And it is verifiably resting.
        v = await verify_permissioned_offer(
            transport, _SUBJECT, r.offer_sequence, expect_placed=True
        )
        assert v.passed is True

    @pytest.mark.asyncio
    async def test_hybrid_flag_offer_also_succeeds(self, transport):
        await _accepted_credential(transport)
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        r = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, hybrid=True, wallet_address=_SUBJECT,
        )
        assert r.success is True


# ── (e) un-credentialed account's permissioned offer fails ────────────────


class TestUncredentialedOfferFails:
    @pytest.mark.asyncio
    async def test_offer_rejected_without_credential(self, transport):
        await _accepted_credential(transport)  # only the SUBJECT is credentialed
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        await _fund(transport, _OUTSIDER)
        r = await create_permissioned_offer(
            transport, "sOUTSIDER", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, wallet_address=_OUTSIDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"
        # No offer rests for the outsider.
        v = await verify_permissioned_offer(
            transport, _OUTSIDER, 999, expect_placed=False
        )
        assert v.passed is True

    @pytest.mark.asyncio
    async def test_offer_to_nonexistent_domain_rejected(self, transport):
        await _accepted_credential(transport)
        r = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id="D" * 64, wallet_address=_SUBJECT,
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"


# ── (f) CredentialIDs-vs-DomainID rail distinction ────────────────────────


class TestRailDistinction:
    @pytest.mark.asyncio
    async def test_only_a_held_credential_via_domain_admits(self, transport):
        """Eligibility is proven by holding an accepted credential the domain
        lists, referenced by DomainID — there is NO CredentialIDs channel on the
        permissioned offer. A PROVISIONAL (unaccepted) credential does not admit,
        proving it is the accepted-credential-via-DomainID rail, not a hash field."""
        # Issue but do NOT accept — provisional only.
        await _fund(transport, _SUBJECT)
        await create_credential(
            transport, "sISSUER", _SUBJECT, _TYPE, issuer_address=_ISSUER
        )
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        # Provisional credential → not eligible → offer FAILS.
        r_prov = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, wallet_address=_SUBJECT,
        )
        assert r_prov.success is False
        assert r_prov.result_code == "tecNO_PERMISSION"

        # Accept it → now eligible → offer SUCCEEDS. Nothing about the offer
        # changed except the credential's accepted state (the DomainID rail).
        await accept_credential(
            transport, "sSUBJECT", _ISSUER, _TYPE, subject_address=_SUBJECT
        )
        r_ok = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, wallet_address=_SUBJECT,
        )
        assert r_ok.success is True


# ── (g) delete frees the domain (compensator) ─────────────────────────────


class TestDeleteDomain:
    @pytest.mark.asyncio
    async def test_delete_frees_reserve_and_removes_domain(self, transport):
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        assert transport._owner_counts.get(_OWNER, 0) == 1
        r = await delete_permissioned_domain(
            transport, "sOWNER", created.domain_id, owner_address=_OWNER
        )
        assert r.success is True
        assert transport._owner_counts.get(_OWNER, 0) == 0
        assert await transport.get_permissioned_domains(_OWNER) == []

    @pytest.mark.asyncio
    async def test_nonowner_delete_rejected(self, transport):
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        r = await delete_permissioned_domain(
            transport, "sOUTSIDER", created.domain_id, owner_address=_OUTSIDER
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_rejected(self, transport):
        r = await delete_permissioned_domain(
            transport, "sOWNER", "E" * 64, owner_address=_OWNER
        )
        assert r.success is False
        assert r.result_code == "tecNO_ENTRY"


# ── (h) linter accepts the module ─────────────────────────────────────────


class TestPermissionedDomainsModule:
    def test_lints_clean(self):
        issues = lint_module_file(
            Path(__file__).parent.parent / "modules" / "permissioned_domains_101.md"
        )
        assert not [i for i in issues if i.level == "error"], (
            f"permissioned_domains_101 has lint errors: "
            f"{[str(i) for i in issues if i.level == 'error']}"
        )


# ── (i) verify handlers record via _record_verification on both paths ─────


class TestVerifyHandlersRecord:
    @pytest.mark.asyncio
    async def test_verify_domain_records_failure_when_prereqs_missing(self, transport):
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_domain
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        state = LabState(network="dry-run", wallet_address="")
        context: dict = {}  # no domain_id
        step = ModuleStep(text="", action="verify_domain", action_args={})
        await handle_verify_domain(step, state, transport, "", context, Console())
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_domain"
        assert recs[0]["passed"] is False
        assert recs[0]["failures"]

    @pytest.mark.asyncio
    async def test_verify_domain_records_success(self, transport):
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_domain
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        state = LabState(network="dry-run", wallet_address=_OWNER)
        context = {
            "domain_id": created.domain_id,
            "domain_issuer": _ISSUER,
            "domain_credential_type": _TYPE,
        }
        step = ModuleStep(text="", action="verify_domain", action_args={})
        await handle_verify_domain(step, state, transport, "", context, Console())
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_domain"
        assert recs[0]["passed"] is True
        assert recs[0]["failures"] == []

    @pytest.mark.asyncio
    async def test_verify_permissioned_offer_records_failure_when_prereqs_missing(
        self, transport
    ):
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_permissioned_offer
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        state = LabState(network="dry-run", wallet_address="")
        context: dict = {}  # no subject_address / permissioned_offer_seq
        step = ModuleStep(text="", action="verify_permissioned_offer", action_args={})
        await handle_verify_permissioned_offer(
            step, state, transport, "", context, Console()
        )
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_permissioned_offer"
        assert recs[0]["passed"] is False
        assert recs[0]["failures"]

    @pytest.mark.asyncio
    async def test_verify_permissioned_offer_records_success(self, transport):
        from rich.console import Console

        from xrpl_lab.handlers import handle_verify_permissioned_offer
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        await _accepted_credential(transport)
        created = await set_permissioned_domain(
            transport, "sOWNER", [(_ISSUER, _TYPE)], owner_address=_OWNER
        )
        placed = await create_permissioned_offer(
            transport, "sSUBJECT", "LAB", "50", _ISSUER, "XRP", "10", "",
            domain_id=created.domain_id, wallet_address=_SUBJECT,
        )
        state = LabState(network="dry-run", wallet_address=_OWNER)
        context = {
            "subject_address": _SUBJECT,
            "permissioned_offer_seq": placed.offer_sequence,
        }
        step = ModuleStep(text="", action="verify_permissioned_offer", action_args={})
        await handle_verify_permissioned_offer(
            step, state, transport, "", context, Console()
        )
        recs = context.get("verifications", [])
        assert len(recs) == 1
        assert recs[0]["action"] == "verify_permissioned_offer"
        assert recs[0]["passed"] is True
        assert recs[0]["failures"] == []
