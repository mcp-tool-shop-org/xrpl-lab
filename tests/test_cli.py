"""CLI smoke tests — offline only."""

from click.testing import CliRunner

from xrpl_lab.cli import main


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.10.0" in result.output


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
