"""Wave-7/8 api-cli — F-54b8db18 / F-ad988398.

``xrpl-lab audit`` already seals packs via ``write_audit_pack`` (integrity_sha256),
and ``verify_audit_pack`` exists in audit.py, but there is no product CLI entry
point. Proof and certificate families close the loop (``proof verify``,
``cert-verify``); audit packs leave it open.

Fix under test: ``xrpl-lab audit-verify <file> [--json]`` calls existing
``verify_audit_pack`` and exits non-zero on mismatch — mirror cert-verify shape.

Call-site enumeration (product):
  write_audit_pack  — cli.py audit; handlers.py (out of domain)
  verify_audit_pack — audit.py definition only until this command wires it

Run in isolation:
    python -m pytest tests/test_w7_api_cli_audit_verify.py -q
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from xrpl_lab.cli import main


@pytest.mark.asyncio
async def test_audit_verify_valid_pack_exits_zero(tmp_path):
    """Clean pack from write_audit_pack must PASS via audit-verify."""
    from xrpl_lab.audit import run_audit, write_audit_pack
    from xrpl_lab.transport.dry_run import DryRunTransport

    report = await run_audit(DryRunTransport(), ["TX1", "TX2"])
    path = tmp_path / "audit_pack.json"
    write_audit_pack(report, path)

    runner = CliRunner()
    result = runner.invoke(main, ["audit-verify", str(path)])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output


@pytest.mark.asyncio
async def test_audit_verify_tampered_pack_exits_nonzero(tmp_path):
    """Mutating a hashed field must FAIL audit-verify (exit != 0)."""
    from xrpl_lab.audit import run_audit, write_audit_pack
    from xrpl_lab.transport.dry_run import DryRunTransport

    report = await run_audit(DryRunTransport(), ["TX1", "TX2"])
    path = tmp_path / "audit_pack.json"
    write_audit_pack(report, path)

    pack = json.loads(path.read_text(encoding="utf-8"))
    pack["summary"]["passed"] = pack["summary"]["passed"] + 99
    path.write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["audit-verify", str(path)])
    assert result.exit_code != 0, result.output
    assert "FAIL" in result.output


@pytest.mark.asyncio
async def test_audit_verify_json_output(tmp_path):
    """--json yields machine-readable valid/message (parity with cert-verify)."""
    from xrpl_lab.audit import run_audit, write_audit_pack
    from xrpl_lab.transport.dry_run import DryRunTransport

    report = await run_audit(DryRunTransport(), ["TX1"])
    path = tmp_path / "audit_pack.json"
    write_audit_pack(report, path)

    runner = CliRunner()
    result = runner.invoke(main, ["audit-verify", str(path), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["valid"] is True
    assert "integrity" in data or "sha256" in data or data.get("message")


def test_audit_verify_command_is_registered():
    """Click must expose audit-verify (not only the library verifier)."""
    runner = CliRunner()
    result = runner.invoke(main, ["audit-verify", "--help"])
    assert result.exit_code == 0, result.output
    assert "FILE" in result.output or "file" in result.output.lower()
