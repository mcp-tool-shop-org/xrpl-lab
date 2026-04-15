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
