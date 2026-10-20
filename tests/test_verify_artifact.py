"""Unified `xrpl-lab verify-artifact <file>` — marker-based detection + dispatch.

The tool emits FOUR tamper-evident / well-formedness-sealed JSON artifacts:
proof packs, certificates, audit packs, support bundles. Historically each had
its own verify entry point (proof verify / cert-verify / audit-verify /
support-bundle --verify); verify-artifact is the single surface that detects
the kind from the artifact's OWN markers and dispatches to the SAME existing
verification core the native command uses.

Also pinned here: the deprecated fragmentation surfaces keep their behavior and
exit codes while printing a one-line stderr note, and the three pure aliases
(self-check, feedback, proof generate) still run but are hidden from --help.

Run in isolation:
    python -m pytest tests/test_verify_artifact.py -q
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from xrpl_lab.cli import main

# ── Artifact fixtures (mirrors test_cli.py / test_w7_api_cli_audit_verify.py) ──


def _hashable_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _write_proof_pack(path: Path, tamper: bool = False, **extra) -> None:
    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "completed_modules": [],
        "total_transactions": 0,
        **extra,
    }
    content = _hashable_json(pack)
    pack["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    if tamper:
        pack["address"] = "rTampered"  # edit AFTER hashing
    path.write_text(json.dumps(pack), encoding="utf-8")


def _write_certificate(path: Path, tamper: bool = False) -> None:
    cert = {
        "xrpl_lab_certificate": True,
        "version": "1.0.0",
        "network": "testnet",
        "address": "rTest123",
        "total_modules": 3,
        "total_transactions": 10,
    }
    content = _hashable_json(cert)
    cert["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    if tamper:
        cert["total_modules"] = 99
    path.write_text(json.dumps(cert), encoding="utf-8")


def _write_support_bundle(path: Path, **extra) -> None:
    bundle = {
        "schema": "xrpl-lab-support-bundle-v1",
        "version": "1.0",
        "generated": "2026-01-01T00:00:00Z",
        "learner": {"version": "1.0", "completed_count": 0, "total_modules": 0},
        "network": "testnet",
        **extra,
    }
    path.write_text(json.dumps(bundle), encoding="utf-8")


async def _write_audit_pack(path: Path) -> None:
    """Real pack via the same generator the audit command uses (dry-run)."""
    from xrpl_lab.audit import run_audit, write_audit_pack
    from xrpl_lab.transport.dry_run import DryRunTransport

    report = await run_audit(DryRunTransport(), ["TX1", "TX2"])
    write_audit_pack(report, path)


def _help_listed_commands(help_text: str) -> set[str]:
    """First-token set of rows in a click ``Commands:`` listing section."""
    section = help_text.split("Commands:", 1)[-1]
    return {ln.split()[0] for ln in section.splitlines() if ln.strip()}


# ── Detection + dispatch per artifact kind ────────────────────────────────


class TestVerifyArtifactKinds:
    def test_proof_pack_passes(self, tmp_path):
        path = tmp_path / "pack.json"
        _write_proof_pack(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 0, result.output
        assert "Artifact:" in result.output
        assert "proof pack" in result.output
        assert "PASS" in result.output
        # The unified command is the replacement — it must not deprecate itself.
        assert result.stderr == ""

    def test_proof_pack_tampered_fails(self, tmp_path):
        path = tmp_path / "pack.json"
        _write_proof_pack(path, tamper=True)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        assert "FAIL" in result.output

    def test_certificate_passes(self, tmp_path):
        path = tmp_path / "cert.json"
        _write_certificate(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 0, result.output
        assert "certificate" in result.output
        assert "PASS" in result.output

    def test_certificate_tampered_fails(self, tmp_path):
        path = tmp_path / "cert.json"
        _write_certificate(path, tamper=True)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        assert "FAIL" in result.output

    @pytest.mark.asyncio
    async def test_audit_pack_passes(self, tmp_path):
        path = tmp_path / "audit_pack.json"
        await _write_audit_pack(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 0, result.output
        assert "audit pack" in result.output
        assert "PASS" in result.output

    def test_support_bundle_passes(self, tmp_path):
        path = tmp_path / "bundle.json"
        _write_support_bundle(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 0, result.output
        assert "support bundle" in result.output
        assert "well-formed" in result.output

    def test_support_bundle_missing_fields_fails(self, tmp_path):
        """Bundle-shaped file missing required fields → FAIL (not 'unknown')."""
        path = tmp_path / "bundle.json"
        _write_support_bundle(path, learner={})
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        assert "FAIL" in result.output

    def test_ambiguous_markers_prefer_proof_pack(self, tmp_path):
        """A file carrying BOTH markers is verified by the marker-bearing check."""
        path = tmp_path / "ambiguous.json"
        _write_proof_pack(path, schema="xrpl-lab-support-bundle-v1")
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 0, result.output
        assert "proof pack" in result.output
        assert "PASS" in result.output


# ── Error surfaces ─────────────────────────────────────────────────────────


class TestVerifyArtifactErrors:
    def test_unknown_kind_exit_1_and_names_kinds(self, tmp_path):
        path = tmp_path / "mystery.json"
        path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        # Rich wraps long console lines — collapse whitespace before matching.
        flat = " ".join(result.output.split())
        for kind in ("proof pack", "certificate", "audit pack", "support bundle"):
            assert kind in flat

    def test_json_array_is_unknown_kind(self, tmp_path):
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        assert "Unrecognized artifact" in result.output

    def test_invalid_json_exit_1(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        result = CliRunner().invoke(main, ["verify-artifact", str(path)])
        assert result.exit_code == 1, result.output
        assert "Invalid JSON" in result.output

    def test_unreadable_file_is_clean_failure(self, tmp_path, monkeypatch):
        """COREBCD-005 parity: guarded read, no traceback, no abs-path leak."""
        target = tmp_path / "pack.json"
        target.write_text("{}", encoding="utf-8")
        abs_path = str(target)

        real_read_text = Path.read_text

        def boom(self, *args, **kwargs):
            if self == target:
                raise PermissionError(13, "Permission denied", abs_path)
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", boom)
        result = CliRunner().invoke(main, ["verify-artifact", abs_path])
        assert result.exit_code == 1
        assert not isinstance(result.exception, PermissionError)
        assert abs_path not in result.output


# ── --json output ───────────────────────────────────────────────────────────


class TestVerifyArtifactJson:
    def test_proof_pack_json(self, tmp_path):
        path = tmp_path / "pack.json"
        _write_proof_pack(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["artifact_kind"] == "proof_pack"
        assert data["address"] == "rTest123"
        assert data["sha256"]

    def test_certificate_json(self, tmp_path):
        path = tmp_path / "cert.json"
        _write_certificate(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["artifact_kind"] == "certificate"

    @pytest.mark.asyncio
    async def test_audit_pack_json(self, tmp_path):
        path = tmp_path / "audit_pack.json"
        await _write_audit_pack(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["artifact_kind"] == "audit_pack"
        assert data["integrity_sha256"]

    def test_support_bundle_json(self, tmp_path):
        path = tmp_path / "bundle.json"
        _write_support_bundle(path)
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["artifact_kind"] == "support_bundle"

    def test_unknown_kind_json(self, tmp_path):
        path = tmp_path / "mystery.json"
        path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["artifact_kind"] == "unknown"
        assert "proof pack" in data["message"]

    def test_invalid_json_json(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        result = CliRunner().invoke(main, ["verify-artifact", str(path), "--json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["message"].startswith("Invalid JSON")


# ── Deprecated native verify commands: unchanged surface + stderr note ──────


class TestDeprecatedVerifyCommands:
    def test_proof_verify_still_works_with_note(self, tmp_path):
        path = tmp_path / "pack.json"
        _write_proof_pack(path)
        result = CliRunner().invoke(main, ["proof", "verify", str(path)])
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert result.stderr == "`proof verify` is deprecated, use `verify-artifact`.\n"

    def test_cert_verify_still_works_with_note(self, tmp_path):
        path = tmp_path / "cert.json"
        _write_certificate(path)
        result = CliRunner().invoke(main, ["cert-verify", str(path)])
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert result.stderr == "`cert-verify` is deprecated, use `verify-artifact`.\n"

    @pytest.mark.asyncio
    async def test_audit_verify_still_works_with_note(self, tmp_path):
        path = tmp_path / "audit_pack.json"
        await _write_audit_pack(path)
        result = CliRunner().invoke(main, ["audit-verify", str(path)])
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert result.stderr == "`audit-verify` is deprecated, use `verify-artifact`.\n"

    def test_support_bundle_verify_still_works_with_note(self, tmp_path):
        path = tmp_path / "bundle.json"
        _write_support_bundle(path)
        result = CliRunner().invoke(main, ["support-bundle", "--verify", str(path)])
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert result.stderr == (
            "`support-bundle --verify` is deprecated, use `verify-artifact`.\n"
        )

    def test_support_bundle_generate_has_no_note(self, tmp_path, monkeypatch):
        """Only the --verify flag is deprecated; plain generation stays silent."""
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws",
        )
        monkeypatch.setattr(
            "xrpl_lab.workshop.get_workspace_dir", lambda: tmp_path / "ws",
        )
        result = CliRunner().invoke(main, ["support-bundle"])
        assert result.exit_code == 0, result.output
        assert result.stderr == ""

    def test_proof_verify_tampered_still_fails_with_note(self, tmp_path):
        path = tmp_path / "pack.json"
        _write_proof_pack(path, tamper=True)
        result = CliRunner().invoke(main, ["proof", "verify", str(path)])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert result.stderr == "`proof verify` is deprecated, use `verify-artifact`.\n"

    def test_deprecated_commands_still_visible_in_help(self):
        """Deprecated verify entries are demoted by note, not hidden."""
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        listed = _help_listed_commands(result.output)
        assert "cert-verify" in listed
        assert "audit-verify" in listed
        assert "support-bundle" in listed
        assert "verify-artifact" in listed
        proof_help = CliRunner().invoke(main, ["proof", "--help"])
        assert "verify" in _help_listed_commands(proof_help.output)


# ── Hidden pure aliases: still run, absent from help, note on stderr ────────


class TestHiddenAliases:
    def test_hidden_aliases_absent_from_main_help(self):
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        listed = _help_listed_commands(result.output)
        assert "self-check" not in listed
        assert "feedback" not in listed

    def test_proof_generate_absent_from_proof_help(self):
        result = CliRunner().invoke(main, ["proof", "--help"])
        assert result.exit_code == 0
        assert "generate" not in _help_listed_commands(result.output)

    def test_self_check_still_runs_with_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws",
        )
        result = CliRunner().invoke(main, ["self-check"])
        assert result.exit_code == 0, result.output
        assert "Doctor" in result.output
        assert result.stderr == "`self-check` is deprecated, use `doctor`.\n"

    def test_feedback_still_runs_with_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws",
        )
        monkeypatch.setattr(
            "xrpl_lab.workshop.get_workspace_dir", lambda: tmp_path / "ws",
        )
        result = CliRunner().invoke(main, ["feedback"])
        assert result.exit_code == 0, result.output
        assert "XRPL Lab Support Bundle" in result.output
        assert result.stderr == "`feedback` is deprecated, use `support-bundle`.\n"

    def test_proof_generate_still_runs_with_note(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        result = CliRunner().invoke(main, ["proof", "generate"])
        assert result.exit_code == 0, result.output
        assert "No completed modules" in result.output
        assert result.stderr == "`proof generate` is deprecated, use `proof-pack`.\n"
