"""wallet / fund / send / verify, plus module init and lint (authoring)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from xrpl.wallet import Wallet

import xrpl_lab.cli as cli
from tests.cov_cli._helpers import invoke, make_state
from xrpl_lab.errors import LabError, LabException
from xrpl_lab.linter import LintIssue
from xrpl_lab.state import load_state
from xrpl_lab.transport.base import FundResult, TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

REPO_MODULES = Path(__file__).resolve().parents[2] / "modules"


def _no_sleep(monkeypatch):
    import xrpl_lab.runtime as runtime

    async def _instant(_s):
        return None

    monkeypatch.setattr(runtime.asyncio, "sleep", _instant)


def _real_wallet(lab) -> Wallet:
    """Create + persist a real (random, testnet-format) wallet in the temp home."""
    from xrpl_lab.actions.wallet import save_wallet

    w = Wallet.create()
    path = save_wallet(w)
    make_state(wallet=w.address)
    assert Path(path).exists()
    return w


# ── wallet create / show ──────────────────────────────────────────────


def test_wallet_create_persists_the_seed_and_records_the_address(lab):
    r = invoke(["wallet", "create"])
    assert r.exit_code == 0, r.output
    assert "Wallet created!" in r.stdout
    assert "Never share your wallet seed" in r.stdout
    saved = json.loads((lab.home / "wallet.json").read_text(encoding="utf-8"))
    st = load_state()
    assert st.wallet_address == saved["address"]
    assert st.wallet_path == str(lab.home / "wallet.json")
    assert saved["address"] in r.stdout
    assert saved["seed"] not in r.stdout  # create must not echo the secret


def test_wallet_create_refuses_to_overwrite_an_existing_wallet(lab):
    first = invoke(["wallet", "create"])
    assert first.exit_code == 0
    before = (lab.home / "wallet.json").read_text(encoding="utf-8")
    again = invoke(["wallet", "create"])
    assert again.exit_code == 0
    assert "Wallet already exists" in again.stdout
    assert (lab.home / "wallet.json").read_text(encoding="utf-8") == before


def test_wallet_create_at_a_custom_path(lab):
    target = lab.work / "custom" / "w.json"
    target.parent.mkdir()
    r = invoke(["wallet", "create", "--path", str(target)])
    assert r.exit_code == 0, r.output
    assert target.exists()
    assert not (lab.home / "wallet.json").exists()
    assert load_state().wallet_path == str(target)
    again = invoke(["wallet", "create", "--path", str(target)])
    assert "already exists at this location" in again.stdout


@pytest.mark.parametrize(
    ("code", "exit_code"), [("PERM_WALLET_ACL_FAILED", 2), ("IO_DISK_FULL", 2)],
)
def test_wallet_create_save_failure_exits_with_taxonomy_code_and_saves_no_state(
    lab, monkeypatch, code, exit_code,
):
    def _boom(*_a, **_k):
        raise LabException(LabError(code=code, message="cannot save", hint="do X"))

    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", _boom)
    r = invoke(["wallet", "create"])
    assert r.exit_code == exit_code
    assert f"{code}:" in r.stdout and "do X" in r.stdout
    assert "Wallet created!" not in r.stdout
    assert load_state().wallet_address is None


def test_wallet_create_state_lock_failure_exits_1(lab, monkeypatch):
    def _locked(_state, **_k):
        from xrpl_lab.errors import state_locked

        raise LabException(state_locked())

    monkeypatch.setattr(cli, "save_state", _locked)
    r = invoke(["wallet", "create"])
    assert r.exit_code == 1  # STATE_LOCKED -> 1
    assert "STATE_LOCKED:" in r.stdout


def test_wallet_show_without_a_wallet(lab):
    r = invoke(["wallet", "show"])
    assert r.exit_code == 0
    assert "No wallet found. Run 'xrpl-lab wallet create' first." in r.stdout


def test_wallet_show_prints_address_and_public_key_but_never_the_seed(lab):
    w = _real_wallet(lab)
    r = invoke(["wallet", "show"])
    assert r.exit_code == 0
    assert w.address in r.stdout
    assert w.public_key in r.stdout
    assert w.seed not in r.stdout


# ── fund ──────────────────────────────────────────────────────────────


class _Faucet(DryRunTransport):
    def __init__(self, result: FundResult, balance: str = "0") -> None:
        super().__init__()
        self._result = result
        self._balance = balance
        self.requests: list[str] = []

    async def fund_from_faucet(self, address: str) -> FundResult:
        self.requests.append(address)
        return self._result

    async def get_balance(self, address: str) -> str:
        return self._balance


def _use(monkeypatch, transport) -> None:
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: transport)


def test_fund_without_a_wallet_is_state_error_exit_1(lab):
    r = invoke(["fund", "--dry-run"])
    assert r.exit_code == 1
    assert "No wallet found" in r.stdout


def test_fund_dry_run_reports_the_validated_balance(lab):
    make_state(wallet="rFUNDME")
    r = invoke(["fund", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "Funded! Balance: 1000" in r.stdout


def test_fund_accepted_but_not_yet_validated_is_a_soft_notice(lab, monkeypatch):
    _no_sleep(monkeypatch)
    make_state(wallet="rFUNDME")
    t = _Faucet(FundResult(success=True, address="rFUNDME"), balance="0")
    _use(monkeypatch, t)
    r = invoke(["fund"])
    assert r.exit_code == 0
    assert t.requests == ["rFUNDME"]
    assert "isn't on a validated ledger yet" in " ".join(r.stdout.split())
    assert "Funded!" not in r.stdout


def test_fund_rate_limited_gets_a_clock_banner_and_exit_2(lab, monkeypatch):
    make_state(wallet="rFUNDME")
    _use(monkeypatch, _Faucet(FundResult(
        success=False, address="rFUNDME", message="429",
        code="RUNTIME_FAUCET_RATE_LIMITED",
    )))
    r = invoke(["fund"])
    assert r.exit_code == 2  # RUNTIME_ -> 2
    assert "Faucet rate-limited (HTTP 429)." in r.stdout
    assert "--dry-run" in r.stdout


def test_fund_misconfigured_endpoint_names_the_fix_and_scrubs_credentials(
    lab, monkeypatch,
):
    make_state(wallet="rFUNDME")
    msg = "Refusing faucet https://bob:hunter2@evil.example/path?api_key=SECRET123"
    _use(monkeypatch, _Faucet(FundResult(
        success=False, address="rFUNDME", message=msg, code="CONFIG_NON_TESTNET",
    )))
    r = invoke(["fund"])
    assert r.exit_code == 1  # CONFIG_ -> 1
    assert "CONFIG_NON_TESTNET:" in r.stdout
    assert "XRPL_LAB_FAUCET_URL" in r.stdout
    for leaked in ("hunter2", "SECRET123", "api_key"):
        assert leaked not in r.stdout


def test_fund_generic_failure_exits_2_with_a_retry_hint(lab, monkeypatch):
    make_state(wallet="rFUNDME")
    _use(monkeypatch, _Faucet(FundResult(
        success=False, address="rFUNDME", message="faucet down",
    )))
    r = invoke(["fund"])
    assert r.exit_code == 2
    assert "Funding failed: faucet down" in r.stdout
    assert "xrpl-lab fund" in r.stdout


# ── send ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "needle"),
    [
        ("abc", "Invalid amount"),
        ("", "Invalid amount"),
        ("Infinity", "finite"),
        ("NaN", "finite"),
        ("-Infinity", "finite"),
        ("0", "must be positive"),
        ("-3", "must be positive"),
        ("100000000001", "exceeds the maximum XRP supply"),
        ("1e500", "exceeds the maximum XRP supply"),
    ],
)
def test_send_rejects_bad_amounts_before_touching_wallet_or_transport(
    lab, monkeypatch, amount, needle,
):
    def _never(*_a, **_k):
        raise AssertionError("transport must not be built for a rejected amount")

    monkeypatch.setattr(cli, "_get_transport", _never)
    r = invoke(["send", "--to", "rDEST", "--amount", amount])
    assert r.exit_code == 2
    assert needle in r.stdout


def test_send_requires_a_destination_and_an_amount(lab):
    assert invoke(["send", "--amount", "1"]).exit_code == 2
    assert invoke(["send", "--to", "rDEST"]).exit_code == 2


def test_send_without_a_wallet_is_state_error_exit_1(lab):
    r = invoke(["send", "--to", "rDEST", "--amount", "1", "--dry-run"])
    assert r.exit_code == 1
    assert "No wallet found" in r.stdout


def test_send_dry_run_payment_prints_the_receipt(lab, monkeypatch):
    w = _real_wallet(lab)
    t = DryRunTransport()
    asyncio.run(t.fund_from_faucet(w.address))
    _use(monkeypatch, t)
    dest = Wallet.create().address
    r = invoke(["send", "--to", dest, "--amount", "1.5", "--memo", "hi", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "Payment sent!" in r.stdout
    assert "TXID:" in r.stdout
    assert "Result: tesSUCCESS" in r.stdout


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: cli.send prints 'Payment failed' but exits 0 (only the amount and "
        "wallet guards exit non-zero), so a script's `send && next` treats a "
        "failed payment as success - the same defect PC-003 fixed for `fund`"
    ),
)
def test_send_failed_payment_exits_non_zero(lab, monkeypatch):
    w = _real_wallet(lab)
    t = DryRunTransport()
    asyncio.run(t.fund_from_faucet(w.address))
    t.set_fail_next()
    _use(monkeypatch, t)
    r = invoke(["send", "--to", Wallet.create().address, "--amount", "1", "--dry-run"])
    assert "Payment failed:" in r.stdout
    assert "Result code: tecUNFUNDED_PAYMENT" in r.stdout
    assert r.exit_code != 0


# ── verify ────────────────────────────────────────────────────────────


def _verify_ledger(monkeypatch, fixtures: dict[str, TxInfo]) -> None:
    t = DryRunTransport()
    t.set_tx_fixtures(fixtures)
    _use(monkeypatch, t)


def test_verify_passing_tx_lists_checks_and_details(lab, monkeypatch):
    _verify_ledger(monkeypatch, {"TXV1": TxInfo(
        txid="TXV1", tx_type="Payment", account="rFROM", destination="rTO",
        amount="1000000", result_code="tesSUCCESS", validated=True, fee="12",
        ledger_index=7, memos=["XRPLLAB|hello", "second"],
    )})
    r = invoke(["verify", "--tx", "TXV1", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "Verification passed!" in r.stdout
    assert "✓ Result: tesSUCCESS" in r.stdout
    assert "Type: Payment" in r.stdout
    assert "From: rFROM" in r.stdout
    assert "To: rTO" in r.stdout
    assert "Amount: 1000000" in r.stdout
    assert "Memos: XRPLLAB|hello, second" in r.stdout


def test_verify_failing_tx_exits_1_and_lists_the_failure(lab, monkeypatch):
    _verify_ledger(monkeypatch, {"TXV2": TxInfo(
        txid="TXV2", tx_type="OfferCreate", account="rFROM",
        result_code="tecUNFUNDED_OFFER", validated=True,
    )})
    r = invoke(["verify", "--tx", "TXV2", "--dry-run"])
    assert r.exit_code == 1
    assert "Verification failed." in r.stdout
    assert "✗ Expected tesSUCCESS, got tecUNFUNDED_OFFER" in r.stdout
    assert "To:" not in r.stdout  # no destination, no memos


def test_verify_unknown_txid_fails_without_inventing_details(lab, monkeypatch):
    _verify_ledger(monkeypatch, {})
    r = invoke(["verify", "--tx", "NO_SUCH_TX", "--dry-run"])
    assert r.exit_code == 1
    assert "Verification failed." in r.stdout


def test_verify_with_no_recorded_checks_says_so(lab, monkeypatch):
    from xrpl_lab.actions.verify import VerifyResult

    async def _empty(_transport, txid):
        return VerifyResult(
            passed=True, tx_info=TxInfo(txid=txid, tx_type="Payment"),
            checks=[], failures=[],
        )

    monkeypatch.setattr(cli, "verify_tx", _empty)
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: DryRunTransport())
    r = invoke(["verify", "--tx", "TXV3"])
    assert r.exit_code == 0
    assert "No checks or failures recorded for this transaction." in r.stdout


def test_verify_requires_the_tx_option(lab):
    assert invoke(["verify"]).exit_code == 2


# ── module init (scaffolder) ──────────────────────────────────────────


def test_module_init_creates_a_lint_clean_skeleton(lab):
    r = invoke([
        "module", "init", "--id", "my_new_module", "--track", "foundations",
        "--title", "My New Module", "--time", "15 min",
        "--level", "intermediate",
    ])
    assert r.exit_code == 0, r.output
    out = lab.work / "my_new_module.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "id: my_new_module" in text
    assert "title: My New Module" in text
    assert "level: intermediate" in text
    assert "mode: testnet" in text
    assert "Created:" in r.stdout
    assert "PASS" in r.stdout
    assert "xrpl-lab lint" in r.stdout


def test_module_init_dry_run_mode_is_written_and_linted_with_a_warning(lab):
    r = invoke([
        "module", "init", "--id", "sandbox_mod", "--track", "foundations",
        "--title", "Sandbox", "--time", "10 min", "--mode", "dry-run",
    ])
    assert r.exit_code == 0, r.output
    assert "mode: dry-run" in (lab.work / "sandbox_mod.md").read_text(encoding="utf-8")
    assert "[WARN] sandbox_mod: frontmatter" in r.stdout
    assert "dry_run_only" in " ".join(r.stdout.split())


def test_module_init_custom_outfile_and_unknown_requires_note(lab):
    target = lab.work / "sub" / "x.md"
    target.parent.mkdir()
    r = invoke([
        "module", "init", "--id", "needs_ghost", "--track", "foundations",
        "--title", "T", "--time", "5 min", "--requires", "ghost_mod, other_ghost",
        "--outfile", str(target),
    ])
    assert r.exit_code == 0, r.output
    assert target.exists()
    assert "requires references unknown modules: ghost_mod, other_ghost" in r.stdout.replace(
        "\n", " "
    )


@pytest.mark.parametrize("bad", ["Bad-Name", "1leading", "has space", "UPPER", ""])
def test_module_init_rejects_non_snake_case_ids(lab, bad):
    r = invoke([
        "module", "init", "--id", bad, "--track", "foundations",
        "--title", "T", "--time", "5 min",
    ])
    assert r.exit_code == 2
    assert "Invalid module ID" in r.stdout
    assert list(lab.work.glob("*.md")) == []


def test_module_init_rejects_an_id_already_in_the_catalog(lab):
    existing = next(iter(sorted(p.stem for p in REPO_MODULES.glob("*.md"))))
    r = invoke([
        "module", "init", "--id", existing, "--track", "foundations",
        "--title", "T", "--time", "5 min",
    ])
    assert r.exit_code == 2
    assert "already exists in the catalog" in r.stdout.replace("\n", " ")
    assert f"modules/{existing}.md" in r.stdout


def test_module_init_refuses_to_overwrite_a_file(lab):
    target = lab.work / "taken.md"
    target.write_text("KEEP ME", encoding="utf-8")
    r = invoke([
        "module", "init", "--id", "fresh_id", "--track", "foundations",
        "--title", "T", "--time", "5 min", "--outfile", str(target),
    ])
    assert r.exit_code == 2
    assert "Refusing to overwrite" in r.stdout.replace("\n", " ")
    assert target.read_text(encoding="utf-8") == "KEEP ME"


def test_module_init_unknown_track_is_a_usage_error(lab):
    r = invoke([
        "module", "init", "--id", "fresh_id", "--track", "no_such_track",
        "--title", "T", "--time", "5 min",
    ])
    assert r.exit_code == 2
    assert "Invalid value for '--track'" in r.output


def test_module_init_prints_lint_issues_in_error_and_warning_colours(lab, monkeypatch):
    monkeypatch.setattr(
        "xrpl_lab.linter.lint_module_file",
        lambda _p: [
            LintIssue("error", "m", "frontmatter", "bad field"),
            LintIssue("warning", "m", "step 1", "soft problem"),
        ],
    )
    r = invoke([
        "module", "init", "--id", "lint_me", "--track", "foundations",
        "--title", "T", "--time", "5 min",
    ])
    assert r.exit_code == 0
    assert "[ERROR] m: frontmatter — bad field" in r.stdout
    assert "[WARN] m: step 1 — soft problem" in r.stdout
    assert "PASS" not in r.stdout


# ── lint ──────────────────────────────────────────────────────────────


@pytest.fixture()
def modules_dir(lab) -> Path:
    dest = lab.work / "modules"
    shutil.copytree(REPO_MODULES, dest)
    return dest


def test_lint_with_no_matching_files(lab):
    text = invoke(["lint", "nothing/*.md"])
    assert text.exit_code == 0
    assert "No files matching 'nothing/*.md'" in text.stdout
    js = invoke(["lint", "nothing/*.md", "--json"])
    assert js.exit_code == 0
    assert json.loads(js.stdout) == {
        "passed": True, "errors": 0, "warnings": 0, "issues": [],
    }


def test_lint_full_catalog_passes_and_runs_curriculum_checks(modules_dir):
    n = len(list(modules_dir.glob("*.md")))
    r = invoke(["lint"])
    assert r.exit_code == 0, r.stdout
    assert f"Linted {n} module(s): 0 error(s)" in r.stdout
    assert "PASS" in r.stdout
    assert "skipped for this subset" not in r.stdout


def test_lint_strict_subset_skips_curriculum_validation(modules_dir):
    r = invoke(["lint", "modules/receipt*.md"])
    assert r.exit_code == 0, r.stdout
    assert "Curriculum checks" in r.stdout and "were skipped for this subset glob" in " ".join(
        r.stdout.split()
    )
    js = invoke(["lint", "modules/receipt*.md", "--json"])
    assert json.loads(js.stdout)["passed"] is True


def test_lint_reports_errors_and_exits_1(modules_dir):
    broken = modules_dir / "zz_broken.md"
    broken.write_text("no frontmatter at all\n", encoding="utf-8")
    text = invoke(["lint", "modules/zz_broken.md"])
    assert text.exit_code == 1
    assert "[ERROR]" in text.stdout
    assert "FAIL" in text.stdout

    js = invoke(["lint", "modules/zz_broken.md", "--json"])
    assert js.exit_code == 1
    d = json.loads(js.stdout)
    assert d["passed"] is False and d["errors"] >= 1
    assert all(i["level"] in {"error", "warning"} for i in d["issues"])


def test_lint_no_curriculum_flag_skips_cross_module_checks(modules_dir, monkeypatch):
    called = []
    monkeypatch.setattr(
        "xrpl_lab.linter.lint_curriculum", lambda *a, **k: called.append(1) or [],
    )
    assert invoke(["lint", "--no-curriculum"]).exit_code == 0
    assert called == []
    assert invoke(["lint"]).exit_code == 0
    assert called == [1]


def test_lint_curriculum_error_fails_the_run(modules_dir, monkeypatch):
    monkeypatch.setattr(
        "xrpl_lab.linter.lint_curriculum",
        lambda *a, **k: [LintIssue("error", "catalog", "cycle", "a -> b -> a")],
    )
    r = invoke(["lint"])
    assert r.exit_code == 1
    assert "a -> b -> a" in r.stdout


def test_lint_mentions_kb_cross_check_when_a_kb_is_available(modules_dir, monkeypatch):
    monkeypatch.setattr(
        "xrpl_lab.linter.load_kb_capability_slugs", lambda *a, **k: frozenset({"x", "y"}),
    )
    r = invoke(["lint", "modules/receipt*.md", "--no-curriculum"])
    assert "kb_source cross-check: validated against 2 xrpl-knowledge capability slugs" in (
        " ".join(r.stdout.split())
    )


def test_send_prints_the_explorer_link_when_the_transport_supplies_one(lab, monkeypatch):
    from xrpl_lab.transport.base import SubmitResult

    _real_wallet(lab)

    class _Explorer(DryRunTransport):
        async def submit_payment(self, *a, **k):
            return SubmitResult(
                success=True, txid="TXEXPL", result_code="tesSUCCESS",
                explorer_url="https://testnet.xrpl.org/transactions/TXEXPL",
            )

    _use(monkeypatch, _Explorer())
    r = invoke(["send", "--to", Wallet.create().address, "--amount", "2"])
    assert r.exit_code == 0, r.output
    assert "TXID: TXEXPL" in r.stdout
    assert "Explorer: https://testnet.xrpl.org/transactions/TXEXPL" in r.stdout
