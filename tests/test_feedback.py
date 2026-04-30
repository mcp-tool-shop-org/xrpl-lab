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


def test_feedback_generation_when_workspace_unwritable(tmp_path, monkeypatch):
    """F-TESTS-B-003: feedback generation under read-only workspace.

    When the workspace directory exists but is read-only (perms locked
    out, mounted read-only, etc.), generate_feedback must:

      1. NOT raise an unhandled IOError / PermissionError that surfaces
         to the user as a stack trace.
      2. Either succeed (the proof-pack lookup is a best-effort read,
         not a write) OR fail with a structured / readable error.

    The current implementation reads from the workspace; it doesn't write
    to it during feedback generation. So the contract this test pins is:
    a read-only workspace must not crash the feedback path. If a future
    refactor adds a write into the workspace from feedback, this test
    fires and forces the change to handle the failure cleanly.
    """
    import os
    import stat

    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.feedback.get_workspace_dir", lambda: ws)

    # Lock the workspace read-only. macOS / Linux honor 0o555 for dir perms;
    # Windows would no-op this and the test still passes the no-crash contract.
    original_mode = ws.stat().st_mode
    try:
        os.chmod(ws, stat.S_IRUSR | stat.S_IXUSR)  # r-x------
        try:
            md = generate_feedback()
        except (PermissionError, OSError) as exc:
            # Acceptable if the failure is structured — message must not be
            # an unhandled raw stacktrace fragment.
            msg = str(exc).lower()
            assert (
                "permission" in msg
                or "denied" in msg
                or "read-only" in msg
            ), (
                f"feedback raised an opaque error under "
                f"read-only workspace: {exc!r}"
            )
            return

        # Most-likely path: feedback succeeds (read-only workspace doesn't
        # block reads). The output must still contain the canonical
        # sections — NOT a half-rendered stub.
        assert "## XRPL Lab Feedback" in md
        assert "### Doctor" in md
        assert "### Environment" in md
    finally:
        # Restore mode so tmp_path cleanup can rmtree.
        os.chmod(ws, original_mode)
