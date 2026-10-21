"""Wallet, payment, verify-tx, issuer, trust-line and freeze handlers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import xrpl_lab.handlers as handlers
from xrpl_lab.errors import LabError, LabException
from xrpl_lab.transport.base import FundResult

from ._h import EXPLORER, FAILED_TXID, TXID, Env, bad, checks_result, ok, secret, verdict

ISSUER = "rISSUERADDRESS123"


# -- _print_lab_error / _require --


def test_print_lab_error_shows_code_message_and_hint(env: Env) -> None:
    handlers._print_lab_error(
        env.console, LabError(code="X_CODE", message="it broke", hint="try again"),
    )
    assert "X_CODE: it broke" in env.out
    assert "Hint: try again" in env.out


def test_print_lab_error_omits_an_empty_hint(env: Env) -> None:
    handlers._print_lab_error(env.console, LabError(code="X_CODE", message="m", hint=""))
    assert "X_CODE: m" in env.out
    assert "Hint:" not in env.out


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_require_rejects_missing_or_blank(raw) -> None:
    with pytest.raises(LabException) as ei:
        handlers._require({"k": raw}, {}, "k", action="act", hint="do this")
    assert ei.value.error.code == "INPUT_REQUIRED_FIELD"
    assert "'k'" in ei.value.error.message and "'act'" in ei.value.error.message
    assert ei.value.error.hint == "do this"


def test_require_falls_back_to_context_and_strips() -> None:
    assert handlers._require({}, {"k": "  v "}, "k", action="a", hint="h") == "v"
    assert handlers._require({"k": 5}, {"k": "no"}, "k", action="a", hint="h") == "5"


# -- ensure_funded --


@pytest.mark.asyncio
async def test_ensure_funded_records_failed_verification_when_unfunded(env: Env) -> None:
    calls = env.stub("ensure_funded", False)
    out = await env.run("handle_ensure_funded")
    assert len(calls) == 1
    v = verdict(out, "ensure_funded")
    assert v["passed"] is False
    assert v["failures"] == ["wallet not funded on a validated ledger"]


@pytest.mark.asyncio
async def test_ensure_funded_records_nothing_when_funded(env: Env) -> None:
    env.stub("ensure_funded", True)
    out = await env.run("handle_ensure_funded")
    assert "verifications" not in out


@pytest.mark.asyncio
async def test_ensure_funded_skips_without_a_wallet_address(env: Env) -> None:
    env.state.wallet_address = None
    calls = env.stub("ensure_funded", False)
    out = await env.run("handle_ensure_funded")
    assert calls == []
    assert "verifications" not in out


@pytest.mark.asyncio
async def test_ensure_wallet_stores_the_wrapped_seed(env: Env) -> None:
    wrapped = secret("sWRAPPED")
    env.stub("ensure_wallet", (env.state, wrapped))
    out = await env.run("handle_ensure_wallet")
    assert out["wallet_seed"] is wrapped


# -- submit_payment --


@pytest.mark.asyncio
async def test_submit_payment_success_shows_fee_result_and_explorer(env: Env) -> None:
    calls = env.stub("send_payment", ok())
    out = await env.run(
        "handle_submit_payment",
        {"destination": "rDEST", "amount": "7", "memo": "hi {timestamp}"},
    )
    (args, _), = calls
    assert args[2:4] == ("rDEST", "7")
    assert args[4].startswith("hi ") and "{timestamp}" not in args[4]
    assert out["last_submit"].txid == TXID
    assert out["txids"] == [TXID]
    assert "Fee: 12 drops" in env.out and "Result: tesSUCCESS" in env.out
    assert EXPLORER in env.out
    assert env.last().success is True


@pytest.mark.asyncio
async def test_submit_payment_failure_keeps_the_failed_hash(env: Env) -> None:
    env.stub("send_payment", bad(code="tecUNFUNDED_PAYMENT", error="short of XRP"))
    out = await env.run("handle_submit_payment", {"destination": "rDEST"})
    assert "Payment failed: short of XRP" in env.out
    assert "Result code: tecUNFUNDED_PAYMENT" in env.out
    assert out["failed_txids"] == [
        {"result_code": "tecUNFUNDED_PAYMENT", "error": "short of XRP"}
    ]
    assert "txids" not in out
    assert env.last().success is False and env.last().txid == FAILED_TXID


@pytest.mark.asyncio
async def test_submit_payment_failure_without_hash_is_indexed_failed(env: Env) -> None:
    env.stub("send_payment", bad(txid=""))
    await env.run("handle_submit_payment", {"destination": "rDEST"})
    assert env.last().txid == "failed"


@pytest.mark.asyncio
async def test_submit_payment_with_no_destination_uses_a_practice_address(env: Env) -> None:
    """2.6.1: XRPL rejects a payment to yourself (temREDUNDANT), so the
    practice payment goes to a fresh address made for the run."""
    calls = env.stub("send_payment", ok())
    await env.run("handle_submit_payment")
    (args, _), = calls
    assert args[2] != "rLEARNER" and args[2].startswith("r")
    assert args[2] == env.ctx["practice_recipient"]
    assert "temREDUNDANT" in env.out


@pytest.mark.asyncio
async def test_submit_payment_with_no_destination_and_no_wallet_raises(env: Env) -> None:
    env.state.wallet_address = None
    calls = env.stub("send_payment", ok())
    with pytest.raises(LabException) as ei:
        await env.run("handle_submit_payment")
    assert ei.value.error.code == "INPUT_REQUIRED_FIELD"
    assert "destination" in ei.value.error.message
    assert calls == []  # nothing was submitted


@pytest.mark.asyncio
async def test_submit_payment_real_dry_run_transport(env: Env) -> None:
    out = await env.run("handle_submit_payment", {"destination": "rDEST", "amount": "1"})
    assert len(out["txids"]) == 1
    assert env.last().txid == out["txids"][0]
    assert env.last().success is True


# -- submit_payment_fail --


@pytest.mark.asyncio
async def test_submit_payment_fail_arms_the_transport_and_records_the_failure(env: Env) -> None:
    out = await env.run("handle_submit_payment_fail", {"reason": "bad_sequence"})
    assert "Intentionally submitting a failing tx (bad_sequence)" in env.out
    (failed,) = out["failed_txids"]
    assert failed["result_code"]
    assert f"Result code: {failed['result_code']}" in env.out
    assert out["last_submit"].success is False


@pytest.mark.asyncio
async def test_submit_payment_fail_unexpected_success_is_indexed(env: Env) -> None:
    env.transport = type("Bare", (), {})()  # no arming hook on this transport
    env.stub("send_payment", ok())
    out = await env.run("handle_submit_payment_fail", {"destination": "rDEST"})
    assert "Unexpected success" in env.out
    assert EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert "failed_txids" not in out
    assert env.last().success is True and env.last().explorer_url == EXPLORER
    assert env.saved == 1


@pytest.mark.asyncio
async def test_submit_payment_fail_unexpected_success_without_explorer(env: Env) -> None:
    env.stub("send_payment", ok(explorer=""))
    await env.run("handle_submit_payment_fail")
    assert "Explorer:" not in env.out
    assert env.last().success is True


@pytest.mark.asyncio
async def test_submit_payment_fail_works_on_a_transport_without_the_hook(env: Env) -> None:
    class Bare:
        pass

    env.transport = Bare()
    env.stub("send_payment", bad(code="tecUNFUNDED_PAYMENT", error="e"))
    out = await env.run("handle_submit_payment_fail")
    assert out["failed_txids"][0]["result_code"] == "tecUNFUNDED_PAYMENT"
    assert "Error: e" in env.out


# -- verify_tx --


@pytest.mark.asyncio
async def test_verify_tx_without_a_txid_is_a_failed_verification(env: Env) -> None:
    out = await env.run("handle_verify_tx")
    assert "No transaction to verify yet" in env.out
    v = verdict(out, "verify_tx")
    assert v["passed"] is False
    assert "txid missing" in v["failures"][0]


@pytest.mark.asyncio
async def test_verify_tx_passes_and_prints_checks(env: Env) -> None:
    calls = env.stub("verify_tx", SimpleNamespace(checks=["tx found"], failures=[]))
    out = await env.run("handle_verify_tx", txids=["T0", "T1"])
    assert calls[0][0][1] == "T1"  # the latest txid
    assert "tx found" in env.out
    assert verdict(out, "verify_tx") == {"action": "verify_tx", "passed": True, "failures": []}


@pytest.mark.asyncio
async def test_verify_tx_failure_is_recorded(env: Env) -> None:
    env.stub("verify_tx", SimpleNamespace(checks=["seen"], failures=["wrong result"]))
    out = await env.run("handle_verify_tx", txids=["T1"])
    assert "wrong result" in env.out
    v = verdict(out, "verify_tx")
    assert v["passed"] is False and v["failures"] == ["wrong result"]


# -- issuer wallet --


@pytest.mark.asyncio
async def test_create_issuer_wallet_creates_then_reuses(env: Env) -> None:
    out = await env.run("handle_create_issuer_wallet")
    assert "Issuer wallet created" in env.out
    address = out["issuer_address"]
    seed = out["issuer_seed"].get()
    path = env.tmp_path / ".xrpl-lab" / "issuer_wallet.json"
    assert path.exists()
    assert address in path.read_text(encoding="utf-8")

    # A second run reuses the same issuer instead of orphaning its trust lines.
    env2 = Env(env.tmp_path, env.mp)
    out2 = await env2.run("handle_create_issuer_wallet")
    assert out2["issuer_address"] == address
    assert out2["issuer_seed"].get() == seed
    assert "Reusing existing issuer wallet" in env2.out
    assert "account_hygiene" in env2.out
    assert "Issuer wallet created" not in env2.out
    assert json.loads(path.read_text(encoding="utf-8")) is not None


@pytest.mark.asyncio
async def test_fund_issuer_without_an_issuer(env: Env) -> None:
    out = await env.run("handle_fund_issuer")
    assert "No issuer wallet found" in env.out
    assert "verifications" not in out


@pytest.mark.asyncio
async def test_fund_issuer_success(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address=ISSUER))
    env.stub("await_validated_balance", 100)
    out = await env.run("handle_fund_issuer", issuer_address=ISSUER)
    assert "Issuer funded! Balance: 100 XRP" in env.out
    assert "verifications" not in out


@pytest.mark.asyncio
async def test_fund_issuer_faucet_answers_but_never_validates(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address=ISSUER))
    env.stub("await_validated_balance", 0)
    out = await env.run("handle_fund_issuer", issuer_address=ISSUER)
    assert "hasn't appeared on a validated ledger" in env.out
    assert "re-running this module" in env.out
    v = verdict(out, "fund_issuer")
    assert v["passed"] is False
    assert v["failures"] == ["issuer account not funded on a validated ledger"]


@pytest.mark.asyncio
async def test_fund_issuer_rate_limited_points_at_dry_run(env: Env) -> None:
    env.on_transport(
        "fund_from_faucet",
        FundResult(success=False, address=ISSUER, code="RUNTIME_FAUCET_RATE_LIMITED"),
    )
    out = await env.run("handle_fund_issuer", issuer_address=ISSUER)
    assert "RUNTIME_FAUCET_RATE_LIMITED" in env.out
    assert "--dry-run" in env.out
    assert "Funding failed" not in env.out
    assert verdict(out, "fund_issuer")["passed"] is False


@pytest.mark.asyncio
async def test_fund_issuer_generic_failure_sanitizes_endpoints(env: Env) -> None:
    env.on_transport(
        "fund_from_faucet",
        FundResult(
            success=False, address=ISSUER,
            message="boom at https://user:secret@faucet.example.test/path",
        ),
    )
    out = await env.run("handle_fund_issuer", issuer_address=ISSUER)
    assert "Funding failed: boom" in env.out
    assert "secret@" not in env.out
    assert "re-running this module" in env.out
    assert verdict(out, "fund_issuer")["passed"] is False


# -- _fund_new_wallet --


@pytest.mark.asyncio
async def test_fund_new_wallet_quiet_success_prints_nothing(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="rN"))
    env.stub("await_validated_balance", 50)
    got = await handlers._fund_new_wallet(
        env.transport, "rN", "Receiver", env.console, env.ctx, "act", quiet=True,
    )
    assert got is True
    assert "funded" not in env.out


@pytest.mark.asyncio
async def test_fund_new_wallet_loud_success(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="rN"))
    env.stub("await_validated_balance", 50)
    got = await handlers._fund_new_wallet(
        env.transport, "rN", "Receiver", env.console, env.ctx, "act",
    )
    assert got is True
    assert "Receiver funded! Balance: 50 XRP" in env.out


@pytest.mark.asyncio
async def test_fund_new_wallet_unvalidated_is_a_failed_step(env: Env) -> None:
    env.on_transport("fund_from_faucet", FundResult(success=True, address="rN"))
    env.stub("await_validated_balance", 0)
    got = await handlers._fund_new_wallet(
        env.transport, "rN", "Receiver", env.console, env.ctx, "act",
    )
    assert got is False
    assert "receiver wallet rN hasn't appeared" in env.out
    assert verdict(env.ctx, "act")["failures"] == [
        "receiver wallet not funded on a validated ledger"
    ]


@pytest.mark.asyncio
async def test_fund_new_wallet_rate_limited(env: Env) -> None:
    env.on_transport(
        "fund_from_faucet",
        FundResult(success=False, address="rN", code="RUNTIME_FAUCET_RATE_LIMITED"),
    )
    got = await handlers._fund_new_wallet(
        env.transport, "rN", "Issuer", env.console, env.ctx, "act",
    )
    assert got is False
    assert "RUNTIME_FAUCET_RATE_LIMITED" in env.out
    assert verdict(env.ctx, "act")["passed"] is False


@pytest.mark.asyncio
async def test_fund_new_wallet_generic_failure(env: Env) -> None:
    env.on_transport(
        "fund_from_faucet", FundResult(success=False, address="rN", message="faucet down"),
    )
    got = await handlers._fund_new_wallet(
        env.transport, "rN", "Issuer", env.console, env.ctx, "act",
    )
    assert got is False
    assert "Issuer funding: faucet down" in env.out
    assert verdict(env.ctx, "act")["failures"] == [
        "issuer wallet not funded on a validated ledger"
    ]


# -- set_trust_line / issue_token / remove_trust_line extras --


@pytest.mark.asyncio
async def test_set_trust_line_requires_a_currency(env: Env) -> None:
    calls = env.stub("set_trust_line", ok())
    with pytest.raises(LabException) as ei:
        await env.run("handle_set_trust_line", {"currency": ""}, issuer_address=ISSUER)
    assert ei.value.error.code == "INPUT_REQUIRED_FIELD"
    assert calls == []


@pytest.mark.asyncio
async def test_set_trust_line_without_an_issuer_does_not_submit(env: Env) -> None:
    calls = env.stub("set_trust_line", ok())
    out = await env.run("handle_set_trust_line", {"currency": "LAB"})
    assert calls == []
    assert "No issuer address in context" in env.out
    assert env.records() == [] and "txids" not in out


@pytest.mark.asyncio
async def test_set_trust_line_passes_limit_and_wallet(env: Env) -> None:
    calls = env.stub("set_trust_line", ok())
    await env.run("handle_set_trust_line", {"currency": "USD", "limit": "55"},
                  issuer_address=ISSUER)
    (args, kwargs), = calls
    assert args[2:] == (ISSUER, "USD", "55")
    assert kwargs == {"wallet_address": "rLEARNER"}
    assert "Limit: 55" in env.out


@pytest.mark.asyncio
async def test_set_trust_line_tecno_line_gets_the_directional_hint(env: Env) -> None:
    env.stub("set_trust_line", bad(code="tecNO_LINE", error="no line"))
    await env.run("handle_set_trust_line", {"currency": "LAB"}, issuer_address=ISSUER)
    assert "Trust lines are directional" in env.out


@pytest.mark.asyncio
async def test_set_trust_line_other_failure_has_no_directional_hint(env: Env) -> None:
    env.stub("set_trust_line", bad(code="tecINSUF_RESERVE_LINE", error="no reserve"))
    await env.run("handle_set_trust_line", {"currency": "LAB"}, issuer_address=ISSUER)
    assert "Trust line failed: no reserve" in env.out
    assert "directional" not in env.out


@pytest.mark.asyncio
async def test_issue_token_needs_issuer_and_holder(env: Env) -> None:
    calls = env.stub("issue_token", ok())
    await env.run("handle_issue_token", issuer_address=ISSUER)
    assert calls == []
    assert "Missing issuer or holder wallet" in env.out

    env.state.wallet_address = None
    await env.run("handle_issue_token", issuer_seed=secret("sISS"))
    assert calls == []


@pytest.mark.asyncio
async def test_issue_token_accepts_a_plain_string_seed_and_sends_memo(env: Env) -> None:
    calls = env.stub("issue_token", ok())
    await env.run(
        "handle_issue_token", {"currency": "GLD", "amount": "9"},
        issuer_seed="sPLAIN", issuer_address=ISSUER,
    )
    (args, kwargs), = calls
    assert args[1] == "sPLAIN"
    assert args[2:5] == ("rLEARNER", "GLD", ISSUER)
    assert kwargs["memo"] == "XRPLLAB|ISSUE|GLD|9"
    assert "9 GLD issued!" in env.out


@pytest.mark.asyncio
async def test_issue_token_expect_fail_needs_wallets(env: Env) -> None:
    calls = env.stub("issue_token", bad())
    out = await env.run("handle_issue_token_expect_fail")
    assert calls == []
    assert "Missing issuer or holder wallet" in env.out
    assert "failed_txids" not in out


@pytest.mark.asyncio
async def test_issue_token_expect_fail_teaches_the_code(env: Env) -> None:
    env.stub("issue_token", bad(code="tecNO_LINE", error="no trust line"))
    out = await env.run(
        "handle_issue_token_expect_fail", issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert "Expected failure: tecNO_LINE" in env.out
    assert "Error: no trust line" in env.out
    assert "Category:" in env.out and "Meaning:" in env.out and "Action:" in env.out
    assert out["failed_txids"] == [{"result_code": "tecNO_LINE", "error": "no trust line"}]
    assert env.last().success is False and env.last().txid == FAILED_TXID


@pytest.mark.asyncio
async def test_issue_token_expect_fail_failure_without_hash(env: Env) -> None:
    env.stub("issue_token", bad(txid=""))
    await env.run(
        "handle_issue_token_expect_fail", issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert env.last().txid == "failed"


@pytest.mark.asyncio
async def test_issue_token_expect_fail_unexpected_success_is_indexed(env: Env) -> None:
    env.stub("issue_token", ok())
    out = await env.run(
        "handle_issue_token_expect_fail", {"currency": "DBG", "amount": "3"},
        issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert "Unexpected success" in env.out and EXPLORER in env.out
    assert out["txids"] == [TXID]
    assert "failed_txids" not in out
    assert env.last().success is True and env.last().explorer_url == EXPLORER


@pytest.mark.asyncio
async def test_issue_token_expect_fail_unexpected_success_without_a_hash(env: Env) -> None:
    env.stub("issue_token", ok(txid="", explorer=""))
    out = await env.run(
        "handle_issue_token_expect_fail", issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert env.records() == []  # never mints a {"failed", success=True} record
    assert "txids" not in out


# -- verify_trust_line --


@pytest.mark.asyncio
async def test_verify_trust_line_without_a_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_trust_line")
    assert "No wallet address found" in env.out
    assert verdict(out, "verify_trust_line")["passed"] is False


@pytest.mark.asyncio
async def test_verify_trust_line_found_with_a_failure_fails(env: Env) -> None:
    res = checks_result(found=True, checks=["line exists"], failures=["limit too low"])
    calls = env.stub("verify_trust_line", res)
    out = await env.run("handle_verify_trust_line", {"currency": "GLD"}, issuer_address=ISSUER)
    assert calls[0][1] == {"expected_issuer": ISSUER}
    assert "line exists" in env.out and "limit too low" in env.out
    assert verdict(out, "verify_trust_line") == {
        "action": "verify_trust_line", "passed": False, "failures": ["limit too low"],
    }
    assert out["last_trust_line_verify"] is res


@pytest.mark.asyncio
async def test_verify_trust_line_not_found_prints_only_failures(env: Env) -> None:
    res = checks_result(found=False, checks=["should not show"], failures=["no line"])
    env.stub("verify_trust_line", res)
    out = await env.run("handle_verify_trust_line")
    assert "no line" in env.out and "should not show" not in env.out
    assert verdict(out, "verify_trust_line")["passed"] is False


@pytest.mark.asyncio
async def test_verify_trust_line_found_clean_passes(env: Env) -> None:
    env.stub("verify_trust_line", checks_result(found=True, checks=["ok"]))
    out = await env.run("handle_verify_trust_line")
    assert verdict(out, "verify_trust_line")["passed"] is True


# -- remove_trust_line / verify_trust_line_removed --


@pytest.mark.asyncio
async def test_remove_trust_line_without_an_issuer(env: Env) -> None:
    calls = env.stub("remove_trust_line", ok())
    await env.run("handle_remove_trust_line")
    assert calls == []
    assert "No issuer address in context" in env.out


@pytest.mark.asyncio
async def test_remove_trust_line_issuer_override_wins(env: Env) -> None:
    calls = env.stub("remove_trust_line", ok())
    await env.run(
        "handle_remove_trust_line", {"issuer": " rPEER ", "currency": "OLD"},
        issuer_address=ISSUER,
    )
    assert calls[0][0][2] == "rPEER"
    assert "Peer (issuer override): rPEER" in env.out
    assert "Trust line removed" in env.out


@pytest.mark.asyncio
async def test_remove_trust_line_balance_failure_hints_at_returning_tokens(env: Env) -> None:
    env.stub("remove_trust_line", bad(error="Line still has a Balance"))
    await env.run("handle_remove_trust_line", issuer_address=ISSUER)
    assert "send tokens back to issuer" in env.out


@pytest.mark.asyncio
async def test_verify_trust_line_removed_no_wallet(env: Env) -> None:
    env.state.wallet_address = None
    out = await env.run("handle_verify_trust_line_removed")
    assert verdict(out, "verify_trust_line_removed")["passed"] is False


@pytest.mark.asyncio
async def test_verify_trust_line_removed_passes_when_gone(env: Env) -> None:
    calls = env.stub(
        "verify_trust_line_removed", checks_result(found=False, checks=["line is gone"]),
    )
    out = await env.run(
        "handle_verify_trust_line_removed", {"issuer": "rPEER"}, issuer_address=ISSUER,
    )
    assert calls[0][1] == {"expected_issuer": "rPEER"}
    assert "Verifying removal against peer (issuer override): rPEER" in env.out
    assert "line is gone" in env.out
    assert verdict(out, "verify_trust_line_removed")["passed"] is True


@pytest.mark.asyncio
async def test_verify_trust_line_removed_fails_when_still_there(env: Env) -> None:
    env.stub("verify_trust_line_removed", checks_result(found=True, failures=["still present"]))
    out = await env.run("handle_verify_trust_line_removed")
    assert "still present" in env.out
    v = verdict(out, "verify_trust_line_removed")
    assert v["passed"] is False and v["failures"] == ["still present"]


# -- freeze --


def test_parse_bool_arg() -> None:
    assert handlers._parse_bool_arg(None) is None
    for yes in ("true", "TRUE", "1", "yes", " on "):
        assert handlers._parse_bool_arg(yes) is True
    for no in ("false", "0", "no", "off", ""):
        assert handlers._parse_bool_arg(no) is False


@pytest.mark.asyncio
async def test_set_freeze_needs_issuer_and_holder(env: Env) -> None:
    calls = env.stub("set_individual_freeze", ok())
    await env.run("handle_set_freeze")
    assert calls == []
    assert "Missing issuer or holder wallet" in env.out


@pytest.mark.asyncio
async def test_set_freeze_unfreeze_wording_and_flag(env: Env) -> None:
    calls = env.stub("set_individual_freeze", ok())
    await env.run(
        "handle_set_freeze", {"freeze": "false", "currency": "GLD"},
        issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert calls[0][0][4] is False
    assert "Unfreezing the holder's GLD trust line" in env.out
    assert "Individual freeze cleared!" in env.out


@pytest.mark.asyncio
async def test_set_freeze_freeze_wording(env: Env) -> None:
    calls = env.stub("set_individual_freeze", ok())
    await env.run("handle_set_freeze", issuer_seed=secret("sISS"), issuer_address=ISSUER)
    assert calls[0][0][4] is True
    assert "Freezing the holder's GLD trust line" in env.out
    assert "Individual freeze set!" in env.out


@pytest.mark.asyncio
async def test_set_global_freeze_needs_an_issuer(env: Env) -> None:
    calls = env.stub("set_global_freeze", ok())
    await env.run("handle_set_global_freeze")
    assert calls == []
    assert "No issuer wallet" in env.out


@pytest.mark.asyncio
async def test_set_global_freeze_clear_wording(env: Env) -> None:
    calls = env.stub("set_global_freeze", ok())
    await env.run(
        "handle_set_global_freeze", {"enable": "false"},
        issuer_seed=secret("sISS"), issuer_address=ISSUER,
    )
    assert calls[0][0][2] is False
    assert "Clearing Global Freeze" in env.out and "Global freeze cleared!" in env.out


@pytest.mark.asyncio
async def test_verify_freeze_passes_through_expectations(env: Env) -> None:
    res = checks_result(checks=["line frozen"])
    calls = env.stub("verify_freeze", res)
    out = await env.run(
        "handle_verify_freeze", {"expect_individual": "true", "expect_global": "no"},
        issuer_address=ISSUER,
    )
    assert calls[0][1] == {"expect_individual": True, "expect_global": False}
    assert "line frozen" in env.out
    assert out["last_freeze_verify"] is res
    assert verdict(out, "verify_freeze")["passed"] is True


@pytest.mark.asyncio
async def test_verify_freeze_failure(env: Env) -> None:
    env.stub("verify_freeze", checks_result(passed=False, failures=["not frozen"]))
    out = await env.run("handle_verify_freeze")
    assert "not frozen" in env.out
    assert verdict(out, "verify_freeze") == {
        "action": "verify_freeze", "passed": False, "failures": ["not frozen"],
    }
