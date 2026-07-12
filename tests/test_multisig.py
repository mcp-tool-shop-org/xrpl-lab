"""Tests for the Multisig Treasury module (SignerListSet + multi-signed Payment).

Multi-signing is native, mainnet-live XRPL. The module puts N-of-M signer
control on a treasury account and moves funds by quorum arithmetic. This suite
pins the rules against the offline dry-run transport so a dry-run "pass" never
masks a testnet failure:

  (a) SignerListSet preflight parity (tem class): quorum cannot exceed the
      sum of the weights (temBAD_QUORUM); the account cannot list ITSELF and
      duplicates are refused (temBAD_SIGNER); weights must be positive
      (temBAD_WEIGHT); 1..32 entries; and the delete shape is exact —
      SignerQuorum=0 AND SignerEntries omitted, half a delete is temMALFORMED;
  (b) happy path: install a 2-of-3 list → the SignerList object reads back
      with the exact quorum + roster → owner reserve is charged once (and a
      replace does not double-charge);
  (c) multi-signed Payment meeting quorum validates, debits amount + the
      SCALED fee (base × (1 + signatures)), and credits the destination;
  (d) below-quorum → tefBAD_QUORUM; non-member signer → tefBAD_SIGNATURE;
      duplicate co-signature → tefBAD_SIGNATURE; no list at all →
      tefNOT_MULTI_SIGNING — and a failed attempt moves NO funds;
  (e) delete frees the reserve, reads back absent, and deleting an absent
      list is an idempotent tesSUCCESS (rippled's removeSignersFromLedger);
  (f) the module lints clean;
  (g) the verify handlers record via ``_record_verification`` on BOTH the
      success path and the missing-prerequisite path (honest-pack contract),
      and the expect-fail handler green-lights ONLY the taught tefBAD_QUORUM.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from xrpl_lab.actions.multisig import (
    delete_signer_list,
    send_multisig_payment,
    set_signer_list,
    verify_signer_list,
)
from xrpl_lab.linter import lint_module_file
from xrpl_lab.transport.dry_run import DryRunTransport

TREASURY = "rTREASURY00000000000000000000"
S1 = "rSIGNER1000000000000000000000"
S2 = "rSIGNER2000000000000000000000"
S3 = "rSIGNER3000000000000000000000"
PAYEE = "rPAYEE00000000000000000000000"

TWO_OF_THREE = [(S1, 1), (S2, 1), (S3, 1)]


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Keep handler save_state() writes inside the test sandbox."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / "home"))
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)


async def _install_two_of_three(t: DryRunTransport) -> None:
    r = await set_signer_list(t, "sTREASURY", 2, TWO_OF_THREE, TREASURY)
    assert r.success is True


class TestSignerListSetPreflight:
    """(a) tem-class parity — the dry-run rejects exactly what the network does."""

    @pytest.mark.asyncio
    async def test_quorum_above_weight_sum_rejected(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 4, TWO_OF_THREE, TREASURY)
        assert r.success is False
        assert r.result_code == "temBAD_QUORUM"
        assert "sum" in r.error.lower()

    @pytest.mark.asyncio
    async def test_owner_cannot_list_itself(self):
        t = DryRunTransport()
        r = await set_signer_list(
            t, "sTREASURY", 2, [(TREASURY, 1), (S1, 1)], TREASURY
        )
        assert r.success is False
        assert r.result_code == "temBAD_SIGNER"
        assert "own" in r.error.lower()

    @pytest.mark.asyncio
    async def test_duplicate_signer_rejected(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 2, [(S1, 1), (S1, 1)], TREASURY)
        assert r.success is False
        assert r.result_code == "temBAD_SIGNER"
        assert "duplicate" in r.error.lower()

    @pytest.mark.asyncio
    async def test_zero_weight_rejected(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 1, [(S1, 0), (S2, 1)], TREASURY)
        assert r.success is False
        assert r.result_code == "temBAD_WEIGHT"

    @pytest.mark.asyncio
    async def test_negative_quorum_rejected(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", -1, [(S1, 1)], TREASURY)
        assert r.success is False
        assert r.result_code == "temBAD_QUORUM"

    @pytest.mark.asyncio
    async def test_more_than_32_entries_rejected(self):
        t = DryRunTransport()
        roster = [(f"rSIGNER{i:03d}00000000000000000000", 1) for i in range(33)]
        r = await set_signer_list(t, "sTREASURY", 1, roster, TREASURY)
        assert r.success is False
        assert r.result_code == "temMALFORMED"

    @pytest.mark.asyncio
    async def test_bad_delete_zero_quorum_with_entries(self):
        """Delete = SignerQuorum=0 AND omit entries; only-one-half is temMALFORMED."""
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 0, [(S1, 1)], TREASURY)
        assert r.success is False
        assert r.result_code == "temMALFORMED"

    @pytest.mark.asyncio
    async def test_bad_delete_nonzero_quorum_without_entries(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 2, [], TREASURY)
        assert r.success is False
        assert r.result_code == "temMALFORMED"

    @pytest.mark.asyncio
    async def test_transport_enforces_even_when_action_layer_bypassed(self):
        """A direct transport caller can't skip the preflight (defense in depth)."""
        t = DryRunTransport()
        r = await t.submit_signer_list_set(
            "sTREASURY", 4, TWO_OF_THREE, TREASURY
        )
        assert r.success is False
        assert r.result_code == "temBAD_QUORUM"
        r2 = await t.submit_signer_list_set(
            "sTREASURY", 2, [(TREASURY, 1), (S1, 1)], TREASURY
        )
        assert r2.success is False
        assert r2.result_code == "temBAD_SIGNER"


class TestSignerListSetSuccess:
    """(b) install + read-back + reserve accounting."""

    @pytest.mark.asyncio
    async def test_install_two_of_three(self):
        t = DryRunTransport()
        r = await set_signer_list(t, "sTREASURY", 2, TWO_OF_THREE, TREASURY)
        assert r.success is True
        assert r.txid != ""
        info = await t.get_signer_list(TREASURY)
        assert info is not None
        assert info.signer_quorum == 2
        assert set(info.entries) == set(TWO_OF_THREE)

    @pytest.mark.asyncio
    async def test_install_charges_one_owner_reserve(self):
        t = DryRunTransport()
        before = t._owner_counts.get(TREASURY, 0)
        await _install_two_of_three(t)
        assert t._owner_counts.get(TREASURY, 0) == before + 1

    @pytest.mark.asyncio
    async def test_replace_is_wholesale_and_does_not_double_charge(self):
        """Every SignerListSet REPLACES the roster; the reserve stays 1."""
        t = DryRunTransport()
        await _install_two_of_three(t)
        after_first = t._owner_counts.get(TREASURY, 0)
        r = await set_signer_list(t, "sTREASURY", 1, [(S1, 2), (S2, 1)], TREASURY)
        assert r.success is True
        assert t._owner_counts.get(TREASURY, 0) == after_first
        info = await t.get_signer_list(TREASURY)
        assert info is not None
        assert info.signer_quorum == 1
        assert set(info.entries) == {(S1, 2), (S2, 1)}
        assert (S3, 1) not in info.entries  # dropped entry is GONE, not kept

    @pytest.mark.asyncio
    async def test_get_signer_list_none_for_plain_account(self):
        t = DryRunTransport()
        assert await t.get_signer_list(TREASURY) is None


class TestSignerListDelete:
    """(e) delete shape, reserve release, and idempotent delete-absent."""

    @pytest.mark.asyncio
    async def test_delete_removes_list_and_frees_reserve(self):
        t = DryRunTransport()
        await _install_two_of_three(t)
        owned = t._owner_counts.get(TREASURY, 0)
        r = await delete_signer_list(t, "sTREASURY", TREASURY)
        assert r.success is True
        assert await t.get_signer_list(TREASURY) is None
        assert t._owner_counts.get(TREASURY, 0) == owned - 1

    @pytest.mark.asyncio
    async def test_delete_absent_list_is_idempotent_success(self):
        """rippled: 'if the signer list doesn't exist we've already succeeded
        in deleting it' — tesSUCCESS, and no reserve is (un)charged."""
        t = DryRunTransport()
        before = t._owner_counts.get(TREASURY, 0)
        r = await delete_signer_list(t, "sTREASURY", TREASURY)
        assert r.success is True
        assert r.result_code == "tesSUCCESS"
        assert t._owner_counts.get(TREASURY, 0) == before


class TestMultisigPayment:
    """(c) + (d) quorum arithmetic, fee scaling, and the tef failure set."""

    async def _funded_treasury(self) -> DryRunTransport:
        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)  # 1000 XRP
        await _install_two_of_three(t)
        return t

    @pytest.mark.asyncio
    async def test_meeting_quorum_succeeds_and_moves_funds(self):
        t = await self._funded_treasury()
        before = t._balances[TREASURY]
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "10", ["sS1", "sS2"], [S1, S2],
        )
        assert r.success is True
        assert r.txid != ""
        # Fee rule: base (12 drops in the dry model) × (1 + 2 signatures).
        assert r.fee == "36"
        assert t._balances[TREASURY] == before - 10_000_000 - 36
        assert t._balances.get(PAYEE, 0) == 10_000_000

    @pytest.mark.asyncio
    async def test_below_quorum_fails_tef_bad_quorum(self):
        """One valid signature, weight 1 < quorum 2 → tefBAD_QUORUM."""
        t = await self._funded_treasury()
        before = t._balances[TREASURY]
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "10", ["sS1"], [S1],
        )
        assert r.success is False
        assert r.result_code == "tefBAD_QUORUM"
        assert "quorum" in r.error.lower()
        # A refused payment moves NO funds.
        assert t._balances[TREASURY] == before
        assert t._balances.get(PAYEE, 0) == 0

    @pytest.mark.asyncio
    async def test_no_signer_list_fails_tef_not_multi_signing(self):
        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "10", ["sS1", "sS2"], [S1, S2],
        )
        assert r.success is False
        assert r.result_code == "tefNOT_MULTI_SIGNING"

    @pytest.mark.asyncio
    async def test_non_member_signer_fails_tef_bad_signature(self):
        t = await self._funded_treasury()
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "10", ["sS1", "sSTRANGER"], [S1, PAYEE],
        )
        assert r.success is False
        assert r.result_code == "tefBAD_SIGNATURE"

    @pytest.mark.asyncio
    async def test_duplicate_cosignature_fails_tef_bad_signature(self):
        """The same signer twice cannot double its weight."""
        t = await self._funded_treasury()
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "10", ["sS1", "sS1"], [S1, S1],
        )
        assert r.success is False
        assert r.result_code == "tefBAD_SIGNATURE"

    @pytest.mark.asyncio
    async def test_weight_arithmetic_not_signer_count(self):
        """Quorum 2 with a weight-2 lead: ONE signature can meet quorum."""
        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        r = await set_signer_list(
            t, "sTREASURY", 2, [(S1, 2), (S2, 1), (S3, 1)], TREASURY
        )
        assert r.success is True
        pay = await send_multisig_payment(
            t, TREASURY, PAYEE, "5", ["sS1"], [S1],
        )
        assert pay.success is True
        # And a weight-1 junior alone still fails.
        fail = await send_multisig_payment(
            t, TREASURY, PAYEE, "5", ["sS2"], [S2],
        )
        assert fail.success is False
        assert fail.result_code == "tefBAD_QUORUM"

    @pytest.mark.asyncio
    async def test_empty_signers_rejected_locally(self):
        t = await self._funded_treasury()
        r = await send_multisig_payment(t, TREASURY, PAYEE, "10", [], [])
        assert r.success is False
        assert r.result_code == "local_error"
        assert "signer" in r.error.lower()

    @pytest.mark.asyncio
    async def test_bad_amount_rejected_with_network_shape(self):
        t = await self._funded_treasury()
        r = await send_multisig_payment(
            t, TREASURY, PAYEE, "-5", ["sS1", "sS2"], [S1, S2],
        )
        assert r.success is False
        assert r.result_code == "temBAD_AMOUNT"


class TestVerifySignerList:
    """The read-back verifier — exact-match checks and the absent mode."""

    @pytest.mark.asyncio
    async def test_verify_passes_after_install(self):
        t = DryRunTransport()
        await _install_two_of_three(t)
        v = await verify_signer_list(
            t, TREASURY, expected_quorum=2, expected_entries=TWO_OF_THREE
        )
        assert v.passed
        assert v.found
        assert v.quorum == 2

    @pytest.mark.asyncio
    async def test_verify_fails_on_quorum_mismatch(self):
        t = DryRunTransport()
        await _install_two_of_three(t)
        v = await verify_signer_list(t, TREASURY, expected_quorum=3)
        assert not v.passed
        assert any("quorum" in f.lower() for f in v.failures)

    @pytest.mark.asyncio
    async def test_verify_fails_on_roster_mismatch(self):
        t = DryRunTransport()
        await _install_two_of_three(t)
        v = await verify_signer_list(
            t, TREASURY, expected_entries=[(S1, 1), (S2, 1), (PAYEE, 1)]
        )
        assert not v.passed

    @pytest.mark.asyncio
    async def test_verify_absent_mode(self):
        t = DryRunTransport()
        v = await verify_signer_list(t, TREASURY, expect_absent=True)
        assert v.passed
        assert not v.found
        # And the inverse: a list still attached fails the absent check.
        await _install_two_of_three(t)
        v2 = await verify_signer_list(t, TREASURY, expect_absent=True)
        assert not v2.passed

    @pytest.mark.asyncio
    async def test_verify_fails_when_no_list_installed(self):
        t = DryRunTransport()
        v = await verify_signer_list(t, TREASURY, expected_quorum=2)
        assert not v.passed
        assert not v.found


class TestModuleLints:
    def test_multisig_module_lints_clean(self):
        """(f) the authored module lints with no errors."""
        issues = lint_module_file(
            Path(__file__).parent.parent / "modules" / "multisig_treasury_101.md"
        )
        assert not [i for i in issues if i.level == "error"], (
            f"module lint errors: {[str(i) for i in issues if i.level == 'error']}"
        )


class TestHandlers:
    """(g) handler-level contracts: honest-pack recording + expect-fail honesty."""

    def _handler_env(self, t: DryRunTransport):
        from xrpl_lab.runtime import _SecretValue
        from xrpl_lab.state import LabState

        state = LabState(network="dry-run", wallet_address=TREASURY)
        context = {
            "wallet_seed": _SecretValue("sTREASURY"),
            "signer_seeds": [
                _SecretValue("sS1"), _SecretValue("sS2"), _SecretValue("sS3"),
            ],
            "signer_addresses": [S1, S2, S3],
        }
        return state, context

    @pytest.mark.asyncio
    async def test_set_and_verify_signer_list_handlers(self):
        from xrpl_lab.handlers import (
            handle_set_signer_list,
            handle_verify_signer_list,
        )
        from xrpl_lab.modules import ModuleStep

        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        state, context = self._handler_env(t)
        step = ModuleStep(
            text="", action="set_signer_list",
            action_args={"quorum": "2", "weights": "1,1,1"},
        )
        out = await handle_set_signer_list(
            step, state, t, "", context, Console(quiet=True)
        )
        assert out["multisig_quorum"] == 2
        assert set(out["multisig_entries"]) == set(TWO_OF_THREE)
        assert out.get("txids"), "a successful SignerListSet must record its txid"

        vstep = ModuleStep(text="", action="verify_signer_list", action_args={})
        out = await handle_verify_signer_list(
            vstep, state, t, "", out, Console(quiet=True)
        )
        rec = next(
            v for v in out["verifications"] if v["action"] == "verify_signer_list"
        )
        assert rec["passed"] is True

    @pytest.mark.asyncio
    async def test_verify_handler_records_on_missing_prereq(self):
        """No signer list in context → the verify could not run → it records a
        FAILED verification (honest pack), not a silent skip."""
        from xrpl_lab.handlers import handle_verify_signer_list
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address="")
        context: dict = {}
        step = ModuleStep(text="", action="verify_signer_list", action_args={})
        out = await handle_verify_signer_list(
            step, state, t, "", context, Console(quiet=True)
        )
        rec = next(
            (v for v in out.get("verifications", [])
             if v["action"] == "verify_signer_list"),
            None,
        )
        assert rec is not None, "verify handler must record even when it cannot run"
        assert rec["passed"] is False
        assert rec["failures"], "a could-not-run verification must carry a reason"

    @pytest.mark.asyncio
    async def test_verify_deleted_handler_records_on_missing_prereq(self):
        from xrpl_lab.handlers import handle_verify_signer_list_deleted
        from xrpl_lab.modules import ModuleStep
        from xrpl_lab.state import LabState

        t = DryRunTransport()
        state = LabState(network="dry-run", wallet_address="")
        step = ModuleStep(
            text="", action="verify_signer_list_deleted", action_args={}
        )
        out = await handle_verify_signer_list_deleted(
            step, state, t, "", {}, Console(quiet=True)
        )
        rec = next(
            (v for v in out.get("verifications", [])
             if v["action"] == "verify_signer_list_deleted"),
            None,
        )
        assert rec is not None
        assert rec["passed"] is False

    @pytest.mark.asyncio
    async def test_payment_and_delete_handlers_full_arc(self):
        """set list → pay meeting quorum → delete → verify gone, via handlers."""
        from xrpl_lab.handlers import (
            handle_delete_signer_list,
            handle_send_multisig_payment,
            handle_set_signer_list,
            handle_verify_signer_list_deleted,
        )
        from xrpl_lab.modules import ModuleStep

        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        state, context = self._handler_env(t)
        console = Console(quiet=True)

        context = await handle_set_signer_list(
            ModuleStep(text="", action="set_signer_list",
                       action_args={"quorum": "2", "weights": "1,1,1"}),
            state, t, "", context, console,
        )
        context = await handle_send_multisig_payment(
            ModuleStep(text="", action="send_multisig_payment",
                       action_args={"amount": "10", "signer_count": "2"}),
            state, t, "", context, console,
        )
        assert context.get("multisig_payment_txid"), "quorum-met payment must record"
        # The default payee is signer 1's address; 10 XRP landed there.
        assert t._balances.get(S1, 0) == 10_000_000

        context = await handle_delete_signer_list(
            ModuleStep(text="", action="delete_signer_list", action_args={}),
            state, t, "", context, console,
        )
        assert context.get("signer_list_deleted") is True

        context = await handle_verify_signer_list_deleted(
            ModuleStep(text="", action="verify_signer_list_deleted",
                       action_args={}),
            state, t, "", context, console,
        )
        rec = next(
            v for v in context["verifications"]
            if v["action"] == "verify_signer_list_deleted"
        )
        assert rec["passed"] is True

    @pytest.mark.asyncio
    async def test_expect_fail_handler_records_taught_failure(self):
        """One signature below quorum → tefBAD_QUORUM lands in failed_txids."""
        from xrpl_lab.handlers import (
            handle_send_multisig_payment_expect_fail,
            handle_set_signer_list,
        )
        from xrpl_lab.modules import ModuleStep

        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        state, context = self._handler_env(t)
        console = Console(quiet=True)
        context = await handle_set_signer_list(
            ModuleStep(text="", action="set_signer_list",
                       action_args={"quorum": "2", "weights": "1,1,1"}),
            state, t, "", context, console,
        )
        context = await handle_send_multisig_payment_expect_fail(
            ModuleStep(text="", action="send_multisig_payment_expect_fail",
                       action_args={"signer_count": "1"}),
            state, t, "", context, console,
        )
        failed = context.get("failed_txids", [])
        assert failed, "the expect-fail step must record its failure"
        assert failed[-1]["result_code"] == "tefBAD_QUORUM"

    @pytest.mark.asyncio
    async def test_expect_fail_unexpected_success_records_real_txid_only(self):
        """If the signature set unexpectedly MEETS quorum, only a real txid is
        recorded (no {txid:'failed', success:true} shapes in the pack)."""
        from xrpl_lab.handlers import (
            handle_send_multisig_payment_expect_fail,
            handle_set_signer_list,
        )
        from xrpl_lab.modules import ModuleStep

        t = DryRunTransport()
        await t.fund_from_faucet(TREASURY)
        state, context = self._handler_env(t)
        console = Console(quiet=True)
        # Quorum 1 — a single signature MEETS quorum, so the "failure" step
        # unexpectedly succeeds.
        context = await handle_set_signer_list(
            ModuleStep(text="", action="set_signer_list",
                       action_args={"quorum": "1", "weights": "1,1,1"}),
            state, t, "", context, console,
        )
        context = await handle_send_multisig_payment_expect_fail(
            ModuleStep(text="", action="send_multisig_payment_expect_fail",
                       action_args={"signer_count": "1"}),
            state, t, "", context, console,
        )
        assert not context.get("failed_txids")
        assert context.get("txids"), "the unexpected success must record its txid"
        assert all(tx and tx != "failed" for tx in context["txids"])


class TestRegistryAndCatalog:
    """The new actions are registered and the doctor teaches the new codes."""

    def test_all_multisig_actions_registered(self):
        import xrpl_lab.handlers  # noqa: F401 — populate the registry
        from xrpl_lab.registry import is_registered

        for name in (
            "create_signer_wallets",
            "set_signer_list",
            "verify_signer_list",
            "send_multisig_payment",
            "send_multisig_payment_expect_fail",
            "delete_signer_list",
            "verify_signer_list_deleted",
        ):
            assert is_registered(name), f"action '{name}' is not registered"

    def test_doctor_explains_multisig_codes(self):
        from xrpl_lab.doctor import explain_result_code

        for code in (
            "tefBAD_QUORUM", "tefNOT_MULTI_SIGNING", "tefBAD_SIGNATURE",
            "temBAD_QUORUM", "temBAD_SIGNER", "temBAD_WEIGHT",
        ):
            info = explain_result_code(code)
            assert info["meaning"], f"{code} has no meaning"
            assert info["action"], f"{code} has no action"
            # A specific catalog entry, not the generic prefix fallback.
            assert info["action"] != "Check XRPL docs for this specific code", (
                f"{code} fell through to the generic prefix explanation"
            )


class TestRunnerSnapshotWithSecretLists:
    """The runner's step-rollback snapshot must survive a LIST of secrets.

    ``create_signer_wallets`` stores ``context['signer_seeds']`` as a list of
    ``_SecretValue`` — the first module to nest secrets inside a container.
    ``_snapshot_context`` used to hold aside only TOP-LEVEL secret values and
    deepcopy the rest, so the wrapper's anti-clone ``__reduce__`` raised
    TypeError and the module crashed at the very first step (caught by the
    end-to-end dry-run, not the unit layer). The fix copies the list itself
    (so a partial append mid-step still rolls back) while sharing the
    unclonable wrapper references.
    """

    def test_snapshot_survives_secret_list(self):
        from xrpl_lab.runner import _snapshot_context
        from xrpl_lab.runtime import _SecretValue

        s1, s2 = _SecretValue("sS1"), _SecretValue("sS2")
        context = {
            "wallet_seed": _SecretValue("sTREASURY"),
            "signer_seeds": [s1, s2],
            "signer_addresses": [S1, S2],
            "txids": ["ABC123"],
        }
        snap = _snapshot_context(context)  # would raise TypeError before the fix
        # Secret wrappers are SHARED (unclonable by design), not copied.
        assert snap["signer_seeds"][0] is s1
        assert snap["signer_seeds"][1] is s2
        assert snap["wallet_seed"] is context["wallet_seed"]
        # The list CONTAINER is copied — a partial append mid-step must not
        # leak into the snapshot (the rollback contract, same as txids).
        context["signer_seeds"].append(_SecretValue("sS3"))
        context["txids"].append("DEF456")
        assert len(snap["signer_seeds"]) == 2
        assert snap["txids"] == ["ABC123"]
