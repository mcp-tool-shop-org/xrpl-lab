"""Learner-facing CLI commands: start, list, run, status, tracks, recovery, doctor.

Every test drives ``xrpl_lab.cli.main`` through ``CliRunner`` inside the
isolated ``lab`` fixture (see conftest.py). The module runner and transports
are stand-ins, so nothing touches the network.
"""

from __future__ import annotations

import json

import pytest

import xrpl_lab.cli as cli
from tests.cov_cli._helpers import (
    all_module_ids,
    fake_run_module,
    invoke,
    make_state,
    write_json,
)
from xrpl_lab.curriculum import build_graph
from xrpl_lab.doctor import Check, DoctorReport
from xrpl_lab.errors import LabError, LabException
from xrpl_lab.modules import load_all_modules
from xrpl_lab.state import load_state
from xrpl_lab.transport.dry_run import DryRunTransport

# ── _get_transport ────────────────────────────────────────────────────


def test_get_transport_dry_run_is_offline_transport():
    assert isinstance(cli._get_transport(True), DryRunTransport)


def test_get_transport_live_is_the_testnet_transport():
    from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

    t = cli._get_transport(False)
    assert isinstance(t, XRPLTestnetTransport)
    assert t.network_name == "testnet"


# ── XRPL Camp detection helpers ───────────────────────────────────────


def test_detect_camp_certificate_none_when_absent(lab):
    assert cli._detect_camp_certificate() is None


@pytest.mark.parametrize("where", ["cwd", "cwd_camp", "home_camp"])
def test_detect_camp_certificate_finds_each_location(lab, where):
    base = {
        "cwd": lab.work,
        "cwd_camp": lab.work / ".xrpl-camp",
        "home_camp": lab.user_home / ".xrpl-camp",
    }[where]
    base.mkdir(exist_ok=True)
    cert = base / "xrpl_camp_certificate.json"
    cert.write_text("{}", encoding="utf-8")
    assert cli._detect_camp_certificate() == cert


def test_detect_camp_certificate_prefers_cwd_over_home(lab):
    (lab.user_home / ".xrpl-camp").mkdir()
    (lab.user_home / ".xrpl-camp" / "xrpl_camp_certificate.json").write_text("{}")
    local = lab.work / "xrpl_camp_certificate.json"
    local.write_text("{}")
    assert cli._detect_camp_certificate() == local


def test_detect_camp_wallet_none_when_absent(lab):
    assert cli._detect_camp_wallet() is None


@pytest.mark.parametrize("where", ["cwd_camp", "home_camp"])
def test_detect_camp_wallet_finds_each_location(lab, where):
    base = {
        "cwd_camp": lab.work / ".xrpl-camp",
        "home_camp": lab.user_home / ".xrpl-camp",
    }[where]
    base.mkdir()
    w = base / "wallet.json"
    w.write_text("{}", encoding="utf-8")
    assert cli._detect_camp_wallet() == w


def _camp_wallet(lab, payload):
    d = lab.work / ".xrpl-camp"
    d.mkdir(exist_ok=True)
    p = d / "wallet.json"
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        write_json(p, payload)
    return p


def test_try_import_returns_false_without_a_camp_wallet(lab):
    state = load_state()
    assert cli._try_import_camp_wallet(state) is False
    assert state.wallet_address is None


def test_try_import_skips_when_lab_wallet_already_exists(lab):
    from xrpl_lab.actions.wallet import create_wallet, save_wallet

    save_wallet(create_wallet())
    _camp_wallet(lab, {"seed": "sEdSKaCy2JT7JaM7v95H9SxkhP9wS2r"})
    state = load_state()
    assert cli._try_import_camp_wallet(state) is False
    assert state.wallet_address is None


def test_try_import_false_for_seedless_camp_wallet(lab):
    _camp_wallet(lab, {"address": "rCAMP"})
    assert cli._try_import_camp_wallet(load_state()) is False


def test_try_import_false_for_malformed_camp_wallet(lab):
    _camp_wallet(lab, "{not json")
    assert cli._try_import_camp_wallet(load_state()) is False


def test_try_import_false_for_invalid_seed(lab):
    _camp_wallet(lab, {"seed": "definitely-not-a-seed"})
    state = load_state()
    assert cli._try_import_camp_wallet(state) is False
    assert state.wallet_address is None


def test_try_import_saves_wallet_and_state(lab):
    from xrpl.wallet import Wallet

    camp = Wallet.create()
    _camp_wallet(lab, {"seed": camp.seed})
    state = load_state()
    assert cli._try_import_camp_wallet(state) is True
    assert state.wallet_address == camp.address
    assert (lab.home / "wallet.json").exists()
    assert load_state().wallet_address == camp.address


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [("PERM_WALLET_ACL_FAILED", 2), ("STATE_LOCKED", 1)],
)
def test_try_import_structured_error_exits_with_taxonomy_code(
    lab, monkeypatch, capsys, code, exit_code,
):
    from xrpl.wallet import Wallet

    _camp_wallet(lab, {"seed": Wallet.create().seed})

    def _boom(*_a, **_k):
        raise LabException(LabError(code=code, message="boom msg", hint="fix hint"))

    monkeypatch.setattr("xrpl_lab.actions.wallet.save_wallet", _boom)
    with pytest.raises(SystemExit) as exc:
        cli._try_import_camp_wallet(load_state())
    assert exc.value.code == exit_code
    out = capsys.readouterr().out
    assert code in out
    assert "boom msg" in out
    assert "fix hint" in out


# ── start ─────────────────────────────────────────────────────────────


@pytest.fixture()
def runner_calls(monkeypatch):
    """Replace the real module runner and the transport factory."""
    calls: list[dict] = []
    monkeypatch.setattr("xrpl_lab.runner.run_module", fake_run_module(calls))
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: DryRunTransport())
    return calls


def _first_module():
    modules = load_all_modules()
    return modules[build_graph(modules).next_module(set())]


def test_start_declining_does_not_run_a_module(lab, runner_calls):
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0
    assert "dry-run (offline sandbox)" in r.output
    assert "No XRPL Camp certificate found" in r.output
    assert "Available modules:" in r.output
    assert f"Next up: {_first_module().title}" in r.output
    assert runner_calls == []
    assert load_state().completed_modules == []


def test_start_default_answer_runs_the_next_module_in_dry_run(lab, runner_calls):
    r = invoke(["start", "--dry-run"], input="\n")
    assert r.exit_code == 0, r.output
    assert [c["module"] for c in runner_calls] == [_first_module().id]
    assert runner_calls[0]["dry_run"] is True
    assert isinstance(runner_calls[0]["transport"], DryRunTransport)
    assert load_state().is_module_completed(_first_module().id)


def test_start_testnet_mode_label_when_not_dry_run(lab, runner_calls):
    r = invoke(["start"], input="n\n")
    assert r.exit_code == 0
    assert "Network: XRPL Testnet" in r.output
    assert "Offline sandbox:" not in r.output


def test_start_eof_on_prompt_says_bye(lab, runner_calls):
    r = invoke(["start", "--dry-run"], input="")
    assert r.exit_code == 0
    assert "Bye!" in r.output
    assert runner_calls == []


def test_start_exits_3_when_the_run_completed_with_failed_steps(lab, monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "xrpl_lab.runner.run_module", fake_run_module(calls, verified=False),
    )
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: DryRunTransport())
    r = invoke(["start", "--dry-run"], input="y\n")
    assert r.exit_code == 3, r.output
    assert "exiting with code 3" in r.output


def test_start_shows_done_and_todo_labels_and_requires(lab, runner_calls):
    ids = all_module_ids()
    make_state(completed=ids[:1])
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0
    assert "✓ done" in r.output
    assert "◌ todo" in r.output
    assert "Track:" in r.output and "Mode:" in r.output


def test_start_with_everything_completed_points_at_proof_pack(lab, runner_calls):
    make_state(completed=all_module_ids())
    r = invoke(["start", "--dry-run"], input="")
    assert r.exit_code == 0
    assert "All modules completed!" in r.output
    assert "proof-pack" in r.output
    assert "Start this module?" not in r.output


def test_start_exits_1_when_no_modules_are_installed(lab, monkeypatch):
    monkeypatch.setattr(cli, "load_all_modules", lambda: {})
    r = invoke(["start"], input="")
    assert r.exit_code == 1
    assert "No modules found" in r.output


def test_start_reports_a_camp_certificate_and_its_address(lab, runner_calls):
    write_json(
        lab.work / "xrpl_camp_certificate.json", {"address": "rCAMPADDRESS1"},
    )
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0
    assert "XRPL Camp certificate found" in r.output
    assert "rCAMPADDRESS1" in r.output
    assert "No XRPL Camp certificate found" not in r.output


def test_start_warns_when_lab_wallet_differs_from_camp_address(lab, runner_calls):
    make_state(wallet="rLABWALLET")
    write_json(lab.work / "xrpl_camp_certificate.json", {"address": "rCAMPADDRESS1"})
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0
    assert "Lab is using a different wallet" in r.output


def test_start_tolerates_a_corrupt_camp_certificate(lab, runner_calls):
    (lab.work / "xrpl_camp_certificate.json").write_text("{nope", encoding="utf-8")
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0
    assert "Available modules:" in r.output
    assert "XRPL Camp certificate found" not in r.output


def test_start_imports_the_camp_wallet_into_lab_state(lab, runner_calls):
    from xrpl.wallet import Wallet

    camp = Wallet.create()
    write_json(lab.work / "xrpl_camp_certificate.json", {"address": camp.address})
    _camp_wallet(lab, {"seed": camp.seed})
    r = invoke(["start", "--dry-run"], input="n\n")
    assert r.exit_code == 0, r.output
    assert "XRPL Camp wallet imported" in r.output
    assert camp.address in r.output
    assert load_state().wallet_address == camp.address
    assert (lab.home / "wallet.json").exists()


# ── list ──────────────────────────────────────────────────────────────


def test_list_marks_done_unverified_next_and_todo(lab):
    ids = list(build_graph(load_all_modules()).canonical_order())
    make_state(completed=ids[:2], unverified=(ids[1],))
    r = invoke(["list"])
    assert r.exit_code == 0
    assert "✓" in r.output  # proven completion
    assert "⚠" in r.output  # completed but unverified
    assert "unverified" in r.output
    assert "→" in r.output  # next up
    assert "·" in r.output  # todo


# ── run ───────────────────────────────────────────────────────────────


def test_run_unknown_module_exits_1_and_lists_available(lab, runner_calls):
    r = invoke(["run", "no_such_module"])
    assert r.exit_code == 1
    assert "Module 'no_such_module' not found" in r.output
    assert all_module_ids()[0] in r.output
    assert runner_calls == []


def test_run_completed_module_needs_force(lab, runner_calls):
    mid = all_module_ids()[0]
    make_state(completed=[mid])
    r = invoke(["run", mid, "--dry-run"])
    assert r.exit_code == 0
    assert "already completed" in r.output
    assert "--force" in r.output
    assert runner_calls == []


def test_run_force_reruns_a_completed_module(lab, runner_calls):
    mid = all_module_ids()[0]
    make_state(completed=[mid])
    r = invoke(["run", mid, "--dry-run", "--force"])
    assert r.exit_code == 0, r.output
    assert runner_calls == [{
        "module": mid, "transport": runner_calls[0]["transport"],
        "dry_run": True, "force": True,
    }]


def test_run_executes_a_fresh_module_and_records_completion(lab, runner_calls):
    mid = all_module_ids()[0]
    r = invoke(["run", mid, "--dry-run"])
    assert r.exit_code == 0, r.output
    assert runner_calls[0]["force"] is False
    assert load_state().is_module_completed(mid)


def test_run_exits_3_for_a_module_that_completed_unverified(lab, monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        "xrpl_lab.runner.run_module", fake_run_module(calls, verified=False),
    )
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: DryRunTransport())
    mid = all_module_ids()[0]
    r = invoke(["run", mid, "--dry-run"])
    assert r.exit_code == 3
    assert f"'{mid}' completed with failed steps; exiting with code 3." in r.output


def test_run_stopped_early_keeps_exit_zero(lab, monkeypatch):
    calls: list = []
    monkeypatch.setattr("xrpl_lab.runner.run_module", fake_run_module(calls, ok=False))
    monkeypatch.setattr(cli, "_get_transport", lambda dry_run=False: DryRunTransport())
    mid = all_module_ids()[0]
    r = invoke(["run", mid, "--dry-run"])
    assert r.exit_code == 0
    assert not load_state().is_module_completed(mid)


def test_exit_if_unverified_is_silent_for_verified_and_missing_modules(lab, capsys):
    make_state(completed=["alpha"])
    cli._exit_if_unverified("alpha", True, cli.console)  # verified -> no exit
    cli._exit_if_unverified("never_ran", True, cli.console)  # no record -> no exit
    assert capsys.readouterr().out == ""


# ── status ────────────────────────────────────────────────────────────


def test_status_json_is_the_learner_status_shape(lab):
    ids = all_module_ids()
    make_state(completed=ids[:1], unverified=(ids[0],), tx=[("A", ids[0], False)])
    r = invoke(["status", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["wallet_address"] == "rLEARNER123"
    assert data["completed_count"] == 1
    assert data["total_modules"] == len(ids)
    assert data["all_verified"] is False
    assert data["unverified_modules"] == [ids[0]]
    assert data["failed_transactions"] == 1


def test_status_fresh_install_nudges_to_start_and_flags_missing_wallet(lab):
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "Wallet: not created yet" in r.output
    assert "Run xrpl-lab start to begin." in r.output
    assert "✗" in r.output  # missing wallet is a hard blocker
    assert "Proof pack: no" in r.output and "Certificate: no" in r.output


def test_status_shows_endpoint_overrides(lab, monkeypatch):
    monkeypatch.setenv("XRPL_LAB_RPC_URL", "wss://s.altnet.rippletest.net:51233")
    monkeypatch.setenv("XRPL_LAB_FAUCET_URL", "https://faucet.altnet.rippletest.net/accounts")
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "RPC endpoint:" in r.output and "(override)" in r.output
    assert "Faucet:" in r.output


def test_status_all_done_with_unverified_tx_artifacts_and_activity(lab):
    ids = all_module_ids()
    make_state(
        completed=ids, unverified=(ids[2],),
        tx=[("A", ids[0], True), ("B", ids[0], False)],
    )
    (lab.ws / "reports").mkdir(parents=True)
    (lab.ws / "reports" / "r1.md").write_text("# r", encoding="utf-8")
    (lab.ws / "proofs").mkdir()
    (lab.ws / "proofs" / "xrpl_lab_proof_pack.json").write_text("{}", encoding="utf-8")
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "All modules completed!" in r.output
    assert "DONE" in r.output
    assert f"Last completed: {ids[-1]}" in r.output
    assert "Transactions: 2 (1 ok, 1 failed)" in r.output
    assert "1 module(s) completed but UNVERIFIED" in r.output
    assert f"Unverified: {ids[2]}" in r.output
    assert "Reports: 1" in r.output
    assert "Proof pack: yes" in r.output


def test_status_partial_progress_shows_active_and_todo_tracks(lab):
    ids = list(build_graph(load_all_modules()).canonical_order())
    make_state(completed=ids[:1])
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "ACTIVE" in r.output
    assert "TODO" in r.output
    assert f"Progress: 1/{len(ids)} modules" in r.output
    assert "Next up:" in r.output


# ── tracks ────────────────────────────────────────────────────────────


def test_tracks_lists_done_unverified_and_todo_modules(lab):
    ids = list(build_graph(load_all_modules()).canonical_order())
    make_state(
        completed=ids[:2], unverified=(ids[1],),
        tx=[("TXA", ids[0], True)],
    )
    r = invoke(["tracks"])
    assert r.exit_code == 0
    assert "Tracks" in r.output
    assert f"✓ done  {ids[0]}" in r.output
    assert f"⚠ done (unverified)  {ids[1]}" in r.output
    assert "◌ todo" in r.output
    assert "Transactions: 1" in r.output


def test_tracks_complete_track_is_marked_done(lab):
    make_state(completed=all_module_ids())
    r = invoke(["tracks"])
    assert r.exit_code == 0
    assert "✓ DONE" in r.output
    assert "◌ todo" not in r.output


def test_tracks_reports_artifacts_and_skills_for_completed_modules(lab):
    ids = list(build_graph(load_all_modules()).canonical_order())
    make_state(completed=ids[:1])
    (lab.ws / "reports").mkdir(parents=True)
    (lab.ws / "reports" / f"{ids[0]}.md").write_text("# r", encoding="utf-8")
    r = invoke(["tracks"])
    assert r.exit_code == 0
    assert f"Reports: {ids[0]}.md" in r.output


# ── recovery ──────────────────────────────────────────────────────────


def test_recovery_with_a_wallet_and_a_clean_state_reports_no_blockers(lab):
    ids = list(build_graph(load_all_modules()).canonical_order())
    # complete everything with a proof pack present -> nothing to recover from
    make_state(completed=ids)
    (lab.ws / "proofs").mkdir(parents=True)
    (lab.ws / "proofs" / "xrpl_lab_proof_pack.json").write_text("{}", encoding="utf-8")
    r = invoke(["recovery"])
    assert r.exit_code == 0
    assert "No known blockers found." in r.output
    assert "xrpl-lab start" in r.output


def test_recovery_without_a_wallet_names_the_command(lab):
    r = invoke(["recovery"])
    assert r.exit_code == 0
    assert "Recovery" in r.output
    assert "No wallet yet" in r.output
    assert "xrpl-lab wallet create" in r.output


# ── doctor / self-check rendering ─────────────────────────────────────


def _patch_doctor(monkeypatch, checks):
    async def _fake():
        return DoctorReport(checks=checks)

    monkeypatch.setattr("xrpl_lab.doctor.run_doctor", _fake)


def test_doctor_hard_failure_shows_cross_and_hint(lab, monkeypatch):
    _patch_doctor(monkeypatch, [
        Check("Alpha", True, "alpha detail"),
        Check("Beta", False, "beta broke", "run the beta fix"),
    ])
    r = invoke(["doctor"])
    assert r.exit_code == 0
    assert "✓ Alpha" in r.output
    assert "✗ Beta" in r.output
    assert "run the beta fix" in r.output
    assert "1/2 checks passed — needs attention." in r.output


def test_doctor_warn_only_is_all_good_with_notes(lab, monkeypatch):
    _patch_doctor(monkeypatch, [
        Check("Alpha", True, "ok"),
        Check("Drift", False, "drifted", "see docs", severity="warn"),
    ])
    r = invoke(["doctor"])
    assert r.exit_code == 0
    assert "! Drift" in r.output
    assert "see docs" in r.output
    assert "all good (see notes above)." in r.output
    assert "needs attention" not in r.output


def test_doctor_all_passing_is_all_good(lab, monkeypatch):
    _patch_doctor(monkeypatch, [Check("Alpha", True, "ok", "hidden hint")])
    r = invoke(["doctor"])
    assert r.exit_code == 0
    assert "1/1 checks passed — all good." in r.output
    assert "hidden hint" not in r.output  # a plain pass hides its hint


def test_self_check_is_a_deprecated_alias_noting_on_stderr(lab, monkeypatch):
    _patch_doctor(monkeypatch, [Check("Alpha", True, "ok")])
    r = invoke(["self-check"])
    assert r.exit_code == 0
    assert r.stderr == "`self-check` is deprecated, use `doctor`.\n"
    assert "1/1 checks passed — all good." in r.stdout


# ── proof-pack / certificate (export commands) ────────────────────────


@pytest.mark.parametrize("cmd", [["proof-pack"], ["proof", "generate"], ["certificate"]])
def test_export_commands_nudge_when_nothing_is_completed(lab, cmd):
    r = invoke(cmd)
    assert r.exit_code == 0
    assert "No completed modules yet. Nothing to export." in r.output
    assert "xrpl-lab start" in r.output
    assert not (lab.ws / "proofs").exists()


@pytest.mark.parametrize(
    ("cmd", "filename", "marker"),
    [
        (["proof-pack"], "xrpl_lab_proof_pack.json", "xrpl_lab_proof_pack"),
        (["proof", "generate"], "xrpl_lab_proof_pack.json", "xrpl_lab_proof_pack"),
        (["certificate"], "xrpl_lab_certificate.json", "xrpl_lab_certificate"),
    ],
)
def test_export_commands_write_a_hash_valid_artifact(lab, cmd, filename, marker):
    from xrpl_lab.reporting import verify_certificate, verify_proof_pack

    ids = all_module_ids()
    make_state(completed=ids[:2], tx=[("TXH1", ids[0], True)])
    r = invoke(cmd)
    assert r.exit_code == 0, r.output
    path = lab.ws / "proofs" / filename
    assert path.exists()
    assert filename in r.stdout.replace("\n", "")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body[marker] is True
    verify = verify_proof_pack if marker == "xrpl_lab_proof_pack" else verify_certificate
    assert verify(body) == (True, "Integrity verified")
    if cmd == ["proof", "generate"]:
        assert r.stderr == "`proof generate` is deprecated, use `proof-pack`.\n"


def test_status_mode_hint_blocker_is_amber_not_red(lab):
    """A 'runs offline' hint is guidance, not a hard block: warn glyph, not cross."""
    modules = load_all_modules()
    graph = build_graph(modules)
    order = list(graph.canonical_order())
    done = None
    for i in range(len(order)):
        nxt = graph.next_module(set(order[:i]))
        if nxt and modules[nxt].mode == "dry-run" and all(
            r in order[:i] for r in modules[nxt].requires
        ):
            done = order[:i]
            break
    if done is None:
        pytest.skip("no dry-run-only module is reachable as 'next up'")
    make_state(completed=done)
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "⚠" in r.output and "runs offline — add --dry-run" in r.output
    assert "✗" not in r.output


def test_status_skips_tracks_that_have_no_modules(lab, monkeypatch):
    from xrpl_lab import workshop

    real = workshop.get_learner_status

    def _with_empty_track(*a, **k):
        ls = real(*a, **k)
        ls.track_progress.append(workshop.TrackProgress(
            track="ghost_track", completed=[], remaining=[], total=0, done=0,
            is_complete=False,
        ))
        return ls

    monkeypatch.setattr(workshop, "get_learner_status", _with_empty_track)
    r = invoke(["status"])
    assert r.exit_code == 0
    assert "ghost_track" not in r.output
    assert "TODO" in r.output  # the real tracks still render
