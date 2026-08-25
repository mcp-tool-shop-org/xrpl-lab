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
from xrpl_lab.linter import lint_module_file, lint_module_text
from xrpl_lab.modules import _ACTION_RE, _STEP_RE, parse_module
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


async def _run_shipped_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, DryRunTransport]:
    """Run ``modules/token_escrow_101.md`` end-to-end offline through the runner.

    Returns the captured console text and the transport, so a caller can assert
    on what the learner SAW as well as on the resulting ledger state.
    """
    import io

    import xrpl_lab.runner as runner_mod
    import xrpl_lab.state as state_mod
    from xrpl_lab.state import LabState

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr(runner_mod, "load_state", lambda: LabState())

    text = (
        Path(__file__).parent.parent / "modules" / "token_escrow_101.md"
    ).read_text(encoding="utf-8")

    buf = io.StringIO()
    console = Console(file=buf, no_color=True, width=120)
    monkeypatch.setattr(console, "input", lambda _p="": "")

    transport = DryRunTransport()
    ok = await runner_mod.run_module(
        parse_module(text), transport, dry_run=True, console=console
    )
    assert ok is True
    return buf.getvalue(), transport


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
            cancel_after=None, finish_after=FINISH, source_address=HOLDER,
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


class TestOneActionPerStep:
    """(g) Regression guard for the silently-dropped-action defect.

    ``parse_module`` binds a step's action with ``_ACTION_RE.search()`` — the
    FIRST match in a heading's body wins and any later action comment under the
    same heading is discarded with no warning. token_escrow_101 shipped a
    Step 6 that declared BOTH ``set_trust_line`` and ``issue_token``; only the
    trust line ran, so the holder never received the 100 GLD the lesson text
    promises and the module's OWN happy path failed ``tecUNFUNDED`` at
    EscrowCreate ("Cannot escrow 50 GLD — the source holds only 0") on every
    run. The fix splits the step in two, matching the curriculum's
    one-action-per-heading convention (cf. clawback_101 Step 11/12).
    """

    def test_module_parses_both_trust_line_and_issue_token(self):
        """Both actions survive parsing as separate steps.

        This is the direct structural assertion: before the split, no step in
        the parsed module carried ``issue_token`` at all.
        """
        text = (
            Path(__file__).parent.parent / "modules" / "token_escrow_101.md"
        ).read_text(encoding="utf-8")
        actions = [s.action for s in parse_module(text).steps if s.action]

        assert "issue_token" in actions, (
            "issue_token was parsed away — the holder never receives GLD"
        )
        assert "set_trust_line" in actions
        # Order matters: the trust line must exist before the issuer can send.
        assert actions.index("set_trust_line") < actions.index("issue_token")
        # And the holder must be funded before the escrow is attempted.
        assert actions.index("issue_token") < actions.index("create_token_escrow")

    def test_no_curriculum_step_declares_two_actions(self):
        """No module in the curriculum hides a second action under one heading.

        This is the defect-class guard: token_escrow_101 was the only instance
        across all 32 modules, and this keeps it that way.
        """
        modules_dir = Path(__file__).parent.parent / "modules"
        offenders: list[str] = []
        for md in sorted(modules_dir.glob("*.md")):
            parts = _STEP_RE.split(md.read_text(encoding="utf-8"))
            for i in range(1, len(parts), 2):
                body = parts[i + 1] if i + 1 < len(parts) else ""
                names = [n for n, _ in _ACTION_RE.findall(body)]
                if len(names) > 1:
                    offenders.append(f"{md.name} '{parts[i].strip()}': {names}")
        assert not offenders, f"steps with multiple actions: {offenders}"

    def test_linter_flags_a_two_action_step(self):
        """The linter now catches this shape instead of passing it silently.

        Before this rule, a module with two actions under one heading linted
        completely clean — which is why the defect shipped.
        """
        text = (
            "---\n"
            "id: two_action\ntitle: Two Action\ntime: 1 min\nlevel: beginner\n"
            "track: tokens\nsummary: fixture\n"
            "---\n\n"
            "## Step 1: Do two things\n\n"
            "<!-- action: set_trust_line currency=GLD limit=1000 -->\n\n"
            "<!-- action: issue_token currency=GLD amount=100 -->\n"
        )
        errors = [i for i in lint_module_text(text, filename="two_action.md")
                  if i.level == "error"]
        assert len(errors) == 1, f"expected one error, got {[str(e) for e in errors]}"
        assert "issue_token" in errors[0].message
        assert "only the first" in errors[0].message

    def test_linter_accepts_one_action_per_step(self):
        """The same two actions, split across two headings, lint clean."""
        text = (
            "---\n"
            "id: one_action\ntitle: One Action\ntime: 1 min\nlevel: beginner\n"
            "track: tokens\nsummary: fixture\n"
            "---\n\n"
            "## Step 1: Trust\n\n"
            "<!-- action: set_trust_line currency=GLD limit=1000 -->\n\n"
            "## Step 2: Receive\n\n"
            "<!-- action: issue_token currency=GLD amount=100 -->\n"
        )
        errors = [i for i in lint_module_text(text, filename="one_action.md")
                  if i.level == "error"]
        assert not errors, f"unexpected errors: {[str(e) for e in errors]}"


class TestModuleEndToEnd:
    """(h) Drive the SHIPPED module through the runner, not a hand-built one.

    The unit tests in :class:`TestHappyPath` pass distinct HOLDER/RECIPIENT
    addresses straight to the action functions, so they never exercised the
    authored markdown — which is why the dropped ``issue_token`` went unnoticed.
    This drives ``modules/token_escrow_101.md`` itself.

    Scope note (superseded): this class used to document the module's closing
    "recipient balance rose by 50" check as unassertable offline, because
    ``submit_trust_set`` keyed every line by ``_address_from_seed`` — which
    collapses all seeds to ``_DRY_RUN_WALLET_ADDRESS`` — so the holder and the
    recipient shared ONE trust-line bucket, and escrowing 50 GLD out of it and
    crediting it back at EscrowFinish netted zero. ``submit_trust_set`` now
    takes the same ``wallet_address`` hint the rest of the transport already
    used (cf. ``submit_token_escrow_create``'s ``source_address``), so the two
    parties are distinct accounts offline and the checkpoint is a real
    assertion here — see :meth:`test_shipped_module_checkpoint_passes`.
    """

    @pytest.mark.asyncio
    async def test_shipped_module_escrow_is_funded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out, _ = await _run_shipped_module(tmp_path, monkeypatch)

        # The dropped step actually ran.
        assert "Issuing 100 GLD" in out, "issue_token never executed"

        # The escrow is funded — this is the exact failure the defect caused.
        assert "tecUNFUNDED" not in out, (
            "EscrowCreate hit tecUNFUNDED — the holder was never issued the token"
        )
        assert "the source holds only 0" not in out
        assert "Token escrow created" in out, "EscrowCreate did not succeed"
        assert "Token escrow finished" in out, "EscrowFinish did not succeed"

    @pytest.mark.asyncio
    async def test_shipped_module_checkpoint_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The closing ``verify_token_moved`` checkpoint does not FALSE-FAIL offline.

        Every step of this module succeeded in ``--dry-run`` (EscrowCreate and
        EscrowFinish both returned tesSUCCESS) and the learner still got a red
        ✗ on the last line, which reads as "the lesson failed". The cause was
        not the lesson: ``submit_trust_set`` keyed the holder's line and the
        recipient's line by the seed-collapsed address, so both parties shared
        one bucket, and escrowing 50 GLD out of it then crediting it back on
        finish left the balance exactly where it started.
        """
        out, transport = await _run_shipped_module(tmp_path, monkeypatch)

        # The precise false failure this guards against.
        assert "changed by 0, expected" not in out, (
            "the closing checkpoint false-failed: the recipient's balance did "
            "not move because holder and recipient share one trust-line bucket"
        )
        # No checkpoint failure of ANY shape on the closing verify.
        assert "✗" not in out, (
            f"module reported a failed check in dry-run: "
            f"{[ln for ln in out.splitlines() if '✗' in ln]}"
        )
        assert "Recipient received 50 GLD (balance 0 -> 50)" in out
        assert "Token moved — the escrowed IOU is now the recipient's." in out

        # Root cause, asserted structurally rather than through the console:
        # the holder and the recipient are DISTINCT accounts offline, each
        # holding 50 GLD of the same issuer after the escrow is finished.
        buckets = {
            addr: [tl for tl in lines if tl.currency == "GLD"]
            for addr, lines in transport._trust_lines.items()
        }
        gld_holders = {addr: ls[0].balance for addr, ls in buckets.items() if ls}
        assert len(gld_holders) == 2, (
            f"expected two distinct GLD accounts (holder + recipient), got "
            f"{gld_holders}"
        )
        assert sorted(gld_holders.values()) == ["50", "50"], (
            f"the escrowed 50 GLD did not split holder/recipient: {gld_holders}"
        )
