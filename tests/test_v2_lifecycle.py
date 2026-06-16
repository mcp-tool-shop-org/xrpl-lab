"""v2.0.0 lifecycle-completion tests (f1-engine domain).

The audit found three half-told stories: a learner could ``EscrowCreate`` but
never finish/cancel (XRP locked forever), ``DIDSet`` but never ``DIDDelete``
(identity un-revocable), and ``NFTokenMint`` but never burn (reserve never
freed). v2.0.0 closes all three. This module pins the new behavior fully
offline:

  - Escrow finish + cancel: happy paths, the time-gate error paths
    (finish before FinishAfter / cancel before CancelAfter), the
    wrong/nonexistent-target path, the create-sequence capture, and the
    reserve-freed outcome.
  - DID delete: happy path + verify-gone, and delete-when-no-DID.
  - NFT burn: happy path + verify-gone + reserve-freed, and burn-nonexistent.
  - dry-run ↔ testnet PARITY: the new methods exist with the same signatures
    on both transports, and the dry-run error codes are real XRPL ``tec*``
    tokens that ``explain_result_code`` recognizes (the same teaching seam the
    create handlers use), so finish/cancel/delete/burn fail consistently.

Everything runs against ``DryRunTransport`` (no network, no ``xrpl`` client)
plus source/signature inspection of the testnet transport, so the whole module
is network-free. The testnet WRITE path's mainnet-refusal guard is pinned
separately by ``tests/test_network_safety.py`` (reflection gate).
"""

from __future__ import annotations

import inspect

import pytest

from xrpl_lab.actions.did import delete_did, verify_did_deleted
from xrpl_lab.actions.escrow import (
    cancel_escrow,
    create_escrow,
    finish_escrow,
    verify_escrow_finished,
)
from xrpl_lab.actions.nft import burn_nft, mint_nft, verify_nft_burned
from xrpl_lab.doctor import explain_result_code
from xrpl_lab.transport.base import Transport
from xrpl_lab.transport.dry_run import _DRY_RUN_WALLET_ADDRESS, DryRunTransport
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

OWNER = _DRY_RUN_WALLET_ADDRESS
SEED = "sWALLET"
DEST = "rDESTINATIONxxxxxxxxxxxxxxxxx"

# Ripple-epoch reference points for the deterministic dry-run clock.
_T_EARLY = 1_000_000_000
_T_FINISH = 1_000_000_100  # FinishAfter
_T_CANCEL = 1_000_000_200  # CancelAfter (later than FinishAfter)


# ── Escrow finish/cancel — create-sequence capture ───────────────────────


class TestEscrowSequenceCapture:
    """create_escrow must surface the create-sequence finish/cancel consume."""

    @pytest.mark.asyncio
    async def test_create_populates_sequence(self):
        t = DryRunTransport()
        res = await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        assert res.success is True
        escrows = await t.get_escrows(OWNER)
        assert len(escrows) == 1
        assert escrows[0].sequence > 0, "EscrowInfo.sequence must be populated"


# ── Escrow finish — happy path + reserve freed ───────────────────────────


class TestEscrowFinishHappyPath:
    @pytest.mark.asyncio
    async def test_finish_releases_funds_and_frees_reserve(self):
        t = DryRunTransport()
        # Far-future default clock makes the escrow immediately finishable.
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence

        owner_before = (await t.get_account_info(OWNER)).owner_count
        dest_before = int((await t.get_account_info(DEST)).balance_drops)

        res = await finish_escrow(t, SEED, OWNER, seq)
        assert res.success is True
        assert res.result_code == "tesSUCCESS"
        assert res.txid

        # Escrow object gone — reserve freed.
        assert await t.get_escrows(OWNER) == []
        owner_after = (await t.get_account_info(OWNER)).owner_count
        assert owner_after == owner_before - 1, "owner reserve must be freed"

        # Funds released to the destination (10 XRP = 10_000_000 drops).
        dest_after = int((await t.get_account_info(DEST)).balance_drops)
        assert dest_after == dest_before + 10_000_000

    @pytest.mark.asyncio
    async def test_verify_escrow_finished_reports_gone(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        await finish_escrow(t, SEED, OWNER, seq)

        result = await verify_escrow_finished(t, OWNER, offer_sequence=seq)
        assert result.passed is True
        assert result.gone is True
        assert not result.failures


# ── Escrow cancel — reclaim path ─────────────────────────────────────────


class TestEscrowCancelHappyPath:
    @pytest.mark.asyncio
    async def test_cancel_reclaims_funds_to_owner(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        owner_reserve_before = (await t.get_account_info(OWNER)).owner_count
        owner_bal_before = self._bal(t, OWNER)

        res = await cancel_escrow(t, SEED, OWNER, seq)
        assert res.success is True
        assert res.result_code == "tesSUCCESS"

        assert await t.get_escrows(OWNER) == []
        owner_reserve_after = (await t.get_account_info(OWNER)).owner_count
        assert owner_reserve_after == owner_reserve_before - 1
        # Reclaim: the locked XRP returns to the OWNER, not the destination.
        assert self._bal(t, OWNER) == owner_bal_before + 10_000_000

    @staticmethod
    def _bal(t: DryRunTransport, addr: str) -> int:
        return t._balances.get(addr, 0)


# ── Escrow time-gate error paths ─────────────────────────────────────────


class TestEscrowTimeGateErrors:
    @pytest.mark.asyncio
    async def test_finish_before_finish_after_is_no_permission(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        # Clock set BEFORE FinishAfter — not yet finishable.
        t.set_dry_clock(_T_EARLY)

        res = await finish_escrow(t, SEED, OWNER, seq)
        assert res.success is False
        assert res.result_code == "tecNO_PERMISSION"
        # The escrow must still be on-ledger — a failed finish removes nothing.
        assert len(await t.get_escrows(OWNER)) == 1

    @pytest.mark.asyncio
    async def test_cancel_before_cancel_after_is_no_permission(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        # Clock between FinishAfter and CancelAfter — cancel not yet allowed.
        t.set_dry_clock(_T_FINISH + 1)

        res = await cancel_escrow(t, SEED, OWNER, seq)
        assert res.success is False
        assert res.result_code == "tecNO_PERMISSION"
        assert len(await t.get_escrows(OWNER)) == 1


# ── Escrow wrong/nonexistent target ──────────────────────────────────────


class TestEscrowMissingTarget:
    @pytest.mark.asyncio
    async def test_finish_nonexistent_escrow(self):
        t = DryRunTransport()
        # No escrow created at all.
        res = await finish_escrow(t, SEED, OWNER, 999999)
        assert res.success is False
        assert res.result_code == "tecNO_TARGET"

    @pytest.mark.asyncio
    async def test_finish_wrong_sequence(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        res = await finish_escrow(t, SEED, OWNER, seq + 1)  # wrong OfferSequence
        assert res.success is False
        assert res.result_code == "tecNO_TARGET"
        # The real escrow is untouched.
        assert len(await t.get_escrows(OWNER)) == 1

    @pytest.mark.asyncio
    async def test_finish_already_finished(self):
        t = DryRunTransport()
        await create_escrow(t, SEED, "10", DEST, _T_FINISH, _T_CANCEL)
        seq = (await t.get_escrows(OWNER))[0].sequence
        first = await finish_escrow(t, SEED, OWNER, seq)
        assert first.success is True
        # Finishing the same escrow again must fail — it's gone now.
        second = await finish_escrow(t, SEED, OWNER, seq)
        assert second.success is False
        assert second.result_code == "tecNO_TARGET"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_escrow(self):
        t = DryRunTransport()
        res = await cancel_escrow(t, SEED, OWNER, 999999)
        assert res.success is False
        assert res.result_code == "tecNO_TARGET"


# ── DID delete ───────────────────────────────────────────────────────────


class TestDIDDelete:
    @pytest.mark.asyncio
    async def test_delete_then_verify_gone(self):
        t = DryRunTransport()
        set_res = await t.submit_did_set(SEED, "did:xrpl:1:example", "")
        assert set_res.success is True
        reserve_with_did = (await t.get_account_info(OWNER)).owner_count

        res = await delete_did(t, SEED)
        assert res.success is True
        assert res.result_code == "tesSUCCESS"

        # DID gone, reserve freed.
        assert await t.get_did(OWNER) is None
        reserve_after = (await t.get_account_info(OWNER)).owner_count
        assert reserve_after == reserve_with_did - 1

        verify = await verify_did_deleted(t, OWNER)
        assert verify.passed is True
        assert verify.gone is True

    @pytest.mark.asyncio
    async def test_delete_when_no_did_is_no_entry(self):
        t = DryRunTransport()
        # No DID ever set.
        res = await delete_did(t, SEED)
        assert res.success is False
        assert res.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_verify_did_deleted_fails_when_did_present(self):
        t = DryRunTransport()
        await t.submit_did_set(SEED, "did:xrpl:1:example", "")
        verify = await verify_did_deleted(t, OWNER)
        assert verify.passed is False
        assert verify.failures


# ── NFT burn ─────────────────────────────────────────────────────────────


class TestNFTBurn:
    @pytest.mark.asyncio
    async def test_burn_then_verify_gone_and_reserve_freed(self):
        t = DryRunTransport()
        mint = await mint_nft(t, SEED, "ipfs://example/asset.json", taxon=7)
        assert mint.success is True
        nft_id = mint.nft_id
        assert nft_id
        reserve_with_nft = (await t.get_account_info(OWNER)).owner_count

        res = await burn_nft(t, SEED, nft_id)
        assert res.success is True
        assert res.result_code == "tesSUCCESS"

        # NFT gone, reserve freed.
        assert await t.get_account_nfts(OWNER) == []
        reserve_after = (await t.get_account_info(OWNER)).owner_count
        assert reserve_after == reserve_with_nft - 1

        verify = await verify_nft_burned(t, OWNER, nftoken_id=nft_id)
        assert verify.passed is True
        assert verify.gone is True

    @pytest.mark.asyncio
    async def test_burn_nonexistent_is_no_entry(self):
        t = DryRunTransport()
        res = await burn_nft(t, SEED, "00080000DEADBEEF")
        assert res.success is False
        assert res.result_code == "tecNO_ENTRY"

    @pytest.mark.asyncio
    async def test_burn_one_of_many_leaves_the_rest(self):
        t = DryRunTransport()
        a = await mint_nft(t, SEED, "ipfs://a.json", taxon=1)
        b = await mint_nft(t, SEED, "ipfs://b.json", taxon=2)
        assert a.nft_id and b.nft_id

        res = await burn_nft(t, SEED, a.nft_id)
        assert res.success is True

        remaining = await t.get_account_nfts(OWNER)
        ids = {n.nft_id for n in remaining}
        assert a.nft_id not in ids
        assert b.nft_id in ids

    @pytest.mark.asyncio
    async def test_verify_nft_burned_fails_when_still_owned(self):
        t = DryRunTransport()
        mint = await mint_nft(t, SEED, "ipfs://example.json", taxon=7)
        verify = await verify_nft_burned(t, OWNER, nftoken_id=mint.nft_id)
        assert verify.passed is False
        assert verify.failures


# ── dry-run ↔ testnet PARITY ─────────────────────────────────────────────


class TestTransportParity:
    """The new methods must exist with matching signatures on both transports,
    and the dry-run error codes must be real XRPL tokens the teaching seam
    (explain_result_code) recognizes — so finish/cancel/delete/burn fail
    consistently and teach the same concept on both."""

    _NEW_METHODS = [
        "submit_escrow_finish",
        "submit_escrow_cancel",
        "submit_did_delete",
        "submit_nft_burn",
    ]

    @pytest.mark.parametrize("method", _NEW_METHODS)
    def test_method_exists_on_base_and_both_transports(self, method):
        assert hasattr(Transport, method), f"{method} missing from base contract"
        assert hasattr(DryRunTransport, method)
        assert hasattr(XRPLTestnetTransport, method)

    @pytest.mark.parametrize("method", _NEW_METHODS)
    def test_signatures_match_across_transports(self, method):
        dry_sig = inspect.signature(getattr(DryRunTransport, method))
        net_sig = inspect.signature(getattr(XRPLTestnetTransport, method))
        assert list(dry_sig.parameters) == list(net_sig.parameters), (
            f"{method} parameter list differs between transports"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "code",
        ["tecNO_PERMISSION", "tecNO_TARGET", "tecNO_ENTRY"],
    )
    async def test_dry_run_error_codes_are_real_and_explained(self, code):
        # Every error code the dry-run lifecycle methods emit must be a genuine
        # XRPL result code that explain_result_code can teach — the same routing
        # the create handlers use. A made-up code would teach nothing.
        info = explain_result_code(code)
        assert info["meaning"], f"{code} has no meaning in the doctor"
        assert info["action"], f"{code} has no action guidance in the doctor"

    @pytest.mark.asyncio
    async def test_testnet_methods_are_network_guarded(self):
        # Each new testnet signing method must call _network_guard() in its
        # source BEFORE building the wallet, so a mainnet override is refused
        # before the seed loads (pinned end-to-end by test_network_safety.py;
        # this is a fast source-level smoke check for the four new methods).
        for method in self._NEW_METHODS:
            src = inspect.getsource(getattr(XRPLTestnetTransport, method))
            guard_pos = src.find("_network_guard")
            wallet_pos = src.find("Wallet.from_seed")
            assert guard_pos != -1, f"{method} must call _network_guard()"
            assert wallet_pos != -1, f"{method} must build a wallet"
            assert guard_pos < wallet_pos, (
                f"{method}: _network_guard() must run BEFORE Wallet.from_seed"
            )
