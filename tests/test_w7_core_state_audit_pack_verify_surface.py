"""Wave-7/8 core-state — audit-pack verify product surface (F-ad988398 / F-c2d0587d).

``verify_audit_pack`` exists and seals trust in tests, but had no product-facing
callable beyond the raw function. This suite pins:

1. ``verify_audit_pack_surface`` — structured result with SIMULATED parity.
2. ``is_audit_pack`` — marker detection for /api/verify auto-detect.
3. ``verify_offline_artifact`` — reporting auto-detect that routes audit packs
   through the same integrity check (library half; CLI Click stays api-cli).
"""

from __future__ import annotations

import json

import pytest

from xrpl_lab.audit import (
    is_audit_pack,
    run_audit,
    verify_audit_pack,
    verify_audit_pack_surface,
    write_audit_pack,
)
from xrpl_lab.reporting import verify_offline_artifact
from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.mark.asyncio
async def test_verify_audit_pack_surface_clean_dry_run(tmp_path):
    """Product surface must verify a clean dry-run pack and flag SIMULATED."""
    transport = DryRunTransport()
    report = await run_audit(transport, ["TX1", "TX2"], dry_run=True)
    path = tmp_path / "pack.json"
    write_audit_pack(report, path)
    pack = json.loads(path.read_text(encoding="utf-8"))

    result = verify_audit_pack_surface(pack)

    assert result["artifact_kind"] == "audit_pack"
    assert result["hash_valid"] is True
    assert result["overall_passed"] is True
    assert "verified" in result["hash_message"].lower()
    assert result["simulated"] is True, (
        "dry-run audit packs must surface simulated=True (SIMULATED banner parity "
        "with proof verify / cert-verify)"
    )
    assert str(result.get("network", "")).lower() in ("dry-run", "dry_run")


@pytest.mark.asyncio
async def test_verify_audit_pack_surface_detects_tamper(tmp_path):
    transport = DryRunTransport()
    report = await run_audit(transport, ["TX1"])
    path = tmp_path / "pack.json"
    write_audit_pack(report, path)
    pack = json.loads(path.read_text(encoding="utf-8"))
    pack["summary"]["passed"] = pack["summary"]["passed"] + 99

    result = verify_audit_pack_surface(pack)

    assert result["hash_valid"] is False
    assert result["overall_passed"] is False
    assert "mismatch" in result["hash_message"].lower()


def test_is_audit_pack_marker():
    assert is_audit_pack({"tool": "xrpl-lab", "verdicts": []}) is True
    assert is_audit_pack({"xrpl_lab_proof_pack": True}) is False
    assert is_audit_pack({"xrpl_lab_certificate": True}) is False
    assert is_audit_pack("not a dict") is False


@pytest.mark.asyncio
async def test_verify_offline_artifact_auto_detects_audit_pack(tmp_path):
    """reporting.verify_offline_artifact must accept audit packs (API half)."""
    transport = DryRunTransport()
    report = await run_audit(transport, ["TX1"], dry_run=True)
    path = tmp_path / "pack.json"
    write_audit_pack(report, path)
    pack = json.loads(path.read_text(encoding="utf-8"))

    # Raw verifier still works (unchanged contract).
    valid, _ = verify_audit_pack(pack)
    assert valid

    result = verify_offline_artifact(pack)
    assert result["artifact_kind"] == "audit_pack"
    assert result["hash_valid"] is True
    assert result["simulated"] is True


def test_verify_offline_artifact_unknown():
    result = verify_offline_artifact({"foo": 1})
    assert result["artifact_kind"] == "unknown"
    assert result["hash_valid"] is False
