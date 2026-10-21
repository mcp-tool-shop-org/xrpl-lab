"""2.7.4 (#28): the defects the 2.7.3 full live sweep found.

Book Keeper ran all 32 lessons in one home, in curriculum order, on testnet:
- custodial_crediting_101 left ``asfRequireDest`` on the learner, so every
  later untagged payment to the learner validated ``tecDST_TAG_NEEDED``;
- clawback_101 reused the shared issuer, which by then owned objects, so
  enabling clawback validated ``tecOWNERS``;
- checks_101's 50 XRP Check met a learner holding 49.99967 XRP
  (``tecPATH_PARTIAL``);
- mpt_distribution_101's issuance was signed by the learner, who then
  couldn't hold it (``tecNO_PERMISSION``);
- account_hygiene's currency code ``HYGIENE`` is invalid (xrpl-py refuses it
  before signing), and the dry run accepted it;
- a never-submitted record (txid ``failed``) verified as "not found on the
  public ledger".

Each CLI dry run starts a fresh ledger, so the interference cases are tested
here in one process, on one ledger, the way the sweep ran them.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers
import xrpl_lab.runtime as runtime
from tests.cov_testnet import _fakes
from xrpl_lab.modules import ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import FundResult, SubmitResult, TrustLineInfo
from xrpl_lab.transport.dry_run import DryRunTransport
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

LEARNER = "rLEARNER"


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, no_color=True, width=200), buf


async def _run_course(
    filenames: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> DryRunTransport:
    """Run shipped lessons in order in one home, on one ledger; assert each verified."""
    import xrpl_lab.runner as runner_mod
    import xrpl_lab.state as state_mod
    from tests._shipped_module import MODULES_DIR
    from xrpl_lab.modules import parse_module

    monkeypatch.setattr(state_mod, "DEFAULT_HOME_DIR", tmp_path)
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(state_mod, "DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
    monkeypatch.chdir(tmp_path)  # the shared issuer file is workspace-relative
    transport = DryRunTransport()
    for name in filenames:
        mod = parse_module((MODULES_DIR / name).read_text(encoding="utf-8"))
        console, buf = _console()
        console.input = lambda *a, **k: ""
        assert await runner_mod.run_module(mod, transport, dry_run=True, console=console), name
        cm = next(m for m in state_mod.load_state().completed_modules
                  if m.module_id == mod.id)
        assert cm.verified is True, f"{name}:\n{buf.getvalue()}"
    return transport


# ── Item 1: custodial_crediting_101 clears RequireDest ─────────────────


@pytest.mark.asyncio
async def test_custodial_leaves_require_dest_off(tmp_path, monkeypatch) -> None:
    from tests._shipped_module import run_shipped_module

    out, transport = await run_shipped_module(
        "custodial_crediting_101.md", tmp_path, monkeypatch)
    assert transport._require_dest == set()
    assert "untagged payments to your wallet are accepted again" in out


@pytest.mark.asyncio
async def test_a_lesson_after_custodial_can_pay_the_learner(tmp_path, monkeypatch) -> None:
    """The sweep's case: deposit_gate_101 after custodial, in one home."""
    await _run_course(
        ["custodial_crediting_101.md", "deposit_gate_101.md"], tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_ensure_funded_warns_when_require_dest_was_left_on(monkeypatch) -> None:
    async def _funded(*args, **kwargs):
        return True

    monkeypatch.setattr(handlers, "ensure_funded", _funded)
    t = DryRunTransport()
    t._require_dest.add(LEARNER)
    step = ModuleStep(text="x", action="ensure_funded", action_args={})
    for module_id, warned in (("amm_liquidity_101", True), ("custodial_crediting_101", False)):
        console, buf = _console()
        await handlers.handle_ensure_funded(
            step, LabState(wallet_address=LEARNER), t, "", {"module_id": module_id}, console)
        assert ("RequireDest is on" in buf.getvalue()) is warned


@pytest.mark.asyncio
async def test_a_failed_clear_fails_the_step_when_the_read_back_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "save_state", lambda state: None)

    async def _fail(*args, **kwargs):
        return SubmitResult(success=False, result_code="local_error", error="timed out")

    async def _unknown(address):
        return None

    monkeypatch.setattr(handlers, "enable_require_dest", _fail)
    t = DryRunTransport()
    monkeypatch.setattr(t, "get_require_dest", _unknown)
    console, buf = _console()
    step = ModuleStep(text="x", action="disable_require_dest", action_args={})
    ctx = await handlers.handle_disable_require_dest(
        step, LabState(wallet_address=LEARNER), t, "sSEED", {"module_id": "m"}, console)
    assert "Clearing it failed" in buf.getvalue()
    assert [v["failures"] for v in ctx["verifications"]] == [
        ["ClearFlag asfRequireDest did not succeed"]]


@pytest.mark.asyncio
async def test_a_flag_still_set_fails_the_step(monkeypatch) -> None:
    monkeypatch.setattr(handlers, "save_state", lambda state: None)

    async def _ok(*args, **kwargs):
        return SubmitResult(success=True, txid="A" * 64, result_code="tesSUCCESS")

    async def _on(address):
        return True

    monkeypatch.setattr(handlers, "enable_require_dest", _ok)
    t = DryRunTransport()
    monkeypatch.setattr(t, "get_require_dest", _on)
    console, _ = _console()
    step = ModuleStep(text="x", action="disable_require_dest", action_args={})
    ctx = await handlers.handle_disable_require_dest(
        step, LabState(wallet_address=LEARNER), t, "sSEED", {"module_id": "m"}, console)
    assert [v["failures"] for v in ctx["verifications"]] == [
        ["lsfRequireDestTag still set after the cleanup"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("flags", "expected"), [(0x00020000, True), (0x01000000, False)])
async def test_the_testnet_transport_reads_require_dest(monkeypatch, flags, expected) -> None:
    _fakes.install(monkeypatch, results={
        "AccountInfo": {"account_data": {"Account": LEARNER, "Flags": flags}},
    })
    assert await XRPLTestnetTransport().get_require_dest(LEARNER) is expected


@pytest.mark.asyncio
async def test_an_unreadable_account_is_unknown(monkeypatch) -> None:
    _fakes.install(monkeypatch, results={"AccountInfo": {"error": "actNotFound"}})
    assert await XRPLTestnetTransport().get_require_dest(LEARNER) is None


@pytest.mark.asyncio
async def test_an_rpc_error_reads_as_unknown(monkeypatch) -> None:
    import xrpl_lab.transport.xrpl_testnet as xt

    class _Down:
        async def __aenter__(self):
            raise ConnectionError("rpc down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(xt, "_rpc_client", lambda url: _Down())
    assert await XRPLTestnetTransport().get_require_dest(LEARNER) is None


@pytest.mark.asyncio
async def test_the_base_transport_does_not_know_require_dest() -> None:
    from xrpl_lab.transport.base import Transport

    assert await Transport.get_require_dest(DryRunTransport(), LEARNER) is None


# ── Item 2: clawback_101 uses an issuer of its own ─────────────────────


@pytest.mark.asyncio
async def test_clawback_after_a_lesson_that_used_the_shared_issuer(tmp_path, monkeypatch) -> None:
    """The sweep's case: the shared issuer already has a trust line to it."""
    await _run_course(["trust_lines_101.md", "clawback_101.md"], tmp_path, monkeypatch)
    assert (tmp_path / ".xrpl-lab" / "issuer_wallet.json").exists()  # the shared one stays


@pytest.mark.asyncio
async def test_a_fresh_issuer_is_not_saved_to_the_shared_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    console, _ = _console()
    step = ModuleStep(text="x", action="create_issuer_wallet", action_args={"fresh": "true"})
    ctx = await handlers.handle_create_issuer_wallet(
        step, LabState(), DryRunTransport(), "", {}, console)
    assert ctx["issuer_address"]
    assert not (tmp_path / ".xrpl-lab" / "issuer_wallet.json").exists()


@pytest.mark.asyncio
async def test_the_dry_run_refuses_clawback_for_an_issuer_that_owns_objects() -> None:
    t = DryRunTransport()
    t._trust_lines["rHOLDER"] = [
        TrustLineInfo(account="rHOLDER", peer="rISSUER", currency="GLD", balance="0")]
    r = await t.submit_account_set_clawback("sISSUER", issuer_address="rISSUER")
    assert (r.success, r.result_code) == (False, "tecOWNERS")
    t2 = DryRunTransport()
    t2._owner_counts["rISSUER"] = 1
    r2 = await t2.submit_account_set_clawback("sISSUER", issuer_address="rISSUER")
    assert r2.result_code == "tecOWNERS"


# ── Item 3: checks_101 tops the learner up ─────────────────────────────


class _Faucet:
    def __init__(self, balances: list[str], ok: bool = True) -> None:
        self._balances = balances
        self._ok = ok
        self.calls = 0

    async def get_balance(self, address: str) -> str:
        return self._balances.pop(0) if len(self._balances) > 1 else self._balances[0]

    async def fund_from_faucet(self, address: str) -> FundResult:
        self.calls += 1
        return FundResult(success=self._ok, address=address)


@pytest.mark.asyncio
async def test_a_wallet_below_the_floor_is_topped_up(monkeypatch) -> None:
    monkeypatch.setattr(runtime.asyncio, "sleep", _no_sleep)
    t = _Faucet(["49.99967", "49.99967", "149.99967"])
    console, buf = _console()
    assert await runtime.ensure_funded(LabState(), t, LEARNER, console, min_xrp=Decimal(60))
    assert t.calls == 1
    assert "Topped up! Balance: 149.99967 XRP" in buf.getvalue()


@pytest.mark.asyncio
async def test_a_wallet_at_the_floor_is_left_alone() -> None:
    t = _Faucet(["75"])
    console, _ = _console()
    assert await runtime.ensure_funded(LabState(), t, LEARNER, console, min_xrp=Decimal(60))
    assert t.calls == 0


@pytest.mark.asyncio
async def test_a_refused_top_up_still_runs_the_lesson(monkeypatch) -> None:
    monkeypatch.setattr(runtime.asyncio, "sleep", _no_sleep)
    t = _Faucet(["40"], ok=False)
    console, buf = _console()
    assert await runtime.ensure_funded(LabState(), t, LEARNER, console, min_xrp=Decimal(60))
    assert t.calls == 3  # retried like first funding (Argon, round 1, F3)
    assert "didn't top the wallet up" in buf.getvalue()


@pytest.mark.asyncio
async def test_a_top_up_retries_a_transient_failure(monkeypatch) -> None:
    monkeypatch.setattr(runtime.asyncio, "sleep", _no_sleep)
    t = _Faucet(["40", "40", "140"])
    answers = iter([False, True])

    async def _flaky(address):
        t.calls += 1
        return FundResult(success=next(answers), address=address)

    t.fund_from_faucet = _flaky
    console, buf = _console()
    assert await runtime.ensure_funded(LabState(), t, LEARNER, console, min_xrp=Decimal(60))
    assert t.calls == 2
    assert "Topped up! Balance: 140 XRP" in buf.getvalue()


@pytest.mark.asyncio
async def test_a_top_up_that_never_lands_says_so(monkeypatch) -> None:
    monkeypatch.setattr(runtime.asyncio, "sleep", _no_sleep)
    t = _Faucet(["40"])
    console, buf = _console()
    assert await runtime.ensure_funded(LabState(), t, LEARNER, console, min_xrp=Decimal(60))
    assert "hasn't reached a validated ledger yet" in buf.getvalue()


@pytest.mark.asyncio
async def test_the_handler_passes_min_xrp(monkeypatch) -> None:
    seen = []

    async def _funded(state, transport, address, console, min_xrp=None):
        seen.append(min_xrp)
        return True

    monkeypatch.setattr(handlers, "ensure_funded", _funded)
    for args in ({"min_xrp": "60"}, {"min_xrp": "lots"}, {}):
        console, _ = _console()
        step = ModuleStep(text="x", action="ensure_funded", action_args=args)
        await handlers.handle_ensure_funded(
            step, LabState(wallet_address=LEARNER), DryRunTransport(), "",
            {"module_id": "checks_101"}, console)
    assert seen == [Decimal(60), None, None]


def test_checks_101_asks_for_the_floor() -> None:
    from xrpl_lab.modules import load_all_modules

    step = next(s for s in load_all_modules()["checks_101"].steps if s.action == "ensure_funded")
    assert step.action_args.get("min_xrp") == "60"


async def _no_sleep(_seconds: float) -> None:
    return None


# ── Item 4: mpt_distribution_101's issuer wallet signs the issuance ────


@pytest.mark.asyncio
async def test_mpt_distribution_runs_clean(tmp_path, monkeypatch) -> None:
    await _run_course(["mpt_distribution_101.md"], tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_an_issuer_cannot_hold_its_own_mpt() -> None:
    t = DryRunTransport()
    t.bind_wallet("sLEARNER", LEARNER)
    t._funded_addresses.add(LEARNER)
    t._balances[LEARNER] = 100_000_000
    created = await t.submit_mpt_issuance_create("sLEARNER", "1000")
    r = await t.submit_mpt_authorize(
        "sLEARNER", created.mpt_issuance_id, holder_address=LEARNER)
    assert (r.success, r.result_code) == (False, "tecNO_PERMISSION")


@pytest.mark.asyncio
async def test_signer_issuer_needs_an_issuer_wallet() -> None:
    console, buf = _console()
    step = ModuleStep(text="x", action="create_mpt_issuance", action_args={"signer": "issuer"})
    await handlers.handle_create_mpt_issuance(
        step, LabState(), DryRunTransport(), "", {"module_id": "m"}, console)
    assert "No issuer wallet in context" in buf.getvalue()


# ── Items 5 and 7: currency codes ──────────────────────────────────────


@pytest.mark.asyncio
async def test_account_hygiene_runs_clean(tmp_path, monkeypatch) -> None:
    await _run_course(["account_hygiene.md"], tmp_path, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize(("code", "ok"), [
    ("HYG", True), ("HYGIENE", False), ("XRP", False), ("AB", False),
    (b"HYGIENE".hex().upper().ljust(40, "0"), True),
])
async def test_the_dry_run_checks_currency_codes(code, ok) -> None:
    t = DryRunTransport()
    r = await t.submit_trust_set("sSEED", "rISSUER", code, "100")
    assert (r.result_code != "local_error") is ok
    if not ok:
        assert "Invalid currency code" in r.error


@pytest.mark.asyncio
async def test_the_dry_run_checks_issued_payments_and_offers() -> None:
    t = DryRunTransport()
    pay = await t.submit_issued_payment("sSEED", "rHOLDER", "HYGIENE", "rISSUER", "1")
    assert pay.result_code == "local_error"
    offer = await t.submit_offer_create("sSEED", "HYGIENE", "10", "rISSUER", "XRP", "1", "")
    assert offer.result_code == "local_error"


# ── Item 6: a never-submitted record says so ───────────────────────────


@pytest.mark.asyncio
async def test_a_never_submitted_record_has_a_clear_reason() -> None:
    from xrpl_lab.reporting import LIVE_FAIL, _verify_one_tx_live

    r = await _verify_one_tx_live(
        "failed", "testnet", DryRunTransport(), claim={"success": False})
    assert r.status == LIVE_FAIL
    assert "before its transaction reached the network" in r.reason


# ── Argon, 2.7.4 round 1: F1 and F2 ────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "code"), [
    ("_require_dest", "tecDST_TAG_NEEDED"), ("_deposit_auth", "tecNO_PERMISSION"),
])
async def test_token_payments_respect_the_destination_flags(gate, code) -> None:
    """F1: the network gates every incoming Payment, issued and MPT included."""
    t = DryRunTransport()
    t.bind_wallet("sISSUER", "rISSUER")
    getattr(t, gate).add(LEARNER)
    issued = await t.submit_issued_payment("sISSUER", LEARNER, "GLD", "rISSUER", "10")
    mpt = await t.submit_mpt_payment("sISSUER", LEARNER, "0" * 48, "10")
    assert (issued.result_code, mpt.result_code) == (code, code)


@pytest.mark.asyncio
async def test_a_preauthorized_issuer_passes_deposit_auth() -> None:
    t = DryRunTransport()
    t.bind_wallet("sISSUER", "rISSUER")
    t._deposit_auth.add(LEARNER)
    t._deposit_preauth_addr.setdefault(LEARNER, set()).add("rISSUER")
    r = await t.submit_issued_payment("sISSUER", LEARNER, "GLD", "rISSUER", "10")
    assert r.result_code != "tecNO_PERMISSION"


@pytest.mark.asyncio
async def test_more_token_paths_check_currency_codes() -> None:
    """F2: clawback, freeze, token escrow and AMM legs refuse a bad code too."""
    t = DryRunTransport()
    results = [
        await t.submit_clawback("sISSUER", "rHOLDER", "GOLD", "1"),
        await t.submit_set_freeze("sISSUER", "rHOLDER", "GOLD", True),
        await t.submit_amm_create("sSEED", "XRP", "10", "", "GOLD", "10", "rISSUER"),
        await t.submit_amm_deposit("sSEED", "XRP", "10", "", "GOLD", "10", "rISSUER"),
        await t.submit_amm_withdraw("sSEED", "XRP", "", "GOLD", "rISSUER"),
        await t.submit_partial_payment(
            "sISSUER", "rHOLDER", "GOLD", "rISSUER", "10", "1", "1"),
        await t.submit_token_escrow_create(
            "sSEED", "GOLD", "rISSUER", "1", "rDEST", 9_999_999_999),
        await t.submit_permissioned_offer_create(
            "sSEED", "GOLD", "1", "rISSUER", "XRP", "1", "", "D" * 64),
        await t.submit_nft_create_offer("sSEED", "0" * 64, "1", currency="GOLD"),
    ]
    assert [r.result_code for r in results] == ["local_error"] * 9


def test_an_xrp_leg_is_not_a_currency_code() -> None:
    from xrpl_lab.transport.dry_run import _leg_currency_error

    assert _leg_currency_error("XRP", "GLD") is None
    assert _leg_currency_error("XRP", "GOLD").result_code == "local_error"


@pytest.mark.asyncio
async def test_untagged_creates_to_a_require_dest_account_fail() -> None:
    """EscrowCreate, CheckCreate and PaymentChannelCreate are gated too."""
    t = DryRunTransport()
    t._require_dest.add(LEARNER)
    results = [
        await t.submit_escrow_create("sSEED", "10", LEARNER, 9_999_999_999),
        await t.submit_check_create("sSEED", LEARNER, "10"),
        await t.submit_payment_channel_create("sSEED", "10", LEARNER, 60, "ED" + "0" * 64),
    ]
    assert [r.result_code for r in results] == ["tecDST_TAG_NEEDED"] * 3
    tagged = await t.submit_check_create("sSEED", LEARNER, "10", destination_tag=7)
    assert tagged.result_code != "tecDST_TAG_NEEDED"


# ── Book Keeper, 2.7.4 live sweep: a --force rerun, and the HYG line ───


def test_a_rerun_replaces_the_verdict_and_keeps_the_txids() -> None:
    """clawback_101: a failed first run (a faucet 429), then a passing --force rerun."""
    state = LabState()
    state.complete_module("clawback_101", txids=["A"], report_path="r1", verified=False)
    state.complete_module("clawback_101", txids=["A", "B"], report_path="r2", verified=True)
    [record] = state.completed_modules
    assert (record.verified, record.txids, record.report_path) == (True, ["A", "B"], "r2")
    state.complete_module("clawback_101", txids=["C"], verified=False)
    [record] = state.completed_modules
    assert (record.verified, record.txids, record.report_path) == (False, ["A", "B", "C"], "r2")


@pytest.mark.asyncio
@pytest.mark.parametrize(("account_flags", "limit", "expected"), [
    (0, "0", 0x00020000),           # tfSetNoRipple: no DefaultRipple on the account
    (0x00800000, "0", 0x00040000),  # tfClearNoRipple: the default with DefaultRipple
    (0, "100", 0),                  # not a removal: no flag
])
async def test_a_removal_puts_no_ripple_back_to_the_default(
    monkeypatch, account_flags, limit, expected,
) -> None:
    env = _fakes.install(monkeypatch, results={
        "AccountInfo": {"account_data": {"Account": _fakes.ADDR, "Flags": account_flags}},
    })
    await XRPLTestnetTransport().submit_trust_set(_fakes.SEED, "rISSUER" + "x" * 26, "HYG", limit)
    assert int(env.xrpl().get("Flags", 0)) == expected


@pytest.mark.asyncio
async def test_a_bad_seed_on_removal_is_a_local_error(monkeypatch) -> None:
    _fakes.install(monkeypatch)
    r = await XRPLTestnetTransport().submit_trust_set("not-a-seed", "rISSUER", "HYG", "0")
    assert (r.success, r.result_code) == (False, "local_error")
