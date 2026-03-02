"""CLI smoke tests — offline only."""

from click.testing import CliRunner

from xrpl_lab.cli import main


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_list():
    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    # Rich table may truncate IDs in narrow terminals
    assert "receipt_liter" in result.output
    assert "failure_liter" in result.output


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
