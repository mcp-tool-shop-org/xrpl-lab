"""CLI smoke tests — offline only."""

from unittest.mock import MagicMock

from click.testing import CliRunner

from xrpl_lab.cli import main


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    from xrpl_lab import __version__
    assert __version__ in result.output


def test_list():
    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    # Rich table truncates IDs — check shorter prefixes after Mode column added
    assert "receipt_" in result.output
    assert "failure_" in result.output
    assert "trust_li" in result.output
    assert "dex_lite" in result.output or "dex_lit" in result.output
    assert "reserves" in result.output
    assert "account_" in result.output
    assert "amm_liqu" in result.output or "amm_liq" in result.output
    assert "dex_mark" in result.output
    assert "dex_inve" in result.output or "dex_inv" in result.output
    assert "dex_vs_a" in result.output
    # Mode column shows testnet and dry-run
    assert "testnet" in result.output
    assert "dry-run" in result.output


def test_status(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Status" in result.output


# ── F-TESTS-C-002: pin status pedagogical contract ────────────────────


class TestStatusOutputPedagogy:
    """Pin the curriculum-position language of `xrpl-lab status`.

    The status command is the learner's main "where am I?" surface.
    A refactor that drops "Next up:" / "Progress: N/M modules" / track
    progress / wallet-blocker pedagogy would silently regress the
    onboarding contract. Pin the load-bearing labels.
    """

    def test_status_fresh_install_pins_curriculum_position(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

        # Section header: a learner reading this should see "Status".
        assert "Status" in result.output
        # Curriculum position summary: progress fraction is part of the
        # pedagogical contract — learner sees how many modules total.
        assert "Progress:" in result.output
        assert "modules" in result.output
        # Next-step pointer: "Next up:" is the learner's forward-arrow.
        # On a fresh install this points at the first module.
        assert "Next up:" in result.output
        # Wallet-blocker pedagogy: when no wallet, status surfaces the
        # exact next command, not a generic "wallet missing" line.
        assert "No wallet yet" in result.output
        assert "xrpl-lab wallet create" in result.output

    def test_status_with_wallet_pins_track_progress(
        self, tmp_path, monkeypatch,
    ):
        """Once a wallet exists, the wallet-blocker is gone and the
        track-progress summary becomes the dominant onboarding signal."""
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        s = LabState(wallet_address="rTEST123")
        save_state(s)

        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

        # Wallet line surfaces the address (not "not created yet").
        assert "rTEST123" in result.output
        # Track progress: each track shows fractional progress so the
        # learner sees they have foundations/dex/reserves/audit/amm work.
        assert "foundations" in result.output
        # Network is testnet by default — pedagogy: this is the public
        # XRPL test network, not a local fake.
        assert "testnet" in result.output


def test_run_unknown_module():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_reset_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["reset"], input="no\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_reset_wrong_case(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["reset"], input="reset\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_doctor(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "Doctor" in result.output


class TestDoctorOutputPedagogy:
    """F-TESTS-C-001: pin the humanized doctor CLI surface.

    The `Check.hint` strings carry the doctor's "what to do next"
    contract. We pin both the broken-path (no wallet — clear failure
    cascade with actionable hints) and the happy-path doctor surface
    (panel header + section structure) so a refactor that strips the
    panel or the bare-stub hints regresses loud.
    """

    def test_doctor_no_wallet_surfaces_actionable_hint(
        self, tmp_path, monkeypatch,
    ):
        """In a clean tmp workspace with no wallet, doctor surfaces the
        wallet-missing failure with the canonical recovery command."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws",
        )
        # Stub network checks so the assertion isn't network-dependent.
        from xrpl_lab.doctor import Check

        async def _stub_rpc() -> Check:
            return Check("RPC endpoint", True, "stub")

        async def _stub_faucet() -> Check:
            return Check("Faucet", True, "stub")

        monkeypatch.setattr("xrpl_lab.doctor._check_rpc", _stub_rpc)
        monkeypatch.setattr("xrpl_lab.doctor._check_faucet", _stub_faucet)

        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        # Panel header
        assert "Doctor" in result.output
        # Wallet section pins the actionable recovery command. The hint
        # text in doctor.py:_check_wallet is "Run: xrpl-lab wallet create".
        assert "Wallet" in result.output
        assert "Not found" in result.output
        assert "xrpl-lab wallet create" in result.output

    def test_doctor_summary_format_pinned(self, tmp_path, monkeypatch):
        """The N/M summary line is part of the at-a-glance contract."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws",
        )

        from xrpl_lab.doctor import Check

        async def _stub_rpc() -> Check:
            return Check("RPC endpoint", True, "stub")

        async def _stub_faucet() -> Check:
            return Check("Faucet", True, "stub")

        monkeypatch.setattr("xrpl_lab.doctor._check_rpc", _stub_rpc)
        monkeypatch.setattr("xrpl_lab.doctor._check_faucet", _stub_faucet)

        runner = CliRunner()
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0
        # Summary must use the "N/M checks passed" wording.
        assert "checks passed" in result.output


def test_proof_pack_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["proof-pack"])
    assert result.exit_code == 0
    assert "No completed modules" in result.output


def test_certificate_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["certificate"])
    assert result.exit_code == 0
    assert "No completed modules" in result.output


def test_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.workshop.get_workspace_dir", lambda: tmp_path / "ws")
    runner = CliRunner()
    result = runner.invoke(main, ["feedback"])
    assert result.exit_code == 0
    assert "XRPL Lab Support Bundle" in result.output
    assert "Doctor" in result.output


def test_self_check(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    runner = CliRunner()
    result = runner.invoke(main, ["self-check"])
    assert result.exit_code == 0
    assert "Doctor" in result.output


# ── proof verify ──────────────────────────────────────────────────────


def test_proof_verify_valid(tmp_path):
    """Verify a valid proof pack passes."""
    import hashlib
    import json

    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "completed_modules": [],
        "total_transactions": 0,
    }
    content = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode()).hexdigest()

    path = tmp_path / "proof.json"
    path.write_text(json.dumps(pack), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["proof", "verify", str(path)])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_proof_verify_tampered(tmp_path):
    """Verify a tampered proof pack fails."""
    import hashlib
    import json

    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "completed_modules": [],
        "total_transactions": 0,
    }
    content = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    pack["address"] = "rTampered"  # tamper after hash

    path = tmp_path / "proof.json"
    path.write_text(json.dumps(pack), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["proof", "verify", str(path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_proof_verify_json_output(tmp_path):
    """Verify --json produces machine-readable output."""
    import hashlib
    import json

    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "completed_modules": [],
        "total_transactions": 0,
    }
    content = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode()).hexdigest()

    path = tmp_path / "proof.json"
    path.write_text(json.dumps(pack), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["proof", "verify", str(path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["valid"] is True
    assert data["address"] == "rTest123"


def test_cert_verify_valid(tmp_path):
    """Verify a valid certificate passes."""
    import hashlib
    import json

    cert = {
        "xrpl_lab_certificate": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "total_modules": 3,
        "total_transactions": 10,
    }
    content = json.dumps(cert, sort_keys=True, separators=(",", ":"))
    cert["sha256"] = hashlib.sha256(content.encode()).hexdigest()

    path = tmp_path / "cert.json"
    path.write_text(json.dumps(cert), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["cert-verify", str(path)])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_cert_verify_tampered(tmp_path):
    """Verify a tampered certificate fails."""
    import hashlib
    import json

    cert = {
        "xrpl_lab_certificate": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "total_modules": 3,
        "total_transactions": 10,
    }
    content = json.dumps(cert, sort_keys=True, separators=(",", ":"))
    cert["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    cert["total_modules"] = 99  # tamper

    path = tmp_path / "cert.json"
    path.write_text(json.dumps(cert), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["cert-verify", str(path)])
    assert result.exit_code == 1
    assert "FAIL" in result.output


# ── serve command ─────────────────────────────────────────────────────


def test_serve_command_is_registered():
    """The 'serve' command must exist in the CLI group."""
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output.lower() or "Start" in result.output


def test_serve_has_port_option():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output


def test_serve_has_host_option():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output


def test_serve_has_dry_run_option():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_serve_default_port_is_8321():
    """Verify the serve command's --port option defaults to 8321."""
    # Inspect the Click command object directly rather than relying on help text
    serve_cmd = main.commands["serve"]
    port_param = next(p for p in serve_cmd.params if p.name == "port")
    assert port_param.default == 8321


def test_serve_dry_run_launches_with_dry_run_app(monkeypatch):
    """serve --dry-run should call create_app(dry_run=True) and pass it to uvicorn."""

    captured = {}

    def fake_create_app(dry_run=False):
        captured["dry_run"] = dry_run
        # Return a minimal stand-in — uvicorn.run will be mocked anyway
        return object()

    def fake_uvicorn_run(app, host, port):
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("xrpl_lab.server.create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--dry-run", "--port", "9999", "--host", "0.0.0.0"])
    assert result.exit_code == 0
    assert captured.get("dry_run") is True
    assert captured.get("port") == 9999
    assert captured.get("host") == "0.0.0.0"


def test_serve_testnet_mode_by_default(monkeypatch):
    """serve without --dry-run should call create_app(dry_run=False)."""

    captured = {}

    def fake_create_app(dry_run=False):
        captured["dry_run"] = dry_run
        return object()

    def fake_uvicorn_run(app, host, port):
        pass

    monkeypatch.setattr("xrpl_lab.server.create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(main, ["serve"])
    assert result.exit_code == 0
    assert captured.get("dry_run") is False


# ── audit --no-pack ───────────────────────────────────────────────────


def _make_fake_audit_report():
    """Build a minimal mock AuditReport that satisfies cli.py's interface."""
    report = MagicMock()
    report.total = 1
    report.passed = 1
    report.failed = 0
    report.not_found = 0
    report.failure_summary.return_value = {}
    return report


def test_audit_no_pack_skips_pack_write(tmp_path, monkeypatch):
    """--no-pack must prevent write_audit_pack from being called."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    (ws / "reports").mkdir(parents=True, exist_ok=True)
    (ws / "proofs").mkdir(parents=True, exist_ok=True)

    txids_file = tmp_path / "txids.txt"
    txid = "AAAA1111BBBB2222CCCC3333DDDD4444EEEE5555FFFF6666AAAA1111BBBB2222"
    txids_file.write_text(f"{txid}\n", encoding="utf-8")

    pack_written = []

    import xrpl_lab.audit as audit_mod

    def fake_write_pack(report, path):
        pack_written.append(str(path))

    monkeypatch.setattr(audit_mod, "write_audit_pack", fake_write_pack)

    async def fake_run_audit(transport, txids, config):
        return _make_fake_audit_report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)

    runner = CliRunner()
    result = runner.invoke(main, [
        "audit",
        "--txids", str(txids_file),
        "--dry-run",
        "--no-pack",
    ])
    assert result.exit_code == 0, result.output
    assert pack_written == [], f"Expected no pack written, but got: {pack_written}"


def test_audit_writes_pack_by_default(tmp_path, monkeypatch):
    """Without --no-pack, write_audit_pack must be called."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    (ws / "reports").mkdir(parents=True, exist_ok=True)
    (ws / "proofs").mkdir(parents=True, exist_ok=True)

    txids_file = tmp_path / "txids.txt"
    txid = "AAAA1111BBBB2222CCCC3333DDDD4444EEEE5555FFFF6666AAAA1111BBBB2222"
    txids_file.write_text(f"{txid}\n", encoding="utf-8")

    pack_written = []

    import xrpl_lab.audit as audit_mod

    def fake_write_pack(report, path):
        pack_written.append(str(path))

    monkeypatch.setattr(audit_mod, "write_audit_pack", fake_write_pack)

    async def fake_run_audit(transport, txids, config):
        return _make_fake_audit_report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)

    runner = CliRunner()
    result = runner.invoke(main, [
        "audit",
        "--txids", str(txids_file),
        "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    assert len(pack_written) == 1, f"Expected pack written once, got: {pack_written}"


# ── F-TESTS-C-003: pin the recovery CLI surface ───────────────────────


class TestRecoveryOutput:
    """Pin the wave-3 humanized recovery output (commit 6c75e1f).

    Two distinct branches:

    1. ``no known blockers`` — surfaces the next-step pointers
       (xrpl-lab start + xrpl-lab status). The wave-1 message was a
       bare affirmation; the humanized branch teaches what to do next.

    2. stuck-state recovery — when there's a real blocker (e.g. no
       wallet yet), the hint surfaces:
       * the situation phrase (so the learner can recognize their state)
       * the concrete command to run
       * an explanation that teaches the underlying XRPL concept

    These are the load-bearing pedagogical strings — not whole
    paragraphs, just the concept markers a future refactor must keep.
    """

    def test_recovery_no_blockers_pins_next_steps(
        self, tmp_path, monkeypatch,
    ):
        """Wallet present + no missing prereqs + receipt_literacy is the
        next module (testnet, no requires) → no recovery hints fire.
        The 'no known blockers' branch must surface BOTH next-step
        pointers (start AND status) per F-BACKEND-C-010."""
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        s = LabState(wallet_address="rTEST123")
        save_state(s)

        runner = CliRunner()
        result = runner.invoke(main, ["recovery"])
        assert result.exit_code == 0

        # The "all clear" affirmation.
        assert "No known blockers found" in result.output
        # The pedagogical lift over the wave-1 affirmation: BOTH
        # next-step pointers surface so a learner who sees this knows
        # exactly how to advance.
        assert "xrpl-lab start" in result.output
        assert "xrpl-lab status" in result.output

    def test_recovery_no_wallet_teaches_wallet_concept(
        self, tmp_path, monkeypatch,
    ):
        """Stuck-state branch: no wallet yet. Recovery surfaces the
        canonical command AND teaches the XRPL wallet concept (the
        F-BACKEND-C-008 humanization)."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)

        runner = CliRunner()
        result = runner.invoke(main, ["recovery"])
        assert result.exit_code == 0

        # Situation phrase
        assert "No wallet yet" in result.output
        # Concrete recovery command
        assert "xrpl-lab wallet create" in result.output
        # Pedagogy: a wallet signs transactions / proves control. The
        # full humanized hint includes "signs your" + "transactions"
        # (Rich wraps at the terminal width, so we pin discrete tokens
        # rather than the full phrase).
        assert "signs your" in result.output
        assert "proves you control" in result.output
        # Storage-location pedagogy: ~/.xrpl-lab/wallet.json, owner-only.
        assert "owner-only" in result.output


# ── F-TESTS-C-004 + F-TESTS-C-007: --help pedagogical content ─────────


class TestHelpPedagogy:
    """Pin the wave-1 + wave-3 humanized --help content.

    Backend P1's commit 6c75e1f rewrote --dry-run and --force help to
    teach when to use the flag, not just describe it. The serve --help
    --dry-run is intentionally left as the bare 'Offline sandbox for
    all operations' line — the pedagogy lives on the START and RUN
    entry points where learners actually pass --dry-run.
    """

    def test_start_dry_run_help_teaches_when_to_use_sandbox(self):
        """F-BACKEND-C-004: start --dry-run --help teaches the two
        canonical use-cases — learn-without-network, repeat-without-
        consuming-faucet-requests.

        Click line-wraps the long --help text, so we pin discrete
        tokens that survive any wrap point rather than the full
        phrase."""
        runner = CliRunner()
        result = runner.invoke(main, ["start", "--help"])
        assert result.exit_code == 0
        # Concept: simulated transactions, won't hit testnet.
        assert "simulated" in result.output
        assert "won't execute on" in result.output
        # Concept: repeat modules without consuming faucet requests.
        # "consuming testnet faucet requests" is the longest unwrapped
        # phrase that survives Click's terminal-width wrapping.
        assert "consuming testnet faucet requests" in result.output

    def test_run_dry_run_help_teaches_sandbox_semantics(self):
        """run --dry-run also teaches sandbox semantics. Same
        humanized text as start — both are F-BACKEND-C-004 surfaces."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "simulated" in result.output
        assert "consuming testnet faucet requests" in result.output

    def test_run_force_help_explains_use_case(self):
        """F-BACKEND-C-009: --force isn't just 'redo' — help text says
        WHY you'd want to (practice / retry with different values)."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output
        # The use-case context that distinguishes the wave-3 humanized
        # text from the bare wave-1 "Re-run completed module" stub.
        assert "practice" in result.output or "retrying" in result.output

    def test_recovery_help_describes_diagnostic_surface(self):
        """F-TESTS-C-007: recovery --help mentions diagnosing stuck
        states (the value prop, not just 'show recovery commands')."""
        runner = CliRunner()
        result = runner.invoke(main, ["recovery", "--help"])
        assert result.exit_code == 0
        # The "Diagnose stuck states" docstring leads.
        assert "stuck" in result.output.lower()

    def test_serve_dry_run_help_present(self):
        """F-TESTS-C-004: serve --help still surfaces --dry-run as a
        flag (the pedagogical text lives on start/run entry points;
        serve's flag stays terse). This pins that --dry-run isn't
        accidentally dropped from serve."""
        runner = CliRunner()
        result = runner.invoke(main, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        # The terse-but-present "Offline sandbox" framing carries the
        # wave-1 framing — pin "Offline sandbox" so a refactor either
        # keeps it OR upgrades to the longer humanized text (both
        # acceptable; the regression is dropping the concept entirely).
        assert "sandbox" in result.output.lower()

    def test_run_force_already_completed_surfaces_force_pedagogy(
        self, tmp_path, monkeypatch,
    ):
        """F-BACKEND-C-006: when a module is already completed and
        --force is NOT passed, the message clarifies --force semantics
        (progress updates; previous tx IDs preserved in the proof
        pack). Pin those load-bearing phrases."""
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        ws = tmp_path / "ws"
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
        s = LabState(wallet_address="rTEST123")
        s.complete_module("receipt_literacy")
        save_state(s)

        runner = CliRunner()
        result = runner.invoke(main, ["run", "receipt_literacy"])
        assert result.exit_code == 0
        # Pedagogy: --force is the redo flag.
        assert "--force" in result.output
        # Concept: progress and reports get updated.
        assert "progress" in result.output.lower()
        # Concept: the proof pack preserves prior txids — historical
        # truth isn't lost.
        assert "preserved" in result.output or "preserve" in result.output
