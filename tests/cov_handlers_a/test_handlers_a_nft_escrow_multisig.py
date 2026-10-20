"""NFT, escrow, token-escrow and multisig handlers (beyond the shared submit table)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import xrpl_lab.handlers as handlers
from xrpl_lab.errors import LabException
from xrpl_lab.transport.base import EscrowInfo, FundResult, TrustLineInfo

from ._h import EXPLORER, TXID, Env, bad, checks_result, ok, secret, verdict

ISSUER = "rISSUERADDRESS123"
NFT_ID = "0008" + "A" * 60


# -- _explain_failure / _record_submit --


def test_explain_failure_with_no_code_prints_nothing(env: Env) -> None:
    handlers._explain_failure(env.console, "")
    assert env.out == ""


def test_explain_failure_prints_the_triplet(env: Env) -> None:
    handlers._explain_failure(env.console, "tecNO_PERMISSION")
    assert "Category:" in env.out and "Meaning:" in env.out and "Action:" in env.out


def test_explain_failure_infers_unknown_codes_by_prefix(env: Env) -> None:
    handlers._explain_failure(env.console, "tecBRAND_NEW_CODE")
    assert "claimed" in env.out and "tecBRAND_NEW_CODE" in env.out


def test_record_submit_success_and_failure(env: Env) -> None:
    handlers._record_submit(env.state, env.ctx, ok())
    handlers._record_submit(env.state, env.ctx, bad(txid=""))
    assert [(r.txid, r.success) for r in env.records()] == [(TXID, True), ("failed", False)]
    assert env.ctx["txids"] == [TXID]
    assert env.saved == 2


# -- mint_nft --


@pytest.mark.asyncio
async def test_mint_nft_requires_a_wallet(env: Env) -> None:
    calls = env.stub("mint_nft", ok())
    env.ctx.pop("wallet_seed")
    await env.run("handle_mint_nft")
    assert calls == [] and "No wallet in context" in env.out


@pytest.mark.asyncio
async def test_mint_nft_bad_numbers_fall_back_with_notes(env: Env) -> None:
    calls = env.stub("mint_nft", ok())
    await env.run("handle_mint_nft", {"taxon": "x", "transfer_fee": "y"})
    assert "Invalid taxon, using default (0)" in env.out
    assert "Invalid transfer_fee, using default (0)" in env.out
    assert calls[0][0][3:5] == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "clamped"), [("999999", 50000), ("-4", 0)])
async def test_mint_nft_clamps_the_royalty(env: Env, raw: str, clamped: int) -> None:
    calls = env.stub("mint_nft", ok())
    out = await env.run("handle_mint_nft", {"transfer_fee": raw})
    assert f"clamping to {clamped}" in env.out
    assert calls[0][0][4] == clamped
    assert out["nft_transfer_fee"] == clamped


@pytest.mark.asyncio
async def test_mint_nft_success_captures_the_id_and_royalty(env: Env) -> None:
    calls = env.stub("mint_nft", ok(nft_id=NFT_ID))
    out = await env.run(
        "handle_mint_nft",
        {"uri": "ipfs://x", "taxon": "7", "transfer_fee": "2500",
         "transferable": "false", "mutable": "yes"},
    )
    assert calls[0][0][2:] == ("ipfs://x", 7, 2500, False, True)
    assert out["nft_id"] == NFT_ID
    assert out["nft_transfer_fee"] == 2500
    assert "Royalty (TransferFee): 2.500%" in env.out
    assert f"NFTokenID: {NFT_ID}" in env.out
    assert "transferable False" in env.out and "mutable True" in env.out


@pytest.mark.asyncio
async def test_mint_nft_without_an_id_sets_no_nft_context(env: Env) -> None:
    env.stub("mint_nft", ok())
    out = await env.run("handle_mint_nft")
    assert "nft_id" not in out
    assert out["nft_transfer_fee"] == 0
    assert "Royalty" not in env.out


# -- verify_nft / burn / verify_nft_burned --


@pytest.mark.asyncio
async def test_verify_nft_without_a_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_nft")
    assert verdict(out, "verify_nft")["passed"] is False


@pytest.mark.asyncio
async def test_verify_nft_pass(env: Env) -> None:
    res = checks_result(found=True, checks=["owns it"])
    calls = env.stub("verify_nft", res)
    out = await env.run("handle_verify_nft", nft_id=NFT_ID)
    assert calls[0][1] == {"expected_nft_id": NFT_ID}
    assert "NFT ownership verified on-ledger" in env.out
    assert verdict(out, "verify_nft")["passed"] is True


@pytest.mark.asyncio
async def test_verify_nft_found_but_failing_is_not_a_pass(env: Env) -> None:
    env.stub("verify_nft", checks_result(passed=False, found=True, failures=["wrong id"]))
    out = await env.run("handle_verify_nft")
    assert "NFT ownership verified" not in env.out and "wrong id" in env.out
    assert verdict(out, "verify_nft")["failures"] == ["wrong id"]


@pytest.mark.asyncio
async def test_burn_nft_requires_a_wallet_and_an_explicit_id(env: Env) -> None:
    calls = env.stub("burn_nft", ok())
    await env.run("handle_burn_nft")
    assert calls == []
    assert "No NFToken to burn" in env.out and "Burns are irreversible" in env.out
    assert env.records() == []

    env.ctx.pop("wallet_seed")
    await env.run("handle_burn_nft", nft_id=NFT_ID)
    assert calls == []


@pytest.mark.asyncio
async def test_burn_nft_explicit_arg_beats_context_and_is_remembered(env: Env) -> None:
    calls = env.stub("burn_nft", ok())
    out = await env.run("handle_burn_nft", {"nftoken_id": "EXPLICIT" + "0" * 30}, nft_id=NFT_ID)
    assert calls[0][0][2] == "EXPLICIT" + "0" * 30
    assert out["burned_nft_id"] == "EXPLICIT" + "0" * 30
    assert "NFToken burned" in env.out


@pytest.mark.asyncio
async def test_burn_nft_failure_does_not_remember_a_burn(env: Env) -> None:
    env.stub("burn_nft", bad(error="not yours"))
    out = await env.run("handle_burn_nft", nft_id=NFT_ID)
    assert "NFTokenBurn failed: not yours" in env.out
    assert "burned_nft_id" not in out


@pytest.mark.asyncio
async def test_verify_nft_burned_paths(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_nft_burned")
    assert verdict(out, "verify_nft_burned")["passed"] is False

    env2 = Env(env.tmp_path, env.mp)
    calls = env2.stub("verify_nft_burned", checks_result(checks=["gone"]))
    out2 = await env2.run("handle_verify_nft_burned", burned_nft_id="B1", nft_id="M1")
    assert calls[0][1] == {"nftoken_id": "B1"}
    assert "asset destroyed, reserve freed" in env2.out
    assert verdict(out2, "verify_nft_burned")["passed"] is True

    env3 = Env(env.tmp_path, env.mp)
    env3.stub("verify_nft_burned", checks_result(passed=False, failures=["still owned"]))
    out3 = await env3.run("handle_verify_nft_burned")
    assert "still owned" in env3.out and "lifecycle complete" not in env3.out
    assert verdict(out3, "verify_nft_burned")["passed"] is False


# -- escrow create-sequence resolution --


@pytest.mark.asyncio
async def test_resolve_escrow_sequence_no_escrows(env: Env) -> None:
    env.on_transport("get_escrows", [])
    assert await handlers._resolve_created_escrow_sequence(
        env.transport, "rO", "rD", 10, 20, env.console) is None


@pytest.mark.asyncio
async def test_resolve_escrow_sequence_picks_newest_exact_match(env: Env) -> None:
    env.on_transport("get_escrows", [
        EscrowInfo(sequence=4, destination="rD", finish_after=10, cancel_after=20),
        EscrowInfo(sequence=9, destination="rD", finish_after=10, cancel_after=20),
        EscrowInfo(sequence=12, destination="rOTHER", finish_after=10, cancel_after=20),
    ])
    got = await handlers._resolve_created_escrow_sequence(
        env.transport, "rO", "rD", 10, 20, env.console)
    assert got == 9
    assert "matched by destination" not in env.out


@pytest.mark.asyncio
async def test_resolve_escrow_sequence_falls_back_to_cancel_after(env: Env) -> None:
    env.on_transport("get_escrows", [
        EscrowInfo(sequence=5, destination="rD", finish_after=11, cancel_after=20),
    ])
    got = await handlers._resolve_created_escrow_sequence(
        env.transport, "rO", "rD", 10, 20, env.console)
    assert got == 5
    assert "matched by destination + CancelAfter" in env.out


@pytest.mark.asyncio
async def test_resolve_escrow_sequence_gives_up_when_nothing_matches(env: Env) -> None:
    env.on_transport("get_escrows", [
        EscrowInfo(sequence=5, destination="rELSE", finish_after=10, cancel_after=20),
    ])
    got = await handlers._resolve_created_escrow_sequence(
        env.transport, "rO", "rD", 10, 20, env.console)
    assert got is None
    assert "create-sequence not captured" in env.out


@pytest.mark.asyncio
async def test_resolve_escrow_sequence_zero_means_unresolved(env: Env) -> None:
    env.on_transport("get_escrows", [
        EscrowInfo(sequence=0, destination="rD", finish_after=10, cancel_after=20),
    ])
    assert await handlers._resolve_created_escrow_sequence(
        env.transport, "rO", "rD", 10, 20, env.console) is None


# -- create_escrow --


@pytest.mark.asyncio
async def test_create_escrow_requires_a_wallet(env: Env) -> None:
    calls = env.stub("create_escrow", ok())
    env.ctx.pop("wallet_seed")
    await env.run("handle_create_escrow")
    assert calls == [] and "No wallet in context" in env.out


@pytest.mark.asyncio
async def test_create_escrow_success_captures_the_identity_and_sequence(env: Env) -> None:
    calls = env.stub("create_escrow", ok())

    async def _escrows(addr):
        a = calls[0][0]
        return [
            EscrowInfo(sequence=3, destination="rOLD", finish_after=1, cancel_after=2),
            EscrowInfo(sequence=8, destination=a[3], finish_after=a[4], cancel_after=a[5]),
        ]

    env.mp.setattr(env.transport, "get_escrows", _escrows)
    now = int(time.time()) - handlers._RIPPLE_EPOCH
    out = await env.run("handle_create_escrow", {"amount": "4", "finish_seconds": "60"})
    args = calls[0][0]
    assert args[2:4] == ("4", "rLEARNER")  # defaults to escrow-to-self
    assert now + 55 <= args[4] <= now + 65
    assert args[5] == args[4] + 86400
    assert out["escrow_sequence"] == 8
    assert out["escrow_owner"] == "rLEARNER"
    assert out["escrow_destination"] == "rLEARNER"
    assert out["escrow_finish_after"] == args[4]
    assert out["escrow_cancel_after"] == args[5]
    assert "Escrow create-sequence: 8" in env.out and "finishable in ~60s" in env.out


@pytest.mark.asyncio
async def test_create_escrow_that_cannot_be_resolved_sets_no_sequence(env: Env) -> None:
    env.stub("create_escrow", ok())
    env.on_transport("get_escrows", [])
    out = await env.run("handle_create_escrow", {"destination": "rDEST"})
    assert "escrow_sequence" not in out
    assert out["escrow_destination"] == "rDEST"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "delay", "note"),
    [("abc", 120, "Invalid finish_seconds, using default (120)"),
     ("-100", 1, "finish_seconds -100 is invalid")],
)
async def test_create_escrow_validates_the_delay(env: Env, raw: str, delay: int, note: str) -> None:
    calls = env.stub("create_escrow", ok())
    env.on_transport("get_escrows", [])
    await env.run("handle_create_escrow", {"finish_seconds": raw})
    assert note in env.out
    now = int(time.time()) - handlers._RIPPLE_EPOCH
    assert now + delay - 5 <= calls[0][0][4] <= now + delay + 5  # never in the past


@pytest.mark.asyncio
async def test_create_escrow_failure_is_not_resolved(env: Env) -> None:
    env.stub("create_escrow", bad(code="tecDIR_FULL", error="full"))
    probe = env.on_transport("get_escrows", [])
    out = await env.run("handle_create_escrow")
    assert probe == []
    assert "Escrow failed: full" in env.out
    assert "escrow_owner" not in out


# -- verify_escrow --


@pytest.mark.asyncio
async def test_verify_escrow_paths(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_escrow")
    assert verdict(out, "verify_escrow")["passed"] is False

    env2 = Env(env.tmp_path, env.mp)
    env2.stub("verify_escrow", checks_result(found=True, checks=["escrow rests"]))
    out2 = await env2.run("handle_verify_escrow")
    assert "Escrow verified on-ledger" in env2.out
    assert verdict(out2, "verify_escrow")["passed"] is True

    env3 = Env(env.tmp_path, env.mp)
    env3.stub("verify_escrow", checks_result(passed=False, found=True, failures=["amount off"]))
    out3 = await env3.run("handle_verify_escrow")
    assert "amount off" in env3.out and "Escrow verified" not in env3.out
    assert verdict(out3, "verify_escrow")["failures"] == ["amount off"]


# -- _wait_for_finish_after --


class _Sleeper:
    def __init__(self) -> None:
        self.slept: list[int] = []

    async def sleep(self, seconds: int) -> None:
        self.slept.append(seconds)


@pytest.fixture()
def sleeper(env: Env) -> _Sleeper:
    s = _Sleeper()
    env.mp.setattr(handlers, "asyncio", SimpleNamespace(sleep=s.sleep))
    return s


def _real_transport() -> SimpleNamespace:
    return SimpleNamespace(network_name="testnet")


@pytest.mark.asyncio
async def test_wait_skips_without_a_finish_after(env: Env, sleeper: _Sleeper) -> None:
    await handlers._wait_for_finish_after(_real_transport(), None, env.console)
    assert sleeper.slept == []


@pytest.mark.asyncio
async def test_wait_skips_on_the_dry_run_transport(env: Env, sleeper: _Sleeper) -> None:
    future = int(time.time()) - handlers._RIPPLE_EPOCH + 1000
    await handlers._wait_for_finish_after(env.transport, future, env.console)
    assert sleeper.slept == [] and env.out == ""


@pytest.mark.asyncio
async def test_wait_skips_an_unparsable_finish_after(env: Env, sleeper: _Sleeper) -> None:
    await handlers._wait_for_finish_after(_real_transport(), "soon", env.console)
    assert sleeper.slept == []


@pytest.mark.asyncio
async def test_wait_skips_an_elapsed_finish_after(env: Env, sleeper: _Sleeper) -> None:
    past = int(time.time()) - handlers._RIPPLE_EPOCH - 10
    await handlers._wait_for_finish_after(_real_transport(), past, env.console)
    assert sleeper.slept == []


@pytest.mark.asyncio
async def test_wait_sleeps_the_remainder_plus_a_margin(env: Env, sleeper: _Sleeper) -> None:
    future = int(time.time()) - handlers._RIPPLE_EPOCH + 30
    await handlers._wait_for_finish_after(_real_transport(), future, env.console)
    (waited,) = sleeper.slept
    assert 30 <= waited <= 33
    assert f"Waiting ~{waited}s for FinishAfter" in env.out


@pytest.mark.asyncio
async def test_wait_is_capped(env: Env, sleeper: _Sleeper) -> None:
    far = int(time.time()) - handlers._RIPPLE_EPOCH + 10_000
    await handlers._wait_for_finish_after(_real_transport(), far, env.console)
    assert sleeper.slept == [300]
    await handlers._wait_for_finish_after(_real_transport(), far, env.console, max_wait=7)
    assert sleeper.slept == [300, 7]


# -- finish / cancel escrow --


def test_resolve_escrow_target(env: Env) -> None:
    assert handlers._resolve_escrow_target(env.state, {}) == ("rLEARNER", None)
    assert handlers._resolve_escrow_target(
        env.state, {"escrow_owner": "rO", "escrow_sequence": 4}) == ("rO", 4)
    env.state.wallet_address = None
    assert handlers._resolve_escrow_target(env.state, {}) == ("", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "stub", "word"),
    [("handle_finish_escrow", "finish_escrow", "finish"),
     ("handle_cancel_escrow", "cancel_escrow", "cancel")],
)
async def test_finish_and_cancel_escrow_preconditions(
    env: Env, handler: str, stub: str, word: str,
) -> None:
    calls = env.stub(stub, ok())
    env.ctx.pop("wallet_seed")
    await env.run(handler)
    assert "No wallet in context" in env.out

    env.ctx["wallet_seed"] = secret()
    await env.run(handler)  # no escrow_sequence captured
    assert f"No escrow to {word}" in env.out

    env.ctx["escrow_sequence"] = 0
    env.state.wallet_address = None
    await env.run(handler)  # no owner
    assert calls == [] and env.records() == []


@pytest.mark.asyncio
async def test_finish_escrow_passes_owner_and_sequence_and_waits(
    env: Env, sleeper: _Sleeper,
) -> None:
    calls = env.stub("finish_escrow", ok())
    env.transport = _real_transport()
    future = int(time.time()) - handlers._RIPPLE_EPOCH + 20
    out = await env.run(
        "handle_finish_escrow", escrow_owner="rOWNER12345678", escrow_sequence=5,
        escrow_finish_after=future,
    )
    assert calls[0][0][2:] == ("rOWNER12345678", 5)
    assert len(sleeper.slept) == 1
    assert "Escrow finished" in env.out
    assert out["txids"] == [TXID]


@pytest.mark.asyncio
async def test_cancel_escrow_passes_owner_and_sequence(env: Env) -> None:
    calls = env.stub("cancel_escrow", ok())
    await env.run("handle_cancel_escrow", escrow_sequence=6)
    assert calls[0][0][2:] == ("rLEARNER", 6)  # owner defaults to the learner
    assert "Escrow cancelled" in env.out


@pytest.mark.asyncio
async def test_verify_escrow_finished_paths(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_escrow_finished")
    assert verdict(out, "verify_escrow_finished")["passed"] is False

    env2 = Env(env.tmp_path, env.mp)
    calls = env2.stub("verify_escrow_finished", checks_result(checks=["gone"]))
    out2 = await env2.run(
        "handle_verify_escrow_finished", escrow_owner="rOWNER", escrow_sequence=5,
    )
    assert calls[0][0][1] == "rOWNER" and calls[0][1] == {"offer_sequence": 5}
    assert "Escrow lifecycle complete" in env2.out
    assert verdict(out2, "verify_escrow_finished")["passed"] is True

    env3 = Env(env.tmp_path, env.mp)
    env3.stub("verify_escrow_finished", checks_result(passed=False, failures=["still there"]))
    out3 = await env3.run("handle_verify_escrow_finished")
    assert "still there" in env3.out and "lifecycle complete" not in env3.out
    assert verdict(out3, "verify_escrow_finished")["failures"] == ["still there"]


# -- token escrow setup --


@pytest.mark.asyncio
async def test_allow_trustline_locking_needs_an_issuer(env: Env) -> None:
    calls = env.stub("set_allow_trustline_locking", ok())
    await env.run("handle_set_allow_trustline_locking")
    assert calls == [] and "No issuer wallet in context" in env.out


@pytest.mark.asyncio
async def test_allow_trustline_locking_success_sets_the_flag_in_context(env: Env) -> None:
    env.stub("set_allow_trustline_locking", ok())
    out = await env.run(
        "handle_set_allow_trustline_locking", issuer_seed="sPLAIN", issuer_address=ISSUER,
    )
    assert out["allow_trustline_locking"] is True


@pytest.mark.asyncio
async def test_allow_trustline_locking_failure_leaves_the_flag_unset(env: Env) -> None:
    env.stub("set_allow_trustline_locking", bad(error="refused"))
    out = await env.run(
        "handle_set_allow_trustline_locking", issuer_seed=secret("s"), issuer_address=ISSUER,
    )
    assert "Opt-in failed: refused" in env.out
    assert "allow_trustline_locking" not in out


@pytest.mark.asyncio
async def test_create_token_recipient_needs_an_issuer(env: Env) -> None:
    out = await env.run("handle_create_token_recipient")
    assert "No issuer in context" in env.out
    assert "recipient_address" not in out


@pytest.mark.asyncio
@pytest.mark.parametrize(("trust_ok", "line"), [
    (True, "Recipient trust line set."), (False, "Recipient trust line: no room"),
])
async def test_create_token_recipient_funds_and_trusts(env: Env, trust_ok: bool, line: str) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="x"))
    env.stub("await_validated_balance", 10)
    calls = env.stub("set_trust_line", ok() if trust_ok else bad(error="no room"))
    out = await env.run(
        "handle_create_token_recipient", {"currency": "GLD", "limit": "77"},
        issuer_address=ISSUER,
    )
    assert out["recipient_address"].startswith("r")
    seed, addr = out["recipient_seed"].get(), out["recipient_address"]
    assert calls[0][0][1:] == (seed, ISSUER, "GLD", "77")
    assert calls[0][1] == {"wallet_address": addr}
    assert line in env.out
    assert "Recipient funded! Balance: 10 XRP" in env.out


@pytest.mark.asyncio
async def test_create_token_recipient_records_an_unfunded_recipient(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=False, address="x", message="down"))
    env.stub("set_trust_line", ok())
    out = await env.run("handle_create_token_recipient", issuer_address=ISSUER)
    assert verdict(out, "create_token_recipient")["passed"] is False


@pytest.mark.asyncio
async def test_create_noopt_issuer_needs_a_wallet(env: Env) -> None:
    env.ctx.pop("wallet_seed")
    out = await env.run("handle_create_noopt_issuer")
    assert "No wallet in context" in env.out
    assert "noopt_issuer_address" not in out


@pytest.mark.asyncio
@pytest.mark.parametrize("issue_ok", [True, False])
async def test_create_noopt_issuer_creates_funds_and_issues(env: Env, issue_ok: bool) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="x"))
    env.stub("await_validated_balance", 10)
    trust = env.stub("set_trust_line", ok())
    issue = env.stub("issue_token", ok() if issue_ok else bad(error="cannot issue"))
    out = await env.run("handle_create_noopt_issuer", {"currency": "NOP", "amount": "9"})
    addr = out["noopt_issuer_address"]
    assert out["noopt_currency"] == "NOP"
    assert trust[0][0][2:] == (addr, "NOP", "1000")
    assert issue[0][0][1] == out["noopt_issuer_seed"].get()
    assert issue[0][0][2:] == ("rLEARNER", "NOP", addr, "9")
    assert "Issuer funded" not in env.out  # the setup keeps the faucet line quiet
    if issue_ok:
        assert "Issued 9 NOP from a no-opt-in issuer." in env.out
    else:
        assert "Issuance setup note: cannot issue" in env.out


@pytest.mark.asyncio
async def test_snapshot_recipient_balance_needs_a_recipient(env: Env) -> None:
    out = await env.run("handle_snapshot_recipient_balance")
    assert "No recipient wallet" in env.out
    assert "token_balance_before" not in out


@pytest.mark.asyncio
async def test_snapshot_recipient_balance_reads_the_matching_line(env: Env) -> None:
    env.on_transport("get_trust_lines", [
        TrustLineInfo(account="rR", peer="rELSE", currency="GLD", balance="1"),
        TrustLineInfo(account="rR", peer=ISSUER, currency="USD", balance="2"),
        TrustLineInfo(account="rR", peer=ISSUER, currency="GLD", balance="33"),
    ])
    out = await env.run(
        "handle_snapshot_recipient_balance", {}, recipient_address="rR", issuer_address=ISSUER,
    )
    assert out["recipient_balance_before"] == "33"
    assert out["token_balance_before"] == "33"
    assert "Recipient GLD balance (before): 33" in env.out


@pytest.mark.asyncio
async def test_snapshot_recipient_balance_after_label_keeps_the_before_value(env: Env) -> None:
    env.on_transport("get_trust_lines", [])
    out = await env.run(
        "handle_snapshot_recipient_balance", {"label": "after"},
        recipient_address="rR", token_balance_before="33",
    )
    assert out["recipient_balance_after"] == "0"
    assert out["token_balance_before"] == "33"  # untouched by an "after" snapshot


@pytest.mark.asyncio
async def test_snapshot_recipient_balance_without_an_issuer_takes_any_peer(env: Env) -> None:
    env.on_transport("get_trust_lines", [
        TrustLineInfo(account="rR", peer="rANY", currency="GLD", balance="5"),
    ])
    out = await env.run("handle_snapshot_recipient_balance", recipient_address="rR")
    assert out["recipient_balance_before"] == "5"


# -- create_token_escrow --


@pytest.mark.asyncio
async def test_create_token_escrow_preconditions(env: Env) -> None:
    calls = env.stub("create_token_escrow", ok())
    env.ctx.pop("wallet_seed")
    await env.run("handle_create_token_escrow", issuer_address=ISSUER, recipient_address="rR")
    assert "No wallet in context" in env.out

    env2 = Env(env.tmp_path, env.mp)
    calls2 = env2.stub("create_token_escrow", ok())
    await env2.run("handle_create_token_escrow", issuer_address=ISSUER)
    assert "Missing issuer or recipient" in env2.out
    assert calls == [] and calls2 == [] and env.records() == [] and env2.records() == []


@pytest.mark.asyncio
async def test_create_token_escrow_recipient_can_come_from_the_step(env: Env) -> None:
    calls = env.stub("create_token_escrow", ok())
    env.on_transport("get_escrows", [])
    await env.run("handle_create_token_escrow", {"destination": "rARG"}, issuer_address=ISSUER)
    assert calls[0][0][5] == "rARG"


@pytest.mark.asyncio
async def test_create_token_escrow_success_keeps_the_context_and_matches_by_identity(
    env: Env,
) -> None:
    calls = env.stub("create_token_escrow", ok())

    async def _escrows(addr):
        k = calls[0][1]
        return [EscrowInfo(sequence=21, destination="rR",
                           finish_after=k["finish_after"], cancel_after=k["cancel_after"])]

    env.mp.setattr(env.transport, "get_escrows", _escrows)
    out = await env.run(
        "handle_create_token_escrow",
        {"currency": "GLD", "amount": "40", "cancel_seconds": "500", "finish_seconds": "20"},
        issuer_address=ISSUER, recipient_address="rR",
    )
    k = calls[0][1]
    assert k["cancel_after"] - k["finish_after"] == 480
    assert k["source_address"] == "rLEARNER"
    assert out["token_escrow_sequence"] == 21
    assert out["token_escrow_currency"] == "GLD" and out["token_escrow_amount"] == "40"
    assert out["token_escrow_issuer"] == ISSUER and out["token_escrow_recipient"] == "rR"
    assert out["token_escrow_owner"] == "rLEARNER"
    assert out["token_escrow_finish_after"] == k["finish_after"]
    assert out["token_escrow_cancel_after"] == k["cancel_after"]
    assert "Escrow create-sequence: 21" in env.out


@pytest.mark.asyncio
async def test_create_token_escrow_validates_the_windows(env: Env) -> None:
    calls = env.stub("create_token_escrow", ok())
    env.on_transport("get_escrows", [])
    await env.run(
        "handle_create_token_escrow", {"cancel_seconds": "zzz", "finish_seconds": "qq"},
        issuer_address=ISSUER, recipient_address="rR",
    )
    assert "Invalid cancel_seconds, using default (86400)" in env.out
    assert "Invalid finish_seconds, using default (30)" in env.out
    k = calls[0][1]
    assert k["cancel_after"] - k["finish_after"] == 86400 - 30

    env2 = Env(env.tmp_path, env.mp)
    calls2 = env2.stub("create_token_escrow", ok())
    env2.on_transport("get_escrows", [])
    await env2.run(
        "handle_create_token_escrow", {"cancel_seconds": "-5", "finish_seconds": "0"},
        issuer_address=ISSUER, recipient_address="rR",
    )
    assert "finish_seconds 0 is invalid" in env2.out
    k2 = calls2[0][1]
    assert k2["cancel_after"] == k2["finish_after"]  # both floored to 1 second


@pytest.mark.asyncio
async def test_create_token_escrow_unresolved_sequence(env: Env) -> None:
    env.stub("create_token_escrow", ok())
    env.on_transport("get_escrows", [])
    out = await env.run(
        "handle_create_token_escrow", issuer_address=ISSUER, recipient_address="rR",
    )
    assert "token_escrow_sequence" not in out


# -- create_token_escrow_expect_fail --


@pytest.mark.asyncio
async def test_expect_fail_escrow_without_a_noopt_issuer_halts_loudly(env: Env) -> None:
    calls = env.stub("create_token_escrow", bad())
    with pytest.raises(LabException) as ei:
        await env.run("handle_create_token_escrow_expect_fail")
    assert ei.value.error.code == "STATE_MISSING_NOOPT_ISSUER"
    assert "create_noopt_issuer" in ei.value.error.hint
    assert calls == []


@pytest.mark.asyncio
async def test_expect_fail_escrow_requires_a_wallet(env: Env) -> None:
    calls = env.stub("create_token_escrow", bad())
    env.ctx.pop("wallet_seed")
    await env.run("handle_create_token_escrow_expect_fail", noopt_issuer_address="rNOOPT")
    assert calls == [] and "No wallet in context" in env.out


@pytest.mark.asyncio
async def test_expect_fail_escrow_submits_against_the_noopt_issuer(env: Env) -> None:
    calls = env.stub("create_token_escrow", bad(code="tecNO_PERMISSION", error="not opted in"))
    out = await env.run(
        "handle_create_token_escrow_expect_fail", {"cancel_seconds": "x", "finish_seconds": "y"},
        noopt_issuer_address="rNOOPT", noopt_currency="NOP", recipient_address="rR",
    )
    args, kwargs = calls[0]
    assert args[2:] == ("NOP", "rNOOPT", "50", "rR")
    assert kwargs["cancel_after"] > kwargs["finish_after"]
    assert "Expected failure: tecNO_PERMISSION" in env.out
    assert "not opted in" in env.out and "Meaning:" in env.out
    assert out["failed_txids"] == [{"result_code": "tecNO_PERMISSION", "error": "not opted in"}]


@pytest.mark.asyncio
async def test_expect_fail_escrow_a_different_code_is_not_called_expected(env: Env) -> None:
    env.stub("create_token_escrow", bad(code="tecNO_LINE", error="no line"))
    out = await env.run(
        "handle_create_token_escrow_expect_fail", noopt_issuer_address="rNOOPT",
    )
    assert "Failed with tecNO_LINE" in env.out
    assert "Expected failure:" not in env.out
    assert "did not exercise the opt-in rule" in env.out
    assert out["failed_txids"][0]["result_code"] == "tecNO_LINE"


@pytest.mark.asyncio
async def test_expect_fail_escrow_unexpected_success_records_a_real_hash(env: Env) -> None:
    env.stub("create_token_escrow", ok())
    out = await env.run(
        "handle_create_token_escrow_expect_fail", noopt_issuer_address="rNOOPT",
    )
    assert "Unexpected success" in env.out and EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert "failed_txids" not in out
    assert env.last().success is True and env.last().explorer_url == EXPLORER


@pytest.mark.asyncio
async def test_expect_fail_escrow_unexpected_success_without_hash_records_nothing(env: Env) -> None:
    env.stub("create_token_escrow", ok(txid="", explorer=""))
    out = await env.run(
        "handle_create_token_escrow_expect_fail", noopt_issuer_address="rNOOPT",
    )
    assert env.records() == [] and "txids" not in out


# -- finish_token_escrow --


@pytest.mark.asyncio
async def test_finish_token_escrow_needs_a_captured_sequence(env: Env) -> None:
    calls = env.stub("finish_token_escrow", ok())
    await env.run("handle_finish_token_escrow")
    assert calls == [] and "No token escrow to finish" in env.out


@pytest.mark.asyncio
async def test_finish_token_escrow_needs_some_wallet(env: Env) -> None:
    calls = env.stub("finish_token_escrow", ok())
    env.ctx.pop("wallet_seed")
    await env.run("handle_finish_token_escrow", token_escrow_sequence=3)
    assert calls == [] and "No wallet to submit EscrowFinish" in env.out


@pytest.mark.asyncio
async def test_finish_token_escrow_falls_back_to_the_holder_wallet(env: Env) -> None:
    calls = env.stub("finish_token_escrow", ok())
    await env.run("handle_finish_token_escrow", token_escrow_sequence=3)
    assert calls[0][0][1:] == ("sSEED", "rLEARNER", 3)


@pytest.mark.asyncio
async def test_finish_token_escrow_recipient_finishes_after_the_wait(
    env: Env, sleeper: _Sleeper,
) -> None:
    calls = env.stub("finish_token_escrow", ok())
    env.transport = _real_transport()
    future = int(time.time()) - handlers._RIPPLE_EPOCH + 15
    out = await env.run(
        "handle_finish_token_escrow", token_escrow_owner="rHOLDER12345678",
        token_escrow_sequence=3, recipient_seed=secret("sREC"),
        token_escrow_finish_after=future,
    )
    assert calls[0][0][1:] == ("sREC", "rHOLDER12345678", 3)
    assert len(sleeper.slept) == 1
    assert "IOU released to the recipient" in env.out
    assert out["txids"] == [TXID]


# -- verify_token_moved --


@pytest.mark.asyncio
async def test_verify_token_moved_without_prerequisites(env: Env) -> None:
    out = await env.run("handle_verify_token_moved")
    assert "token-escrow steps did not run" in env.out
    assert verdict(out, "verify_token_moved")["passed"] is False


@pytest.mark.asyncio
async def test_verify_token_moved_uses_the_escrow_context(env: Env) -> None:
    calls = env.stub("verify_token_moved", checks_result(checks=["balance rose"]))
    out = await env.run(
        "handle_verify_token_moved", token_escrow_recipient="rR", token_escrow_currency="GLD",
        token_escrow_issuer=ISSUER, token_balance_before="2", token_escrow_amount="40",
    )
    assert calls[0][0][1:] == ("rR", "GLD", ISSUER)
    assert calls[0][1] == {"before": "2", "expected_increase": "40"}
    assert "the escrowed IOU is now the recipient's" in env.out
    assert verdict(out, "verify_token_moved")["passed"] is True


@pytest.mark.asyncio
async def test_verify_token_moved_falls_back_to_recipient_and_issuer_context(env: Env) -> None:
    calls = env.stub("verify_token_moved", checks_result(passed=False, failures=["no change"]))
    out = await env.run(
        "handle_verify_token_moved", recipient_address="rR2", issuer_address=ISSUER,
    )
    assert calls[0][0][1:] == ("rR2", "GLD", ISSUER)
    assert calls[0][1] == {"before": "0", "expected_increase": None}
    assert "no change" in env.out and "now the recipient's" not in env.out
    assert verdict(out, "verify_token_moved")["failures"] == ["no change"]


# -- multisig --


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "expected", "note"), [
    ("abc", 3, "Invalid count, using default (3)"),
    ("0", 3, "count 0 is outside this lesson's 1-8 range"),
    ("9", 3, "count 9 is outside"),
    ("2", 2, ""),
])
async def test_create_signer_wallets(env: Env, raw: str, expected: int, note: str) -> None:
    out = await env.run("handle_create_signer_wallets", {"count": raw})
    assert len(out["signer_addresses"]) == expected == len(out["signer_seeds"])
    assert len(set(out["signer_addresses"])) == expected  # distinct keys
    assert all(s.get().startswith("s") for s in out["signer_seeds"])
    assert all(a in env.out for a in out["signer_addresses"])
    if note:
        assert note in env.out
    else:
        assert "outside" not in env.out and "Invalid" not in env.out


@pytest.mark.asyncio
async def test_set_signer_list_preconditions(env: Env) -> None:
    calls = env.stub("set_signer_list", ok())
    env.ctx.pop("wallet_seed")
    await env.run("handle_set_signer_list")
    assert "No wallet in context" in env.out

    env.ctx["wallet_seed"] = secret()
    await env.run("handle_set_signer_list")
    assert "No signer wallets in context" in env.out
    assert calls == [] and env.records() == []


@pytest.mark.asyncio
async def test_set_signer_list_pads_and_repairs_weights(env: Env) -> None:
    calls = env.stub("set_signer_list", ok())
    out = await env.run(
        "handle_set_signer_list", {"quorum": "x", "weights": "2, bad ,"},
        signer_addresses=["rS1", "rS2", "rS3"],
    )
    assert "Invalid quorum, using default (2)" in env.out
    # "2" kept, "bad" repaired to 1, third padded to 1.
    assert calls[0][0][2:] == (2, [("rS1", 2), ("rS2", 1), ("rS3", 1)], "rLEARNER")
    assert out["multisig_quorum"] == 2
    assert out["multisig_entries"] == [("rS1", 2), ("rS2", 1), ("rS3", 1)]
    assert "2-of-4 signer list" in env.out
    assert "owner-reserve increment" in env.out


@pytest.mark.asyncio
async def test_set_signer_list_failure_keeps_no_roster(env: Env) -> None:
    env.stub("set_signer_list", bad(error="bad quorum"))
    out = await env.run("handle_set_signer_list", signer_addresses=["rS1", "rS2"])
    assert "SignerListSet failed: bad quorum" in env.out
    assert "multisig_quorum" not in out and "multisig_entries" not in out


@pytest.mark.asyncio
async def test_verify_signer_list_paths(env: Env) -> None:
    out = await env.run("handle_verify_signer_list")  # nothing installed yet
    assert "SignerListSet step did not run" in env.out
    assert verdict(out, "verify_signer_list")["passed"] is False

    env2 = Env(env.tmp_path, env.mp)
    calls = env2.stub("verify_signer_list", checks_result(checks=["quorum 2"]))
    out2 = await env2.run(
        "handle_verify_signer_list", multisig_quorum=2, multisig_entries=[("rS1", 1)],
    )
    assert calls[0][1] == {"expected_quorum": 2, "expected_entries": [("rS1", 1)]}
    assert "exactly the quorum and roster you installed" in env2.out
    assert verdict(out2, "verify_signer_list")["passed"] is True

    env3 = Env(env.tmp_path, env.mp)
    env3.stub("verify_signer_list", checks_result(passed=False, failures=["quorum differs"]))
    out3 = await env3.run("handle_verify_signer_list", multisig_quorum=2)
    assert "quorum differs" in env3.out and "exactly the quorum" not in env3.out
    assert verdict(out3, "verify_signer_list")["failures"] == ["quorum differs"]


@pytest.mark.asyncio
async def test_verify_signer_list_zero_quorum_is_not_missing(env: Env) -> None:
    calls = env.stub("verify_signer_list", checks_result())
    await env.run("handle_verify_signer_list", multisig_quorum=0)
    assert len(calls) == 1


def test_pick_signers_and_combined_weight() -> None:
    ctx = {
        "signer_seeds": [secret("s1"), "s2", secret("s3")],
        "signer_addresses": ["rA", "rB", "rC"],
        "multisig_entries": [("rA", 2), ("rB", 1), ("rC", 5)],
    }
    assert handlers._pick_signers(ctx, 2) == (["s1", "s2"], ["rA", "rB"])
    assert handlers._pick_signers({}, 2) == ([], [])
    assert handlers._combined_weight(ctx, ["rA", "rB", "rUNKNOWN"]) == 3
    assert handlers._combined_weight({}, ["rA"]) == 0


def _multisig_ctx(n: int = 3) -> dict:
    return {
        "signer_seeds": [secret(f"s{i}") for i in range(n)],
        "signer_addresses": [f"rS{i}" for i in range(n)],
        "multisig_entries": [(f"rS{i}", 1) for i in range(n)],
        "multisig_quorum": 2,
    }


@pytest.mark.asyncio
async def test_send_multisig_payment_preconditions(env: Env) -> None:
    calls = env.stub("send_multisig_payment", ok())
    await env.run("handle_send_multisig_payment")  # no signer_seeds
    assert "Missing treasury or signer wallets" in env.out

    env.state.wallet_address = None
    await env.run("handle_send_multisig_payment", **_multisig_ctx())
    assert calls == []


@pytest.mark.asyncio
async def test_send_multisig_payment_needs_enough_signers(env: Env) -> None:
    calls = env.stub("send_multisig_payment", ok())
    await env.run("handle_send_multisig_payment", {"signer_count": "5"}, **_multisig_ctx(2))
    assert "Only 2 signer wallet(s) in context" in env.out
    assert calls == [] and env.records() == []


@pytest.mark.asyncio
async def test_send_multisig_payment_signs_with_the_requested_signers(env: Env) -> None:
    calls = env.stub("send_multisig_payment", ok())
    out = await env.run(
        "handle_send_multisig_payment", {"signer_count": "x", "amount": "3"}, **_multisig_ctx(),
    )
    assert "Invalid signer_count, using default (2)" in env.out
    args, kwargs = calls[0]
    assert args[1:5] == ("rLEARNER", "rS0", "3", ["s0", "s1"])  # default payee = first keyholder
    assert kwargs == {"signer_addresses": ["rS0", "rS1"], "memo": "XRPLLAB|MULTISIG|2sig"}
    assert "combined weight 2 vs quorum 2" in env.out
    assert "base fee × (1 + 2 signatures)" in env.out
    assert "Fee paid: 12 drops" in env.out
    assert out["multisig_payment_txid"] == TXID


@pytest.mark.asyncio
async def test_send_multisig_payment_destination_precedence(env: Env) -> None:
    calls = env.stub("send_multisig_payment", ok())
    await env.run("handle_send_multisig_payment", multisig_payee="rPAYEE", **_multisig_ctx())
    assert calls[0][0][2] == "rPAYEE"
    await env.run("handle_send_multisig_payment", {"destination": "rARG"})
    assert calls[1][0][2] == "rARG"


@pytest.mark.asyncio
async def test_send_multisig_payment_failure_sets_no_payment_txid(env: Env) -> None:
    env.stub("send_multisig_payment", bad(code="tefBAD_QUORUM", error="light"))
    out = await env.run("handle_send_multisig_payment", **_multisig_ctx())
    assert "Multi-signed payment failed: light" in env.out
    assert "multisig_payment_txid" not in out


@pytest.mark.asyncio
async def test_multisig_expect_fail_preconditions(env: Env) -> None:
    calls = env.stub("send_multisig_payment", bad())
    await env.run("handle_send_multisig_payment_expect_fail")
    assert "Missing treasury or signer wallets" in env.out

    await env.run("handle_send_multisig_payment_expect_fail", signer_seeds=[])
    assert "No signer wallets in context" in env.out
    assert calls == [] and "failed_txids" not in env.ctx


@pytest.mark.asyncio
async def test_multisig_expect_fail_below_quorum_is_the_taught_failure(env: Env) -> None:
    calls = env.stub("send_multisig_payment", bad(code="tefBAD_QUORUM", error="weight 1 < 2"))
    out = await env.run("handle_send_multisig_payment_expect_fail", {"signer_count": "x"},
                        **_multisig_ctx())
    args, kwargs = calls[0]
    assert args[4] == ["s0"] and kwargs["signer_addresses"] == ["rS0"]
    assert "combined weight 1 vs quorum 2" in env.out
    assert "Expected failure: tefBAD_QUORUM" in env.out
    assert out["failed_txids"] == [{"result_code": "tefBAD_QUORUM", "error": "weight 1 < 2"}]


@pytest.mark.asyncio
async def test_multisig_expect_fail_other_code_is_called_out(env: Env) -> None:
    env.stub("send_multisig_payment", bad(code="tefBAD_SIGNATURE", error="bad sig"))
    out = await env.run("handle_send_multisig_payment_expect_fail", **_multisig_ctx())
    assert "Failed with tefBAD_SIGNATURE" in env.out
    assert "did not exercise the quorum rule" in env.out
    assert "Expected failure:" not in env.out
    assert out["failed_txids"][0]["result_code"] == "tefBAD_SIGNATURE"


@pytest.mark.asyncio
async def test_multisig_expect_fail_unexpected_success_records_real_hash_only(env: Env) -> None:
    env.stub("send_multisig_payment", ok())
    out = await env.run("handle_send_multisig_payment_expect_fail", **_multisig_ctx())
    assert "Unexpected success" in env.out and EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert env.last().success is True

    env2 = Env(env.tmp_path, env.mp)
    env2.stub("send_multisig_payment", ok(txid="", explorer=""))
    out2 = await env2.run("handle_send_multisig_payment_expect_fail", **_multisig_ctx())
    assert env2.records() == [] and "txids" not in out2
