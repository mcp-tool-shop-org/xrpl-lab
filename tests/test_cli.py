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
    # Rich table truncates IDs — check short prefixes (8 modules = narrower cols)
    assert "receipt_lit" in result.output
    assert "failure_lit" in result.output
    assert "trust_line" in result.output
    assert "dex_lite" in result.output
    assert "reserves" in result.output
    assert "account_hy" in result.output
    assert "receipt_au" in result.output
    assert "amm_liquid" in result.output
    assert "dex_market" in result.output
    assert "dex_invent" in result.output
    assert "dex_vs_amm" in result.output


def test_status(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Status" in result.output


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
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")
    runner = CliRunner()
    result = runner.invoke(main, ["feedback"])
    assert result.exit_code == 0
    assert "XRPL Lab Feedback" in result.output
    assert "Doctor" in result.output


def test_self_check(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    runner = CliRunner()
    result = runner.invoke(main, ["self-check"])
    assert result.exit_code == 0
    assert "Doctor" in result.output


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
