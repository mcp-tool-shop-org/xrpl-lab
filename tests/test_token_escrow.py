"""Tests for Token Escrow (XLS-85) — FC-001, the payments-track IOU-escrow module.

XLS-85 (TokenEscrow amendment, mainnet-live 2026-02-12) extends Escrow beyond
XRP so an ISSUED currency (IOU) can be time-locked. Three hard preconditions the
network enforces — and this suite pins each against the offline dry-run
transport so a dry-run "pass" never masks a testnet failure:

  (a) issuer opt-in is MANDATORY: without ``asfAllowTrustLineLocking`` on the
      issuer, ``EscrowCreate`` for that IOU fails ``tecNO_PERMISSION``;
  (b) the token's ISSUER cannot be the escrow SOURCE — an issuer escrowing its
      own token as sender fails ``tecNO_PERMISSION``;
  (c) every token escrow MUST carry a ``CancelAfter`` (unlike XRP, there is no
      open-ended token escrow) — a missing CancelAfter is rejected;
  (d) happy path: opt-in → holder escrows N IOU to a recipient → recipient
      finishes → the recipient's issued balance increased by N;
  (e) the module lints clean;
  (f) the verify handler records via ``_record_verification`` on BOTH the
      success path and the missing-prerequisite path (the honest-pack contract).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.actions.token_escrow import (
    create_token_escrow,
    finish_escrow,
    set_allow_trustline_locking,
    verify_token_moved,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.base import TrustLineInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# Ripple-epoch times for the deterministic offline clock. CANCEL is far enough
# out that the default far-future dry clock makes a fresh escrow immediately
# finishable (the happy path never waits on a wall clock).
CANCEL = 950_000_000
FINISH = 900_000_000

ISSUER = "rISSUER00000000000000000000000"
HOLDER = "rHOLDER00000000000000000000000"
RECIPIENT = "rRECIP000000000000000000000000"
CUR = "GLD"


def _seed_holding(transport: DryRunTransport, address: str, value: str) -> None:
    """Give *address* a live GLD trust line holding *value* of the issuer's token."""
    transport._trust_lines.setdefault(address, []).append(
        TrustLineInfo(account=address, peer=ISSUER, currency=CUR, balance=value, limit="1000")
    )


class TestIssuerOptInMandatory:
    @pytest.mark.asyncio
    async def test_escrow_without_optin_fails_no_permission(self):
        """(a) Holder escrows the IOU but the issuer never set
        asfAllowTrustLineLocking → tecNO_PERMISSION on EscrowCreate."""
        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        r = await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=HOLDER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"
        assert "AllowTrustLineLocking" in r.error or "opt" in r.error.lower()

    @pytest.mark.asyncio
    async def test_escrow_after_optin_succeeds(self):
        """With the issuer opted in first, the same escrow now succeeds."""
        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        opt = await set_allow_trustline_locking(t, "sISSUER", ISSUER)
        assert opt.success is True
        r = await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=HOLDER,
        )
        assert r.success is True
        assert r.txid != ""


class TestIssuerCannotBeSource:
    @pytest.mark.asyncio
    async def test_issuer_as_source_fails_no_permission(self):
        """(b) The token issuer escrowing its OWN token as sender →
        tecNO_PERMISSION, even with opt-in set."""
        t = DryRunTransport()
        await set_allow_trustline_locking(t, "sISSUER", ISSUER)
        # source_address == the issuer of the escrowed token.
        r = await create_token_escrow(
            t, "sISSUER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=ISSUER,
        )
        assert r.success is False
        assert r.result_code == "tecNO_PERMISSION"
        assert "issuer" in r.error.lower() and "source" in r.error.lower()


class TestCancelAfterMandatory:
    @pytest.mark.asyncio
    async def test_missing_cancel_after_rejected(self):
        """(c) A token escrow with no CancelAfter is rejected — unlike XRP,
        there is no open-ended token escrow."""
        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        await set_allow_trustline_locking(t, "sISSUER", ISSUER)
        r = await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=None, source_address=HOLDER,
        )
        assert r.success is False
        assert "CancelAfter" in r.error
        # A local pre-submission rejection (never reaches the ledger).
        assert r.result_code in ("local_error", "temMALFORMED")


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_optin_escrow_finish_credits_recipient(self):
        """(d) opt-in → holder escrows 50 GLD → recipient finishes → the
        recipient's GLD balance increased by 50 (net of any transfer fee; the
        demo is fee-free, so exactly 50)."""
        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        _seed_holding(t, RECIPIENT, "0")  # recipient trusts the issuer, holds 0
        await set_allow_trustline_locking(t, "sISSUER", ISSUER)

        # Holder locks 50 GLD to the recipient.
        r = await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=HOLDER,
        )
        assert r.success is True

        # Holder's balance dropped by the locked amount (50 GLD moved into escrow).
        holder_line = next(
            tl for tl in await t.get_trust_lines(HOLDER)
            if tl.currency == CUR
        )
        assert holder_line.balance == "50"

        # Recover the create-sequence and finish the escrow.
        escrows = await t.get_escrows(HOLDER)
        assert len(escrows) == 1
        seq = escrows[0].sequence
        assert seq != 0

        fin = await finish_escrow(t, "sRECIP", HOLDER, seq)
        assert fin.success is True

        # Recipient's GLD balance rose by exactly 50 (fee-free demo).
        recip_line = next(
            tl for tl in await t.get_trust_lines(RECIPIENT)
            if tl.currency == CUR
        )
        assert recip_line.balance == "50"

    @pytest.mark.asyncio
    async def test_verify_token_moved_passes_after_finish(self):
        """verify_token_moved confirms the recipient's balance rose by the
        escrowed amount."""
        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        _seed_holding(t, RECIPIENT, "0")
        await set_allow_trustline_locking(t, "sISSUER", ISSUER)
        await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=HOLDER,
        )
        seq = (await t.get_escrows(HOLDER))[0].sequence
        await finish_escrow(t, "sRECIP", HOLDER, seq)

        v = await verify_token_moved(
            t, RECIPIENT, CUR, ISSUER, before="0", expected_increase="50"
        )
        assert v.passed
        assert v.found


class TestModuleLints:
    def test_token_escrow_module_lints_clean(self):
        """(e) the authored module lints with no errors."""
        issues = lint_module_file(
            Path(__file__).parent.parent / "modules" / "token_escrow_101.md"
        )
        assert not [i for i in issues if i.level == "error"], (
            f"module lint errors: {[str(i) for i in issues if i.level == 'error']}"
        )


class TestVerifyHandlerRecords:
    """(f) the verify handler calls _record_verification on BOTH paths."""

    @pytest.mark.asyncio
    async def test_verify_handler_records_on_success(self):
        from xrpl_lab.handlers import handle_verify_token_moved
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        t = DryRunTransport()
        _seed_holding(t, HOLDER, "100")
        _seed_holding(t, RECIPIENT, "0")
        await set_allow_trustline_locking(t, "sISSUER", ISSUER)
        await create_token_escrow(
            t, "sHOLDER", CUR, ISSUER, "50", RECIPIENT,
            cancel_after=CANCEL, finish_after=FINISH, source_address=HOLDER,
        )
        seq = (await t.get_escrows(HOLDER))[0].sequence
        await finish_escrow(t, "sRECIP", HOLDER, seq)

        state = LabState(network="dry-run", wallet_address=RECIPIENT)
        context = {
            "token_escrow_recipient": RECIPIENT,
            "token_escrow_currency": CUR,
            "token_escrow_issuer": ISSUER,
            "token_balance_before": "0",
            "token_escrow_amount": "50",
        }
        step = ModuleStep(text="", action="verify_token_moved", action_args={})
        out = await handle_verify_token_moved(
            step, state, t, "", context, Console(quiet=True)
        )
        verifs = out.get("verifications", [])
        assert any(v["action"] == "verify_token_moved" for v in verifs)
        rec = next(v for v in verifs if v["action"] == "verify_token_moved")
        assert rec["passed"] is True

    @pytest.mark.asyncio
    async def test_verify_handler_records_on_missing_prereq(self):
        """No recipient/context set → the verify could not run → it records a
        FAILED verification (honest pack), not a silent skip."""
        from xrpl_lab.handlers import handle_verify_token_moved
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address="")
        context: dict = {}  # no recipient, no before-balance
        step = ModuleStep(text="", action="verify_token_moved", action_args={})
        out = await handle_verify_token_moved(
            step, state, t, "", context, Console(quiet=True)
        )
        verifs = out.get("verifications", [])
        rec = next(
            (v for v in verifs if v["action"] == "verify_token_moved"), None
        )
        assert rec is not None, "verify handler must record even when it cannot run"
        assert rec["passed"] is False
        assert rec["failures"], "a could-not-run verification must carry a failure reason"
