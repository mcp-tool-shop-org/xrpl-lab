"""Tests for the feedback generator."""

from xrpl_lab.feedback import generate_feedback


def test_feedback_basic(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")

    md = generate_feedback()
    assert "## XRPL Lab Feedback" in md
    assert "xrpl-lab v" in md
    assert "### Doctor" in md
    assert "### Environment" in md
    assert "### Progress" in md


def test_feedback_contains_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")

    md = generate_feedback()
    assert "RPC:" in md
    assert "Faucet:" in md


def test_feedback_with_proof_pack(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")

    # Create a mock proof pack
    proofs = tmp_path / "ws" / "proofs"
    proofs.mkdir(parents=True)
    pack = {
        "sha256": "abc123",
        "total_transactions": 5,
    }
    (proofs / "xrpl_lab_proof_pack.json").write_text(
        json.dumps(pack), encoding="utf-8"
    )

    md = generate_feedback()
    assert "### Proof Pack" in md
    assert "abc123" in md


def test_feedback_no_wallet(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: tmp_path / "ws")

    md = generate_feedback()
    # Should still work without a wallet
    assert "Modules completed: 0" in md
